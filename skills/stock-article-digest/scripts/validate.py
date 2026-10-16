#!/usr/bin/env python3
"""檢查一份摘要檔的格式，並用官方清單核對每個代號。

用法：validate.py stock-notes/2026-10-13-xxx.md
沒問題 exit 0；有錯誤 exit 1，錯誤與提醒印在 stdout。

front matter 只接受固定的寫法（見 SKILL.md），這裡用小型解析器讀，
不依賴 PyYAML。寫法跑掉就會被擋下來，這是刻意的：之後用程式掃
整個資料夾時，靠的就是每份檔案長得一樣。
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tickers import load  # noqa: E402

VOCAB = Path(__file__).resolve().parent.parent / "references" / "tag-vocabulary.md"

REQUIRED = ["date", "date_from", "processed", "title", "source", "mode",
            "tickers", "sectors", "tags", "new_tags"]
TICKER_RE = re.compile(r"^(TW|TWO|US|JP|KR|HK):([A-Z0-9][A-Z0-9.\-]*|\?)$")
BODY_TICKER_RE = re.compile(r"\[((?:TW|TWO|US|JP|KR|HK):(?:[A-Z0-9][A-Z0-9.\-]*|\?))\]")
SECTIONS = ["核心摘要", "產業鏈與概念股", "財務數據", "市場情緒與留言"]
# 刻意不收的段落：這份檔案只記錄原文，模型自己的分析與延伸閱讀不放進來
FORBIDDEN = ["深度問答", "延伸搜尋", "延伸參考", "延伸閱讀"]
CHAIN_HEADER = ["關鍵技術/元件", "關聯產業", "相關公司", "來源", "關聯說明"]
FIN_HEADER = ["公司", "項目", "數值", "期間", "原文依據", "備註"]


# ---------- front matter ----------

def split_top(s: str, sep: str = ",") -> list:
    """以 sep 切開，但忽略雙引號裡的。"""
    out, buf, quoted = [], [], False
    for ch in s:
        if ch == '"':
            quoted = not quoted
        if ch == sep and not quoted:
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return [x.strip() for x in out]


def scalar(s: str):
    s = s.strip()
    if len(s) >= 2 and s[0] == s[-1] == '"':
        return s[1:-1].replace('\\"', '"')
    return s


def parse_value(s: str):
    s = s.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        return [scalar(x) for x in split_top(inner)] if inner else []
    if s.startswith("{") and s.endswith("}"):
        d = {}
        for part in split_top(s[1:-1]):
            k, _, v = part.partition(":")
            d[k.strip()] = scalar(v)
        return d
    return scalar(s)


def parse_front_matter(text: str):
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        raise ValueError("檔案第一行必須是 ---")
    try:
        end = next(i for i in range(1, len(lines)) if lines[i].strip() == "---")
    except StopIteration:
        raise ValueError("front matter 沒有結尾的 ---")
    fm, key = {}, None
    for no, ln in enumerate(lines[1:end], start=2):
        if not ln.strip():
            continue
        if ln.startswith("  - ") or ln.startswith("- "):
            if key is None or not isinstance(fm.get(key), list):
                raise ValueError(f"第 {no} 行：清單項目前面沒有對應的鍵")
            fm[key].append(parse_value(ln.split("- ", 1)[1]))
            continue
        m = re.match(r"^([a-z_]+):(.*)$", ln)
        if not m:
            raise ValueError(f"第 {no} 行看不懂：{ln}")
        key, rest = m.group(1), m.group(2).strip()
        fm[key] = [] if rest == "" else parse_value(rest)
    return fm, "\n".join(lines[end + 1:])


# ---------- 標籤清單 ----------

def load_vocab():
    vocab, cur = {"sectors": set(), "tags": set()}, None
    for ln in VOCAB.read_text().split("\n"):
        if ln.startswith("## "):
            name = ln[3:].strip()
            cur = name if name in vocab else None
        elif cur and ln.startswith("- "):
            vocab[cur].add(ln[2:].split("（")[0].strip())
    return vocab


# ---------- 本文 ----------

def sections(body: str) -> dict:
    out, cur = {}, None
    for ln in body.split("\n"):
        if ln.startswith("## "):
            cur = ln[3:].strip()
            out[cur] = []
        elif cur is not None:
            out[cur].append(ln)
    return {k: "\n".join(v) for k, v in out.items()}


def table_rows(sec: str) -> list:
    rows = []
    for ln in sec.split("\n"):
        ln = ln.strip()
        if ln.startswith("|") and ln.endswith("|"):
            cells = [c.strip() for c in ln[1:-1].split("|")]
            if not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                rows.append(cells)
    return rows


def main(argv) -> int:
    if len(argv) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    text = Path(argv[0]).read_text()
    errors, warns = [], []

    try:
        fm, body = parse_front_matter(text)
    except ValueError as e:
        print(f"ERROR front matter：{e}")
        return 1

    for k in REQUIRED:
        if k not in fm:
            errors.append(f"front matter 缺少 {k}")
    date = fm.get("date", "")
    if date != "unknown" and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(date)):
        errors.append(f"date 必須是 YYYY-MM-DD 或 unknown，目前是 {date!r}")
    if date == "unknown" and fm.get("date_from") != "none":
        errors.append("date 是 unknown 時 date_from 要寫 none")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(fm.get("processed", ""))):
        errors.append("processed 必須是 YYYY-MM-DD")
    if fm.get("mode") not in ("digest", "full"):
        errors.append("mode 只能是 digest 或 full")

    # 標籤
    vocab = load_vocab()
    new_tags = set(fm.get("new_tags") or [])
    for field in ("sectors", "tags"):
        for t in fm.get(field) or []:
            if " " in t or "#" in t:
                errors.append(f"{field} 的「{t}」不能有空白或 #")
            elif t not in vocab[field] and t not in new_tags:
                errors.append(f"{field} 的「{t}」不在標籤清單，要嘛換成清單裡的字，要嘛列進 new_tags")
    for t in new_tags:
        warns.append(f"新標籤「{t}」：請人決定要不要收進 references/tag-vocabulary.md")

    # 代號
    tickers = fm.get("tickers") or []
    if not isinstance(tickers, list):
        errors.append("tickers 必須是清單")
        tickers = []
    data, net_warn = load()
    warns.extend(net_warn)
    index = {m: {r["code"]: r for r in rows} for m, rows in data.items()}
    fm_codes = set()
    for t in tickers:
        if not isinstance(t, dict):
            errors.append(f"tickers 項目格式錯誤：{t!r}")
            continue
        code, name = t.get("code", ""), t.get("name", "")
        fm_codes.add(code)
        if not TICKER_RE.match(code):
            errors.append(f"代號格式錯誤：{code!r}（要像 TW:2330、TWO:3324、US:NVDA）")
            continue
        if t.get("origin") not in ("原文", "補充"):
            errors.append(f"{code} 的 origin 只能是 原文 或 補充")
        verified = t.get("verified")
        if verified not in ("listed", "format-only", "not-found"):
            errors.append(f"{code} 的 verified 只能是 listed / format-only / not-found")
            continue
        market, num = code.split(":")
        if num == "?":
            if verified != "not-found":
                errors.append(f"{name} 代號是 ? 時 verified 要寫 not-found")
            warns.append(f"{name} 查不到代號，請人確認")
            continue
        if verified == "not-found":
            errors.append(f"{code} 已經寫了代號，verified 卻是 not-found")
            continue
        if market in ("TW", "TWO", "US") and not data.get(market):
            warns.append(f"{market} 清單無法取得，{code} 沒有核對")
            continue
        if verified == "format-only":
            # 只有清單本來就不收的才能免核對：日韓港股、台股 ETF（00 開頭）
            if market in ("TW", "TWO") and not num.startswith("00"):
                errors.append(f"{code} 是台股個股，必須查清單，不能寫 format-only")
            if market == "US":
                errors.append(f"{code} 是美股，必須查清單，不能寫 format-only")
            continue
        # verified == listed
        if market not in index:
            errors.append(f"{code}：{market} 沒有官方清單，verified 要寫 format-only")
            continue
        row = index[market].get(num)
        if row is None:
            other = "TWO" if market == "TW" else "TW" if market == "TWO" else None
            if other and num in index.get(other, {}):
                errors.append(f"{code} 市場寫錯，應為 {other}:{num}（{index[other][num]['short']}）")
            else:
                errors.append(f"{code} 在 {market} 清單裡找不到")
            continue
        if market in ("TW", "TWO"):
            if name != row["short"] and name not in row["name"]:
                errors.append(f"{code} 官方簡稱是「{row['short']}」，跟寫的「{name}」對不上，代號可能錯了")
            if t.get("industry") != row["industry"]:
                errors.append(f"{code} 的 industry 要照官方填「{row['industry']}」，目前是 {t.get('industry')!r}")

    # 本文段落
    secs = sections(body)
    for s in SECTIONS:
        if s not in secs:
            errors.append(f"缺少段落：## {s}")

    body_codes = set(BODY_TICKER_RE.findall(body))
    for c in sorted(body_codes - fm_codes):
        errors.append(f"本文出現 [{c}]，但 front matter 的 tickers 沒有")
    for c in sorted(fm_codes - body_codes):
        if TICKER_RE.match(c):
            errors.append(f"tickers 有 {c}，但本文沒出現 [{c}]")

    chain = secs.get("產業鏈與概念股", "")
    rows = table_rows(chain)
    if rows:
        if rows[0] != CHAIN_HEADER:
            errors.append(f"產業鏈表格欄位要是 {CHAIN_HEADER}，目前是 {rows[0]}")
        else:
            for r in rows[1:]:
                if len(r) != len(CHAIN_HEADER):
                    errors.append(f"產業鏈表格欄數不對：{r}")
                elif r[3] not in ("原文", "補充"):
                    errors.append(f"產業鏈表格「來源」只能填 原文 或 補充：{r}")
    elif "本文未提及" not in chain:
        errors.append("產業鏈與概念股：沒有表格，也沒寫「本文未提及」")

    fin = secs.get("財務數據", "")
    rows = table_rows(fin)
    if rows:
        if rows[0] != FIN_HEADER:
            errors.append(f"財務表格欄位要是 {FIN_HEADER}，目前是 {rows[0]}")
        else:
            for r in rows[1:]:
                if len(r) != len(FIN_HEADER) or not r[4] or r[4] in ("-", "—"):
                    errors.append(f"財務表格每一列都要有「原文依據」：{r}")
    elif "本文未提及" not in fin:
        errors.append("財務數據：沒有表格，也沒寫「本文未提及」")

    for s in secs:
        if any(f in s for f in FORBIDDEN):
            errors.append(f"不要有「## {s}」段落：只整理原文，不加自己的分析或延伸資料")

    for e in errors:
        print(f"ERROR {e}")
    for w in warns:
        print(f"WARN  {w}")
    if not errors:
        print("OK")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
