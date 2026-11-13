#!/usr/bin/env python3
"""
tests/unio-index-lock.py — Regression suite for Git index.lock safety (R-02 / next0.5.28).

Verifies that unio run preserves live and Unknown Git index locks:
- Refuses startup nonzero BEFORE provider or account grant consumption.
- Never removes or alters index.lock (regular, symlink, broken symlink, or non-regular).
- Allows live writer to finish exit 0 with all staged updates intact.
- Target file bytes are preserved and git fsck passes.
- Normal runs without index.lock proceed cleanly.
"""

from pathlib import Path
import os
import shlex
import signal
import subprocess
import sys
import tempfile
import time


def find_installer():
    root = Path(__file__).resolve().parent.parent
    installer = root / 'unio-install.sh'
    if not installer.is_file():
        raise RuntimeError(f"unio-install.sh not found at {installer}")
    return installer


def get_scratch_base():
    # Keep scratch files isolated to designated fixtures dir or system temp
    cand = Path('/mnt/d/Vibe Coding/_vm/unio/tmp/unio-next/index-lock-gemini-medium-20261113/fixtures')
    if cand.is_dir():
        return cand
    if 'UNIO_TEST_SCRATCH' in os.environ:
        p = Path(os.environ['UNIO_TEST_SCRATCH'])
        if p.is_dir():
            return p
    return None


def run_tests():
    installer = find_installer()
    scratch_base = get_scratch_base()
    
    with tempfile.TemporaryDirectory(prefix='unio-index-lock-', dir=scratch_base) as fixture_dir:
        L = Path(fixture_dir)
        bin_dir = L / 'bin'
        conf_dir = L / 'conf'
        comp_dir = L / 'completion'
        bin_dir.mkdir(parents=True, exist_ok=True)
        conf_dir.mkdir(parents=True, exist_ok=True)
        comp_dir.mkdir(parents=True, exist_ok=True)

        # Explicit all 3 UNIO install paths before any subprocess installer. NEVER SOURCE installer.
        env = dict(
            os.environ,
            UNIO_BIN_DIR=str(bin_dir),
            UNIO_CONF_DIR=str(conf_dir),
            UNIO_COMPLETION_DIR=str(comp_dir),
            UNIO_CLI_UPDATES_OFFLINE='1',
            UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_SYNC='0',
            UNIO_AUTO_OFF='0',
            GIT_CONFIG_GLOBAL='/dev/null',
            GIT_CONFIG_NOSYSTEM='1',
            GIT_AUTHOR_NAME='Index Lock Tester',
            GIT_COMMITTER_NAME='Index Lock Tester',
            GIT_AUTHOR_EMAIL='tester@example.invalid',
            GIT_COMMITTER_EMAIL='tester@example.invalid',
        )
        env['PATH'] = str(bin_dir) + os.pathsep + env.get('PATH', '')

        # Install unio via subprocess
        res = subprocess.run(['bash', str(installer)], env=env, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"Installer failed (rc={res.returncode}):\n{res.stderr}\n{res.stdout}")

        at = bin_dir / 'unio'
        if not at.is_file():
            raise RuntimeError(f"Installed CLI not found at {at}")

        # Offline codegraph stub
        codegraph = bin_dir / 'codegraph'
        codegraph.write_text('#!/bin/sh\nexit 0\n')
        codegraph.chmod(0o755)

        # Offline provider stub and marker
        marker = L / 'provider-marker'
        stub = L / 'provider-stub.sh'
        stub.write_text(
            '#!/bin/bash\n'
            'printf called >> ' + shlex.quote(str(marker)) + '\n'
            'exit 0\n'
        )
        stub.chmod(0o755)
        (conf_dir / 'agents.conf').write_text('stub=bash ' + shlex.quote(str(stub)) + '\n')

        def get_provider_calls():
            return marker.read_text().count('called') if marker.is_file() else 0

        # Initialize test repository and worktree
        repo = L / 'project/repo'
        repo.mkdir(parents=True, exist_ok=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=repo, env=env, check=True)
        (repo / 'base.txt').write_text('fixture baseline\n')
        subprocess.run(['git', 'add', 'base.txt'], cwd=repo, env=env, check=True)
        subprocess.run(['git', 'commit', '-qm', 'fixture baseline'], cwd=repo, env=env, check=True)

        # Initialize unio worker
        res = subprocess.run([str(at), 'init', 'stub'], cwd=repo, env=env, capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"unio init failed (rc={res.returncode}):\n{res.stderr}\n{res.stdout}")

        root = repo.parent
        tasks_dir = root / 'coord/tasks'
        tasks_dir.mkdir(parents=True, exist_ok=True)
        task_file = tasks_dir / 'T-LOCK-TEST.md'
        task_file.write_text(
            '# Task T-LOCK-TEST — worker: stub\n\n'
            '## Goal\nPreserve Git index locks\n\n'
            '## Context\nTesting lock preservation\n\n'
            '## Allowed scope\n- candidate.txt\n\n'
            '## Constraints\nnone\n\n'
            '## Validate\n$ true\n\n'
            '## Done means\ncommitted\n\n'
            '## Report\nSUMMARY\n'
        )

        wt = root / 'wt/stub'
        gitdir_raw = subprocess.check_output(
            ['git', 'rev-parse', '--path-format=absolute', '--git-dir'],
            cwd=wt, env=env, text=True
        ).strip()
        gitdir = Path(gitdir_raw)
        lock_file = gitdir / 'index.lock'

        target = wt / 'candidate.txt'
        initial_target_bytes = b'candidate file content remains untouched\n'
        target.write_bytes(initial_target_bytes)

        def start_live_writer():
            child = subprocess.Popen(
                ['git', 'update-index', '--add', '--stdin'],
                cwd=wt, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                start_new_session=True
            )
            deadline = time.monotonic() + 10.0
            while not lock_file.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.02)
            if child.poll() is not None:
                _, err = child.communicate()
                raise RuntimeError(f"Writer exited prematurely: {err.decode('utf-8', errors='replace')}")
            if not lock_file.exists():
                child.kill()
                child.wait()
                raise RuntimeError("Writer did not acquire index.lock in time")
            return child

        print("[TEST 1] Control: Owned live writer stages file and exits 0...")
        writer = start_live_writer()
        try:
            _, err = writer.communicate(b'candidate.txt\n', timeout=10)
            if writer.returncode != 0:
                raise AssertionError(f"Control writer failed (rc={writer.returncode}): {err.decode()}")
            staged = subprocess.check_output(['git', 'ls-files', '--', 'candidate.txt'], cwd=wt, env=env, text=True).strip()
            if staged != 'candidate.txt':
                raise AssertionError("Control writer did not stage candidate.txt")
            if lock_file.exists():
                raise AssertionError("index.lock remained after control writer completion")
        finally:
            if writer.poll() is None:
                os.killpg(writer.pid, signal.SIGKILL)
                writer.wait()
        subprocess.run(['git', 'rm', '-q', '--cached', '--', 'candidate.txt'], cwd=wt, env=env, check=True)
        print("  PASS: Control writer completed exit 0, candidate staged, lock cleared.")

        print("[TEST 2] Reproduce owned live writer + candidate unio run...")
        writer = start_live_writer()
        try:
            lock_inode_before = lock_file.stat().st_ino
            calls_before = get_provider_calls()

            run_res = subprocess.run(
                [str(at), 'run', 'stub', 'T-LOCK-TEST'],
                cwd=repo, env=env, capture_output=True, text=True, timeout=90
            )

            # 1. unio run must refuse startup with nonzero returncode
            if run_res.returncode == 0:
                raise AssertionError("unio run unexpectedly succeeded while live writer held index.lock!")

            # 2. Provider stub must NOT have been called
            calls_after = get_provider_calls()
            if calls_after != calls_before:
                raise AssertionError(f"Provider was called {calls_after - calls_before} time(s); should be 0!")

            # 3. Live writer must still be alive
            if writer.poll() is not None:
                raise AssertionError("Live writer was killed or exited prematurely during unio run!")

            # 4. index.lock must still exist with the exact same inode
            if not lock_file.exists():
                raise AssertionError("index.lock was deleted by unio run!")
            if lock_file.stat().st_ino != lock_inode_before:
                raise AssertionError("index.lock was replaced/recreated by unio run!")

            # 5. Live writer completes successfully
            _, err = writer.communicate(b'candidate.txt\n', timeout=10)
            if writer.returncode != 0:
                raise AssertionError(f"Live writer failed after unio run (rc={writer.returncode}): {err.decode()}")

            # 6. Candidate file is staged by writer
            staged = subprocess.check_output(['git', 'ls-files', '--', 'candidate.txt'], cwd=wt, env=env, text=True).strip()
            if staged != 'candidate.txt':
                raise AssertionError("candidate.txt was not staged by writer after unio run")

            # 7. Candidate file bytes are unchanged
            if target.read_bytes() != initial_target_bytes:
                raise AssertionError("candidate.txt file bytes were altered!")

            # 8. git fsck passes
            fsck = subprocess.run(['git', 'fsck', '--no-reflogs'], cwd=wt, env=env, capture_output=True, text=True)
            if fsck.returncode != 0:
                raise AssertionError(f"git fsck failed (rc={fsck.returncode}): {fsck.stderr}")
        finally:
            if writer.poll() is None:
                try:
                    os.killpg(writer.pid, signal.SIGTERM)
                    writer.wait(timeout=2)
                except Exception:
                    os.killpg(writer.pid, signal.SIGKILL)
                    writer.wait()

        subprocess.run(['git', 'rm', '-q', '--cached', '--', 'candidate.txt'], cwd=wt, env=env, check=True)
        print("  PASS: Live writer preserved, lock untouched, unio refused nonzero, writer exited 0, update staged.")

        print("[TEST 3] Stale / Unknown pre-existing lock file...")
        stale_content = b'stale lock file from interrupted process\n'
        lock_file.write_bytes(stale_content)
        stale_inode = lock_file.stat().st_ino
        calls_before = get_provider_calls()

        run_res = subprocess.run(
            [str(at), 'run', 'stub', 'T-LOCK-TEST'],
            cwd=repo, env=env, capture_output=True, text=True, timeout=90
        )
        if run_res.returncode == 0:
            raise AssertionError("unio run unexpectedly succeeded with pre-existing index.lock!")
        if get_provider_calls() != calls_before:
            raise AssertionError("Provider called when stale index.lock existed!")
        if not lock_file.exists():
            raise AssertionError("Pre-existing index.lock was deleted by unio run!")
        if lock_file.stat().st_ino != stale_inode or lock_file.read_bytes() != stale_content:
            raise AssertionError("Pre-existing index.lock content or inode was modified!")
        lock_file.unlink()
        print("  PASS: Pre-existing lock left untouched, unio refused nonzero, provider not called.")

        print("[TEST 4] Broken symlink index.lock negative case...")
        broken_target = wt / 'nonexistent-target'
        lock_file.symlink_to(broken_target)
        if not lock_file.is_symlink():
            raise AssertionError("Failed to create broken symlink")
        calls_before = get_provider_calls()

        run_res = subprocess.run(
            [str(at), 'run', 'stub', 'T-LOCK-TEST'],
            cwd=repo, env=env, capture_output=True, text=True, timeout=90
        )
        if run_res.returncode == 0:
            raise AssertionError("unio run unexpectedly succeeded with broken symlink index.lock!")
        if get_provider_calls() != calls_before:
            raise AssertionError("Provider called with broken symlink index.lock!")
        if not lock_file.is_symlink():
            raise AssertionError("Broken symlink index.lock was deleted or altered!")
        lock_file.unlink()
        print("  PASS: Broken symlink lock refused nonzero, link preserved, provider not called.")

        print("[TEST 5] Special non-regular entry (directory as index.lock)...")
        lock_file.mkdir()
        calls_before = get_provider_calls()

        run_res = subprocess.run(
            [str(at), 'run', 'stub', 'T-LOCK-TEST'],
            cwd=repo, env=env, capture_output=True, text=True, timeout=90
        )
        if run_res.returncode == 0:
            raise AssertionError("unio run unexpectedly succeeded with directory index.lock!")
        if get_provider_calls() != calls_before:
            raise AssertionError("Provider called with directory index.lock!")
        if not lock_file.is_dir():
            raise AssertionError("Directory index.lock was altered or deleted!")
        lock_file.rmdir()
        print("  PASS: Directory index.lock refused nonzero, untouched, provider not called.")

        print("[TEST 6] Normal run without index.lock...")
        calls_before = get_provider_calls()
        run_res = subprocess.run(
            [str(at), 'run', 'stub', 'T-LOCK-TEST'],
            cwd=repo, env=env, capture_output=True, text=True, timeout=90
        )
        if run_res.returncode != 0:
            raise AssertionError(f"Normal unio run failed (rc={run_res.returncode}):\n{run_res.stderr}\n{run_res.stdout}")
        calls_after = get_provider_calls()
        if calls_after != calls_before + 1:
            raise AssertionError(f"Provider expected 1 call, got {calls_after - calls_before}")
        if lock_file.exists():
            raise AssertionError("index.lock remained after normal run")
        print("  PASS: Normal run succeeded with exit 0 and provider executed.")

    print("\nAll index.lock safety tests passed successfully.")


if __name__ == '__main__':
    run_tests()
