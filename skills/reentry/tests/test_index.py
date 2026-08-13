#!/usr/bin/env python3
"""scripts/reentry_index.py 的測試（SPEC §5.1）。

只用標準函式庫的 unittest。跑法：

    python3 -m unittest discover -s tests -v
    python3 tests/test_index.py

時間一律用**帶時區的**常數，檔案時間一律用絕對時刻（timestamp）。
測試不准依賴跑測試那台機器的時區——不然這份測試在台北綠、在 UTC 紅，
而紅的那個是測試自己壞掉，不是腳本壞掉。
"""

from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = TESTS_DIR.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
SCRIPT = SCRIPTS_DIR / "reentry_index.py"
FIXTURE = TESTS_DIR / "fixture"

TAIPEI = timezone(timedelta(hours=8))

# 基準時間釘死，不吃系統時鐘也不吃系統時區，測試才會穩定。
# 用 +08:00 是因為 fixture 的 updated 都寫 +08:00，兩邊在同一個時間框裡。
NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=TAIPEI)

# fixture 的 handoff.md 各自寫了 updated，這是「多久沒動」的來源（SPEC §3.1）。
FIXTURE_UPDATED = {
    "deploy-cli": datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI),
    "orders-api": datetime(2026, 8, 10, 18, 2, 11, tzinfo=TAIPEI),
    "storefront-web": datetime(2026, 7, 22, 14, 30, 0, tzinfo=TAIPEI),
}


# 有了 .py 副檔名就直接 import。先關掉 bytecode，不要在 scripts/ 留下 __pycache__。
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS_DIR))

import reentry_index as index  # noqa: E402


def write_project(root: Path, name: str, *, handoff=None, debt=None, mtime=None) -> Path:
    """在暫存根目錄下造一個專案資料夾。fixture 一律不動，邊界狀況都造在這裡。

    mtime 吃帶時區的時間，寫進去的是絕對時刻，所以跑測試的機器在哪個時區都一樣。
    """
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    if handoff is not None:
        path = folder / "handoff.md"
        path.write_text(handoff, encoding="utf-8")
        if mtime is not None:
            stamp = mtime.timestamp()
            os.utime(path, (stamp, stamp))
    if debt is not None:
        (folder / "debt.md").write_text(debt, encoding="utf-8")
    return folder


HANDOFF_TEMPLATE = """---
project: {name}
{updated}---

## {section_last}
{last}

## {section_next}
{next_step}

## 關鍵詞
甲, 乙

## 不確定的地方
（無）
"""


def handoff_of(
    name: str,
    last: str = "做了一些事",
    next_step: str = "接著做另一些事",
    updated: datetime | str | None = None,
) -> str:
    """造一份 handoff.md。updated 給 None 就整個欄位不寫，那時間才會退回 mtime。"""
    if updated is None:
        field = ""
    elif isinstance(updated, datetime):
        field = f"updated: {updated.isoformat()}\n"
    else:
        field = f"updated: {updated}\n"
    return HANDOFF_TEMPLATE.format(
        name=name,
        updated=field,
        last=last,
        next_step=next_step,
        section_last=index.SECTION_LAST,
        section_next=index.SECTION_NEXT,
    )


class TempRootTestCase(unittest.TestCase):
    """每個測試一個乾淨的暫存 REENTRY_ROOT。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def render(self, now: datetime = NOW) -> str:
        return index.format_index(index.scan(self.root), now)


class FixtureIndexTest(unittest.TestCase):
    """三個 fixture 專案的完整輸出。"""

    @classmethod
    def setUpClass(cls):
        cls.output = index.format_index(index.scan(FIXTURE), NOW)
        cls.lines = cls.output.split("\n")

    def test_only_registered_folders_show_up(self):
        entries = index.scan(FIXTURE)
        self.assertEqual([e.name for e in entries], ["orders-api", "deploy-cli", "storefront-web"])

    def test_sorted_by_most_recently_touched(self):
        # orders-api 8/10、deploy-cli 8/7、storefront-web 7/22，最近動過的在最上面
        heads = [line for line in self.lines if line and not line.startswith(" ")]
        self.assertEqual([h.split()[0] for h in heads], ["orders-api", "deploy-cli", "storefront-web"])

    def test_deploy_cli_block_matches_spec_example(self):
        self.assertIn(
            "deploy-cli      5 天前    欠 2\n"
            "  上次：把 ConfigStore 的 load/save 寫完，備份邏輯還沒接上。\n"
            "  下一步：實作設定檔損毀時的重建流程，改完跑 `pytest tests/test_config.py`",
            self.output,
        )

    def test_orders_api_block(self):
        # debt.md 只有一條，而且是 - [x]，所以欠 0
        self.assertIn(
            "orders-api      2 天前    欠 0\n"
            "  上次：第三階段的 migration runner 骨架，schema_migration 表建起來了。\n"
            "  下一步：補 `tests/store/test_migration.py`，先測重跑不會重複套用",
            self.output,
        )

    def test_storefront_block_without_artifacts_md(self):
        # 邊界：storefront-web 沒有 artifacts.md。索引不讀那個檔，所以照常出現、欄位齊全。
        self.assertFalse((FIXTURE / "storefront-web" / "artifacts.md").exists())
        self.assertIn(
            "storefront-web  21 天前   欠 1\n"
            "  上次：商品列表頁的響應式排版調完。\n"
            "  下一步：門市查詢的子頁籤還沒做，要補 Leaflet 地圖與門市清單表",
            self.output,
        )

    def test_two_indented_lines_per_entry(self):
        # 每筆就是「一行標頭 + 上次 + 下一步」，多一行都不行（SPEC §5.1）
        blocks = self.output.split("\n\n")
        self.assertEqual(len(blocks), 3)
        for block in blocks:
            rows = block.split("\n")
            self.assertEqual(len(rows), 3)
            self.assertTrue(rows[1].startswith("  上次："))
            self.assertTrue(rows[2].startswith("  下一步："))

    def test_warning_and_misremembered_sections_are_not_printed(self):
        # deploy-cli 有 warning 跟「我當初記錯的」，索引這一層都不該露出來
        self.assertNotIn("四項裡三項跟事實對不上", self.output)
        self.assertNotIn("我當初記錯的", self.output)
        self.assertNotIn("14 passed", self.output)

    def test_keywords_section_not_printed(self):
        self.assertNotIn("關鍵詞", self.output)
        self.assertNotIn("ensure_config_dir", self.output)


class DebtCountTest(unittest.TestCase):
    def test_counts_unchecked_only(self):
        text = (
            "# 理解債 — X\n\n"
            "- [ ] 問題一？\n      commit: aaa1111\n"
            "- [x] 問題二？\n      commit: bbb2222\n"
            "- [X] 問題三？\n"
            "- [ ] 問題四？\n"
        )
        self.assertEqual(index.count_open_debt(text), 2)

    def test_continuation_lines_are_not_items(self):
        text = "- [ ] 只有一條？\n      commit: a3f9c21\n      added: 2026-08-07\n"
        self.assertEqual(index.count_open_debt(text), 1)

    def test_fixture_counts(self):
        for name, expected in (("deploy-cli", 2), ("orders-api", 0), ("storefront-web", 1)):
            with self.subTest(name=name):
                text = (FIXTURE / name / "debt.md").read_text(encoding="utf-8")
                self.assertEqual(index.count_open_debt(text), expected)

    def test_missing_file_counts_zero(self):
        self.assertEqual(index.count_open_debt(None), 0)


class SectionParseTest(unittest.TestCase):
    def sections(self, text: str) -> dict:
        return index.load_note(text)[1]

    def test_last_section_name(self):
        """「上次」欄讀的是 handoff.md 的第一節，名字以共用模組為準。"""
        self.assertEqual(index.SECTION_LAST, "我叫它做什麼，做到哪裡")

    def test_frontmatter_is_ignored(self):
        # warning 那行若被當成內容，「上次」就會抓錯
        sections = self.sections((FIXTURE / "deploy-cli" / "handoff.md").read_text("utf-8"))
        self.assertEqual(
            index.section_first_line(sections, index.SECTION_LAST),
            "把 ConfigStore 的 load/save 寫完，備份邏輯還沒接上。",
        )

    def test_old_section_name_is_not_read(self):
        """改名之後舊名字就是「沒寫」，不要偷偷相容——相容等於兩種格式並存，
        而使用者看到的是「（未填寫）」，他會去改自己的檔案，不會來報 bug。"""
        sections = self.sections("---\nproject: Old\n---\n\n## 這次做了什麼\n舊格式寫的\n")
        self.assertIsNone(index.section_first_line(sections, index.SECTION_LAST))

    def test_first_non_empty_line_wins(self):
        sections = self.sections("## 下一步\n\n\n真正的下一步\n補充說明\n")
        self.assertEqual(index.section_first_line(sections, index.SECTION_NEXT), "真正的下一步")

    def test_missing_section_returns_none(self):
        sections = self.sections(f"## {index.SECTION_LAST}\n有寫\n")
        self.assertIsNone(index.section_first_line(sections, index.SECTION_NEXT))


class AgeTest(unittest.TestCase):
    def test_calendar_days(self):
        # 用日曆天算，不是「經過幾個 86400 秒」：8/7 晚上到 8/12 中午不到五整天，
        # 但人講的是 5 天前，SPEC §5.1 的範例也是這個數字
        moment = datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI)
        self.assertEqual(index.relative_day(moment, NOW), "5 天前")

    def test_same_day_falls_back_to_hours(self):
        # 同一天回來給小時，不要印成 0 天前
        moment = datetime(2026, 8, 12, 1, 0, 0, tzinfo=TAIPEI)
        self.assertEqual(index.relative_day(moment, NOW), "11 小時前")

    def test_just_now(self):
        self.assertEqual(index.relative_day(NOW - timedelta(minutes=20), NOW), "剛剛")

    def test_late_last_night_is_one_day(self):
        # 只隔 12 小時，但跨過午夜就算一天
        moment = datetime(2026, 8, 11, 23, 50, 0, tzinfo=TAIPEI)
        self.assertEqual(index.relative_day(moment, NOW), "1 天前")

    def test_future_time_does_not_print_negative(self):
        # 時鐘歪掉或檔案從別台複製過來
        self.assertEqual(index.relative_day(NOW + timedelta(days=3), NOW), "剛剛")

    def test_days_are_counted_in_the_now_timezone(self):
        """日曆天算在 now 的時區裡，不算在機器的時區裡。

        同一組時刻，用台北的 now 問是 5 天，用夏威夷的 now 問是 4 天——那邊的「今天」
        還沒翻頁。重點是這兩個答案都跟跑測試那台機器的時區無關。
        """
        moment = datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI)
        honolulu = timezone(timedelta(hours=-10))
        self.assertEqual(index.relative_day(moment, NOW), "5 天前")
        self.assertEqual(index.relative_day(moment, NOW.astimezone(honolulu)), "4 天前")

    def test_naive_time_is_read_as_local(self):
        """沒寫時區的時間當本機時間讀。兩邊都用本機框，答案就不隨機器時區跑。"""
        now = datetime(2026, 8, 12, 12, 0, 0).astimezone()
        moment = datetime(2026, 8, 11, 9, 0, 0)
        self.assertEqual(index.relative_day(moment, now), "1 天前")


class TouchedAtTest(TempRootTestCase):
    """「多久沒動」的時間來源：updated 優先，mtime 是備胎（SPEC §3.1）。"""

    def touched(self, name: str):
        return {e.name: e.touched_at for e in index.scan(self.root)}[name]

    def test_updated_wins_over_mtime(self):
        write_project(
            self.root,
            "Cloned",
            handoff=handoff_of("Cloned", updated=datetime(2026, 8, 10, 18, 0, tzinfo=TAIPEI)),
            mtime=datetime(2026, 8, 12, 11, 0, tzinfo=TAIPEI),
        )
        self.assertEqual(self.touched("Cloned"), datetime(2026, 8, 10, 18, 0, tzinfo=TAIPEI))
        self.assertIn("2 天前", self.render())

    def test_fresh_clone_does_not_reset_the_age(self):
        """SPEC §11 第 7 項要把這些檔放進私有倉。clone 之後每個檔的 mtime 都是 clone
        當下，整欄會一致地說「剛剛」。updated 是內容的一部分，clone 不會動到它。"""
        write_project(
            self.root,
            "deploy-cli",
            handoff=handoff_of("deploy-cli", updated=datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI)),
            mtime=NOW,  # 假裝剛剛才 clone 下來
        )
        self.assertIn("5 天前", self.render())
        self.assertNotIn("剛剛", self.render())

    def test_falls_back_to_mtime_when_updated_missing(self):
        write_project(
            self.root,
            "NoField",
            handoff=handoff_of("NoField"),
            mtime=datetime(2026, 8, 11, 9, 0, tzinfo=TAIPEI),
        )
        self.assertNotIn("updated", (self.root / "NoField" / "handoff.md").read_text("utf-8"))
        self.assertIn("1 天前", self.render())

    def test_falls_back_to_mtime_when_updated_is_garbage(self):
        """updated 打壞不該讓這一筆消失，也不該讓整個索引罷工——降級用 mtime。"""
        write_project(
            self.root,
            "Broken",
            handoff=handoff_of("Broken", updated="上週三下午"),
            mtime=datetime(2026, 8, 11, 9, 0, tzinfo=TAIPEI),
        )
        output = self.render()
        self.assertIn("Broken", output)
        self.assertIn("1 天前", output)
        self.assertNotIn("上週三", output)

    def test_empty_updated_falls_back_to_mtime(self):
        write_project(
            self.root,
            "Blankish",
            handoff=handoff_of("Blankish", updated=""),
            mtime=datetime(2026, 8, 9, 9, 0, tzinfo=TAIPEI),
        )
        self.assertIn("3 天前", self.render())

    def test_updated_without_timezone_is_local(self):
        write_project(self.root, "Naive", handoff=handoff_of("Naive", updated="2026-08-11T09:00:00"))
        local_now = datetime(2026, 8, 12, 12, 0).astimezone()
        self.assertIn("1 天前", self.render(now=local_now))

    def test_date_only_updated(self):
        write_project(self.root, "DateOnly", handoff=handoff_of("DateOnly", updated="2026-08-09"))
        self.assertIn("3 天前", self.render(now=datetime(2026, 8, 12, 12, 0).astimezone()))

    def test_updated_ordering_beats_mtime_ordering(self):
        """排序也吃 updated：mtime 的先後跟 updated 相反時，以 updated 為準。"""
        write_project(
            self.root,
            "Older",
            handoff=handoff_of("Older", updated=datetime(2026, 8, 1, 9, 0, tzinfo=TAIPEI)),
            mtime=datetime(2026, 8, 12, 11, 0, tzinfo=TAIPEI),
        )
        write_project(
            self.root,
            "Newer",
            handoff=handoff_of("Newer", updated=datetime(2026, 8, 11, 9, 0, tzinfo=TAIPEI)),
            mtime=datetime(2026, 8, 1, 9, 0, tzinfo=TAIPEI),
        )
        self.assertEqual([e.name for e in index.scan(self.root)], ["Newer", "Older"])


class BoundaryTest(TempRootTestCase):
    def test_folder_without_handoff_is_listed_last(self):
        # SPEC 沒寫死這種資料夾怎麼辦。決定：照列，但排最後、標「還沒交接」。
        # 理由：資料夾存在＝登記過（SPEC §3），靜靜略過就是索引在說謊。
        write_project(
            self.root,
            "Alive",
            handoff=handoff_of("Alive", updated=datetime(2026, 8, 11, 9, 0, tzinfo=TAIPEI)),
        )
        write_project(self.root, "Blank", debt="- [ ] 這條還在？\n")

        output = self.render()
        blocks = output.split("\n\n")
        self.assertEqual(blocks[0].split()[0], "Alive")
        # 沒有 handoff 就沒有「上次／下一步」，不硬湊兩行空殼
        self.assertEqual(
            blocks[-1],
            "Blank       還沒交接  欠 1\n  （沒有 handoff.md，這個專案還沒收過工）",
        )

    def test_several_folders_without_handoff_sort_by_name(self):
        write_project(self.root, "Yankee")
        write_project(self.root, "Bravo")
        entries = index.scan(self.root)
        self.assertEqual([e.name for e in entries], ["Bravo", "Yankee"])

    def test_folder_without_debt_md_counts_zero(self):
        write_project(self.root, "NoDebt", handoff=handoff_of("NoDebt"))
        self.assertIn("欠 0", self.render())

    def test_handoff_without_required_sections(self):
        write_project(self.root, "Sparse", handoff="---\nproject: Sparse\n---\n\n## 關鍵詞\n甲\n")
        output = self.render()
        self.assertIn("  上次：（未填寫）", output)
        self.assertIn("  下一步：（未填寫）", output)

    def test_empty_sections_fall_back_to_placeholder(self):
        write_project(
            self.root, "Empty", handoff=f"## {index.SECTION_LAST}\n\n## {index.SECTION_NEXT}\n\n"
        )
        self.assertIn("  上次：（未填寫）", self.render())

    def test_stray_files_and_hidden_dirs_are_skipped(self):
        write_project(self.root, "Real", handoff=handoff_of("Real"))
        (self.root / "README.md").write_text("不是專案\n", encoding="utf-8")
        (self.root / ".git").mkdir()
        entries = index.scan(self.root)
        self.assertEqual([e.name for e in entries], ["Real"])

    def test_columns_widen_for_long_names(self):
        write_project(
            self.root,
            "a-very-long-project-name",
            handoff=handoff_of("x", updated=datetime(2026, 8, 11, 9, 0, tzinfo=TAIPEI)),
        )
        write_project(
            self.root,
            "短",
            handoff=handoff_of("y", updated=datetime(2026, 8, 10, 9, 0, tzinfo=TAIPEI)),
        )
        heads = [line for line in self.render().split("\n") if line and not line.startswith(" ")]
        self.assertEqual(len(heads), 2)
        # 中文名字算兩格寬，所以要比顯示寬度而不是字元數：「欠」得對齊在同一欄
        offsets = {index.display_width(head.split("欠")[0]) for head in heads}
        self.assertEqual(len(offsets), 1, heads)
        # 欄位撐開了，長名字後面至少還有兩格
        self.assertTrue(any(head.startswith("a-very-long-project-name  ") for head in heads))

    def test_same_time_ties_break_by_name(self):
        stamp = datetime(2026, 8, 11, 9, 0, tzinfo=TAIPEI)
        for name in ("Zeta", "Alpha", "Mid"):
            write_project(self.root, name, handoff=handoff_of(name, updated=stamp))
        entries = index.scan(self.root)
        self.assertEqual([e.name for e in entries], ["Alpha", "Mid", "Zeta"])

    def test_empty_root_prints_a_note(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            code = index.main(["--root", str(self.root), "--now", "2026-08-12T12:00:00+08:00"])
        self.assertEqual(code, 0)
        self.assertIn("底下沒有專案", buffer.getvalue())
        self.assertEqual(index.format_index([], NOW), "")


class DisplayWidthTest(unittest.TestCase):
    def test_cjk_counts_two(self):
        self.assertEqual(index.display_width("欠 2"), 4)
        self.assertEqual(index.display_width("deploy-cli"), 10)
        self.assertEqual(index.display_width("5 天前"), 6)

    def test_pad_reaches_target_width(self):
        self.assertEqual(index.display_width(index.pad("短", 12)), 12)
        self.assertEqual(index.pad("超過寬度就不截斷", 4), "超過寬度就不截斷")


class CliTest(unittest.TestCase):
    """真的跑一次腳本：它必須能在終端機獨立執行，不靠 Claude Code。"""

    def run_script(self, *args, root=None, now=None):
        env = dict(os.environ)
        env.pop("REENTRY_ROOT", None)
        env.pop("REENTRY_NOW", None)
        if root is not None:
            env["REENTRY_ROOT"] = str(root)
        if now is not None:
            env["REENTRY_NOW"] = now
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env
        )

    def test_reads_root_from_env(self):
        result = self.run_script("--now", "2026-08-12T12:00:00+08:00", root=FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.split("\n")[0], "orders-api      2 天前    欠 0")
        self.assertTrue(result.stdout.endswith("\n"))

    def test_root_flag_overrides_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script(
                "--root", str(FIXTURE), "--now", "2026-08-12T12:00:00+08:00", root=tmp
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("deploy-cli", result.stdout)

    def test_reads_now_from_env(self):
        """三支腳本吃同一個 $REENTRY_NOW。這支以前只有 --now，設了環境變數不理人。"""
        result = self.run_script(root=FIXTURE, now="2026-08-12T12:00:00+08:00")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deploy-cli      5 天前", result.stdout)

    def test_now_flag_overrides_env(self):
        result = self.run_script(
            "--now", "2026-08-12T12:00:00+08:00", root=FIXTURE, now="2026-09-30T12:00:00+08:00"
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deploy-cli      5 天前", result.stdout)

    def test_missing_root_exits_nonzero(self):
        result = self.run_script(root=FIXTURE / "does-not-exist")
        self.assertEqual(result.returncode, 1)
        self.assertIn("找不到 REENTRY_ROOT", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_bad_now_value_exits_two(self):
        result = self.run_script("--now", "上週三", root=FIXTURE)
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISO 8601", result.stderr)

    def test_bad_now_env_exits_two(self):
        result = self.run_script(root=FIXTURE, now="上週三")
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISO 8601", result.stderr)

    def test_naive_now_is_accepted(self):
        # 沒寫時區就當本機時間，天數會跟著機器的時區走，所以這裡只確認它跑得起來
        result = self.run_script("--now", "2026-08-12T12:00:00", root=FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deploy-cli", result.stdout)

    def test_empty_root_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.run_script(root=tmp)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("底下沒有專案", result.stdout)

    def test_runs_without_now_flag(self):
        # 沒給基準時間就用系統時鐘，這條只確認不會炸，不驗天數
        result = self.run_script(root=FIXTURE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deploy-cli", result.stdout)

    def test_runs_with_an_empty_path(self):
        """skill 裡靠 `python3 <路徑>` 呼叫：PATH 上不會有這支指令，執行權限也不是條件。"""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            env={"PATH": "", "REENTRY_ROOT": str(FIXTURE), "REENTRY_NOW": "2026-08-12T12:00:00+08:00"},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deploy-cli      5 天前", result.stdout)


class FixtureUntouchedTest(unittest.TestCase):
    """fixture 是共用的，測試不准動到它。"""

    def test_updated_fields_are_the_expected_ones(self):
        """上面那些天數是從 updated 算出來的，這裡確認 fixture 還是那些值。

        不驗 mtime：mtime 是備胎，而且它落在哪一天會跟著跑測試的機器時區變。
        """
        for name, expected in FIXTURE_UPDATED.items():
            with self.subTest(name=name):
                path = FIXTURE / name / "handoff.md"
                meta, _ = index.load_note(path.read_text(encoding="utf-8"))
                self.assertEqual(index.resolve_touched_at(path), expected)
                self.assertEqual(meta["updated"], expected.isoformat())


if __name__ == "__main__":
    unittest.main(verbosity=2)
