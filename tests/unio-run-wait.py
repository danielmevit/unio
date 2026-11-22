#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Background launch acknowledgement and `unio wait` against the installed CLI.

Real public commands only (run -b, wait, kill, stop, resume, tier); the sole
provider boundary is a fake scripted worker. Covers: acknowledged start with
published identity, immediate completion with the control files already
retired, failure exit propagation, the child's started/refused acknowledgement
records, the bounded Unknown deadline, STOP, timeout, malformed/stale pid
evidence, orphan, interrupt stopping only the waiter, exact-attempt binding
across a concurrent launch of the same task, a pair of waits over the same
worker/task across two attempts (a frozen first waiter keeps its own exit and
never receives the replacement result, or reports Unknown when its immutable
receipt is deliberately removed), partial multi-task deadlines, and direct
hand-built coordination fixtures for exact-attempt resolution. Also covered:
a fault of only the supplemental receipt writer keeps the canonical end write
with the truthful exact exit, an exact receipt takes precedence while polling
over a pending flag plus a live (possibly same-worker replacement) identity,
mixed generation observations are resampled bounded or rejected, and after an
--any winner the remaining work is reported as still in progress (timeout
wording only on an actual deadline).
"""
import contextlib
import io
import json
import os
import re
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
SCRATCH = Path(os.environ.get(
    'UNIO_WAIT_TEST_SCRATCH',
    str(SOURCE.parents[3] / 'tmp' / 'unio-next'
        / 'ocy-wait-mistral-glm-high-20261122' / 'fixtures')))
SCRATCH.mkdir(parents=True, exist_ok=True)

TASK_TEXT = '# Task {name}\n## Goal\nfake work\n## Allowed scope\n- hello.txt\n## Validate\n$ true\n## Done means\nnothing special\n## Report\nSUMMARY\n'


def run(argv, env, cwd, timeout=240):
    return subprocess.run(argv, env=env, cwd=cwd, text=True,
                          capture_output=True, timeout=timeout)


def ok(name, condition, detail=''):
    if not condition:
        raise SystemExit('FAILED: %s %s' % (name, detail))
    print('ok %s' % name, flush=True)


with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='run-wait-') as tmp:
    base = Path(tmp)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), TMPDIR=str(base),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
               UNIO_TEST_PROV_MARKER=str(base / 'provider-calls'))
    install = run(['bash', str(SOURCE / 'unio-install.sh')], env, SOURCE)
    assert install.returncode == 0, install.stderr
    at = base / 'bin' / 'unio'
    root = base / 'project'
    repo = root / 'repo'
    repo.mkdir(parents=True)
    for args in (['git', 'init', '-q', '-b', 'main'],
                 ['git', 'commit', '-q', '--allow-empty', '-m', 'mock'],
                 [str(at), 'init', 'mocka-1', 'mockb-1'],
                 [str(at), 'tier', 'high']):
        p = run(args, env, repo)
        assert p.returncode == 0, (args, p.stderr)

    provider = base / 'provider.sh'
    provider.write_text(
        '#!/bin/bash\n'
        'printf \'%s\\n\' "$UNIO_CODEX_TASK" >> "$UNIO_TEST_PROV_MARKER"\n'
        'case "$UNIO_CODEX_TASK" in\n'
        '  t-ok) sleep 3; exit 0;;\n'
        '  t-fast) exit 0;;\n'
        '  t-fail) sleep 2; exit 7;;\n'
        '  t-fg) sleep 2; exit 0;;\n'
        '  t-bogus) sleep 45; exit 0;;\n'
        '  t-a) sleep 60; exit 0;;\n'
        '  t-b) sleep 1; exit 5;;\n'
        '  t-orphan) sleep 90; exit 0;;\n'
        '  t-int) sleep 25; exit 0;;\n'
        '  t-conc) if [ "$UNIO_CODEX_WORKER" = mockb-1 ]; then sleep 1; exit 9; else sleep 20; exit 0; fi;;\n'
        '  t-two) n=$(grep -c "^t-two$" "$UNIO_TEST_PROV_MARKER" || true)\n'
        '         if [ $((n % 2)) = 1 ]; then sleep 4; exit 0; else sleep 1; exit 9; fi;;\n'
        '  t-aux) sleep 2; exit 7;;\n'
        '  *) exit 0;;\n'
        'esac\n')
    (base / 'conf' / 'agents.conf').write_text(
        'mocka=bash "%s"\nmockb=bash "%s"\n' % (provider, provider))
    tasks = root / 'coord' / 'tasks'
    for name in ('t-ok', 't-fast', 't-fail', 't-fg', 't-stop', 't-bogus',
                 't-a', 't-b', 't-orphan', 't-int', 't-conc', 't-two', 't-aux'):
        (tasks / (name + '.md')).write_text(TASK_TEXT.format(name=name))

    def cli(*args, timeout=240):
        return run([str(at), *args], env, repo, timeout=timeout)

    def wait_worker_free(worker, limit=60):
        # `unio wait` now returns an attempt's exact exit as soon as its
        # immutable receipt exists, while the finished run's shell may still
        # be retiring (and holding the worker lock) for a moment; a following
        # launch waits bounded for the lock instead of racing it.
        lock = root / 'coord' / '.locks' / (worker + '.lock')
        end = time.monotonic() + limit
        while time.monotonic() < end:
            p = run(['bash', '-c', 'exec 9>>"$1"; flock -n 9', 'harness', str(lock)],
                    env, repo, timeout=10)
            if p.returncode == 0:
                return
            time.sleep(0.2)
        raise SystemExit('FAILED: worker %s lock stayed busy for %ds' % (worker, limit))

    def launch_bg(worker, task):
        wait_worker_free(worker)
        p = cli('run', '-b', worker, task)
        started = [line for line in p.stdout.splitlines()
                   if line.startswith('started in background')]
        ok('run -b %s acknowledged start' % task,
           p.returncode == 0 and len(started) == 1,
           (p.returncode, p.stdout, p.stderr))
        pidfile = root / 'coord' / 'reports' / (task + '.pid')
        ok('run -b %s published identity before reporting' % task,
           pidfile.is_file() and (root / 'coord' / 'reports' / (task + '.own')).is_file(),
           'pid/own missing right after start')
        ok('run -b %s cleaned its acknowledgement file' % task,
           not list((root / 'coord' / '.locks').glob('bg-ack.*')))
        return p, pidfile

    def wait_pid_appears(pidfile, limit=60):
        limit = time.monotonic() + limit
        while time.monotonic() < limit:
            if pidfile.is_file():
                return pidfile.read_text().strip()
            time.sleep(0.2)
        raise SystemExit('FAILED: identity never published: %s' % pidfile)

    # 1. acknowledged start, then a successful wait
    launch_bg('mocka-1', 't-ok')
    p = cli('wait', 't-ok', '--timeout', '120')
    ok('wait returns the recorded exit 0', p.returncode == 0 and 'exit 0' in p.stdout,
       (p.returncode, p.stdout, p.stderr))

    # 2. immediate completion: the start is still acknowledged, and the exact
    #    exit stays recoverable from the same attempt after the public
    #    control files retire — no fast completion is missed or guessed
    launch_bg('mocka-1', 't-fast')
    p = cli('wait', 't-fast', '--timeout', '120')
    ok('wait does not miss an immediately completing attempt',
       p.returncode == 0 and 'exit 0' in p.stdout, (p.returncode, p.stdout, p.stderr))
    p = cli('wait', 't-fast', '--timeout', '30')
    ok('wait recovers the exact exit of a completed attempt after control retirement',
       p.returncode == 0 and 'exit 0' in p.stdout and 'still running' not in p.stdout
       and 'nothing is bound' not in p.stderr, (p.returncode, p.stdout, p.stderr))
    p = cli('wait', 't-fast.md', '--timeout', '30')
    ok('wait accepts the .md task suffix on a completed attempt',
       p.returncode == 0 and 'exit 0' in p.stdout, (p.returncode, p.stdout, p.stderr))
    # reuse: a second attempt of the same worker/task mints a new exact
    # identity; both immutable receipts survive and the latest is reported
    launch_bg('mocka-1', 't-fast')
    p = cli('wait', 't-fast', '--timeout', '120')
    ok('wait reports the latest attempt after task reuse',
       p.returncode == 0 and 'exit 0' in p.stdout, (p.returncode, p.stdout, p.stderr))
    receipts = sorted((root / 'coord' / 'results' / 'mocka-1'
                       / 't-fast.attempts').glob('*.json'))
    ok('both immutable attempt receipts survive reuse', len(receipts) == 2, receipts)

    # 2b. pair of waits over the same worker/task across two attempts: run A
    #     exits 0, run B exits 9. A waiter frozen on attempt A keeps A's own
    #     exit across B's replacement of the task-addressed view.
    def freeze_waiter(waiter):
        # `unio wait` execs python, so the Popen pid is the watcher itself.
        time.sleep(1.5)  # binding happens before the first poll
        os.kill(waiter.pid, signal.SIGSTOP)

    launch_bg('mocka-1', 't-two')
    waiter_a = subprocess.Popen([str(at), 'wait', 't-two', '--timeout', '240'],
                                env=env, cwd=repo, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    freeze_waiter(waiter_a)
    p = cli('wait', 't-two', '--timeout', '120')
    ok('attempt A exit 0 is recoverable while its own waiter is frozen',
       p.returncode == 0 and 'exit 0' in p.stdout, (p.returncode, p.stdout, p.stderr))
    launch_bg('mocka-1', 't-two')
    p = cli('wait', 't-two', '--timeout', '120')
    ok('attempt B exit 9 is the latest attempt', p.returncode == 9 and 'exit 9' in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    os.kill(waiter_a.pid, signal.SIGCONT)
    out, err = waiter_a.communicate(timeout=240)
    ok('a waiter bound to attempt A reports its own exit, never B exit 9',
       waiter_a.returncode == 0 and 'exit 0' in out and 'exit 9' not in out,
       (waiter_a.returncode, out, err))
    # the same pair with attempt C exit 0 whose immutable receipt is then
    # deliberately removed: its waiter must report Unknown, never D exit 9
    launch_bg('mocka-1', 't-two')
    waiter_c = subprocess.Popen([str(at), 'wait', 't-two', '--timeout', '240'],
                                env=env, cwd=repo, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)
    freeze_waiter(waiter_c)
    p = cli('wait', 't-two', '--timeout', '120')
    ok('attempt C exit 0 completed while its waiter was frozen',
       p.returncode == 0 and 'exit 0' in p.stdout, (p.returncode, p.stdout, p.stderr))
    ledger = json.loads((root / 'coord' / 'retries' / 't-two' / 'state.json').read_text())
    receipt_c = (root / 'coord' / 'results' / 'mocka-1' / 't-two.attempts'
                 / (ledger['latest']['mocka-1']['id'] + '.json'))
    ok('attempt C wrote its immutable receipt', receipt_c.is_file())
    receipt_c.unlink()
    launch_bg('mocka-1', 't-two')
    p = cli('wait', 't-two', '--timeout', '120')
    ok('attempt D exit 9 is the latest attempt', p.returncode == 9 and 'exit 9' in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    os.kill(waiter_c.pid, signal.SIGCONT)
    out, err = waiter_c.communicate(timeout=240)
    ok('a waiter whose original receipt was removed reports Unknown, never a later exit',
       waiter_c.returncode == 2 and 'Unknown' in out and 'exit 9' not in out,
       (waiter_c.returncode, out, err))

    # 3. failure: the actual worker exit is propagated
    launch_bg('mocka-1', 't-fail')
    p = cli('wait', 't-fail', '--timeout', '120')
    ok('wait propagates the actual failure exit 7',
       p.returncode == 7 and 'exit 7' in p.stdout, (p.returncode, p.stdout, p.stderr))

    # 3b. a fault of ONLY the supplemental immutable receipt writer (the
    #     .attempts path is blocked by a regular file, so the storage
    #     protections refuse just that extra write): the original canonical
    #     result end write must still persist the truthful exact exit
    launch_bg('mocka-1', 't-aux')
    (root / 'coord' / 'results' / 'mocka-1' / 't-aux.attempts').write_text('blocked\n')
    p = cli('wait', 't-aux', '--timeout', '120')
    ok('wait returns the exact exit when only the supplemental receipt write failed',
       p.returncode == 7 and 'exit 7' in p.stdout, (p.returncode, p.stdout, p.stderr))
    aux_doc = json.loads((root / 'coord' / 'results' / 'mocka-1' / 't-aux.json').read_text())
    ok('the canonical result kept the truthful exact exit despite the receipt fault',
       aux_doc['process']['state'] == 'failed' and aux_doc['process']['exit_code'] == 7
       and isinstance(aux_doc.get('attempt_id'), str), aux_doc.get('process'))

    # 4. the detached child's started record names the published identity
    locks = root / 'coord' / '.locks'
    ack = locks / 'ack-test-started'
    ack.write_text('')
    child = subprocess.Popen([str(at), 'run', 'mocka-1', 't-fg'],
                              env=dict(env, UNIO_BG='1', UNIO_BG_ACK=str(ack)),
                              cwd=repo, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid = wait_pid_appears(root / 'coord' / 'reports' / 't-fg.pid')
    library = base / 'functions.sh'
    library.write_text(at.read_text().split('case "${1:-help}" in\n')[0])
    p = run(['bash', '-c', 'source "$1"; saves "$2" _bg-ack-wait "$3" 5 mocka-1 t-fg',
             'harness', str(library), str(root), str(ack)], env, repo, timeout=30)
    ok('child started acknowledgement matches the published pid',
       p.returncode == 0 and p.stdout.strip() == 'started %s' % pid,
       (p.returncode, p.stdout, p.stderr))
    ok('foreground child finished', child.wait(timeout=180) == 0)

    # 5. STOP: the parent refuses without launching; a detached child that
    #    hits STOP acknowledges the refusal, never a start
    assert cli('stop').returncode == 0
    p = cli('run', '-b', 'mocka-1', 't-stop')
    ok('run -b under STOP refuses without claiming a start',
       p.returncode != 0 and 'started in background' not in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    ack2 = locks / 'ack-test-refused'
    ack2.write_text('')
    p = run([str(at), 'run', 'mocka-1', 't-stop'],
            env=dict(env, UNIO_BG='1', UNIO_BG_ACK=str(ack2)), cwd=repo, timeout=60)
    ok('STOP child exits nonzero without identity',
       p.returncode != 0 and not (root / 'coord' / 'reports' / 't-stop.pid').exists())
    p = run(['bash', '-c', 'source "$1"; saves "$2" _bg-ack-wait "$3" 5 mocka-1 t-stop',
             'harness', str(library), str(root), str(ack2)], env, repo, timeout=30)
    ok('child refusal is acknowledged and distinguished from started',
       p.returncode == 2 and 'refused before identity was published' in p.stderr
       and 'started' not in p.stdout, (p.returncode, p.stdout, p.stderr))
    assert cli('resume').returncode == 0

    # 6. bounded Unknown deadline for a missing acknowledgement
    ack3 = locks / 'ack-test-unknown'
    ack3.write_text('')
    started = time.monotonic()
    p = run(['bash', '-c', 'source "$1"; saves "$2" _bg-ack-wait "$3" 1 mocka-1 t-none',
             'harness', str(library), str(root), str(ack3)], env, repo, timeout=30)
    ok('missing acknowledgement is bounded Unknown, not started',
       p.returncode == 2 and 'Unknown' in p.stderr and 'started' not in p.stdout
       and time.monotonic() - started < 10, (p.returncode, p.stdout, p.stderr))

    # 7. live attempt: bounded timeout leaves it running, STOP does not
    #    block the read-only waiter, and bogus pid evidence is refused
    _, pidfile = launch_bg('mocka-1', 't-bogus')
    real_pid = pidfile.read_text()
    assert cli('stop').returncode == 0
    p = cli('wait', 't-bogus', '--timeout', '1')
    ok('wait timeout is bounded and signals nothing',
       p.returncode == 2 and 'timeout' in p.stderr and pidfile.read_text() == real_pid,
       (p.returncode, p.stdout, p.stderr))
    p = cli('wait', 't-bogus', '--timeout', '0')
    ok('wait rejects an invalid timeout bound', p.returncode == 2 and 'whole seconds' in p.stderr)
    assert cli('resume').returncode == 0
    marker = repo / 'evaluated-marker'
    for value in ('-1', '0', 'abc', '99999999999999999999', '$(touch evaluated-marker)'):
        pidfile.write_text(value + '\n')
        p = cli('wait', 't-bogus', '--timeout', '30')
        ok('wait refuses bogus pid evidence safely: %r' % value,
           p.returncode == 2 and 'nothing is bound' in p.stderr and not marker.exists()
           and pidfile.read_text() == value + '\n', (p.returncode, p.stdout, p.stderr))
    sleeper = subprocess.Popen(['sleep', '30'])
    pidfile.write_text(str(sleeper.pid) + '\n')
    p = cli('wait', 't-bogus', '--timeout', '30')
    ok('wait refuses a pid that does not match the recorded ownership',
       p.returncode == 2 and 'nothing is bound' in p.stderr, (p.returncode, p.stdout, p.stderr))
    sleeper.kill()
    sleeper.wait()
    pidfile.write_text(real_pid)
    p = cli('kill', 't-bogus')
    ok('kill still cleans up after wait refused to act on bad evidence',
       p.returncode == 0, (p.returncode, p.stdout, p.stderr))

    # 8. --any returns the first attempt to end; a partial multi-task deadline
    #    is incomplete (exit 2) even when the completed task exited 0
    launch_bg('mocka-1', 't-a')
    launch_bg('mockb-1', 't-b')
    p = cli('wait', 't-a', 't-b', '--any', '--timeout', '240')
    ok('--any returns the first attempt to end with its actual exit',
       p.returncode == 5 and 'exit 5' in p.stdout and 't-b' in p.stdout
       and 't-a' in p.stdout, (p.returncode, p.stdout, p.stderr))
    p = cli('wait', 't-ok', 't-a', '--timeout', '2')
    ok('all-mode with one exit-0 task and one live task at the deadline is incomplete',
       p.returncode == 2 and 'exit 0' in p.stdout and 'still running' in p.stdout
       and 'no bound attempt ended' not in p.stderr, (p.returncode, p.stdout, p.stderr))
    p = cli('wait', 't-ok', 't-a', '--any', '--timeout', '30')
    ok('--any reports its actual winner when one attempt already ended',
       p.returncode == 0 and 'exit 0' in p.stdout, (p.returncode, p.stdout, p.stderr))
    assert cli('kill', 't-a').returncode == 0

    # 9. orphan: the shell dies without recording an exit
    launch_bg('mocka-1', 't-orphan')
    pid = int(wait_pid_appears(root / 'coord' / 'reports' / 't-orphan.pid'))
    os.kill(pid, signal.SIGKILL)
    p = cli('wait', 't-orphan', '--timeout', '60')
    ok('wait reports an orphan as completion Unknown',
       p.returncode == 2 and 'Unknown' in p.stdout, (p.returncode, p.stdout, p.stderr))
    p = cli('kill', 't-orphan')
    ok('kill reaps the orphaned controls', p.returncode == 0, (p.returncode, p.stdout, p.stderr))

    # 10. interrupt stops only the waiter
    launch_bg('mocka-1', 't-int')
    pidfile = root / 'coord' / 'reports' / 't-int.pid'
    waiter = subprocess.Popen([str(at), 'wait', 't-int', '--timeout', '120'],
                               env=env, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True)
    time.sleep(3)
    waiter.send_signal(signal.SIGINT)
    ok('interrupt stops only the waiter', waiter.wait(timeout=30) == 130 and pidfile.is_file())
    assert cli('kill', 't-int').returncode == 0

    # 11. exact-attempt binding across a concurrent launch of the same task:
    #     the public identity is replaced, the waiter still returns the exit
    #     of the attempt it bound
    launch_bg('mocka-1', 't-conc')
    waiter = subprocess.Popen([str(at), 'wait', 't-conc', '--timeout', '240'],
                              env=env, cwd=repo, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True)
    time.sleep(2)
    launch_bg('mockb-1', 't-conc')
    out, err = waiter.communicate(timeout=240)
    ok('wait stays bound to its exact attempt across a concurrent launch',
       waiter.returncode == 0 and 'mocka-1' in out and 'exit 0' in out
       and 'exit 9' not in out, (waiter.returncode, out, err))

    # 12. direct regression fixtures: exact-attempt resolution against a
    #     hand-built coordination tree — no provider, no real run; the waiter
    #     is read-only, so a synthetic tree exercises binding and resolution
    #     deterministically, including stale and reused pid identities
    fixture = base / 'fixture-root'
    fcoord = fixture / 'coord'
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    when = '2026-01-01T00:00:00+00:00'
    a_id, b_id, c_id = 'a' * 32, 'b' * 32, 'c' * 32

    def fwait(*args):
        return run(['bash', '-c', 'source "$1"; shift; saves "$1" _wait "${@:2}"',
                    'harness', str(library), str(fixture), *args],
                   env, repo, timeout=60)

    def fwrite(path, doc):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc) + '\n')
        path.chmod(0o600)

    def fraw(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        path.chmod(0o600)

    def fledger(task, latest):
        fwrite(fcoord / 'retries' / task / 'state.json',
               dict(schema_version=1, task=task, failed_attempts=0,
                    retry_granted=False, latest=latest, updated_at=when))

    def freceipt(worker, task, attempt_id, code):
        fwrite(fcoord / 'results' / worker / (task + '.attempts') / (attempt_id + '.json'),
               dict(schema_version=1, worker=worker, task=task, attempt_id=attempt_id,
                    state='succeeded' if code == 0 else 'failed',
                    exit_code=code, updated_at=when))

    def fdoc(worker, task, attempt_id, state, code):
        fwrite(fcoord / 'results' / worker / (task + '.json'),
               dict(schema_version=1, worker=worker, task=task, updated_at=when,
                    attempt_id=attempt_id,
                    process=dict(state=state, exit_code=code, revision=None)))

    # a terminal attempt whose receipt survives a newer attempt replacing the
    # task-addressed result view: the exact exit 3 wins, never exit 9
    fledger('f-task', {'f-work': dict(id=a_id, pending=False, failed=True)})
    fdoc('f-work', 'f-task', b_id, 'succeeded', 9)
    freceipt('f-work', 'f-task', a_id, 3)
    p = fwait('f-task', '--timeout', '5')
    ok('fixture: the immutable receipt wins over a replacement result',
       p.returncode == 3 and 'exit 3' in p.stdout and 'exit 9' not in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    # the receipt deliberately removed: Unknown, never the later result
    (fcoord / 'results' / 'f-work' / 'f-task.attempts' / (a_id + '.json')).unlink()
    p = fwait('f-task', '--timeout', '5')
    ok('fixture: a removed receipt reports Unknown, never the later exit',
       p.returncode == 2 and 'Unknown' in p.stdout and 'exit 9' not in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    # no receipt, but the result still names the bound attempt: its own exit
    fdoc('f-work', 'f-task', a_id, 'failed', 3)
    p = fwait('f-task', '--timeout', '5')
    ok('fixture: a result naming the bound attempt is its own exit',
       p.returncode == 3 and 'exit 3' in p.stdout, (p.returncode, p.stdout, p.stderr))
    # several workers recorded attempts and no ownership selects one: refuse
    fledger('f-amb', {'f-work': dict(id=a_id, pending=False, failed=False),
                      'other': dict(id=b_id, pending=False, failed=False)})
    p = fwait('f-amb', '--timeout', '5')
    ok('fixture: several candidate handles are refused, never guessed',
       p.returncode == 2 and 'nothing is bound' in p.stderr
       and 'several workers' in p.stderr, (p.returncode, p.stdout, p.stderr))

    # a pending attempt watched through a live shell identity plus a terminal
    # attempt: at the deadline the wait is incomplete although one task
    # completed normally with exit 0
    sleeper = subprocess.Popen(['sleep', '300'], start_new_session=True)
    fields = Path('/proc/%d/stat' % sleeper.pid).read_text().rsplit(')', 1)[1].split()
    shell_start, shell_sid = int(fields[19]), int(fields[3])
    fledger('f-live', {'f-work': dict(id=c_id, pending=True, failed=False)})
    fwrite(fcoord / 'reports' / 'f-live.own',
           dict(schema_version=1, boot_id=boot, worker='f-work', task='f-live',
                shell_pid=sleeper.pid, shell_start=shell_start, shell_sid=shell_sid,
                provider_pid=None, provider_sid=None, provider_start=None))
    fraw(fcoord / 'reports' / 'f-live.pid', '%d\n' % sleeper.pid)
    fledger('f-done', {'f-work': dict(id=b_id, pending=False, failed=False)})
    freceipt('f-work', 'f-done', b_id, 0)
    p = fwait('f-done', 'f-live', '--timeout', '1')
    ok('fixture: one exit-0 task and one live task at the deadline is incomplete',
       p.returncode == 2 and 'exit 0' in p.stdout and 'still running' in p.stdout
       and 'no bound attempt ended' not in p.stderr, (p.returncode, p.stdout, p.stderr))
    p = fwait('f-done', 'f-live', '--any', '--timeout', '5')
    ok('fixture: --any reports its actual winner immediately',
       p.returncode == 0 and 'exit 0' in p.stdout, (p.returncode, p.stdout, p.stderr))
    p = fwait('f-done', 'f-live', '--any', '--timeout', '5')
    ok('fixture: after an --any winner the remaining work is still in progress, not a timeout',
       p.returncode == 0 and any("'f-done'" in line and 'exit 0' in line for line in p.stdout.splitlines())
       and any("'f-live'" in line and 'still running' in line and 'still in progress' in line
               and 'timeout' not in line for line in p.stdout.splitlines()),
       (p.returncode, p.stdout, p.stderr))
    p = fwait('f-done', 'f-live', '--timeout', '1')
    ok('fixture: timeout wording appears only on an actual deadline',
       p.returncode == 2 and any('timeout after 1s' in line for line in p.stdout.splitlines())
       and 'no bound attempt ended' not in p.stderr, (p.returncode, p.stdout, p.stderr))
    # stale identity: the shell died without recording anything — polling
    # must not claim a process is running from the stale identity
    sleeper.kill()
    sleeper.wait()
    p = fwait('f-live', '--timeout', '5')
    ok('fixture: a dead shell is never claimed running; the outcome is Unknown',
       p.returncode == 2 and 'Unknown' in p.stdout and 'still running' not in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    # reused pid: a different live process under the recorded pid — the
    # start-ticks mismatch proves it is not the recorded attempt
    other = subprocess.Popen(['sleep', '300'], start_new_session=True)
    own = json.loads((fcoord / 'reports' / 'f-live.own').read_text())
    own['shell_pid'] = other.pid
    fwrite(fcoord / 'reports' / 'f-live.own', own)
    fraw(fcoord / 'reports' / 'f-live.pid', '%d\n' % other.pid)
    p = fwait('f-live', '--timeout', '5')
    ok('fixture: a reused pid never counts as the recorded running attempt',
       p.returncode == 2 and 'Unknown' in p.stdout and 'still running' not in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    other.kill()
    other.wait()

    # 13. generation-bound live owner proof: a pending attempt whose terminal
    #     receipt already exists, while the public owner/pid sample was
    #     supplied by a same-worker replacement run (a live foreign identity)
    sleeper2 = subprocess.Popen(['sleep', '300'], start_new_session=True)
    fields = Path('/proc/%d/stat' % sleeper2.pid).read_text().rsplit(')', 1)[1].split()
    fledger('f-mix', {'f-work': dict(id=a_id, pending=True, failed=False)})
    fwrite(fcoord / 'reports' / 'f-mix.own',
           dict(schema_version=1, boot_id=boot, worker='f-work', task='f-mix',
                shell_pid=sleeper2.pid, shell_start=int(fields[19]), shell_sid=int(fields[3]),
                provider_pid=None, provider_sid=None, provider_start=None))
    fraw(fcoord / 'reports' / 'f-mix.pid', '%d\n' % sleeper2.pid)
    freceipt('f-work', 'f-mix', a_id, 7)
    p = fwait('f-mix', '--timeout', '5')
    ok('fixture: an exact receipt wins over a pending flag plus a live foreign identity',
       p.returncode == 7 and 'exit 7' in p.stdout and 'still running' not in p.stdout,
       (p.returncode, p.stdout, p.stderr))
    sleeper2.kill()
    sleeper2.wait()

    # 14. selected-function regressions against the exact committed waiter
    #     source (no provider, no real run): deterministic mixed-generation
    #     interleavings of the retry ledger and the public owner/pid sample
    waiter_source = (SOURCE / 'tools' / 'run-wait.py').read_text()

    class _Refuse(Exception):
        pass

    def waiter_env():
        env = dict(os=os, re=re, sys=sys, time=time, signal=signal, Refuse=_Refuse,
                   ident=lambda v: isinstance(v, str) and bool(v),
                   under=lambda *parts: '/'.join(parts))
        exec(compile(waiter_source, '<run-wait.py>', 'exec'), env)
        return env

    def ledger_doc(attempt_id):
        return dict(schema_version=1, task='repeat',
                    latest={'fixture': dict(id=attempt_id, pending=True, failed=False)})

    own_b = dict(worker='fixture', task='repeat', shell_pid=2222, shell_start=20002,
                 shell_sid=2222, boot_id='00000000-0000-0000-0000-000000000002')
    # the ledger observed A pending, then same-worker run B started before
    # the public owner/pid sample was taken: the live identity must bind to
    # its own generation (B), never to the stale A
    seen = {'n': 0}

    def shifting_ledger(root, task):
        seen['n'] += 1
        return ledger_doc(a_id if seen['n'] == 1 else b_id)

    env = waiter_env()
    env['_wait_retry_state'] = shifting_ledger
    env['load_owner'] = lambda *a: dict(own_b)
    env['read_path'] = lambda *a, **k: (None, b'2222\n')
    binding, failure = env['wait_bind']('/fixture', 'repeat')
    ok('fixture: a same-worker replacement identity binds to its own generation, never mixed',
       failure is None and binding['attempt_id'] == b_id and binding['shell_pid'] == 2222
       and binding['pending'] is True, (binding, failure))
    # a ledger that keeps alternating between generations while sampling is a
    # permanently mixed observation: bounded resample, then refuse
    seen['n'] = 0

    def alternating_ledger(root, task):
        seen['n'] += 1
        return ledger_doc(a_id if seen['n'] % 2 else b_id)

    env = waiter_env()
    env['_wait_retry_state'] = alternating_ledger
    env['load_owner'] = lambda *a: dict(own_b)
    env['read_path'] = lambda *a, **k: (None, b'2222\n')
    binding, failure = env['wait_bind']('/fixture', 'repeat')
    ok('fixture: never-consistent mixed observations are rejected, never bound',
       binding is None and failure[0] == 'stale' and 'mixed' in failure[1], (binding, failure))
    # while polling, an exact receipt for the bound attempt takes precedence
    # over a pending flag plus a live (possibly foreign) shell identity
    env = waiter_env()
    env['wait_bind'] = lambda root, task: (
        dict(worker='fixture', task=task, attempt_id=a_id, pending=True, shell_pid=2222,
             shell_start=20002, shell_sid=2222), None)
    env['_wait_live'] = lambda binding: True
    env['_wait_receipt'] = lambda *a: dict(exit_code=7)
    env['_wait_resolve'] = lambda *a: ('unknown', 'must not be used while an exact receipt exists')
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = env['wait_main']('/fixture', ['repeat', '--timeout', '1'])
    ok('fixture: an exact receipt takes precedence while polling a live pending attempt',
       code == 7 and 'exit 7' in out.getvalue() and 'still running' not in out.getvalue(),
       (code, out.getvalue(), err.getvalue()))

    # 15. focused selected-function regression for the writer side: a fault of
    #     only the supplemental immutable receipt writer must leave the
    #     original canonical result end write intact, with a clear diagnostic
    installer = (SOURCE / 'unio-install.sh').read_text()
    wstart = installer.index('def update(root, worker, task, operation, encoded, *args):')
    wend = installer.index('\ndef hidden(wt):', wstart)
    update_source = installer[wstart:wend]
    writes, diags = [], []

    def fault_receipt(*args):
        raise OSError(28, 'synthetic auxiliary receipt write failure only')

    for operation in ('end', 'end-unbound'):
        record = dict(process=dict(state='running', exit_code=None), attempt_id='a' * 32)
        env2 = dict(json=json, revision=lambda rev: True,
                    load=lambda *a, **k: dict(record),
                    outcome_finish=lambda *a: None, delivery_finish=lambda *a: None,
                    retry=lambda *a: dict(id='a' * 32, pending=False, failed=True),
                    attempt_receipt=fault_receipt,
                    current=lambda *a: None, snapshot=lambda *a: {},
                    valid_document=lambda *a: None,
                    locations=lambda *a: (None, None, 'canonical.json'),
                    atomic=lambda path, data: writes.append((operation, path, data['process']['exit_code'])),
                    stamp=lambda: '2026-01-01T00:00:00+00:00', sys=sys)
        exec(compile(update_source, '<update>', 'exec'), env2)
        with contextlib.redirect_stderr(io.StringIO()) as diag:
            env2['update']('/fixture', 'worker', 'task', operation, '{}', '7')
        diags.append(diag.getvalue())
    ok('fixture: a fault of only the supplemental receipt writer keeps the canonical end write',
       ('end', 'canonical.json', 7) in writes and ('end-unbound', 'canonical.json', 7) in writes,
       writes)
    ok('fixture: the receipt fault produced a clear diagnostic naming the exact exit',
       all('immutable attempt receipt' in d and 'exact exit 7' in d for d in diags), diags)

    # exact receipts survive every public flow above, with the real exits
    for name, code in (('t-ok', 0), ('t-fail', 7)):
        stored = [json.loads(path.read_text()) for path in
                  (root / 'coord' / 'results' / 'mocka-1'
                   / (name + '.attempts')).glob('*.json')]
        ok('the exact receipt for %s survives with its real exit' % name,
           len(stored) == 1 and stored[0]['exit_code'] == code
           and stored[0]['state'] == ('succeeded' if code == 0 else 'failed'), stored)

    calls = (base / 'provider-calls').read_text().split()
    # Runs killed before their supervisor finished the baseline capture never
    # reach a provider; every run that did is counted exactly once, STOP
    # never started one, and no wait or acknowledgement ever added a call.
    expected = {'t-ok': 1, 't-fast': 2, 't-fail': 1, 't-fg': 1, 't-a': 1, 't-b': 1,
                't-conc': 2, 't-two': 4, 't-aux': 1}
    ok('no provider call ever came from wait or the acknowledgement',
       all(calls.count(task) == count for task, count in expected.items())
       and 't-stop' not in calls
       and all(calls.count(task) <= 1 for task in ('t-bogus', 't-orphan', 't-int'))
       and len(calls) <= 17, calls)
    for name in ('ack-test-started', 'ack-test-refused', 'ack-test-unknown'):
        (locks / name).unlink(missing_ok=True)
    ok('no acknowledgement litter remains',
       not list((root / 'coord' / '.locks').glob('bg-ack.*')))
print('run/wait checks passed; fake provider only.')
