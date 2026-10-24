#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed save-attempt identity, archival reuse and failure bookkeeping."""
import collections
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import types
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
passed = 0


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='save-attempt-reuse-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
               UNIO_COMPLETION_DIR=str(base/'completion'), UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_SAVE_CAPTURE_TIMEOUT='300',
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
    check('real Git workers initialize', unio('init', 'mock-source', 'mock-dest').returncode == 0)
    unio('stop')
    (root/'coord/tasks/T.md').write_text('# T\nOffline only\n')
    wt = root/'wt/mock-source'
    (wt/'committed.txt').write_bytes(b'carried commit\n')
    git(wt, 'add', 'committed.txt'); git(wt, 'commit', '-qm', 'carried')
    (wt/'file.txt').write_bytes(b'staged\0bytes\n'); git(wt, 'add', 'file.txt')
    (wt/'file.txt').write_bytes(b'working\0bytes\n')
    (wt/'new.bin').write_bytes(bytes(range(256)))
    created = unio('save', 'create', 'mock-source', 'T')
    match = re.search(r'^saved ([0-9a-f]{32}):', created.stdout, re.M)
    check('installed save succeeds', created.returncode == 0 and match is not None)
    sid = match[1]; store = root/'coord/saves'; original = store/sid
    template = base/'template'; shutil.copytree(original, template)
    body = engine.read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY\n', 1)[0]
    module = types.ModuleType('installed_save_attempt_reuse')
    exec(compile(body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], str(engine), 'exec'), module.__dict__)

    def clone(number, worker='old-worker', key=None):
        key = key or '%032x' % number; dest = store/key; shutil.copytree(template, dest)
        doc = json.loads((dest/'manifest.json').read_text())
        doc.update(save_id=key, worker=worker, published_at='2026-10-01T00:00:%02d+00:00' % number)
        (dest/'manifest.json').write_text(json.dumps(doc)+'\n')
        return key, dest

    def attempt():
        return json.loads((store/'attempts/mock-source.json').read_text())

    restored = unio('save', 'restore', sid, 'mock-dest')
    dest = root/'wt/mock-dest'
    check('exact restoration including index and carried HEAD', restored.returncode == 0
          and (dest/'file.txt').read_bytes() == (wt/'file.txt').read_bytes()
          and (dest/'new.bin').read_bytes() == (wt/'new.bin').read_bytes()
          and git(dest, 'ls-files', '--stage', '-z') == git(wt, 'ls-files', '--stage', '-z')
          and git(dest, 'rev-parse', 'HEAD') == git(wt, 'rev-parse', 'HEAD'))

    real_write = module.write_attempt
    def locked_write(*args, **kwargs):
        if kwargs.get('known_good') is not None:
            with (root/'coord/.locks/saves.lock').open('rb') as lock:
                try:
                    module.fcntl.flock(lock, module.fcntl.LOCK_EX | module.fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    raise AssertionError('successful attempt escaped publication lock')
        return real_write(*args, **kwargs)

    real_load = module.load_save
    real_last = module.last_good
    loads = collections.Counter()
    def counted(path, key, deep):
        loads[(key, deep)] += 1
        return real_load(path, key, deep)

    def create():
        with patch.dict(os.environ, env):
            return module.cmd_create(str(root), 'mock-source', 'T')

    def active_ids():
        return {p.name for p in store.iterdir() if re.fullmatch('[0-9a-f]{32}', p.name)}

    def bytes_under(path):
        return {str(p.relative_to(path)): p.read_bytes() for p in path.rglob('*') if p.is_file()}

    def source_state():
        return (bytes_under(wt), git(wt, 'ls-files', '--stage', '-z'),
                git(wt, 'rev-parse', 'HEAD'), bytes_under(store/'claims'))

    # Observe the installed publisher's return, independently of attempt metadata.
    # Every success requires a fresh complete record for exactly this publication.
    def success(label, must_archive=False):
        loads.clear()
        before = active_ids()
        preserved = source_state()
        old_bytes = {key: bytes_under(store/key) for key in before}
        with patch.object(module, 'load_save', counted), patch.object(module, 'write_attempt', wraps=locked_write) as writes, patch.object(module, 'publish', wraps=module.publish) as published, patch.object(module, 'last_good', side_effect=AssertionError('redundant last_good')):
            check(label, create() == 0)
        new = active_ids() - before
        check(label + ' exactly one new publication', len(new) == 1 and published.call_count == 1)
        new_id = next(iter(new))
        record = attempt()
        check(label + ' current complete attempt', record['status'] == 'complete' and record['save_id'] == new_id)
        check(label + ' exactly one known_good write', writes.call_count == 1
              and writes.call_args.kwargs.get('known_good') is not None
              and writes.call_args.args[6] == new_id)
        expected = real_last(str(store), 'mock-source', False)
        check(label + ' metadata identity', record['last_good_id'] == expected['id'])
        moved = before - active_ids()
        if must_archive:
            check(label + ' actually archives history', bool(moved))
        check(label + ' archived IDs and bytes preserved', all(
            not (store/key).exists() and bytes_under(store/'archive'/key/'snapshot') == old_bytes[key]
            for key in moved))
        check(label + ' source bytes and claim pins preserved', source_state() == preserved
              and original.exists())
        return new_id

    success('ordinary successful capture avoids last_good traversal')
    check('existing valid save loaded once deeply and never metadata-only',
          loads[(sid, True)] == 1 and loads[(sid, False)] == 0)
    future, future_path = clone(1, 'mock-source')
    doc = json.loads((future_path/'manifest.json').read_text())
    doc['published_at'] = '2099-01-01T00:00:00+00:00'
    (future_path/'manifest.json').write_text(json.dumps(doc)+'\n')
    success('future history wins over new save')
    check('future selected', attempt()['last_good_id'] == future)
    pooled = next((future_path/'pool').iterdir())
    pooled.write_bytes(b'z'*len(pooled.read_bytes()))
    success('metadata-valid body-corrupt future history remains eligible')
    check('deep failure gets one metadata fallback', loads[(future, True)] == 1 and loads[(future, False)] == 1)
    # A no-op current write must fail the same success assertion even though
    # the metadata-only winner remains the future save from the prior attempt.
    stale = attempt()
    original_atomic = module.atomic_private
    def skipped_attempt(path, data):
        if '/attempts/' in path:
            return None  # Silently discard only the current attempt publication.
        return original_atomic(path, data)
    try:
        with patch.object(module, 'atomic_private', skipped_attempt):
            success('negative control skips current attempt write')
    except AssertionError as error:
        check('skipped current write detected by identity assertion',
              str(error) == 'negative control skips current attempt write current complete attempt'
              and attempt() == stale
              and real_last(str(store), 'mock-source', False)['id'] == stale['last_good_id'])
    else:
        raise AssertionError('skipped current attempt write escaped success assertions')

    archive = store/'archive'; archive.mkdir(exist_ok=True, mode=0o700)
    archived, archived_path = clone(3, 'mock-source')
    doc = json.loads((archived_path/'manifest.json').read_text())
    doc['published_at'] = '2100-01-01T00:00:00+00:00'
    (archived_path/'manifest.json').write_text(json.dumps(doc)+'\n')
    wrapper = archive/archived; wrapper.mkdir(mode=0o700)
    shutil.move(str(archived_path), wrapper/'snapshot')
    archived_bytes = bytes_under(wrapper/'snapshot')
    for number in range(10, 16):
        clone(number, 'mock-source')
    success('existing future archive wins while active history is archived', must_archive=True)
    check('future archive selected with bytes intact', attempt()['last_good_id'] == archived
          and bytes_under(wrapper/'snapshot') == archived_bytes)

    real_urandom = os.urandom
    def pinned_save_id(value):
        # Pin only the first 16-byte request (the save ID); delegate every other
        # call, including atomic_private's 8-byte nonce, to the real function.
        sizes = []
        def fake(n):
            sizes.append(n)
            if n == 16 and sizes.count(16) == 1:
                return bytes.fromhex(value)
            return real_urandom(n)
        return patch.object(module.os, 'urandom', side_effect=fake), sizes

    def fixed_tie(when, existing_key, new_key, label, publisher=None, must_archive=False):
        existing, existing_path = clone(4, 'mock-source', key=existing_key)
        doc = json.loads((existing_path/'manifest.json').read_text())
        doc['published_at'] = when
        (existing_path/'manifest.json').write_text(json.dumps(doc)+'\n')
        pin, sizes = pinned_save_id(new_key)
        with patch.object(module, 'stamp', return_value=when), pin, patch.object(module, 'publish', publisher or module.publish):
            new_id = success(label, must_archive=must_archive)
        check(label + ' pins only the save ID', new_id == new_key and sizes.count(16) >= 1
              and 8 in sizes and attempt()['last_good_id'] in (existing, new_key))
        return existing, existing_path, new_id

    tied, tied_path, new_id = fixed_tie('2100-01-01T00:00:00+00:00', 'f'*32, '1'*32,
                                        'existing ID deterministically wins publication tie', must_archive=True)
    check('existing tie winner beats deliberately lower new ID',
          new_id == '1'*32 and attempt()['last_good_id'] == tied)
    lower, _, new_id = fixed_tie('2101-01-01T00:00:00+00:00', '2'*32, 'e'*32,
                                 'new ID deterministically wins publication tie')
    check('new tie winner beats deliberately lower existing ID',
          new_id == 'e'*32 and attempt()['last_good_id'] == 'e'*32 != lower)

    # Behavioral mutation control: an in-memory publish lacking only its ID
    # tie-break, bound to the installed globals, must fail the new-wins case.
    # The oracle (real_last) remains the unmodified installed last_good.
    tie_key = "key=lambda item: (item['published'], item['id']))\n"
    anchor = "good = max((item for item in metadata if item['worker'] == worker),\n"
    start = body.index(anchor); end = body.index(tie_key, start) + len(tie_key)
    check('publish ID tie-break located exactly once', body.count(body[start:end]) == 1
          and body[start:end].count('\n') == 2)
    mutant_body = body[:start] + anchor + body[start+len(anchor):end].replace(
        "(item['published'], item['id'])", "item['published']") + body[end:]
    mutant_ns = {}
    exec(compile(mutant_body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], 'mutant', 'exec'), mutant_ns)
    mutant = types.FunctionType(mutant_ns['publish'].__code__, module.__dict__, 'publish',
                                mutant_ns['publish'].__defaults__)
    label = 'mutant without ID tie-break'
    try:
        fixed_tie('2102-01-01T00:00:00+00:00', '3'*32, 'd'*32, label, publisher=mutant)
    except AssertionError as error:
        check('missing ID tie-break detected by fresh metadata identity',
              str(error) == label + ' metadata identity'
              and 'd'*32 in active_ids() and attempt()['save_id'] == 'd'*32
              and attempt()['last_good_id'] == '3'*32
              and real_last(str(store), 'mock-source', False)['id'] == 'd'*32)
    else:
        raise AssertionError('publish without ID tie-break escaped new-wins assertions')

    check('restore claim pin survives captures', original.exists())
    with patch.object(module, 'CAP_PROJECT', 0):
        check('project cap refusal preserved', create() != 0)
    real_atomic = module.atomic_private
    def failed_attempt(path, data):
        if '/attempts/' in path:
            raise OSError('injected attempt write failure')
        return real_atomic(path, data)
    with patch.object(module, 'atomic_private', failed_attempt), patch.object(module, 'write_attempt', wraps=locked_write) as writes:
        before = active_ids()
        check('attempt write failure remains nonfatal', create() == 0)
        new = active_ids() - before
        check('nonfatal failure still attempts exactly one current known_good write',
              len(new) == 1 and writes.call_count == 1
              and writes.call_args.kwargs.get('known_good') is not None
              and writes.call_args.args[5] == 'complete'
              and writes.call_args.args[6] == next(iter(new)))

    real_capture = module.capture
    observations = [0]
    def changing(*args, **kwargs):
        result = real_capture(*args, **kwargs)
        observations[0] += 1
        if observations[0] == 1:
            (wt/'new.bin').write_bytes(b'changed between stable observations')
        return result
    with patch.object(module, 'capture', changing):
        check('stable-byte refusal remains fresh', create() != 0 and observations[0] == 2
              and attempt()['reason'] == 'unstable'
              and attempt()['last_good_id'] == real_last(str(store), 'mock-source', False)['id'])

    # A fresh lookup remains mandatory on refusal, including publication faults.
    for fault in ('between-passes', 'publish-interrupt', 'publish-after-rename'):
        real_fault = module.fault
        def injected(name):
            if name == fault:
                raise module.Refuse('io_error', 'catchable test fault: ' + name)
            return real_fault(name)
        with patch.dict(os.environ, env), patch.object(module, 'fault', injected), patch.object(module, 'last_good', wraps=real_last) as lookup:
            result = module.cmd_create(str(root), 'mock-source', 'T')
        check(fault + ' refuses with fresh bookkeeping', result != 0 and lookup.call_count == 1)
        check(fault + ' identity remains equivalent', attempt()['last_good_id'] == real_last(str(store), 'mock-source', False)['id'])

    archive = store/'archive'; archive.mkdir(exist_ok=True, mode=0o700)
    duplicate = max(active_ids())  # Extra tie captures may have archived fff....
    wrapper = archive/duplicate; wrapper.mkdir(mode=0o700)
    shutil.copytree(store/duplicate, wrapper/'snapshot')
    check('duplicate active/archive refuses', create() != 0)
    shutil.rmtree(wrapper)
    bad = archive/('%032x' % 99); bad.mkdir(mode=0o700)
    check('corrupt archive refuses', create() != 0)
    shutil.rmtree(bad)
    check('provider never invoked', not calls.exists())
print('%d save-attempt-reuse checks passed' % passed)
