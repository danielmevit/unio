#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed latest lookup equivalence, conservative races and bounded I/O work."""
import collections
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
        key, _ = clone(n, 'foreign-worker')
        if n > 6:
            archive = module.archive_for_store(str(store), True)
            module.archive_save(str(store), key, archive)
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
    real_read_at, real_read_stored = module.read_at, module.read_stored_at
    def counted_read_at(fd, name, *args, **kwargs):
        if name == 'manifest.json': counts['manifest_reads'] += 1
        return real_read_at(fd, name, *args, **kwargs)
    def counted_read_stored(fd, name, *args, **kwargs):
        if name == 'manifest.json': counts['manifest_reads'] += 1
        return real_read_stored(fd, name, *args, **kwargs)
    with patch.object(module, 'load_save', counted_load), patch.object(module, 'private_at', counted_private), \
            patch.object(module, 'read_at', counted_read_at), patch.object(module, 'read_stored_at', counted_read_stored):
        found = module.last_good(str(store), 'mock-source', False)
    check('populated fixture selects supported original', found['id'] == sid)
    counts['foreign_loads'] += 0
    print('LOOKUP COUNTERS ' + json.dumps(dict(counts), sort_keys=True), flush=True)
    check('lookup avoids unrelated full metadata loads', counts['foreign_loads'] == 0 and counts['loads'] == 1)
    check('lookup stats only selected pool', counts['pool_stats'] == len(list((original/'pool').iterdir())))

    def fixture(label):
        directory = base/label
        directory.mkdir(mode=0o700)
        for name in ('attempts', 'claims'):
            (directory/name).mkdir(mode=0o700)
        return directory

    def put(directory, key, worker='wanted', stamp='2099-01-01T00:00:00+00:00', archived=False):
        if archived:
            archive = directory/'archive'; archive.mkdir(mode=0o700, exist_ok=True)
            wrapper = archive/key; wrapper.mkdir(mode=0o700)
            path = wrapper/'snapshot'
        else:
            path = directory/key
        shutil.copytree(template, path)
        doc = json.loads((path/'manifest.json').read_text())
        doc.update(save_id=key, worker=worker, published_at=stamp)
        (path/'manifest.json').write_text(json.dumps(doc)+'\n')
        return path

    def reference(directory, worker, deep):
        # Pre-optimization semantics via the installed public validators.
        active, bad = module.scan_store(str(directory))
        archive = module.archive_for_store(str(directory))
        history, old_bad = module.scan_archive(archive)
        if {i['id'] for i in active + bad} & {i['id'] for i in history + old_bad}:
            raise module.Refuse('invalid_save', 'duplicate active/archive save ID')
        for item in sorted(active + history, key=lambda i: (i['published'], i['id']), reverse=True):
            if item['worker'] != worker:
                continue
            try:
                if deep:
                    path = module.archived_path(archive, item['id']) if item['archived'] else str(directory/item['id'])
                    module.load_save(path, item['id'], True)
                return item
            except module.Refuse:
                pass
        return None

    def outcome(call):
        try:
            return ('item', call())
        except module.Refuse as error:
            return ('refuse', error.code, error.message)

    def equivalent(label, directory, expected, worker='wanted'):
        for deep in (False, True):
            result = outcome(lambda: module.last_good(str(directory), worker, deep))
            check(label + ' complete shape/reference deep=' + str(deep),
                  result == outcome(lambda: reference(directory, worker, deep)))
            if expected == 'refuse':
                check(label + ' refusal deep=' + str(deep), result[0] == 'refuse')
            else:
                check(label + ' selection deep=' + str(deep), result[0] == 'item'
                      and (result[1]['id'] if result[1] else None) == expected)

    low, high = '1'*32, 'e'*32
    d = fixture('empty'); equivalent('empty', d, None)
    put(d, low, 'foreign', archived=True); equivalent('foreign history', d, None)
    d = fixture('ordering')
    put(d, low); put(d, high, archived=True)
    equivalent('archive wins future timestamp tie by ID', d, high)
    shutil.rmtree(d/'archive'); put(d, high)
    equivalent('active wins future timestamp tie by ID', d, high)
    shutil.rmtree(d/high); put(d, high, stamp='2001-01-01T00:00:00+00:00', archived=True)
    equivalent('publication time precedes ID', d, low)

    d = fixture('only-invalid'); path = put(d, high)
    next((path/'pool').iterdir()).unlink()
    equivalent('only invalid metadata means no usable save', d, None)
    shutil.rmtree(path); path = put(d, high)
    pooled = next((path/'pool').iterdir()); pooled.write_bytes(b'z'*len(pooled.read_bytes()))
    check('only byte-corrupt save shallow eligible deep empty',
          module.last_good(str(d), 'wanted', False)['id'] == high and module.last_good(str(d), 'wanted', True) is None)

    # Newest hints remain untrusted until every ordinary metadata check passes.
    for kind in ('missing-body', 'extra-body', 'body-size', 'body-mode', 'body-link',
                 'body-hardlink', 'body-fifo', 'missing-task', 'missing-bundle',
                 'extra-entry', 'manifest-malformed', 'manifest-oversized',
                 'manifest-mode', 'manifest-link', 'manifest-hardlink', 'fingerprint',
                 'context-mode', 'task-size', 'directory-link', 'directory-mode'):
        d = fixture(kind); put(d, low, stamp='2001-01-01T00:00:00+00:00')
        path = put(d, high)
        pooled = next((path/'pool').iterdir())
        if kind == 'missing-body': pooled.unlink()
        elif kind == 'extra-body': (path/'pool'/('a'*64)).write_bytes(b'extra')
        elif kind == 'body-size': pooled.write_bytes(b'wrong size')
        elif kind == 'body-mode': pooled.chmod(0o644)
        elif kind == 'body-link':
            pooled.unlink(); pooled.symlink_to(next((template/'pool').iterdir()))
        elif kind == 'body-hardlink': os.link(pooled, base/(kind+'-outside'))
        elif kind == 'body-fifo': pooled.unlink(); os.mkfifo(pooled, 0o600)
        elif kind == 'missing-task': (path/'context/task.md').unlink()
        elif kind == 'missing-bundle': (path/'bundle').unlink()
        elif kind == 'extra-entry': (path/'unexpected').write_bytes(b'x')
        elif kind == 'manifest-malformed': (path/'manifest.json').write_text('{}\n')
        elif kind == 'manifest-oversized': (path/'manifest.json').write_bytes(b' '*(module.MAX_MANIFEST+1))
        elif kind == 'manifest-mode': (path/'manifest.json').chmod(0o644)
        elif kind == 'manifest-hardlink': os.link(path/'manifest.json', base/(kind+'-outside'))
        elif kind == 'fingerprint':
            doc = json.loads((path/'manifest.json').read_text()); doc['fingerprint'] = '0'*64
            (path/'manifest.json').write_text(json.dumps(doc)+'\n')
        elif kind == 'context-mode': (path/'context').chmod(0o755)
        elif kind == 'task-size': (path/'context/task.md').write_bytes(b'wrong size')
        elif kind == 'manifest-link':
            (path/'manifest.json').unlink(); (path/'manifest.json').symlink_to(template/'manifest.json')
        elif kind == 'directory-link':
            shutil.rmtree(path); path.symlink_to(template, target_is_directory=True)
        elif kind == 'directory-mode': path.chmod(0o755)
        equivalent(kind + ' falls back to older', d, low)

    for kind in ('body', 'context', 'bundle'):
        d = fixture('corrupt-'+kind); put(d, low, stamp='2001-01-01T00:00:00+00:00')
        path = put(d, high, archived=True)
        damaged = next((path/'pool').iterdir()) if kind == 'body' else path/('context/task.md' if kind == 'context' else 'bundle')
        damaged.write_bytes(b'z'*len(damaged.read_bytes()))
        shallow = module.last_good(str(d), 'wanted', False)
        deep = module.last_good(str(d), 'wanted', True)
        check(kind + ' same-size corruption shallow eligible deep falls back', shallow['id'] == high and deep['id'] == low
              and shallow == reference(d, 'wanted', False) and deep == reference(d, 'wanted', True))

    for kind in ('valid', 'malformed', 'foreign', 'unknown'):
        d = fixture('duplicate-'+kind)
        key = 'unknown-entry' if kind == 'unknown' else high
        if kind == 'unknown':
            (d/key).write_bytes(b'x'); (d/'archive').mkdir(mode=0o700); (d/'archive'/key).write_bytes(b'y')
        else:
            put(d, key, 'foreign' if kind == 'foreign' else 'wanted')
            path = put(d, key, 'foreign' if kind == 'foreign' else 'wanted', archived=True)
            if kind == 'malformed': (path/'manifest.json').write_text('{}\n')
        equivalent('global duplicate '+kind, d, 'refuse')

    d = fixture('unknown'); put(d, low)
    (d/'unknown').write_bytes(b'evidence'); (d/'.staging-preserved').mkdir()
    (d/'claims'/'unreadable.json').write_bytes(b'bad claim')
    equivalent('unknown entries staging and claims do not change lookup', d, low)
    d = fixture('archive-reservation'); put(d, low)
    (d/'archive').mkdir(mode=0o700); (d/'archive'/high).mkdir(mode=0o700)
    equivalent('incomplete archive reservation retained', d, low)
    (d/'archive').chmod(0o755)
    equivalent('unsafe archive root refused', d, 'refuse')

    d = fixture('archive-link'); put(d, low)
    (d/'archive').symlink_to(template, target_is_directory=True)
    equivalent('symlink archive root refused', d, 'refuse')
    d = fixture('archive-wrapper-link'); put(d, low)
    (d/'archive').mkdir(mode=0o700)
    (d/'archive'/high).symlink_to(template, target_is_directory=True)
    equivalent('symlink archive wrapper cannot qualify', d, low)
    d = fixture('bounded-names'); put(d, low)
    real_names = module.bounded_names
    def bounded(path, limit=4096):
        if str(path) == str(d):
            raise module.Refuse('excessive', 'too many entries to observe save storage safely')
        return real_names(path, limit)
    with patch.object(module, 'bounded_names', bounded):
        equivalent('bounded discovery refusal preserved', d, 'refuse')

    # Mutation controls use the actual installed helper, with no alternate Git object.
    d = fixture('unvalidated-negative'); put(d, low, stamp='2001-01-01T00:00:00+00:00')
    bad = put(d, high); next((bad/'pool').iterdir()).unlink()
    def require_validated():
        assert module.last_good(str(d), 'wanted', False)['id'] == low, 'unvalidated candidate returned'
    require_validated()
    real_load_save = module.load_save
    def trusting(path, key, deep):
        if key == high:
            return dict(manifest=json.loads((bad/'manifest.json').read_text()), stored_bytes=0)
        return real_load_save(path, key, deep)
    try:
        with patch.object(module, 'load_save', trusting): require_validated()
    except AssertionError as error:
        check('negative control catches unvalidated manifest winner', str(error) == 'unvalidated candidate returned')
    else:
        raise AssertionError('negative control escaped')

    # A disagreement at full validation or the second discovery must discard hints.
    for kind in ('selected-worker', 'foreign-worker', 'duplicate-appears', 'candidate-disappears'):
        d = fixture('race-'+kind); put(d, low, stamp='2001-01-01T00:00:00+00:00')
        winner = put(d, high)
        foreign_key = 'f'*32; foreign = put(d, foreign_key, 'foreign')
        calls_to_load = [0]
        def changing_load(path, key, deep):
            calls_to_load[0] += 1
            if calls_to_load[0] == 1:
                if kind in ('selected-worker', 'foreign-worker'):
                    changed = winner if kind == 'selected-worker' else foreign
                    doc = json.loads((changed/'manifest.json').read_text())
                    doc['worker'] = 'foreign' if kind == 'selected-worker' else 'wanted'
                    (changed/'manifest.json').write_text(json.dumps(doc)+'\n')
                elif kind == 'duplicate-appears': put(d, foreign_key, 'foreign', archived=True)
                else: shutil.rmtree(winner)
            return real_load_save(path, key, deep)
        with patch.object(module, 'load_save', changing_load):
            raced = outcome(lambda: module.last_good(str(d), 'wanted', False))
        check('bounded race fallback '+kind, raced == outcome(lambda: reference(d, 'wanted', False)))

    # Real periodic skip keeps the prior attempt byte-identical. A catchable
    # stable-observation refusal records a fresh refused attempt and last good.
    # These do not replace existing suites' real publication/archival fault tests.
    before_ids = set(p.name for p in store.iterdir())
    attempt_path = store/'attempts/mock-source.json'
    before_attempt = attempt_path.read_bytes()
    with patch.dict(os.environ, env), patch.object(module, 'publish', side_effect=AssertionError('periodic published')):
        check('periodic unchanged state skips publication', module.create_locked(str(root), 'mock-source', 'T', reason='periodic') == 0)
    check('periodic preserves store IDs and complete attempt bytes', before_ids == set(p.name for p in store.iterdir())
          and before_attempt == attempt_path.read_bytes())
    real_capture = module.capture
    observations = [0]
    def unstable(*args, **kwargs):
        result, task_bytes = real_capture(*args, **kwargs)
        observations[0] += 1
        if observations[0] == 2:
            result = dict(result, fingerprint='0'*64)
        return result, task_bytes
    with patch.dict(os.environ, env), patch.object(module, 'capture', unstable):
        check('stable-byte refusal remains nonzero', module.cmd_create(str(root), 'mock-source', 'T') != 0)
    attempt = json.loads(attempt_path.read_text())
    check('refusal bookkeeping uses metadata-valid latest and both observations', observations[0] == 2
          and attempt['status'] == 'refused' and attempt['reason'] == 'unstable'
          and attempt['save_id'] is None and attempt['last_good_id'] == sid)
    check('provider never invoked', not calls.exists())
print('%d save-latest-lookup checks passed' % passed)
