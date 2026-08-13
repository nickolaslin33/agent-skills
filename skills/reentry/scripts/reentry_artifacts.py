#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""reentry_artifacts.py — 從 git 產生 artifacts.md（SPEC §3.3）。

用法：
    python3 "$SKILL_DIR"/scripts/reentry_artifacts.py <專案名> [工作目錄] [選項]

    python3 "$SKILL_DIR"/scripts/reentry_artifacts.py deploy-cli
    python3 "$SKILL_DIR"/scripts/reentry_artifacts.py deploy-cli ~/projects/deploy-cli --test-result "pytest 14 passed / 2 failed"
    python3 "$SKILL_DIR"/scripts/reentry_artifacts.py deploy-cli --since HEAD~3 --stdout

`$SKILL_DIR` 指這個 skill 的安裝目錄，呼叫方自己代換成真實路徑；這個 skill 要能在
Claude Code、Codex、Gemini、Grok、Kiro 底下都跑得動，所以不依賴任何 harness 專屬機制、
不依賴執行權限、也不依賴 PATH。

寫到 $REENTRY_ROOT/<專案名>/artifacts.md，每次覆蓋（SPEC §3.3）。
$REENTRY_ROOT 預設 ~/reentry。工作目錄沒給的話用 $REENTRY_PROJECTS_ROOT/<專案名>，
預設 ~/LIN/<專案名>（SPEC §3：專案名 = 資料夾名）。

只用標準函式庫，不綁任何一家 agent，也能單獨在終端機跑（SPEC §8）。


幾個 SPEC 沒寫死、在這裡定下來的事
-----------------------------------

1. diff 的比較基準
   預設是「工作區相對 HEAD 的未提交變更」，含已 stage、未 stage、以及未被 .gitignore
   擋掉的未追蹤檔。理由：這支腳本跑在收工流程的第四階段，而第二階段要餵給校驗 agent 的
   就是這份還沒進 commit 的 diff，兩邊看同一個東西才不會對不上。
   例外一：工作區乾淨（該提交的都提交了）時，退回比對最後一個 commit，不然收工前
   先 commit 的人會拿到一份空的 artifacts.md。
   例外二：repo 還沒有任何 commit 時，全部算新增。
   基準一律寫進「## 明細」，讀的人不用猜這批數字是哪來的。
   要自己指定基準就用 --since <ref>。

2. 目標不是 git repo 時（LIN 底下有四個沒 git）
   照樣寫出 artifacts.md，但「## 明細」誠實寫「不是 git repo」。不靜靜跳過的原因是
   舊檔會留在原地——過期的明細比沒有明細更糟，覆蓋掉才安全。SPEC §3 也講明沒有 git
   的專案照樣有資料夾。這種情況 exit 0，收工流程不該因此中斷。

3. $REENTRY_ROOT/<專案名>/ 不存在時直接報錯，不自動建
   SPEC §3：「只有登記過的專案存在」，登記＝手動建資料夾。腳本自己建等於偷偷幫人
   登記，還會在打錯專案名的時候生出一個沒人要的資料夾。

4. 三節裡有一節腳本寫不了
   artifacts.md 是 `## 改了什麼` ／ `## 驗證` ／ `## 明細` 三節。腳本只產得出後兩節：
   它撈得到 `store/migration.py` 改了幾行，但不知道那個檔是「migration runner」——
   功能層的描述需要理解。所以 `## 改了什麼` 寫的是一句自曝的佔位句，等第四階段的 agent
   看著 `## 明細` 改掉。佔位句留著不會靜靜過去：回來時那一節會被印出來，沒填就直接
   出現在使用者眼前。
   `## 驗證` 同理——有 --test-result 就寫值，沒有就留佔位句給 agent 填。

旗標與環境變數跟另外兩支一致：
    --root / $REENTRY_ROOT   交接紀錄的根目錄，預設 ~/reentry
    --now  / $REENTRY_NOW    基準時間（ISO 8601），寫進 generated，預設是現在
旗標蓋環境變數，環境變數蓋預設值。
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 共用核心跟這支腳本放在同一層。不要在 scripts/ 留下 __pycache__。
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reentry_common import (  # noqa: E402
    CHANGED_PLACEHOLDER,
    ENV_NOW,
    ENV_ROOT,
    SECTION_CHANGED,
    SECTION_DETAIL,
    SECTION_VERIFY,
    VERIFY_PLACEHOLDER,
    ReentryError,
    display_width,
    pad,
    resolve_now,
    resolve_root,
)

MINUS = "−"  # SPEC §3.3 的範例用的是減號 U+2212，不是 ASCII 的 hyphen

# SPEC §3.3 硬規則：寫值不寫「完成」。--test-result 是唯一的外部輸入，擋在這裡。
EMPTY_WORDS = (
    "完成",  # 涵蓋 已完成 / 設定完成 / 全部完成
    "已設定",
    "已驗證",
    "已修復",
    "已修正",
    "已處理",
    "已更新",
    "已確認",
    "已通過",
    "全數通過",
    "全部通過",
    "全過",
    "全綠",
    "都過了",
    "沒問題",
    "一切正常",
    "正常運作",
)


# ---------------------------------------------------------------- 基礎工具


def format_timestamp(moment: datetime) -> str:
    """2026-08-12T23:16:41+08:00，秒為單位，不要微秒。"""
    return moment.replace(microsecond=0).isoformat()


def default_workdir(project: str) -> Path:
    root = os.environ.get("REENTRY_PROJECTS_ROOT") or "~/LIN"
    return Path(root).expanduser() / project


def check_test_result(text: str) -> str:
    """防呆：測試結果必須帶值。違規就中止，不自己改寫成別的話。"""
    stripped = text.strip()
    if not stripped:
        raise ReentryError("--test-result 是空的，不要給空字串。")
    for word in EMPTY_WORDS:
        if word in stripped:
            raise ReentryError(
                f"--test-result 出現無值的詞「{word}」：{stripped}\n"
                "SPEC §3.3 規定寫值不寫完成。改成像「pytest 14 passed / 2 failed」這樣。"
            )
    if not re.search(r"\d", stripped):
        raise ReentryError(
            f"--test-result 裡一個數字都沒有：{stripped}\n"
            "SPEC §3.3 規定寫值。改成像「pytest 14 passed / 2 failed」這樣。"
        )
    return stripped


# ---------------------------------------------------------------- git


def run_git(workdir: Path, *args: str) -> tuple[int, bytes]:
    """跑 git，回 (returncode, stdout)。stderr 吞掉，錯誤用回傳碼判。"""
    proc = subprocess.run(
        ["git", "-C", str(workdir), *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return proc.returncode, proc.stdout


def git_text(workdir: Path, *args: str) -> str | None:
    code, out = run_git(workdir, *args)
    if code != 0:
        return None
    return out.decode("utf-8", "replace").strip()


def is_git_repo(workdir: Path) -> bool:
    return git_text(workdir, "rev-parse", "--is-inside-work-tree") == "true"


def split_nul(raw: bytes) -> list[str]:
    text = raw.decode("utf-8", "surrogateescape")
    return [chunk for chunk in text.split("\0") if chunk != ""]


class Entry:
    """明細的一行。"""

    def __init__(self, path: str, status: str, added: int, deleted: int, binary: bool = False):
        self.path = path
        self.status = status  # modified / added / deleted / renamed
        self.added = added
        self.deleted = deleted
        self.binary = binary

    @property
    def churn(self) -> int:
        return self.added + self.deleted

    def right_column(self) -> str:
        if self.binary:
            return "二進位"
        counts = f"+{self.added} {MINUS}{self.deleted}"
        if self.status == "added":
            return f"新增 +{self.added}"
        if self.status == "deleted":
            return f"刪除 {MINUS}{self.deleted}"
        if self.status == "renamed":
            return f"更名 {counts}"
        return counts


def parse_numstat(raw: bytes) -> dict[str, tuple[int, int, bool]]:
    """numstat -z 的欄位切法：一般是 adds\\tdels\\tpath，更名是 adds\\tdels\\t 後面兩個獨立欄位。"""
    fields = split_nul(raw)
    result: dict[str, tuple[int, int, bool]] = {}
    index = 0
    while index < len(fields):
        head = fields[index]
        index += 1
        parts = head.split("\t")
        if len(parts) < 3:
            continue
        adds_raw, dels_raw, tail = parts[0], parts[1], "\t".join(parts[2:])
        binary = adds_raw == "-" or dels_raw == "-"
        adds = 0 if binary else int(adds_raw)
        dels = 0 if binary else int(dels_raw)
        if tail == "":
            # 更名／複製：接下來兩個欄位是舊路徑與新路徑
            if index + 1 < len(fields):
                path = fields[index + 1]
                index += 2
            else:
                break
        else:
            path = tail
        result[path] = (adds, dels, binary)
    return result


def parse_name_status(raw: bytes) -> dict[str, str]:
    """name-status -z：狀態碼一欄，路徑一欄；R/C 多吃一欄（舊路徑、新路徑）。"""
    fields = split_nul(raw)
    result: dict[str, str] = {}
    index = 0
    while index < len(fields):
        code = fields[index]
        index += 1
        if not code:
            continue
        letter = code[0]
        if letter in ("R", "C"):
            if index + 1 >= len(fields):
                break
            path = fields[index + 1]
            index += 2
        else:
            if index >= len(fields):
                break
            path = fields[index]
            index += 1
        result[path] = {
            "A": "added",
            "D": "deleted",
            "R": "renamed",
            "C": "added",
        }.get(letter, "modified")
    return result


def count_untracked(workdir: Path, rel_path: str) -> tuple[int, bool]:
    """未追蹤檔的行數。含 NUL 就當二進位，不硬算行數。

    一塊一塊讀，免得未追蹤的大檔（沒被 .gitignore 擋掉的 dump、log）把記憶體吃光。
    """
    target = workdir / rel_path
    lines = 0
    last_byte = b""
    try:
        with target.open("rb") as handle:
            while True:
                chunk = handle.read(1 << 20)
                if not chunk:
                    break
                if b"\0" in chunk:
                    return 0, True
                lines += chunk.count(b"\n")
                last_byte = chunk[-1:]
    except OSError:
        return 0, False
    if last_byte and last_byte != b"\n":
        lines += 1  # 最後一行沒有換行符也算一行
    return lines, False


def diff_entries(workdir: Path, *rev_args: str) -> list[Entry]:
    """跑一輪 diff，組出明細。rev_args 就是接在 git diff 後面的 revision 參數。"""
    code, numstat_raw = run_git(workdir, "diff", "-M", "--numstat", "-z", *rev_args, "--")
    if code != 0:
        raise ReentryError(f"git diff 失敗：git diff {' '.join(rev_args)}")
    _, status_raw = run_git(workdir, "diff", "-M", "--name-status", "-z", *rev_args, "--")

    numbers = parse_numstat(numstat_raw)
    statuses = parse_name_status(status_raw)

    entries = []
    for path, (adds, dels, binary) in numbers.items():
        entries.append(Entry(path, statuses.get(path, "modified"), adds, dels, binary))
    return entries


def untracked_entries(workdir: Path) -> list[Entry]:
    code, raw = run_git(workdir, "ls-files", "--others", "--exclude-standard", "-z")
    if code != 0:
        return []
    entries = []
    for rel_path in split_nul(raw):
        lines, binary = count_untracked(workdir, rel_path)
        entries.append(Entry(rel_path, "added", lines, 0, binary))
    return entries


def short_sha(workdir: Path, rev: str) -> str:
    return git_text(workdir, "rev-parse", "--short", rev) or rev


class Collected:
    def __init__(self, entries: list[Entry], baseline: str, is_repo: bool = True):
        self.entries = entries
        self.baseline = baseline
        self.is_repo = is_repo

    @property
    def added(self) -> int:
        return sum(e.added for e in self.entries)

    @property
    def deleted(self) -> int:
        return sum(e.deleted for e in self.entries)


def collect(workdir: Path, since: str | None) -> Collected:
    """照上面第 1 點的規則決定基準，然後把明細撈出來。"""
    if not workdir.is_dir():
        raise ReentryError(f"工作目錄不存在：{workdir}")

    if not is_git_repo(workdir):
        return Collected([], f"不是 git repo（{workdir}），沒有 diff 可統計", is_repo=False)

    if since:
        if git_text(workdir, "rev-parse", "--verify", "--quiet", f"{since}^{{commit}}") is None:
            raise ReentryError(f"--since 指的 {since} 在這個 repo 裡找不到")
        entries = diff_entries(workdir, since) + untracked_entries(workdir)
        baseline = f"比較基準：{since}（{short_sha(workdir, since)}）到工作區"
        return Collected(entries, baseline)

    has_head = git_text(workdir, "rev-parse", "--verify", "--quiet", "HEAD") is not None
    if not has_head:
        # 還沒有任何 commit：已 stage 的用 empty tree 比，其他就是未追蹤檔
        empty_tree = git_text(workdir, "hash-object", "-t", "tree", os.devnull) or ""
        entries = []
        if empty_tree:
            entries += diff_entries(workdir, empty_tree)
        entries += untracked_entries(workdir)
        return Collected(entries, "比較基準：這個 repo 還沒有 commit，全部算新增")

    entries = diff_entries(workdir, "HEAD") + untracked_entries(workdir)
    if entries:
        return Collected(entries, f"比較基準：工作區未提交的變更（對 HEAD {short_sha(workdir, 'HEAD')}）")

    # 工作區乾淨 → 退回看最後一個 commit，不然收工前先 commit 的人拿到空檔案
    baseline = f"比較基準：最後一個 commit {short_sha(workdir, 'HEAD')}（工作區沒有未提交的變更）"
    if git_text(workdir, "rev-parse", "--verify", "--quiet", "HEAD~1") is not None:
        return Collected(diff_entries(workdir, "HEAD~1", "HEAD"), baseline)

    # HEAD 就是第一個 commit，沒有 parent 可比，拿 empty tree 當基準
    empty_tree = git_text(workdir, "hash-object", "-t", "tree", os.devnull)
    if empty_tree:
        return Collected(diff_entries(workdir, empty_tree, "HEAD"), baseline)
    return Collected([], baseline)


# ---------------------------------------------------------------- 排版


def sort_entries(entries: list[Entry]) -> list[Entry]:
    return sorted(entries, key=lambda e: (-e.churn, e.path))


def render(project: str, moment: datetime, data: Collected, test_results: list[str]) -> str:
    """排出 artifacts.md 的三節：改了什麼 ／ 驗證 ／ 明細。

    順序是刻意的，跟閱讀順序一樣：功能層的一句話在最上面，原始事實壓在最下面。
    回來時只印前兩節，明細留在檔案裡給那句話查證用。
    """
    entries = sort_entries(data.entries)

    lines = [
        "---",
        f"project: {project}",
        f"generated: {format_timestamp(moment)}",
        "---",
        "",
        # 腳本不知道那些檔是幹嘛的，這一節等 agent 填（見檔頭第 4 點）
        f"## {SECTION_CHANGED}",
        CHANGED_PLACEHOLDER,
        "",
        f"## {SECTION_VERIFY}",
        # --test-result 抓得到就寫值，沒給就一樣留佔位句，不留空節
        *(test_results or [VERIFY_PLACEHOLDER]),
        "",
        f"## {SECTION_DETAIL}",
    ]

    if not data.is_repo:
        # 沒有 git 就沒有明細可撈。誠實寫清楚，比留一個空的 ## 明細好
        lines.append(data.baseline)
        return "\n".join(lines) + "\n"

    lines.append(f"改了 {len(entries)} 個檔（+{data.added} {MINUS}{data.deleted}）")
    if entries:
        width = max(display_width(e.path) for e in entries)
        for entry in entries:
            lines.append(f"{pad(entry.path, width)}  {entry.right_column()}")
    else:
        lines.append("（無變更）")
    # 基準壓在最後：讀的人不用猜這批數字是從哪裡比出來的
    lines.append(data.baseline)

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- 進入點


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reentry_artifacts.py",
        description="從 git 產生 artifacts.md（SPEC §3.3），寫到 $REENTRY_ROOT/<專案名>/artifacts.md。",
    )
    parser.add_argument("project", help="專案名，同時是 $REENTRY_ROOT 底下的資料夾名")
    parser.add_argument(
        "workdir",
        nargs="?",
        help="專案的工作目錄，預設 $REENTRY_PROJECTS_ROOT/<專案名>（再預設 ~/LIN/<專案名>）",
    )
    parser.add_argument("--since", help="自己指定 diff 基準（commit / tag / branch），預設看工作區未提交的變更")
    parser.add_argument(
        "--test-result",
        action="append",
        default=[],
        metavar="TEXT",
        help="測試結果，原樣寫進 ## 驗證，可重複。要寫值，例如「pytest 14 passed / 2 failed」",
    )
    parser.add_argument(
        "--root",
        default=None,
        help=f"交接紀錄的根目錄，預設讀 ${ENV_ROOT}，再預設 ~/reentry",
    )
    parser.add_argument(
        "--now",
        default=None,
        help=f"覆蓋 generated 的時間（ISO 8601），預設讀 ${ENV_NOW}，再預設是現在",
    )
    parser.add_argument("--stdout", action="store_true", help="印出來就好，不寫檔")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        moment = resolve_now(args.now)
        test_results = [check_test_result(text) for text in args.test_result]
        workdir = Path(args.workdir).expanduser() if args.workdir else default_workdir(args.project)
        data = collect(workdir, args.since)
        document = render(args.project, moment, data, test_results)

        if args.stdout:
            sys.stdout.write(document)
            return 0

        project_dir = resolve_root(args.root) / args.project
        if not project_dir.is_dir():
            raise ReentryError(
                f"找不到 {project_dir}\n"
                "只有登記過的專案存在（SPEC §3），登記就是手動建這個資料夾。腳本不自己建。"
            )
        target = project_dir / "artifacts.md"
        target.write_text(document, encoding="utf-8")
    except ReentryError as exc:
        print(f"reentry_artifacts.py: {exc}", file=sys.stderr)
        return exc.exit_code

    if not data.is_repo:
        print(f"{workdir} 不是 git repo，artifacts.md 只記了這件事", file=sys.stderr)
    print(str(target))
    return 0


if __name__ == "__main__":
    sys.exit(main())
