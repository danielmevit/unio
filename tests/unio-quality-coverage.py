#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""M1 acceptance-coverage regressions, run after the contract cases in the same sandbox.

Each check closes a gap found by the clause-by-clause audit in
docs/M1-ACCEPTANCE-AUDIT.md. Mock providers only; every provider command
touches a marker so "no provider was invoked" is observable.
"""
import json
import os
from pathlib import Path
import shlex
import shutil
import signal
import stat
import subprocess
import time

root = Path.cwd().parent
wt = root / 'wt/mock'
at = str(Path(os.environ['UNIO_BIN_DIR']) / 'unio')
conf = Path(os.environ['UNIO_CONF_DIR']) / 'agents.conf'
mark = root / 'cov-provider-called'
count = 0


def call(*args, code=0, env=None):
    # These M1 fixtures intentionally rerun old failure scenarios. The test
    # operator grants each blocked invocation; the separate brake suite must
    # prove that unapproved invocations cannot reach a mock provider.
    if args and args[0] == 'run':
        retry_file = root / 'coord/retries' / args[2] / 'state.json'
        if retry_file.exists() and json.loads(retry_file.read_text())['failed_attempts'] >= 2:
            grant = subprocess.run([at, 'allow-retry', args[2]], capture_output=True, text=True)
            assert grant.returncode == 0, grant.stderr
    p = subprocess.run([at, *args], capture_output=True, text=True,
                       env=dict(os.environ, **(env or {})))
    assert p.returncode == code, (args, p.returncode, code, p.stdout[-2000:], p.stderr[-2000:])
    return p


def git(*args, cwd=wt):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def check(label, condition=True):
    global count
    assert condition, label
    count += 1
    print('  coverage: ' + label)


def configure(mock='echo cov >> hello.txt; git add hello.txt; git commit -qm cov',
              review="printf '%s\\n' '```unio-findings-v1' '{\"schema_version\":1,\"findings\":[]}' '```' 'VERDICT: APPROVE'"):
    touch = 'touch ' + shlex.quote(str(mark)) + '; '
    conf.write_text('mock=bash -c ' + shlex.quote(touch + mock) + '\n'
                    + 'rev=bash -c ' + shlex.quote(touch + review) + '\n'
                    + "noop=bash -c 'exit 0'\n")


def task(name, scope='- *', checks='$ test -s hello.txt'):
    (root / 'coord/tasks' / (name + '.md')).write_text(
        f'# {name}\n## Allowed scope\n{scope}\n## Validate\n{checks}\n')


def data(name='cov'):
    return json.loads(call('result', 'mock', name).stdout)


def ready(name='cov'):
    call('run', 'mock', name)
    call('verify', 'mock', name)
    call('review', 'mock', name, 'rev')
    assert data(name)['ready_for_human_review']


def forget_provider():
    if mark.exists():
        mark.unlink()


assert git('status', '--porcelain') == '', 'coverage expects a clean mock checkout'
configure()
task('cov')
ready()
d = data()
check('result carries every contract field',
      d['schema_version'] == 1 and d['worker'] == 'mock' and d['task'] == 'cov'
      and isinstance(d['updated_at'], str)
      and set(d['revision']) == {'candidate_commit', 'base_commit', 'task_sha256', 'worktree_sha256'}
      and {'state', 'exit_code', 'revision'} <= set(d['process'])
      and {'state', 'scope', 'checks_run', 'checks_failed', 'reasons', 'revision'} <= set(d['validation'])
      and {'state', 'reviewer', 'process_exit_code', 'revision'} <= set(d['review'])
      and d['review']['reviewer'] == 'rev'
      and d['human'] == {'state': 'pending'} and d['integration'] == {'state': 'not_attempted'}
      and type(d['stale']) is bool and type(d['ready_for_human_review']) is bool)

# result and handoff are local only, and the packet carries the promised context.
forget_provider()
call('result', 'mock', 'cov')
hp = call('handoff', 'mock', 'cov')
packet = Path(hp.stdout.strip())
check('result and handoff never invoke a provider', not mark.exists())
h = (packet / 'HANDOFF.md').read_text()
check('handoff packet carries task, revision, checks, issues and next steps',
      (packet / 'task.md').read_text() == (root / 'coord/tasks/cov.md').read_text()
      and json.loads((packet / 'revision.json').read_text()) == d['current_revision']
      and all(s in h for s in ('## Completed checks', '## Outstanding issues',
                               '## Next safe actions', 'Recheck old evidence'))
      and 'sensitive information' in hp.stderr)

# A packet is published whole or not at all, and earlier packets stay intact.
parent = packet.parent
shim = root / 'cov-shim'
shim.mkdir()
(shim / 'git').write_text(
    '#!/bin/sh\n'
    'case "$*" in *"ls-files --others"*)\n'
    '  if [ -n "$COV_MUTATE" ] && [ ! -e "$COV_DONE" ]; then : > "$COV_DONE"; echo late >> "$COV_MUTATE"; fi;;\n'
    'esac\n'
    'if [ -n "$COV_HOLD" ]; then\n'
    '  for p in "$COV_PARENT"/.pending-*; do\n'
    '    if [ -d "$p" ]; then : > "$COV_HOLD"; sleep 30; fi\n'
    '  done\n'
    'fi\n'
    'exec ' + shlex.quote(shutil.which('git')) + ' "$@"\n')
os.chmod(shim / 'git', 0o755)
shimmed = str(shim) + ':' + os.environ['PATH']


def packets():
    return {p.name: {f.name: f.read_bytes() for f in p.iterdir()} for p in parent.iterdir()}


prior = packets()
p = call('handoff', 'mock', 'cov', code=2,
         env={'PATH': shimmed, 'COV_MUTATE': str(wt / 'late.txt'), 'COV_DONE': str(root / 'cov-done')})
check('candidate change during handoff publishes no packet',
      (root / 'cov-done').exists() and 'candidate changed during handoff' in p.stderr and packets() == prior)
(wt / 'late.txt').unlink()
(root / 'cov-done').unlink()
hold = root / 'cov-hold'
proc = subprocess.Popen([at, 'handoff', 'mock', 'cov'], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        env=dict(os.environ, PATH=shimmed, COV_HOLD=str(hold), COV_PARENT=str(parent)),
                        start_new_session=True)
for _ in range(400):
    if hold.exists():
        break
    time.sleep(.05)
held = hold.exists()
os.killpg(proc.pid, signal.SIGKILL)
proc.communicate()
after = packets()
pending = [n for n in after if n.startswith('.pending-')]
check('handoff killed mid-publication publishes no partial packet',
      held and pending and {n: t for n, t in after.items() if n not in pending} == prior)
hold.unlink()
packet2 = Path(call('handoff', 'mock', 'cov').stdout.strip())
check('next handoff after an interruption is complete and unique',
      packet2.name not in prior and {f.name for f in packet2.iterdir()}
      == {'task.md', 'result.json', 'revision.json', 'changed-files.json', 'HANDOFF.md'})
check('next handoff removes the interrupted scratch folder',
      not [n for n in os.listdir(parent) if n.startswith('.pending-')])
shutil.rmtree(shim)

# Old PASS text in a report is never upgraded to structured evidence.
res = root / 'coord/results/mock/cov.json'
saved = res.read_bytes()
res.unlink()
p = call('result', 'mock', 'cov', code=2)
check('old PASS report text is not trusted as structured evidence',
      'verdict=PASS' in (root / 'coord/reports/cov.md').read_text() and 'not trusted' in p.stderr)
res.write_bytes(saved)

# Reports and the ledger only ever grow.
report = root / 'coord/reports/cov.md'
ledger = root / 'coord/reports/ledger.jsonl'
r0, l0 = report.read_text(), ledger.read_text()
call('run', 'mock', 'cov')
r1, l1 = report.read_text(), ledger.read_text()
check('reports and ledger are append-only',
      r1.startswith(r0) and r1.count('## run ') == r0.count('## run ') + 1
      and l1.startswith(l0) and len(l1.splitlines()) > len(l0.splitlines()))
forget_provider()
call('review', 'mock', 'cov', 'rev', code=2)
check('no reviewer runs without current passed validation', not mark.exists())

# Reasons are kept individually, and real failure outranks missing evidence.
task('cov-none', scope='', checks='')
call('run', 'mock', 'cov-none')
call('verify', 'mock', 'cov-none', code=2)
v = data('cov-none')['validation']
check('missing scope and checks keep both reasons',
      v['state'] == 'incomplete' and v['scope'] == 'UNCHECKED' and v['reasons'] == ['missing_scope', 'missing_validate'])
task('cov-prec', scope='- no-such-path', checks='')
call('run', 'mock', 'cov-prec')
call('verify', 'mock', 'cov-prec', code=1)
v = data('cov-prec')['validation']
check('real failure outranks missing checks',
      v['state'] == 'failed' and v['scope'] == 'VIOLATION' and {'missing_validate', 'scope_violation'} <= set(v['reasons']))
task('cov-fail', checks='$ false')
call('run', 'mock', 'cov-fail')
call('verify', 'mock', 'cov-fail', code=1)
v = data('cov-fail')['validation']
check('failed check persisted with counts',
      v['state'] == 'failed' and v['checks_run'] == 1 and v['checks_failed'] == 1 and v['reasons'] == ['check_failed'])

# Worker failure stays visible next to passing checks and never becomes ready.
configure(mock='echo cov >> hello.txt; git add hello.txt; git commit -qm cov; exit 7')
call('run', 'mock', 'cov', code=7, env={'UNIO_AUTO_VERIFY': '1'})
configure()
call('review', 'mock', 'cov', 'rev')
d = data()
check('auto-verify keeps worker exit and validation; a failed worker is never ready',
      d['process']['state'] == 'failed' and d['process']['exit_code'] == 7
      and d['validation']['state'] == 'passed' and d['review']['state'] == 'approved'
      and not d['ready_for_human_review'])

# While the worker runs, its process state is running with an unknown exit.
started = root / 'cov-started'
release = root / 'cov-release'
# Wait for a release file, not a fixed sleep: reading the result can take
# longer than a short sleep on a slow drive, and then the run has finished.
configure(mock='touch ' + shlex.quote(str(started)) + '; i=0; while [ ! -e ' + shlex.quote(str(release))
          + ' ] && [ $i -lt 1200 ]; do sleep .05; i=$((i+1)); done'
          + '; echo cov >> hello.txt; git add hello.txt; git commit -qm cov')
proc = subprocess.Popen([at, 'run', 'mock', 'cov'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
for _ in range(1200):
    if started.exists():
        break
    time.sleep(.05)
mid = data()['process']
release.touch()
proc.communicate(timeout=120)
check('process is running with an unknown exit, then succeeded',
      started.exists() and mid['state'] == 'running' and mid['exit_code'] is None
      and proc.returncode == 0 and data()['process']['state'] == 'succeeded')
started.unlink()
release.unlink()
configure()

# Ignored files stay out of the revision hash; a tracked mode change is in it.
before = data()['current_revision']['worktree_sha256']
with open(root / 'repo/.git/info/exclude', 'a') as f:
    f.write('cov-ignored.log\n')
(wt / 'cov-ignored.log').write_text('noise')
same = data()['current_revision']['worktree_sha256'] == before
mode = stat.S_IMODE(os.stat(wt / 'hello.txt').st_mode)
os.chmod(wt / 'hello.txt', mode | 0o111)
moded = data()['current_revision']['worktree_sha256'] != before
os.chmod(wt / 'hello.txt', mode)
check('ignored files stay out of the hash; mode changes are in it',
      same and moded and data()['current_revision']['worktree_sha256'] == before)
(wt / 'cov-ignored.log').unlink()

# Reviewer output is preserved as raw local text and never run as shell.
ready()
executed = root / 'cov-executed'
configure(review='printf "%s\\n" ' + shlex.quote('$(touch ' + str(executed) + ')') + ' "VERDICT: APPROVE"')
old_raw = set(root.glob('coord/reports/cov.review.*'))
call('review', 'mock', 'cov', 'rev')
new_raw = set(root.glob('coord/reports/cov.review.*')) - old_raw
raw = new_raw.pop() if len(new_raw) == 1 else None
check('raw reviewer output kept locally and never executed',
      raw is not None and '$(touch' in (raw / 'stdout.log').read_text() and (raw / 'stderr.log').exists()
      and not executed.exists() and data()['review']['state'] == 'approved')
configure()

# Partial review material is refused before any reviewer is invoked.
for label, script, path, message in [
    ('binary', "printf 'a\\000b' > cov.bin", 'cov.bin', 'binary changes require manual inspection'),
    ('oversized', "head -c 310000 /dev/zero | tr '\\000' x > cov-big.txt", 'cov-big.txt',
     'exceeds 300000 bytes; nothing was clipped or reviewed'),
    ('non-UTF-8', "printf 'caf\\351\\n' > cov-latin.txt", 'cov-latin.txt', 'non-UTF-8 data'),
]:
    configure(mock=script + '; git add ' + path + '; git commit -qm ' + path)
    call('run', 'mock', 'cov')
    call('verify', 'mock', 'cov')
    forget_provider()
    p = call('review', 'mock', 'cov', 'rev', code=2)
    r = data()['review']
    check(label + ' review material refused before any reviewer runs',
          message in p.stderr and r['state'] == 'unknown' and not r['material_complete'] and not mark.exists())
    git('rm', '-q', path)
    git('commit', '-qm', 'drop ' + path)
configure()

# Live commands announce the trusted-host boundary; availability text is honest.
p = call('run', 'mock', 'cov')
call('verify', 'mock', 'cov')
q = call('review', 'mock', 'cov', 'rev')
saved_conf = conf.read_text()
conf.write_text("noop=bash -c 'echo ok'\n")
s = call('smoke')
conf.write_text(saved_conf)
check('run, review and smoke state the trusted-host boundary',
      all('Execution boundary: trusted_host' in x.stderr and 'not OS sandboxes' in x.stderr for x in (p, q, s)))
check('human availability separates installed from usable',
      'installed does not mean usable' in call('agents').stdout)

# Python 3 is checked before any provider can start.
farm = root / 'cov-nopython'
farm.mkdir()
for directory in dict.fromkeys(os.path.realpath(x) for x in ('/usr/local/bin', '/usr/bin', '/bin')):
    if not os.path.isdir(directory):
        continue
    for name in os.listdir(directory):
        target = os.path.join(directory, name)
        if (not name.startswith('python') and not os.path.lexists(farm / name)
                and os.path.isfile(target) and os.access(target, os.X_OK)):
            (farm / name).symlink_to(target)
forget_provider()
p = call('run', 'mock', 'cov', code=1, env={'PATH': str(farm)})
check('missing Python 3 stops run before any provider starts',
      'Python 3 is required' in p.stderr and not mark.exists())
shutil.rmtree(farm)

# A missing base is a failure (exit 1), judged before the snapshot needs it.
base_file = root / 'coord/base'
saved_base = base_file.read_text()
base_file.write_text('ghost-branch\n')
p = call('verify', 'mock', 'cov', code=1)
check('missing base fails verify with exit 1', 'does not exist' in p.stderr)
base_file.write_text(saved_base)

# Scratch from a writer killed mid-write is swept by the next locked write.
stale = root / 'coord/results/mock/.result-killed'
stale.write_text('{')
subprocess.run([at, 'verify', 'mock', 'cov'], capture_output=True, text=True)
check('a killed writer\'s scratch result is swept on the next write', not stale.exists())
check('no temporary result files left behind', not list((root / 'coord/results/mock').glob('.result-*')))
print(f'quality coverage regressions: {count} passed')
