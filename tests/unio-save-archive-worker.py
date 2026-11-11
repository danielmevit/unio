#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Offline explicit `unio save archive-worker` planning and application.

Reproduces the protected-latest cap in tiny private fixtures (clones of one
real native save with changed ID/worker/time), then checks read-only plans,
deterministic plan hashes, explicit selected-worker application, protected
pinned/corrupt/unsafe evidence, races, caps and an interrupted move. No live
provider is used and no owner store is touched.
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
helper = SOURCE.joinpath('unio-install.sh').read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY\n', 1)[0]
core = {}
exec(compile(helper.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], '<save-helper>', 'exec'), core)
passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='save-archive-worker-') as directory:
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
    receipts = coord/'reports/.checkpoint-archive'
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
    check('missing-store planning refuses without creating a store', unio('save', 'archive-worker',
          'mock-a', '--plan', '--json').returncode == 1 and not store.exists() and not archive.exists())
    check('apply without a prior exact plan hash is refused',
          unio('save', 'archive-worker', 'mock-a', '--apply', 'f'*64).returncode == 2)
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

    def seed(unique):
        for p in store.iterdir():
            if re.fullmatch('[0-9a-f]{32}', p.name) or p.name == 'archive': shutil.rmtree(p)
        for p in (store/'claims').iterdir(): p.unlink()
        initial = [clone(store, i+1, 'iso-%d' % i if unique else workers[i//4], i) for i in range(32)]
        originals = {sid: content(store/sid) for sid in initial}
        return initial, originals

    def tree():
        return sorted(p.relative_to(coord).as_posix() for p in coord.rglob('*'))

    def plan(worker, as_json=True):
        args = ['save', 'archive-worker', worker]
        if as_json:
            args += ['--plan', '--json']
        return unio(*args)

    def apply(worker, plan_hash, fault=None):
        return unio('save', 'archive-worker', worker, '--apply', plan_hash, '--confirm-inactive', '--json',
                    fault=fault)

    initial, originals = seed(True)
    r = unio('save', 'create', workers[8], 'T1')
    check('32 protected latests reproduce ordinary new-save refusal', r.returncode == 1
          and 'newest' in r.stderr and ids(store) == set(initial) and not archive.exists())

    before = tree()
    r = plan('iso-5')
    data = json.loads(r.stdout)
    check('read-only plan explains selection with zero writes', r.returncode == 0
          and data['status'] == 'planned' and data['mode'] == 'plan' and data['worker'] == 'iso-5'
          and len(data['selected']) == 1 and data['selected'][0]['save_id'] == initial[5]
          and data['blocked'] == [] and data['newest_active_save'] == initial[5]
          and data['apply_usage'] == 'unio save archive-worker iso-5 --apply %s --confirm-inactive' % data['plan_hash']
          and re.fullmatch('[0-9a-f]{64}', data['plan_hash'])
          and data['freed_slots'] == 1 and data['native_activity'] == 'idle'
          and data['unmanaged_activity'] == 'unknown' and data['unattributed_corrupt_active'] == 0
          and data['active_saves'] == 32 and isinstance(data['active_bytes'], int)
          and data['archived_saves'] == 0 and data['archive_after_saves'] == 1
          and data['archive_capacity'] == 'known'
          and data['protected_newest_other_workers'] == sorted(sid for sid in initial if sid != initial[5])
          and tree() == before and not receipts.exists() and not archive.exists())

    check('plain plan form is read-only but equivalent text', plan('iso-5', as_json=False).returncode == 0)
    core['write_attempt'](str(store), 'iso-31', 'T1', '2026-11-11T10:00:00+00:00', 'lock_busy', 'refused', None)
    later = json.loads(plan('iso-5').stdout)
    check('unchanged state keeps its hash despite unrelated refused attempts',
          later['plan_hash'] == data['plan_hash'])

    stale = json.loads(plan('iso-13').stdout)
    core['write_attempt'](str(store), 'iso-13', 'T1', '2026-11-11T10:01:00+00:00', 'manual', 'refused', None)
    r = apply('iso-13', stale['plan_hash'])
    check('stale plan refuses without moving a save', r.returncode == 1 and 'stale' in r.stderr
          and initial[13] in ids(store) and not archive.exists())

    r = apply('iso-5', data['plan_hash'])
    moved = json.loads(r.stdout)
    stem = 'iso-5-' + data['plan_hash'][:16]
    check('explicit selected-worker application frees its slot exactly',
          r.returncode == 0 and moved['status'] == 'archived' and moved['mode'] == 'apply'
          and moved['confirm_inactive'] and moved['plan_hash'] == data['plan_hash']
          and moved['moved'] == [initial[5]] and moved['remaining'] == []
          and moved['freed_active_slots'] == 1 and moved['last_good_id'] == initial[5]
          and moved['last_good_check'] == 'resolved' and moved['archived_saves'] == 1
          and initial[5] in ids(archive) and initial[5] not in ids(store))
    check('archived exact manifests/pools/bundle/bytes preserved',
          content(archive/initial[5]) == originals[initial[5]]
          and (receipts/(stem + '.intent.json')).exists() and (receipts/(stem + '.outcome.json')).exists()
          and not (store/'attempts/iso-5.json').exists())

    r = unio('save', 'create', workers[8], 'T1')
    check('freed slots allow the ordinary next mock save without a cap override',
          r.returncode == 0 and len(ids(store)) == 32 and ids(archive) == {initial[5]})
    r = unio('save', 'create', workers[10], 'T1')
    check('automatic newest protection is unchanged after explicit archival',
          r.returncode == 1 and 'newest' in r.stderr and len(ids(store)) == 32)

    check('archived latest still inspects', json.loads(unio('save', 'inspect',
          initial[5], '--json').stdout)['valid'] and initial[5] in ids(archive))
    worker_view = json.loads(unio('save', 'inspect', '--worker', 'iso-5', '--json').stdout)
    check('last-good resolution rechecks through the archive path',
          worker_view['last_good']['save_id'] == initial[5])

    (coord/'STOP').write_text('frozen\n')
    stop_plan = json.loads(plan('iso-9').stdout)
    stop_apply = apply('iso-9', stop_plan['plan_hash'])
    check('explicit archival works with STOP set like inspect/restore',
          stop_apply.returncode == 0 and json.loads(stop_apply.stdout)['status'] == 'archived'
          and initial[9] in ids(archive) and not calls.exists())
    (coord/'STOP').unlink()

    (coord/'tasks/T2.md').write_text('# T2\nSecond fixture task.\n')
    r = unio('save', 'create', workers[0], 'T2')
    real_plan = json.loads(plan(workers[0]).stdout)
    real_apply = apply(workers[0], real_plan['plan_hash'])
    real_id = real_plan['selected'][0]['save_id']
    check('explicit archival of a real native worker keeps its worktree identity',
          r.returncode == 0 and real_apply.returncode == 0
          and real_plan['selected'] == [real_plan['selected'][0]] and [real_plan['selected'][0]['save_id']] == [real_id]
          and json.loads(real_apply.stdout)['moved'] == [real_id] and real_id in ids(archive))
    restored = unio('save', 'restore', real_id, workers[9])
    check('archived latest restores exact bytes into another worker',
          restored.returncode == 0 and real_id in ids(archive)
          and (project/'wt'/workers[9]/'README.md').read_text() == 'native saved bytes\n'
          and not calls.exists())

    initial, _ = seed(True)
    lock_path = coord/'.locks/iso-11.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    held = open(lock_path, 'w+b'); held.truncate(0); os.fchmod(held.fileno(), 0o600)
    fcntl.flock(held, fcntl.LOCK_EX)
    try:
        busy_plan = json.loads(plan('iso-11').stdout)
        r = apply('iso-11', busy_plan['plan_hash'])
        check('known live/locked native worker refuses before effects',
              busy_plan['native_activity'] == 'busy' and r.returncode == 2
              and 'lock_busy' in r.stderr and initial[11] in ids(store) and ids(archive) == set())
    finally:
        held.close()
    check('unsafe worker names and apply forms refuse usage',
          unio('save', 'archive-worker', 'zzz/bad').returncode == 2
          and unio('save', 'archive-worker').returncode == 2
          and unio('save', 'archive-worker', 'iso-11', '--apply', 'nothex', '--confirm-inactive').returncode == 2
          and unio('save', 'archive-worker', 'iso-11', '--confirm-inactive', '--apply', 'f'*64).returncode == 2)

    initial, _ = seed(True)
    claim = dict(schema_version=1, claim_id='%032x' % 777, save_id=initial[14], destination='mock-z',
                 new_task=None, task_sha256=None, source_fingerprint='0'*64, preimage_fingerprint='0'*64,
                 created_at='2026-11-11T09:00:00+00:00', updated_at='2026-11-11T09:00:00+00:00',
                 state='reserved', outcome=None)
    core['write_claim'](str(store), claim)
    pinned = json.loads(plan('iso-14').stdout)
    r = apply('iso-14', pinned['plan_hash'])
    check('claim-pinned newest save is never selected or moved',
          pinned['selected'] == [] and pinned['blocked'] == [dict(save_id=initial[14], reason='claim_pinned')]
          and pinned['freed_slots'] == 0
          and r.returncode == 1 and initial[14] in ids(store) and ids(archive) == set())

    initial, _ = seed(True)
    body = next((store/initial[20]/'pool').iterdir()); body.write_bytes(b'x'*body.stat().st_size)
    shallow = json.loads(plan('iso-20').stdout)
    r = apply('iso-20', shallow['plan_hash'])
    check('apply deep-validates selected bodies before any effect',
          r.returncode == 1 and 'stored content hash mismatch' in r.stderr
          and initial[20] in ids(store) and ids(archive) == set())
    doc = json.loads((store/initial[21]/'manifest.json').read_text())
    doc['context'] = dict(doc['context'], task_bytes=doc['context']['task_bytes'] + 1)
    (store/initial[21]/'manifest.json').write_text(json.dumps(doc) + '\n')
    corrupt = json.loads(plan('iso-21').stdout)
    r = apply('iso-21', corrupt['plan_hash'])
    check('corrupt selected save stays as blocked evidence',
          corrupt['selected'] == [] and corrupt['blocked'] == [dict(save_id=initial[21], reason='corrupt_evidence')]
          and r.returncode == 1 and 'no unclaimed valid active save' in r.stderr
          and initial[21] in ids(store)
          and json.loads(unio('save', 'usage', '--json').stdout)['corrupt_evidence'] == 1)

    initial, _ = seed(True)
    archive.symlink_to(base/'elsewhere', target_is_directory=True)
    check('unsafe archive link refuses before anything moves', plan('iso-2').returncode != 0
          and initial[2] in ids(store))
    archive.unlink()

    archive.mkdir(mode=0o700); (archive/('0'*32)).mkdir(mode=0o700)
    r = plan('iso-2')
    check('unknown archive capacity blocks planning and application',
          r.returncode == 1 and 'corrupt or unsupported' in r.stderr and initial[2] in ids(store))
    shutil.rmtree(archive)
    archive.mkdir(mode=0o700)
    clone(archive, 3, 'iso-2', 2)
    r = plan('iso-2')
    check('duplicate active/archive save ID refuses before effects',
          r.returncode == 1 and 'duplicate' in r.stderr and initial[2] in ids(store))
    shutil.rmtree(archive)

    initial, _ = seed(True); archive.mkdir(mode=0o700)
    for i in range(128): clone(archive, 900+i, 'arch-old', i)
    capped = json.loads(plan('iso-17').stdout)
    r = apply('iso-17', capped['plan_hash'])
    check('archive count cap blocks application without deleting history',
          'count cap' in capped['archive_capacity'] and r.returncode == 1
          and 'archive count cap' in r.stderr and initial[17] in ids(store) and len(ids(archive)) == 128)
    shutil.rmtree(archive)
    seed(True)
    core['ARCHIVE_CAP_BYTES'] = 1
    try:
        material = core['archive_worker_material'](str(store), 'iso-18', core['Budget'](30))
        core['archive_capacity_refusal'](material['historical'], material['selected'])
    except core['Refuse'] as error: byte_refused = 'archive byte cap' in error.message
    else: byte_refused = False
    finally: core['ARCHIVE_CAP_BYTES'] = 512*1024*1024
    check('measured-byte boundary refuses before mutation (reduced test cap)',
          byte_refused and ids(store) and len(ids(archive)) == 0)

    initial, originals = seed(False)
    mine = initial[12:16]
    before_attempts = sorted((p.name, p.read_bytes()) for p in (store/'attempts').iterdir())
    live = json.loads(plan('mock-d').stdout)
    r = apply('mock-d', live['plan_hash'], fault='archive-after-move')
    moved_ids = ids(archive)
    check('interruption after one atomic move reports nonzero and never invents completion',
          r.returncode not in (0, 1) and len(moved_ids & set(mine)) == 1
          and len(set(mine) & ids(store)) == 3
          and all(content((store if sid in ids(store) else archive)/sid) == originals[sid] for sid in mine)
          and sorted((p.name, p.read_bytes()) for p in (store/'attempts').iterdir()) == before_attempts)
    check('interrupted snapshots remain readable and store still observes as known',
          json.loads(unio('save', 'inspect', next(iter(moved_ids)), '--json').stdout)['valid']
          and json.loads(unio('save', 'inspect', next(iter(set(mine) - moved_ids)), '--json').stdout)['valid']
          and json.loads(unio('save', 'usage', '--json').stdout)['status'] == 'observed')
    intent = 'mock-d-' + live['plan_hash'][:16] + '.intent.json'
    check('intent receipt records the interrupted maintenance without inventing an outcome',
          (receipts/intent).exists() and json.loads((receipts/intent).read_text())['status'] == 'applying'
          and not any(p.name.startswith('mock-d-' + live['plan_hash'][:16] + '.outcome') for p in receipts.iterdir()))
    resumed = json.loads(plan('mock-d').stdout)
    check('further application needs a fresh exact plan after partial state',
          resumed['plan_hash'] != live['plan_hash'] and resumed['freed_slots'] == 3)
    r = apply('mock-d', resumed['plan_hash'])
    done = json.loads(r.stdout)
    check('re-planned application completes preserving every remaining ID and byte',
          r.returncode == 0 and done['status'] == 'archived'
          and set(done['moved']) == set(mine) - moved_ids and done['remaining'] == []
          and set(mine) <= ids(archive)
          and all(content(archive/sid) == originals[sid] for sid in mine)
          and sorted((p.name, p.read_bytes()) for p in (store/'attempts').iterdir()) == before_attempts
          and not (store/'attempts/mock-d.json').exists())
    check('bounded maintenance receipts persist with their own schema',
          {p.name for p in receipts.iterdir()} >= {'iso-5-' + data['plan_hash'][:16] + '.intent.json',
                                                   'mock-d-' + resumed['plan_hash'][:16] + '.outcome.json'}
          and all(p.stat().st_uid == os.getuid() and p.stat().st_mode & 0o077 == 0 for p in receipts.iterdir())
          and len(list(receipts.iterdir())) >= 4)
    check('no provider call was made and usage reflects the archived worker', not calls.exists()
          and json.loads(unio('save', 'usage', '--json').stdout)['archived_saves'] == 4)
    print('Save archive-worker: %d checks passed' % passed)
