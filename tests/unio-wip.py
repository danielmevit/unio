#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed offline WIP acceptance; local mock processes only, private tmpfs."""
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import tempfile
import time

SOURCE = Path(__file__).resolve().parent.parent
passed = 0


def check(label, value, detail=''):
    global passed
    if not value:
        raise AssertionError(label + '\n' + str(detail))
    passed += 1
    print('  ok ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='unio-wip-', dir='/dev/shm') as tmp:
    base = Path(tmp)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='30', GIT_AUTHOR_NAME='offline',
               GIT_COMMITTER_NAME='offline', GIT_AUTHOR_EMAIL='offline@example.invalid',
               GIT_COMMITTER_EMAIL='offline@example.invalid')
    for key in ('UNIO_SAVE_TEST_FAULT', 'UNIO_TEST_FAULT_DIR', 'BASH_ENV'):
        env.pop(key, None)
    subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env, check=True, capture_output=True)
    at = str(base / 'bin/unio')
    root = base / 'project'
    repo = root / 'repo'
    repo.mkdir(parents=True)

    def run(args, cwd=repo, codes=(0,), extra=None):
        cp = subprocess.run(args, cwd=cwd, env=dict(env, **(extra or {})), text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60)
        if cp.returncode not in codes:
            raise AssertionError(str(args) + '\n' + cp.stdout)
        return cp

    def git(*args, cwd=repo):
        return run(['git', *args], cwd).stdout.strip()

    git('init', '-q', '-b', 'main')
    (repo / 'tracked.txt').write_text('base\n')
    (repo / 'delete.txt').write_text('delete me\n')
    git('add', 'tracked.txt', 'delete.txt')
    git('commit', '-qm', 'base')
    run([at, 'init', 'mock'])
    run([at, 'tier', 'low'])
    run([at, 'lead', 'none'])
    wt = root / 'wt/mock'
    initial = git('rev-parse', 'HEAD', cwd=wt)
    provider = base / 'provider.py'
    provider.write_text('''import os, signal, subprocess, time
from pathlib import Path
case = os.environ['WIP_CASE']
p = Path('tracked.txt')
if case == 'clean':
    raise SystemExit(0)
if case == 'secret':
    Path('.env').write_text('dummy fixture only')
elif case == 'outside':
    Path('outside.txt').write_text('outside')
elif case == 'binary':
    p.write_bytes(b'bad\\0bytes')
elif case == 'symlink':
    p.unlink(); p.symlink_to('delete.txt')
elif case == 'fifo':
    os.mkfifo('fifo')
elif case == 'merge':
    gd = subprocess.check_output(['git','rev-parse','--absolute-git-dir'], text=True).strip()
    Path(gd, 'MERGE_HEAD').write_text(subprocess.check_output(['git','rev-parse','HEAD'], text=True))
elif case == 'delete':
    Path('delete.txt').unlink()
else:
    p.write_text('worker text\\n')
if case == 'partial':
    subprocess.run(['git','add','tracked.txt'], check=True)
    p.write_text('worker unstaged text\\n')
if case == 'committed':
    subprocess.run(['git','add','tracked.txt'], check=True)
    subprocess.run(['git','commit','-qm','worker commit'], check=True)
    raise SystemExit(0)
if case == 'term':
    Path(os.environ['WIP_READY']).write_text('ready')
    time.sleep(60)
print('transport failed' if case == 'transport' else 'limit reached')
raise SystemExit(42)
''')
    (base / 'conf/agents.conf').write_text('mock=python3 ' + shlex.quote(str(provider)) + '\n')
    task = root / 'coord/tasks/task.md'
    task.write_text('# Offline WIP\n\n## Allowed scope\n- tracked.txt\n- delete.txt\n\n## Validate\n$ true\n')
    hookdir = base / 'hooks'
    hookdir.mkdir()
    hook = hookdir / 'pre-commit'
    marker = base / 'hook-ran'
    git('config', 'core.hooksPath', str(hookdir), cwd=wt)

    def reset():
        for name in ('fifo', '.env', 'outside.txt'):
            (wt / name).unlink(missing_ok=True)
        gd = Path(git('rev-parse', '--absolute-git-dir', cwd=wt))
        (gd / 'MERGE_HEAD').unlink(missing_ok=True)
        git('reset', '--hard', initial, cwd=wt)
        git('clean', '-fd', cwd=wt)
        hook.unlink(missing_ok=True)
        marker.unlink(missing_ok=True)

    invocation = [0]

    def invoke(case, expected=42):
        invocation[0] += 1
        task_id = 'case-%d' % invocation[0]
        (task.parent / (task_id + '.md')).write_text(task.read_text())
        cp = run([at, 'run', 'mock', task_id], codes=(expected,), extra={'WIP_CASE': case})
        receipts = sorted((root / 'coord/reports/.wip').glob('*.json'), key=lambda p: p.stat().st_mtime_ns)
        receipts = [p for p in receipts if not p.name.endswith(('.start.json', '.claim.json'))]
        doc = json.loads(receipts[-1].read_text())
        check(case + ' keeps original Source exit', doc['original_exit'] == expected, cp.stdout)
        check(case + ' stays unaccepted', doc['accepted'] is False)
        check(case + ' report includes outcome and recovery guidance',
              'WIP ' + doc['outcome'] in cp.stdout and 'unio save inspect' in cp.stdout, cp.stdout)
        check(case + ' private receipt', receipts[-1].stat().st_mode & 0o077 == 0)
        return doc, cp

    check('default off', 'WIP off' in run([at, 'wip', 'status']).stdout)
    doc, cp = invoke('limit')
    check('default off leaves bytes uncommitted', doc['outcome'] == 'skipped' and git('rev-parse', 'HEAD', cwd=wt) == initial)
    reset()
    run([at, 'wip', 'on'])
    for case in ('limit', 'transport', 'delete'):
        reset()
        hook.write_text('#!/bin/sh\necho normal-hook > ' + shlex.quote(str(marker)) + '\n')
        hook.chmod(0o700)
        doc, cp = invoke(case)
        check(case + ' creates scoped WIP', doc['outcome'] == 'created' and doc['revision'] == git('rev-parse', 'HEAD', cwd=wt), cp.stdout)
        check(case + ' normal hooks execute', marker.exists())
        check(case + ' leaves clean index/worktree', not git('status', '--porcelain', cwd=wt))
        result = run([at, 'result', 'mock', 'case-%d' % invocation[0]], codes=(0, 1, 2)).stdout
        check(case + ' structured result failed', 'failed' in result, result)
    for case in ('partial', 'secret', 'outside', 'binary', 'symlink', 'fifo', 'merge'):
        reset()
        doc, cp = invoke(case)
        check(case + ' refuses without commit', doc['outcome'] == 'refused' and git('rev-parse', 'HEAD', cwd=wt) == initial, cp.stdout)
        if case == 'partial':
            check('partial index bytes retained', git('show', ':tracked.txt', cwd=wt) == 'worker text' and (wt / 'tracked.txt').read_text() == 'worker unstaged text\n')
    reset()
    hook.write_text('#!/bin/sh\necho hook-refused > ' + shlex.quote(str(marker)) + '\nexit 1\n')
    hook.chmod(0o700)
    before_index = Path(git('rev-parse', '--absolute-git-dir', cwd=wt), 'index').read_bytes()
    doc, cp = invoke('limit')
    check('hook failure preserves original index and edits', doc['outcome'] == 'refused' and marker.exists()
          and Path(git('rev-parse', '--absolute-git-dir', cwd=wt), 'index').read_bytes() == before_index
          and (wt / 'tracked.txt').read_text() == 'worker text\n', cp.stdout)
    reset()
    hook.write_text('#!/bin/sh\necho hook-mutated > tracked.txt\n')
    hook.chmod(0o700)
    doc, cp = invoke('limit')
    check('hook mutation reports Unknown and preserves changed bytes', doc['outcome'] == 'unknown'
          and (wt / 'tracked.txt').read_text() == 'hook-mutated\n', cp.stdout)
    reset()
    shim = base / 'shim'
    shim.mkdir()
    real_git = subprocess.check_output(['which', 'git'], text=True).strip()
    (shim / 'git').write_text('#!/bin/sh\n' + shlex.quote(real_git) + ' "$@"\nrc=$?\n'
        + 'case "$GIT_INDEX_FILE" in *unio-wip-*) echo changing-bytes > ' + shlex.quote(str(wt / 'tracked.txt')) + ';; esac\nexit "$rc"\n')
    (shim / 'git').chmod(0o700)
    old_path = env['PATH']
    env['PATH'] = str(shim) + os.pathsep + old_path
    doc, cp = invoke('limit')
    env['PATH'] = old_path
    check('changing bytes refuse before commit and remain available', doc['outcome'] == 'refused'
          and git('rev-parse', 'HEAD', cwd=wt) == initial and 'changing-bytes' in (wt / 'tracked.txt').read_text(), cp.stdout)
    for case in ('clean', 'committed'):
        reset()
        doc, cp = invoke(case, 0)
        check(case + ' avoids duplicate WIP', doc['outcome'] == 'skipped')
        check(case + ' exact commit count', git('rev-list', '--count', initial + '..HEAD', cwd=wt) == ('1' if case == 'committed' else '0'))
    reset()
    (wt / 'tracked.txt').write_text('existing user edit\n')
    doc, cp = invoke('limit')
    check('dirty initial state refuses', doc['outcome'] == 'refused' and 'initial worktree' in doc['reason'], cp.stdout)
    reset()
    reset()
    (wt / 'tracked.txt').write_text('preexisting staged user text\n')
    git('add', 'tracked.txt', cwd=wt)
    staged_before = Path(git('rev-parse', '--absolute-git-dir', cwd=wt), 'index').read_bytes()
    doc, cp = invoke('limit')
    check('preexisting staging refuses and preserves original index', doc['outcome'] == 'refused'
          and 'initial safety' in doc['reason']
          and Path(git('rev-parse', '--absolute-git-dir', cwd=wt), 'index').read_bytes() == staged_before, cp.stdout)
    reset()
    setting = root / 'coord/wip.json'
    setting.write_text('{bad')
    doc, cp = invoke('limit')
    check('malformed setting refuses', doc['outcome'] == 'refused', cp.stdout)
    setting.unlink()
    run([at, 'wip', 'on'])
    reset()
    setting.chmod(0o644)
    doc, cp = invoke('limit')
    check('unsafe setting never enables WIP', doc['outcome'] == 'refused' and 'private' in doc['reason'], cp.stdout)
    setting.chmod(0o600)

    reset()
    ready = base / 'ready'
    proc = subprocess.Popen([at, 'run', 'mock', 'task'], cwd=repo,
                            env=dict(env, WIP_CASE='term', WIP_READY=str(ready)),
                            text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    deadline = time.monotonic() + 30
    while not ready.exists() and time.monotonic() < deadline:
        time.sleep(.05)
    check('TERM provider started', ready.exists())
    proc.send_signal(signal.SIGTERM)
    output = proc.communicate(timeout=30)[0]
    check('TERM exit preserved with WIP', proc.returncode == 143 and 'WIP created' in output, output)
    check('report contains WIP and save guidance', 'WIP created' in (root / 'coord/reports/task.md').read_text())
    installed = Path(at).read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY', 1)[0]
    installed = installed.rsplit('\nsys.exit(main(sys.argv[1:]))', 1)[0]
    native = {}
    exec(compile(installed, '<installed WIP helper>', 'exec'), native)
    native['inherited_run'] = lambda *args: 'f' * 32
    native['parent_matches'] = lambda record: True
    native['load_owner'] = lambda path: dict(worker='mock', task='task', shell_pid=os.getppid(), provider_pid=123)
    native['capture'] = lambda *args: (_ for _ in ()).throw(AssertionError('capture before idle proof'))
    for state, run_id in [('unknown', 'e' * 32), ('ok', 'd' * 32)]:
        native['inherited_run'] = lambda *args, identity=run_id: identity
        native['session_members'] = lambda record, outcome=state: (outcome, [])
        native['wip_finish'](str(root), 'mock', 'task', '42')
        refused = json.loads((root / ('coord/reports/.wip/' + run_id + '.json')).read_text())
        check('unproved/live owned writers never reach capture or commit: ' + state, refused['outcome'] == 'unknown')
    try:
        native['wip_finish'](str(root), 'mock', 'task', '42')
        check('duplicate run attempt must refuse', False)
    except FileExistsError:
        check('duplicate run attempt cannot replay commit', True)


print('PASS %d WIP checks (installed offline mocks)' % passed)
