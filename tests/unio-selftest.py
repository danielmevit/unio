#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed, mock-only selftest regression; honors the caller's TMPDIR."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parent.parent


def check(label, condition, detail=''):
    assert condition, label + ': ' + detail
    print('ok ' + label, flush=True)


def background_regressions(runner, base, env):
    """Exercise the installed selftest helpers with deterministic fake jobs."""
    installed = runner.read_text()
    start = installed.index('  # ST_BACKGROUND_HELPERS_BEGIN')
    end = installed.index('  # ST_BACKGROUND_HELPERS_END', start)
    helpers = installed[start:end]
    fake = base / 'fake-background'
    fake.write_text("""#!/usr/bin/env python3
import os, signal, sys, time
from pathlib import Path
reports = Path('../coord/reports')
if sys.argv[1] == 'kill':
    os.kill(int((reports / (sys.argv[2] + '.pid')).read_text()), signal.SIGTERM)
    sys.exit(0)
mode, task = sys.argv[2:4]
pidfile, own = [reports / (task + suffix) for suffix in ('.pid', '.own')]
def stop(*args):
    pidfile.unlink(missing_ok=True)
    own.unlink(missing_ok=True)
    sys.exit(0)
signal.signal(signal.SIGTERM, stop)
if mode == 'no-start':
    sys.exit(23)
if mode == 'never-start':
    time.sleep(120)
    sys.exit(24)
time.sleep(3)
pidfile.write_text(str(os.getpid()))
own.write_text('fake-owned')
Path(os.environ['UNIO_SELFTEST_STARTED']).touch()
if mode == 'complete':
    time.sleep(.2)
    stop()
while True:
    time.sleep(.1)
""")
    fake.chmod(0o755)
    fixture = base / 'background regressions'
    (fixture / 'repo').mkdir(parents=True)
    (fixture / 'coord/reports').mkdir(parents=True)
    harness = base / 'background-harness.sh'
    harness.write_text(helpers + r'''
ST="$1"
# An unrelated fixture process must survive every cleanup.
sleep 180 & sentinel=$!
trap '[ -z "${ST_BG_PID:-}" ] || st_bg_cleanup; kill "$sentinel" 2>/dev/null; wait "$sentinel" 2>/dev/null' EXIT
st_bg_launch delayed delayed
st_bg_wait ready || exit 1
[ "$SECONDS" -ge 3 ] || exit 2
st_bg_cleanup || exit 3
kill -0 "$sentinel" || exit 4
st_bg_launch complete complete
# Initially absent controls must not count as completion.
st_bg_wait complete || exit 5
[ -f "$ST/complete.started" ] || exit 6
st_bg_cleanup || exit 7
st_bg_launch no-start no-start
if st_bg_wait complete; then exit 8; fi
st_bg_cleanup || exit 9
st_bg_launch never-start never-start
# Bound the negative readiness case with the production helper's 60s limit.
if st_bg_wait ready; then exit 10; fi
st_bg_cleanup || exit 11
kill -0 "$ST_BG_PID" 2>/dev/null && exit 12
kill -0 "$sentinel" || exit 13
exit 0
''')
    result = subprocess.run(['bash', '-c', 'source "$1" "$2"', str(fake),
                             str(harness), str(fixture)], cwd=fixture / 'repo',
                            env=env, text=True, capture_output=True, timeout=100)
    check('installed background delayed-start/completion/no-start/cleanup regressions',
          result.returncode == 0, result.stdout + result.stderr)
    check('bounded fake failures include useful diagnostics',
          'task=no-start' in result.stderr and 'child exit=23' in result.stderr and
          'task=never-start' in result.stderr and 'phase=ready' in result.stderr,
          result.stderr)
    check('fake-owned controls cleaned', not list((fixture / 'coord/reports').iterdir()))
    # Negative controls reproduce the former observation logic against the
    # same delayed jobs. They must fail, rather than become green by retries.
    text = harness.read_text()
    for phase, old_wait, expected in (
        ('ready', 'sleep 2; [ -f "../coord/reports/$ST_BG_TASK.pid" ]', 1),
        ('complete', '[ ! -f "../coord/reports/$ST_BG_TASK.pid" ]', 6),
    ):
        replacement = 'st_bg_wait() { ' + old_wait + '; }\n'
        case = text.replace('ST="$1"', replacement + 'ST="$1"')
        if phase == 'complete':
            case = case.replace('st_bg_wait ready || exit 1',
                                'sleep 4; [ -f "$ST/delayed.started" ] || exit 1')
        harness.write_text(case)
        old = subprocess.run(['bash', '-c', 'source "$1" "$2"', str(fake),
                              str(harness), str(fixture)], cwd=fixture / 'repo',
                             env=env, text=True, capture_output=True, timeout=20)
        check('former ' + phase + ' observation fails delayed fixture',
              old.returncode == expected, old.stdout + old.stderr)



with tempfile.TemporaryDirectory(prefix='unio selftest ',
                                 dir=os.environ.get('TMPDIR')) as tmp:
    base = Path(tmp)
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
    result = subprocess.run([str(runner), 'selftest'], cwd=base, env=env,
                            capture_output=True, text=True, timeout=300)
    print(result.stdout, end='', flush=True)
    check('selftest without external helper exits zero', result.returncode == 0, result.stdout + result.stderr)
    check('all 40 built-in assertions pass',
          'selftest: 40 ok, 0 failed' in result.stdout and
          len(re.findall(r'^  ok    ', result.stdout, re.M)) == 40 and
          '  FAIL  ' not in result.stdout, result.stdout)
    match = re.search(r'^== unio selftest — sandbox: (.+) ==$', result.stdout, re.M)
    check('sandbox honors TMPDIR with spaces', bool(match) and Path(match[1]).parent == base)
    check('successful sandbox removed', bool(match) and not Path(match[1]).exists())
    after = {p.relative_to(conf): p.read_bytes() for p in conf.rglob('*') if p.is_file()}
    check('installed profile untouched', before == after)
    check('global Git config untouched', global_config.read_bytes() == sentinel)
