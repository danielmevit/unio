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


with tempfile.TemporaryDirectory(prefix='save-latest-lookup-') as directory:
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
    module = types.ModuleType('installed_save_latest_lookup')
    exec(compile(body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], str(engine), 'exec'), module.__dict__)

    def clone(number, worker='old-worker'):
        key = '%032x' % number; dest = store/key; shutil.copytree(template, dest)
        doc = json.loads((dest/'manifest.json').read_text())
        doc.update(save_id=key, worker=worker, published_at='2026-10-01T00:00:%02d+00:00' % number)
        (dest/'manifest.json').write_text(json.dumps(doc)+'\n')
        return key, dest

    # Populated supported saves; bodies are copied, never fabricated manifests.
    for n in range(1, 13):
        clone(n, 'foreign-worker')
    counts = collections.Counter()
    real_load, real_private = module.load_save, module.private_at
    def counted_load(path, key, deep):
        counts['loads'] += 1
        if key != sid:
            counts['foreign_loads'] += 1
        return real_load(path, key, deep)
    def counted_private(fd, name, kind):
        if kind == 'file' and module.HEX64.fullmatch(name):
            counts['pool_stats'] += 1
        return real_private(fd, name, kind)
    with patch.object(module, 'load_save', counted_load), patch.object(module, 'private_at', counted_private):
        found = module.last_good(str(store), 'mock-source', False)
    check('populated fixture selects supported original', found['id'] == sid)
    print('LOOKUP COUNTERS ' + json.dumps(dict(counts), sort_keys=True), flush=True)
    check('lookup avoids unrelated full metadata loads', counts['foreign_loads'] == 0 and counts['loads'] == 1)
    check('lookup stats only selected pool', counts['pool_stats'] == len(list((original/'pool').iterdir())))
