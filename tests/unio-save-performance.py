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
    (base/'conf/agents.conf').write_text("mock=sh -c 'echo invoked >> \"%s\"; exit 99'\n" % calls)
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

    # This count is through the installed helper, not a mirrored loader.
    counts = collections.Counter(); private_at = module.private_at

    def counted(dfd, name, kind):
        counts[kind] += 1
        return private_at(dfd, name, kind)

    with patch.object(module, 'private_at', counted):
        loaded = module.load_save(str(original), sid, True)
    check('deep loader avoids pathname file preflight for body bytes', counts['file'] == 1)
    check('loaded worktree bytes exact', b'working\0bytes\n' in loaded['bodies'].values())
    check('loaded index bytes exact', b'staged\0bytes\n' in loaded['bodies'].values())
    restored = unio('save', 'restore', sid, 'mock-dest')
    check('installed exact restore succeeds', restored.returncode == 0)
    dest = root/'wt/mock-dest'
    check('restore worktree bytes exact', (dest/'file.txt').read_bytes() == (wt/'file.txt').read_bytes()
          and (dest/'new.bin').read_bytes() == (wt/'new.bin').read_bytes())
    check('restore index exact', git(dest, 'ls-files', '--stage', '-z') == git(wt, 'ls-files', '--stage', '-z'))
    # Claimed source is pinned. A different worker's newest must also survive.
    old = [clone(n) for n in range(1, 7)]
    newest = old[-1][0]
    (wt/'new.bin').write_bytes(b'next state')
    check('retention capture succeeds', unio('save', 'create', 'mock-source', 'T').returncode == 0)
    check('claim pin and other worker newest survive', original.exists() and (store/newest).exists())

    def refused(path, key):
        try:
            module.load_save(str(path), key, True)
        except module.Refuse:
            return True
        return False

    bad_id, bad = clone(10, 'corrupt-worker')
    pooled = next((bad/'pool').iterdir()); exact = pooled.read_bytes()
    pooled.write_bytes(b'z'*len(exact))
    check('same-size corrupted old body refused', refused(bad, bad_id))
    bad_manifest_id, bad_manifest = clone(11, 'corrupt-worker')
    (bad_manifest/'manifest.json').write_text('{}\n')
    check('corrupted old manifest refused', refused(bad_manifest, bad_manifest_id))
    unsafe_id, unsafe = clone(12, 'unsafe-worker')
    unsafe_file = next((unsafe/'pool').iterdir()); target = base/'outside'; target.write_bytes(unsafe_file.read_bytes())
    unsafe_file.unlink(); unsafe_file.symlink_to(target)
    check('stored symlink refused', refused(unsafe, unsafe_id))
    hard_id, hard = clone(13, 'unsafe-worker')
    hard_file = next((hard/'pool').iterdir()); os.link(hard_file, base/'hard-link')
    check('stored hardlink refused', refused(hard, hard_id))
    mode_id, mode = clone(14, 'unsafe-worker')
    mode_file = next((mode/'pool').iterdir()); mode_file.chmod(0o644)
    check('stored mode refused', refused(mode, mode_id))
    protected = [bad, bad_manifest, unsafe, hard, mode]
    before = {str(p): hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest() for p in protected}
    (wt/'new.bin').write_bytes(b'after corrupt history')
    result = unio('save', 'create', 'mock-source', 'T')
    check('capture preserves corrupt evidence', result.returncode == 0
          and all(p.exists() and hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest() == before[str(p)]
                  for p in protected))
    check('last good remains inspectable', unio('save', 'inspect', '--worker', 'mock-source', '--json').returncode == 0)
    # Change privacy metadata at open, after any pathname preflight. The
    # installed loader must validate the descriptor before reading its bytes.
    race_id, race = clone(15, 'race-worker')
    race_file = next((race/'pool').iterdir())
    original_open = os.open

    def racing_open(name, flags, *args, **kwargs):
        if name == race_file.name:
            race_file.chmod(0o644)
        return original_open(name, flags, *args, **kwargs)

    with patch.object(module.os, 'open', racing_open):
        check('privacy change at open refused on actual descriptor', refused(race, race_id))
    race_file.chmod(0o600)
    # Worktree observations still perform fresh reads on each pass.
    capture = module.capture; observations = [0]

    def changing(*args, **kwargs):
        result = capture(*args, **kwargs)
        observations[0] += 1
        if observations[0] == 1:
            (wt/'new.bin').write_bytes(b'changed between observations')
        return result

    with patch.dict(os.environ, env), patch.object(module, 'capture', changing):
        check('changing worktree refused across real observations', module.cmd_create(str(root), 'mock-source', 'T') != 0)
    check('both observations performed', observations[0] == 2)
    check('provider never invoked', not calls.exists())
print('%d save-performance checks passed' % passed)
