#!/usr/bin/env python3
"""reentry_common — 三支腳本共用的核心（SPEC §3、§5）。

`reentry_index.py`、`reentry_read.py`、`reentry_artifacts.py` 都 import 這一份。理由很簡單：
同一條規則抄三份，今天數字對得起來，改一次就開始漂。理解債的條目數在索引裡是「欠 N」、
在單一專案裡是「欠債 N」，兩邊算出不同的數字，人會先不信任這個工具，然後就不用了。

跟三支腳本同放在 `scripts/` 是刻意的——不裝套件、不設 PYTHONPATH（SPEC §8）。
腳本自己把 `scripts/` 塞進 `sys.path` 就 import 得到，透過 symlink 呼叫也還原得回來
（`Path(__file__).resolve()` 會解開 symlink）。

`$SKILL_DIR` 指這個 skill 的安裝目錄，呼叫方自己代換成真實路徑。這個 skill 要能在
Claude Code、Codex、Gemini、Grok、Kiro 底下都跑得動，所以不依賴任何 harness 專屬機制、
不依賴執行權限、也不依賴 PATH——一律 `python3 "$SKILL_DIR"/scripts/<名字>.py` 這樣呼叫。

只用標準函式庫。
"""

from __future__ import annotations

import os
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------- 常數

DEFAULT_ROOT = "~/reentry"

ENV_ROOT = "REENTRY_ROOT"
ENV_NOW = "REENTRY_NOW"

# `- [ ] 問題？` 一條理解債。續行（commit: / added:）不算條目（SPEC §3.2）。
# 打勾符號只認 x／X，其他符號一律當成還沒還——寧可多列一條要人自己看，
# 也不要因為手打了一個看不懂的記號就讓債悄悄消失。
DEBT_ITEM_RE = re.compile(r"^\s*[-*+]\s+\[(?P<mark>.)\]\s*(?P<text>.*)$")

# Markdown 標題。要求 # 後面有空白，`#hashtag` 不是標題。
HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*$")

TIME_EXAMPLE = "2026-08-12T23:16:41+08:00"

# ---------------------------------------------------------------- 章節名
#
# 章節名放這裡不放各腳本，是因為改名一定要一次改完：`handoff.md` 的第一節同時被索引的
# 「上次」欄與回來時的第二段讀，各寫一份字串就會有一邊漏改，而漏改的症狀是欄位變成
# 「（未填寫）」——看起來像使用者沒寫，不像程式讀錯，人會去改自己的檔案而不是回報 bug。

# handoff.md：人在第一階段憑記憶寫的。第一節問的是「我叫它做什麼」不是「這次做了什麼」——
# 他沒有寫這些程式，是他指揮 agent 寫的，記憶痕跡在指令上，不在檔案上。
SECTION_LAST = "我叫它做什麼，做到哪裡"
SECTION_NEXT = "下一步"
SECTION_MISREMEMBERED = "我當初記錯的"

# artifacts.md：三節分工不同，不要混。
SECTION_CHANGED = "改了什麼"  # agent 看著明細寫的功能層描述
SECTION_VERIFY = "驗證"  # 測試與 lint 的結果
SECTION_DETAIL = "明細"  # 腳本從 git 撈的原始事實，回來時不印

# decisions/<日期>-<標題>.md
SECTION_DECISION = "決定"

# `## 改了什麼` 腳本寫不了——它不知道 `store/migration.py` 是「migration runner」，那需要
# 理解。所以留一句會自曝的佔位句：回來時 `## 改了什麼` 是會被印出來的，沒填就直接出現在
# 使用者眼前，不會安安靜靜留在檔案裡等人哪天發現。
CHANGED_PLACEHOLDER = "（尚未填寫：agent 要看著下面的明細寫成功能層描述，寫完把這行刪掉）"
VERIFY_PLACEHOLDER = "（尚未填寫：測試與 lint 的結果，寫值例如 pytest 11 passed）"

# 排序用的墊底時間，給問不到時間的東西用，不會被印出來。
OLDEST = datetime(1, 1, 1, tzinfo=timezone.utc)


class ReentryError(Exception):
    """能直接印給人看的錯誤。exit_code 決定腳本的退出碼。"""

    exit_code = 1


class TimeFormatError(ReentryError):
    """--now / $REENTRY_NOW 看不懂。三支腳本一律用 2，跟其他錯誤分得開。"""

    exit_code = 2


# ---------------------------------------------------------------- 排版


def char_width(char: str) -> int:
    """單一字元的終端機顯示寬度。組合符號（聲調、變音）不佔格。"""
    if unicodedata.combining(char):
        return 0
    return 2 if unicodedata.east_asian_width(char) in ("W", "F") else 1


def display_width(text: str) -> int:
    """算終端機顯示寬度：中日韓全形字佔 2 格。"""
    return sum(char_width(char) for char in text)


def pad(text: str, width: int) -> str:
    """靠左補到指定顯示寬度（不足就補空白，超過就原樣吐回）。"""
    return text + " " * max(0, width - display_width(text))


ELLIPSIS = "…"


def clip(text: str, width: int) -> str:
    """截到指定顯示寬度，被截掉就補一個「…」。

    截的是顯示寬度不是字元數，中文一個字佔兩格，用 len() 會截出參差不齊的邊。
    """
    if display_width(text) <= width:
        return text
    budget = width - display_width(ELLIPSIS)
    kept: list[str] = []
    used = 0
    for char in text:
        size = char_width(char)
        if used + size > budget:
            break
        kept.append(char)
        used += size
    return "".join(kept).rstrip() + ELLIPSIS


# ---------------------------------------------------------------- 讀檔


def read_text(path: Path) -> str | None:
    """讀檔，讀不到就回 None（不存在、不是檔案、沒權限、不是 UTF-8 都算）。

    順手把 BOM 與 CRLF 收掉，後面每一支都不用再處理一次。
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    return raw.lstrip("﻿").replace("\r\n", "\n")


# ---------------------------------------------------------------- Markdown


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """切出 YAML frontmatter 與本文。只認最上面那組 `---`。

    值只用第一個冒號切，所以 `updated: 2026-08-12T23:14:05+08:00` 不會被時間裡的
    冒號切壞。沒有收尾的 `---` 就當作整份都是本文，寧可多印也不要吃掉內容。
    """
    lines = text.replace("\r\n", "\n").split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text

    meta: dict[str, str] = {}
    for index, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            return meta, "\n".join(lines[index + 1 :])
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return {}, text


def parse_sections(body: str) -> dict[str, list[str]]:
    """把 `## 標題` 切成 {標題: 內容行}。吃的是本文，frontmatter 要先剝掉。

    同名標題以第一個為準：後面那個的內容整段丟掉，不合併。合併會讓「我叫它做什麼，
    做到哪裡」突然多出一段沒人預期的內容。
    """
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for raw_line in body.split("\n"):
        line = raw_line.rstrip()
        match = HEADING_RE.match(line)
        if match:
            title = match.group(2)
            current = title if title not in sections else None
            if current is not None:
                sections[current] = []
            continue
        if current is not None:
            sections[current].append(line)
    return sections


def load_note(text: str) -> tuple[dict[str, str], dict[str, list[str]]]:
    """一次把 handoff.md 拆成 (frontmatter, 章節)。"""
    meta, body = split_frontmatter(text)
    return meta, parse_sections(body)


def load_sections(path: Path) -> dict[str, list[str]]:
    """直接從檔案路徑取章節。讀不到檔就當作沒有章節，不丟錯。

    artifacts.md 與 decisions/*.md 都只需要挑一兩節出來，缺檔是正常狀態
    （storefront-web 就沒有 artifacts.md），不該讓回來時的輸出整份罷工。
    """
    text = read_text(path)
    if text is None:
        return {}
    return parse_sections(split_frontmatter(text)[1])


def section_first_line(sections: dict[str, list[str]], title: str) -> str | None:
    """取某個章節的第一行有字的內容。找不到章節、或章節整段空白都回 None。"""
    for line in sections.get(title, []):
        stripped = line.strip()
        if stripped:
            return stripped
    return None


def one_line(lines: list[str], sep: str = " ") -> str:
    """把一段內容壓成一行。不刪字，只把空行與縮排收掉。"""
    return sep.join(line.strip() for line in lines if line.strip())


# ---------------------------------------------------------------- 理解債


def debt_items(text: str | None) -> list[tuple[bool, str]]:
    """把 debt.md 拆成 [(還完了嗎, 問題)]。commit / added 那些續行不是條目。"""
    if not text:
        return []
    items: list[tuple[bool, str]] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        match = DEBT_ITEM_RE.match(line)
        if not match:
            continue
        done = match.group("mark").strip().lower() == "x"
        items.append((done, match.group("text").strip()))
    return items


def open_debts(text: str | None) -> list[str]:
    """還沒還的那些，只取問題那一行。答案本來就不寫（SPEC §3.2）。"""
    return [question for done, question in debt_items(text) if not done and question]


def count_open_debt(text: str | None) -> int:
    """數還沒還的條目。索引的「欠 N」與單一專案的「欠債 N」共用這一條規則。

    問題那行留白的條目照樣算一條：檔案裡有一個沒打勾的框，人就是欠著。
    """
    return sum(1 for done, _ in debt_items(text) if not done)


# ---------------------------------------------------------------- 時間


def parse_iso(value: str, label: str) -> datetime:
    """吃 ISO 8601，回帶時區的時間。沒寫時區就補本機時區。

    三支腳本共用同一個 parser，所以 `REENTRY_NOW` 設一次，跑哪一支都是同一個時間基準。
    """
    try:
        moment = datetime.fromisoformat(value.strip())
    except ValueError as exc:
        raise TimeFormatError(f"{label} 不是合法的 ISO 8601 時間：{value}（像 {TIME_EXAMPLE}）") from exc
    return moment if moment.tzinfo else moment.astimezone()


def resolve_root(flag: str | os.PathLike[str] | None = None) -> Path:
    """根目錄：`--root` > `$REENTRY_ROOT` > `~/reentry`。三支腳本一致。"""
    if flag:
        return Path(flag).expanduser()
    return Path(os.environ.get(ENV_ROOT) or DEFAULT_ROOT).expanduser()


def resolve_now(flag: str | None = None) -> datetime:
    """基準時間：`--now` > `$REENTRY_NOW` > 系統時鐘。三支腳本一致。

    可注入是為了測試與除錯能釘死時間，不是為了讓人假造時間。
    """
    if flag:
        return parse_iso(flag, "--now")
    raw = os.environ.get(ENV_NOW)
    if raw:
        return parse_iso(raw, f"${ENV_NOW}")
    return datetime.now().astimezone()


def parse_updated(raw: str | None) -> datetime | None:
    """讀 frontmatter 的 `updated`。看不懂就回 None，讓呼叫端退回 mtime。

    這裡刻意不丟錯：`updated` 打壞不該讓整個索引罷工，降級用 mtime 就好。
    """
    if raw is None:
        return None
    value = raw.strip().strip("\"'").strip()
    if not value:
        return None
    try:
        return parse_iso(value, "updated")
    except TimeFormatError:
        return None


def resolve_touched_at(path: Path, text: str | None = None) -> datetime | None:
    """這個專案上次動過的時間。順序：frontmatter 的 `updated` → 檔案 mtime。

    `updated` 排前面是因為 mtime 撐不過複製與 clone——私有倉 clone 到另一台機器之後
    每個檔的 mtime 都是 clone 當下（SPEC §11 第 7 項就是要建這個倉），那時候索引會
    一致地說「剛剛」，等於整欄失效。`updated` 是內容的一部分，走到哪跟到哪（SPEC §3.1）。

    `updated` 缺、空、或看不懂就退回 mtime：比較弱的時間也好過整筆消失。
    檔案不存在就回 None。
    """
    if text is None:
        text = read_text(path)
    if text is not None:
        meta, _ = split_frontmatter(text)
        moment = parse_updated(meta.get("updated"))
        if moment is not None:
            return moment
    try:
        stamp = path.stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(stamp).astimezone()


def relative_day(then: datetime, now: datetime) -> str:
    """多久沒動。用日曆天相減，不是「經過幾個 86400 秒」。

    昨天晚上十一點動過的東西，人講的是「1 天前」不是「12 小時前」。
    SPEC §5.1 的範例也是這樣算的（8/7 收工、8/12 回來 = 5 天前，實際只隔四天多）。

    兩邊先換算到 `now` 的時區再比日期，不然「哪一天」會跟著誰的時鐘變。
    """
    if then.tzinfo is None:
        then = then.astimezone()
    if now.tzinfo is None:
        now = now.astimezone()
    then = then.astimezone(now.tzinfo)
    days = (now.date() - then.date()).days
    if days < 0:
        # 未來時間（時鐘歪掉、檔案從別台複製過來）不印負數
        return "剛剛"
    if days == 0:
        hours = int((now - then).total_seconds() // 3600)
        return "剛剛" if hours < 1 else f"{hours} 小時前"
    return f"{days} 天前"
