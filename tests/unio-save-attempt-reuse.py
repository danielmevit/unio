#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed offline save workflows and descriptor-bound storage validation."""
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


with tempfile.TemporaryDirectory(prefix='save-performance-') as directory:
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
    module = types.ModuleType('installed_save_performance')
    exec(compile(body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], str(engine), 'exec'), module.__dict__)

    def clone(number, worker='old-worker'):
        key = '%032x' % number; dest = store/key; shutil.copytree(template, dest)
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

    # Every success is compared to a fresh installed metadata-only lookup.
    def success(label):
        loads.clear()
        with patch.object(module, 'load_save', counted), patch.object(module, 'write_attempt', locked_write), patch.object(module, 'last_good', side_effect=AssertionError('redundant last_good')):
            check(label, create() == 0)
        expected = real_last(str(store), 'mock-source', False)
        check(label + ' metadata identity', attempt()['last_good_id'] == expected['id'])

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
    tied, tied_path = clone(2, 'mock-source')
    doc = json.loads((tied_path/'manifest.json').read_text())
    doc['published_at'] = '2099-01-01T00:00:00+00:00'
    (tied_path/'manifest.json').write_text(json.dumps(doc)+'\n')
    with patch.object(module, 'stamp', return_value='2099-01-01T00:00:00+00:00'):
        success('tied publication times preserve ID ordering')

    check('restore claim pin survives captures', original.exists())
    with patch.object(module, 'CAP_PROJECT', 0):
        check('project cap refusal preserved', create() != 0)
    real_atomic = module.atomic_private
    def failed_attempt(path, data):
        if '/attempts/' in path:
            raise OSError('injected attempt write failure')
        return real_atomic(path, data)
    with patch.object(module, 'atomic_private', failed_attempt):
        check('attempt write failure remains nonfatal', create() == 0)

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
    wrapper = archive/tied; wrapper.mkdir(mode=0o700)
    shutil.copytree(tied_path, wrapper/'snapshot')
    check('duplicate active/archive refuses', create() != 0)
    shutil.rmtree(wrapper)
    bad = archive/('%032x' % 99); bad.mkdir(mode=0o700)
    check('corrupt archive refuses', create() != 0)
    shutil.rmtree(bad)
    check('provider never invoked', not calls.exists())
print('%d save-attempt-reuse checks passed' % passed)
