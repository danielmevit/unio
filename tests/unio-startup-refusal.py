#!/usr/bin/env python3
"""
tests/unio-startup-refusal.py — Regression suite for visible background
Git-lock startup refusals (BACKGROUND-STARTUP-REFUSAL-20261113 / next 0.5.28).

Verifies that the pre-provider Gitdir-resolution / index.lock startup refusal
leaves a dated, distinct diagnostic in the task report and log:
- Foreground refusal keeps its nonzero exit, original stderr diagnostic, and
  appends a visible `## startup-refused` fragment after any existing content.
- Background refusal: the parent's exit-0 line stays a launch acknowledgement,
  while the detached child (stderr discarded) still records the refusal; the
  fragment appears through `unio report` and `unio tail` after bounded polling.
- Provider stub is never called on refusal; the lock entry, ledger, results,
  and native budget slots stay untouched (no grant consumed).
- Normal foreground and background runs still succeed and record no fragment.
- Gitdir-resolution failure records phase=gitdir-resolution evidence.
All fixtures are disposable and offline; no live provider is contacted.
"""

from pathlib import Path
import fcntl
import os
import shlex
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
    cand = Path('/mnt/d/Vibe Coding/_vm/unio/tmp/unio-next/startup-refusal-mistral-glm-high-20261113/fixtures')
    try:
        cand.mkdir(parents=True, exist_ok=True)
        if cand.is_dir():
            return cand
    except OSError:
        pass
    if 'UNIO_TEST_SCRATCH' in os.environ:
        p = Path(os.environ['UNIO_TEST_SCRATCH'])
        if p.is_dir():
            return p
    return None


def wait_until(predicate, timeout, interval=0.05, message='condition'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    raise AssertionError(f"bounded polling timed out after {timeout}s waiting for {message}")


def write_task(tasks_dir, name):
    task_file = tasks_dir / (name + '.md')
    task_file.write_text(
        '# Task ' + name + ' — worker: stub\n\n'
        '## Goal\nVerify visible startup refusals\n\n'
        '## Context\nOffline regression fixture\n\n'
        '## Allowed scope\n- candidate.txt\n\n'
        '## Constraints\nnone\n\n'
        '## Validate\n$ true\n\n'
        '## Done means\ncommitted\n\n'
        '## Report\nSUMMARY\n'
    )
    return task_file


def run_tests():
    installer = find_installer()
    scratch_base = get_scratch_base()

    with tempfile.TemporaryDirectory(prefix='unio-startup-refusal-', dir=scratch_base) as fixture_dir:
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
            GIT_AUTHOR_NAME='Startup Refusal Tester',
            GIT_COMMITTER_NAME='Startup Refusal Tester',
            GIT_AUTHOR_EMAIL='tester@example.invalid',
            GIT_COMMITTER_EMAIL='tester@example.invalid',
        )
        env['PATH'] = str(bin_dir) + os.pathsep + env.get('PATH', '')

        # Install unio via subprocess (private destinations, no user config)
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
        reports_dir = root / 'coord/reports'
        slots_dir = root / 'coord/.locks/work-policy-slots'
        ledger = reports_dir / 'ledger.jsonl'
        results = root / 'coord/results/stub'
        wt = root / 'wt/stub'
        t_ref_fg = write_task(tasks_dir, 'T-START-REF1')
        t_ref_bg = write_task(tasks_dir, 'T-START-REF2')
        t_ctrl_fg = write_task(tasks_dir, 'T-START-CTRL')
        t_ctrl_bg = write_task(tasks_dir, 'T-START-CTRLB')
        t_gitdir = write_task(tasks_dir, 'T-START-GITDIR')
        assert t_ref_bg.is_file() and t_gitdir.is_file()

        gitdir = Path(subprocess.check_output(
            ['git', 'rev-parse', '--path-format=absolute', '--git-dir'],
            cwd=wt, env=env, text=True).strip())
        lock_file = gitdir / 'index.lock'

        def ledger_lines(task):
            if not ledger.is_file():
                return []
            return [ln for ln in ledger.read_text().splitlines() if f'"task":"{task}"' in ln]

        # A run holds an flock on coord/.locks/<worker>.lock for its whole
        # life, so acquirability from here is the bounded outcome signal for
        # a detached child: free means the child exited (refusal or success).
        def worker_lock_free():
            path = root / 'coord/.locks/stub.lock'
            try:
                fd = os.open(str(path), os.O_RDWR)
            except OSError:
                return True
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(fd, fcntl.LOCK_UN)
                return True
            except OSError:
                return False
            finally:
                os.close(fd)

        def slots_idle():
            if not slots_dir.is_dir():
                return True
            return not any(p.is_file() for p in slots_dir.rglob('*'))

        def unio(*args, timeout=120):
            return subprocess.run([str(at), *args], cwd=repo, env=env,
                                  capture_output=True, text=True, timeout=timeout)

        print("[TEST 1] Foreground refusal: visible fragment, sentinels preserved, provider untouched...")
        report = reports_dir / 'T-START-REF1.md'
        log = reports_dir / 'T-START-REF1.log'
        report_sentinel = 'SENTINEL-REPORT-START\noriginal report line\n'
        log_sentinel = 'SENTINEL-LOG-START\noriginal log line\n'
        reports_dir.mkdir(parents=True, exist_ok=True)
        report.write_text(report_sentinel)
        log.write_text(log_sentinel)
        lock_file.write_bytes(b'stale lock from interrupted process\n')
        lock_inode = lock_file.stat().st_ino
        calls_before = get_provider_calls()

        res = unio('run', 'stub', 'T-START-REF1')
        if res.returncode == 0:
            raise AssertionError("foreground run unexpectedly succeeded with index.lock present")
        if 'unio: Git index is busy or held by an unmanaged process' not in res.stderr:
            raise AssertionError(f"original stderr diagnostic missing:\n{res.stderr}")
        if str(lock_file) not in res.stderr:
            raise AssertionError(f"stderr does not name the lock path:\n{res.stderr}")
        if get_provider_calls() != calls_before:
            raise AssertionError("provider stub was called during a refused foreground run")
        if not lock_file.is_file() or lock_file.stat().st_ino != lock_inode \
                or lock_file.read_bytes() != b'stale lock from interrupted process\n':
            raise AssertionError("index.lock was altered by the refused run")
        report_text = report.read_text()
        log_text = log.read_text()
        if not report_text.startswith(report_sentinel):
            raise AssertionError("original report content was not preserved:\n" + report_text)
        if not log_text.startswith(log_sentinel):
            raise AssertionError("original log content was not preserved:\n" + log_text)
        for text, where in ((report_text, 'report'), (log_text, 'log')):
            if '## startup-refused ' not in text:
                raise AssertionError(f"no startup-refused fragment in {where}:\n{text}")
            if 'phase=git-index-lock' not in text:
                raise AssertionError(f"fragment misses phase in {where}:\n{text}")
            if 'worker=stub' not in text or 'task=T-START-REF1' not in text:
                raise AssertionError(f"fragment misses worker/task in {where}:\n{text}")
        if 'No provider was started' not in report_text:
            raise AssertionError(f"fragment misses provider-not-started statement:\n{report_text}")
        if 'Provider not started' not in log_text:
            raise AssertionError(f"log fragment misses provider-not-started statement:\n{log_text}")
        if 'budget-refused' in report_text:
            raise AssertionError("refusal was mislabeled as a budget refusal:\n" + report_text)
        if 'cannot determine git directory' in report_text:
            raise AssertionError("wrong phase evidence in report fragment")
        if ledger_lines('T-START-REF1'):
            raise AssertionError("ledger recorded events for a refused run:\n"
                                 + '\n'.join(ledger_lines('T-START-REF1')))
        if not slots_idle():
            raise AssertionError("native budget slot left behind by a refused run")
        if (results / 'T-START-REF1.json').exists():
            raise AssertionError("a refused run produced a structured result")
        rep = unio('report', 'T-START-REF1')
        if rep.returncode != 0 or '## startup-refused ' not in rep.stdout:
            raise AssertionError(f"unio report does not show the refusal: rc={rep.returncode}\n{rep.stdout}")
        tail_res = unio('tail', 'T-START-REF1')
        if tail_res.returncode != 0 or '## startup-refused ' not in tail_res.stdout:
            raise AssertionError(f"unio tail does not show the refusal: rc={tail_res.returncode}\n{tail_res.stdout}")
        if get_provider_calls() != calls_before:
            raise AssertionError("provider stub was called while reporting a refusal")
        lock_file.unlink()
        print("  PASS: refusal visible via report/tail; sentinels, lock, provider, ledger and slots untouched.")

        print("[TEST 2] Background refusal: parent acknowledgement, child evidence after bounded polling...")
        report_bg = reports_dir / 'T-START-REF2.md'
        log_bg = reports_dir / 'T-START-REF2.log'
        lock_file.write_bytes(b'stale lock for background refusal\n')
        lock_inode_bg = lock_file.stat().st_ino
        calls_before = get_provider_calls()

        res = unio('run', '-b', 'stub', 'T-START-REF2', timeout=60)
        if res.returncode != 0:
            raise AssertionError(f"background parent refused at launch (rc={res.returncode}):\n{res.stderr}")
        if 'started in background' not in res.stdout:
            raise AssertionError(f"parent acknowledgement missing:\n{res.stdout}")

        def child_refusal_recorded():
            return (report_bg.is_file() and '## startup-refused ' in report_bg.read_text()
                    and log_bg.is_file() and '## startup-refused ' in log_bg.read_text())

        wait_until(child_refusal_recorded, 60.0, 0.05, 'detached child refusal fragment in report/log')
        # The fragment precedes the child's die: wait for its exit (lock free)
        # before asserting anything about post-refusal state.
        wait_until(worker_lock_free, 30.0, 0.05, 'refusing background child to exit')

        if get_provider_calls() != calls_before:
            raise AssertionError("provider stub was called during a refused background run")
        if not lock_file.is_file() or lock_file.stat().st_ino != lock_inode_bg \
                or lock_file.read_bytes() != b'stale lock for background refusal\n':
            raise AssertionError("index.lock was altered by the refused background run")
        report_text = report_bg.read_text()
        log_text = log_bg.read_text()
        if 'phase=git-index-lock' not in report_text or 'phase=git-index-lock' not in log_text:
            raise AssertionError(f"background fragment misses phase:\n{report_text}\n{log_text}")
        if 'worker=stub' not in report_text or 'task=T-START-REF2' not in report_text:
            raise AssertionError(f"background fragment misses worker/task:\n{report_text}")
        if 'No provider was started' not in report_text or 'Provider not started' not in log_text:
            raise AssertionError("background fragment misses provider-not-started statement")
        if 'budget-refused' in report_text:
            raise AssertionError("background refusal mislabeled as budget refusal:\n" + report_text)
        if ledger_lines('T-START-REF2'):
            raise AssertionError("ledger recorded events for a refused background run:\n"
                                 + '\n'.join(ledger_lines('T-START-REF2')))
        if (results / 'T-START-REF2.json').exists():
            raise AssertionError("a refused background run produced a structured result")
        if (reports_dir / 'T-START-REF2.pid').exists():
            raise AssertionError("a refused background run left a background pidfile")
        rep = unio('report', 'T-START-REF2')
        if rep.returncode != 0 or '## startup-refused ' not in rep.stdout:
            raise AssertionError(f"unio report does not show the background refusal: rc={rep.returncode}\n{rep.stdout}")
        tail_res = unio('tail', 'T-START-REF2')
        if tail_res.returncode != 0 or '## startup-refused ' not in tail_res.stdout:
            raise AssertionError(f"unio tail does not show the background refusal: rc={tail_res.returncode}\n{tail_res.stdout}")
        lock_file.unlink()
        print("  PASS: parent acked exit 0; child refusal recorded; no provider, grant, result or pidfile.")

        print("[TEST 3] Normal foreground run control...")
        calls_before = get_provider_calls()
        res = unio('run', 'stub', 'T-START-CTRL')
        if res.returncode != 0:
            raise AssertionError(f"normal foreground run failed (rc={res.returncode}):\n{res.stderr}\n{res.stdout}")
        if get_provider_calls() != calls_before + 1:
            raise AssertionError("normal foreground run did not invoke the provider exactly once")
        ctrl_report = (reports_dir / 'T-START-CTRL.md').read_text() if (reports_dir / 'T-START-CTRL.md').is_file() else ''
        ctrl_log = (reports_dir / 'T-START-CTRL.log').read_text() if (reports_dir / 'T-START-CTRL.log').is_file() else ''
        if '## run ' not in ctrl_report:
            raise AssertionError("normal run did not record its run fragment:\n" + ctrl_report)
        if '## startup-refused ' in ctrl_report or '## startup-refused ' in ctrl_log:
            raise AssertionError("normal run recorded a startup refusal fragment")
        if lock_file.exists():
            raise AssertionError("index.lock appeared after a normal run")
        print("  PASS: normal foreground run succeeded with the provider called exactly once.")

        print("[TEST 4] Normal background run control...")
        calls_before = get_provider_calls()
        res = unio('run', '-b', 'stub', 'T-START-CTRLB', timeout=60)
        if res.returncode != 0:
            raise AssertionError(f"normal background run refused at launch (rc={res.returncode}):\n{res.stderr}\n{res.stdout}")
        if 'started in background' not in res.stdout:
            raise AssertionError(f"parent acknowledgement missing:\n{res.stdout}")
        # run_start is recorded while the child holds the worker lock; the lock
        # turning free afterwards bounds the provider phase deterministically.
        wait_until(lambda: any('"event":"run_start"' in ln for ln in ledger_lines('T-START-CTRLB')),
                   60.0, 0.05, 'normal background child to start')
        wait_until(worker_lock_free, 120.0, 0.05, 'normal background child to finish')
        if get_provider_calls() != calls_before + 1:
            raise AssertionError("normal background run did not invoke the provider exactly once")
        ctrlb_report = (reports_dir / 'T-START-CTRLB.md').read_text() if (reports_dir / 'T-START-CTRLB.md').is_file() else ''
        if '## run ' not in ctrlb_report or '## startup-refused ' in ctrlb_report:
            raise AssertionError("normal background run report content unexpected:\n" + ctrlb_report)
        if slots_idle() is False:
            raise AssertionError("native budget slot left behind after normal background run")
        print("  PASS: normal background run succeeded, provider called once, no refusal fragment.")

        print("[TEST 5] Gitdir-resolution failure records its own phase...")
        hidden = gitdir.parent / (gitdir.name + '.fixture-hidden')
        assert not hidden.exists()
        gitdir.rename(hidden)
        try:
            res = unio('run', 'stub', 'T-START-GITDIR')
            if res.returncode == 0:
                raise AssertionError("run unexpectedly succeeded with unresolvable gitdir")
            if 'unio: cannot determine git directory for worktree' not in res.stderr:
                raise AssertionError(f"original gitdir stderr diagnostic missing:\n{res.stderr}")
            if get_provider_calls() != 2:
                raise AssertionError("provider stub was called during a gitdir refusal")
            report_text = (reports_dir / 'T-START-GITDIR.md').read_text()
            log_text = (reports_dir / 'T-START-GITDIR.log').read_text()
            if '## startup-refused ' not in report_text or '## startup-refused ' not in log_text:
                raise AssertionError(f"gitdir refusal not recorded:\n{report_text}\n{log_text}")
            if 'phase=gitdir-resolution' not in report_text:
                raise AssertionError(f"gitdir fragment misses phase:\n{report_text}")
            if 'No provider was started' not in report_text:
                raise AssertionError("gitdir fragment misses provider-not-started statement")
            if ledger_lines('T-START-GITDIR'):
                raise AssertionError("ledger recorded events for a gitdir-refused run")
            if not slots_idle():
                raise AssertionError("native budget slot left behind by a gitdir-refused run")
        finally:
            hidden.rename(gitdir)
        print("  PASS: gitdir-resolution refusal recorded phase evidence without a provider call.")

    print("\nAll startup-refusal visibility tests passed successfully.")


if __name__ == '__main__':
    run_tests()
