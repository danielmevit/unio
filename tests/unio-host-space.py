#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Host-space regressions: deterministic metadata and private provider fixtures."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('host_space', ROOT / 'tools/host-space.py')
h = importlib.util.module_from_spec(spec)
spec.loader.exec_module(h)
checks = 0


def check(label, value, detail=''):
    global checks
    if not value:
        raise AssertionError(label + ': ' + str(detail))
    checks += 1
    print('  ok ' + label, flush=True)


def known(kind, free=1024**4):
    return dict(status='known', kind=kind, volume='E:\\' if kind == 'wsl-host' else 'device:1',
                available_bytes=free, reason=None)


for value in ('', '-1', '+2097152', '1.0', ' 2097152', '2097152\n', '1', str(1024**5 + 1), '9'*100):
    try:
        h.thresholds({'UNIO_DISK_MIN_FREE_BYTES': value})
    except ValueError:
        check('invalid threshold rejected ' + repr(value[:20]), True)
    else:
        raise AssertionError('invalid threshold accepted')
for env in ({'UNIO_DISK_MIN_FREE_BYTES': str(11*h.GIB)},
            {'UNIO_DISK_WARN_FREE_BYTES': 'no'}):
    try:
        h.thresholds(env)
    except ValueError:
        check('invalid warning relation/value rejected', True)
    else:
        raise AssertionError('warning accepted')
check('inclusive threshold endpoints', h.thresholds({'UNIO_DISK_MIN_FREE_BYTES': str(1024**2),
      'UNIO_DISK_WARN_FREE_BYTES': str(1024**5)})['warn_free_bytes'] == 1024**5)

for metadata in ('{}', '[]', '{"verified":true}', 'x'*4097,
                 json.dumps(dict(verified=True, volume='E:\\;evil', available_bytes=1)),
                 json.dumps(dict(verified=True, volume='E:\\', available_bytes=True)),
                 json.dumps(dict(verified=True, volume='E:\\', available_bytes=-1))):
    check('unsafe/ambiguous metadata Unknown', h.windows_metadata(metadata)['status'] == 'unknown')
check('native Windows verified metadata parser', h.windows_metadata(json.dumps(dict(
      verified=True, volume='e:\\', available_bytes=1234)), 'windows')['available_bytes'] == 1234)

with patch.object(h, 'filesystem', side_effect=lambda p, k: known(k)), \
     patch.object(h.platform, 'release', return_value='microsoft-standard-WSL2'), \
     patch.dict(os.environ, {}, clear=True):
    for free, expected in ((0, 'critical'), (2*h.GIB-1, 'critical'), (2*h.GIB, 'warning'),
                           (10*h.GIB-1, 'warning'), (10*h.GIB, 'adequate')):
        with patch.object(h, 'wsl_host', return_value=known('wsl-host', free)):
            doc = h.observe('/fixture')
            check('huge ext4/host boundary ' + str(free), doc['overall'] == expected)
    for low_kind in ('project', 'coordination', 'temp'):
        with patch.object(h, 'filesystem', side_effect=lambda p, k: known(k, 0 if k == low_kind else 1024**4)), \
             patch.object(h, 'wsl_host', return_value=known('wsl-host')):
            check(low_kind+' critical independently', h.observe('/fixture')['overall'] == 'critical')
    with patch.object(h, 'wsl_host', return_value=h.unknown('wsl-host', 'ambiguous')):
        check('Unknown never adequate', h.observe('/fixture')['overall'] == 'unknown')
        with patch.object(h, 'filesystem', side_effect=lambda p, k: known(k, 0)):
            check('critical dominates Unknown', h.observe('/fixture')['overall'] == 'critical')

with patch.dict(os.environ, {'WSL_DISTRO_NAME': "a'; $(touch injected); `bad`"}), \
     patch.object(h.shutil, 'which', return_value='/fixture/powershell.exe'):
    def probe(argv, payload):
        check('distro injection absent from executable script', 'touch injected' not in str(argv))
        check('distro passed as JSON data', json.loads(payload)['distro'] == os.environ['WSL_DISTRO_NAME'])
        return '{}'
    with patch.object(h, 'bounded_probe', side_effect=probe):
        check('ambiguous WSL Unknown', h.wsl_host()['status'] == 'unknown')
    with patch.object(h, 'bounded_probe', side_effect=ValueError('host probe timed out')):
        check('timeout Unknown with reason', 'timed out' in h.wsl_host()['reason'])
    with patch.object(h.shutil, 'which', return_value=None):
        check('unavailable interop Unknown', h.wsl_host()['status'] == 'unknown')

# Filesystem calls are isolated too; a hung statvfs is Unknown, never adequate.
with patch.object(h, 'bounded_probe', side_effect=ValueError('host probe timed out')):
    check('filesystem timeout Unknown', h.filesystem('/fixture', 'project')['status'] == 'unknown')
with patch.object(h, 'bounded_probe', return_value='{"available_bytes":123,"device":7}'):
    check('filesystem available bytes preserved', h.filesystem('/fixture', 'project')['available_bytes'] == 123)
with patch.object(h, 'bounded_probe', return_value='{"available_bytes":-1,"device":7}'):
    check('invalid filesystem metadata Unknown', h.filesystem('/fixture', 'project')['status'] == 'unknown')
with patch.dict(os.environ, {'TMPDIR': '/definitely-missing-unio-temp-directory'}):
    check('read-only temp selection fallback',
          h.filesystem(h.temp_directory(), 'temp')['status'] == 'known')

for script, expected in (("import time; time.sleep(10)", 'timed out'),
                         ("import sys; sys.stdout.write('x'*100000); sys.stdout.flush()", 'exceeded bound')):
    start = time.monotonic()
    try:
        h.bounded_probe([sys.executable, '-c', script], b'{}\n', timeout=0.2)
    except ValueError as exc:
        check('bounded probe ' + expected, expected in str(exc))
    else:
        raise AssertionError('probe accepted')
    check('bounded elapsed below 2 seconds', time.monotonic() - start < 2)

# A finished leader must still be waitable at the exact moment killpg runs.
# This catches reaping before group cleanup, even when the PID is not reused.
real_killpg = os.killpg

def owned_killpg(pid, sig):
    ended = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
    check('leader ownership pinned through group cleanup', ended is not None)
    return real_killpg(pid, sig)

with patch.object(h.os, 'killpg', side_effect=owned_killpg):
    check('successful probe output', h.bounded_probe([sys.executable, '-c',
          "print('{}')"], b'{}\n').strip() == '{}')

# Both pipe-held descendants and an exited stdout with a live leader are bounded.
for script in (
    "import os,time; pid=os.fork(); time.sleep(10) if pid == 0 else os._exit(0)",
    "import os,time; os.close(1); os.close(2); time.sleep(10)",
):
    start = time.monotonic()
    try:
        h.bounded_probe([sys.executable, '-c', script], b'{}\n', timeout=0.2)
    except ValueError as exc:
        check('descendant/live leader deadline', 'timed out' in str(exc))
    else:
        raise AssertionError('unbounded child accepted')
    check('total probe including cleanup below 2 seconds', time.monotonic()-start < 2)
with patch.object(h.subprocess, 'Popen') as popen:
    try:
        h.bounded_probe(['unused'], b'x'*(h.LIMIT+1))
    except ValueError:
        check('oversized input refused before process', not popen.called)
    else:
        raise AssertionError('oversized payload accepted')

with tempfile.TemporaryDirectory(prefix='host-space-') as temporary:
    base = Path(temporary)
    env = dict(os.environ, HOME=str(base), UNIO_BIN_DIR=str(base/'bin'),
               UNIO_CONF_DIR=str(base/'conf'), UNIO_COMPLETION_DIR=str(base/'completion'),
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0', UNIO_TIMEOUT='10',
               GIT_AUTHOR_NAME='fixture', GIT_COMMITTER_NAME='fixture',
               GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_EMAIL='fixture@example.invalid')
    def run(argv, cwd=None, extra=None):
        return subprocess.run(argv, cwd=cwd or base, env=dict(env, **(extra or {})),
                              capture_output=True, text=True, timeout=60)
    out = run(['bash', str(ROOT/'unio-install.sh')])
    check('private install', out.returncode == 0, out.stderr)
    repo = base/'project'/'repo'
    repo.mkdir(parents=True)
    for args in (['init', '-q', '-b', 'main'], ['commit', '--allow-empty', '-qm', 'seed']):
        out = run(['git', *args], repo)
        check('fixture git ' + args[0], out.returncode == 0, out.stderr)
    at = str(base/'bin/unio')
    def cli(*args, extra=None):
        return run([at, *args], repo, extra)
    out = cli('init', 'mock')
    check('fixture init', out.returncode == 0, out.stderr)
    coord = repo.parent/'coord'
    provider = base/'provider.sh'
    marker = base/'provider-canary'
    provider.write_text('#!/bin/sh\nprintf ran >> "$HOST_CANARY"\nprintf "VERDICT: APPROVE\\n"\n')
    (base/'conf/agents.conf').write_text(''.join(f"{name}=sh '{provider}'\n" for name in ('mock', 'rev1', 'rev2')))
    env['HOST_CANARY'] = str(marker)
    # Private launcher injects measurements into the byte-identical embedded
    # helper. No production test flag or real mount/host state is changed.
    shim = base/'shim'
    shim.mkdir()
    launcher = shim/'python3'
    injection = '''
if 'host_space' in globals():
    host_space['filesystem'] = lambda path, kind: dict(status='known',kind=kind,volume='device:fixture',available_bytes=1024**4,reason=None)
    host_space['platform'].release = lambda: 'microsoft-WSL2'
    def fixture_host():
        mode = __import__('os').environ.get('HOST_FIXTURE', 'low')
        if mode == 'unknown':
            return host_space['unknown']('wsl-host', 'ambiguous fixture mapping')
        return dict(status='known',kind='wsl-host',volume='E:\\\\',available_bytes=1 if mode == 'low' else 1024**4,reason=None)
    host_space['wsl_host'] = fixture_host
'''
    launcher.write_text(f'''#!{sys.executable}
import os,sys
if len(sys.argv)>1 and sys.argv[1]=='-':
    code=sys.stdin.read()
    code=code.replace('# END QUALITY HOST SPACE', {injection!r}+'\\n# END QUALITY HOST SPACE')
    sys.argv=sys.argv[1:]
    exec(compile(code,'<fixture>','exec'),{{'__name__':'__main__'}})
else:
    os.execv({sys.executable!r},[{sys.executable!r},*sys.argv[1:]])
''')
    launcher.chmod(0o755)
    env['PATH'] = str(shim) + ':' + env['PATH']
    def task(name):
        (coord/'tasks'/f'{name}.md').write_text('Private task\n## Allowed scope\n- hello.txt\n## Validate\n$ true\n')
    def snapshot():
        paths = list((coord/'retries').rglob('*')) if (coord/'retries').exists() else []
        paths += [coord/'lead-budget.json']
        return {str(p.relative_to(coord)):p.read_bytes() for p in paths if p.is_file()}
    # Existing state must remain byte-identical, not merely absent.
    retry = coord/'retries/low-fg/state.json'
    retry.parent.mkdir(parents=True)
    retry.write_text(json.dumps(dict(schema_version=1, task='low-fg', failed_attempts=2,
                                   retry_granted=True, latest={})))
    consent = coord/'lead-budget.json'
    check('private lead registration', cli('lead','mock').returncode == 0)
    for reviewer in ('rev1','rev2'):
        check('private reviewer account mapping', cli('account',reviewer,'mock').returncode == 0)
    for name, args in (('low-fg', ('run','mock','low-fg')),
                       ('low-bg', ('run','-b','mock','low-bg')),
                       ('low-review', ('review','mock','low-review','rev1')),
                       ('low-set', ('review-set','mock','low-set','rev1','rev2'))):
        task(name)
        retry_state = coord/'retries'/name/'state.json'
        retry_state.parent.mkdir(parents=True, exist_ok=True)
        retry_state.write_text(json.dumps(dict(schema_version=1, task=name, failed_attempts=2,
                                              retry_granted=True, latest={})))
        grant_agent = 'mock' if args[0] == 'run' else 'rev1'
        grant_worker = 'mock' if args[0] == 'run' else 'rev1'
        out = cli('lead-budget','grant',grant_agent,grant_worker,name,'run' if args[0] == 'run' else 'review')
        check(name+' real ready consent', out.returncode == 0, out.stderr)
        before = snapshot()
        out = cli(*args)
        text = out.stdout+out.stderr
        check(name+' critical refusal', out.returncode == 2 and 'critical disk space' in text, text)
        check(name+' no provider or background claim', not marker.exists() and 'started in background' not in text)
        check(name+' retry/consent unchanged', snapshot() == before)
        slots = coord/'.locks/work-policy-slots'
        check(name+' no slot allocation', not list(slots.rglob('wpslot-*')))
    for name, args in (('bad-fg', ('run','mock','bad-fg')),
                       ('bad-bg', ('run','-b','mock','bad-bg')),
                       ('bad-review', ('review','mock','bad-review','rev1')),
                       ('bad-set', ('review-set','mock','bad-set','rev1','rev2'))):
        task(name)
        retry_state = coord/'retries'/name/'state.json'
        retry_state.parent.mkdir(parents=True, exist_ok=True)
        retry_state.write_text(json.dumps(dict(schema_version=1, task=name, failed_attempts=2,
                                              retry_granted=True, latest={})))
        out = cli('lead-budget','grant','mock' if args[0]=='run' else 'rev1',
                  'mock' if args[0]=='run' else 'rev1',name,'run' if args[0]=='run' else 'review')
        check(name+' real ready consent', out.returncode == 0, out.stderr)
        before = snapshot()
        out = cli(*args, extra={'UNIO_DISK_MIN_FREE_BYTES':'not-decimal'})
        check(name+' invalid settings before provider', out.returncode == 2 and 'decimal integer' in out.stderr
              and not marker.exists() and snapshot() == before, out.stdout+out.stderr)
    (coord/'STOP').write_text('fixture stop\n')
    for mode, expected, exit_code in (('low','critical',2), ('unknown','unknown',0), ('adequate','adequate',0)):
        before = {str(p.relative_to(coord)):p.read_bytes() for p in coord.rglob('*') if p.is_file()}
        out = cli('disk','--json',extra={'HOST_FIXTURE':mode})
        doc = json.loads(out.stdout)
        check('disk while STOP '+mode, out.returncode == exit_code and doc['overall'] == expected, out.stderr)
        check('versioned observation fields', doc['schema_version'] == 1 and doc['observed_at']
              and len(doc['measurements']) == 4 and doc['thresholds']['min_free_bytes'] == 2*h.GIB)
        after = {str(p.relative_to(coord)):p.read_bytes() for p in coord.rglob('*') if p.is_file()}
        check('disk read-only '+mode, before == after)
    (coord/'STOP').unlink()
    consent.unlink()
    check('private lead cleared for healthy routes', cli('lead','none').returncode == 0)
    for reviewer in ('rev1','rev2'):
        check('private healthy account mapping', cli('account',reviewer,reviewer).returncode == 0)
    for mode in ('adequate','unknown'):
        name = 'usable-'+mode
        task(name)
        marker.unlink(missing_ok=True)
        out = cli('run','mock',name,extra={'HOST_FIXTURE':mode})
        check(mode+' admits Source', out.returncode == 0 and marker.exists(), out.stdout+out.stderr)
        check(mode+' observation visible', 'disk observation: '+mode in out.stderr, out.stderr)
        # Prepare current native verification evidence for both review routes.
        wt = repo.parent/'wt/mock'
        (wt/'hello.txt').write_text(mode+'\n')
        for argv in (['git','add','hello.txt'], ['git','commit','-qm','fixture '+mode]):
            out = run(argv, wt)
            check('private candidate commit', out.returncode == 0, out.stderr)
        out = cli('verify','mock',name,extra={'HOST_FIXTURE':mode})
        check(mode+' fixture verify', out.returncode == 0, out.stdout+out.stderr)
        for args in (('review','mock',name,'rev1'), ('review-set','mock',name,'rev1','rev2')):
            marker.unlink(missing_ok=True)
            out = cli(*args,extra={'HOST_FIXTURE':mode})
            check(mode+' '+args[0]+' reaches provider', marker.exists(), out.stdout+out.stderr)

print(f'unio-host-space: {checks} checks passed')
