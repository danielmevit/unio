#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Owned native provider cleanup through the installed public run and kill path.

Fixtures are generic local processes. No provider binary, credential, or
real task path is used. Cleanup signals only recorded pid+start pairs.
"""
import fcntl
import json
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
passed = 0


def check(label, condition, detail=''):
    global passed
    if not condition:
        print('FAIL ' + label)
        if detail:
            print(detail)
        raise SystemExit(1)
    passed += 1
    print('  ok ' + label, flush=True)


def proc_stat(pid):
    try:
        raw = Path('/proc/%d/stat' % pid).read_bytes()
    except OSError:
        return None
    end = raw.rfind(b')')
    if end < 0:
        return None
    fields = raw[end + 2:].split()
    if len(fields) < 20:
        return None
    try:
        return {
            'pid': pid,
            'state': fields[0].decode('ascii', 'replace'),
            'ppid': int(fields[1]),
            'pgid': int(fields[2]),
            'sid': int(fields[3]),
            'start': int(fields[19]),
        }
    except (ValueError, IndexError):
        return None


def same_process(pid, start):
    current = proc_stat(pid)
    return current is not None and current['start'] == start and current['state'] not in ('Z', 'X', 'x')


def kill_exact(pid, start):
    """SIGKILL only when the live process is still the one we recorded."""
    if pid <= 1 or not same_process(pid, start):
        return
    try:
        handle = os.pidfd_open(pid)
    except OSError:
        return
    try:
        if same_process(pid, start):
            signal.pidfd_send_signal(handle, signal.SIGKILL)
    except OSError:
        pass
    finally:
        os.close(handle)


def child_pids(pid):
    try:
        raw = Path('/proc/%d/task/%d/children' % (pid, pid)).read_text().split()
    except OSError:
        return []
    return [int(tok) for tok in raw if tok.isdigit()]


def kill_recorded_tree(pid, start):
    current = proc_stat(pid)
    if current is None or current['start'] != start:
        return
    found = []

    def walk(parent):
        for child in child_pids(parent):
            info = proc_stat(child)
            if info is None or info['ppid'] != parent:
                continue
            found.append(info)
            walk(child)

    walk(pid)
    for info in reversed(found):
        kill_exact(info['pid'], info['start'])
    kill_exact(pid, start)


with tempfile.TemporaryDirectory(prefix='native-stop-', dir='/tmp') as directory:
    base = Path(directory)
    fixture = base / 'fixture'
    fixture.mkdir()
    real_git = shutil.which('git')
    shim_dir = base / 'git-shim'
    shim_dir.mkdir()
    (shim_dir / 'delay.py').write_text(
        'import os, sys, time\n'
        'from pathlib import Path\n'
        'shim = Path(os.environ["NATIVE_STOP_SHIM"])\n'
        'once = shim / "delayed"\n'
        'if not once.exists():\n'
        '    started = time.monotonic()\n'
        '    once.write_text(str(started))\n'
        '    time.sleep(2.0)\n'
        '    (shim / "delay-done").write_text(str(time.monotonic() - started))\n'
        'os.execv(os.environ["NATIVE_STOP_GIT"], ["git", *sys.argv[1:]])\n'
    )
    (shim_dir / 'git').write_text(
        '#!/bin/bash\n'
        'if [ -f "$NATIVE_STOP_SHIM/delay-save" ]; then\n'
        '  for arg in "$@"; do\n'
        '    if [ "$arg" = --show-object-format ]; then\n'
        '      exec python3 "$NATIVE_STOP_SHIM/delay.py" "$@"\n'
        '    fi\n'
        '  done\n'
        'fi\n'
        'exec ' + shlex.quote(real_git) + ' "$@"\n'
    )
    (shim_dir / 'git').chmod(0o755)
    provider = base / 'provider.py'
    provider.write_text(r'''import json, os, signal, time
from pathlib import Path

fixture = Path(os.environ['NATIVE_STOP_FIXTURE'])
case = os.environ['NATIVE_STOP_CASE']

def stat(pid):
    raw = open('/proc/%d/stat' % pid, 'rb').read()
    fields = raw[raw.rfind(b')') + 2:].split()
    return {'pid': pid, 'state': fields[0].decode(), 'ppid': int(fields[1]),
            'pgid': int(fields[2]), 'sid': int(fields[3]), 'start': int(fields[19])}

def publish(kind, info):
    path = fixture / ('live-%s.json' % kind)
    temporary = fixture / ('live-%s.json.tmp' % kind)
    temporary.write_text(json.dumps(info))
    os.replace(temporary, path)

def spawn(kind):
    marker = fixture / ('live-%s.json' % kind)
    marker.unlink(missing_ok=True)
    launcher = os.fork()
    if launcher == 0:
        try:
            child = os.fork()
            if child == 0:
                os.setpgrp()
                signal.signal(signal.SIGHUP, signal.SIG_IGN)
                if kind == 'resist':
                    signal.signal(signal.SIGTERM, signal.SIG_IGN)
                    signal.signal(signal.SIGINT, signal.SIG_IGN)
                elif kind == 'coop':
                    def stop(signum, frame):
                        (fixture / 'coop-term').write_text('term\n')
                        os._exit(0)
                    signal.signal(signal.SIGTERM, stop)
                info = stat(os.getpid())
                if info['pgid'] != info['pid'] or info['sid'] == info['pgid']:
                    os._exit(2)
                info.update(kind=kind, launcher=launcher)
                publish(kind, info)
                while True:
                    time.sleep(0.2)
            deadline = time.monotonic() + 2
            while not marker.exists():
                if time.monotonic() > deadline:
                    os._exit(1)
                time.sleep(0.01)
            os._exit(0)
        except Exception:
            os._exit(1)
    _pid, status = os.waitpid(launcher, 0)
    if os.waitstatus_to_exitcode(status) != 0:
        raise SystemExit('launcher failed for ' + kind)
    info = json.loads(marker.read_text())
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        current = stat(info['pid'])
        if current['start'] == info['start'] and current['ppid'] != launcher:
            info['ppid'] = current['ppid']
            info['pgid'] = current['pgid']
            info['sid'] = current['sid']
            info['reparented'] = True
            publish(kind, info)
            return info
        time.sleep(0.02)
    raise SystemExit('not reparented: ' + kind)

def detach():
    marker = fixture / 'live-detached.json'
    marker.unlink(missing_ok=True)
    pid = os.fork()
    if pid == 0:
        os.setsid()
        info = stat(os.getpid())
        info.update(kind='detached', reparented=False, launcher=os.getppid())
        publish('detached', info)
        while True:
            time.sleep(0.2)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if marker.exists():
            return json.loads(marker.read_text())
        time.sleep(0.02)
    raise SystemExit('detached helper did not publish')

ready = {
    'resist': spawn('resist'),
    'coop': spawn('coop'),
    'detached': detach(),
    'provider_pid': os.getpid(),
    'provider_sid': os.getsid(0),
    'provider_pgid': os.getpgrp(),
}
temporary = fixture / 'ready.json.tmp'
temporary.write_text(json.dumps(ready))
os.replace(temporary, fixture / 'ready.json')
if case == 'exit':
    raise SystemExit(7)
if case == 'unknown':
    fault_file = fixture / ('proc-stat-%d' % ready['resist']['pid'])
    fault_file.write_text('1\n')
    raise SystemExit(0)
while True:
    time.sleep(0.2)
''')
    env = dict(os.environ)
    env.update(UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_TIMEOUT='120',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid',
               NATIVE_STOP_FIXTURE=str(fixture), NATIVE_STOP_SHIM=str(shim_dir),
               NATIVE_STOP_GIT=real_git, PATH=str(shim_dir) + os.pathsep + env.get('PATH', ''))
    for key in ('UNIO_SAVE_CAPTURE_TIMEOUT', 'UNIO_SAVE_TEST_FAULT', 'UNIO_TEST_FAULT_DIR', 'BASH_ENV', 'NATIVE_STOP_CASE'):
        env.pop(key, None)
    subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env, check=True, capture_output=True)
    at = str(base / 'bin' / 'unio')
    root = base / 'project with spaces'
    repo = root / 'repo'
    repo.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=repo, env=env, check=True)
    (repo / 'tracked').write_text('base\n')
    subprocess.run(['git', 'add', 'tracked'], cwd=repo, env=env, check=True)
    subprocess.run(['git', 'commit', '-qm', 'base'], cwd=repo, env=env, check=True)
    subprocess.run([at, 'init', 'mock'], cwd=repo, env=env, check=True, capture_output=True, timeout=90)
    (base / 'conf' / 'agents.conf').write_text('mock=python3 ' + shlex.quote(str(provider)) + '\n')
    subprocess.run([at, 'tier', 'low'], cwd=repo, env=env, check=True, capture_output=True)
    subprocess.run([at, 'lead', 'none'], cwd=repo, env=env, check=True, capture_output=True)
    tasks = root / 'coord' / 'tasks'
    for name in ('kill-task', 'exit-task', 'save-task', 'term-task', 'refuse-task', 'unknown-task'):
        (tasks / (name + '.md')).write_text('# Offline fixture ' + name + '\n')

    exact = []
    shells = []

    def remember(pid, start, kind):
        exact.append({'pid': pid, 'start': start, 'kind': kind})

    sibling = subprocess.Popen(['sleep', '180'])
    outsider = subprocess.Popen(['sleep', '180'], start_new_session=True)
    sibling_start = proc_stat(sibling.pid)['start']
    outsider_start = proc_stat(outsider.pid)['start']
    remember(sibling.pid, sibling_start, 'sibling')
    remember(outsider.pid, outsider_start, 'outsider')

    def cleanup():
        for item in list(shells):
            kill_recorded_tree(item['pid'], item['start'])
        for item in list(exact):
            kill_exact(item['pid'], item['start'])
        for proc in (sibling, outsider):
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def worker_held():
        lock = root / 'coord' / '.locks' / 'mock.lock'
        if not lock.exists():
            return False
        handle = os.open(lock, os.O_RDWR)
        try:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            fcntl.flock(handle, fcntl.LOCK_UN)
            return False
        finally:
            os.close(handle)

    def account_held():
        result = subprocess.run([at, 'policy', '--json'], cwd=repo, env=env,
                                capture_output=True, text=True, timeout=15)
        if result.returncode != 0:
            return True
        active = json.loads(result.stdout).get('active_native_workflows') or {}
        return any(value for value in active.values())

    def wait_ready(seconds=45):
        path = fixture / 'ready.json'
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if path.exists():
                return json.loads(path.read_text())
            time.sleep(0.05)
        raise AssertionError('provider fixture did not become ready')

    def note_ready(ready):
        for kind in ('resist', 'coop', 'detached'):
            info = ready[kind]
            remember(info['pid'], info['start'], kind)
        leader = proc_stat(ready['provider_sid'])
        if leader is not None:
            remember(leader['pid'], leader['start'], 'provider-session')
        provider = proc_stat(ready['provider_pid'])
        if provider is not None:
            remember(ready['provider_pid'], provider['start'], 'provider')

    def survivors():
        lines = []
        for item in exact:
            lines.append('%s %s' % (item['kind'], proc_stat(item['pid'])))
        return '\n'.join(lines)

    try:
        # Public kill of a background run whose helper left the timeout group
        # and was reparented when its launcher exited.
        env['NATIVE_STOP_CASE'] = 'kill'
        for stale in ('ready.json', 'coop-term', 'live-resist.json', 'live-coop.json', 'live-detached.json'):
            (fixture / stale).unlink(missing_ok=True)
        started = subprocess.run([at, 'run', '-b', 'mock', 'kill-task'], cwd=repo, env=env,
                                 capture_output=True, text=True, timeout=30)
        check('background run starts', started.returncode == 0 and 'started in background' in started.stdout,
              started.stdout + started.stderr)
        ready = wait_ready()
        note_ready(ready)
        pidfile = root / 'coord' / 'reports' / 'kill-task.pid'
        shell_pid = int(pidfile.read_text().strip())
        shell = proc_stat(shell_pid)
        shells.append({'pid': shell_pid, 'start': shell['start']})
        resist, coop, detached = ready['resist'], ready['coop'], ready['detached']
        check('helper is in another group of the provider session and reparented',
              resist['reparented'] and resist['pgid'] == resist['pid']
              and resist['sid'] == ready['provider_sid'] and resist['pgid'] != ready['provider_pgid']
              and resist['ppid'] != resist['launcher'] and same_process(resist['pid'], resist['start']),
              json.dumps(ready, indent=2))
        check('run owns the worker while the descendant is live',
              worker_held() and account_held() and same_process(resist['pid'], resist['start']))
        killer = subprocess.Popen([at, 'kill', 'kill-task'], cwd=repo, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        saw_held = False
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and killer.poll() is None:
            if same_process(resist['pid'], resist['start']) and worker_held() and account_held():
                saw_held = True
                break
            time.sleep(0.05)
        try:
            out, err = killer.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            kill_recorded_tree(killer.pid, proc_stat(killer.pid)['start'])
            out, err = killer.communicate(timeout=5)
            check('public kill returned', False, out + err + '\n' + survivors())
        detail = 'exit %s\n%s\n%s\nheld_while_alive=%s\n%s' % (
            killer.returncode, out, err, saw_held, survivors())
        check('worker stayed occupied while the owned descendant was alive', saw_held, detail)
        check('public kill stopped the reparented TERM-resistant descendant',
              not same_process(resist['pid'], resist['start']), detail)
        check('public kill stopped the cooperative descendant with TERM',
              (fixture / 'coop-term').is_file() and not same_process(coop['pid'], coop['start']), detail)
        check('deliberately detached helper is outside the owned session',
              detached['sid'] != ready['provider_sid'] and detached['sid'] == detached['pid'], detail)
        check('detached helper and unrelated processes survived public kill',
              same_process(detached['pid'], detached['start'])
              and same_process(sibling.pid, sibling_start)
              and same_process(outsider.pid, outsider_start), detail)
        check('worker and account are free only after owned descendants are gone',
              not worker_held() and not account_held() and not pidfile.exists(), detail)

        # Natural provider exit must reap the same owned descendants.
        env['NATIVE_STOP_CASE'] = 'exit'
        for stale in ('ready.json', 'coop-term'):
            (fixture / stale).unlink(missing_ok=True)
        (fixture / 'coop-term').unlink(missing_ok=True)
        finished = subprocess.run([at, 'run', 'mock', 'exit-task'], cwd=repo, env=env,
                                  capture_output=True, text=True, timeout=40)
        ready = json.loads((fixture / 'ready.json').read_text())
        note_ready(ready)
        detail = 'exit %s\n%s\n%s\n%s' % (finished.returncode, finished.stdout, finished.stderr, survivors())
        check('natural provider exit keeps its own status', finished.returncode == 7, detail)
        check('natural exit reaps the reparented descendant',
              not same_process(ready['resist']['pid'], ready['resist']['start']), detail)
        check('natural exit delivers TERM to the cooperative descendant',
              (fixture / 'coop-term').is_file()
              and not same_process(ready['coop']['pid'], ready['coop']['start']), detail)
        check('natural exit leaves the detached helper and unrelated processes',
              same_process(ready['detached']['pid'], ready['detached']['start'])
              and same_process(sibling.pid, sibling_start)
              and same_process(outsider.pid, outsider_start), detail)
        check('natural exit releases the worker only after owned cleanup',
              not worker_held() and not account_held(), detail)

        # Cancellation during the final save must not skip that save's budget.
        env['NATIVE_STOP_CASE'] = 'kill'
        for stale in ('ready.json', 'coop-term', 'delayed', 'delay-done'):
            (fixture / stale).unlink(missing_ok=True)
        (shim_dir / 'delayed').unlink(missing_ok=True)
        (shim_dir / 'delay-done').unlink(missing_ok=True)
        started = subprocess.run([at, 'run', '-b', 'mock', 'save-task'], cwd=repo, env=env,
                                 capture_output=True, text=True, timeout=30)
        check('save-case background run starts', started.returncode == 0, started.stdout + started.stderr)
        ready = wait_ready()
        note_ready(ready)
        shell_pid = int((root / 'coord' / 'reports' / 'save-task.pid').read_text().strip())
        shells.append({'pid': shell_pid, 'start': proc_stat(shell_pid)['start']})
        (shim_dir / 'delay-save').write_text('1\n')
        saved = subprocess.run([at, 'kill', 'save-task'], cwd=repo, env=env,
                               capture_output=True, text=True, timeout=40)
        elapsed = None
        if (shim_dir / 'delay-done').exists():
            elapsed = float((shim_dir / 'delay-done').read_text())
        detail = 'exit %s elapsed %s\n%s\n%s\n%s' % (
            saved.returncode, elapsed, saved.stdout, saved.stderr, survivors())
        check('final save finished its bounded attempt after cancellation',
              elapsed is not None and elapsed >= 1.5, detail)
        check('cancellation still stopped the owned descendant',
              not same_process(ready['resist']['pid'], ready['resist']['start'])
              and not worker_held() and not account_held(), detail)
        (shim_dir / 'delay-save').unlink(missing_ok=True)

        # A TERM delivered straight to the background shell must reach the
        # supervisor through the pidfd route and reap the owned session
        # before the worker and the account are released.
        env['NATIVE_STOP_CASE'] = 'kill'
        for stale in ('ready.json', 'coop-term'):
            (fixture / stale).unlink(missing_ok=True)
        started = subprocess.run([at, 'run', '-b', 'mock', 'term-task'], cwd=repo, env=env,
                                 capture_output=True, text=True, timeout=30)
        check('term-case background run starts', started.returncode == 0, started.stdout + started.stderr)
        ready = wait_ready()
        note_ready(ready)
        shell_pid = int((root / 'coord' / 'reports' / 'term-task.pid').read_text().strip())
        shell = proc_stat(shell_pid)
        shells.append({'pid': shell_pid, 'start': shell['start']})
        resist, coop, detached = ready['resist'], ready['coop'], ready['detached']
        os.kill(shell_pid, signal.SIGTERM)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and same_process(shell_pid, shell['start']):
            time.sleep(0.1)
        detail = 'shell gone=%s\n%s' % (not same_process(shell_pid, shell['start']), survivors())
        check('direct TERM stopped the background shell',
              not same_process(shell_pid, shell['start']), detail)
        check('direct TERM reaped the reparented descendant via the pidfd route',
              not same_process(resist['pid'], resist['start']), detail)
        check('direct TERM delivered TERM to the cooperative descendant',
              (fixture / 'coop-term').is_file() and not same_process(coop['pid'], coop['start']), detail)
        check('direct TERM leaves the detached helper and unrelated processes',
              same_process(detached['pid'], detached['start'])
              and same_process(sibling.pid, sibling_start)
              and same_process(outsider.pid, outsider_start), detail)
        check('direct TERM releases the worker only after owned cleanup',
              not worker_held() and not account_held()
              and not (root / 'coord' / 'reports' / 'term-task.pid').exists(), detail)

        # Cleanup Unknown before final capture: the supervisor must prove owned
        # cleanup clear before any final capture. The regression synchronizes on
        # the supervisor's own Unknown verdict, not on provider readiness, and
        # proves no final save attempt can occur until recovery removes the
        # unproved identity marker.
        env['NATIVE_STOP_CASE'] = 'unknown'
        env['UNIO_TEST_FAULT_DIR'] = str(fixture)
        for stale in ('ready.json', 'coop-term'):
            (fixture / stale).unlink(missing_ok=True)
        run_out = base / 'unknown-run.out'
        run_err = base / 'unknown-run.err'
        with open(run_out, 'wb') as out_stream, open(run_err, 'wb') as err_stream:
            unknown_run = subprocess.Popen([at, 'run', 'mock', 'unknown-task'], cwd=repo, env=env,
                                           stdout=out_stream, stderr=err_stream)
        shells.append({'pid': unknown_run.pid, 'start': proc_stat(unknown_run.pid)['start']})
        ready = wait_ready()
        note_ready(ready)
        resist, coop, detached = ready['resist'], ready['coop'], ready['detached']
        fault_marker = fixture / ('proc-stat-%d' % resist['pid'])
        attempt_file = root / 'coord' / 'saves' / 'attempts' / 'mock.json'

        def unknown_attempt():
            if not attempt_file.exists():
                return {}
            try:
                doc = json.loads(attempt_file.read_text())
            except (OSError, ValueError):
                return {}
            return doc if doc.get('task') == 'unknown-task' else {}

        # Synchronize on the actual cleanup state: the supervisor must report
        # owned cleanup Unknown while the owned descendant is still live.
        deadline = time.monotonic() + 30
        note = ''
        while time.monotonic() < deadline:
            text = run_err.read_text(errors='replace')
            lines = [line for line in text.splitlines() if 'owned cleanup Unknown' in line]
            if lines:
                note = lines[0]
                break
            if unknown_run.poll() is not None:
                break
            time.sleep(0.05)
        detail = 'note=%r run_alive=%s resist=%s attempt=%s' % (
            note, unknown_run.poll() is None, same_process(resist['pid'], resist['start']),
            unknown_attempt().get('reason'))
        check('unproved owned descendant keeps cleanup Unknown and holds slots',
              'owned cleanup Unknown' in note and unknown_run.poll() is None
              and same_process(resist['pid'], resist['start'])
              and worker_held() and account_held(), detail)

        # The supervisor is provably in the Unknown cleanup loop now. Watch for
        # a guard violation: any final save attempt for this task, or the run
        # completing, while the owned descendant is still live and unproved.
        violation = ''
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            attempt = unknown_attempt()
            if attempt.get('reason') == 'final':
                violation = 'final save attempted while owned cleanup was Unknown'
                break
            if unknown_run.poll() is not None:
                violation = 'run completed while owned cleanup was Unknown'
                break
            time.sleep(0.05)
        detail = 'violation=%r run_alive=%s resist=%s worker_held=%s account_held=%s attempt=%s' % (
            violation, unknown_run.poll() is None, same_process(resist['pid'], resist['start']),
            worker_held(), account_held(), unknown_attempt().get('reason'))
        check('final save not attempted while owned cleanup is Unknown',
              violation == '' and same_process(resist['pid'], resist['start']), detail)

        # Recovery: remove the fault injection so cleanup can be proved clear.
        fault_marker.unlink(missing_ok=True)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and unknown_run.poll() is None:
            time.sleep(0.05)
        final_attempt = unknown_attempt()
        recovery_detail = ('exit=%s resist=%s coop=%s worker_held=%s account_held=%s own=%s reason=%s\n%s\n%s'
                          % (unknown_run.returncode, same_process(resist['pid'], resist['start']),
                             same_process(coop['pid'], coop['start']), worker_held(), account_held(),
                             (root / 'coord' / 'reports' / 'unknown-task.own').exists(),
                             final_attempt.get('reason'),
                             run_out.read_text(errors='replace'), run_err.read_text(errors='replace')))
        check('recovery establishes clear cleanup and completes run',
              unknown_run.poll() is not None and unknown_run.returncode == 0, recovery_detail)
        check('recovery reaps the owned descendant',
              not same_process(resist['pid'], resist['start'])
              and not same_process(coop['pid'], coop['start'])
              and (fixture / 'coop-term').is_file(), recovery_detail)
        check('recovery releases worker and account only after clear cleanup',
              not worker_held() and not account_held()
              and not (root / 'coord' / 'reports' / 'unknown-task.own').exists(), recovery_detail)
        check('final save captured after proved cleanup with provider status',
              final_attempt.get('reason') == 'final' and final_attempt.get('provider_exit') == 0, recovery_detail)
        check('unrelated processes survived recovery',
              same_process(detached['pid'], detached['start'])
              and same_process(sibling.pid, sibling_start)
              and same_process(outsider.pid, outsider_start), recovery_detail)
        env.pop('UNIO_TEST_FAULT_DIR', None)

        # A live run with corrupted ownership must not be signaled.
        env['NATIVE_STOP_CASE'] = 'kill'
        (fixture / 'ready.json').unlink(missing_ok=True)
        started = subprocess.run([at, 'run', '-b', 'mock', 'refuse-task'], cwd=repo, env=env,
                                 capture_output=True, text=True, timeout=30)
        check('refuse-case background run starts', started.returncode == 0, started.stdout + started.stderr)
        ready = wait_ready()
        note_ready(ready)
        own = root / 'coord' / 'reports' / 'refuse-task.own'
        pidfile = root / 'coord' / 'reports' / 'refuse-task.pid'
        shell_pid = int(pidfile.read_text().strip())
        shell = proc_stat(shell_pid)
        shells.append({'pid': shell_pid, 'start': shell['start']})
        resist = ready['resist']
        original = own.read_text() if own.exists() else ''
        own.write_text('{')
        refused = subprocess.run([at, 'kill', 'refuse-task'], cwd=repo, env=env,
                                 capture_output=True, text=True, timeout=15)
        detail = 'exit %s\n%s\n%s' % (refused.returncode, refused.stdout, refused.stderr)
        check('malformed ownership is not signaled',
              refused.returncode != 0 and pidfile.read_text().strip() == str(shell_pid)
              and same_process(shell_pid, shell['start'])
              and same_process(resist['pid'], resist['start'])
              and same_process(sibling.pid, sibling_start), detail)
        if original:
            own.write_text(original)
            doc = json.loads(original)
            doc['shell_start'] = doc['shell_start'] + 1
            own.write_text(json.dumps(doc))
            refused = subprocess.run([at, 'kill', 'refuse-task'], cwd=repo, env=env,
                                     capture_output=True, text=True, timeout=15)
            detail = 'exit %s\n%s\n%s' % (refused.returncode, refused.stdout, refused.stderr)
            check('reused start identity is not signaled',
                  refused.returncode != 0 and same_process(shell_pid, shell['start'])
                  and same_process(resist['pid'], resist['start'])
                  and pidfile.exists(), detail)
            # Each remaining identity defect keeps the exact supported shape
            # except for one field, so only that field's validation can refuse.
            tampering = (
                ('boolean schema_version is refused as an identity record', 'schema_version', True),
                ('stale boot identity is refused', 'boot_id', '00000000-0000-0000-0000-000000000000'),
                ('string pid type is refused', 'shell_pid', str(shell_pid)),
            )
            for label, field, bad in tampering:
                own.write_text(original)
                doc = json.loads(original)
                doc[field] = bad
                own.write_text(json.dumps(doc))
                refused = subprocess.run([at, 'kill', 'refuse-task'], cwd=repo, env=env,
                                         capture_output=True, text=True, timeout=15)
                detail = 'exit %s\n%s\n%s' % (refused.returncode, refused.stdout, refused.stderr)
                check(label,
                      refused.returncode != 0 and same_process(shell_pid, shell['start'])
                      and same_process(resist['pid'], resist['start'])
                      and pidfile.exists(), detail)
            own.write_text(original)
        else:
            check('ownership file exists before the provider is killable', False, 'no .own file')

        # The shell helper that feeds identity checks must split /proc stat at
        # the last ')': a comm that itself contains ')' must not shift fields.
        paren = subprocess.Popen(
            [sys.executable, '-c',
             'import ctypes, time\n'
             'ctypes.CDLL(None).prctl(15, b"mock)comm")\n'
             'time.sleep(300)\n'])
        remember(paren.pid, proc_stat(paren.pid)['start'], 'paren-comm')
        comm = ''
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                comm = Path('/proc/%d/comm' % paren.pid).read_text().strip()
            except OSError:
                comm = ''
            if ')' in comm:
                break
            time.sleep(0.05)
        info = proc_stat(paren.pid)
        script = (base / 'bin' / 'unio').read_text()
        begin = script.index('policy_stat_field() {')
        end = script.index('\n}', begin) + 2
        probe = subprocess.run(
            ['bash', '-c', script[begin:end] + '\npolicy_stat_field "$1" 20\npolicy_stat_field "$1" 1\n',
             'bash', str(paren.pid)], capture_output=True, text=True, timeout=10)
        fields = probe.stdout.split()
        check('parenthesised comm does not shift stat fields',
              ')' in comm and len(fields) >= 2
              and fields[0] == str(info['start']) and fields[1] == info['state'],
              'comm=%r out=%r expected start=%s state=%s' % (
                  comm, probe.stdout, info['start'], info['state']))
        print('native stop: %d checks passed' % passed)
    finally:
        cleanup()
