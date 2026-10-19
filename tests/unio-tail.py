#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Focused regression tests for non-blocking unio tail, bounds, and follow mode."""

import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def run_cmd(cmd, env=None, cwd=None, check=True):
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env=env, cwd=cwd, start_new_session=True) as proc:
        try:
            stdout, stderr = proc.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate(timeout=3)
            raise AssertionError(f"Command timed out after 15 seconds: {cmd}")
        p = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    if check and p.returncode != 0:
        raise AssertionError(f"Command failed (exit {p.returncode}): {cmd}\nstdout: {p.stdout}\nstderr: {p.stderr}")
    return p


def main():
    print("running unio tail regression suite...")
    with tempfile.TemporaryDirectory(prefix="unio tail test ") as td:
        sb = Path(td)
        bin_dir = sb / "bin dir"
        conf_dir = sb / "conf dir"
        comp_dir = sb / "comp dir"
        project_dir = sb / "project dir"
        repo_dir = project_dir / "repo"

        bin_dir.mkdir(parents=True)
        conf_dir.mkdir(parents=True)
        comp_dir.mkdir(parents=True)
        repo_dir.mkdir(parents=True)

        env = dict(os.environ)
        env["UNIO_BIN_DIR"] = str(bin_dir)
        env["UNIO_CONF_DIR"] = str(conf_dir)
        env["UNIO_COMPLETION_DIR"] = str(comp_dir)
        env["GIT_AUTHOR_NAME"] = "tail-test"
        env["GIT_AUTHOR_EMAIL"] = "tail@test.invalid"
        env["GIT_COMMITTER_NAME"] = "tail-test"
        env["GIT_COMMITTER_EMAIL"] = "tail@test.invalid"

        # Install unio
        run_cmd(["bash", str(REPO_ROOT / "unio-install.sh")], env=env, cwd=str(sb))
        unio_bin = str(bin_dir / "unio")
        assert os.path.isfile(unio_bin), f"unio binary missing: {unio_bin}"

        # Initialize git repo & unio project
        run_cmd(["git", "init", "-q", "-b", "dev", str(repo_dir)], env=env)
        run_cmd(["git", "commit", "-qm", "initial", "--allow-empty"], env=env, cwd=str(repo_dir))
        run_cmd([unio_bin, "init", "mock", "noop"], env=env, cwd=str(repo_dir))

        reports_dir = project_dir / "coord/reports"
        assert reports_dir.is_dir(), f"coord/reports missing: {reports_dir}"

        # -------------------------------------------------------------
        # 1. Default terminates against active append-only log (does not block)
        # -------------------------------------------------------------
        active_log = reports_dir / "T_active.log"
        with open(active_log, "w", encoding="utf-8") as f:
            for i in range(1, 51):
                f.write(f"active line {i}\n")

        stop_writer = threading.Event()

        def active_writer():
            idx = 51
            while not stop_writer.is_set():
                time.sleep(0.05)
                try:
                    with open(active_log, "a", encoding="utf-8") as lf:
                        lf.write(f"active line {idx}\n")
                        lf.flush()
                    idx += 1
                except Exception:
                    break

        writer_thread = threading.Thread(target=active_writer, daemon=True)
        writer_thread.start()

        start_time = time.monotonic()
        p = run_cmd([unio_bin, "tail", "T_active"], env=env, cwd=str(repo_dir))
        elapsed = time.monotonic() - start_time
        stop_writer.set()
        writer_thread.join(timeout=1.0)

        assert elapsed < 5.0, f"unio tail took too long ({elapsed}s); likely blocked following"
        assert p.returncode == 0, f"expected exit 0, got {p.returncode}"
        assert f">> {active_log}" in p.stdout
        lines = [line for line in p.stdout.splitlines() if line.startswith("active line ")]
        assert len(lines) == 40, f"expected 40 lines by default, got {len(lines)}"
        print("  ✓ default terminates against active append-only log in last 40 lines")

        # -------------------------------------------------------------
        # 2. Line count options and bounds
        # -------------------------------------------------------------
        lines_log = reports_dir / "T_lines.log"
        with open(lines_log, "w", encoding="utf-8") as f:
            for i in range(1, 101):
                f.write(f"line {i:03d}\n")

        # Positional task: default 40
        p = run_cmd([unio_bin, "tail", "T_lines"], env=env, cwd=str(repo_dir))
        out_lines = [l for l in p.stdout.splitlines() if l.startswith("line ")]
        assert len(out_lines) == 40
        assert out_lines[0] == "line 061" and out_lines[-1] == "line 100"

        # task.md compatibility
        p = run_cmd([unio_bin, "tail", "T_lines.md"], env=env, cwd=str(repo_dir))
        out_lines = [l for l in p.stdout.splitlines() if l.startswith("line ")]
        assert len(out_lines) == 40
        assert out_lines[0] == "line 061" and out_lines[-1] == "line 100"

        # --lines N
        p = run_cmd([unio_bin, "tail", "T_lines", "--lines", "10"], env=env, cwd=str(repo_dir))
        out_lines = [l for l in p.stdout.splitlines() if l.startswith("line ")]
        assert len(out_lines) == 10
        assert out_lines[0] == "line 091" and out_lines[-1] == "line 100"

        # -n N
        p = run_cmd([unio_bin, "tail", "T_lines", "-n", "5"], env=env, cwd=str(repo_dir))
        out_lines = [l for l in p.stdout.splitlines() if l.startswith("line ")]
        assert len(out_lines) == 5
        assert out_lines[0] == "line 096" and out_lines[-1] == "line 100"

        # --lines=N and -n=N
        p = run_cmd([unio_bin, "tail", "--lines=15", "T_lines"], env=env, cwd=str(repo_dir))
        out_lines = [l for l in p.stdout.splitlines() if l.startswith("line ")]
        assert len(out_lines) == 15

        p = run_cmd([unio_bin, "tail", "-n=7", "T_lines"], env=env, cwd=str(repo_dir))
        out_lines = [l for l in p.stdout.splitlines() if l.startswith("line ")]
        assert len(out_lines) == 7

        # Practical option ordering
        p = run_cmd([unio_bin, "tail", "--lines", "12", "T_lines"], env=env, cwd=str(repo_dir))
        out_lines = [l for l in p.stdout.splitlines() if l.startswith("line ")]
        assert len(out_lines) == 12
        print("  ✓ requested line count and flexible option ordering verified")

        # -------------------------------------------------------------
        # 3. No task selects latest log file
        # -------------------------------------------------------------
        time.sleep(0.05)
        newest_log = reports_dir / "T_newest.log"
        with open(newest_log, "w", encoding="utf-8") as f:
            f.write("newest log line 1\nnewest log line 2\n")

        p = run_cmd([unio_bin, "tail"], env=env, cwd=str(repo_dir))
        assert f">> {newest_log}" in p.stdout
        assert "newest log line 1" in p.stdout
        assert "newest log line 2" in p.stdout
        print("  ✓ no task argument selects latest log as current")

        # -------------------------------------------------------------
        # 4. Safe filenames with spaces preserved
        # -------------------------------------------------------------
        time.sleep(0.05)
        spaces_log = reports_dir / "task with spaces.log"
        with open(spaces_log, "w", encoding="utf-8") as f:
            f.write("spaces log line A\nspaces log line B\n")

        p = run_cmd([unio_bin, "tail"], env=env, cwd=str(repo_dir))
        assert f">> {spaces_log}" in p.stdout
        assert "spaces log line A" in p.stdout
        assert "spaces log line B" in p.stdout
        print("  ✓ filenames and project paths with spaces safely preserved")

        # -------------------------------------------------------------
        # 5. Explicit-follow waits and can be stopped locally safely
        # -------------------------------------------------------------
        follow_log = reports_dir / "T_follow.log"
        with open(follow_log, "w", encoding="utf-8") as f:
            f.write("initial follow line 1\ninitial follow line 2\n")

        # Start unio tail -f T_follow
        proc = subprocess.Popen(
            [unio_bin, "tail", "-f", "T_follow"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(repo_dir)
        )

        try:
            # Read header and initial lines
            header = proc.stdout.readline()
            assert f">> {follow_log}" in header
            line1 = proc.stdout.readline()
            assert "initial follow line 1" in line1
            line2 = proc.stdout.readline()
            assert "initial follow line 2" in line2

            # Now append a new line to simulate live work
            with open(follow_log, "a", encoding="utf-8") as f:
                f.write("live followed line 3\n")
                f.flush()

            # The follower should pick it up
            line3 = proc.stdout.readline()
            assert "live followed line 3" in line3, f"expected live followed line 3, got: {repr(line3)}"

            # Safely stop with SIGTERM
            proc.send_signal(signal.SIGTERM)
            proc.wait(timeout=3.0)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()

        # Also test --follow with practical option ordering
        proc2 = subprocess.Popen(
            [unio_bin, "tail", "T_follow", "--follow", "--lines", "1"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=str(repo_dir)
        )
        try:
            hdr = proc2.stdout.readline()
            assert f">> {follow_log}" in hdr
            l = proc2.stdout.readline()
            assert "live followed line 3" in l
            proc2.send_signal(signal.SIGINT)
            proc2.wait(timeout=3.0)
        finally:
            if proc2.poll() is None:
                proc2.kill()
                proc2.wait()
        print("  ✓ explicit follow waits for appends and stops cleanly")

        # -------------------------------------------------------------
        # 6. Actionable errors: unknown, duplicate, ambiguous, bad bounds, path traversal
        # -------------------------------------------------------------
        # Unknown option
        p = run_cmd([unio_bin, "tail", "--bad-opt"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode != 0
        assert "unknown option: '--bad-opt'" in p.stderr

        # Duplicate follow
        p = run_cmd([unio_bin, "tail", "-f", "--follow"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode != 0
        assert "duplicate follow option" in p.stderr

        # Duplicate lines
        p = run_cmd([unio_bin, "tail", "--lines", "10", "--lines", "20"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode != 0
        assert "duplicate line count option" in p.stderr

        p = run_cmd([unio_bin, "tail", "-n", "10", "--lines=20"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode != 0
        assert "duplicate line count option" in p.stderr

        # Ambiguous task arguments
        p = run_cmd([unio_bin, "tail", "T1", "T2"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode != 0
        assert "ambiguous arguments" in p.stderr

        # Missing argument
        p = run_cmd([unio_bin, "tail", "--lines"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode != 0
        assert "requires a positive integer argument" in p.stderr

        # Bad line counts
        for bad_n in ["0", "-5", "abc", "100001"]:
            p = run_cmd([unio_bin, "tail", "--lines", bad_n], env=env, cwd=str(repo_dir), check=False)
            assert p.returncode != 0, f"expected failure for --lines {bad_n}"

        # Path traversal and invalid task IDs
        for bad_id in ["../secret", "../secret.md", "/etc/passwd", "..", "", "T/sub", "T..name", "T with spaces"]:
            p = run_cmd([unio_bin, "tail", bad_id], env=env, cwd=str(repo_dir), check=False)
            assert p.returncode != 0, f"expected failure for task id {repr(bad_id)}"

        # Missing task log
        p = run_cmd([unio_bin, "tail", "NONEXISTENT"], env=env, cwd=str(repo_dir), check=False)
        assert p.returncode != 0
        assert "no log found for task 'NONEXISTENT'" in p.stderr
        print("  ✓ actionable errors for bad options, bounds, and traversal attempts")

    print("ALL unio-tail tests passed successfully.")


if __name__ == "__main__":
    main()
