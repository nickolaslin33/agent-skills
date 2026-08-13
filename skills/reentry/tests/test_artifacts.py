# -*- coding: utf-8 -*-
"""scripts/reentry_artifacts.py 的測試（SPEC §3.3）。

每個測試自己在臨時目錄開一個小 git repo，不碰 tests/fixture/，也不依賴任何外部 repo。
時間用 $REENTRY_NOW 釘死，輸出才比得動。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_ROOT / "scripts"
SCRIPT = SCRIPTS_DIR / "reentry_artifacts.py"
FIXTURE = SKILL_ROOT / "tests" / "fixture"

FIXED_NOW = "2026-08-12T23:16:41+08:00"
MINUS = "−"  # U+2212

# 共用模組跟腳本同一層，直接 import 拿章節名與佔位句，測試不自己抄一份字串。
sys.dont_write_bytecode = True
sys.path.insert(0, str(SCRIPTS_DIR))

import reentry_common as common  # noqa: E402

CHANGED = common.SECTION_CHANGED
VERIFY = common.SECTION_VERIFY
DETAIL = common.SECTION_DETAIL


# ---------------------------------------------------------------- 工具


def base_env() -> dict[str, str]:
    """把 git 跟使用者的全域設定隔開，免得 gpgsign、hooks、template 干擾測試。"""
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "reentry test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "reentry test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "REENTRY_NOW": FIXED_NOW,
        }
    )
    return env


def git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        env=base_env(),
        check=True,
    )
    return proc.stdout.strip()


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    return path


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def commit_all(repo: Path, message: str = "wip") -> str:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def run_script(*args: str, reentry_root: Path | None = None, **env_extra: str):
    env = base_env()
    if reentry_root is not None:
        env["REENTRY_ROOT"] = str(reentry_root)
    env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        capture_output=True,
        text=True,
        env=env,
    )


def section(document: str, name: str) -> list[str]:
    """撈出某個 ## 段落的內容行。"""
    lines = document.splitlines()
    start = lines.index(f"## {name}") + 1
    body = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        body.append(line)
    while body and body[-1] == "":
        body.pop()
    return body


def detail_rows(document: str) -> list[str]:
    """`## 明細` 裡的檔案列。

    第一行是總數、最後一行是比較基準，兩行都另外驗——夾在中間的才是一個檔一行。
    """
    return section(document, DETAIL)[1:-1]


@pytest.fixture()
def workspace(tmp_path: Path):
    """回傳 (reentry_root, project_dir, workdir)，專案叫 Demo。"""
    root = tmp_path / "reentry"
    (root / "Demo").mkdir(parents=True)
    workdir = make_repo(tmp_path / "src" / "Demo")
    return root, root / "Demo", workdir


# ---------------------------------------------------------------- 腳本本身


def test_runs_by_path_from_any_install_dir(tmp_path: Path):
    """skill 裡一律 `python3 "$SKILL_DIR"/scripts/reentry_artifacts.py` 呼叫。

    複製一份到別的路徑、把執行權限拿掉，照樣跑得動——執行權限、shebang、PATH 上有沒有
    這支指令，都不能是條件（要在 Claude Code / Codex / Gemini / Grok / Kiro 底下都成立）。
    """
    installed = tmp_path / "some skill dir" / "scripts"
    shutil.copytree(SCRIPTS_DIR, installed, ignore=shutil.ignore_patterns("__pycache__"))
    for script in installed.glob("*.py"):
        script.chmod(0o644)

    root = tmp_path / "reentry"
    (root / "Demo").mkdir(parents=True)
    workdir = make_repo(tmp_path / "src" / "Demo")
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    result = subprocess.run(
        [sys.executable, str(installed / "reentry_artifacts.py"), "Demo", str(workdir)],
        capture_output=True,
        text=True,
        env={**base_env(), "REENTRY_ROOT": str(root)},
    )
    assert result.returncode == 0, result.stderr
    assert (root / "Demo" / "artifacts.md").exists()


def test_stdlib_only():
    """標準函式庫 ＋ 同一層的共用模組，沒有第三方套件（SPEC §8：要能直接跑）。"""
    source = SCRIPT.read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:import|from)\s+([\w.]+)", source, re.MULTILINE))
    allowed = set(sys.stdlib_module_names) | {"__future__", "reentry_common"}
    assert imported <= allowed, f"跑出標準函式庫以外的 import：{imported - allowed}"
    assert "reentry_common" in imported, "共用邏輯要從 scripts/reentry_common.py 來，不要自己再寫一份"


def test_shares_the_common_module_with_the_other_scripts():
    """三支腳本用同一份實作，不要各寫各的（不然數字遲早對不起來）。"""
    assert (SCRIPT.parent / "reentry_common.py").is_file()
    source = SCRIPT.read_text(encoding="utf-8")
    for func in ("def display_width(", "def pad(", "def resolve_now("):
        assert func not in source, f"{func} 應該來自共用模組，腳本裡不該再有一份"


# ---------------------------------------------------------------- 格式


def test_document_layout_matches_spec(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "x = 1\n")
    commit_all(workdir)
    write(workdir / "a.py", "x = 1\ny = 2\n")

    result = run_script("Demo", str(workdir), reentry_root=root)
    assert result.returncode == 0, result.stderr

    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    lines = document.splitlines()
    assert lines[0] == "---"
    assert lines[1] == "project: Demo"
    assert lines[2] == f"generated: {FIXED_NOW}"
    assert lines[3] == "---"
    assert document.endswith("\n")

    # 三節，順序固定：功能層的一句話在最上面，原始事實壓在最下面
    headings = [line for line in lines if line.startswith("## ")]
    assert headings == [f"## {CHANGED}", f"## {VERIFY}", f"## {DETAIL}"]
    assert "## 統計" not in lines


def test_changed_section_is_a_placeholder_for_the_agent(workspace):
    """腳本不知道那些檔是幹嘛的，`## 改了什麼` 只能留一句自曝的佔位句等 agent 填。

    佔位句留著不會靜靜過去：回來時這一節會被印出來（見 test_read 的
    test_unfilled_placeholder_is_visible），沒填就直接出現在使用者眼前。
    """
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "x = 1\n")
    commit_all(workdir)

    run_script("Demo", str(workdir), reentry_root=root)
    changed = section((project_dir / "artifacts.md").read_text(encoding="utf-8"), CHANGED)
    assert changed == [common.CHANGED_PLACEHOLDER]
    assert "尚未填寫" in changed[0]


def test_verify_section_falls_back_to_a_placeholder(workspace):
    """沒給 --test-result 就留佔位句給 agent 填，不留空節。"""
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "x = 1\n")
    commit_all(workdir)

    run_script("Demo", str(workdir), reentry_root=root)
    assert section((project_dir / "artifacts.md").read_text(encoding="utf-8"), VERIFY) == [
        common.VERIFY_PLACEHOLDER
    ]


def test_detail_line_shape_matches_fixture(workspace):
    """跟已存在的 fixture 比對形狀：全形括號、U+2212 減號、同一組 frontmatter 欄位。"""
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "x = 1\n")
    commit_all(workdir)
    write(workdir / "a.py", "x = 1\ny = 2\n")
    run_script("Demo", str(workdir), reentry_root=root)

    mine = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    theirs = (FIXTURE / "deploy-cli" / "artifacts.md").read_text(encoding="utf-8")

    pattern = r"^改了 \d+ 個檔（\+\d+ −\d+）$"
    assert re.search(pattern, "\n".join(section(mine, DETAIL)), re.MULTILINE)
    assert re.search(pattern, "\n".join(section(theirs, DETAIL)), re.MULTILINE)

    keys = lambda doc: re.findall(r"^(\w+):", doc.split("---")[1], re.MULTILINE)
    assert keys(mine) == keys(theirs) == ["project", "generated"]


def test_fixture_uses_the_three_section_shape():
    """fixture 是格式的樣本，形狀要跟腳本產的一致。"""
    for name in ("deploy-cli", "orders-api"):
        document = (FIXTURE / name / "artifacts.md").read_text(encoding="utf-8")
        headings = [line for line in document.splitlines() if line.startswith("## ")]
        assert headings == [f"## {CHANGED}", f"## {VERIFY}", f"## {DETAIL}"], name
        # 樣本裡的兩節是填好的，不該還留著佔位句
        assert "尚未填寫" not in document, name


def test_detail_columns_are_aligned(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "short.py", "a = 1\n")
    write(workdir / "a/very/long/path/module.py", "b = 1\n")
    commit_all(workdir)
    write(workdir / "short.py", "a = 2\n")
    write(workdir / "a/very/long/path/module.py", "b = 2\n")

    run_script("Demo", str(workdir), reentry_root=root)
    rows = detail_rows((project_dir / "artifacts.md").read_text(encoding="utf-8"))
    assert len(rows) == 2, f"檔案列抓錯了：{rows}"
    columns = {line.index("+") for line in rows}
    assert len(columns) == 1, f"右欄沒對齊：{rows}"


# ---------------------------------------------------------------- diff 內容


def test_counts_modified_and_untracked(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n2\n3\n")
    commit_all(workdir)
    write(workdir / "a.py", "1\n2\n3\n4\n5\n")  # +2
    write(workdir / "b.py", "x\ny\n")  # 未追蹤，+2

    run_script("Demo", str(workdir), reentry_root=root)
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")

    assert f"改了 2 個檔（+4 {MINUS}0）" in document
    detail = detail_rows(document)
    assert any(line.startswith("a.py") and line.endswith(f"+2 {MINUS}0") for line in detail)
    assert any(line.startswith("b.py") and line.endswith("新增 +2") for line in detail)


def test_staged_new_file_marked_added(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    write(workdir / "new.py", "1\n2\n3\n")
    git(workdir, "add", "new.py")

    run_script("Demo", str(workdir), reentry_root=root)
    detail = detail_rows((project_dir / "artifacts.md").read_text(encoding="utf-8"))
    assert detail == ["new.py  新增 +3"]


def test_deleted_file(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "gone.py", "1\n2\n")
    write(workdir / "stay.py", "1\n")
    commit_all(workdir)
    (workdir / "gone.py").unlink()

    run_script("Demo", str(workdir), reentry_root=root)
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    assert f"改了 1 個檔（+0 {MINUS}2）" in document
    assert detail_rows(document) == [f"gone.py  刪除 {MINUS}2"]


def test_renamed_file(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "old.py", "".join(f"line {i}\n" for i in range(30)))
    commit_all(workdir)
    git(workdir, "mv", "old.py", "new.py")

    run_script("Demo", str(workdir), reentry_root=root)
    detail = detail_rows((project_dir / "artifacts.md").read_text(encoding="utf-8"))
    assert len(detail) == 1
    assert detail[0].startswith("new.py")
    assert "更名" in detail[0]


def test_binary_file_has_no_line_counts(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    (workdir / "blob.bin").write_bytes(b"\x00\x01\x02\x00")

    run_script("Demo", str(workdir), reentry_root=root)
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    assert "blob.bin  二進位" in document
    assert f"改了 1 個檔（+0 {MINUS}0）" in document


def test_single_commit_repo_falls_back_to_that_commit(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir, "只有這一個 commit")

    # 唯一的 commit 就是基準，退化成看那個 commit 本身
    run_script("Demo", str(workdir), reentry_root=root)
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    assert "最後一個 commit" in document
    assert detail_rows(document) == ["a.py  新增 +1"]


# ---------------------------------------------------------------- 比較基準


def test_default_baseline_is_uncommitted_worktree(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    write(workdir / "a.py", "1\n2\n")

    run_script("Demo", str(workdir), reentry_root=root)
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    assert "比較基準：工作區未提交的變更" in section(document, DETAIL)[-1]


def test_clean_worktree_falls_back_to_last_commit(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir, "第一版")
    write(workdir / "a.py", "1\n2\n3\n")
    commit_all(workdir, "第二版")

    run_script("Demo", str(workdir), reentry_root=root)
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    assert f"改了 1 個檔（+2 {MINUS}0）" in document
    assert "最後一個 commit" in section(document, DETAIL)[-1]


def test_since_option_sets_baseline(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    first = commit_all(workdir, "第一版")
    write(workdir / "a.py", "1\n2\n")
    commit_all(workdir, "第二版")
    write(workdir / "a.py", "1\n2\n3\n")
    commit_all(workdir, "第三版")

    run_script("Demo", str(workdir), "--since", first, reentry_root=root)
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    assert f"改了 1 個檔（+2 {MINUS}0）" in document
    assert f"比較基準：{first}" in document


def test_since_option_rejects_unknown_ref(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    result = run_script("Demo", str(workdir), "--since", "nope-nope", reentry_root=root)
    assert result.returncode == 1
    assert "nope-nope" in result.stderr
    assert not (project_dir / "artifacts.md").exists()


def test_repo_without_commits(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n2\n")

    result = run_script("Demo", str(workdir), reentry_root=root)
    assert result.returncode == 0, result.stderr
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    assert "還沒有 commit" in document
    assert f"改了 1 個檔（+2 {MINUS}0）" in document


# ---------------------------------------------------------------- 邊界


def test_non_git_project_still_writes_file(tmp_path: Path):
    root = tmp_path / "reentry"
    (root / "storefront-web").mkdir(parents=True)
    workdir = tmp_path / "src" / "storefront-web"
    workdir.mkdir(parents=True)
    write(workdir / "index.html", "<p>hi</p>\n")

    result = run_script("storefront-web", str(workdir), reentry_root=root)
    assert result.returncode == 0, result.stderr

    document = (root / "storefront-web" / "artifacts.md").read_text(encoding="utf-8")
    assert "project: storefront-web" in document
    assert section(document, DETAIL) == [f"不是 git repo（{workdir}），沒有 diff 可統計"]


def test_non_git_project_overwrites_stale_stats(tmp_path: Path):
    root = tmp_path / "reentry"
    (root / "storefront-web").mkdir(parents=True)
    stale = root / "storefront-web" / "artifacts.md"
    write(stale, f"---\nproject: storefront-web\n---\n\n## {DETAIL}\n改了 9 個檔（+900 −900）\n")
    workdir = tmp_path / "src" / "storefront-web"
    workdir.mkdir(parents=True)

    run_script("storefront-web", str(workdir), reentry_root=root)
    assert "900" not in stale.read_text(encoding="utf-8")


def test_unregistered_project_is_rejected(tmp_path: Path):
    root = tmp_path / "reentry"
    root.mkdir()
    workdir = make_repo(tmp_path / "src" / "Ghost")
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    result = run_script("Ghost", str(workdir), reentry_root=root)
    assert result.returncode == 1
    assert "登記" in result.stderr
    assert not (root / "Ghost").exists()


def test_missing_workdir(workspace):
    root, project_dir, _ = workspace
    result = run_script("Demo", str(root / "does-not-exist"), reentry_root=root)
    assert result.returncode == 1
    assert "工作目錄不存在" in result.stderr
    assert not (project_dir / "artifacts.md").exists()


def test_workdir_defaults_to_projects_root_env(tmp_path: Path):
    root = tmp_path / "reentry"
    (root / "Demo").mkdir(parents=True)
    projects = tmp_path / "projects"
    workdir = make_repo(projects / "Demo")
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    write(workdir / "a.py", "1\n2\n")

    result = run_script("Demo", reentry_root=root, REENTRY_PROJECTS_ROOT=str(projects))
    assert result.returncode == 0, result.stderr
    assert f"改了 1 個檔（+1 {MINUS}0）" in (root / "Demo" / "artifacts.md").read_text(encoding="utf-8")


def test_overwrites_every_run(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    write(workdir / "a.py", "1\n2\n")
    run_script("Demo", str(workdir), reentry_root=root)

    write(workdir / "a.py", "1\n")  # 改回去
    git(workdir, "add", "-A")
    run_script("Demo", str(workdir), reentry_root=root)

    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    headings = [line for line in document.splitlines() if line.startswith("## ")]
    assert headings == [f"## {CHANGED}", f"## {VERIFY}", f"## {DETAIL}"], "覆蓋沒覆蓋乾淨"
    assert "最後一個 commit" in document  # 工作區已經跟 HEAD 一樣了


def test_stdout_writes_nothing(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    write(workdir / "a.py", "1\n2\n")

    result = run_script("Demo", str(workdir), "--stdout", reentry_root=root)
    assert result.returncode == 0, result.stderr
    assert f"## {DETAIL}" in result.stdout
    assert not (project_dir / "artifacts.md").exists()


# ---------------------------------------------------------------- 測試結果的防呆


def test_test_results_copied_verbatim(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    write(workdir / "a.py", "1\n2\n")

    run_script(
        "Demo", str(workdir),
        "--test-result", "pytest 14 passed / 2 failed",
        "--test-result", "mypy 0 errors in 12 files",
        reentry_root=root,
    )
    verify = section((project_dir / "artifacts.md").read_text(encoding="utf-8"), VERIFY)
    assert verify == ["pytest 14 passed / 2 failed", "mypy 0 errors in 12 files"]


@pytest.mark.parametrize(
    "bad",
    ["測試已完成", "已驗證", "全部通過", "測試全綠", "都過了", "pytest 沒問題"],
)
def test_valueless_words_are_rejected(workspace, bad):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    result = run_script("Demo", str(workdir), "--test-result", bad, reentry_root=root)
    assert result.returncode == 1
    assert "SPEC §3.3" in result.stderr
    assert not (project_dir / "artifacts.md").exists(), "被擋下來就不該寫檔"


def test_test_result_without_number_is_rejected(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    result = run_script("Demo", str(workdir), "--test-result", "pytest 跑過了", reentry_root=root)
    assert result.returncode == 1
    assert not (project_dir / "artifacts.md").exists()


def test_rejection_leaves_existing_file_untouched(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    write(project_dir / "artifacts.md", "舊的內容\n")

    result = run_script("Demo", str(workdir), "--test-result", "已完成", reentry_root=root)
    assert result.returncode == 1
    assert (project_dir / "artifacts.md").read_text(encoding="utf-8") == "舊的內容\n"


# ---------------------------------------------------------------- 時間


def test_now_flag_overrides_env(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    run_script("Demo", str(workdir), "--now", "2026-01-02T03:04:05+08:00", reentry_root=root)
    assert "generated: 2026-01-02T03:04:05+08:00" in (project_dir / "artifacts.md").read_text(encoding="utf-8")


def test_falls_back_to_current_time(workspace):
    root, project_dir, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    env = base_env()
    env.pop("REENTRY_NOW")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "Demo", str(workdir)],
        capture_output=True, text=True,
        env={**env, "REENTRY_ROOT": str(root)},
    )
    assert proc.returncode == 0, proc.stderr
    document = (project_dir / "artifacts.md").read_text(encoding="utf-8")
    stamp = re.search(r"^generated: (.+)$", document, re.MULTILINE).group(1)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", stamp)


def test_unparseable_time_errors(workspace):
    """時間看不懂就 2，跟另外兩支同一個退出碼（其他錯誤才是 1）。"""
    root, _, workdir = workspace
    result = run_script("Demo", str(workdir), "--now", "昨天下午", reentry_root=root)
    assert result.returncode == 2
    assert "ISO 8601" in result.stderr


def test_unparseable_env_time_errors(workspace):
    root, _, workdir = workspace
    result = run_script("Demo", str(workdir), reentry_root=root, REENTRY_NOW="昨天下午")
    assert result.returncode == 2
    assert "ISO 8601" in result.stderr


def test_root_flag_overrides_env(tmp_path: Path):
    """--root 三支都有，都蓋得掉 $REENTRY_ROOT。"""
    real = tmp_path / "real"
    decoy = tmp_path / "decoy"
    for base in (real, decoy):
        (base / "Demo").mkdir(parents=True)
    workdir = make_repo(tmp_path / "src" / "Demo")
    write(workdir / "a.py", "1\n")
    commit_all(workdir)

    result = run_script("Demo", str(workdir), "--root", str(real), reentry_root=decoy)
    assert result.returncode == 0, result.stderr
    assert (real / "Demo" / "artifacts.md").exists()
    assert not (decoy / "Demo" / "artifacts.md").exists()


# ---------------------------------------------------------------- fixture 不能被動到


def test_fixture_is_untouched(workspace):
    before = {p: p.read_bytes() for p in FIXTURE.rglob("*") if p.is_file()}
    root, _, workdir = workspace
    write(workdir / "a.py", "1\n")
    commit_all(workdir)
    run_script("Demo", str(workdir), reentry_root=root)
    after = {p: p.read_bytes() for p in FIXTURE.rglob("*") if p.is_file()}
    assert before == after
