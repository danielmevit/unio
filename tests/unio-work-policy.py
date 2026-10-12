#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Work-policy command/state slice: modes, tiers, lead/account, persistence.

Mock-only. Installs under a temporary directory, drives a mock project
whose path contains spaces, and exercises defaults, every enum switch,
persistence, lead/account grouping, invalid arguments, malformed/unsafe/
oversized state, preserved custom roles and the packaged guide. Mode
commands use the public protocol names yolo/balanced/thorough while the
stored schema-1 enum stays yolo/medium/safe; medium/safe remain accepted
compatibility aliases and `unio policy --json` adds a `protocol` field.
Provider commands are mock scripts; no funded provider is called.
"""
import fcntl
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

source = Path(__file__).resolve().parent.parent
passed = [0]


def check(label, condition=True):
    if not condition:
        print('FAIL ' + label)
        sys.exit(1)
    passed[0] += 1
    print('  ok %s' % label)


with tempfile.TemporaryDirectory(prefix='work-policy-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'),
               UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid',
               GIT_COMMITTER_EMAIL='mock@example.invalid',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
               UNIO_TIMEOUT='20', UNIO_VERIFY_TIMEOUT='10')
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env,
                   check=True, capture_output=True)
    at = str(base / 'bin' / 'unio')
    # Mock project path with spaces exercises quoting through every command.
    root = base / 'mock project'
    repo = root / 'repo'
    repo.mkdir(parents=True)

    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, env=env,
                              check=True, capture_output=True)

    def unio(*args, cwd=None):
        return subprocess.run([at, *args], cwd=cwd or repo, env=env,
                              capture_output=True, text=True, timeout=40)

    git('init', '-q', '-b', 'main')
    (repo / 'seed.txt').write_text('seed\n')
    git('add', 'seed.txt')
    git('commit', '-qm', 'seed')
    # Custom owner content must survive init with one policy reference.
    (repo / 'MASTER.md').write_text('# Custom owner instructions\n')
    init = unio('init', 'mock')
    check('init exits 0', init.returncode == 0)
    check('init displays default policy',
          'mode: balanced' in init.stdout and 'tier: low' in init.stdout)
    master = (repo / 'MASTER.md').read_text()
    check('custom MASTER.md preserved', '# Custom owner instructions' in master)
    check('policy reference added once', master.count('UNIO-WORK-POLICY') == 1)
    guide = root / 'coord' / 'docs' / 'WORK-MODES.md'
    check('installed guide packaged',
          guide.is_file() and 'native_workflows' in guide.read_text())
    rerun = unio('init', 'mock')
    check('init is idempotent',
          rerun.returncode == 0
          and (repo / 'MASTER.md').read_text().count('UNIO-WORK-POLICY') == 1)

    state_file = root / 'coord' / 'work-policy.json'
    check('missing state means defaults',
          'mode: balanced' in unio('mode').stdout
          and 'tier: low' in unio('tier').stdout
          and 'lead: (none)' in unio('lead').stdout
          and 'accounts: (none)' in unio('account').stdout)

    human = unio('policy')
    check('human policy shows limits and native state',
          human.returncode == 0 and 'mode: balanced' in human.stdout
          and 'tier: low' in human.stdout and 'capacity: unknown' in human.stdout
          and 'workflow_enforcement: native_workflows' in human.stdout)
    doc = json.loads(unio('policy', '--json').stdout)
    check('policy JSON matches the frozen schema',
          doc['schema_version'] == 1 and doc['mode'] == 'medium'
          and doc['protocol'] == 'balanced'
          and doc['tier'] == 'low' and doc['lead_agent'] is None
          and doc['accounts'] == {} and doc['workflow_limit_per_group'] == 1
          and doc['capacity'] == 'unknown'
          and doc['workflow_enforcement'] == 'native_workflows')

    # Every public name plus the medium/safe compatibility aliases: the
    # command displays the public name while the stored enum stays schema 1.
    for name, shown, stored in (('yolo', 'yolo', 'yolo'),
                                ('balanced', 'balanced', 'medium'),
                                ('thorough', 'thorough', 'safe'),
                                ('medium', 'balanced', 'medium'),
                                ('safe', 'thorough', 'safe')):
        out = unio('mode', name)
        doc = json.loads(unio('policy', '--json').stdout)
        check('mode switch %s shows %s, stores %s' % (name, shown, stored),
              out.returncode == 0 and out.stdout.strip() == 'mode: ' + shown
              and unio('mode').stdout.strip() == 'mode: ' + shown
              and json.loads(state_file.read_text())['mode'] == stored
              and doc['mode'] == stored and doc['protocol'] == shown)
    check('mode switches leave the tier alone',
          json.loads(unio('policy', '--json').stdout)['tier'] == 'low')
    before_tiers = json.loads(unio('policy', '--json').stdout)['mode']
    for tier, limit in (('low', 1), ('medium', 2), ('high', 4)):
        out = unio('tier', tier)
        check('tier switch %s persists with limit %d' % (tier, limit),
              out.returncode == 0 and out.stdout.strip() == 'tier: ' + tier
              and json.loads(unio('policy', '--json').stdout)['workflow_limit_per_group'] == limit)
    check('tier switches leave the mode alone',
          json.loads(unio('policy', '--json').stdout)['mode'] == before_tiers)
    unio('mode', 'medium')
    saved = json.loads(state_file.read_text())
    check('state file is exact typed schema',
          saved['schema_version'] == 1 and type(saved['schema_version']) is int
          and saved['mode'] == 'medium' and saved['tier'] == 'high'
          and saved['lead_agent'] is None and saved['accounts'] == {}
          and type(saved['updated_at']) is str)

    check('lead registers', unio('lead', 'codex').stdout.strip() == 'lead: codex'
          and unio('lead').stdout.strip() == 'lead: codex')
    check('lead reservation recorded in JSON',
          json.loads(unio('policy', '--json').stdout)['lead_agent'] == 'codex')
    check('lead clears with none', unio('lead', 'none').stdout.strip() == 'lead: (none)')
    check('account groups aliases',
          unio('account', 'opencode', 'go-primary').returncode == 0
          and unio('account', 'glm', 'go-primary').returncode == 0
          and 'opencode=go-primary' in unio('account').stdout
          and 'glm=go-primary' in unio('account').stdout)
    check('account grouping recorded in JSON',
          json.loads(unio('policy', '--json').stdout)['accounts']
          == {'glm': 'go-primary', 'opencode': 'go-primary'})
    out = unio('mode', 'thorough')
    doc = json.loads(unio('policy', '--json').stdout)
    check('mode switch keeps tier, lead and accounts independent',
          out.returncode == 0 and doc['mode'] == 'safe'
          and doc['protocol'] == 'thorough' and doc['tier'] == 'low'
          and doc['lead_agent'] is None
          and doc['accounts'] == {'glm': 'go-primary', 'opencode': 'go-primary'})
    unio('mode', 'medium')
    unio('tier', 'low')

    # A policy file written by an older released runner stays readable
    # as-is and is displayed with its public protocol name.
    old_policy = (b'{"accounts": {},"lead_agent": null,"mode": "safe",'
                  b'"schema_version": 1,"tier": "low"}\n')
    state_file.write_bytes(old_policy)
    out = unio('policy')
    doc = json.loads(unio('policy', '--json').stdout)
    check('frozen old policy accepted and shown with its public name',
          out.returncode == 0 and 'mode: thorough' in out.stdout
          and doc['mode'] == 'safe' and doc['protocol'] == 'thorough'
          and state_file.read_bytes() == old_policy)
    unio('mode', 'medium')

    good = state_file.read_bytes()

    def fails_unchanged(label, args):
        out = unio(*args)
        check(label, out.returncode != 0 and state_file.read_bytes() == good)

    fails_unchanged('invalid mode rejected', ('mode', 'turbo'))
    fails_unchanged('surplus mode args rejected', ('mode', 'balanced', 'extra'))
    fails_unchanged('invalid tier rejected', ('tier', 'ultra'))
    fails_unchanged('surplus tier args rejected', ('tier', 'low', 'extra'))
    fails_unchanged('invalid lead label rejected', ('lead', 'bad name'))
    fails_unchanged('surplus lead args rejected', ('lead', 'codex', 'extra'))
    fails_unchanged('single account arg rejected', ('account', 'opencode'))
    fails_unchanged('triple account args rejected', ('account', 'a', 'b', 'c'))
    fails_unchanged('bad account group rejected', ('account', 'opencode', '-x'))
    fails_unchanged('unknown policy flag rejected', ('policy', '--yaml'))
    fails_unchanged('surplus policy args rejected', ('policy', '--json', 'extra'))

    def fails_state_unchanged(label, payload):
        state_file.write_bytes(payload)
        out = unio('policy')
        check(label, out.returncode != 0 and state_file.read_bytes() == payload)
        state_file.write_bytes(good)

    fails_state_unchanged('garbage state fails locally', b'not json\n')
    fails_state_unchanged('duplicate keys rejected',
                          b'{"schema_version":1,"mode":"medium","mode":"yolo",'
                          b'"tier":"low","lead_agent":null,"accounts":{}}')
    fails_state_unchanged('unknown keys rejected',
                          b'{"schema_version":1,"mode":"medium","tier":"low",'
                          b'"lead_agent":null,"accounts":{},"quota":9}')
    fails_state_unchanged('unknown schema rejected',
                          b'{"schema_version":2,"mode":"medium","tier":"low",'
                          b'"lead_agent":null,"accounts":{}}')
    fails_state_unchanged('invalid enum rejected',
                          b'{"schema_version":1,"mode":"turbo","tier":"low",'
                          b'"lead_agent":null,"accounts":{}}')
    fails_state_unchanged('wrong lead type rejected',
                          b'{"schema_version":1,"mode":"medium","tier":"low",'
                          b'"lead_agent":7,"accounts":{}}')
    big = {'schema_version': 1, 'mode': 'medium', 'tier': 'low',
           'lead_agent': None, 'accounts': {}, 'updated_at': 'x' * 70000}
    fails_state_unchanged('oversized state refused', json.dumps(big).encode())
    link = state_file.with_suffix('.link')
    link.write_bytes(good)
    state_file.unlink()
    try:
        state_file.symlink_to(link)
        out = unio('policy')
        check('symlink state refused without reset',
              out.returncode != 0 and state_file.is_symlink())
    finally:
        state_file.unlink(missing_ok=True)
        state_file.write_bytes(good)
    hard = root / 'coord' / 'work-policy-hard.json'
    hard.write_bytes(good)
    state_file.unlink()
    try:
        os.link(hard, state_file)
        out = unio('policy')
        check('hardlinked state refused without reset', out.returncode != 0)
    finally:
        state_file.unlink(missing_ok=True)
        state_file.write_bytes(good)
        hard.unlink(missing_ok=True)
    fifo = root / 'coord' / 'work-policy-fifo'
    if not fifo.exists():
        os.mkfifo(fifo)
    state_file.unlink()
    try:
        os.rename(fifo, state_file)
        out = subprocess.run([at, 'policy'], cwd=repo, env=env,
                             capture_output=True, text=True, timeout=20)
        check('nonregular state refused without reset', out.returncode != 0)
    finally:
        try:
            os.unlink(state_file)
        except OSError:
            pass
        state_file.write_bytes(good)

    status = unio('status')
    check('status displays policy',
          status.returncode == 0 and 'mode: balanced' in status.stdout)
    check('help documents the switches',
          'unio mode [yolo|balanced|thorough]' in unio('help').stdout
          and 'medium/safe stay accepted' in unio('help').stdout
          and 'unio policy [--json]' in unio('help').stdout)
    completion = (base / 'completion' / 'unio').read_text()
    check('completion offers switches and values',
          'mode tier lead account policy' in completion
          and 'yolo balanced thorough medium safe' in completion
          and 'low medium high' in completion)
    check('fresh guide still installed', guide.is_file())

    # mock regressions
    conf_dir = base / 'conf' / 'agents.conf'
    mock_success = repo / 'mock_success.sh'
    mock_success.write_text(
        "#!/bin/bash\n"
        "if [ -n \"${MOCK_MARKER:-}\" ]; then printf 'ran\\n' >> \"$MOCK_MARKER\"; fi\n"
        "exit 0\n")
    mock_success.chmod(0o755)
    mock_fail = repo / 'mock_fail.sh'
    mock_fail.write_text("#!/bin/bash\nexit 1\n")
    mock_fail.chmod(0o755)
    mock_timeout = repo / 'mock_timeout.sh'
    mock_timeout.write_text("#!/bin/bash\nsleep 10\nexit 0\n")
    mock_timeout.chmod(0o755)

    with open(conf_dir, 'a') as f:
        f.write(f"mock_success=bash '{mock_success}'\n")
        f.write(f"mock_fail=bash '{mock_fail}'\n")
        f.write(f"mock_timeout=bash '{mock_timeout}'\n")

    (root / 'coord' / 'tasks').mkdir(parents=True, exist_ok=True)
    (root / 'coord' / 'tasks' / 'task_s.md').write_text("success")
    (root / 'coord' / 'tasks' / 'task_f.md').write_text("fail")
    (root / 'coord' / 'tasks' / 'task_t.md').write_text("timeout")
    (root / 'coord' / 'tasks' / 'task_b.md').write_text("bad")

    unio('init', 'mock_success')
    unio('init', 'mock_fail')
    unio('init', 'mock_timeout')

    out_s = unio('run', 'mock_success', 'task_s')
    check('success run releases slot', out_s.returncode == 0)
    header = root / 'coord' / 'reports' / 'task_s.prompt.md'
    check('worker header shows the public protocol name',
          header.is_file() and 'mode: balanced' in header.read_text())

    out_f = unio('run', 'mock_fail', 'task_f')
    check('fail run releases slot', out_f.returncode == 1)

    bad_task = root / 'coord' / 'tasks' / 'task_b.md'
    bad_task.unlink()
    out_b = unio('run', 'mock_success', 'task_b')
    check('broker failure releases slot', out_b.returncode != 0)

    env['UNIO_TIMEOUT'] = '1'
    out_t = unio('run', 'mock_timeout', 'task_t')
    check('provider timeout enforced and released', out_t.returncode != 0)
    del env['UNIO_TIMEOUT']

    def locked_slots():
        base = root / 'coord' / '.locks' / 'work-policy-slots'
        held = []
        if not base.is_dir():
            return held
        for slot in base.rglob('wpslot-*.json'):
            if slot.is_symlink():
                continue
            fd = os.open(slot, os.O_RDONLY)
            try:
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    held.append(slot)
                else:
                    fcntl.flock(fd, fcntl.LOCK_UN)
            finally:
                os.close(fd)
        return held

    def descendants(pid):
        found = []
        try:
            raw = Path('/proc/%s/task/%s/children' % (pid, pid)).read_text().split()
        except OSError:
            return found
        for tok in raw:
            if tok.isdigit():
                child = int(tok)
                found.append(child)
                found.extend(descendants(child))
        return found

    marker = repo / 'provider-marker'
    marker.unlink(missing_ok=True)
    env['MOCK_MARKER'] = str(marker)
    env['UNIO_POLICY_ADMIT_PARTIAL'] = '1'
    (root / 'coord' / 'tasks' / 'task_p.md').write_text('partial\n')
    started = time.monotonic()
    out_p = unio('run', 'mock_success', 'task_p')
    partial_elapsed = time.monotonic() - started
    check('partial broker reply refuses before any provider',
          out_p.returncode == 2 and partial_elapsed < 12 and not marker.exists()
          and locked_slots() == [])
    del env['UNIO_POLICY_ADMIT_PARTIAL']
    marker.unlink(missing_ok=True)

    retry = root / 'coord' / 'retries' / 'task_q'
    retry.mkdir(parents=True)
    (root / 'coord' / 'tasks' / 'task_q.md').write_text('quality\n')
    (retry / 'state.json').write_text(json.dumps({
        'schema_version': 1, 'task': 'task_q', 'failed_attempts': 2,
        'retry_granted': False, 'latest': {}}))
    out_q = unio('run', 'mock_success', 'task_q')
    check('quality-start failure returns nonzero and starts no provider',
          out_q.returncode != 0 and not marker.exists() and locked_slots() == [])
    del env['MOCK_MARKER']

    hold = repo / 'mock_hold.sh'
    hold.write_text(
        "#!/bin/bash\n"
        "barrier=\"${MOCK_BARRIER:-}\"\n"
        "if [ -n \"$barrier\" ]; then\n"
        "  touch \"$barrier.started\"\n"
        "  while [ ! -f \"$barrier.release\" ]; do sleep 0.05; done\n"
        "fi\n"
        "exit 0\n")
    hold.chmod(0o755)
    with open(conf_dir, 'a') as handle:
        handle.write("mock_hold=bash '%s'\n" % hold)
    unio('init', 'mock_hold')
    (root / 'coord' / 'tasks' / 'task_h.md').write_text('hold\n')
    barrier = repo / 'holdbar'
    env['MOCK_BARRIER'] = str(barrier)
    proc = subprocess.Popen(
        [at, 'run', 'mock_hold', 'task_h'], cwd=repo, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        start_new_session=True)
    try:
        seen = False
        for _ in range(100):
            if (Path(str(barrier) + '.started')).exists():
                seen = True
                break
            time.sleep(0.1)
        check('holder stays up while the provider runs', seen and proc.poll() is None)
        slots = list((root / 'coord' / '.locks' / 'work-policy-slots').rglob('wpslot-*.json'))
        check('slot stays visible while the provider runs', len(slots) == 1 and slots[0].is_file())
        holder = None
        for pid in [proc.pid, *descendants(proc.pid)]:
            fd_dir = Path('/proc/%s/fd' % pid)
            if not fd_dir.is_dir():
                continue
            for fdpath in fd_dir.iterdir():
                try:
                    target = os.readlink(fdpath)
                except OSError:
                    continue
                if target == str(slots[0]):
                    holder = pid
        check('exact holder owns the live slot', holder is not None and holder != proc.pid)
        Path(str(barrier) + '.release').touch()
        out_h, err_h = proc.communicate(timeout=30)
        released = (proc.returncode == 0 and not Path('/proc/%s' % holder).exists()
                    and not slots[0].exists() and locked_slots() == [])
        if not released:
            print(out_h)
            print(err_h)
            print('rc', proc.returncode)
        check('holder release reaps the owned holder', released)
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                proc.wait(timeout=5)
    del env['MOCK_BARRIER']

    # Source the installed closer by itself. Closing an owned descriptor must
    # not leave this shell's stderr on /dev/null.
    close_lines = Path(at).read_text().splitlines()
    try:
        close_start = close_lines.index('policy_close_admission_fds() {')
        close_end = close_lines.index('}', close_start + 1)
    except ValueError:
        close_start = None
        close_end = None
    close_fn = ''
    if close_start is not None and close_lines[close_end] == '}':
        close_fn = '\n'.join(close_lines[close_start:close_end + 1]) + '\n'
    close_probe = None
    if close_fn:
        close_probe = subprocess.run(
            ['bash', '-c', close_fn + (
                'set -euo pipefail\n'
                'exec {owned}>/dev/null\n'
                'POLICY_RD=$owned\n'
                'POLICY_WR=\n'
                'POLICY_IN=\n'
                'policy_close_admission_fds\n'
                'if [ -e "/proc/$$/fd/$owned" ]; then\n'
                '  echo "still-open" >&2\n'
                '  exit 3\n'
                'fi\n'
                'echo "stdout-sentinel"\n'
                'echo "stderr-sentinel" >&2\n'
            )],
            capture_output=True, text=True, timeout=20)
    if (close_probe is None or close_probe.returncode != 0
            or close_probe.stderr != 'stderr-sentinel\n'):
        if close_probe is not None:
            print(close_probe.stdout)
            print(close_probe.stderr)
            print('rc', close_probe.returncode)
    check('closing an admission fd keeps caller stderr',
          close_probe is not None and close_probe.returncode == 0
          and close_probe.stdout == 'stdout-sentinel\n'
          and close_probe.stderr == 'stderr-sentinel\n')

print('work-policy: %d checks passed' % passed[0])
