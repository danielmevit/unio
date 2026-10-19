#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Storage admission regressions: private fixtures and deterministic faults only."""
import errno
import json
import time
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parent.parent
INSTALLER = (SOURCE / 'unio-install.sh').read_text()
QUALITY = INSTALLER.split("<<'QUALITY_PY'\n", 1)[1].split('\nQUALITY_PY', 1)[0]
helper = {}
exec(QUALITY.split('\ntry:\n    cmd,*a=sys.argv[1:]', 1)[0], helper)
checks = 0


def check(label, condition, result=None):
    global checks
    if not condition:
        raise AssertionError(f'{label}: {result}')
    checks += 1
    print('  ok ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='unio-disk-unit-') as temporary:
    directory = Path(temporary)
    for operation in ('write', 'fsync'):
        for number in (errno.EIO, errno.ENOSPC, errno.EACCES):
            with patch.object(os, operation, side_effect=OSError(number, os.strerror(number))):
                try:
                    helper['storage_probe'](str(directory))
                except OSError as exc:
                    check(f'{operation} {errno.errorcode[number]} typed with path',
                          exc.errno == number and exc.filename == str(directory))
                else:
                    raise AssertionError('fault accepted')
            check('failed probe removed temporary file', list(directory.iterdir()) == [])
    target = directory / 'historical.md'
    target.write_text('history\n')
    helper['storage_probe'](str(directory), [target.name])
    check('probe preserves historical contents', target.read_text() == 'history\n')
    link = directory / 'linked'
    link.symlink_to(directory, target_is_directory=True)
    try:
        helper['storage_probe'](str(link))
    except OSError:
        check('no-follow directory traversal', True)
    else:
        raise AssertionError('symlink directory accepted')
    # The descriptor traversal also accepts the filesystem root.
    fd = helper['storage_directory']('/')
    os.close(fd)
    check('root directory is supported', True)


with tempfile.TemporaryDirectory(prefix='unio-disk-installed-', dir='/tmp') as temporary:
    base = Path(temporary)
    env = dict(os.environ, HOME=str(base), UNIO_BIN_DIR=str(base / 'bin'),
               UNIO_CONF_DIR=str(base / 'conf'), UNIO_COMPLETION_DIR=str(base / 'completion'),
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid',
               UNIO_TIMEOUT='10')

    def run(argv, cwd=None, extra=None):
        return subprocess.run(argv, cwd=cwd or base, env=dict(env, **(extra or {})),
                              text=True, capture_output=True, timeout=60)

    installed = run(['bash', str(SOURCE / 'unio-install.sh')])
    check('private install', installed.returncode == 0, installed.stderr)
    at = str(base / 'bin' / 'unio')
    root = base / 'project with spaces'
    repo = root / 'repo'
    repo.mkdir(parents=True)
    for args in (['init', '-q', '-b', 'main'], ['commit', '--allow-empty', '-qm', 'seed']):
        out = run(['git', *args], cwd=repo)
        check('fixture git ' + args[0], out.returncode == 0, out.stderr)

    def unio(*args, extra=None):
        return run([at, *args], cwd=repo, extra=extra)

    init = unio('init', 'mock')
    check('fixture init', init.returncode == 0, init.stderr)
    coord = root / 'coord'
    marker = base / 'provider-canary'
    provider = base / 'provider.sh'
    provider.write_text('#!/bin/sh\nprintf ran >> "$DISK_CANARY"\n')
    (base / 'conf' / 'agents.conf').write_text(f"mock=sh '{provider}'\n")
    env['DISK_CANARY'] = str(marker)

    # Inject a late provider-free policy write failure through a private Python
    # launcher. Production code contains no test fault switch. Preflight passes.
    shim = base / 'shim'
    shim.mkdir()
    launcher = shim / 'python3'
    launcher.write_text(f'''#!{sys.executable}
import errno, os, sys, tempfile
if len(sys.argv) > 1 and sys.argv[1] == '-':
    code = sys.stdin.read()
    real_open = os.open
    def checked_open(path, flags, *args, **kwargs):
        parent_fd = kwargs.get('dir_fd')
        absolute = os.path.join(os.readlink('/proc/self/fd/' + str(parent_fd)), path) if parent_fd is not None else os.path.abspath(path)
        if flags & (os.O_WRONLY | os.O_RDWR):
            for candidate in (os.path.dirname(absolute), absolute):
                if os.path.exists(candidate) and os.stat(candidate).st_mode & 0o222 == 0:
                    raise OSError(errno.EACCES, 'deterministic private-fixture permissions', absolute)
        return real_open(path, flags, *args, **kwargs)
    os.open = checked_open
    real_mkdir = os.mkdir
    def checked_mkdir(path, *args, **kwargs):
        parent_fd = kwargs.get('dir_fd')
        absolute = os.path.join(os.readlink('/proc/self/fd/' + str(parent_fd)), path) if parent_fd is not None else os.path.abspath(path)
        if not os.path.lexists(absolute) and os.stat(os.path.dirname(absolute)).st_mode & 0o222 == 0:
            raise OSError(errno.EACCES, 'deterministic private-fixture permissions', absolute)
        return real_mkdir(path, *args, **kwargs)
    os.mkdir = checked_mkdir
    if 'MAX_SLOT_META = 4096' in code and os.environ.get('DISK_TEST_ERRNO'):
        if '_admit_hold' in sys.argv:
            def fault(*args, **kwargs):
                raise OSError(int(os.environ['DISK_TEST_ERRNO']), 'injected late storage error', kwargs.get('dir'))
            tempfile.mkstemp = fault
        elif '_admit_check' in sys.argv:
            # Deterministic read failure after the synchronous storage probe.
            def fault(*args, **kwargs):
                raise OSError(int(os.environ['DISK_TEST_ERRNO']), 'injected late storage error', sys.argv[2])
            os.read = fault
    sys.argv = sys.argv[1:]
    exec(compile(code, '<installed-helper>', 'exec'), {{'__name__': '__main__'}})
else:
    os.execv({sys.executable!r}, [{sys.executable!r}, *sys.argv[1:]])
''')
    launcher.chmod(0o755)
    env['PATH'] = str(shim) + ':' + env['PATH']

    def task(name):
        (coord / 'tasks' / (name + '.md')).write_text('Task ' + name + '\n')

    def refused(name, bg=False, extra=None):
        task(name)
        marker.unlink(missing_ok=True)
        retry = coord / 'retries' / name / 'state.json'
        before_retry = retry.read_bytes() if retry.is_file() else None
        out = unio('run', *(['-b'] if bg else []), 'mock', name, extra=extra)
        text = out.stdout + out.stderr
        check(name + ' storage refusal', out.returncode != 0 and 'storage refused' in out.stderr, text)
        check(name + ' no provider or started claim', not marker.exists() and 'started in background' not in text, text)
        check(name + ' no false budget advice', 'budget-refused' not in text and 'budget refused' not in text
              and 'Free the group' not in text, text)
        check(name + ' no retry consumed',
              (retry.read_bytes() if retry.is_file() else None) == before_retry)
        check(name + ' remediation on stderr', 'disk space' in out.stderr and 'permissions' in out.stderr, text)
        report = coord / 'reports' / (name + '.md')
        if report.is_file() and not report.is_symlink() and '## storage-refused' in report.read_text():
            check(name + ' persisted storage heading only', 'budget-refused' not in report.read_text())
        return out

    # Existing-file conflicts and permissions on every storage domain, both
    # launch modes. No global mount, disk filling or broad chmod is involved.
    prior_retry = coord / 'retries' / 'reports-fg' / 'state.json'
    prior_retry.parent.mkdir(parents=True)
    prior_retry.write_text(json.dumps(dict(schema_version=1, task='reports-fg', failed_attempts=2, retry_granted=True, latest={})))
    for bg in (False, True):
        suffix = 'bg' if bg else 'fg'
        reports = coord / 'reports'
        saved = coord / 'reports-preserved'
        reports.rename(saved)
        reports.write_text('conflict history\n')
        try:
            out = refused('reports-conflict-' + suffix, bg)
            check('reports conflict path named', str(reports) in out.stderr)
            check('file conflict preserved', reports.read_text() == 'conflict history\n')
        finally:
            reports.unlink()
            saved.rename(reports)
        for relative in ('reports', 'retries', '.locks', '.locks/work-policy-slots/mock'):
            path = coord / relative
            if not path.exists():
                path.mkdir(parents=True)
            original = path.stat().st_mode & 0o777
            path.chmod(0o500)
            try:
                name = relative.replace('/', '-').replace('.', 'x') + '-' + suffix
                out = refused(name, bg)
                check(relative + ' path named', str(path) in out.stderr)
            finally:
                path.chmod(original)
        for relative in ('results/mock', 'retries/conflict-' + suffix, '.locks/work-policy-slots/mock'):
            path = coord / relative
            preserved = path.with_name(path.name + '-preserved')
            existed = path.exists()
            if existed:
                path.rename(preserved)
            path.write_text('storage conflict\n')
            try:
                name = 'conflict-' + suffix if relative.startswith('retries/') else relative.replace('/', '-') + '-conflict-' + suffix
                refused(name, bg)
            finally:
                path.unlink()
                if existed:
                    preserved.rename(path)
        link = coord / '.locks' / 'work-policy.lock'
        preserved_lock = link.with_suffix('.preserved')
        if link.exists():
            link.rename(preserved_lock)
        link.symlink_to(base / 'untouched-lock-target')
        try:
            refused('policy-lock-link-' + suffix, bg)
            check('policy lock symlink target untouched', not (base / 'untouched-lock-target').exists())
        finally:
            link.unlink()
            if preserved_lock.exists():
                preserved_lock.rename(link)
        reports.rename(saved)
        reports.symlink_to(saved, target_is_directory=True)
        try:
            refused('reports-symlink-' + suffix, bg)
        finally:
            reports.unlink()
            saved.rename(reports)
        name = 'readonly-receipt-' + suffix
        receipt = reports / (name + '.md')
        receipt.write_text('original history\n')
        receipt.chmod(0o444)
        try:
            refused(name, bg)
            check('readonly receipt preserved', receipt.read_text() == 'original history\n')
        finally:
            receipt.chmod(0o644)

    # A real locked native slot, not a mock message, retains budget semantics.
    import fcntl
    slots = coord / '.locks' / 'work-policy-slots' / 'mock'
    slot = slots / 'wpslot-fixture.json'
    with slot.open('w') as held:
        held.write('{}\n')
        held.flush()
        fcntl.flock(held, fcntl.LOCK_EX)
        for bg in (False, True):
            name = 'occupied-' + str(bg)
            task(name)
            marker.unlink(missing_ok=True)
            out = unio('run', *(['-b'] if bg else []), 'mock', name)
            check('occupied group remains budget-refused', out.returncode == 2 and 'budget refused' in out.stderr
                  and not marker.exists() and 'started in background' not in out.stdout, out.stderr)
    slot.unlink()

    check('persist policy fixture', unio('tier', 'low').returncode == 0)
    for number in (errno.ENOSPC, errno.EIO):
        refused('late-' + str(number), extra=dict(PATH=str(shim) + ':' + env['PATH'], DISK_TEST_ERRNO=str(number)))
        refused('late-bg-' + str(number), bg=True, extra=dict(DISK_TEST_ERRNO=str(number)))

    task('healthy')
    marker.unlink(missing_ok=True)
    out = unio('run', 'mock', 'healthy')
    check('healthy installed run reaches provider', out.returncode == 0 and marker.read_text() == 'ran', out.stderr)
    check('healthy structured receipt', (coord / 'results' / 'mock' / 'healthy.json').is_file())
    # Existing record directories suffice on a route that does not consume
    # shared-lead consent; the coord parent itself need not accept new files.
    coord_mode = coord.stat().st_mode & 0o777
    coord.chmod(0o500)
    try:
        task('healthy-record-directories')
        out = unio('run', 'mock', 'healthy-record-directories')
        check('only actual writable record directories required', out.returncode == 0, out.stderr)
    finally:
        coord.chmod(coord_mode)
    task('healthy-background')
    marker.unlink()
    out = unio('run', '-b', 'mock', 'healthy-background')
    check('healthy background accepted', out.returncode == 0 and 'started in background' in out.stdout, out.stderr)
    result = coord / 'results' / 'mock' / 'healthy-background.json'
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if result.is_file() and json.loads(result.read_text())['process']['state'] != 'running':
            break
        time.sleep(0.1)
    check('healthy background completed', marker.exists() and result.is_file()
          and json.loads(result.read_text())['process']['state'] == 'succeeded')
    # A terminal result precedes EXIT cleanup. Wait for native ownership to
    # release before removing the fixture under the detached background shell.
    released = False
    with (coord / '.locks' / 'mock.lock').open('a') as worker_lock:
        while time.monotonic() < deadline:
            try:
                fcntl.flock(worker_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                released = True
                break
            except BlockingIOError:
                time.sleep(0.1)
        check('healthy background ownership released', released)
    check('no probe files left', not list(coord.rglob('.unio-disk-*')))

print(f'unio-disk-preflight: {checks} checks passed')
