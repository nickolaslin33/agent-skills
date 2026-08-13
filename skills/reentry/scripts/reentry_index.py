#!/usr/bin/env python3
"""reentry_index.py — 跨專案索引（SPEC §5.1）。

用法：
    python3 "$SKILL_DIR"/scripts/reentry_index.py [--root 路徑] [--now 時間]

`$SKILL_DIR` 指這個 skill 的安裝目錄，呼叫方自己代換成真實路徑；這個 skill 要能在
Claude Code、Codex、Gemini、Grok、Kiro 底下都跑得動，所以不依賴任何 harness 專屬機制、
不依賴執行權限、也不依賴 PATH。

掃 $REENTRY_ROOT 底下每個專案資料夾，每筆印出：

    deploy-cli    5 天前    欠 2
      上次：把 ConfigStore 的 load/save 寫完，備份邏輯還沒接上。
      下一步：實作 tasks.md 的 2.1 剩下的部分，改完跑 `pytest tests/test_config.py`

索引是「算出來的，不是存下來的」（SPEC §5.1）：每次現場掃資料夾，
不落地成檔案，所以不會有不同步的問題。

旗標與環境變數跟另外兩支一致：
    --root / $REENTRY_ROOT   根目錄，預設 ~/reentry
    --now  / $REENTRY_NOW    基準時間（ISO 8601），預設是現在
旗標蓋環境變數，環境變數蓋預設值。

只用標準函式庫，可以在終端機直接跑，不綁任何一家 agent。
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# 共用核心跟這支腳本放在同一層。不要在 scripts/ 留下 __pycache__。
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reentry_common import (  # noqa: E402
    ENV_NOW,
    ENV_ROOT,
    OLDEST,
    SECTION_LAST,
    SECTION_NEXT,
    ReentryError,
    count_open_debt,
    display_width,
    load_note,
    pad,
    read_text,
    relative_day,
    resolve_now,
    resolve_root,
    resolve_touched_at,
    section_first_line,
)

# 欄位最小寬度。SPEC §5.1 的範例就是這個寬度：
# 「deploy-cli」10 格 + 2 空白 = 12，「5 天前」6 格 + 4 空白 = 10。
# 內容更寬時整欄一起長，至少留 2 格間隔，不讓欄位黏在一起。
NAME_COL = 12
AGE_COL = 10
GUTTER = 2
INDENT = "  "

# 找不到對應欄位時印的字。刻意不留空白，空白會被讀成「這裡沒東西」，
# 但實際情況是「handoff.md 裡沒寫」，兩者要分得出來。
PLACEHOLDER = "（未填寫）"
NO_HANDOFF_AGE = "還沒交接"
NO_HANDOFF_NOTE = "（沒有 handoff.md，這個專案還沒收過工）"

# 「上次」欄讀的是 handoff.md 的第一節，章節名來自共用模組（改名要一次改完）。
# 這裡印「上次：」而不是章節名本身，是因為欄寬有限，而且索引是掃描結果不是原文。
# 排序用的墊底時間（OLDEST）也在共用模組，只給沒有 handoff.md 的專案用，不會被印出來。


# --- 掃描 -------------------------------------------------------------------


@dataclass
class Entry:
    name: str
    # 上次動過的時間：handoff.md 的 `updated`，沒有才退回 mtime；沒有 handoff.md 就是 None
    touched_at: datetime | None
    open_debt: int
    last: str | None
    next_step: str | None

    @property
    def has_handoff(self) -> bool:
        return self.touched_at is not None


def scan(root: Path) -> list[Entry]:
    """掃 root 底下每個專案資料夾，回傳排序好的索引資料。

    排序：最近動過的在最上面（SPEC §5.1）。
    """
    entries = [
        read_project(child)
        for child in sorted(root.iterdir())
        # 只認資料夾。根目錄的散檔（README 之類）跟隱藏目錄（.git）不是專案。
        if child.is_dir() and not child.name.startswith(".")
    ]
    # 先按名字排，再用穩定排序把時間壓上去，這樣同時間的照字母序。
    entries.sort(key=lambda e: e.name)
    # 沒有 handoff.md 的排最後：它沒有時間可比，硬塞進時間軸只會騙人。
    entries.sort(key=lambda e: (e.has_handoff, e.touched_at or OLDEST), reverse=True)
    return entries


def read_project(folder: Path) -> Entry:
    handoff_path = folder / "handoff.md"
    handoff = read_text(handoff_path)
    debt = read_text(folder / "debt.md")

    touched_at = resolve_touched_at(handoff_path, handoff) if handoff is not None else None
    sections = load_note(handoff)[1] if handoff is not None else {}
    return Entry(
        name=folder.name,
        touched_at=touched_at,
        # 沒有 debt.md 就是還沒欠過，算 0，不當成錯誤
        open_debt=count_open_debt(debt),
        last=section_first_line(sections, SECTION_LAST),
        next_step=section_first_line(sections, SECTION_NEXT),
    )


# --- 輸出 -------------------------------------------------------------------


def format_index(entries: list[Entry], now: datetime) -> str:
    if not entries:
        return ""

    ages = [relative_day(e.touched_at, now) if e.has_handoff else NO_HANDOFF_AGE for e in entries]
    name_col = max(NAME_COL, max(display_width(e.name) for e in entries) + GUTTER)
    age_col = max(AGE_COL, max(display_width(age) for age in ages) + GUTTER)

    blocks = []
    for entry, age in zip(entries, ages):
        head = (pad(entry.name, name_col) + pad(age, age_col) + f"欠 {entry.open_debt}").rstrip()
        if entry.has_handoff:
            lines = [
                f"{INDENT}上次：{entry.last or PLACEHOLDER}",
                f"{INDENT}下一步：{entry.next_step or PLACEHOLDER}",
            ]
        else:
            lines = [f"{INDENT}{NO_HANDOFF_NOTE}"]
        blocks.append("\n".join([head, *lines]))
    return "\n\n".join(blocks)


# --- CLI --------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reentry_index.py",
        description="列出 $REENTRY_ROOT 底下每個專案的停留狀態。",
    )
    parser.add_argument(
        "--root",
        default=None,
        help=f"根目錄，預設讀環境變數 ${ENV_ROOT}，再預設 ~/reentry",
    )
    parser.add_argument(
        "--now",
        default=None,
        help=f"基準時間（ISO 8601），算相對日期用；預設讀 ${ENV_NOW}，再預設是現在",
    )
    args = parser.parse_args(argv)

    try:
        now = resolve_now(args.now)
    except ReentryError as exc:
        print(str(exc), file=sys.stderr)
        return exc.exit_code

    root = resolve_root(args.root)
    if not root.is_dir():
        print(f"找不到 {ENV_ROOT}：{root}", file=sys.stderr)
        return 1

    entries = scan(root)
    if not entries:
        print(f"（{root} 底下沒有專案）")
        return 0

    print(format_index(entries, now))
    return 0


if __name__ == "__main__":
    sys.exit(main())
