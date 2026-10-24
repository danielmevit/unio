#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed, mock-only selftest regression; honors the caller's TMPDIR."""
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import time

SOURCE = Path(__file__).resolve().parent.parent


def check(label, condition, detail=''):
    assert condition, label + ': ' + detail
    print('ok ' + label, flush=True)


def proc_start(pid):
    try:
        rest = Path('/proc/%d/stat' % pid).read_text().rsplit(')', 1)[1].split()
    except (OSError, IndexError):
        return None
    return None if rest[0] == 'Z' else rest[19]


def term_exact(pid, start):
    """TERM only through a pidfd whose process still has the recorded start."""
    try:
        fd = os.pidfd_open(pid)
    except OSError:
        return False
    try:
        if proc_start(pid) != start:
            return False
        signal.pidfd_send_signal(fd, signal.SIGTERM)
        return True
    finally:
        os.close(fd)


def fixture_runs(root):
    """Published runtimes that hold a lock in their own fixture coord/.locks."""
    found = []
    for pidfile in Path(root).rglob('coord/reports/*.pid'):
        locks = pidfile.parent.parent / '.locks'
        try:
            pid = int(pidfile.read_text().strip())
            inodes = {p.stat().st_ino for p in locks.glob('*.lock')}
            start = proc_start(pid)
            fds = os.listdir('/proc/%d/fdinfo' % pid)
        except (OSError, ValueError):
            continue
        for fd in fds:
            try:
                lines = Path('/proc/%d/fdinfo/%s' % (pid, fd)).read_text().splitlines()
            except OSError:
                continue
            held = any(l.startswith('lock:') and ' WRITE ' in l for l in lines)
            if held and any(l == 'ino:\t%d' % i for i in inodes for l in lines):
                found.append((pid, start, pidfile))
                break
    return found


def stop_fixture_runs(root, bound=30):
    """Exact fixture-owned cleanup; returns runtimes not proved gone."""
    runs = [r for r in fixture_runs(root) if r[1]]
    for pid, start, _ in runs:
        term_exact(pid, start)
    deadline = time.monotonic() + bound
    while runs and time.monotonic() < deadline:
        runs = [r for r in runs if proc_start(r[0]) == r[1]]
        time.sleep(.1)
    return runs


def run_bounded(cmd, timeout, root, **kw):
    """Own session; on timeout print partial output and clean the fixture."""
    proc = subprocess.Popen(cmd, start_new_session=True, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kw)
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, []
    except subprocess.TimeoutExpired:
        # Unreaped, so this group can only hold our own descendants.
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            out, err = proc.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
        left = stop_fixture_runs(root)
        print('outer timeout after %ss; partial output follows' % timeout, flush=True)
        print(out + err, end='', flush=True)
        if left:
            print('fixture runtimes still active, fixture kept: %r' % left, flush=True)
        return None, out, err, left


FAKE = """#!/usr/bin/env python3
import fcntl, os, signal, subprocess, sys, time
from pathlib import Path
reports, locks = Path('../coord/reports'), Path('../coord/.locks')
if sys.argv[1] == 'kill':
    if sys.argv[2] == 'kill-fail':
        sys.exit(2)
    os.kill(int((reports / (sys.argv[2] + '.pid')).read_text()), signal.SIGTERM)
    sys.exit(0)
if sys.argv[1:3] == ['run', '-b']:
    worker, task = sys.argv[3:5]
    if worker == 'refused':
        print('refused by budget')
        sys.exit(2)
    child = subprocess.Popen([sys.executable, '-B', sys.argv[0], 'runtime', worker, task],
                             start_new_session=True, stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rest = Path('/proc/%d/stat' % child.pid).read_text().rsplit(')', 1)[1].split()
    with open(os.environ['FAKE_RECORD'], 'a') as f:
        f.write('%d %s\\n' % (child.pid, rest[19]))
    print('started in background — poll: unio status')
    sys.exit(0)
worker, task = sys.argv[2:4]
pidfile, own = reports / (task + '.pid'), reports / (task + '.own')
def stop(*args):
    pidfile.unlink(missing_ok=True)
    own.unlink(missing_ok=True)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
if worker == 'no-start':
    sys.exit(23)
if worker == 'never-start':
    time.sleep(120)
    sys.exit(24)
time.sleep(3 if worker in ('delayed', 'complete', 'snapshot-failed') else .2)
fd = os.open(locks / (worker + '.lock'), os.O_WRONLY | os.O_CREAT | os.O_APPEND)
os.dup2(fd, 9)
fcntl.flock(9, fcntl.LOCK_EX | fcntl.LOCK_NB)
pidfile.write_text('%d\\n' % os.getpid())
own.write_text('fake-owned')
Path(os.environ['UNIO_SELFTEST_STARTED']).touch()
if worker in ('complete', 'snapshot-failed'):
    time.sleep(.2)
    with open(reports / 'ledger.jsonl', 'a') as f:
        f.write('{"event":"run","task":"%s","exit":0,"snapshot_failed":%d}\\n'
                % (task, worker == 'snapshot-failed'))
    stop()
while True:
    time.sleep(.1)
"""

HARNESS = r"""
ST="$1"
# An unrelated fixture process must survive every cleanup.
sleep 180 & sentinel=$!
trap '[ -z "${ST_BG_TASK:-}" ] || st_bg_cleanup; kill "$sentinel" 2>/dev/null; wait "$sentinel" 2>/dev/null' EXIT
case "${SCENARIO:-all}" in
hang)
  st_bg_launch delayed delayed || exit 1
  st_bg_wait ready || exit 2
  echo "progress: delayed ready"
  sleep 300
  ;;
all)
st_bg_launch delayed delayed || exit 1
st_bg_wait ready || exit 1
[ "$SECONDS" -ge 3 ] || exit 2
st_bg_cleanup || exit 3
kill -0 "$sentinel" || exit 4
st_bg_launch complete complete || exit 5
# Initially absent controls must not count as completion.
st_bg_wait complete || exit 5
[ -f "$ST/complete.started" ] || exit 6
st_bg_cleanup || exit 7
st_bg_launch snapshot-failed snapshot-failed || exit 8
if st_bg_wait complete; then exit 8; fi
st_bg_cleanup || exit 9
if st_bg_launch refused refused; then exit 10; fi
if st_bg_wait ready; then exit 10; fi
st_bg_launch no-start no-start || exit 11
if st_bg_wait complete; then exit 11; fi
if st_bg_cleanup; then exit 12; fi
st_bg_launch never-start never-start || exit 13
if st_bg_wait ready; then exit 13; fi
if st_bg_cleanup; then exit 14; fi
st_bg_launch kill-fail kill-fail || exit 15
st_bg_wait ready || exit 15
st_bg_cleanup || exit 16
st_bg_launch reaped reaped || exit 17
st_bg_wait ready || exit 17
# Crash the runtime, then let its stale pidfile name the sentinel.
kill -KILL "${ST_BG_ID% *}"
while st_bg_proc alive $ST_BG_ID; do sleep 0.1; done
echo "$sentinel" > ../coord/reports/reaped.pid
if st_bg_cleanup; then exit 18; fi
rm -f ../coord/reports/reaped.pid ../coord/reports/reaped.own
kill -0 "$sentinel" || exit 19
ST_BG_TASK=""
exit 0
;;
esac
"""


def background_regressions(runner, base, env):
    """Exercise the installed selftest helpers with deterministic fake jobs."""
    installed = runner.read_text()
    start = installed.index('  # ST_BACKGROUND_HELPERS_BEGIN')
    end = installed.index('  # ST_BACKGROUND_HELPERS_END', start)
    helpers = installed[start:end]
    fake = base / 'fake-background'
    fake.write_text(FAKE)
    fake.chmod(0o755)
    record = base / 'fake-runtimes'
    harness = base / 'background-harness.sh'

    def run(script, label, timeout, **extra):
        fixture = base / ('background ' + label)
        (fixture / 'repo').mkdir(parents=True)
        (fixture / 'coord/reports').mkdir(parents=True)
        (fixture / 'coord/.locks').mkdir(parents=True)
        harness.write_text(script)
        record.write_text('')
        case_env = dict(env, ST_BG_LIMIT='10', FAKE_RECORD=str(record), **extra)
        rc, out, err, left = run_bounded(
            ['bash', '-c', 'source "$1" "$2"', str(fake), str(harness), str(fixture)],
            timeout, fixture, cwd=fixture / 'repo', env=case_env)
        # Test-only teardown of every fake this case spawned, by exact identity.
        spawned = [line.split() for line in record.read_text().splitlines()]
        for pid, start in spawned:
            term_exact(int(pid), start)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and any(
                proc_start(int(p)) == s for p, s in spawned):
            time.sleep(.1)
        alive = [p for p, s in spawned if proc_start(int(p)) == s]
        return rc, out, err, left, alive, fixture

    rc, out, err, left, alive, fixture = run(helpers + HARNESS, 'all', 120)
    check('installed run -b frontend/delayed start/no start/delayed completion/'
          'snapshot failure/native kill failure/reaped pid/sentinel regressions',
          rc == 0, out + err)
    check('bounded fake failures include useful diagnostics',
          'task=no-start' in err and 'phase=complete' in err and
          'task=never-start' in err and 'phase=ready' in err and
          'task=refused frontend=2' in err and 'not exit 0 with a bound snapshot' in err and
          'native kill failed' in err and 'cleanup Unknown' in err, err)
    # never-start is the one fake no cleanup could prove; teardown above
    # killed it by its recorded identity, nothing else may be left.
    check('only the unprovable never-start fake outlived helper cleanup',
          not alive and not left, repr((alive, left)))
    check('fake-owned controls cleaned',
          not list((fixture / 'coord/reports').glob('*.pid')) and
          not list((fixture / 'coord/reports').glob('*.own')))

    rc, out, err, left, alive, fixture = run(helpers + HARNESS, 'hang', 15,
                                             SCENARIO='hang')
    check('outer timeout prints partial progress and cleans the exact detached run',
          rc is None and 'progress: delayed ready' in out and not left and not alive and
          not (fixture / 'coord/reports/delayed.pid').exists(), out + err)

    # Negative controls reproduce the former observation logic against the
    # same delayed jobs. They must fail, rather than become green by retries;
    # only the observed phase is replaced, readiness stays bounded and real.
    for phase, old_wait, expected in (
        ('ready', 'sleep 2; [ -f "../coord/reports/$ST_BG_TASK.pid" ]', 1),
        ('complete', '[ ! -f "../coord/reports/$ST_BG_TASK.pid" ]', 6),
    ):
        override = ('eval "st_bg_wait_new() $(declare -f st_bg_wait | tail -n +2)"\n'
                    'st_bg_wait() { if [ "$1" = ' + phase + ' ]; then ' + old_wait +
                    '; else st_bg_wait_new "$@"; fi; }\n')
        rc, out, err, left, alive, fixture = run(helpers + override + HARNESS,
                                                 'former ' + phase, 60)
        check('former ' + phase + ' observation fails delayed fixture',
              rc == expected and not left and not alive, out + err)


# Fixtures stay project-local unless the caller chooses TMPDIR; a fixture is
# removed only after no runtime it owns is still active.
base = Path(tempfile.mkdtemp(prefix='unio selftest ',
                             dir=os.environ.get('TMPDIR', str(SOURCE))))
try:
    home = base / 'isolated home'
    home.mkdir()
    # Sentinel proves even the fixture's global Git config stays untouched.
    global_config = home / '.gitconfig'
    sentinel = b'[user]\n\tname = fixture\n\temail = fixture@example.invalid\n'
    global_config.write_bytes(sentinel)
    env = dict(os.environ, HOME=str(home), PYTHONDONTWRITEBYTECODE='1',
               UNIO_BIN_DIR=str(base / 'installed bin'),
               UNIO_CONF_DIR=str(base / 'installed conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               TMPDIR=str(base), GIT_CONFIG_GLOBAL=str(global_config),
               GIT_CONFIG_NOSYSTEM='1', UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0', UNIO_TIMEOUT='30',
               GIT_AUTHOR_NAME='fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_NAME='fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
    for key in ('BASH_ENV', 'UNIO_SAVE_TEST_FAULT', 'UNIO_TEST_FAULT_DIR'):
        env.pop(key, None)
    subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env,
                   check=True, capture_output=True, timeout=120)
    runner = base / 'installed bin/unio'
    background_regressions(runner, base, env)
    conf = base / 'installed conf'
    helper = conf / 'lib/remote-guard.py'
    canonical = (SOURCE / 'tools/remote-guard.py').read_bytes()
    check('installed helper is canonical', helper.read_bytes() == canonical)
    # Removing the external file no longer removes the implementation: the
    # byte-identical engine core must still run all behavioral assertions.
    helper.rename(helper.with_suffix('.saved'))
    # Snapshot all installed payload/config bytes; selftest may only write its
    # own sandbox, never alter the invoking profile.
    before = {p.relative_to(conf): p.read_bytes() for p in conf.rglob('*') if p.is_file()}
    rc, stdout, stderr, left = run_bounded([str(runner), 'selftest'], 300, base,
                                          cwd=base, env=env)
    if rc is not None:
        print(stdout, end='', flush=True)
    check('selftest without external helper exits zero', rc == 0 and not left, stdout + stderr)
    check('all 40 built-in assertions pass',
          'selftest: 40 ok, 0 failed' in stdout and
          len(re.findall(r'^  ok    ', stdout, re.M)) == 40 and
          '  FAIL  ' not in stdout, stdout)
    match = re.search(r'^== unio selftest — sandbox: (.+) ==$', stdout, re.M)
    check('sandbox honors TMPDIR with spaces', bool(match) and Path(match[1]).parent == base)
    check('successful sandbox removed', bool(match) and not Path(match[1]).exists())
    after = {p.relative_to(conf): p.read_bytes() for p in conf.rglob('*') if p.is_file()}
    check('installed profile untouched', before == after)
    check('global Git config untouched', global_config.read_bytes() == sentinel)
finally:
    left = stop_fixture_runs(base)
    if left:
        print('fixture kept, runtimes still active: %s %r' % (base, left), flush=True)
    else:
        shutil.rmtree(base)
