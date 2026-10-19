#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Focused regression tests for allowed scope human annotations and disambiguation."""

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd, env=None, cwd=None, check=True):
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, env=env, cwd=cwd)
    if check and p.returncode != 0:
        raise AssertionError(f"Command failed (exit {p.returncode}): {cmd}\nstdout: {p.stdout}\nstderr: {p.stderr}")
    return p


def main():
    print("running unio scope annotations regression suite...")
    with tempfile.TemporaryDirectory(prefix="unio scope test ") as td:
        sb = Path(td)
        bin_dir = sb / "bin"
        conf_dir = sb / "conf"
        comp_dir = sb / "comp"
        project_dir = sb / "project"
        repo_dir = project_dir / "repo"

        bin_dir.mkdir(parents=True)
        conf_dir.mkdir(parents=True)
        comp_dir.mkdir(parents=True)
        repo_dir.mkdir(parents=True)

        env = dict(os.environ)
        env["UNIO_BIN_DIR"] = str(bin_dir)
        env["UNIO_CONF_DIR"] = str(conf_dir)
        env["UNIO_COMPLETION_DIR"] = str(comp_dir)
        env["GIT_AUTHOR_NAME"] = "scope-test"
        env["GIT_AUTHOR_EMAIL"] = "scope@test.invalid"
        env["GIT_COMMITTER_NAME"] = "scope-test"
        env["GIT_COMMITTER_EMAIL"] = "scope@test.invalid"
        env["UNIO_AUTO_VERIFY"] = "0"
        env["UNIO_AUTO_OFF"] = "0"
        env["UNIO_AUTO_SYNC"] = "0"

        # Install unio
        run_cmd(["bash", str(REPO_ROOT / "unio-install.sh")], env=env, cwd=str(sb))
        unio_bin = str(bin_dir / "unio")
        assert os.path.isfile(unio_bin), f"unio binary missing: {unio_bin}"

        # Initialize git repo & unio project
        run_cmd(["git", "init", "-q", "-b", "dev", str(repo_dir)], env=env)
        run_cmd(["git", "commit", "-qm", "initial", "--allow-empty"], env=env, cwd=str(repo_dir))
        run_cmd([unio_bin, "init", "mock", "noop"], env=env, cwd=str(repo_dir))

        tasks_dir = project_dir / "coord/tasks"
        reports_dir = project_dir / "coord/reports"
        wt_mock = project_dir / "wt/mock"
        assert tasks_dir.is_dir()
        assert wt_mock.is_dir()

        agents_conf = conf_dir / "agents.conf"

        def setup_task(task_id, scope_lines, validate_lines):
            scope_block = "\n".join(f"- {s}" for s in scope_lines)
            validate_block = "\n".join(f"$ {v}" for v in validate_lines)
            content = f"# Task {task_id}\n\n## Goal\ntest\n\n## Allowed scope\n{scope_block}\n\n## Validate\n{validate_block}\n"
            (tasks_dir / f"{task_id}.md").write_text(content, encoding="utf-8")

        def set_mock_worker(script):
            agents_conf.write_text(f"mock=bash -c {repr(script)}\nnoop=bash -c 'exit 0'\n", encoding="utf-8")

        def reset_mock():
            run_cmd(["git", "-C", str(wt_mock), "reset", "--hard", "dev"], env=env)
            run_cmd(["git", "-C", str(wt_mock), "clean", "-fdx"], env=env)

        # -------------------------------------------------------------
        # 1. Annotated exact path passes with warning
        # -------------------------------------------------------------
        reset_mock()
        setup_task("T_annot_exact", ["hello.txt (only X adjustments)"], ["test -s hello.txt"])
        set_mock_worker("echo hello > hello.txt; git add hello.txt; git commit -qm 'touch hello'")
        run_cmd([unio_bin, "run", "mock", "T_annot_exact"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_annot_exact"], env=env, cwd=str(repo_dir))

        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "scope    : OK (1 pattern(s))" in p.stdout
        assert "warning  : stripped annotation '(only X adjustments)' from scope pattern 'hello.txt'" in p.stdout

        # Verify warning also appended to report
        report_text = (reports_dir / "T_annot_exact.md").read_text(encoding="utf-8")
        assert "warning: stripped annotation '(only X adjustments)' from scope pattern 'hello.txt'" in report_text
        print("  ✓ annotated exact path passes with visible bounded warning")

        # -------------------------------------------------------------
        # 2. Annotated glob passes with warning
        # -------------------------------------------------------------
        reset_mock()
        setup_task("T_annot_glob", ["src/* (only CAD Stage 1 adjustments)"], ["test -s src/engine.py"])
        set_mock_worker("mkdir -p src; echo 'engine' > src/engine.py; git add src; git commit -qm 'touch src/engine.py'")
        run_cmd([unio_bin, "run", "mock", "T_annot_glob"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_annot_glob"], env=env, cwd=str(repo_dir))

        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "scope    : OK (1 pattern(s))" in p.stdout
        assert "warning  : stripped annotation '(only CAD Stage 1 adjustments)' from scope pattern 'src/*'" in p.stdout
        print("  ✓ annotated glob passes with visible bounded warning")

        # -------------------------------------------------------------
        # 3. Out-of-scope still fails
        # -------------------------------------------------------------
        reset_mock()
        setup_task("T_out_of_scope", ["allowed.txt (only allowed changes)"], ["true"])
        set_mock_worker("echo bad > forbidden.txt; git add forbidden.txt; git commit -qm 'touch forbidden'")
        run_cmd([unio_bin, "run", "mock", "T_out_of_scope"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_out_of_scope"], env=env, cwd=str(repo_dir), check=False)

        assert p.returncode == 1
        assert "verdict  : FAIL" in p.stdout
        assert "scope_violation" in p.stdout
        assert "VIOLATION — out-of-scope changes:" in p.stdout
        assert "forbidden.txt" in p.stdout
        print("  ✓ out-of-scope modification still fails with scope_violation")

        # -------------------------------------------------------------
        # 4. Traversal patterns rejected / cannot waive out-of-scope files
        # -------------------------------------------------------------
        reset_mock()
        setup_task("T_traversal", ["../escape.txt (attempt bypass)"], ["true"])
        set_mock_worker("echo leak > leak.txt; git add leak.txt; git commit -qm 'leak'")
        run_cmd([unio_bin, "run", "mock", "T_traversal"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_traversal"], env=env, cwd=str(repo_dir), check=False)

        assert p.returncode in (1, 2)
        assert "verdict  : PASS" not in p.stdout
        print("  ✓ traversal constructs cannot waive scope")

        # -------------------------------------------------------------
        # 5. Old paths with spaces, literal parentheses, quoted and backticked forms
        # -------------------------------------------------------------
        # 5a. Path with spaces (unannotated)
        reset_mock()
        setup_task("T_spaces", ["path with spaces/my file.txt"], ["test -s 'path with spaces/my file.txt'"])
        set_mock_worker("mkdir -p 'path with spaces'; echo content > 'path with spaces/my file.txt'; git add 'path with spaces'; git commit -qm 'spaces'")
        run_cmd([unio_bin, "run", "mock", "T_spaces"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_spaces"], env=env, cwd=str(repo_dir))
        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "warning" not in p.stdout.lower()

        # 5b. Path with literal parentheses (unannotated)
        reset_mock()
        setup_task("T_parens", ["docs/file (copy).txt"], ["test -s 'docs/file (copy).txt'"])
        set_mock_worker("mkdir -p docs; echo copy > 'docs/file (copy).txt'; git add docs; git commit -qm 'parens'")
        run_cmd([unio_bin, "run", "mock", "T_parens"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_parens"], env=env, cwd=str(repo_dir))
        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "warning" not in p.stdout.lower()

        # A trailing unquoted parenthesis is a literal path, never authority
        # to change the different path obtained by stripping it.
        for task_id, changed, expected in [('T_literal', 'folder (old)', 0),
                                           ('T_literal_forbidden', 'folder', 1)]:
            reset_mock()
            setup_task(task_id, ['folder (old)'], ['true'])
            set_mock_worker(f"echo content > '{changed}'; git add '{changed}'; git commit -qm literal")
            run_cmd([unio_bin, "run", "mock", task_id], env=env, cwd=str(repo_dir))
            p = run_cmd([unio_bin, "verify", "mock", task_id], env=env, cwd=str(repo_dir), check=False)
            assert p.returncode == expected, p.stdout + p.stderr
            assert "stripped annotation" not in p.stdout

        # 5c. Quoted path with spaces and parentheses (unannotated)
        reset_mock()
        setup_task("T_quoted", ['"dir with spaces/file (1).txt"'], ["test -s 'dir with spaces/file (1).txt'"])
        set_mock_worker("mkdir -p 'dir with spaces'; echo one > 'dir with spaces/file (1).txt'; git add 'dir with spaces'; git commit -qm 'quoted'")
        run_cmd([unio_bin, "run", "mock", "T_quoted"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_quoted"], env=env, cwd=str(repo_dir))
        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "warning" not in p.stdout.lower()

        # 5d. Quoted path with annotation outside quotes
        reset_mock()
        setup_task("T_quoted_annot", ['"dir/annotated.txt" (only one line)'], ["test -s dir/annotated.txt"])
        set_mock_worker("mkdir -p dir; echo annot > dir/annotated.txt; git add dir; git commit -qm 'quoted annot'")
        run_cmd([unio_bin, "run", "mock", "T_quoted_annot"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_quoted_annot"], env=env, cwd=str(repo_dir))
        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "warning  : stripped annotation '(only one line)' from scope pattern 'dir/annotated.txt'" in p.stdout

        # 5e. Backticked path with annotation
        reset_mock()
        setup_task("T_backtick_annot", ['`src/helper.py` (minor tweak)'], ["test -s src/helper.py"])
        set_mock_worker("mkdir -p src; echo helper > src/helper.py; git add src; git commit -qm 'backtick'")
        run_cmd([unio_bin, "run", "mock", "T_backtick_annot"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_backtick_annot"], env=env, cwd=str(repo_dir))
        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "warning  : stripped annotation '(minor tweak)' from scope pattern 'src/helper.py'" in p.stdout

        # 5f. Disambiguation of literal path ending with parentheses via quotes
        reset_mock()
        setup_task("T_disambig", ['"docs/archive (1)"'], ["test -s 'docs/archive (1)'"])
        set_mock_worker("mkdir -p docs; echo archive > 'docs/archive (1)'; git add docs; git commit -qm 'archive'")
        run_cmd([unio_bin, "run", "mock", "T_disambig"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_disambig"], env=env, cwd=str(repo_dir))
        assert p.returncode == 0
        assert "verdict  : PASS" in p.stdout
        assert "warning" not in p.stdout.lower()
        print("  ✓ unannotated paths (spaces, parentheses, quotes) and quoted disambiguation work cleanly")

        # -------------------------------------------------------------
        # 6. Retain missing scope / validate behavior
        # -------------------------------------------------------------
        reset_mock()
        (tasks_dir / "T_no_scope.md").write_text("# T\n## Goal\ntest\n## Validate\n$ true\n", encoding="utf-8")
        set_mock_worker("echo ok > ok.txt; git add ok.txt; git commit -qm 'ok'")
        run_cmd([unio_bin, "run", "mock", "T_no_scope"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_no_scope"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode == 2
        assert "verdict  : INCOMPLETE" in p.stdout
        assert "missing_scope" in p.stdout

        reset_mock()
        (tasks_dir / "T_no_validate.md").write_text("# T\n## Goal\ntest\n## Allowed scope\n- hello.txt\n", encoding="utf-8")
        set_mock_worker("echo hello > hello.txt; git add hello.txt; git commit -qm 'hello'")
        run_cmd([unio_bin, "run", "mock", "T_no_validate"], env=env, cwd=str(repo_dir))
        p = run_cmd([unio_bin, "verify", "mock", "T_no_validate"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode == 2
        assert "verdict  : INCOMPLETE" in p.stdout
        assert "missing_validate" in p.stdout
        print("  ✓ missing scope and missing validate behaviors strictly retained")

    print("ALL unio-scope-annotations tests passed successfully.")


if __name__ == "__main__":
    main()
