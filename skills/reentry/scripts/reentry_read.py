#!/usr/bin/env python3
"""reentry_read.py — 讀取單一專案的重新進入資訊（SPEC §5.2）。

用法：
    python3 "$SKILL_DIR"/scripts/reentry_read.py <專案名> [--root 路徑] [--now 時間]

`$SKILL_DIR` 指這個 skill 的安裝目錄，呼叫方自己代換成真實路徑；這個 skill 要能在
Claude Code、Codex、Gemini、Grok、Kiro 底下都跑得動，所以不依賴任何 harness 專屬機制、
不依賴執行權限、也不依賴 PATH。

旗標與環境變數跟另外兩支一致：
    --root / $REENTRY_ROOT   交接紀錄的根目錄，預設 ~/reentry
    --now  / $REENTRY_NOW    計算相對日期用的基準時間（ISO 8601），預設為現在
旗標蓋環境變數，環境變數蓋預設值。

輸出順序固定：

    警告（若有）→ 上次叫它做什麼、做到哪裡 → 上次的決定（若有）→ 欠債 → 下一步

最後一句提示。下一步刻意壓在最後：問題不是動不起來，是太容易就往下跑了。

「上次的決定」**只在 decisions/ 真的有東西時才印**。多數收工不會產生值得記的決定，
永遠留一個空欄位會退化成每次略過的噪音；但有決定的那幾次，那是回來最需要知道的
東西之一。所以是「有就印、沒有就整段不存在」，不是「印一個（無）」。

`artifacts.md` 只印 `## 改了什麼` 與 `## 驗證`，**`## 明細` 永遠不印**——明細是給
`## 改了什麼` 那句話查證用的原始事實，不是回來時要讀的東西。

`## 我當初記錯的` 永遠不印。那些糾正在收工當下已經處理過一輪，
回來該讀的是篩選過的 debt.md。

輸出短是**成立條件不是建議**（SPEC §5.2）：每段各一到兩行，整體不超過螢幕一半，
否則人會直接捲到底。所以這裡會截斷，見下面 SCREEN_COLS / MAX_ROWS。
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 共用核心跟這支腳本放在同一層。不要在 scripts/ 留下 __pycache__。
sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))

from reentry_common import (  # noqa: E402
    ENV_NOW,
    ENV_ROOT,
    OLDEST,
    SECTION_CHANGED,
    SECTION_DECISION,
    SECTION_LAST,
    SECTION_MISREMEMBERED,
    SECTION_NEXT,
    SECTION_VERIFY,
    ReentryError,
    clip,
    display_width,
    load_note,
    load_sections,
    one_line,
    open_debts,
    parse_sections,
    parse_updated,
    read_text,
    relative_day,
    resolve_now,
    resolve_root,
    resolve_touched_at,
    split_frontmatter,
)

# 這些章節絕對不進回來時的輸出（SPEC §3.1、§5.2）
HIDDEN_SECTIONS = (SECTION_MISREMEMBERED,)

# 段落標籤。跟檔案裡的章節名不完全一樣是刻意的：檔案裡是使用者第一人稱寫的
# 「我叫它做什麼，做到哪裡」，回來時讀的是上一輪的自己，所以掛「上次」。
LABEL_LAST = "上次叫它做什麼、做到哪裡"
LABEL_DECISION = "上次的決定"
LABEL_WARNING = "警告"
# 待確認跟理解債不一樣：理解債是「以為自己懂但沒懂」，靠校驗者問機制問題還；
# 待確認是「知道自己不知道」，靠去查或問人還。兩者還法不同，所以不共用 debt.md。
LABEL_QUESTIONS = "待確認"

# SPEC §5.2 的成立條件換算成數字。
#
# 「螢幕」取 40 列（一般終端機視窗的高度），一半就是 20 列，這是整份輸出的上限。
# 「一到兩行」是每一段的**內文**行數，段落標題（警告／上次的決定／欠債 N）是標籤不算。
# 寬度取 80 欄：超過就會折行，折行的兩行在螢幕上就是兩列，講好的「一行」會偷偷變成三列。
# 這幾個數字寫死不跟著終端機大小變——每次輸出長得一樣，人才建立得起「打開就知道
# 哪裡看什麼」的肌肉記憶（SPEC §8）。
SCREEN_COLS = 80
SCREEN_ROWS = 40
MAX_ROWS = SCREEN_ROWS // 2
BLOCK_BODY_LINES = 2

# 20 列全部配完是這樣（警告與決定都在的最壞情況）：
#
#     抬頭 1 ＋ 空行 1
#     警告   標題 1 ＋ 內文 1 ＋ 空行 1
#     上次   標題 1 ＋ 內文 2 ＋ 空行 1   ← 一行使用者寫的，一行 artifacts
#     決定   標題 1 ＋ 內文 1 ＋ 空行 1
#     欠債   標題 1 ＋ 內文 2 ＋ 空行 1
#     下一步 標題 1 ＋ 內文 1 ＋ 空行 1
#     提示 1
#
# 剛好 20，沒有餘裕。所以 `## 改了什麼` 與 `## 驗證` 是併成一行印的（見 artifacts_line），
# 決定也壓成一行。要再加東西就得先想清楚拿掉什麼，不要默默讓輸出長出螢幕。

# 欠債最多列幾條。列滿三條加一句「還有 N 條」就是四行內文，直接違反上面那條成立條件，
# 所以列兩條，超出的數量掛回段落標題，資訊沒少。
MAX_DEBT_SHOWN = BLOCK_BODY_LINES

# 併 `## 改了什麼` 與 `## 驗證` 用的分隔符。跟句號分得開，一眼看得出是兩件事。
ARTIFACTS_SEP = "・"

# 段落內文的縮排寬度，跟 body() 裡那兩個空白是同一件事。
INDENT_COLS = 2

# 併行時留給 `## 改了什麼` 的最低寬度。低於這個數字就不切了——切到只剩「改了 2…」
# 沒有資訊，不如整行交給外層截斷。
MIN_CHANGED_COLS = 20

PROMPT = "先用自己的話說一次下一步再動手。"
MISSING = "（沒寫）"


# ---------- 解析 ----------


def visible_sections(sections: dict[str, list[str]]) -> dict[str, list[str]]:
    """隱藏章節在這裡就丟掉，不往下傳。"""
    for title in HIDDEN_SECTIONS:
        sections.pop(title, None)
    return sections


def artifacts_line(path: Path) -> str:
    """artifacts.md 取 `## 改了什麼` 與 `## 驗證`，併成一行。檔案不存在就是沒有。

    `## 明細` 不讀。它是原始事實（路徑、增減行數），存在是為了讓 `## 改了什麼` 那句話
    有東西可查證，不是回來時要看的——檔案數量對使用者不是線索，他沒寫這些程式。

    併成一行是被螢幕高度逼的（見上面的 20 列預算），不是因為兩者是同一件事。所以中間
    用「・」隔開，而不是接成一句話。

    一行放不下的時候**先砍描述，不砍驗證**。兩者的可替代性不一樣：描述砍掉還有
    artifacts.md 可以翻，「14 passed / 2 failed」砍掉就只剩「測試跑過了」這種印象，
    而那正是這套機制要對付的東西。
    """
    sections = load_sections(path)
    changed = one_line(sections.get(SECTION_CHANGED, []))
    verify = one_line(sections.get(SECTION_VERIFY, []))
    if not changed or not verify:
        return changed or verify

    budget = SCREEN_COLS - INDENT_COLS - display_width(ARTIFACTS_SEP) - display_width(verify)
    if budget >= MIN_CHANGED_COLS:
        changed = clip(changed, budget)
    # 驗證本身就長到沒有餘裕時不硬切，交給外層統一截斷，至少留一個「…」看得出被截了
    return f"{changed}{ARTIFACTS_SEP}{verify}"


def decision_moment(path: Path, meta: dict[str, str]):
    """決策紀錄的時間：frontmatter 的 `date` 優先，退回檔名前面那段日期。

    跟 handoff 的 `updated` 同一個道理——檔名與內容跟著檔案走，mtime 撐不過 clone。
    兩邊都問不出來就回 None，排序時墊到最後面（但還是印得到，只要它是唯一一篇）。
    """
    for raw in (meta.get("date"), path.name[:10]):
        moment = parse_updated(raw)
        if moment is not None:
            return moment
    return None


def latest_decision(project_dir: Path) -> str:
    """decisions/ 裡最新那一篇的 `## 決定`，壓成一行。沒有就回空字串。

    回空字串是有意義的：呼叫端據此決定整段印不印。空的決定紀錄（有檔案但 `## 決定`
    沒寫）也一樣當成沒有——寧可整段不出現，也不要印一個空欄位讓人學會略過它。
    """
    try:
        paths = sorted(
            path
            for path in (project_dir / "decisions").iterdir()
            if path.is_file() and path.suffix == ".md"
        )
    except OSError:  # 沒有 decisions/、不是資料夾、沒權限——都當作沒有決定
        return ""

    found = []
    for path in paths:
        text = read_text(path)
        if text is None:
            continue
        meta, body = split_frontmatter(text)
        decision = one_line(parse_sections(body).get(SECTION_DECISION, []))
        if not decision:
            continue
        moment = decision_moment(path, meta)
        found.append(((moment is not None, moment or OLDEST, path.name), decision))
    if not found:
        return ""
    return max(found, key=lambda item: item[0])[1]


def warning_text(meta: dict) -> str:
    """warning 省略、空的、或 false 都當作沒有警告。"""
    raw = meta.get("warning", "").strip()
    if not raw or raw.lower() in ("false", "no", "none", "null"):
        return ""
    return raw


# ---------- 排版 ----------


def body(lines: list[str]) -> list[str]:
    """段落內文：縮排、截到一列寬，最多兩行。空的就給一句佔位，段落不留空殼。"""
    kept = [line for line in lines if line.strip()] or [MISSING]
    return [clip(f"{' ' * INDENT_COLS}{line}", SCREEN_COLS) for line in kept[:BLOCK_BODY_LINES]]


def debt_block(debts: list[str]) -> list[str]:
    """欠債段落。條數永遠印全，內容只列前兩條，超出的掛在標題上。"""
    head = f"欠債 {len(debts)}"
    if len(debts) > MAX_DEBT_SHOWN:
        head += f"（只列 {MAX_DEBT_SHOWN} 條，其餘看 debt.md）"
    if not debts:
        return [clip(head, SCREEN_COLS)]
    return [clip(head, SCREEN_COLS), *body([f"- {q}" for q in debts[:MAX_DEBT_SHOWN]])]


def question_block(questions: list[str]) -> list[str]:
    """待確認段落。跟欠債不同，沒有的時候整段不印——欠債是這套機制的核心指標，
    零筆本身有意義；待確認是附帶的，永遠留一個空欄位會退化成每次略過的噪音。"""
    head = f"{LABEL_QUESTIONS} {len(questions)}"
    if len(questions) > MAX_DEBT_SHOWN:
        head += f"（只列 {MAX_DEBT_SHOWN} 條，其餘看 open-questions.md）"
    return [clip(head, SCREEN_COLS), *body([f"- {q}" for q in questions[:MAX_DEBT_SHOWN]])]


def render(project: str, root: Path, now: datetime) -> list[str]:
    project_dir = root / project
    handoff_path = project_dir / "handoff.md"
    text = read_text(handoff_path)
    if text is None:
        die(f"{project} 沒有 handoff.md（找的是 {handoff_path}）")

    meta, sections = load_note(text)
    sections = visible_sections(sections)

    last = one_line(sections.get(SECTION_LAST, []))
    nxt = one_line(sections.get(SECTION_NEXT, []))
    artifacts = artifacts_line(project_dir / "artifacts.md")
    decision = latest_decision(project_dir)
    debts = open_debts(read_text(project_dir / "debt.md"))
    questions = open_debts(read_text(project_dir / "open-questions.md"))
    touched_at = resolve_touched_at(handoff_path, text)

    # 檔案讀得到卻問不到時間（沒有 updated，stat 又失敗）就照實說不知道，不要瞎猜一個
    age = relative_day(touched_at, now) if touched_at else "時間不明"
    out = [clip(f"{project}  {age}", SCREEN_COLS), ""]

    warning = warning_text(meta)
    if warning:
        out += [LABEL_WARNING, *body([warning]), ""]

    out += [LABEL_LAST, *body([last or MISSING, artifacts]), ""]
    # 有決定才有這一段。沒有的時候整段不存在，不留空殼（SPEC §5.2 的「若有」）。
    if decision:
        out += [LABEL_DECISION, *body([decision]), ""]
    out += [*debt_block(debts), ""]
    if questions:
        out += [*question_block(questions), ""]
    out += [SECTION_NEXT, *body([nxt or MISSING]), ""]
    out.append(PROMPT)
    return out


def rows(lines: list[str]) -> int:
    """這份輸出在 80 欄的終端機上佔幾列。

    給測試量 SPEC §5.2 的成立條件用：截斷之後每行都在一列以內，所以正常情況等於行數；
    哪天截斷漏掉某一行，這裡就會算出比行數大的值。
    """
    return sum(max(1, -(-display_width(line) // SCREEN_COLS)) for line in lines)


# ---------- 進入點 ----------


USAGE = '用法：python3 "$SKILL_DIR"/scripts/reentry_read.py <專案名> [--root 路徑] [--now 時間]'


def die(message: str, code: int = 1):
    print(message, file=sys.stderr)
    raise SystemExit(code)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reentry_read.py",
        usage=USAGE,
        description="印出單一專案的重新進入資訊（SPEC §5.2）。",
        epilog=(
            f"環境變數：\n"
            f"  {ENV_ROOT}   交接紀錄的根目錄，預設 ~/reentry\n"
            f"  {ENV_NOW}    基準時間（ISO 8601），預設是現在\n"
            "旗標蓋環境變數，環境變數蓋預設值。"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("project", help="專案名，也就是 $REENTRY_ROOT 底下的資料夾名")
    parser.add_argument("--root", default=None, help=f"根目錄，預設讀 ${ENV_ROOT}，再預設 ~/reentry")
    parser.add_argument("--now", default=None, help=f"基準時間（ISO 8601），預設讀 ${ENV_NOW}，再預設是現在")
    return parser


def main(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)

    project = args.project.strip()
    if not project or "/" in project or project.startswith("."):
        die(f"專案名不合法：{args.project}", 2)

    try:
        now = resolve_now(args.now)
    except ReentryError as exc:
        die(str(exc), exc.exit_code)

    root = resolve_root(args.root)
    if not (root / project).is_dir():
        known = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
        hint = "、".join(known) if known else "（一個都沒有）"
        die(f"{root} 底下沒有 {project}。有登記的：{hint}")

    for line in render(project, root, now):
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
