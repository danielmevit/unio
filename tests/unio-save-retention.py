#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Offline installed archival workflows and protected-history boundaries.

Pressure fixtures clone a real native save, changing only its ID, worker and
publication time. Content/fingerprints remain valid. No live provider is used.
"""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1]
helper = SOURCE.joinpath('unio-install.sh').read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY', 1)[0]
core = {}
exec(compile(helper.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], '<save-helper>', 'exec'), core)
passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='save-retention-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
               UNIO_COMPLETION_DIR=str(base/'completion'), UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock', GIT_AUTHOR_EMAIL='mock@example.invalid',
               GIT_COMMITTER_EMAIL='mock@example.invalid')
    env.pop('UNIO_SAVE_TEST_FAULT', None)
    subprocess.run(['bash', str(SOURCE/'unio-install.sh')], env=env, check=True, capture_output=True)
    engine = str(base/'bin/unio')
    project = base/'project with spaces'
    repo = project/'repo'; repo.mkdir(parents=True)
    coord = project/'coord'; store = coord/'saves'; archive = store/'archive'
    calls = base/'mock-calls'
    (base/'conf/agents.conf').write_text('mock=sh -c \'echo invoked >> "%s"; exit 7\'\n' % calls)

    def unio(*args, fault=None):
        return subprocess.run([engine, *args], cwd=repo, env=dict(env, UNIO_SAVE_TEST_FAULT=fault or ''),
                              text=True, capture_output=True, timeout=90)

    def git(*args):
        return subprocess.run(['git', '-C', str(repo), *args], env=env, check=True, capture_output=True)

    (repo/'README.md').write_text('native saved bytes\n')
    git('init', '-q', '-b', 'main'); git('add', '.'); git('commit', '-qm', 'base')
    workers = ['mock-' + letter for letter in 'abcdefghijk']
    check('native workers initialize', unio('init', *workers).returncode == 0)
    unio('stop')
    before = sorted(p.relative_to(coord).as_posix() for p in coord.rglob('*'))
    missing = unio('save', 'usage', '--json')
    check('missing-store usage reports zero without writes', missing.returncode == 0
          and json.loads(missing.stdout)['active_saves'] == 0
          and before == sorted(p.relative_to(coord).as_posix() for p in coord.rglob('*')) and not store.exists())
    (coord/'tasks/T1.md').write_text('# T1\nKeep native bytes.\n')
    created = unio('save', 'create', workers[0], 'T1')
    match = re.search(r'^saved ([0-9a-f]{32}):', created.stdout, re.M)
    check('native template save created', created.returncode == 0 and match is not None)
    template = base/'template'; shutil.copytree(store/match[1], template)

    def ids(where):
        return {p.name for p in where.iterdir() if re.fullmatch('[0-9a-f]{32}', p.name)} if where.exists() else set()

    def content(where):
        if where.parent == archive:
            where = where/'snapshot'
        return {p.relative_to(where).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in where.rglob('*') if p.is_file() and not p.is_symlink()}

    def clone(where, number, worker, second):
        sid = '%032x' % number
        dest = where/sid
        if where == archive:
            dest.mkdir(mode=0o700)
            dest = dest/'snapshot'
        shutil.copytree(template, dest)
        doc = json.loads((dest/'manifest.json').read_text())
        doc.update(save_id=sid, worker=worker, published_at='2026-10-10T10:%02d:%02d+00:00' % (second//60, second%60))
        (dest/'manifest.json').write_text(json.dumps(doc) + '\n')
        return sid

    def seed(unique=False):
        for p in store.iterdir():
            if re.fullmatch('[0-9a-f]{32}', p.name) or p.name == 'archive': shutil.rmtree(p)
        for p in (store/'claims').iterdir(): p.unlink()
        return [clone(store, i+1, 'isolated-%d' % i if unique else workers[i//4], i) for i in range(32)]

    initial = seed(); originals = {sid: content(store/sid) for sid in initial}
    core['load_save'](str(store/initial[0]), initial[0], True)
    r = unio('save', 'create', workers[8], 'T1')
    if r.returncode:
        print('Native pressure-save diagnostic:', r.returncode, r.stdout, r.stderr, flush=True)
    check('33rd save archives oldest eligible from another worker', r.returncode == 0
          and len(ids(store)) == 32 and ids(archive) == {initial[0]})
    check('all previous IDs and bytes preserved exactly', all(content((store if sid in ids(store) else archive)/sid)
          == originals[sid] for sid in initial))
    check('each original worker newest remains active', all(initial[i] in ids(store) for i in range(3, 32, 4)))
    inspected = unio('save', 'inspect', initial[0], '--json')
    check('archived ID inspects without moving it back', inspected.returncode == 0
          and json.loads(inspected.stdout)['valid'] and initial[0] in ids(archive))
    restored = unio('save', 'restore', initial[0], workers[9])
    check('archived ID restores and remains archived', restored.returncode == 0
          and initial[0] in ids(archive) and (project/'wt'/workers[9]/'README.md').read_text() == 'native saved bytes\n')
    before_usage = content(store)
    usage = unio('save', 'usage', '--json'); stats = json.loads(usage.stdout)
    check('usage measures actual archive bytes, unique pins and fixed caps without writes', usage.returncode == 0
          and stats['active_saves'] == 32 and stats['archived_saves'] == 1 and stats['valid_pins'] == 1
          and stats['archived_bytes'] == sum(p.stat().st_size for p in (archive/initial[0]).rglob('*') if p.is_file())
          and stats['archive_cap_saves'] == 128 and stats['archive_cap_bytes'] == 512*1024*1024
          and content(store) == before_usage)
    check('usage rejects unknown arguments', unio('save', 'usage', 'oops').returncode == 2)
    lock = (coord/'.locks/saves.lock').open('rb'); fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        busy = unio('save', 'usage', '--json')
        check('busy usage reports Unknown without changing evidence', busy.returncode == 2
              and json.loads(busy.stdout)['status'] == 'unknown' and content(store) == before_usage)
    finally: lock.close()
    check('save/usage/inspect/restore made no provider calls', not calls.exists())

    (coord/'tasks/CONT1.md').write_text('# CONT1\nSeparate authorized mock continuation.\n## Allowed scope\n- README.md\n## Validate\n$ true\n')
    unio('resume')
    continued = unio('save', 'continue', initial[0], workers[9], 'CONT1')
    unio('stop')
    check('archived continuation resolves through native claim/run path once', continued.returncode == 7
          and calls.read_text() == 'invoked\n' and initial[0] in ids(archive))
    replay = unio('save', 'continue', initial[0], workers[9], 'CONT1')
    check('STOP/replay dispatches no further continuation', replay.returncode != 0 and calls.read_text() == 'invoked\n')

    initial = seed()
    unio('save', 'restore', initial[0], workers[10])
    r = unio('save', 'create', workers[8], 'T1')
    check('active claim pin is skipped under cross-worker pressure', r.returncode == 0
          and initial[0] in ids(store) and initial[1] in ids(archive))

    initial = seed(unique=True); newest_bytes = {sid: content(store/sid) for sid in initial}
    r = unio('save', 'create', workers[8], 'T1')
    check('32 distinct newest saves refuse rather than losing a worker checkpoint', r.returncode == 1
          and 'newest' in r.stderr and ids(store) == set(initial) and not archive.exists()
          and all(content(store/sid) == newest_bytes[sid] for sid in initial))

    initial = seed()
    overcap = store/('e'*32); overcap.mkdir(mode=0o700)
    r = unio('save', 'create', workers[8], 'T1')
    check('already-overfull store with corrupt evidence refuses before archival',
          r.returncode == 1 and 'already exceeds the project cap' in r.stderr
          and ids(store) == set(initial) | {overcap.name} and not archive.exists())

    initial = seed()
    bad = store/'claims'/('f'*32 + '.json'); bad.write_text('{}'); bad.chmod(0o600)
    r = unio('save', 'create', workers[8], 'T1')
    check('unreadable claims block archival and retain every save', r.returncode == 1
          and 'unreadable claims' in r.stderr and ids(store) == set(initial) and not archive.exists())
    check('usage marks unreadable claims Unknown', json.loads(unio('save', 'usage', '--json').stdout)['status'] == 'unknown')

    initial = seed()
    body = next((store/initial[0]/'pool').iterdir()); body.write_bytes(b'x'*body.stat().st_size)
    bad_bytes = content(store/initial[0])
    r = unio('save', 'create', workers[8], 'T1')
    check('hash-corrupt save is never archived or deleted', r.returncode == 0
          and initial[0] in ids(store) and content(store/initial[0]) == bad_bytes and initial[1] in ids(archive))

    initial = seed(); archive.mkdir(mode=0o700); (archive/initial[0]).mkdir(mode=0o700)
    try:
        core['archive_save'](str(store), initial[0], str(archive))
    except core['Refuse']: collision = True
    else: collision = False
    check('no-replace refuses even an empty destination collision', collision
          and (archive/initial[0]).is_dir() and content(store/initial[0]) == originals[initial[0]])
    check('duplicate ID inspect refuses ambiguity', unio('save', 'inspect', initial[0], '--json').returncode != 0)
    check('worker inspection refuses a corrupt archive ID collision',
          unio('save', 'inspect', '--worker', workers[0], '--json').returncode != 0)

    initial = seed(); archive.symlink_to(base/'elsewhere', target_is_directory=True)
    r = unio('save', 'create', workers[8], 'T1')
    check('unsafe archive link refuses before moving history', r.returncode == 1 and ids(store) == set(initial))
    archive.unlink()

    initial = seed(); archive.mkdir(mode=0o700)
    for i in range(128): clone(archive, 1000+i, workers[0], i)
    r = unio('save', 'create', workers[8], 'T1')
    check('actual 128-save archive cap refuses without publishing or deleting', r.returncode == 1
          and 'archive count cap' in r.stderr and len(ids(store)) == 32 and len(ids(archive)) == 128)

    initial = seed(); core['ARCHIVE_CAP_BYTES'] = 1
    try:
        core['retention_plan'](str(store), workers[8], core['Budget'](30))
    except core['Refuse'] as error: byte_refused = 'archive byte cap' in error.message
    else: byte_refused = False
    finally: core['ARCHIVE_CAP_BYTES'] = 512*1024*1024
    check('measured-byte boundary refuses before mutation (reduced test cap)', byte_refused and ids(store) == set(initial))

    r = unio('save', 'create', workers[8], 'T1', fault='archive-after-move')
    check('interruption after atomic move keeps all old IDs and bytes', r.returncode != 0
          and ids(store) | ids(archive) == set(initial)
          and all(content((store if sid in ids(store) else archive)/sid) == originals[sid] for sid in initial))
    check('interrupted archived ID still inspects', unio('save', 'inspect', initial[0], '--json').returncode == 0)
    check('only explicitly authorized mock continuation was invoked', calls.read_text() == 'invoked\n')
    print('Save retention: %d checks passed' % passed)
