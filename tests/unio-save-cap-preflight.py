#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed save capacity preflight, refusal-only boundary and zero body reads."""
import collections
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import time
import types
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='save-cap-preflight-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
               UNIO_COMPLETION_DIR=str(base/'completion'), UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_SAVE_CAPTURE_TIMEOUT='30',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    env.pop('UNIO_SAVE_TEST_FAULT', None)
    subprocess.run(['bash', str(SOURCE/'unio-install.sh')], env=env,
                   check=True, capture_output=True, timeout=120)
    engine = base/'bin/unio'
    calls = base/'provider-calls'
    (base/'conf/agents.conf').write_text("mock=bash -c 'echo invoked >> \"%s\"; exit 99'\n" % calls)
    root = base/'project with spaces'; repo = root/'repo'; repo.mkdir(parents=True)

    def git(where, *args):
        return subprocess.check_output(['git', '-C', str(where), *args], env=env, stderr=subprocess.PIPE)

    def unio(*args):
        return subprocess.run([str(engine), *args], cwd=repo, env=env,
                              capture_output=True, text=True, timeout=180)

    (repo/'file.txt').write_bytes(b'base\n')
    git(repo, 'init', '-q', '-b', 'main'); git(repo, 'add', '.'); git(repo, 'commit', '-qm', 'base')
    workers = ['mock-w%02d' % i for i in range(35)]
    check('real Git workers initialize', unio('init', *workers).returncode == 0)
    unio('stop')

    (root/'coord/tasks/T1.md').write_text('# T1\nOffline only\n')
    wt0 = root/'wt'/workers[0]
    (wt0/'committed.txt').write_bytes(b'carried commit\n')
    git(wt0, 'add', 'committed.txt'); git(wt0, 'commit', '-qm', 'carried')
    (wt0/'file.txt').write_bytes(b'staged\0bytes\n'); git(wt0, 'add', 'file.txt')
    (wt0/'file.txt').write_bytes(b'working\0bytes\n')
    (wt0/'new.bin').write_bytes(bytes(range(256)))
    created = unio('save', 'create', workers[0], 'T1')
    match = re.search(r'^saved ([0-9a-f]{32}):', created.stdout, re.M)
    check('installed template save succeeds', created.returncode == 0 and match is not None)
    sid = match[1]; store = root/'coord/saves'; archive = store/'archive'
    template = base/'template'; shutil.copytree(store/sid, template)

    body = engine.read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY\n', 1)[0]
    module = types.ModuleType('installed_save_cap_preflight')
    exec(compile(body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], str(engine), 'exec'), module.__dict__)

    def ids(where):
        return {p.name for p in where.iterdir() if re.fullmatch('[0-9a-f]{32}', p.name)} if where.exists() else set()

    def content(where):
        if where.parent == archive:
            where = where/'snapshot'
        return {p.relative_to(where).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in where.rglob('*') if p.is_file() and not p.is_symlink()}

    def clone(where, number, worker, second, run_id=None):
        key = '%032x' % number
        dest = where/key
        if where == archive:
            dest.mkdir(mode=0o700)
            dest = dest/'snapshot'
        shutil.copytree(template, dest)
        doc = json.loads((dest/'manifest.json').read_text())
        doc.update(save_id=key, worker=worker,
                   published_at='2026-10-10T10:%02d:%02d+00:00' % (second // 60, second % 60))
        if run_id is not None:
            doc['run_id'] = run_id
        # Recompute fingerprint matching updated doc fields
        doc['fingerprint'] = module.fingerprint(doc['git'], doc['entries'], doc['context'])
        (dest/'manifest.json').write_text(json.dumps(doc, indent=1, sort_keys=True) + '\n')
        return key

    def clear_store():
        if store.exists():
            for p in store.iterdir():
                if re.fullmatch('[0-9a-f]{32}', p.name) or p.name in ('archive', '.staging'):
                    if p.is_symlink() or p.is_file(): p.unlink()
                    else: shutil.rmtree(p, ignore_errors=True)
            claims_dir = store/'claims'
            if claims_dir.exists():
                for p in claims_dir.iterdir(): p.unlink()

    def seed_32_distinct():
        clear_store()
        return [clone(store, i + 1, workers[i], i) for i in range(32)]

    def seed_32_grouped():
        clear_store()
        # 8 workers, 4 saves each = 32 saves
        return [clone(store, i + 1, workers[i // 4], i) for i in range(32)]

    # Instrument counters on helper module
    counts = collections.Counter()
    real_capture = module.capture
    real_read_stored_at = module.read_stored_at
    real_load_save = module.load_save

    def instrumented_capture(*args, **kwargs):
        counts['capture'] += 1
        return real_capture(*args, **kwargs)

    def instrumented_read_stored_at(dfd, name, limit):
        # Pool bodies, task context, or bundle
        if name != 'manifest.json':
            counts['body_reads'] += 1
        return real_read_stored_at(dfd, name, limit)

    def instrumented_load_save(*args, **kwargs):
        counts['load_save'] += 1
        return real_load_save(*args, **kwargs)

    module.capture = instrumented_capture
    module.read_stored_at = instrumented_read_stored_at
    module.load_save = instrumented_load_save

    # -------------------------------------------------------------------------
    # 1. Current-Positive: Synthetic 32 worker/full protected store refuses
    #    with ZERO capture and ZERO body reads.
    # -------------------------------------------------------------------------
    initial = seed_32_distinct()
    initial_bytes = {sid: content(store/sid) for sid in initial}
    counts.clear()

    # Worker 32 attempts to save into a store full of 32 distinct workers' newest saves
    wt32 = root/'wt'/workers[32]
    (wt32/'file.txt').write_bytes(b'unobserved\n')
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    attempt_file = store/'attempts'/(workers[32] + '.json')
    attempt_doc = json.loads(attempt_file.read_text()) if attempt_file.exists() else {}

    check('synthetic 32-worker full protected store refuses with exit 1', rc == 1)
    check('preflight refusal performs ZERO capture calls', counts['capture'] == 0)
    check('preflight refusal performs ZERO body/bundle/context reads', counts['body_reads'] == 0)
    check('preflight refusal performs ZERO deep load_save operations', counts['load_save'] == 0)
    check('all 32 original saves and bytes preserved exactly',
          ids(store) == set(initial) and all(content(store/sid) == initial_bytes[sid] for sid in initial))
    check('attempt record preserves status refused and reason excessive',
          attempt_doc.get('status') == 'refused' and attempt_doc.get('reason') == 'excessive'
          and attempt_doc.get('save_id') is None)

    # -------------------------------------------------------------------------
    # 2. Base-Negative: Show that bypassing preflight causes 2 capture passes
    #    and full store body rereads before refusing.
    # -------------------------------------------------------------------------
    counts.clear()
    with patch.object(module, 'capacity_preflight', lambda *a, **k: None):
        with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
            base_rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    check('baseline without preflight also refuses with exit 1', base_rc == 1)
    check('baseline executed exactly 2 worktree capture passes', counts['capture'] == 2)
    check('baseline reread all save bodies during deep scan_store', counts['body_reads'] > 0)
    check('baseline deep loaded all 32 saves', counts['load_save'] == 32)

    # -------------------------------------------------------------------------
    # 3. Corrupted Metadata: remains protected and refuses with zero capture/body reads.
    # -------------------------------------------------------------------------
    initial = seed_32_distinct()
    # Corrupt manifest in save 0 (invalid JSON)
    (store/initial[0]/'manifest.json').write_text('{"bad json')
    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    check('corrupted metadata store refuses with exit 1', rc == 1)
    check('corrupted metadata refusal performs zero capture passes', counts['capture'] == 0)
    check('corrupted metadata refusal performs zero body reads', counts['body_reads'] == 0)
    check('corrupted manifest remains protected in store', (store/initial[0]/'manifest.json').read_text() == '{"bad json')

    # -------------------------------------------------------------------------
    # 4. Claimed Metadata: pinned saves block archival and refuse early.
    # -------------------------------------------------------------------------
    initial = seed_32_grouped()
    # Pin all older saves with valid 0600 claims (older saves are indices != 3 mod 4)
    claims_dir = store/'claims'; claims_dir.mkdir(exist_ok=True)
    claim_count = 0
    for idx, sid in enumerate(initial):
        if idx % 4 != 3:  # Not newest for worker
            cid = '%032x' % (idx + 100)
            claim_doc = dict(schema_version=1, claim_id=cid, save_id=sid,
                             destination='mock-dest', new_task=None, task_sha256=None,
                             source_fingerprint='a'*64, preimage_fingerprint='b'*64,
                             created_at='2026-10-10T10:00:00+00:00',
                             updated_at='2026-10-10T10:00:00+00:00',
                             state='reserved', outcome=None)
            p = claims_dir/(cid + '.json')
            p.write_bytes(json.dumps(claim_doc).encode() + b'\n')
            p.chmod(0o600)
            claim_count += 1

    valid_claims, bad_claims = module.load_claims(str(store))
    check('claims loaded as valid and readable (0 unreadable)', len(valid_claims) == claim_count and bad_claims == 0)
    check('claims pinned expected save IDs', {c['save_id'] for c in valid_claims} == {sid for idx, sid in enumerate(initial) if idx % 4 != 3})

    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    attempt_file = store/'attempts'/(workers[32] + '.json')
    attempt_doc = json.loads(attempt_file.read_text()) if attempt_file.exists() else {}

    check('store with all older saves claimed refuses with exit 1', rc == 1)
    check('claimed store refusal performs zero capture passes', counts['capture'] == 0)
    check('claimed store refusal performs zero body reads', counts['body_reads'] == 0)
    check('all claimed saves remain active in store', ids(store) == set(initial))
    check('attempt record preserves status refused and reason excessive',
          attempt_doc.get('status') == 'refused' and attempt_doc.get('reason') == 'excessive')

    # Verify directly that preflight refusal is due to active project cap, NOT bad_claims
    pre_err = None
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        try:
            module.capacity_preflight(str(store), workers[32], module.Budget(60.0), reason='manual')
        except module.Refuse as e:
            pre_err = e
    check('claimed store preflight refusal message is active project cap reached',
          pre_err is not None and pre_err.code == 'excessive' and 'active project cap reached' in pre_err.message)

    # -------------------------------------------------------------------------
    # 5. Symlink Metadata: symlinks are never followed and refuse early.
    # -------------------------------------------------------------------------
    initial = seed_32_distinct()
    # Replace one save directory with a symlink to an outside directory
    shutil.rmtree(store/initial[0])
    (store/initial[0]).symlink_to(base)
    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    check('symlink directory in store refuses with exit 1', rc == 1)
    check('symlink directory refusal performs zero capture passes', counts['capture'] == 0)
    check('symlink directory refusal performs zero body reads', counts['body_reads'] == 0)
    check('symlink directory was not followed or removed', (store/initial[0]).is_symlink())

    # Replace symlink with valid save, but make manifest.json a symlink
    (store/initial[0]).unlink()
    clone(store, 1, workers[0], 0)
    (store/initial[0]/'manifest.json').unlink()
    (store/initial[0]/'manifest.json').symlink_to(base)
    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    check('symlink manifest in store refuses with exit 1', rc == 1)
    check('symlink manifest refusal performs zero capture passes', counts['capture'] == 0)
    check('symlink manifest refusal performs zero body reads', counts['body_reads'] == 0)
    check('symlink manifest was not followed or deleted', (store/initial[0]/'manifest.json').is_symlink())

    # -------------------------------------------------------------------------
    # 6. Unreadable Claim: blocks archival and refuses with zero capture/body reads.
    # -------------------------------------------------------------------------
    initial = seed_32_grouped()
    bad_claim = store/'claims'/('badclaim' + '0'*24 + '.json')
    bad_claim.write_text('{}')
    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    check('unreadable claim blocks archival and refuses with exit 1', rc == 1)
    check('unreadable claim refusal performs zero capture passes', counts['capture'] == 0)
    check('unreadable claim refusal performs zero body reads', counts['body_reads'] == 0)
    bad_claim.unlink()

    # -------------------------------------------------------------------------
    # 7. Eligible History: stores with unpinned older saves archive & publish.
    # -------------------------------------------------------------------------
    initial = seed_32_grouped()
    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[8]), 'rb'):
        rc = module.create_locked(str(root), workers[8], 'T1', reason='manual')

    check('store with eligible history successfully publishes (exit 0)', rc == 0)
    check('publication executed standard two capture passes', counts['capture'] == 2)
    check('publication archived exactly oldest eligible save', len(ids(store)) == 32 and len(ids(archive)) == 1)

    # -------------------------------------------------------------------------
    # 8. Unchanged Periodic No-op Retained:
    #    When worker has matching run_id save and unchanged worktree, returns 0.
    # -------------------------------------------------------------------------
    initial = seed_32_distinct()
    # Give workers[0] save a specific run_id
    run_id = '0123456789abcdef0123456789abcdef'
    doc0 = json.loads((store/initial[0]/'manifest.json').read_text())
    doc0['run_id'] = run_id
    doc0['fingerprint'] = module.fingerprint(doc0['git'], doc0['entries'], doc0['context'])
    (store/initial[0]/'manifest.json').write_text(json.dumps(doc0) + '\n')

    # Ensure worker[0] worktree matches fingerprint exactly
    module.unio_restore_save = None  # Just use unio CLI restore
    unio('save', 'restore', initial[0], workers[0])

    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[0]), 'rb'):
        rc = module.create_locked(str(root), workers[0], 'T1', reason='periodic', run_id=run_id)

    check('unchanged periodic capture returns exit 0 (keeps previous)', rc == 0)
    check('store still has exactly 32 saves without duplication', len(ids(store)) == 32)

    # A periodic capture for a worker with NO saves in the store still refuses early
    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='periodic', run_id='unmatched-run')

    check('periodic save without matching run_id refuses with exit 1', rc == 1)
    check('unmatched periodic refusal performs zero capture passes', counts['capture'] == 0)
    check('unmatched periodic refusal performs zero body reads', counts['body_reads'] == 0)

    # -------------------------------------------------------------------------
    # 9. Worker Cap Refusal: 8 saves for same worker with no archival eligibility.
    # -------------------------------------------------------------------------
    clear_store()
    w_saves = [clone(store, i + 1, workers[0], i) for i in range(8)]
    # Pin all 8 saves with valid 0600 claims
    for idx, sid in enumerate(w_saves):
        cid = '%032x' % (idx + 200)
        claim_doc = dict(schema_version=1, claim_id=cid, save_id=sid,
                         destination='mock-dest', new_task=None, task_sha256=None,
                         source_fingerprint='a'*64, preimage_fingerprint='b'*64,
                         created_at='2026-10-10T10:00:00+00:00',
                         updated_at='2026-10-10T10:00:00+00:00',
                         state='reserved', outcome=None)
        p = claims_dir/(cid + '.json')
        p.write_bytes(json.dumps(claim_doc).encode() + b'\n')
        p.chmod(0o600)

    w_claims, w_bad = module.load_claims(str(store))
    check('worker cap claims loaded as valid (0 unreadable)', len(w_claims) == 8 and w_bad == 0)
    check('worker cap pins cover all 8 saves', {c['save_id'] for c in w_claims} == set(w_saves))

    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[0]), 'rb'):
        rc = module.create_locked(str(root), workers[0], 'T1', reason='manual')

    check('worker cap reached refuses with exit 1', rc == 1)
    check('worker cap refusal performs zero capture passes', counts['capture'] == 0)
    check('worker cap refusal performs zero body reads', counts['body_reads'] == 0)

    w_err = None
    with os.fdopen(module.require_lock(str(root), workers[0]), 'rb'):
        try:
            module.capacity_preflight(str(store), workers[0], module.Budget(60.0), reason='manual')
        except module.Refuse as e:
            w_err = e
    check('worker cap preflight refusal message is active worker cap reached',
          w_err is not None and w_err.code == 'excessive' and 'active worker cap reached' in w_err.message)

    # -------------------------------------------------------------------------
    # 10. Already Overfull Store (>32 active entries) refuses with zero capture.
    # -------------------------------------------------------------------------
    initial = seed_32_distinct()
    overcap = store/('e'*32); overcap.mkdir(mode=0o700)
    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
        rc = module.create_locked(str(root), workers[32], 'T1', reason='manual')

    check('already overfull store (>32) refuses with exit 1', rc == 1)
    check('overfull store refusal performs zero capture passes', counts['capture'] == 0)
    check('overfull store refusal performs zero body reads', counts['body_reads'] == 0)
    overcap.rmdir()

    # -------------------------------------------------------------------------
    # 11. Concurrent Interleaving Race: preflight falls through on ambiguity
    #     without false refusal; quiescent store refuses (current-positive).
    # -------------------------------------------------------------------------
    clear_store()
    # 30 distinct workers' newest saves + worker 2 with older X and newer Z
    for i in range(30):
        clone(store, i + 1, workers[i], i)
    X = clone(store, 0xa1, workers[2], 50)
    Z = clone(store, 0xa2, workers[2], 55)
    Y = '%032x' % 0xa3
    race_staging = base/'race_staging'; race_staging.mkdir(mode=0o700, exist_ok=True)
    clone(race_staging, 0xa3, workers[2], 70)

    real_bounded = module.bounded_names
    interleaved_state = {'done': False}
    def interleaved_bounded(path, limit=4096):
        names = real_bounded(path, limit)
        if str(path) == str(store) and not interleaved_state['done']:
            interleaved_state['done'] = True
            arch = module.archive_for_store(str(store), True)
            module.archive_save(str(store), X, arch)
            os.rename(str(race_staging/Y), str(store/Y))
        return names

    module.bounded_names = interleaved_bounded
    race_res = None
    try:
        try:
            module.capacity_preflight(str(store), workers[1], module.Budget(60.0))
        except Exception as e:
            race_res = (type(e).__name__, getattr(e, 'code', None), getattr(e, 'message', str(e)))
    finally:
        module.bounded_names = real_bounded

    post_plan = None
    try:
        module.retention_plan(str(store), workers[1], module.Budget(60.0))
    except Exception as e:
        post_plan = (type(e).__name__, getattr(e, 'code', None), getattr(e, 'message', str(e)))

    check('interleaved preflight does NOT falsely refuse (falls through on ambiguity)', race_res is None)
    check('post-state retention plan confirms publication would succeed', post_plan is None)

    # Current-positive: without interleaving, quiescent store with 32 protected saves refuses
    clear_store()
    seed_32_distinct()
    quiescent_res = None
    try:
        module.capacity_preflight(str(store), workers[32], module.Budget(60.0))
    except Exception as e:
        quiescent_res = (type(e).__name__, getattr(e, 'code', None))
    check('quiescent full store without interleaving refuses excessive', quiescent_res == ('Refuse', 'excessive'))

    # -------------------------------------------------------------------------
    # 12. Changed Periodic Save into Full Store: avoids deep full-store rereads.
    # -------------------------------------------------------------------------
    initial = seed_32_distinct()
    p_run = '0123456789abcdef0123456789abcdef'
    doc0 = json.loads((store/initial[0]/'manifest.json').read_text())
    doc0['run_id'] = p_run
    doc0['fingerprint'] = module.fingerprint(doc0['git'], doc0['entries'], doc0['context'])
    (store/initial[0]/'manifest.json').write_text(json.dumps(doc0) + '\n')

    # Modify worker 0's worktree so it has genuine uncommitted changes (proves changed)
    (root/'wt'/workers[0]/'file.txt').write_bytes(b'changed-periodic-content\n')

    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[0]), 'rb'):
        rc = module.create_locked(str(root), workers[0], 'T1', reason='periodic', run_id=p_run)

    attempt_file = store/'attempts'/(workers[0] + '.json')
    attempt_doc = json.loads(attempt_file.read_text()) if attempt_file.exists() else {}

    check('changed periodic save into full store refuses with exit 1', rc == 1)
    check('changed periodic executed exactly 2 capture passes to prove changes', counts['capture'] == 2)
    check('changed periodic avoids full-store body rereads (< 32 saves read)', counts['body_reads'] < 32)
    check('changed periodic does NOT deep-load all 32 saves (only selected save checked)', counts['load_save'] <= 3)
    check('changed periodic attempt status is refused and reason is excessive',
          attempt_doc.get('status') == 'refused' and attempt_doc.get('reason') == 'excessive'
          and attempt_doc.get('save_id') is None)

    # -------------------------------------------------------------------------
    # 13. Budget Deadline Exhaustion during Periodic Archive Enumeration.
    # -------------------------------------------------------------------------
    clear_store()
    seed_32_distinct()
    arch = store/'archive'
    arch.mkdir(mode=0o700, exist_ok=True)
    clone(arch, 999, workers[0], 0, run_id='run-arch')
    expired_budget = module.Budget(0.001)
    expired_budget.deadline = time.monotonic() - 1.0  # Already expired
    deadline_refused = False
    try:
        module.capacity_preflight(str(store), workers[32], expired_budget, reason='periodic', run_id='unmatched')
    except module.Refuse as r:
        if r.code == 'excessive' and 'second bound' in r.message:
            deadline_refused = True
    check('expired budget during periodic archive scan raises excessive refusal', deadline_refused)

    with patch.object(module, 'Budget', lambda sec: expired_budget):
        with os.fdopen(module.require_lock(str(root), workers[32]), 'rb'):
            rc = module.create_locked(str(root), workers[32], 'T1', reason='periodic', run_id='unmatched')

    attempt_file = store/'attempts'/(workers[32] + '.json')
    attempt_doc = json.loads(attempt_file.read_text()) if attempt_file.exists() else {}

    check('deadline exhaustion in create_locked returns exit 1', rc == 1)
    check('deadline exhaustion attempt doc records status refused and reason excessive',
          attempt_doc.get('status') == 'refused' and attempt_doc.get('reason') == 'excessive')

    # -------------------------------------------------------------------------
    # 14. Archived Same-Run Periodic Exemption:
    #     Worker matching save only in archive falls through and returns 0 when unchanged.
    # -------------------------------------------------------------------------
    clear_store()
    for i in range(32):
        clone(store, i + 1, workers[i + 1], i)
    arch.mkdir(mode=0o700, exist_ok=True)
    arch_sid = clone(arch, 888, workers[0], 0, run_id='run-arch-match')

    # Restore worker 0 worktree to match template
    git(wt0, 'reset', '-q', '--hard', 'HEAD')
    (wt0/'file.txt').write_bytes(b'staged\0bytes\n'); git(wt0, 'add', 'file.txt')
    (wt0/'file.txt').write_bytes(b'working\0bytes\n')
    (wt0/'new.bin').write_bytes(bytes(range(256)))

    counts.clear()
    with os.fdopen(module.require_lock(str(root), workers[0]), 'rb'):
        rc = module.create_locked(str(root), workers[0], 'T1', reason='periodic', run_id='run-arch-match')

    check('archived same-run periodic unchanged returns exit 0', rc == 0)
    check('archived same-run unchanged did not increase active store count', len(ids(store)) == 32)

    print('Save capacity preflight: %d checks passed' % passed)
