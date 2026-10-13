#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Actual manual/native capture budgets with offline, private fixtures.

A Git shim delays one real observation per helper or sends a real signal to
that helper. Production clocks, capture code, admission and cleanup are intact.
The long cases exercise the real sixty-second periodic interval and the original
thirty-second final-cancellation cleanup ceiling.
No provider/model/network call, global install or inherited capture setting.
"""
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import types
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('  ok ' + label, flush=True)


def until(predicate, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(0.05)
    raise AssertionError('timed out waiting for fixture evidence')


# One-second fixtures use native temporary storage, independently of a mounted
# Windows TMPDIR. The comparable populated-store measurement is separate.
with tempfile.TemporaryDirectory(prefix='save-capture-budget-', dir='/tmp') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_TIMEOUT='120',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0', GIT_OPTIONAL_LOCKS='0',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    for key in ('UNIO_SAVE_CAPTURE_TIMEOUT', 'UNIO_SAVE_TEST_FAULT', 'BASH_ENV', 'BUDGET_GATE'):
        env.pop(key, None)
    subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env, check=True, capture_output=True)
    at = str(base / 'bin' / 'unio')
    root, repo = base / 'project with spaces', base / 'project with spaces' / 'repo'
    repo.mkdir(parents=True)

    def git(cwd, *args):
        return subprocess.check_output(['git', *args], cwd=cwd, env=env, stderr=subprocess.DEVNULL)

    def unio(*args, extra=None, timeout=25):
        return subprocess.run([at, *args], cwd=repo, env=dict(env, **(extra or {})),
                              capture_output=True, text=True, timeout=timeout)

    def good(result):
        assert result.returncode == 0, result.stdout + result.stderr
        return result

    git(repo, 'init', '-q', '-b', 'main')
    (repo / 'tracked').write_text('base\n')
    git(repo, 'add', 'tracked')
    git(repo, 'commit', '-qm', 'base')
    workers = ['mock-' + name for name in
               ('manual', 'dest', 'default', 'short', 'long', 'deadline', 'external',
                'crash', 'source-kill', 'invalid', 'cancel', 'cancel-final', 'periodic')]
    good(unio('init', *workers, timeout=120))
    coord, wt = root / 'coord', root / 'wt'
    for name in workers:
        (coord / 'tasks' / (name + '.md')).write_text('# Offline fixture ' + name + '\n')

    calls = base / 'calls'
    provider = base / 'mock-provider.py'
    provider.write_text('''import os, time
from pathlib import Path
base = Path(os.environ['BUDGET_FIXTURE'])
case = Path.cwd().name
with (base / 'calls').open('a') as out: out.write(case + '\\n')
Path('tracked').write_text('unfinished ' + case + '\\n')
(base / (case + '-started')).touch()
if case == 'mock-periodic':
    while not (base / 'periodic-finish').exists(): time.sleep(0.05)
raise SystemExit(137 if case == 'mock-source-kill' else 23)
''')
    (base / 'conf' / 'agents.conf').write_text('mock=python3 ' + shlex.quote(str(provider)) + '\n')
    env['BUDGET_FIXTURE'] = str(base)
    # Only the save helper uses --show-object-format; native pre/postflight and
    # provider Git operations pass straight through. All actual Git bytes remain.
    shim_dir = base / 'git-shim'
    shim_dir.mkdir()
    shim = shim_dir / 'git'
    real_git = shutil.which('git')
    shim.write_text('#!/usr/bin/env python3\n' + '''import json, os, signal, sys, time
from pathlib import Path
gate = os.environ.get('BUDGET_GATE')
if gate and '--show-object-format' in sys.argv:
    gate = Path(gate)
    helper = os.getppid()
    claim = gate / (str(helper) + '.claimed')
    try:
        fd = os.open(claim, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        fd = None
    if fd is not None:
        os.close(fd)
        mode = (gate / 'mode').read_text().strip()
        if mode == 'stop-final':
            mode = 'stop' if (Path(os.environ['BUDGET_FIXTURE']) / 'mock-cancel-final-started').exists() else 'pass'
        if mode == 'stop-first':
            try:
                fd = os.open(gate / 'first', os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
                mode = 'stop'
            except FileExistsError:
                mode = 'pass'
        if mode in ('stop', 'kill'):
            os.kill(helper, signal.SIGSTOP if mode == 'stop' else signal.SIGKILL)
        evidence = gate / (str(helper) + '.json')
        temporary = gate / (str(helper) + '.json.tmp')
        temporary.write_text(json.dumps(dict(
            helper=helper, shim=os.getpid(), mode=mode, at=time.monotonic())))
        temporary.replace(evidence)
        if mode == 'delay': time.sleep(1.4)
os.execv(''' + repr(real_git) + ''', ['git', *sys.argv[1:]])
''')
    shim_payload = shim_dir / 'git-fixture.py'
    shim_payload.write_text(shim.read_text())
    shim.write_text('#!/usr/bin/env bash\n'
                    + 'if [ -n "${BUDGET_GATE:-}" ]; then\n'
                    + '  for arg in "$@"; do\n'
                    + '    if [ "$arg" = --show-object-format ]; then exec python3 '
                    + shlex.quote(str(shim_payload)) + ' "$@"; fi\n'
                    + '  done\nfi\nexec ' + shlex.quote(real_git) + ' "$@"\n')
    shim.chmod(0o755)
    env['PATH'] = str(shim_dir) + os.pathsep + env['PATH']

    def gate(name, mode):
        path = base / ('gate-' + name)
        path.mkdir()
        (path / 'mode').write_text(mode)
        return path

    def events(path):
        return [json.loads(p.read_text()) for p in path.glob('*.json')]

    def saves(worker):
        store = coord / 'saves'
        docs = [json.loads((p / 'manifest.json').read_text()) for p in store.iterdir()
                if re.fullmatch('[0-9a-f]{32}', p.name)] if store.exists() else []
        return sorted((d for d in docs if d['worker'] == worker), key=lambda d: d['published_at'])

    def attempt(worker):
        return json.loads((coord / 'saves' / 'attempts' / (worker + '.json')).read_text())

    def disk(path):
        if not path.exists():
            return None
        return {str(p.relative_to(path)): (p.stat().st_mode, hashlib.sha256(p.read_bytes()).hexdigest())
                for p in path.rglob('*') if p.is_file()}

    def source_state(worker):
        path = wt / worker
        gd = Path(git(path, 'rev-parse', '--absolute-git-dir').decode().strip())
        return git(path, 'rev-parse', 'HEAD'), (gd / 'index').read_bytes(), (path / 'tracked').read_bytes()

    def released(worker):
        with (coord / '.locks' / (worker + '.lock')).open('r') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        check(worker + ' releases native worker/account ownership',
              not json.loads(good(unio('policy', '--json')).stdout)['active_native_workflows'])

    def reaped(path):
        def live(pid):
            try:
                return Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()[0] != 'Z'
            except FileNotFoundError:
                return False
        check(path.name + ' helpers and Git children reaped',
              all(not live(e[k]) for e in events(path) for k in ('helper', 'shim')))

    def native(worker, extra=None):
        run = unio('run', worker, worker, extra=extra)
        code = 137 if worker == 'mock-source-kill' else 23
        check(worker + ' preserves actual Source/native/structured process exit',
              run.returncode == code
              and json.loads(unio('result', worker, worker).stdout)['process']['exit_code'] == code)
        released(worker)
        return run

    # Supplemental contract check; outcomes below exercise the installed CLI.
    body = (SOURCE / 'unio-install.sh').read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY\n', 1)[0]
    module = types.ModuleType('budget_contract')
    exec(compile(body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], 'budget_contract', 'exec'), module.__dict__)
    prior = os.environ.pop('UNIO_SAVE_CAPTURE_TIMEOUT', None)
    try:
        check('unchanged default capture/observation 30s and restore 120s',
              module.capture_seconds() == module.CAPTURE_SECONDS == 30 and module.RESTORE_SECONDS == 120)
    finally:
        if prior is not None:
            os.environ['UNIO_SAVE_CAPTURE_TIMEOUT'] = prior

    # Invalid manual input cannot create a store, lock, attempt or observation.
    invalid = ['', '0', '-1', '301', '1.5', '1s', ' 1', '1 ', '+1', '1e2', '1\n', '٣', '9' * 5000]
    invalid_gate = gate('invalid', 'kill')
    before_locks = disk(coord / '.locks')
    for value in invalid:
        run = unio('save', 'create', 'mock-invalid', 'mock-invalid', extra=dict(
            UNIO_SAVE_CAPTURE_TIMEOUT=value, BUDGET_GATE=str(invalid_gate)))
        check('invalid whole-second input refused before effects: ' + repr(value[:12]),
              run.returncode == 1 and 'UNIO_SAVE_CAPTURE_TIMEOUT' in run.stderr and '1–300' in run.stderr
              and not (coord / 'saves').exists() and disk(coord / '.locks') == before_locks
              and not events(invalid_gate))
    check('read-only usage remains usable with invalid capture configuration and no store',
          unio('save', 'usage', '--json', extra=dict(UNIO_SAVE_CAPTURE_TIMEOUT='bad')).returncode == 0)

    before = source_state('mock-manual')
    good(unio('save', 'create', 'mock-manual', 'mock-manual'))
    check('unset default performs actual manual capture without touching HEAD/index/bytes',
          len(saves('mock-manual')) == 1 and source_state('mock-manual') == before)
    for value in ('1', '300', '0003'):
        check('supported boundary/whole-second value captures: ' + value,
              unio('save', 'create', 'mock-manual', 'mock-manual',
                   extra=dict(UNIO_SAVE_CAPTURE_TIMEOUT=value)).returncode == 0)
    prior_ids = [d['save_id'] for d in saves('mock-manual')]
    short_gate = gate('manual-short', 'delay')
    run = unio('save', 'create', 'mock-manual', 'mock-manual', extra=dict(
        UNIO_SAVE_CAPTURE_TIMEOUT='1', BUDGET_GATE=str(short_gate)))
    check('1s manual budget refuses an actual delayed capture and retains previous snapshots',
          run.returncode == 1 and '1 second bound' in run.stderr
          and [d['save_id'] for d in saves('mock-manual')] == prior_ids
          and attempt('mock-manual')['last_good_id'] == prior_ids[-1])
    reaped(short_gate)
    long_gate = gate('manual-long', 'delay')
    good(unio('save', 'create', 'mock-manual', 'mock-manual', extra=dict(
        UNIO_SAVE_CAPTURE_TIMEOUT='3', BUDGET_GATE=str(long_gate))))
    check('3s manual budget changes delayed capture outcome and preserves source',
          saves('mock-manual')[-1]['save_id'] not in prior_ids and source_state('mock-manual') == before)
    reaped(long_gate)
    sid = saves('mock-manual')[-1]['save_id']
    evidence = disk(coord / 'saves')
    for args in (('inspect', sid, '--json'), ('inspect', '--worker', 'mock-manual', '--json'), ('usage', '--json')):
        check('read-only ' + ' '.join(args[:2]) + ' ignores invalid capture configuration',
              unio('save', *args, extra=dict(UNIO_SAVE_CAPTURE_TIMEOUT='bad')).returncode == 0
              and disk(coord / 'saves') == evidence)
    check('restore stays independently usable and exact with invalid capture setting',
          unio('save', 'restore', sid, 'mock-dest', extra=dict(UNIO_SAVE_CAPTURE_TIMEOUT='bad')).returncode == 0
          and (wt / 'mock-dest' / 'tracked').read_bytes() == before[2])

    good(unio('resume'))
    active = None
    try:
        run = native('mock-default')
        check('unset default actually publishes native baseline/final failure captures',
              [d['reason'] for d in saves('mock-default')] == ['baseline', 'final-failure']
              and saves('mock-default')[-1]['provider_exit'] == 23 and 'deadline exceeded' not in run.stderr)
        for name, seconds in (('short', '1'), ('long', '3')):
            path = gate('native-' + name, 'delay')
            run = native('mock-' + name, dict(UNIO_SAVE_CAPTURE_TIMEOUT=seconds, BUDGET_GATE=str(path)))
            check(seconds + 's applies to both real native baseline and final helpers',
                  len(events(path)) == 2 and (not saves('mock-short') if name == 'short' else
                  [d['reason'] for d in saves('mock-long')] == ['baseline', 'final-failure']))
            reaped(path)

        for name, mode in (('deadline', 'stop'), ('external', 'kill'), ('crash', 'pass')):
            worker = 'mock-' + name
            good(unio('save', 'create', worker, worker))
            sid = saves(worker)[-1]['save_id']
            snapshot = disk(coord / 'saves' / sid)
            path = gate(name, mode)
            extra = dict(UNIO_SAVE_CAPTURE_TIMEOUT='1' if name == 'deadline' else '3', BUDGET_GATE=str(path))
            if name == 'crash':
                extra['UNIO_SAVE_TEST_FAULT'] = 'publish-interrupt'
            run = native(worker, extra)
            helper_exit = '75' if name == 'crash' else '-9'
            check(name + ' keeps real helper exit and attributes only controller deadline',
                  run.stderr.count('helper exit ' + helper_exit) == 2
                  and (run.stderr.count('capture deadline exceeded (1 seconds)') == 2
                       if name == 'deadline' else 'deadline exceeded' not in run.stderr))
            check(name + ' retains immutable last-good save and real provider exit',
                  [d['save_id'] for d in saves(worker)] == [sid] and disk(coord / 'saves' / sid) == snapshot
                  and attempt(worker)['last_good_id'] == sid and attempt(worker)['provider_exit'] == 23
                  and attempt(worker)['status'] == 'failed'
                  and unio('save', 'inspect', sid, '--json').returncode == 0)
            reaped(path)

        run = native('mock-source-kill')
        check('Source exit 137 is independent of capture deadlines',
              saves('mock-source-kill')[-1]['provider_exit'] == 137 and 'deadline exceeded' not in run.stderr)
        evidence = disk(coord / 'saves')
        run = native('mock-invalid', dict(UNIO_SAVE_CAPTURE_TIMEOUT='bad', BUDGET_GATE=str(invalid_gate)))
        check('invalid native configuration refuses capture before effects and keeps provider independent',
              run.stderr.count('UNIO_SAVE_CAPTURE_TIMEOUT') == 2
              and disk(coord / 'saves') == evidence and not events(invalid_gate))

        path = gate('cancel', 'stop-first')
        out, err = base / 'cancel.stdout', base / 'cancel.stderr'
        with out.open('w') as stdout, err.open('w') as stderr:
            active = subprocess.Popen([at, 'run', 'mock-cancel', 'mock-cancel'], cwd=repo,
                                      env=dict(env, UNIO_SAVE_CAPTURE_TIMEOUT='300', BUDGET_GATE=str(path)),
                                      stdout=stdout, stderr=stderr)
            until(lambda: events(path))
            started = time.monotonic()
            active.send_signal(signal.SIGTERM)
            active.wait(timeout=12)
        check('300s capture configuration keeps cancellation grace bounded and real exit 143',
              active.returncode == 143 and time.monotonic() - started < 8
              and 'helper exit -9' in err.read_text() and 'deadline exceeded' not in err.read_text()
              and not (base / 'mock-cancel-started').exists()
              and saves('mock-cancel')[-1]['provider_exit'] == 143)
        active = None
        released('mock-cancel')
        reaped(path)

        # Keep the original final-cleanup ceiling even when the configured
        # capture budget is 300s. This real stopped-helper check takes ~31s;
        # it verifies TERM/escalation, receipts and ownership, not just a sleep.
        print('  checking original final-cancellation ceiling (30s)', flush=True)
        path = gate('cancel-final', 'stop-final')
        out, err = base / 'cancel-final.stdout', base / 'cancel-final.stderr'
        with out.open('w') as stdout, err.open('w') as stderr:
            active = subprocess.Popen([at, 'run', 'mock-cancel-final', 'mock-cancel-final'], cwd=repo,
                                      env=dict(env, UNIO_SAVE_CAPTURE_TIMEOUT='300', BUDGET_GATE=str(path)),
                                      stdout=stdout, stderr=stderr)
            until(lambda: any(e['mode'] == 'stop' for e in events(path)))
            baseline = saves('mock-cancel-final')[0]['save_id']
            started = time.monotonic()
            active.send_signal(signal.SIGTERM)
            active.wait(timeout=38)
        check('300s final capture cancellation retains original 30s cleanup plus 1s grace',
              active.returncode == 143 and 30 <= time.monotonic() - started < 36
              and 'helper exit -9' in err.read_text() and 'deadline exceeded' not in err.read_text()
              and [d['save_id'] for d in saves('mock-cancel-final')] == [baseline]
              and attempt('mock-cancel-final')['last_good_id'] == baseline
              and attempt('mock-cancel-final')['provider_exit'] == 23)
        active = None
        released('mock-cancel-final')
        reaped(path)

        # Real production periodic interval, with a dynamic fixture gate enabled
        # only after baseline. Final capture succeeds after the gate is released.
        print('  waiting for real native periodic interval (60s)', flush=True)
        path = gate('periodic', 'pass')
        out, err = base / 'periodic.stdout', base / 'periodic.stderr'
        with out.open('w') as stdout, err.open('w') as stderr:
            active = subprocess.Popen([at, 'run', 'mock-periodic', 'mock-periodic'], cwd=repo,
                                      env=dict(env, UNIO_SAVE_CAPTURE_TIMEOUT='3', BUDGET_GATE=str(path)),
                                      stdout=stdout, stderr=stderr)
            until(lambda: (base / 'mock-periodic-started').exists())
            baseline = saves('mock-periodic')[0]['save_id']
            (path / 'mode').write_text('stop')
            until(lambda: 'automatic periodic save unavailable' in err.read_text(), seconds=70)
            check('actual periodic controller uses configured deadline and preserves baseline',
                  'helper exit -9; capture deadline exceeded (3 seconds)' in err.read_text()
                  and attempt('mock-periodic')['last_good_id'] == baseline
                  and [d['save_id'] for d in saves('mock-periodic')] == [baseline])
            (path / 'mode').write_text('pass')
            (base / 'periodic-finish').touch()
            active.wait(timeout=15)
        check('periodic deadline leaves provider running and final capture usable',
              active.returncode == 23 and len(events(path)) == 3
              and [d['reason'] for d in saves('mock-periodic')] == ['baseline', 'final-failure']
              and saves('mock-periodic')[-1]['provider_exit'] == 23)
        active = None
        released('mock-periodic')
        reaped(path)
    finally:
        if active is not None and active.poll() is None:
            # Release stopped helpers even on an assertion failure, then use the
            # real supervisor's orderly cancellation before any outer escalation.
            for p in base.glob('gate-*/*.json'):
                try:
                    os.kill(json.loads(p.read_text())['helper'], signal.SIGCONT)
                except ProcessLookupError:
                    pass
            active.terminate()
            active.wait(timeout=40)
        unio('stop')

    check('all calls are deliberate offline mocks, with cancellation making none',
          calls.read_text().splitlines() == ['mock-' + name for name in
              ('default', 'short', 'long', 'deadline', 'external', 'crash', 'source-kill', 'invalid', 'cancel-final', 'periodic')])

print('PASS: %d save capture budget checks' % passed)
