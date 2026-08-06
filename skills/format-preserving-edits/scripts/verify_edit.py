#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_edit.py — 改完設定檔之後，證明「只改了該改的，沒有夾帶重排」。

驗兩件事，缺一不可：
  1. 語意對不對：真的加了 / 刪了 / 改了那些東西，沒有多也沒有少。
  2. diff 形狀對不對：純新增 (N+ / 0-)、純刪除 (0+ / N-)、改值 (n+ / n-)。
     如果一堆被刪的行和被加的行「去掉空白後長得一模一樣」，那就是重排噪音——
     這種 diff 沒有人 review 得動，必須清掉。

用法：
    python3 verify_edit.py path/to/file.json          # 跟 git HEAD 比
    python3 verify_edit.py --base :0 path/to/f.json   # 跟 index 比
    python3 verify_edit.py old.json new.json          # 比兩個檔

只要偵測到重排噪音就 exit 1。
"""
from __future__ import print_function

import argparse
import collections
import difflib
import io
import json
import os
import subprocess
import sys
import unicodedata

CAP = 40


def _dw(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)


def row(label, value, width=14):
    return "%s%s: %s" % (label, " " * max(1, width - _dw(label)), value)


def norm(line):
    """去掉所有空白差異，留下實質內容。"""
    return "".join(line.split())


def read_file(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def read_git(rev, path):
    root = subprocess.check_output(
        ["git", "-C", os.path.dirname(os.path.abspath(path)) or ".",
         "rev-parse", "--show-toplevel"]).decode().strip()
    rel = os.path.relpath(os.path.abspath(path), root)
    spec = "%s:%s" % (rev, rel) if rev != ":0" else ":0:%s" % rel
    return subprocess.check_output(["git", "-C", root, "show", spec]).decode("utf-8")


# --------------------------------------------------------------------------

def check_meta(old, new):
    issues = []
    notes = []

    def eol(t):
        crlf = t.count("\r\n")
        lf = t.count("\n") - crlf
        return "CRLF" if crlf and not lf else ("LF" if lf and not crlf else "mixed")

    if eol(old) != eol(new):
        issues.append("換行字元從 %s 變成 %s" % (eol(old), eol(new)))
    if old.startswith("﻿") != new.startswith("﻿"):
        issues.append("BOM 被加上或拿掉了")
    if old.endswith("\n") != new.endswith("\n"):
        issues.append("檔尾換行從 %s 變成 %s"
                      % (bool(old.endswith("\n")), bool(new.endswith("\n"))))

    def indent_sig(t):
        c = collections.Counter()
        for ln in t.split("\n"):
            if ln.strip():
                w = len(ln) - len(ln.lstrip())
                if w:
                    c["\t" if ln[:1] == "\t" else "sp%d" % w] += 1
        return c

    a, b = indent_sig(old), indent_sig(new)
    gone = [k for k in a if k not in b]
    added = [k for k in b if k not in a]
    if gone or added:
        notes.append("縮排寬度種類變化：消失 %s / 新增 %s"
                     % (gone or "無", added or "無"))
    return issues, notes


def check_shape(old, new):
    a = old.split("\n")
    b = new.split("\n")
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    removed, addedl = [], []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete"):
            removed.extend(a[i1:i2])
        if tag in ("replace", "insert"):
            addedl.extend(b[j1:j2])

    rem_norm = collections.Counter(norm(x) for x in removed if x.strip())
    add_norm = collections.Counter(norm(x) for x in addedl if x.strip())
    churn = rem_norm & add_norm  # 兩邊都有、只差空白 → 重排噪音
    churn_n = sum(churn.values())

    if not removed and addedl:
        shape = "純新增"
    elif removed and not addedl:
        shape = "純刪除"
    elif not removed and not addedl:
        shape = "沒有差異"
    else:
        shape = "有增有刪"
    return {
        "added": len([x for x in addedl if x.strip()]),
        "removed": len([x for x in removed if x.strip()]),
        "shape": shape,
        "churn": churn_n,
        "churn_examples": [k for k, _ in churn.most_common(5)],
    }


# --------------------------------------------------------------------------

def load_struct(text, path):
    ext = os.path.splitext(path)[1].lower()
    known = (".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".env", ".properties")
    if ext in (".json", ".jsonc", ".json5") or (ext not in known
                                                and text.lstrip()[:1] in "{["):
        try:
            return json.loads(text), "json"
        except ValueError:
            return None, None
    if ext in (".yaml", ".yml"):
        try:
            import yaml
            return yaml.safe_load(text), "yaml"
        except Exception:
            return None, None
    if ext == ".toml":
        try:
            import tomllib
            return tomllib.loads(text), "toml"
        except Exception:
            return None, None
    return None, None


def diff_struct(a, b, path="$", out=None):
    out = [] if out is None else out
    if len(out) > CAP:
        return out
    if type(a) is not type(b) and not (isinstance(a, (int, float))
                                       and isinstance(b, (int, float))):
        out.append(("改型別", path, "%s -> %s" % (type(a).__name__, type(b).__name__)))
        return out
    if isinstance(a, dict):
        for k in a:
            if k not in b:
                out.append(("刪除", "%s.%s" % (path, k), ""))
        for k in b:
            if k not in a:
                out.append(("新增", "%s.%s" % (path, k), ""))
        for k in a:
            if k in b:
                diff_struct(a[k], b[k], "%s.%s" % (path, k), out)
    elif isinstance(a, list):
        if len(a) != len(b):
            out.append(("長度", path, "%d -> %d" % (len(a), len(b))))
        for i in range(min(len(a), len(b))):
            diff_struct(a[i], b[i], "%s[%d]" % (path, i), out)
    elif a != b:
        out.append(("改值", path, "%r -> %r" % (a, b)))
    return out


# --------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("files", nargs="+")
    p.add_argument("--base", default="HEAD", help="git 比較基準（預設 HEAD，:0 為 index）")
    args = p.parse_args(argv)

    if len(args.files) == 2 and all(os.path.exists(f) for f in args.files):
        old, new = read_file(args.files[0]), read_file(args.files[1])
        label = "%s -> %s" % tuple(args.files)
        path = args.files[1]
    elif len(args.files) == 1:
        path = args.files[0]
        old, new = read_git(args.base, path), read_file(path)
        label = "%s (%s -> worktree)" % (path, args.base)
    else:
        p.error("給 1 個檔（跟 git 比）或 2 個檔（互比）")
        return 2

    print("=" * 72)
    print(label)
    print("=" * 72)

    shape = check_shape(old, new)
    print("  " + row("diff 形狀", "%s  (+%d / -%d)"
                     % (shape["shape"], shape["added"], shape["removed"])))

    meta_issues, meta_notes = check_meta(old, new)
    for m in meta_issues:
        print("  " + row("✗ 檔案層級", m))
    for m in meta_notes:
        print("  " + row("· 註記", m))

    bad = bool(meta_issues)
    if shape["churn"]:
        bad = True
        print("  " + row("✗ 重排噪音",
                         "%d 行「被刪又被加、只差空白」——這些是重排，不是異動"
                         % shape["churn"]))
        for ex in shape["churn_examples"]:
            print("      例：%s" % (ex[:70] + ("…" if len(ex) > 70 else "")))
        print("      → 把這些行還原（git checkout -- <file> 後重做），只動真正要動的地方")
    else:
        print("  " + row("✓ 重排噪音", "無"))

    a, kind = load_struct(old, path)
    b, kind2 = load_struct(new, path)
    if kind and kind == kind2:
        d = diff_struct(a, b)
        print("  " + row("語意差異 (%s)" % kind, "%d 處" % len(d)))
        for tag, ppath, detail in d[:CAP]:
            print("      %-6s %s %s" % (tag, ppath, detail))
        if len(d) > CAP:
            print("      …（還有更多，只列前 %d 筆）" % CAP)
    else:
        print("  " + row("語意差異", "無法解析成結構（只做了文字檢查）"))

    print()
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
