#!/usr/bin/env python3
"""scripts/reentry_read.py 的測試（SPEC §5.2）。

只用標準函式庫，直接跑腳本，測的是終端機上真的看得到的輸出。
fixture 一個字都不改，需要別的資料就自己開暫存目錄。

時間一律用帶時區的常數、檔案時間一律用絕對時刻，測試不准依賴機器的時區。
"""

import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL / "scripts"
SCRIPT = SCRIPTS_DIR / "reentry_read.py"
FIXTURE = SKILL / "tests" / "fixture"

TAIPEI = timezone(timedelta(hours=8))

# 固定基準時間，讓「N 天前」在任何一天、任何時區跑都一樣
NOW_DT = datetime(2026, 8, 12, 18, 0, 0, tzinfo=TAIPEI)
NOW = NOW_DT.isoformat()

PROMPT = "先用自己的話說一次下一步再動手。"


# 直接 import，常數與 rows() 要拿來量輸出。
# 先關掉 bytecode，不要在 scripts/ 留下 __pycache__。
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS_DIR))

import reentry_common as common  # noqa: E402
import reentry_read as read  # noqa: E402

LAST = read.LABEL_LAST
DECISION = read.LABEL_DECISION


def run(project=None, root=FIXTURE, now=NOW, extra_args=()):
    args = [sys.executable, str(SCRIPT)]
    if project is not None:
        args.append(project)
    args.extend(extra_args)
    env = {"PATH": "/usr/bin:/bin", "REENTRY_ROOT": str(root)}
    if now:
        env["REENTRY_NOW"] = now
    return subprocess.run(args, capture_output=True, text=True, env=env)


def handoff(project="X", last="做了事", next_step="做下一件", updated=None, extra="", warning=None):
    fields = "".join(
        f"{key}: {value}\n"
        for key, value in (("updated", updated), ("warning", warning))
        if value is not None
    )
    return (
        f"---\nproject: {project}\n{fields}---\n\n"
        f"## {common.SECTION_LAST}\n{last}\n\n## {common.SECTION_NEXT}\n{next_step}\n{extra}"
    )


def artifacts(changed=common.CHANGED_PLACEHOLDER, verify=common.VERIFY_PLACEHOLDER, detail="a.py  +1 −0"):
    """三節的 artifacts.md。預設就是腳本剛產完、還沒有人填的樣子。"""
    return (
        "---\nproject: X\ngenerated: 2026-08-12T23:16:41+08:00\n---\n\n"
        f"## {common.SECTION_CHANGED}\n{changed}\n\n"
        f"## {common.SECTION_VERIFY}\n{verify}\n\n"
        f"## {common.SECTION_DETAIL}\n{detail}\n"
    )


def decision(text="就這樣決定了。", date="2026-08-12", extra=""):
    return f"---\nproject: X\ndate: {date}\npromoted: false\n---\n\n## 決定\n{text}\n{extra}"


def write_project(root: Path, name="P", *, handoff_text=None, artifacts_text=None, decisions=None, debt=None, questions=None):
    """在暫存根目錄造一個專案。fixture 一律不動，邊界狀況都造在這裡。"""
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "handoff.md").write_text(handoff_text or handoff(name), encoding="utf-8")
    if artifacts_text is not None:
        (folder / "artifacts.md").write_text(artifacts_text, encoding="utf-8")
    if debt is not None:
        (folder / "debt.md").write_text(debt, encoding="utf-8")
    if questions is not None:
        (folder / "open-questions.md").write_text(questions, encoding="utf-8")
    for filename, text in (decisions or {}).items():
        (folder / "decisions").mkdir(exist_ok=True)
        (folder / "decisions" / filename).write_text(text, encoding="utf-8")
    return folder


class TestHiddenSection(unittest.TestCase):
    """「我當初記錯的」絕對不能出現在輸出裡。這是規格的硬條件。"""

    def test_heading_absent(self):
        out = run("deploy-cli").stdout
        self.assertNotIn("我當初記錯的", out)

    def test_content_absent(self):
        """標題不見了不算數，底下每一條內容也要不見。"""
        out = run("deploy-cli").stdout
        for line in (
            "我寫「測試全過」，實際是 14 passed / 2 failed",
            "我說備份寫在 save 裡，實際在 load 的例外處理",
        ):
            self.assertNotIn(line, out)
        # 抽幾個只在該段出現的關鍵字再確認一次
        for token in ("測試全過", "例外處理"):
            self.assertNotIn(token, out)

    def test_content_really_is_in_the_fixture(self):
        """確認上面那個測試不是因為 fixture 根本沒寫才過的。"""
        text = (FIXTURE / "deploy-cli" / "handoff.md").read_text(encoding="utf-8")
        self.assertIn("## 我當初記錯的", text)
        self.assertIn("我寫「測試全過」", text)


class TestOrder(unittest.TestCase):
    """順序固定：警告 → 上次叫它做什麼、做到哪裡 → 上次的決定 → 欠債 → 下一步 → 提示。"""

    def test_blocks_in_order_with_warning(self):
        # deploy-cli 有警告、沒有決策紀錄
        out = run("deploy-cli").stdout
        positions = [out.index(label) for label in ("警告", LAST, "欠債", "下一步")]
        self.assertEqual(positions, sorted(positions))

    def test_blocks_in_order_with_decision(self):
        # orders-api 沒有警告、有決策紀錄
        out = run("orders-api").stdout
        positions = [out.index(label) for label in (LAST, DECISION, "欠債", "下一步")]
        self.assertEqual(positions, sorted(positions))

    def test_all_five_blocks_in_order(self):
        """警告與決定同時存在時的完整順序。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(
                root,
                "Full",
                handoff_text=handoff("Full", warning="對不上的地方很多。"),
                artifacts_text=artifacts(changed="改了 1 個設定檔", verify="pytest 3 passed"),
                decisions={"2026-08-12-要不要重建.md": decision("損毀就重建，不中止。")},
                debt="- [ ] 為什麼？\n",
            )
            out = run("Full", root=root).stdout
        positions = [out.index(label) for label in ("警告", LAST, DECISION, "欠債", "下一步")]
        self.assertEqual(positions, sorted(positions))

    def test_next_step_after_debt_even_without_warning(self):
        out = run("orders-api").stdout
        self.assertLess(out.index(LAST), out.index("欠債"))
        self.assertLess(out.index("欠債"), out.index("下一步"))

    def test_prompt_is_the_last_line(self):
        lines = [line for line in run("deploy-cli").stdout.split("\n") if line.strip()]
        self.assertEqual(lines[-1], PROMPT)

    def test_next_step_is_the_last_block(self):
        """下一步壓在最後是刻意的，提示句後面不能再冒出別的東西。"""
        out = run("storefront-web").stdout
        tail = out[out.index("下一步") :]
        self.assertIn("門市查詢的子頁籤還沒做", tail)
        self.assertTrue(tail.rstrip().endswith(PROMPT))


class TestWarning(unittest.TestCase):
    def test_shown_when_present(self):
        out = run("deploy-cli").stdout
        self.assertIn("這批產出你基本沒吸收，四項裡三項跟事實對不上。", out)

    def test_absent_when_key_missing(self):
        self.assertNotIn("警告", run("orders-api").stdout)

    def test_absent_when_false(self):
        out = run("storefront-web").stdout
        self.assertNotIn("警告", out)
        self.assertNotIn("false", out)


class TestArtifacts(unittest.TestCase):
    """artifacts.md 印 `## 改了什麼` 與 `## 驗證`，`## 明細` 永遠不印。"""

    def test_changed_and_verify_shown(self):
        out = run("orders-api").stdout
        self.assertIn("新增 migration runner 與第一份 schema", out)
        self.assertIn("pytest 8 passed", out)

    def test_verify_survives_even_when_the_description_is_long(self):
        """一行放不下就砍描述，不砍數字——「14 passed / 2 failed」砍掉就只剩印象。"""
        out = run("deploy-cli").stdout
        self.assertIn("pytest 14 passed / 2 failed", out)
        self.assertIn("…", out)  # 被砍掉的是描述那半邊，而且看得出被砍了

    def test_detail_not_shown(self):
        """明細是給「改了什麼」查證用的原始事實，不是回來時要讀的東西。"""
        out = run("deploy-cli").stdout
        self.assertNotIn("明細", out)
        self.assertNotIn("改了 3 個檔（+119 −4）", out)
        self.assertNotIn("比較基準", out)
        for path in ("src/stock_tui/config/store.py", "pyproject.toml"):
            self.assertNotIn(path, out)
        # tests/test_config.py 在人自己寫的「下一步」裡也出現過，
        # 所以只看抬頭到欠債之間這段，確認明細沒有混進來。
        head = out[: out.index("欠債")]
        self.assertNotIn("tests/test_config.py", head)

    def test_detail_really_is_in_the_fixture(self):
        """確認上面那條不是因為 fixture 根本沒有明細才過的。"""
        text = (FIXTURE / "deploy-cli" / "artifacts.md").read_text(encoding="utf-8")
        self.assertIn("## 明細", text)
        self.assertIn("src/stock_tui/config/store.py", text)

    def test_unfilled_placeholder_is_visible(self):
        """`## 改了什麼` 腳本填不了，留的是自曝的佔位句：沒人填就會出現在回來時的輸出裡。

        這條就是「不可能不小心留著」的機制本身——佔位句不是註解，是會被印給使用者看的。
        """
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root, "Fresh", artifacts_text=artifacts())
            out = run("Fresh", root=root).stdout
        self.assertIn("尚未填寫", out)
        self.assertIn("agent 要看著", out)

    def test_missing_artifacts_file_is_fine(self):
        """storefront-web 沒有 artifacts.md，照樣要能印完整輸出。"""
        self.assertFalse((FIXTURE / "storefront-web" / "artifacts.md").exists())
        result = run("storefront-web")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("商品列表頁的響應式排版調完。", result.stdout)
        self.assertIn(PROMPT, result.stdout)

    def test_only_one_of_the_two_sections(self):
        """只有其中一節有內容時不要留下孤零零的分隔符。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root, "OnlyChanged", artifacts_text=artifacts(changed="改了 1 個檔", verify=""))
            write_project(root, "OnlyVerify", artifacts_text=artifacts(changed="", verify="pytest 3 passed"))
            first = run("OnlyChanged", root=root).stdout
            second = run("OnlyVerify", root=root).stdout
        self.assertIn("改了 1 個檔", first)
        self.assertNotIn(read.ARTIFACTS_SEP, first)
        self.assertIn("pytest 3 passed", second)
        self.assertNotIn(read.ARTIFACTS_SEP, second)


class TestDecision(unittest.TestCase):
    """「上次的決定」只在 decisions/ 真的有東西時才印。

    永遠留一個空欄位會退化成每次略過的噪音；但有決定的那幾次，那是回來最需要知道的
    東西之一。所以是「有就印、沒有就整段不存在」，不是「印一個（無）」。
    """

    def test_shown_when_a_decision_exists(self):
        out = run("orders-api").stdout
        self.assertIn(DECISION, out)
        self.assertIn("migration 版本記在 DB 的 schema_migration 表，不靠檔名排序。", out)

    def test_absent_when_the_project_has_no_decisions(self):
        # deploy-cli 有 decisions/ 但裡面是空的——收工沒產生值得記的決定就是這個樣子
        self.assertEqual(list((FIXTURE / "deploy-cli" / "decisions").iterdir()), [])
        out = run("deploy-cli").stdout
        self.assertNotIn(DECISION, out)
        self.assertNotIn("決定", out)  # 連「（無）」這種空殼都不留

    def test_only_the_decision_section_is_printed(self):
        """排除了什麼／後續 todo／技術債是收工端的東西，不進回來時的輸出。"""
        out = run("orders-api").stdout
        self.assertNotIn("排除了什麼", out)
        self.assertNotIn("手動改過檔名", out)
        self.assertNotIn("技術債", out)

    def test_latest_entry_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(
                root,
                "Many",
                decisions={
                    "2026-08-01-舊的.md": decision("最舊的決定。", date="2026-08-01"),
                    "2026-08-11-最新的.md": decision("最新的決定。", date="2026-08-11"),
                    "2026-08-05-中間的.md": decision("中間的決定。", date="2026-08-05"),
                },
            )
            out = run("Many", root=root).stdout
        self.assertIn("最新的決定。", out)
        self.assertNotIn("最舊的決定。", out)
        self.assertNotIn("中間的決定。", out)

    def test_filename_date_is_the_fallback(self):
        """frontmatter 的 date 打壞或沒寫時，退回檔名前面那段日期。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(
                root,
                "ByName",
                decisions={
                    "2026-08-01-舊的.md": "## 決定\n最舊的決定。\n",
                    "2026-08-11-最新的.md": "## 決定\n最新的決定。\n",
                },
            )
            out = run("ByName", root=root).stdout
        self.assertIn("最新的決定。", out)
        self.assertNotIn("最舊的決定。", out)

    def test_empty_decision_section_counts_as_none(self):
        """有檔案但 `## 決定` 沒寫，等於沒有決定——不要印一個空段落。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root, "Blank", decisions={"2026-08-12-空的.md": decision("")})
            out = run("Blank", root=root).stdout
        self.assertNotIn(DECISION, out)

    def test_empty_decisions_dir_counts_as_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = write_project(root, "Empty")
            (folder / "decisions").mkdir()
            out = run("Empty", root=root).stdout
        self.assertNotIn(DECISION, out)
        self.assertIn(PROMPT, out)

    def test_non_markdown_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            folder = write_project(root, "Mixed", decisions={"2026-08-01-真的.md": decision("真的決定。")})
            (folder / "decisions" / "2026-08-12-筆記.txt").write_text(
                "## 決定\n這個不算。\n", encoding="utf-8"
            )
            out = run("Mixed", root=root).stdout
        self.assertIn("真的決定。", out)
        self.assertNotIn("這個不算。", out)

    def test_multi_line_decision_is_squeezed_to_one_line(self):
        """決定寫成兩行也只佔一行——20 列的預算沒有第二行可以給（見 read 的段落預算）。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(
                root,
                "Wordy",
                decisions={"2026-08-12-兩行.md": decision("第一行的決定。\n第二行的補充。")},
            )
            out = run("Wordy", root=root).stdout
        block = next(b for b in out.split("\n\n") if b.startswith(DECISION))
        self.assertEqual(len(block.split("\n")), 2, block)


class TestDebt(unittest.TestCase):
    def test_only_unchecked(self):
        out = run("deploy-cli").stdout
        self.assertIn("欠債 2", out)
        self.assertIn("為什麼備份要在 load 失敗時做", out)
        self.assertIn("ensure_config_dir 為什麼要吞掉 FileExistsError", out)
        self.assertNotIn("為什麼 AppConfig 用 dataclass", out)

    def test_zero_when_all_paid(self):
        out = run("orders-api").stdout
        self.assertIn("欠債 0", out)
        self.assertNotIn("為什麼 migration 要記在 DB 裡", out)

    def test_commit_and_added_not_printed(self):
        out = run("deploy-cli").stdout
        self.assertNotIn("a3f9c21", out)
        self.assertNotIn("added:", out)

    def test_missing_debt_file_counts_as_zero(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Solo").mkdir()
            (root / "Solo" / "handoff.md").write_text(handoff("Solo"), encoding="utf-8")
            result = run("Solo", root=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("欠債 0", result.stdout)

    def test_long_debt_list_is_capped(self):
        """欠債太多時只列前兩條，剩幾條掛在標題上。輸出短是成立條件（SPEC §5.2）。"""
        with self.crowded_project(count=7) as root:
            out = run("Many", root=root).stdout
        self.assertIn("欠債 7", out)
        self.assertEqual(out.count("為什麼？"), read.MAX_DEBT_SHOWN)
        self.assertIn("其餘看 debt.md", out)

    def test_debt_block_body_never_exceeds_two_lines(self):
        for count in (0, 1, 2, 3, 12):
            with self.subTest(count=count), self.crowded_project(count=count) as root:
                out = run("Many", root=root).stdout
                block = next(b for b in out.split("\n\n") if b.startswith("欠債"))
                self.assertLessEqual(len(block.split("\n")[1:]), read.BLOCK_BODY_LINES, block)

    @staticmethod
    @contextmanager
    def crowded_project(count: int):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Many").mkdir()
            (root / "Many" / "handoff.md").write_text(handoff("Many"), encoding="utf-8")
            items = "\n".join(
                f"- [ ] 第 {i} 個為什麼？\n      commit: abc123{i}" for i in range(1, count + 1)
            )
            (root / "Many" / "debt.md").write_text(f"# 理解債 — Many\n\n{items}\n", encoding="utf-8")
            yield root


class TestBrevity(unittest.TestCase):
    """SPEC §5.2 的成立條件（不是建議）：每段各一到兩行，整體不超過螢幕一半。

    量的是**螢幕上的列數**不是字串裡的換行數。一行 400 字的「我叫它做什麼」在字串裡
    是一行，在 80 欄的終端機上是五列——只數 `\\n` 的測試永遠是綠的，而人看到的還是
    要捲的畫面。
    """

    def rows(self, out: str) -> int:
        return read.rows(out.rstrip("\n").split("\n"))

    def blocks(self, out: str) -> list[str]:
        return [b for b in out.rstrip("\n").split("\n\n") if b.strip()]

    def assert_fits(self, out: str):
        lines = out.rstrip("\n").split("\n")
        for line in lines:
            self.assertLessEqual(
                read.display_width(line), read.SCREEN_COLS, f"這行會折行：{line!r}"
            )
        self.assertLessEqual(self.rows(out), read.MAX_ROWS, out)
        # blocks[0] 是抬頭、最後一塊是提示句，中間每一段的內文都不准超過兩行
        for block in self.blocks(out)[1:-1]:
            self.assertLessEqual(len(block.split("\n")[1:]), read.BLOCK_BODY_LINES, block)

    def test_fixture_projects_fit(self):
        for project in ("deploy-cli", "orders-api", "storefront-web"):
            with self.subTest(project=project):
                self.assert_fits(run(project).stdout)

    def test_hostile_project_still_fits(self):
        """把每一段都灌到爆的專案。沒有截斷的話這條一定紅。"""
        with self.hostile_project() as (root, material):
            out = run("Hostile", root=root).stdout
        # 先確認材料真的夠長，不然這個測試等於沒測
        for key in ("last", "warning", "changed", "decision"):
            self.assertGreater(read.display_width(material[key]), read.SCREEN_COLS, key)
        self.assertGreater(material["debts"], read.BLOCK_BODY_LINES)
        self.assert_fits(out)

    def test_hostile_project_keeps_every_block(self):
        """塞不下不是靠少印一段解決的：五段都在，而且驗證那半邊沒被描述擠掉。"""
        with self.hostile_project() as (root, material):
            out = run("Hostile", root=root).stdout
        for label in ("警告", LAST, DECISION, "欠債", "下一步"):
            self.assertIn(label, out)
        self.assertIn(material["verify"], out)

    def test_truncated_lines_are_marked(self):
        """截掉的東西要看得出來被截了，不能無聲消失。"""
        with self.hostile_project() as (root, _):
            out = run("Hostile", root=root).stdout
        self.assertIn("…", out)

    def test_nothing_is_dropped_silently_from_the_debt_count(self):
        """只列兩條，但欠幾條要照實印。"""
        with self.hostile_project() as (root, material):
            out = run("Hostile", root=root).stdout
        self.assertIn(f"欠債 {material['debts']}", out)

    @staticmethod
    @contextmanager
    def hostile_project():
        """每一段都灌到爆，而且警告與決定同時存在——這是 20 列預算的最壞情況。"""
        material = {
            "warning": "這批產出你基本沒吸收，" * 12,
            "last": "把 ConfigStore 的 load/save 寫完，備份邏輯還沒接上，" * 20,
            "next": "實作設定檔損毀時的重建流程，改完跑 pytest，" * 15,
            "changed": "改了設定載入檔、CLI 進入點、還有一大票測試檔，" * 10,
            "verify": "pytest 118 passed / 4 failed",
            "decision": "損毀時直接以預設值重建不中止啟動，" * 8,
            "debts": 12,
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "root"
            (root / "Hostile" / "decisions").mkdir(parents=True)
            (root / "Hostile" / "handoff.md").write_text(
                "---\nproject: Hostile\n"
                f"updated: {(NOW_DT - timedelta(days=5)).isoformat()}\n"
                f"warning: {material['warning']}\n---\n\n"
                # 多行的一段，壓成一行之後會很長
                f"## {common.SECTION_LAST}\n" + "\n".join([material["last"]] * 4) + "\n\n"
                f"## {common.SECTION_NEXT}\n{material['next']}\n",
                encoding="utf-8",
            )
            (root / "Hostile" / "debt.md").write_text(
                "# 理解債 — Hostile\n\n"
                + "\n".join(
                    f"- [ ] 第 {i} 條：為什麼這裡非得這樣寫不可，" * 1 + "換個寫法會怎樣？" * 8
                    for i in range(1, material["debts"] + 1)
                )
                + "\n",
                encoding="utf-8",
            )
            (root / "Hostile" / "artifacts.md").write_text(
                "---\nproject: Hostile\ngenerated: 2026-08-07T23:16:41+08:00\n---\n\n"
                f"## {common.SECTION_CHANGED}\n" + "\n".join([material["changed"]] * 3) + "\n\n"
                f"## {common.SECTION_VERIFY}\n{material['verify']}\n\n"
                f"## {common.SECTION_DETAIL}\n" + "x.py  +1 −0\n" * 30,
                encoding="utf-8",
            )
            (root / "Hostile" / "decisions" / "2026-08-07-又臭又長的決定.md").write_text(
                decision("\n".join([material["decision"]] * 3), date="2026-08-07"),
                encoding="utf-8",
            )
            yield root, material

    def test_keywords_and_uncertainty_not_printed(self):
        """§5.2 只列四段，關鍵詞與不確定的地方不進回來時的輸出。"""
        out = run("deploy-cli").stdout
        self.assertNotIn("關鍵詞", out)
        self.assertNotIn("不確定的地方", out)


class TestClip(unittest.TestCase):
    def test_short_text_untouched(self):
        self.assertEqual(read.clip("短短一行", 80), "短短一行")

    def test_cuts_by_display_width_not_character_count(self):
        clipped = read.clip("中" * 50, 20)
        self.assertLessEqual(read.display_width(clipped), 20)
        self.assertTrue(clipped.endswith("…"))

    def test_boundary_is_exact(self):
        self.assertEqual(read.clip("a" * 80, 80), "a" * 80)
        self.assertEqual(read.display_width(read.clip("a" * 81, 80)), 80)


class TestRelativeDate(unittest.TestCase):
    def test_days_from_injected_now(self):
        self.assertIn("5 天前", run("deploy-cli").stdout)
        self.assertIn("2 天前", run("orders-api").stdout)
        self.assertIn("21 天前", run("storefront-web").stdout)

    def test_hours_within_the_same_day(self):
        """同一天回來就給小時，不要顯示成 0 天前。"""
        with self.same_day_project(hours_ago=3) as root:
            out = run("Today", root=root).stdout
        self.assertIn("3 小時前", out)
        self.assertNotIn("天前", out)

    def test_just_now(self):
        with self.same_day_project(hours_ago=0) as root:
            out = run("Today", root=root).stdout
        self.assertIn("剛剛", out)

    def test_hours_from_mtime_when_updated_is_missing(self):
        """沒有 updated 就退回 mtime，時間框一樣要對得起來。"""
        with self.same_day_project(hours_ago=3, use_updated=False) as root:
            out = run("Today", root=root).stdout
        self.assertIn("3 小時前", out)

    @staticmethod
    @contextmanager
    def same_day_project(hours_ago, use_updated=True):
        """開一個暫存專案，把「上次動過」押在基準時間的同一天。

        use_updated 決定走哪條路徑：寫進 frontmatter，還是只留 mtime。
        兩條都要測，因為 clone 過來的檔案只剩 frontmatter 是準的。
        """
        moment = NOW_DT - timedelta(hours=hours_ago)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Today").mkdir()
            path = root / "Today" / "handoff.md"
            path.write_text(
                handoff("Today", "剛做完", "接著做", updated=moment.isoformat() if use_updated else None),
                encoding="utf-8",
            )
            # mtime 一律押在同一個絕對時刻，兩條路徑的期望值才一樣
            os.utime(path, (moment.timestamp(), moment.timestamp()))
            yield root

    def test_runs_without_injected_now(self):
        """沒給基準時間也要能跑，不能硬編今天。"""
        result = run("deploy-cli", now=None)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(PROMPT, result.stdout)


class TestTimeSource(unittest.TestCase):
    """「多久沒動」的來源：updated 優先，mtime 是備胎（SPEC §3.1）。"""

    @contextmanager
    def project(self, *, updated, mtime):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "P").mkdir()
            path = root / "P" / "handoff.md"
            path.write_text(handoff("P", updated=updated), encoding="utf-8")
            os.utime(path, (mtime.timestamp(), mtime.timestamp()))
            yield root

    def test_updated_wins_over_mtime(self):
        with self.project(
            updated=(NOW_DT - timedelta(days=5)).isoformat(), mtime=NOW_DT
        ) as root:
            self.assertIn("5 天前", run("P", root=root).stdout)

    def test_falls_back_to_mtime(self):
        with self.project(updated=None, mtime=NOW_DT - timedelta(days=5)) as root:
            self.assertIn("5 天前", run("P", root=root).stdout)

    def test_garbage_updated_falls_back_to_mtime(self):
        with self.project(updated="上週三下午", mtime=NOW_DT - timedelta(days=5)) as root:
            result = run("P", root=root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("5 天前", result.stdout)
            self.assertNotIn("上週三", result.stdout)


class TestCli(unittest.TestCase):
    def test_no_argument(self):
        result = run()
        self.assertEqual(result.returncode, 2)
        self.assertIn("用法", result.stderr)

    def test_unknown_project(self):
        result = run("NotAProject")
        self.assertEqual(result.returncode, 1)
        self.assertIn("NotAProject", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_path_traversal_rejected(self):
        result = run("../fixture/deploy-cli")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")

    def test_project_without_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Empty").mkdir()
            result = run("Empty", root=root)
            self.assertEqual(result.returncode, 1)
            self.assertIn("handoff.md", result.stderr)

    def test_help(self):
        result = run(extra_args=["--help"])
        self.assertEqual(result.returncode, 0)
        self.assertIn("REENTRY_ROOT", result.stdout)
        self.assertIn("REENTRY_NOW", result.stdout)

    def test_root_flag_overrides_env(self):
        """三支腳本都吃 --root。這支以前只有環境變數。"""
        with tempfile.TemporaryDirectory() as tmp:
            result = run("deploy-cli", root=tmp, extra_args=["--root", str(FIXTURE)])
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("5 天前", result.stdout)

    def test_now_flag_overrides_env(self):
        """三支腳本都吃 --now。這支以前只有環境變數。"""
        result = run("deploy-cli", now="2026-09-30T12:00:00+08:00", extra_args=["--now", NOW])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("5 天前", result.stdout)

    def test_bad_now_flag_exits_two(self):
        result = run("deploy-cli", extra_args=["--now", "上週三"])
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISO 8601", result.stderr)

    def test_bad_now_env_exits_two(self):
        result = run("deploy-cli", now="上週三")
        self.assertEqual(result.returncode, 2)
        self.assertIn("ISO 8601", result.stderr)

    def test_runs_with_an_empty_path(self):
        """skill 裡靠 `python3 <路徑>` 呼叫：PATH 上不會有這支指令，執行權限也不是條件。"""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "deploy-cli"],
            capture_output=True,
            text=True,
            env={"PATH": "", "REENTRY_ROOT": str(FIXTURE), "REENTRY_NOW": NOW},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(PROMPT, result.stdout)


class TestFixtureUntouched(unittest.TestCase):
    def test_no_files_written_into_fixture(self):
        before = sorted(p.name for p in (FIXTURE / "storefront-web").iterdir())
        run("storefront-web")
        after = sorted(p.name for p in (FIXTURE / "storefront-web").iterdir())
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class TestOpenQuestions(unittest.TestCase):
    """待確認跟欠債分開，而且沒有未打勾的就整段不印。"""

    def test_shows_only_unchecked(self):
        out = run("orders-api").stdout
        self.assertIn("待確認 1", out)
        self.assertIn("tuning 跟 limits", out)
        self.assertNotIn("schema_migration 的版本欄位", out)

    def test_answer_line_never_leaks(self):
        """待確認可以寫答案，但回來時不印——印出來就不用去查了。"""
        self.assertNotIn("跟檔名前綴一致", run("orders-api").stdout)

    def test_absent_file_means_no_block(self):
        """沒有 open-questions.md 就整段不出現，不留空殼。"""
        self.assertNotIn("待確認", run("storefront-web").stdout)

    def test_all_checked_also_means_no_block(self):
        """全部打勾等於沒有待確認，一樣不印。"""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_project(root, "Q", questions="# 待確認 — Q\n\n- [x] 已經查到了\n")
            self.assertNotIn("待確認", run("Q", root=root).stdout)

    def test_debt_comes_before_questions(self):
        out = run("orders-api").stdout
        self.assertLess(out.index("欠債"), out.index("待確認"))

    def test_questions_come_before_next_step(self):
        """待確認插在欠債與下一步之間，不能把下一步擠到前面。"""
        out = run("orders-api").stdout
        self.assertLess(out.index("待確認"), out.rindex("下一步"))
