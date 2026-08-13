#!/usr/bin/env python3
"""掃描檔案裡有沒有夾帶到本機的識別資訊。

跟一般的 secret scanner 不同，這支腳本不是靠固定 regex 猜什麼像機密，
而是**先從當前環境把「你是誰、你手邊有哪些專案」問出來**，再拿這份清單去比對檔案。

差別很實際：`PhoenixTracker`、`orders-api` 這種專案代號長得跟一般英文字沒兩樣，
任何 regex 都抓不到，但它就在你的工作目錄旁邊，一比對就現形。

用法：
    python3 scan_identifiers.py FILE [FILE...]
    python3 scan_identifiers.py --repo /path/to/repo FILE...
    python3 scan_identifiers.py --list-only          # 只印出偵測到的識別資訊，不掃檔案

離開碼：有 HIGH 等級的命中回傳 1，其餘回傳 0，方便掛進 pre-commit hook。
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

# 這些字太常見或太通用，當識別資訊用只會製造雜訊。
STOPLIST = {
    "src", "lib", "bin", "dist", "build", "docs", "doc", "test", "tests",
    "public", "static", "assets", "config", "scripts", "tmp", "temp", "node_modules",
    "desktop", "documents", "downloads", "library", "movies", "music", "pictures",
    "applications", "projects", "code", "work", "repos", "github", "dev", "data",
    "main", "master", "app", "api", "web", "www", "home", "user", "users", "admin",
}

# RFC 2606 / RFC 6761 保留給文件使用的網域，出現在文件裡是正確的，不該報。
RESERVED_DOMAINS = {
    "example.com", "example.org", "example.net", "example.edu",
    "localhost", "test", "invalid", "local",
}

HOME_PATH_RE = re.compile(r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)([A-Za-z0-9._-]+)")
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")

# `git@github.com:owner/repo.git` 長得跟 email 一樣，但它是 SSH URL 不是聯絡方式。
# 真正該看的是後面的 owner/repo，那段已經由 git remote 那條規則負責。
SSH_URL_RE = re.compile(r"\b(?:git|hg)@[A-Za-z0-9.-]+[:/]")


def sh(args, cwd=None):
    """跑一個指令，失敗就回空字串。

    偵測不到某一項識別資訊（例如這個目錄不是 git repo）不該讓整支腳本中斷，
    其他來源掃出來的結果仍然有用。
    """
    try:
        r = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def collect_identifiers(repo: Path):
    """從環境問出「你是誰、你手邊有哪些專案」。

    回傳 [(值, 類別, 嚴重度)]。嚴重度 HIGH 表示幾乎不該出現在對外檔案裡；
    REVIEW 表示要人看一眼——例如 repo 自己的名字出現在自己的 README 是合理的。
    """
    found = []
    seen = set()

    def add(value, kind, severity):
        v = (value or "").strip()
        if len(v) < 4 or v.lower() in STOPLIST or v.lower() in seen:
            return
        seen.add(v.lower())
        found.append((v, kind, severity))

    # 使用者名稱：從 home 目錄名拿，比 $USER 可靠（$USER 在 CI 裡常是 runner）。
    home = Path.home()
    add(home.name, "本機使用者名稱", "HIGH")

    # git 身分。local 跟 global 都要問——global 常常是公司帳號。
    for scope in ("--local", "--global"):
        for key, kind in (("user.name", "git 使用者名稱"), ("user.email", "git email")):
            add(sh(["git", "config", scope, key], cwd=repo), f"{kind} ({scope.lstrip('-')})", "HIGH")

    # git remote：抓出 owner 跟 repo 名。
    for line in sh(["git", "remote", "-v"], cwd=repo).splitlines():
        m = re.search(r"[:/]([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?\s", line + " ")
        if m:
            add(m.group(1), "git remote 帳號", "REVIEW")
            add(m.group(2), "git remote repo 名", "REVIEW")

    # repo 自己的名字。出現在自己的文件裡通常合理，所以只標 REVIEW。
    add(repo.name, "本 repo 名稱", "REVIEW")

    # 工作區裡的其他專案。這是最會漏、也最該抓的一類——
    # 寫文件時順手拿隔壁專案當範例，名字就跟著進去了。
    parent = repo.parent
    if parent != repo:
        try:
            for sibling in sorted(parent.iterdir()):
                if sibling.is_dir() and not sibling.name.startswith(".") and sibling != repo:
                    add(sibling.name, "工作區裡的其他專案", "HIGH")
        except OSError:
            pass

    return found


def scan_file(path: Path, identifiers):
    """回傳 [(行號, 嚴重度, 命中的字, 說明)]。"""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        print(f"讀不到 {path}：{e}", file=sys.stderr)
        return []

    hits = []
    for lineno, line in enumerate(lines, 1):
        low = line.lower()

        for value, kind, severity in identifiers:
            if value.lower() in low:
                hits.append((lineno, severity, value, kind))

        for m in HOME_PATH_RE.finditer(line):
            hits.append((lineno, "HIGH", m.group(0), "家目錄路徑"))

        ssh_spans = [m.span() for m in SSH_URL_RE.finditer(line)]
        for m in EMAIL_RE.finditer(line):
            if m.group(1).lower() in RESERVED_DOMAINS or "noreply" in m.group(0).lower():
                continue
            # 落在 SSH URL 前綴裡的不是 email。
            if any(s <= m.start() < e for s, e in ssh_spans):
                continue
            hits.append((lineno, "HIGH", m.group(0), "email 位址"))

    # 同一行同一個字只報一次。
    deduped, seen = [], set()
    for h in hits:
        key = (h[0], h[2].lower())
        if key not in seen:
            seen.add(key)
            deduped.append(h)
    return deduped


def main():
    ap = argparse.ArgumentParser(description="掃描檔案裡夾帶的本機識別資訊")
    ap.add_argument("files", nargs="*", type=Path)
    ap.add_argument("--repo", type=Path, default=None,
                    help="repo 根目錄，預設用 git rev-parse 從現在的位置往上找")
    ap.add_argument("--list-only", action="store_true",
                    help="只列出偵測到的識別資訊，不掃檔案")
    args = ap.parse_args()

    repo = args.repo
    if repo is None:
        top = sh(["git", "rev-parse", "--show-toplevel"])
        repo = Path(top) if top else Path.cwd()
    repo = repo.resolve()

    identifiers = collect_identifiers(repo)

    print(f"repo：{repo}")
    print(f"偵測到 {len(identifiers)} 筆識別資訊，會拿去比對檔案內容：\n")
    for value, kind, severity in identifiers:
        print(f"  [{severity:6s}] {kind:28s} {value}")

    if args.list_only or not args.files:
        if not args.files and not args.list_only:
            print("\n（沒有指定要掃的檔案。加上檔案路徑，或用 --list-only 只看清單。）")
        return 0

    print("\n" + "=" * 60)
    high_total = 0
    for path in args.files:
        hits = scan_file(path, identifiers)
        if not hits:
            print(f"\n{path} — 乾淨")
            continue
        high = [h for h in hits if h[1] == "HIGH"]
        high_total += len(high)
        print(f"\n{path} — {len(hits)} 處命中（HIGH {len(high)}）")
        for lineno, severity, value, kind in sorted(hits):
            print(f"  {severity:6s} :{lineno:<4d} 「{value}」 ← {kind}")

    print("\n" + "=" * 60)
    if high_total:
        print(f"HIGH 等級命中 {high_total} 處，這些幾乎都該換成虛構的替代素材。")
        print("REVIEW 等級要自己看：repo 自己的名字出現在自己的安裝說明裡是正常的。")
    else:
        print("沒有 HIGH 等級命中。")
    return 1 if high_total else 0


if __name__ == "__main__":
    sys.exit(main())
