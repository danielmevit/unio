#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Offline native supervision: real exits, saves, restore, signals and ownership.

One real two-minute run proves unchanged periodic deduplication followed by a
changed periodic capture. Other providers finish immediately or are interrupted.
No live providers, fake timing interval, global install or external dependency.
"""
import fcntl
import json
import os
import re
import shlex
import signal
import stat
import subprocess
import tempfile
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('  ok ' + label, flush=True)


def until(predicate, seconds=40):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(0.1)
    raise AssertionError('timed out waiting for fixture evidence')


with tempfile.TemporaryDirectory(prefix='auto-saving-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_TIMEOUT='240',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0', GIT_OPTIONAL_LOCKS='0',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    env.pop('UNIO_SAVE_TEST_FAULT', None)
    env.pop('UNIO_SAVE_CAPTURE_TIMEOUT', None)  # These suites assert default compatibility.
    subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env, check=True, capture_output=True)
    at = str(base / 'bin' / 'unio')
    root = base / 'project with spaces'
    repo = root / 'repo'
    repo.mkdir(parents=True)

    def git(cwd, *args):
        return subprocess.check_output(['git', *args], cwd=cwd, env=env, stderr=subprocess.DEVNULL)

    def unio(*args, extra=None, timeout=90):
        return subprocess.run([at, *args], cwd=repo, env=dict(env, **(extra or {})),
                              capture_output=True, text=True, timeout=timeout)

    def launch(worker, task, extra=None):
        return subprocess.Popen([at, 'run', worker, task], cwd=repo, env=dict(env, **(extra or {})),
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    git(repo, 'init', '-q', '-b', 'main')
    (repo / 'tracked').write_text('base\n')
    (repo / 'deleted').write_text('will disappear\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-qm', 'base')
    scenarios = ['mixed', 'success', 'timeout', 'term', 'refuse', 'crash', 'kill', 'launch', 'periodic']
    workers = ['mock-' + s for s in scenarios] + ['mock-restore', 'mock-periodic-restore']
    check('initialize real native worktrees', unio('init', *workers).returncode == 0)
    coord, wt = root / 'coord', root / 'wt'
    calls = base / 'calls'
    provider = base / 'provider.py'
    provider.write_text(r'''
import json, os, subprocess, time
from pathlib import Path
root = Path(os.environ['AUTO_ROOT'])
scenario = os.environ['AUTO_CASE']
calls = Path(os.environ['AUTO_CALLS'])
with calls.open('a') as out: out.write(scenario + '\n')
fds = []
for f in Path('/proc/self/fd').iterdir():
    try: fds.append(os.readlink(f))
    except OSError: pass
(root / (scenario + '-fds.json')).write_text(json.dumps(fds))
lineage, pid = [], os.getpid()
for _ in range(4):
    lineage.append(pid)
    pid = int(Path('/proc/%d/status' % pid).read_text().split('PPid:\t')[1].splitlines()[0])
(root / (scenario + '-pids.json')).write_text(json.dumps(lineage))
Path('tracked').write_text('staged\n')
subprocess.run(['git', 'add', 'tracked'], check=True)
Path('tracked').write_text('unstaged\n')
Path('deleted').unlink()
Path('binary').write_bytes(b'\0\xff\x01')
Path('empty').touch()
Path('executable').write_text('#!/bin/sh\nexit 0\n')
Path('executable').chmod(0o755)
(root / (scenario + '-started')).touch()
if scenario == 'refuse': Path('.env').write_text('secret fixture\n')
if scenario == 'periodic':
    # Wait for the test to inspect a real changed and unchanged periodic check.
    while not (root / 'periodic-finish').exists(): time.sleep(0.1)
if scenario in ('timeout', 'term', 'kill'):
    while True: time.sleep(1)
raise SystemExit(0 if scenario == 'success' else 23)
''')
    (base / 'conf' / 'agents.conf').write_text('mock=python3 ' + shlex.quote(str(provider)) + '\n')
    env.update(AUTO_ROOT=str(base), AUTO_CALLS=str(calls))
    for s in scenarios:
        (coord / 'tasks' / (s + '.md')).write_text('# ' + s + '\nKeep unfinished work.\n')

    def saves(worker):
        store = coord / 'saves'
        docs = []
        if store.exists():
            for p in store.iterdir():
                if re.fullmatch('[0-9a-f]{32}', p.name):
                    d = json.loads((p / 'manifest.json').read_text())
                    if d['worker'] == worker:
                        docs.append(d)
        return sorted(docs, key=lambda d: d['published_at'])

    def result(worker, task):
        return json.loads(unio('result', worker, task).stdout)

    def view(path):
        names = set(git(path, 'ls-files', '-c', '-o', '--exclude-standard', '-z').split(b'\0'))
        files = {}
        for name in names - {b''}:
            p = path / os.fsdecode(name)
            if p.exists():
                files[name] = (stat.S_IMODE(p.stat().st_mode), p.read_bytes())
        return git(path, 'rev-parse', 'HEAD'), git(path, 'ls-files', '-s', '-z'), files

    def released(worker, scenario):
        with (coord / '.locks' / (worker + '.lock')).open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        policy = json.loads(unio('policy', '--json').stdout)
        check(scenario + ' releases native worker and account ownership',
              not policy['active_native_workflows'])
        fds = json.loads((base / (scenario + '-fds.json')).read_text())
        check(scenario + ' provider inherits no worker or control descriptors',
              not any('/coord/.locks/' in p for p in fds))
        def live(pid):
            try:
                return Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()[0] != 'Z'
            except FileNotFoundError:
                return False
        pids = json.loads((base / (scenario + '-pids.json')).read_text())
        check(scenario + ' owned provider, timeout, supervisor and run processes are reaped',
              all(not live(pid) for pid in pids))

    check('resume before native runs', unio('resume').returncode == 0)
    try:
        for scenario, code in [('mixed', 23), ('success', 0), ('timeout', 124), ('term', 143)]:
            worker = 'mock-' + scenario
            extra = dict(AUTO_CASE=scenario)
            if scenario == 'timeout':
                extra['UNIO_TIMEOUT'] = '1'
            if scenario == 'term':
                proc = launch(worker, scenario, extra)
                until(lambda: (base / 'term-started').exists())
                proc.send_signal(signal.SIGTERM)
                stdout, stderr = proc.communicate(timeout=70)
                actual = proc.returncode
            else:
                run = unio('run', worker, scenario, extra=extra)
                actual, stdout, stderr = run.returncode, run.stdout, run.stderr
            check(scenario + ' preserves real native exit: ' + stdout[-80:] + stderr[-80:], actual == code)
            docs = saves(worker)
            check(scenario + ' captures baseline and final without an AI answer',
                  [d['reason'] for d in docs] == ['baseline', 'final' if code == 0 else 'final-failure'])
            attempt = json.loads((coord / 'retries' / scenario / 'state.json').read_text())['latest'][worker]
            check(scenario + ' binds actual attempt and exit',
                  all(d['run_id'] == attempt['id'] for d in docs) and docs[-1]['provider_exit'] == code)
            r = result(worker, scenario)
            check(scenario + ' structured process receipt preserves exit', r['process']['exit_code'] == code)
            released(worker, scenario)
            if scenario == 'mixed':
                before = view(wt / worker)
                restored = unio('save', 'restore', docs[-1]['save_id'], 'mock-restore')
                check('final-failure restores exact index and working bytes/modes',
                      restored.returncode == 0 and view(wt / 'mock-restore') == before)
                check('staged/unstaged divergence, deletion, binary, empty and executable really restored',
                      git(wt / 'mock-restore', 'show', ':tracked') == b'staged\n'
                      and (wt / 'mock-restore' / 'tracked').read_bytes() == b'unstaged\n'
                      and not (wt / 'mock-restore' / 'deleted').exists()
                      and (wt / 'mock-restore' / 'binary').read_bytes() == b'\0\xff\x01'
                      and (wt / 'mock-restore' / 'empty').read_bytes() == b''
                      and (wt / 'mock-restore' / 'executable').stat().st_mode & 0o111)

        run = unio('run', 'mock-refuse', 'refuse', extra=dict(AUTO_CASE='refuse'))
        docs = saves('mock-refuse')
        attempt = json.loads((coord / 'saves' / 'attempts' / 'mock-refuse.json').read_text())
        check('refused final retains baseline and actual provider failure',
              run.returncode == 23 and len(docs) == 1 and docs[0]['reason'] == 'baseline'
              and attempt['reason'] == 'secret_name' and attempt['provider_exit'] == 23
              and attempt['last_good_id'] == docs[0]['save_id'])
        released('mock-refuse', 'refuse')

        manual = unio('save', 'create', 'mock-crash', 'crash')
        check('prepare prior good save for capture-crash case', manual.returncode == 0)
        good = saves('mock-crash')[0]['save_id']
        run = unio('run', 'mock-crash', 'crash',
                   extra=dict(AUTO_CASE='crash', UNIO_SAVE_TEST_FAULT='publish-interrupt'))
        attempt = json.loads((coord / 'saves' / 'attempts' / 'mock-crash.json').read_text())
        check('crashed baseline/final helpers never prevent provider execution or erase prior save',
              run.returncode == 23 and [d['save_id'] for d in saves('mock-crash')] == [good]
              and attempt['status'] == 'failed' and attempt['provider_exit'] == 23
              and attempt['last_good_id'] == good)
        released('mock-crash', 'crash')

        started = unio('run', '-b', 'mock-kill', 'kill', extra=dict(AUTO_CASE='kill'))
        check('start a real native background run', started.returncode == 0)
        until(lambda: (base / 'kill-started').exists())
        with (coord / '.locks' / 'saves.lock').open('r+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            killer = subprocess.Popen([at, 'kill', 'kill'], cwd=repo, env=env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            time.sleep(2)
            check('public kill allows final-save contention beyond the old one-second cutoff', killer.poll() is None)
            fcntl.flock(lock, fcntl.LOCK_UN)
        stdout, stderr = killer.communicate(timeout=90)
        docs = saves('mock-kill')
        check('public background kill preserves final save and structured exit143',
              killer.returncode == 0 and docs[-1]['reason'] == 'final-failure'
              and docs[-1]['provider_exit'] == 143
              and result('mock-kill', 'kill')['process']['exit_code'] == 143
              and not (coord / 'reports' / 'kill.pid').exists())
        released('mock-kill', 'kill')

        check('prepare prior good save for capture-start failure',
              unio('save', 'create', 'mock-launch', 'launch').returncode == 0)
        good = saves('mock-launch')[0]['save_id']
        run = unio('run', 'mock-launch', 'launch',
                   extra=dict(AUTO_CASE='launch', UNIO_SAVE_TEST_FAULT='capture-launch'))
        attempt = json.loads((coord / 'saves' / 'attempts' / 'mock-launch.json').read_text())
        check('capture-start exception does not prevent dispatch or erase prior good evidence',
              run.returncode == 23 and [d['save_id'] for d in saves('mock-launch')] == [good]
              and attempt['status'] == 'failed' and attempt['provider_exit'] == 23
              and attempt['last_good_id'] == good)
        released('mock-launch', 'launch')

        proc = launch('mock-periodic', 'periodic', dict(AUTO_CASE='periodic'))
        until(lambda: any(d['reason'] == 'periodic' for d in saves('mock-periodic')), 120)
        docs = saves('mock-periodic')
        check('real sixty-second timer saves changed work before provider exits',
              proc.poll() is None and [d['reason'] for d in docs] == ['baseline', 'periodic'])
        periodic_id = docs[-1]['save_id']
        os.set_blocking(proc.stdout.fileno(), False)
        observed = bytearray()

        def unchanged():
            try:
                observed.extend(os.read(proc.stdout.fileno(), 65536))
            except BlockingIOError:
                pass
            return b'periodic state unchanged; keeping save ' in observed

        until(unchanged, 110)
        os.set_blocking(proc.stdout.fileno(), True)
        check('unchanged next periodic check creates no duplicate save',
              [d['save_id'] for d in saves('mock-periodic')] == [d['save_id'] for d in docs])
        (base / 'periodic-finish').touch()
        stdout, stderr = proc.communicate(timeout=70)
        check('periodic supervision preserves final exit and separate final evidence',
              proc.returncode == 23 and saves('mock-periodic')[-1]['reason'] == 'final-failure'
              and saves('mock-periodic')[-1]['provider_exit'] == 23)
        check('periodic checkpoint independently restores exact unfinished state',
              unio('save', 'restore', periodic_id, 'mock-periodic-restore').returncode == 0
              and view(wt / 'mock-periodic-restore') == view(wt / 'mock-periodic'))
        released('mock-periodic', 'periodic')
        check('exactly one provider invocation per frozen task, no retries',
              calls.read_text().splitlines() == scenarios)
    finally:
        if 'killer' in locals() and killer.poll() is None:
            killer.communicate(timeout=90)
        if (coord / 'reports' / 'kill.pid').exists():
            unio('kill', 'kill', timeout=90)
        if 'proc' in locals() and proc.poll() is None:
            proc.terminate()
            proc.communicate(timeout=70)
        check('stop after native runs', unio('stop').returncode == 0 and (coord / 'STOP').exists())

print('automatic work saving: %d checks passed' % passed)
