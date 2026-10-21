#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed admission lifecycle regression; owned scratch and fake providers only."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
SCRATCH = SOURCE / 'tmp' / 'admission-tests'
SCRATCH.mkdir(parents=True, exist_ok=True)

def run(argv, env, cwd, timeout=60):
    return subprocess.run(argv, env=env, cwd=cwd, text=True,
                          capture_output=True, timeout=timeout)

with tempfile.TemporaryDirectory(dir=SCRATCH, prefix='installed-') as tmp:
    base = Path(tmp)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
               UNIO_COMPLETION_DIR=str(base/'completion'), TMPDIR=str(base),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0')
    install = run(['bash', str(SOURCE/'unio-install.sh')], env, SOURCE)
    assert install.returncode == 0, install.stderr
    at = base/'bin/unio'
    pristine = at.read_text()
    root = base/'project'
    repo = root/'repo'
    repo.mkdir(parents=True)
    for args in (['git', 'init', '-b', 'main'], ['git', 'commit', '--allow-empty', '-m', 'mock'],
                 [str(at), 'init', 'mock']):
        p = run(args, env, repo)
        assert p.returncode == 0, p.stderr
    task = root/'coord/tasks/test.md'
    task.write_text('mock admission material\n')
    # Exercise the actual installed Bash and embedded Python, stopping before
    # CLI dispatch. Only the provider boundary is replaced with a marker.
    library = base/'installed-functions.sh'
    harness = base/'admit.sh'
    harness.write_text('''#!/bin/bash
source "$1"
if policy_admit_hold "$2" mock mock test "$3" "$2/coord/tasks/test.md"; then
  printf 'configured_timeout=%s\\n' "$POLICY_ADMISSION_TIMEOUT"
  printf 'fake provider\\n' >> "$2/provider-marker"
  policy_release_slot "$2"
else
  exit 2
fi
''')
    hook = "        # Fail closed. Tests use this to prove a partial reply cannot admit."
    def attempt(name, injection='', bound='3', kind='run', expected=None, late=False):
        installed = pristine.split('case "${1:-help}" in\n')[0]
        target = "            sys.stdout.write('%s\\n%s\\n%s\\n%s\\nCOMPLETE\\n' % (" if late else hook
        assert target in installed
        library.write_text(installed.replace(target, injection+'\n'+target, 1))
        marker = root/'provider-marker'
        marker.unlink(missing_ok=True)
        e = dict(env)
        if bound is None:
            e.pop('UNIO_ADMISSION_TIMEOUT', None)
        else:
            e['UNIO_ADMISSION_TIMEOUT'] = bound
        before = time.monotonic()
        p = run(['bash', str(harness), str(library), str(root), kind], e, repo, timeout=45)
        elapsed = time.monotonic()-before
        if expected is None:
            assert p.returncode == 0 and marker.exists(), (name, p.returncode, p.stdout, p.stderr)
            assert 'configured_timeout='+str(30 if bound is None else int(bound)) in p.stdout, p.stdout
        else:
            assert p.returncode == 2 and not marker.exists(), (name, p.returncode, p.stderr)
            assert expected in p.stderr, (name, expected, p.stderr)
            assert 'Free the group' not in p.stderr, p.stderr
        assert not list((root/'coord/.locks').glob('.ipc-*')), name
        # Slots killed before reply can leave unlocked historical metadata;
        # the normal sweep must reclaim it, never an active lock.
        assert not list((root/'coord/.locks').glob('work-policy-slots/*/wpslot-*.json')), name
        print(f'ok {name} ({elapsed:.2f}s)', flush=True)
        return p
    attempt('old five second bound reproduction', '        import time; time.sleep(6)', '5', expected='phase=deadline')
    attempt('delayed over old five seconds', '        import time; time.sleep(6)', '20')
    attempt('deadline', '        import time; time.sleep(6)', '1', expected='phase=deadline')
    attempt('partial complete line', "        print('grp', flush=True); sys.exit(0)", expected='phase=partial')
    attempt('partial unterminated line', "        sys.stdout.write('grp'); sys.stdout.flush(); sys.exit(0)", expected='phase=partial')
    attempt('EOF', '        sys.exit(0)', expected='phase=eof')
    attempt('holder death', '        os.kill(os.getpid(), 9)', expected='phase=holder-exit')
    attempt('holder refusal', "        fail('mock holder refused')", expected='phase=holder-refusal')
    attempt('storage failure', "        raise OSError('mock storage unavailable')", expected='UNIO_STORAGE_ERROR')
    def cli(*args):
        p = run([str(at), *args], env, repo)
        assert p.returncode == 0, (args, p.stderr)
        return p
    cli('lead', 'mock')
    attempt('lead capacity refusal', expected='at cap 1')
    cli('tier', 'medium')
    attempt('lead budget refusal', expected='lead-budget grant')
    cli('lead-budget', 'grant', 'mock', 'mock', 'test', 'run')
    grants = root/'coord/lead-budget.json'
    original_grants = grants.read_bytes()
    # A sentinel proves the holder was never invoked for invalid bounds.
    sentinel = base/'holder-started'
    for kind in ('run', 'review'):
        for bound in ('', '0', '301', '-1', '1.5', '999999999999999999999', 'x'):
            attempt('invalid '+kind+' '+repr(bound), f"        open({str(sentinel)!r}, 'w').close()", bound, kind,
                    expected='UNIO_ADMISSION_CONFIG')
            assert not sentinel.exists()
            assert grants.read_bytes() == original_grants
    attempt('deadline after grant consumption', '            import time; time.sleep(6)', '1',
            expected='phase=deadline', late=True)
    assert json.loads(grants.read_text())['grants'][-1]['state'] == 'used'
    cli('lead', 'none')
    # Invalid configuration must fail at every public entry point, including
    # background Source, before locks, material preparation or grant effects.
    for args in (('run', 'mock', 'test'), ('run', '-b', 'mock', 'test'),
                 ('review', 'mock', 'test', 'reviewer'),
                 ('review-set', 'mock', 'test', 'reviewer1', 'reviewer2')):
        before_grants = grants.read_bytes()
        failed = run([str(at), *args], dict(env, UNIO_ADMISSION_TIMEOUT='0'), repo)
        assert failed.returncode == 2 and 'UNIO_ADMISSION_CONFIG' in failed.stderr, (args, failed.stderr)
        assert grants.read_bytes() == before_grants
        assert not (root/'provider-marker').exists()
        assert not list((root/'coord/.locks').glob('.ipc-*'))
        print('ok installed invalid '+args[0]+(' background' if '-b' in args else ''), flush=True)
    attempt('default thirty second configuration', bound=None)
    attempt('upper bound configuration', bound='300')
    attempt('explicit five second compatibility', bound='5')
    attempt('review admission', kind='review')
    report = root/'coord/reports/test.md'
    history = report.read_bytes()
    report.chmod(0o400)
    try:
        attempt('stderr survives report write failure', '        sys.exit(0)', expected='phase=eof')
        assert report.read_bytes() == history
    finally:
        report.chmod(0o600)
    # Native Source STOP check at the installed CLI entry point.
    mock = base/'provider.sh'
    mock.write_text('echo called >> "'+str(root/'provider-marker')+'"\nexit 7\n')
    (base/'conf/agents.conf').write_text('mock=bash "'+str(mock)+'"\n')
    (root/'provider-marker').unlink(missing_ok=True)
    cli('stop')
    stopped = run([str(at), 'run', 'mock', 'test'], env, repo)
    assert stopped.returncode != 0 and not (root/'provider-marker').exists(), stopped.stderr
    print('ok installed Source STOP blocks fake provider', flush=True)
print('Installed admission checks passed; fake provider only.')
