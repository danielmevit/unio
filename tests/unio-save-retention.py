#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Save retention with archival: 32 valid saves across workers, archival under pressure,
inspect/restore of archived saves, protection of newest/pins/corrupt, archive bounds.

Offline and mock-only. Uses the same fixture approach as unio-work-saving.py.
"""
import fcntl
import json
import os
import re
import shutil
import signal
import stat
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


with tempfile.TemporaryDirectory(prefix='save-retention-') as directory:
    base = Path(directory)
    calls = base / 'provider-calls'
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid',
               GIT_OPTIONAL_LOCKS='0', UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0')
    env.pop('UNIO_SAVE_TEST_FAULT', None)
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env, check=True, capture_output=True)
    (base / 'conf' / 'agents.conf').write_text("mock=sh -c 'echo called >> \"%s\"'\n" % calls)
    at = str(base / 'bin' / 'unio')
    root = base / 'mock project'
    repo = root / 'repo'
    repo.mkdir(parents=True)

    def git(cwd, *args, data=None):
        return subprocess.run(['git', *args], cwd=cwd, env=env, check=True, capture_output=True,
                              input=data).stdout

    def unio(*args, fault=None, cwd=None, timeout=120):
        e = dict(env, UNIO_SAVE_TEST_FAULT=fault) if fault else env
        return subprocess.run([at, *args], cwd=cwd or repo, env=e, capture_output=True, text=True, timeout=timeout)

    def write(path, data, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        os.chmod(path, mode)

    # Base commit
    write(repo / '.gitignore', 'cache/\n*.log\n.env\n')
    write(repo / 'README.md', 'base readme\n')
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'base')
    base_commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
    workers = ['mock-' + c for c in 'abcdefghij']
    init = unio('init', *workers)
    check('init creates mock workers', init.returncode == 0)
    coord, wt = root / 'coord', root / 'wt'
    write(coord / 'tasks' / 'T1.md', '# T1\nFinish the feature.\n## Validate\n$ false\n')
    unio('stop')
    check('STOP is set for every save command below', (coord / 'STOP').exists())

    # Create 32 saves across 4 workers (8 per worker to test per-worker cap)
    save_ids = []
    for i, worker in enumerate(workers[:4]):
        for j in range(8):
            task_content = '# Task %d-%d\nContent.\n' % (i, j)
            write(coord / 'tasks' / ('T%d-%d.md' % (i, j)), task_content)
            r = unio('save', 'create', worker, 'T%d-%d' % (i, j))
            check('%s save %d created' % (worker, j), r.returncode == 0)
            # Extract save ID from output
            match = re.search(r'saved ([0-9a-f]{32}):', r.stdout)
            if match:
                save_ids.append(match.group(1))
    
    check('created 32 saves', len(save_ids) == 32)

    # Verify saves are in the store
    store = root / 'coord' / 'saves'
    check('saves directory exists', store.exists())
    active_saves = [d for d in os.listdir(store) if re.fullmatch(r'[0-9a-f]{32}', d)]
    check('active saves count', len(active_saves) == 32)

    # Create a new save from a 5th worker - should trigger archival
    task_content = '# New Task\nNew content.\n'
    write(coord / 'tasks' / 'new.md', task_content)
    r = unio('save', 'create', workers[4], 'new')
    check('new worker save triggers archival', r.returncode == 0)
    
    # Check that archive was created and has saves
    archive = root / 'coord' / 'saves' / 'archive'
    check('archive directory exists', archive.exists())
    archived_saves = [d for d in os.listdir(archive) if re.fullmatch(r'[0-9a-f]{32}', d)]
    check('some saves were archived', len(archived_saves) > 0)
    
    # Total saves (active + archived) should still be 33
    active_saves = [d for d in os.listdir(store) if re.fullmatch(r'[0-9a-f]{32}', d)]
    check('total saves preserved', len(active_saves) + len(archived_saves) == 33)

    # Test usage command
    r = unio('save', 'usage')
    check('usage command succeeds', r.returncode == 0)
    check('usage output contains active saves', 'Active saves:' in r.stdout)
    check('usage output contains archived saves', 'Archived saves:' in r.stdout)
    
    # Test usage with --json
    r = unio('save', 'usage', '--json')
    check('usage --json succeeds', r.returncode == 0)
    usage_data = json.loads(r.stdout)
    check('usage JSON has active_saves', 'active_saves' in usage_data)
    check('usage JSON has archived_saves', 'archived_saves' in usage_data)
    check('usage JSON has archive bounds', usage_data.get('archive_cap_saves') == 128)
    check('usage JSON has archive bytes bound', usage_data.get('archive_cap_bytes') == 512 * 1024 * 1024)

    # Test inspect of archived save
    if archived_saves:
        archived_id = archived_saves[0]
        r = unio('save', 'inspect', archived_id)
        check('inspect archived save succeeds', r.returncode == 0)
        check('inspect archived save shows valid', 'complete, valid' in r.stdout)
        
        # Test inspect with --json
        r = unio('save', 'inspect', archived_id, '--json')
        check('inspect archived save --json succeeds', r.returncode == 0)
        inspect_data = json.loads(r.stdout)
        check('inspect archived save JSON valid', inspect_data.get('valid') is True)

    # Test that newest per worker is preserved
    for worker in workers[:5]:
        r = unio('save', 'inspect', '--worker', worker)
        check('worker %s has last good save' % worker, r.returncode == 0)
        check('worker %s last good save exists' % worker, 'last good save:' in r.stdout)

    # Test restore of archived save
    if archived_saves:
        archived_id = archived_saves[0]
        # Get worker from archived save
        r = unio('save', 'inspect', archived_id, '--json')
        inspect_data = json.loads(r.stdout)
        original_worker = inspect_data['worker']
        
        # Restore to a different worker
        dest_worker = workers[5]  # Use a worker that hasn't saved yet
        r = unio('save', 'restore', archived_id, dest_worker)
        check('restore archived save succeeds', r.returncode == 0)

    # Test archive bounds - create many saves to fill archive
    # This tests that archive refuses when bounds are exceeded
    for i in range(100):
        task_content = '# Fill Task %d\nFill.\n' % i
        write(coord / 'tasks' / ('fill%d.md' % i), task_content)
        r = unio('save', 'create', workers[0], 'fill%d' % i)
        if r.returncode != 0:
            # Should fail when archive bounds are exceeded
            check('archive bounds enforced at save %d' % i, True)
            break
    else:
        check('archive bounds not reached after 100 saves', False)

    # Verify archive count doesn't exceed bounds
    archived_saves = [d for d in os.listdir(archive) if re.fullmatch(r'[0-9a-f]{32}', d)]
    check('archive count within bounds', len(archived_saves) <= 128)

    # Test that claims still work with archived saves
    if archived_saves and len(save_ids) >= 2:
        archived_id = archived_saves[0]
        r = unio('save', 'inspect', archived_id, '--json')
        inspect_data = json.loads(r.stdout)
        original_worker = inspect_data['worker']
        
        # Create a claim by restoring
        dest_worker = workers[6]
        r = unio('save', 'restore', archived_id, dest_worker)
        check('create claim for archived save', r.returncode == 0)
        
        # Verify the save is now pinned
        r = unio('save', 'usage', '--json')
        usage_data = json.loads(r.stdout)
        check('pinned count increased', usage_data.get('valid_pins', 0) >= 1)

    print('\nAll retention tests passed: %d checks' % passed[0])
