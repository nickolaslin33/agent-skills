#!/usr/bin/env python3
"""scripts/reentry_common.py 與「三支腳本對得起來」的測試。

這一份守的是兩件事：

1. 同一條規則只有一份實作（SPEC 沒寫，但三份實作遲早會漂）。理解債的條數在索引裡是
   「欠 N」、在單一專案裡是「欠債 N」，兩邊算出不同的數字時，人會先不信任這個工具。
2. 三支腳本的旗標與環境變數是同一組：`--root` / `$REENTRY_ROOT`、`--now` / `$REENTRY_NOW`，
   優先序都是旗標 > 環境變數 > 預設值。設一次 `$REENTRY_NOW` 跑哪一支都是同一個時間基準。

只用標準函式庫。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL / "scripts"
FIXTURE = SKILL / "tests" / "fixture"
COMMON = SCRIPTS_DIR / "reentry_common.py"
SCRIPTS = {
    name: SCRIPTS_DIR / f"{name}.py"
    for name in ("reentry_index", "reentry_read", "reentry_artifacts")
}

TAIPEI = timezone(timedelta(hours=8))
NOW = datetime(2026, 8, 12, 12, 0, 0, tzinfo=TAIPEI).isoformat()
OTHER_NOW = datetime(2026, 9, 30, 12, 0, 0, tzinfo=TAIPEI).isoformat()

# 有了 .py 副檔名就直接 import，不用再自己組 loader。
# 先關掉 bytecode：scripts/ 是給人照路徑呼叫的目錄，不要在裡面長出 __pycache__。
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS_DIR))

import reentry_common as common  # noqa: E402


def env(**extra) -> dict[str, str]:
    base = {"PATH": os.environ.get("PATH", "/usr/bin:/bin")}
    base.update({k: v for k, v in extra.items() if v is not None})
    return base


def run(script: str, *args, **environ):
    return subprocess.run(
        [sys.executable, str(SCRIPTS[script]), *args],
        capture_output=True,
        text=True,
        env=env(**environ),
    )


class SharedModuleTest(unittest.TestCase):
    def test_every_script_imports_the_shared_module(self):
        for name, path in SCRIPTS.items():
            with self.subTest(script=name):
                self.assertIn("from reentry_common import", path.read_text(encoding="utf-8"))

    def test_no_script_reimplements_shared_logic(self):
        """同一條規則不准在腳本裡再長一份出來。這條是為了擋回頭漂，不是風格潔癖。"""
        shared = (
            "display_width",
            "pad",
            "clip",
            "read_text",
            "split_frontmatter",
            "parse_sections",
            "section_first_line",
            "one_line",
            "count_open_debt",
            "open_debts",
            "debt_items",
            "relative_day",
            "resolve_now",
            "resolve_root",
            "resolve_touched_at",
        )
        for name, path in SCRIPTS.items():
            source = path.read_text(encoding="utf-8")
            for func in shared:
                with self.subTest(script=name, func=func):
                    self.assertIsNone(
                        re.search(rf"^def {func}\(", source, re.MULTILINE),
                        f"{name} 自己又定義了一份 {func}()，共用模組裡已經有了",
                    )

    def test_shared_module_is_stdlib_only(self):
        """腳本要能在終端機直接跑，不裝任何東西（SPEC §8）。"""
        source = COMMON.read_text(encoding="utf-8")
        imported = {
            line.split()[1].split(".")[0]
            for line in source.splitlines()
            if re.match(r"^(import|from)\s", line)
        }
        stdlib = set(sys.stdlib_module_names)
        self.assertTrue(imported <= stdlib, f"跑出標準函式庫以外的 import：{imported - stdlib}")
        # 順便確認它真的躺在 scripts/ 裡，不是要人先 pip install
        self.assertNotIn(str(sysconfig.get_paths()["purelib"]), str(COMMON))

    def test_no_pycache_left_in_scripts(self):
        """scripts/ 是給人照路徑呼叫的目錄，不要在裡面長出 __pycache__。"""
        run("reentry_index", "--root", str(FIXTURE), "--now", NOW)
        self.assertFalse((SCRIPTS_DIR / "__pycache__").exists())


class SectionNameTest(unittest.TestCase):
    """章節名只有一份，而且是新的那一份。

    handoff.md 的第一節同時被索引的「上次」欄與回來時的第二段讀。兩邊各寫一份字串，
    漏改的那邊會安靜地印「（未填寫）」——看起來像使用者沒寫，不像程式讀錯。
    """

    OLD_NAMES = ("這次做了什麼", "## 統計")

    def test_names_match_the_documented_format(self):
        self.assertEqual(common.SECTION_LAST, "我叫它做什麼，做到哪裡")
        self.assertEqual(common.SECTION_NEXT, "下一步")
        self.assertEqual(common.SECTION_CHANGED, "改了什麼")
        self.assertEqual(common.SECTION_VERIFY, "驗證")
        self.assertEqual(common.SECTION_DETAIL, "明細")
        self.assertEqual(common.SECTION_DECISION, "決定")

    def test_no_script_hardcodes_a_section_name(self):
        """腳本裡不准再出現章節名的字面值，一律走共用常數。"""
        names = (
            common.SECTION_LAST,
            common.SECTION_NEXT,
            common.SECTION_CHANGED,
            common.SECTION_VERIFY,
            common.SECTION_DETAIL,
            common.SECTION_DECISION,
        )
        for script, path in SCRIPTS.items():
            source = path.read_text(encoding="utf-8")
            for value in names:
                with self.subTest(script=script, value=value):
                    self.assertNotIn(f'"{value}"', source)

    def test_old_names_are_gone_everywhere(self):
        """腳本、模板、fixture 都不准留舊名字。留著就是兩種格式並存。"""
        targets = [
            *SCRIPTS_DIR.glob("*.py"),
            *(SKILL / "assets" / "templates").glob("*.md"),
            *FIXTURE.rglob("*.md"),
        ]
        self.assertGreater(len(targets), 8, "檔案掃不到，這條測試等於沒測")
        for path in targets:
            text = path.read_text(encoding="utf-8")
            for old in self.OLD_NAMES:
                with self.subTest(path=path.name, old=old):
                    # 共用模組的註解裡有一句「不是『這次做了什麼』」，那是說明不是格式
                    if path.name == "reentry_common.py" and old == "這次做了什麼":
                        continue
                    self.assertNotIn(old, text)

    def test_placeholders_announce_themselves(self):
        """佔位句要一眼看得出沒填。它會被印進回來時的輸出，所以不能長得像正常內容。"""
        for placeholder in (common.CHANGED_PLACEHOLDER, common.VERIFY_PLACEHOLDER):
            with self.subTest(placeholder=placeholder):
                self.assertIn("尚未填寫", placeholder)
                self.assertTrue(placeholder.startswith("（"))


class PortabilityTest(unittest.TestCase):
    """跨 agent 可攜：Claude Code、Codex、Gemini、Grok、Kiro 底下都要跑得動。

    呼叫方式一律是 `python3 "$SKILL_DIR"/scripts/<名字>.py`，所以不准依賴執行權限、
    不准依賴 PATH 上有這幾支指令，也不准依賴 skill 裝在哪個路徑。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.workdir = self.tmp / "src"
        self.workdir.mkdir()

    def test_usage_lines_show_the_python3_invocation(self):
        """docstring 要教人怎麼叫，而且不能留舊的連字號指令名。"""
        for name, path in SCRIPTS.items():
            with self.subTest(script=name):
                source = path.read_text(encoding="utf-8")
                self.assertIn(f'python3 "$SKILL_DIR"/scripts/{name}.py', source)
                self.assertIn("$SKILL_DIR", source)
                self.assertNotIn(name.replace("_", "-"), source)

    def test_runs_from_any_install_dir_without_exec_bit(self):
        """整個 scripts/ 複製到別的路徑、全部 0644，照樣跑得動。

        index 與 read 連 PATH 都清空；artifacts 留著 PATH 是因為它 shell out 去跑 git，
        跟腳本自己在不在 PATH 上是兩回事。
        """
        installed = self.tmp / "some skill dir" / "scripts"
        shutil.copytree(SCRIPTS_DIR, installed, ignore=shutil.ignore_patterns("__pycache__"))
        for script in installed.glob("*.py"):
            script.chmod(0o644)

        cases = (
            ("reentry_index", (), ""),
            ("reentry_read", ("deploy-cli",), ""),
            ("reentry_artifacts", ("Demo", str(self.workdir), "--stdout"), os.environ.get("PATH", "")),
        )
        for name, args, path_value in cases:
            with self.subTest(script=name):
                result = subprocess.run(
                    [sys.executable, str(installed / f"{name}.py"), *args],
                    capture_output=True,
                    text=True,
                    env={"PATH": path_value, "REENTRY_ROOT": str(FIXTURE), "REENTRY_NOW": NOW},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertTrue(result.stdout.strip(), "沒有輸出")


class DebtCountAgreementTest(unittest.TestCase):
    """索引的「欠 N」與單一專案的「欠債 N」必須是同一個數字。"""

    CASES = (
        "- [ ] 一？\n- [x] 二？\n- [X] 三？\n- [ ] 四？\n",
        "- [ ] 一？\n      commit: abc1234\n      added: 2026-08-12\n",
        "* [ ] 星號也算一條？\n+ [ ] 加號也算？\n",
        "- [ ] \n",  # 沒寫問題的空條目
        "- [~] 記號打壞的算不算？\n",
        "",
        "# 理解債 — 空的\n\n還沒欠過\n",
    )

    def test_same_number_from_both_paths(self):
        for text in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(
                    common.count_open_debt(text),
                    len([q for q in common.open_debts(text) if q]) + self.blank_items(text),
                )

    @staticmethod
    def blank_items(text: str) -> int:
        return sum(1 for done, q in common.debt_items(text) if not done and not q)

    def test_fixture_counts_agree_with_the_scripts(self):
        index_out = run("reentry_index", "--root", str(FIXTURE), "--now", NOW).stdout
        for name, expected in (("deploy-cli", 2), ("orders-api", 0), ("storefront-web", 1)):
            with self.subTest(project=name):
                text = (FIXTURE / name / "debt.md").read_text(encoding="utf-8")
                self.assertEqual(common.count_open_debt(text), expected)
                self.assertRegex(index_out, rf"(?m)^{name}\s.*欠 {expected}$")
                read_out = run(
                    "reentry_read", name, "--root", str(FIXTURE), "--now", NOW
                ).stdout
                self.assertIn(f"欠債 {expected}", read_out)


class TimeBaseTest(unittest.TestCase):
    """$REENTRY_NOW 設一次，三支腳本看到的是同一個時間。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.workdir = Path(self._tmp.name) / "src"
        self.workdir.mkdir()

    def artifacts_stamp(self, *args, **environ) -> str:
        result = run("reentry_artifacts", "Demo", str(self.workdir), "--stdout", *args, **environ)
        self.assertEqual(result.returncode, 0, result.stderr)
        return re.search(r"^generated: (.+)$", result.stdout, re.MULTILINE).group(1)

    def test_env_now_reaches_all_three(self):
        index_out = run("reentry_index", REENTRY_ROOT=str(FIXTURE), REENTRY_NOW=NOW).stdout
        read_out = run("reentry_read", "deploy-cli", REENTRY_ROOT=str(FIXTURE), REENTRY_NOW=NOW).stdout
        stamp = self.artifacts_stamp(REENTRY_NOW=NOW)

        self.assertRegex(index_out, r"deploy-cli\s+5 天前", index_out)
        self.assertRegex(index_out, r"deploy-cli\s+5 天前", read_out)
        self.assertEqual(stamp, NOW)

    def test_flag_beats_env_in_all_three(self):
        index_out = run(
            "reentry_index", "--now", NOW, REENTRY_ROOT=str(FIXTURE), REENTRY_NOW=OTHER_NOW
        ).stdout
        read_out = run(
            "reentry_read", "deploy-cli", "--now", NOW, REENTRY_ROOT=str(FIXTURE), REENTRY_NOW=OTHER_NOW
        ).stdout
        stamp = self.artifacts_stamp("--now", NOW, REENTRY_NOW=OTHER_NOW)

        self.assertRegex(index_out, r"deploy-cli\s+5 天前", index_out)
        self.assertRegex(index_out, r"deploy-cli\s+5 天前", read_out)
        self.assertEqual(stamp, NOW)

    def test_same_parser_and_same_exit_code_for_garbage(self):
        for script, args in (
            ("reentry_index", ()),
            ("reentry_read", ("deploy-cli",)),
            ("reentry_artifacts", ("Demo", str(self.workdir), "--stdout")),
        ):
            for source in ("flag", "env"):
                with self.subTest(script=script, source=source):
                    if source == "flag":
                        result = run(script, *args, "--now", "上週三", REENTRY_ROOT=str(FIXTURE))
                    else:
                        result = run(script, *args, REENTRY_ROOT=str(FIXTURE), REENTRY_NOW="上週三")
                    self.assertEqual(result.returncode, 2, result.stderr)
                    self.assertIn("ISO 8601", result.stderr)

    def test_naive_time_accepted_everywhere(self):
        naive = "2026-08-12T12:00:00"
        for script, args in (
            ("reentry_index", ()),
            ("reentry_read", ("deploy-cli",)),
            ("reentry_artifacts", ("Demo", str(self.workdir), "--stdout")),
        ):
            with self.subTest(script=script):
                result = run(script, *args, "--now", naive, REENTRY_ROOT=str(FIXTURE))
                self.assertEqual(result.returncode, 0, result.stderr)


class RootFlagTest(unittest.TestCase):
    """--root 三支都要有，而且都蓋得掉 $REENTRY_ROOT。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        self.decoy = self.tmp / "decoy"
        (self.decoy / "Demo").mkdir(parents=True)

    def test_index_root_flag(self):
        result = run("reentry_index", "--root", str(FIXTURE), "--now", NOW, REENTRY_ROOT=str(self.decoy))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("deploy-cli", result.stdout)

    def test_read_root_flag(self):
        result = run(
            "reentry_read", "deploy-cli", "--root", str(FIXTURE), "--now", NOW,
            REENTRY_ROOT=str(self.decoy),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("5 天前", result.stdout)

    def test_artifacts_root_flag(self):
        real = self.tmp / "real"
        (real / "Demo").mkdir(parents=True)
        workdir = self.tmp / "src"
        workdir.mkdir()

        result = run(
            "reentry_artifacts", "Demo", str(workdir), "--root", str(real), "--now", NOW,
            REENTRY_ROOT=str(self.decoy),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((real / "Demo" / "artifacts.md").exists())
        self.assertFalse((self.decoy / "Demo" / "artifacts.md").exists())


class TouchedAtTest(unittest.TestCase):
    """時間來源的單元測試：updated 優先，mtime 是備胎（SPEC §3.1）。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "handoff.md"

    def write(self, updated: str | None, mtime: datetime) -> Path:
        field = f"updated: {updated}\n" if updated is not None else ""
        self.path.write_text(
            f"---\nproject: P\n{field}---\n\n## {common.SECTION_LAST}\n做了事\n", encoding="utf-8"
        )
        os.utime(self.path, (mtime.timestamp(), mtime.timestamp()))
        return self.path

    def test_updated_wins(self):
        updated = datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI)
        path = self.write(updated.isoformat(), datetime(2026, 8, 12, 12, 0, tzinfo=TAIPEI))
        self.assertEqual(common.resolve_touched_at(path), updated)

    def test_mtime_when_updated_absent(self):
        mtime = datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI)
        path = self.write(None, mtime)
        self.assertEqual(common.resolve_touched_at(path), mtime)

    def test_mtime_when_updated_is_garbage(self):
        mtime = datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI)
        for garbage in ("上週三下午", "2026-13-45T99:99:99", "yes", "2026/08/07"):
            with self.subTest(garbage=garbage):
                path = self.write(garbage, mtime)
                self.assertEqual(common.resolve_touched_at(path), mtime)

    def test_quoted_updated_is_accepted(self):
        updated = datetime(2026, 8, 7, 23, 14, 5, tzinfo=TAIPEI)
        path = self.write(f'"{updated.isoformat()}"', datetime(2026, 8, 12, 12, 0, tzinfo=TAIPEI))
        self.assertEqual(common.resolve_touched_at(path), updated)

    def test_missing_file_is_none(self):
        self.assertIsNone(common.resolve_touched_at(self.path.parent / "nope.md"))

    def test_parse_updated_never_raises(self):
        """updated 打壞只降級，不丟錯——一個欄位不該讓整個索引罷工。"""
        for value in (None, "", "   ", "什麼都不是", '""'):
            with self.subTest(value=value):
                self.assertIsNone(common.parse_updated(value))


if __name__ == "__main__":
    unittest.main(verbosity=2)
