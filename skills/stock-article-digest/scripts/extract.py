#!/usr/bin/env python3
"""把網址或存下來的網頁原始碼抽成 JSON：標題、發布日期、正文、留言、圖片說明。

只用標準函式庫。用法：
  extract.py https://example.com/post/123
  extract.py saved-page.html

輸出欄位：
  source      網址或 local:<檔名>
  title       <title> 或 og:title
  published   YYYY-MM-DD；找不到為 null（不要自己猜）
  published_from  日期從哪裡讀到的，例如 meta:article:published_time
  body        正文純文字，段落以空行分隔
  comments    抓到的留言，每則一段純文字；抓不到是空陣列
  images      [{alt, caption}]，只收有文字線索的圖
  warnings    抽取過程的提醒，例如留言可能是後來才載入的
"""

import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tickers import fetch_bytes  # noqa: E402

BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36")

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link",
        "meta", "param", "source", "track", "wbr"}
DROP = {"script", "style", "noscript", "nav", "header", "footer", "aside",
        "form", "button", "svg", "iframe", "template"}
BLOCK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br",
         "blockquote", "section", "article", "pre", "table", "figcaption"}
# 留言區常見的 class / id 字樣；push 是 PTT 的推文
COMMENT_HINT = re.compile(r"comment|reply|respond|discuss|push(?!-?notif)", re.I)
DATE_META = [
    ("property", "article:published_time"),
    ("property", "og:published_time"),
    ("name", "pubdate"),
    ("name", "publishdate"),
    ("name", "publish-date"),
    ("name", "date"),
    ("itemprop", "datePublished"),
]


class Node:
    __slots__ = ("tag", "attrs", "children", "parent")

    def __init__(self, tag, attrs, parent):
        self.tag, self.attrs, self.parent = tag, dict(attrs), parent
        self.children = []


class TreeBuilder(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = Node("#root", [], None)
        self.cur = self.root

    def handle_starttag(self, tag, attrs):
        node = Node(tag, attrs, self.cur)
        self.cur.children.append(node)
        if tag not in VOID:
            self.cur = node

    def handle_startendtag(self, tag, attrs):
        self.cur.children.append(Node(tag, attrs, self.cur))

    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag:
            n = n.parent
        if n is not self.root:  # 找不到對應開頭就忽略這個結尾標籤
            self.cur = n.parent

    def handle_data(self, data):
        self.cur.children.append(data)


def walk(node):
    yield node
    for c in node.children:
        if isinstance(c, Node):
            yield from walk(c)


def text_of(node, skip=frozenset()) -> str:
    parts = []

    def rec(n):
        for c in n.children:
            if isinstance(c, str):
                parts.append(c)
            elif c.tag in DROP or id(c) in skip:
                continue
            else:
                if c.tag in BLOCK:
                    parts.append("\n")
                rec(c)
                if c.tag in BLOCK:
                    parts.append("\n")

    rec(node)
    lines = [re.sub(r"[ \t　\xa0]+", " ", ln).strip()
             for ln in "".join(parts).split("\n")]
    out, blank = [], False
    for ln in lines:
        if ln:
            out.append(ln)
            blank = False
        elif not blank and out:
            out.append("")
            blank = True
    return "\n".join(out).strip()


def decode(raw: bytes) -> str:
    head = raw[:4096].decode("ascii", "ignore")
    m = re.search(r'charset=["\']?([\w-]+)', head, re.I)
    candidates = ([m.group(1)] if m else []) + ["utf-8", "big5", "cp950"]
    for enc in candidates:
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def norm_date(s: str):
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", s or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    if not (1990 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def find_in_jsonld(obj):
    if isinstance(obj, dict):
        if "datePublished" in obj:
            return obj["datePublished"]
        obj = list(obj.values())
    if isinstance(obj, list):
        for v in obj:
            r = find_in_jsonld(v)
            if r:
                return r
    return None


def find_date(nodes):
    for attr, value in DATE_META:
        for n in nodes:
            if n.tag == "meta" and n.attrs.get(attr, "").lower() == value.lower():
                d = norm_date(n.attrs.get("content", ""))
                if d:
                    return d, f"meta:{value}"
    for n in nodes:
        if n.tag == "script" and "ld+json" in n.attrs.get("type", ""):
            raw = "".join(c for c in n.children if isinstance(c, str))
            try:
                d = norm_date(find_in_jsonld(json.loads(raw)) or "")
            except (json.JSONDecodeError, TypeError):
                continue
            if d:
                return d, "json-ld:datePublished"
    for n in nodes:
        if n.tag == "time" and n.attrs.get("datetime"):
            d = norm_date(n.attrs["datetime"])
            if d:
                return d, "time[datetime]"
    return None, None


def hint_of(n) -> str:
    return f"{n.attrs.get('class', '')} {n.attrs.get('id', '')}"


def find_comment_roots(nodes):
    """找最外層、名稱看起來像留言區的元素。"""
    roots = []
    for n in nodes:
        if n.tag in DROP or not COMMENT_HINT.search(hint_of(n)):
            continue
        p, nested = n.parent, False
        while p is not None:
            if p in roots:
                nested = True
                break
            p = p.parent
        if not nested:
            roots.append(n)
    return roots


CONTAINER = {"div", "li", "article", "section", "tr", "dd", "blockquote"}


def split_comments(root) -> list:
    """把留言區拆成一則一則。

    一則留言 = 名稱像留言、而且底下沒有其他「名稱像留言的區塊元素」的區塊元素。
    只看區塊元素，是為了不把 PTT 推文裡的 <span class="push-userid"> 這類
    行內欄位當成獨立留言。
    """
    blocks = [c for c in walk(root) if c.tag in CONTAINER
              and COMMENT_HINT.search(hint_of(c))]
    units = [c for c in blocks if not any(
        o is not c and _is_ancestor(c, o) for o in blocks)]
    texts = [" ".join(text_of(c).split()) for c in (units or [root])]
    return [t for t in texts if len(t) >= 2]


def _is_ancestor(a, b) -> bool:
    p = b.parent
    while p is not None:
        if p is a:
            return True
        p = p.parent
    return False


def find_body(nodes, skip_ids):
    """回傳正文所在的節點；找不到為 None。"""
    articles = [n for n in nodes if n.tag == "article"]
    candidates = articles or [n for n in nodes if n.tag in ("main", "div", "section")]
    best, best_len = None, 0
    for n in candidates:
        # 用段落文字長度挑正文容器，避開整頁 <body>
        plen = sum(len(text_of(p, skip_ids)) for p in walk(n) if p.tag == "p")
        if plen > best_len:
            best, best_len = n, plen
    if best is None or best_len < 200:
        # 沒有 <p> 的頁面（例如 PTT）：挑「最深、但文字量仍有全頁六成以上」的容器
        boxes = [(n, len(text_of(n, skip_ids))) for n in nodes
                 if n.tag in ("article", "main", "div", "section", "body")]
        if not boxes:
            return None
        top = max(length for _, length in boxes)
        best = max((n for n, length in boxes if length >= 0.6 * top), key=_depth)
    return best


def _depth(n) -> int:
    d = 0
    while n.parent is not None:
        n, d = n.parent, d + 1
    return d


def extract(raw: bytes, source: str) -> dict:
    tb = TreeBuilder()
    tb.feed(decode(raw))
    nodes = list(walk(tb.root))
    warnings = []

    title = None
    for n in nodes:
        if n.tag == "meta" and n.attrs.get("property") == "og:title":
            title = n.attrs.get("content", "").strip() or None
            break
    if not title:
        t = next((n for n in nodes if n.tag == "title"), None)
        title = text_of(t) if t else None

    published, published_from = find_date(nodes)
    if not published:
        warnings.append("找不到結構化的發布日期；正文裡若有明寫日期可以引用，否則填 unknown")

    comment_roots = find_comment_roots(nodes)
    comments = []
    for r in comment_roots:
        comments.extend(split_comments(r))
    if not comments:
        warnings.append("沒抓到留言。網址抓取常拿不到後來才載入的留言；"
                        "需要留言就在瀏覽器展開留言後另存網頁原始碼")

    skip_ids = {id(r) for r in comment_roots}
    body_node = find_body(nodes, skip_ids)
    body = text_of(body_node, skip_ids) if body_node else ""

    # 只收正文範圍裡的圖，側欄與推薦文章的縮圖不算
    images = []
    for n in (walk(body_node) if body_node else []):
        if n.tag == "img":
            alt = (n.attrs.get("alt") or "").strip()
            cap = None
            p = n.parent
            while p is not None and p.tag != "figure":
                p = p.parent
            if p is not None:
                fc = next((c for c in walk(p) if c.tag == "figcaption"), None)
                cap = text_of(fc) if fc else None
            if alt and re.search(r"icon|logo|avatar|arrow", alt, re.I):
                alt = ""  # 裝飾性圖示沒有內容線索
            item = {"alt": alt or None, "caption": cap}
            if ((alt and len(alt) > 1) or cap) and item not in images:
                images.append(item)

    return {
        "source": source,
        "title": title,
        "published": published,
        "published_from": published_from,
        "body": body,
        "comments": comments,
        "images": images,
        "warnings": warnings,
    }


def main(argv) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    arg = argv[0]
    if re.match(r"https?://", arg):
        raw, source = fetch_bytes(arg, BROWSER_UA), arg
    else:
        raw, source = Path(arg).read_bytes(), f"local:{Path(arg).name}"
    print(json.dumps(extract(raw, source), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
