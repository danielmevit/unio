#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Private-fixture tests for the read-only `unio cache` inventory.

Every workspace is a tiny disposable Git project. No provider, no network and
no real configuration; a poisoned PATH proves that no provider CLI is started.
"""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
from unittest.mock import patch
import re
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
HELPER = SOURCE / 'tools/worktree-cache.py'
spec = importlib.util.spec_from_file_location('worktree_cache', HELPER)
cache = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cache)
GIT_ENV = {key: value for key, value in os.environ.items()
           if not key.startswith(('GIT_', 'UNIO_'))}
GIT_ENV.update(GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.invalid',
               GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.invalid',
               GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')


def run_git(cwd, *args):
    subprocess.run(('git', '-C', str(cwd)) + args, check=True, env=GIT_ENV,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def snapshot(root):
    """Exact tree state; contents are hashed outside Git's and inside caches."""
    state = {}
    for directory, names, files in os.walk(root):
        for name in names + files:
            path = os.path.join(directory, name)
            info = os.lstat(path)
            digest = None
            if os.path.isfile(path) and not os.path.islink(path):
                digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            state[path] = (info.st_mode, info.st_size, info.st_mtime_ns, info.st_ino, digest)
    return state


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cache inventory ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(os.path.realpath(self.temp.name)) / 'work space'
        (self.root / 'coord/.locks').mkdir(parents=True)
        (self.root / 'coord/results').mkdir()
        (self.root / 'wt').mkdir()
        repo = self.root / 'repo'
        repo.mkdir()
        run_git(repo, 'init', '-q', '-b', 'main')
        for name in ('App/App.csproj', 'Lib/Lib.fsproj', '_bench/B.csproj',
                     'App/Program.cs', 'Deep/Nested/N.csproj', 'NotDotNet/readme.txt'):
            target = repo / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('x\n')
        run_git(repo, 'add', '-A')
        run_git(repo, 'commit', '-qm', 'base')
        self.repo = repo

    def worker(self, name, result='succeeded', lock=True, marker=True, cache_bytes=100):
        path = self.root / 'wt' / name
        run_git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/' + name, str(path))
        if marker:
            (path / '.unio-worker').write_text(name + '\n')
        if lock:
            (self.root / 'coord/.locks' / (name + '.lock')).touch()
        if result:
            self.result(name, result)
        if cache_bytes is not None:
            (path / 'App/bin/Debug').mkdir(parents=True)
            (path / 'App/bin/Debug/a.dll').write_bytes(b'd' * cache_bytes)
        return path

    def result(self, name, state):
        directory = self.root / 'coord/results' / name
        directory.mkdir(exist_ok=True)
        (directory / 'T1.json').write_text(json.dumps(self.receipt(name, 'T1', state)))

    @staticmethod
    def receipt(worker, task='T1', state='succeeded'):
        code = 0 if state == 'succeeded' else 1 if state == 'failed' else None
        return dict(schema_version=1, worker=worker, task=task,
                    process=dict(state=state, exit_code=code))

    def inventory(self, limits=None, hook=cache.noop_hook, clock=None):
        kwargs = dict(limits=limits, hook=hook)
        if clock:
            kwargs['clock'] = clock
        return cache.inventory(str(self.root), **kwargs)

    def reasons(self, result, path):
        return [item['reason'] for item in result['excluded'] if item['path'] == path]

    def paths(self, result):
        return [item['path'] for item in result['candidates']]


class CacheCase(Fixture):
    def test_cache_entry_case_and_tracked_aliases(self):
        path = self.worker('idle', cache_bytes=None)
        # No case-only test is skipped: rename through a distinct intermediate
        # name so these index aliases exercise case-sensitive CI and drvfs.
        for kind in ('bin', 'obj'):
            upper = path / 'App' / kind.title()
            upper.mkdir()
            (upper / 'ThirdParty.dll').write_bytes(b'source')
            run_git(path, 'add', '--', 'App/' + kind.title())
        result = self.inventory()
        for kind in ('bin', 'obj'):
            self.assertNotIn('wt/idle/App/' + kind, self.paths(result))
            self.assertEqual(self.reasons(result, 'wt/idle/App/' + kind), ['case_mismatch'])
            upper = path / 'App' / kind.title()
            temporary = path / 'App' / ('temporary-' + kind)
            upper.rename(temporary)
            temporary.rename(path / 'App' / kind)
        # Exact lowercase entries now exist, but their mixed-case index aliases
        # must still refuse both candidates, independent of core.ignorecase.
        for ignorecase in ('false', 'true'):
            run_git(path, 'config', 'core.ignorecase', ignorecase)
            result = self.inventory()
            for kind in ('bin', 'obj'):
                self.assertEqual(self.reasons(result, 'wt/idle/App/' + kind), ['tracked_files'])
        (path / 'Lib/bin').mkdir()
        (path / 'Lib/bin/generated.dll').write_bytes(b'generated')
        self.assertEqual(self.paths(self.inventory()), ['wt/idle/Lib/bin'])

    def test_literal_magic_project_with_tracked_case_alias(self):
        path = self.worker('idle', cache_bytes=None)
        project = path / 'A[1]'
        project.mkdir()
        (project / 'App.csproj').write_text('project')
        (project / 'Bin').mkdir()
        (project / 'Bin/source.dll').write_text('source')
        run_git(path, 'add', '--', ':(literal)A[1]')
        (project / 'Bin').rename(project / 'temporary')
        (project / 'temporary').rename(project / 'bin')
        result = self.inventory()
        self.assertEqual(self.reasons(result, 'wt/idle/A[1]/bin'), ['tracked_files'])
        run_git(path, 'rm', '--cached', '-r', '--', ':(literal)A[1]/Bin')
        self.assertIn('wt/idle/A[1]/bin', self.paths(self.inventory()))

    def test_malformed_registration_paths_keep_healthy_worker_and_cli_json(self):
        self.worker('good')
        bad = self.worker('bad', cache_bytes=None)
        gitfile = bad / '.git'
        admin = Path(os.fsdecode(gitfile.read_bytes()[8:].strip()))
        targets = [(gitfile, b'gitdir: /nonexistent\0x\n'),
                   (admin / 'gitdir', os.fsencode(str(bad / '.git')) + b'\0x\n'),
                   (admin / 'gitdir', os.fsencode(str(bad)) + b'\0x/.git\n'),
                   (admin / 'commondir', b'../..\0x\n'),
                   (admin / 'HEAD', b'ref: refs/heads/agent/bad\0x\n')]
        for target, malformed in targets:
            with self.subTest(metadata=target.name, malformed=malformed):
                original = target.read_bytes()
                try:
                    target.write_bytes(malformed)
                    result = self.inventory()
                    self.assertEqual(self.paths(result), ['wt/good/App/bin'])
                    self.assertEqual(self.reasons(result, 'wt/bad'), ['unregistered_worktree'])
                    cli = subprocess.run([os.sys.executable, '-I', '-S', '-B', str(HELPER),
                                          '--project', str(self.root), '--json'],
                                         capture_output=True, text=True)
                    self.assertEqual(cli.returncode, 0, cli.stderr)
                    self.assertEqual(cli.stderr, '')
                    self.assertEqual(self.paths(json.loads(cli.stdout)), ['wt/good/App/bin'])
                finally:
                    target.write_bytes(original)

    def test_native_result_shapes_and_identity(self):
        self.worker('idle')
        target = self.root / 'coord/results/idle/T1.json'
        malformed = [None, [], {'process': {'state': 'succeeded'}}]
        for key, value in [('schema_version', True), ('schema_version', 2),
                           ('worker', 'other'), ('task', 'T2'), ('worker', [])]:
            doc = self.receipt('idle')
            doc[key] = value
            malformed.append(doc)
        for state, code in [([], 0), ({}, 0), (None, 0), ('succeeded', True),
                            ('succeeded', None), ('succeeded', 1), ('failed', 0),
                            ('failed', -1), ('failed', '1'), ('failed', None),
                            ('not_run', 0), ('running', 0)]:
            doc = self.receipt('idle')
            doc['process'] = dict(state=state, exit_code=code)
            malformed.append(doc)
        for process in [[], None, {}, {'state': 'succeeded'}]:
            doc = self.receipt('idle')
            doc['process'] = process
            malformed.append(doc)
        for doc in malformed:
            with self.subTest(document=doc):
                target.write_text(json.dumps(doc))
                self.assertEqual(cache.activity(str(self.root), 'idle')[0],
                                 'activity_unknown_results')
        for state in ('succeeded', 'failed', 'not_run'):
            with self.subTest(state=state):
                self.result('idle', state)
                self.assertIsNone(cache.activity(str(self.root), 'idle')[0])
        self.result('idle', 'running')
        self.assertEqual(cache.activity(str(self.root), 'idle')[0], 'running_orphan_uncertain')

    def test_strict_metadata_in_results_and_slots(self):
        self.worker('idle')
        target = self.root / 'coord/results/idle/T1.json'
        slot_dir = self.root / 'coord/.locks/work-policy-slots/group'
        slot_dir.mkdir(parents=True)
        slot = slot_dir / 'slot.json'
        malformed = ['[' * 15000 + '0' + ']' * 15000,
                     '[' * 66 + '0' + ']' * 66,
                     '{"worker":"idle","worker":"other"}',
                     '{"x":NaN}', '{"x":Infinity}', '{"x":-Infinity}', '{"x":1e999}']
        for raw in malformed:
            with self.subTest(raw=raw[:70]):
                target.write_text(raw)
                self.assertTrue(cache.activity(str(self.root), 'idle')[0].startswith(
                    'activity_unknown_metadata_'))
                slot.write_text(raw)
                self.assertFalse(cache.worker_slots(str(self.root))[1])
                slot.unlink()
        self.result('idle', 'succeeded')
        base = dict(schema_version=1, group='group', worker='idle', task='T1',
                    agent='codex', kind='run')
        for key, value in [('schema_version', True), ('group', 'wrong'), ('task', []),
                           ('worker', []), ('agent', None), ('kind', 'unknown')]:
            doc = dict(base)
            doc[key] = value
            slot.write_text(json.dumps(doc))
            self.assertFalse(cache.worker_slots(str(self.root))[1])
            self.assertEqual(cache.activity(str(self.root), 'idle')[0], 'activity_unknown_slots')
        slot.write_text(json.dumps(base))
        self.assertEqual(cache.worker_slots(str(self.root)), ({'idle'}, True))

    def test_metadata_enumeration_bounds(self):
        self.worker('idle')
        results = self.root / 'coord/results/idle'
        (results / 'unrelated').touch()
        with patch.object(cache, 'MAX_RESULTS', 1), patch.object(cache.os, 'listdir',
                                                              side_effect=AssertionError('unbounded')):
            self.assertEqual(cache.activity(str(self.root), 'idle')[0],
                             'activity_unknown_result_limit')
        base = self.root / 'coord/.locks/work-policy-slots'
        group = base / 'group'
        group.mkdir(parents=True)
        for name in ('a', 'b'):
            (group / name).touch()
        with patch.object(cache, 'MAX_SLOT_FILES', 1):
            self.assertFalse(cache.worker_slots(str(self.root))[1])
        (base / 'other').mkdir()
        with patch.object(cache, 'MAX_SLOT_GROUPS', 1):
            self.assertFalse(cache.worker_slots(str(self.root))[1])
        # Directory opens themselves must refuse symlinks.
        (base / 'other').rmdir()
        (base / 'other').symlink_to(group)
        self.assertFalse(cache.worker_slots(str(self.root))[1])

    def test_idle_generated_directory_schema(self):
        self.worker('idle', cache_bytes=123)
        (self.root / 'wt/idle/App/obj').mkdir()
        result = self.inventory()
        self.assertEqual(result['schema_version'], 1)
        self.assertIs(result['dry_run'], True)
        self.assertIs(result['partial'], False)
        self.assertTrue(result['observed_at'])
        self.assertEqual(self.paths(result), ['wt/idle/App/bin', 'wt/idle/App/obj'])
        item = result['candidates'][0]
        self.assertEqual((item['worker'], item['kind'], item['logical_bytes'], item['status']),
                         ('idle', 'bin', 123, 'inactive_observed'))
        self.assertIn('allocated_bytes', item)
        self.assertEqual(result['totals']['logical_bytes'], 123)
        self.assertIn('not deletion permission', result['observation'])
        json.dumps(result)

    def test_only_recognized_top_level_projects(self):
        path = self.worker('idle')
        for name in ('NotDotNet/bin', 'Deep/Nested/bin', 'Deep/bin', 'bin', 'App/sub/bin'):
            (path / name).mkdir(parents=True, exist_ok=True)
        self.assertEqual(self.paths(self.inventory()), ['wt/idle/App/bin'])

    def test_repo_root_project(self):
        (self.repo / 'Root.vbproj').write_text('x\n')
        run_git(self.repo, 'add', '-A')
        run_git(self.repo, 'commit', '-qm', 'root')
        path = self.worker('idle')
        (path / 'bin').mkdir()
        (path / 'bin/r.dll').write_bytes(b'r')
        self.assertEqual(self.paths(self.inventory()), ['wt/idle/App/bin', 'wt/idle/bin'])

    def test_active_lock_excluded_probe_does_not_steal(self):
        self.worker('busy')
        fd = os.open(self.root / 'coord/.locks/busy.lock', os.O_RDWR)
        self.addCleanup(os.close, fd)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = self.inventory()
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/busy'), ['active_lock'])

    def test_stale_running_result_is_not_inactive(self):
        self.worker('stale', result='running')
        result = self.inventory()
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/stale'), ['running_orphan_uncertain'])

    def test_missing_or_unknown_metadata_is_conservative(self):
        self.worker('nolock', lock=False)
        self.worker('noresult', result=None)
        self.worker('weird', result='brand_new_state')
        self.worker('corrupt')
        (self.root / 'coord/results/corrupt/T1.json').write_text('{not json')
        self.worker('slotted')
        slots = self.root / 'coord/.locks/work-policy-slots/claude'
        slots.mkdir(parents=True)
        (slots / 'a.json').write_text(json.dumps(dict(schema_version=1, group='claude', worker='slotted',
                                                        task='T1', agent='claude', kind='run')))
        result = self.inventory()
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/nolock'), ['activity_unknown_no_lock'])
        self.assertEqual(self.reasons(result, 'wt/noresult'), ['activity_unknown_no_result'])
        self.assertEqual(self.reasons(result, 'wt/weird'), ['activity_unknown_results'])
        self.assertEqual(self.reasons(result, 'wt/corrupt'), ['activity_unknown_results'])
        self.assertEqual(self.reasons(result, 'wt/slotted'), ['work_policy_slot'])

    def test_unreadable_slot_blocks_every_worker(self):
        self.worker('idle')
        slots = self.root / 'coord/.locks/work-policy-slots/claude'
        slots.mkdir(parents=True)
        (slots / 'a.json').write_text('{broken')
        self.assertEqual(self.reasons(self.inventory(), 'wt/idle'), ['activity_unknown_slots'])

    def test_unregistered_and_foreign_worktrees(self):
        real = self.worker('real')
        copied = self.root / 'wt/copied'
        shutil.copytree(real, copied)
        (copied / '.unio-worker').write_text('copied\n')
        (self.root / 'coord/.locks/copied.lock').touch()
        self.result('copied', 'succeeded')
        foreign = self.root / 'wt/foreign'
        foreign.mkdir()
        run_git(foreign, 'init', '-q')
        (foreign / '.unio-worker').write_text('foreign\n')
        (self.root / 'wt/marked').mkdir()
        (self.root / 'wt/link').symlink_to(real)
        result = self.inventory()
        self.assertEqual(self.paths(result), ['wt/real/App/bin'])
        self.assertEqual(self.reasons(result, 'wt/copied'), ['unregistered_worktree'])
        self.assertEqual(self.reasons(result, 'wt/foreign'), ['not_a_linked_worktree'])
        self.assertEqual(self.reasons(result, 'wt/marked'), ['not_a_worktree'])
        self.assertEqual(self.reasons(result, 'wt/link'), ['not_a_worktree_directory'])

    def test_foreign_common_git_directory_and_mismatched_marker(self):
        other = self.root.parent / 'other repo'
        other.mkdir()
        run_git(other, 'init', '-q', '-b', 'main')
        run_git(other, 'commit', '-q', '--allow-empty', '-m', 'x')
        external = self.root / 'wt/ext'
        run_git(other, 'worktree', 'add', '-q', '-b', 'agent/ext', str(external))
        (external / '.unio-worker').write_text('ext\n')
        self.worker('wrong', marker=False)
        (self.root / 'wt/wrong/.unio-worker').write_text('someone-else\n')
        self.worker('absent', marker=False)
        result = self.inventory()
        self.assertEqual(self.reasons(result, 'wt/ext'), ['unregistered_worktree'])
        self.assertEqual(self.reasons(result, 'wt/wrong'), ['worker_marker_mismatch'])
        self.assertEqual(self.reasons(result, 'wt/absent'), ['worker_marker_missing_or_unsafe'])

    def test_symlink_never_followed_or_counted(self):
        outside = self.root.parent / 'outside'
        outside.mkdir()
        (outside / 'big').write_bytes(b'z' * 5000)
        path = self.worker('inner')
        (path / 'App/bin/link').symlink_to(outside)
        whole = self.worker('whole', cache_bytes=None)
        (whole / 'App/bin').symlink_to(outside)
        before = snapshot(outside)
        result = self.inventory()
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/inner/App/bin'), ['symlink'])
        self.assertEqual(self.reasons(result, 'wt/whole/App/bin'), ['symlink'])
        self.assertEqual(snapshot(outside), before)

    def test_symlinked_project_directory_refused(self):
        outside = self.root.parent / 'outside'
        (outside / 'bin').mkdir(parents=True)
        path = self.worker('w', cache_bytes=None)
        shutil.rmtree(path / 'Lib')
        (path / 'Lib').symlink_to(outside)
        self.assertEqual(self.reasons(self.inventory(), 'wt/w/Lib/bin'), ['symlink'])

    def test_tracked_source_in_cache_refused(self):
        path = self.worker('tracked')
        (path / 'App/bin/keep.cs').write_text('source\n')
        run_git(path, 'add', '-f', 'App/bin/keep.cs')
        run_git(path, 'commit', '-qm', 'tracked in bin')
        result = self.inventory()
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/tracked/App/bin'), ['tracked_files'])

    def test_benchmark_and_private_preservation(self):
        path = self.worker('bench')
        (path / '_bench/bin').mkdir()
        (path / '_bench/bin/result.json').write_text('evidence')
        (path / 'Lib/bin/BenchmarkDotNet.Artifacts').mkdir(parents=True)
        (path / 'Lib/bin/BenchmarkDotNet.Artifacts/r.csv').write_text('e')
        (path / 'App/obj/credentials').mkdir(parents=True)
        (path / 'App/obj/credentials/token').write_text('secret')
        before = snapshot(self.root)
        result = self.inventory()
        self.assertEqual(snapshot(self.root), before)
        self.assertEqual(self.paths(result), ['wt/bench/App/bin'])
        self.assertEqual(self.reasons(result, 'wt/bench/_bench/bin'), ['protected_project_directory'])
        self.assertEqual(self.reasons(result, 'wt/bench/Lib/bin'), ['protected_entry'])
        self.assertEqual(self.reasons(result, 'wt/bench/App/obj'), ['protected_entry'])

    def test_vhdx_named_entry_refused(self):
        path = self.worker('v')
        (path / 'App/bin/ext4.VHDX').write_bytes(b'')
        self.assertEqual(self.reasons(self.inventory(), 'wt/v/App/bin'), ['protected_entry'])

    def test_hardlink_refused(self):
        path = self.worker('hard')
        os.link(path / 'App/bin/Debug/a.dll', self.root.parent / 'twin')
        result = self.inventory()
        self.assertEqual(self.reasons(result, 'wt/hard/App/bin'), ['hardlink'])
        self.assertEqual(self.paths(result), [])

    def test_unsupported_file_type_refused(self):
        path = self.worker('fifo')
        try:
            os.mkfifo(path / 'App/bin/pipe')
        except OSError as error:
            self.skipTest('fifo unsupported on this filesystem: %s' % error)
        self.assertEqual(self.reasons(self.inventory(), 'wt/fifo/App/bin'), ['unsupported_file_type'])

    def test_mount_escape_refused(self):
        self.worker('mnt')
        path = str(self.root / 'wt/mnt/App/bin/Debug')
        original = cache.mount_points
        self.addCleanup(setattr, cache, 'mount_points', original)
        cache.mount_points = lambda: {path}
        self.assertEqual(self.reasons(self.inventory(), 'wt/mnt/App/bin'), ['mount_escape'])
        cache.mount_points = lambda: None
        self.assertEqual(self.reasons(self.inventory(), 'wt/mnt/App/bin'), ['mount_table_unknown'])

    def test_entry_limit_stays_partial_never_zero(self):
        path = self.worker('many')
        for index in range(20):
            (path / 'App/bin' / ('f%d' % index)).write_bytes(b'x')
        self.worker('zlater')
        result = self.inventory(cache.Limits(entries=5))
        self.assertIs(result['partial'], True)
        self.assertIn('entry_limit', result['partial_reasons'])
        item = result['candidates'][0]
        self.assertEqual(item['status'], 'partial')
        self.assertIsNone(item['logical_bytes'])
        self.assertIsNone(item['allocated_bytes'])
        self.assertFalse(result['totals']['logical_bytes_complete'])
        self.assertEqual(self.reasons(result, 'wt/zlater'), ['not_scanned_bound_reached'])
        self.assertIn('lower bound', cache.human(result))
        self.assertIn('PARTIAL', cache.human(result))

    def test_worktree_and_candidate_limits(self):
        for name in ('a', 'b', 'c'):
            self.worker(name)
        result = self.inventory(cache.Limits(worktrees=2))
        self.assertTrue(result['partial'])
        self.assertIn('worktree_limit', result['partial_reasons'])
        self.assertEqual(len(result['candidates']), 2)
        result = self.inventory(cache.Limits(candidates=1))
        self.assertIn('candidate_limit', result['partial_reasons'])
        self.assertEqual(len(result['candidates']), 1)
        self.assertEqual(self.reasons(result, 'wt/b/App/bin'), ['candidate_limit'])

    def test_time_limit_partial(self):
        self.worker('a')
        now = [0.0]

        def clock():
            now[0] += 1.0
            return now[0]
        result = self.inventory(cache.Limits(seconds=3), clock=clock)
        self.assertIs(result['partial'], True)
        self.assertIn('time_limit', result['partial_reasons'])
        self.assertEqual(result['candidates'], [])

    def test_race_entry_changes_between_observations(self):
        path = self.worker('race')

        def hook(event, _detail):
            if event == 'between_passes':
                (path / 'App/bin/new.dll').write_bytes(b'n')
        result = self.inventory(hook=hook)
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/race/App/bin'), ['changing_entries'])

    def test_race_activity_before_presenting(self):
        self.worker('runs')
        self.worker('locks')
        held = []

        def hook(event, detail):
            if event == 'before_present' and not held:
                held.append(os.open(self.root / 'coord/.locks/locks.lock', os.O_RDWR))
                fcntl.flock(held[0], fcntl.LOCK_EX)
                self.result('runs', 'running')
        result = self.inventory(hook=hook)
        os.close(held[0])
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/locks/App/bin'), ['active_lock'])
        self.assertEqual(self.reasons(result, 'wt/runs/App/bin'), ['running_orphan_uncertain'])

    def test_race_result_replaced_after_scan(self):
        self.worker('later')

        def hook(event, _detail):
            if event == 'before_present':
                (self.root / 'coord/results/later/T2.json').write_text(
                    json.dumps(self.receipt('later', 'T2')))
        result = self.inventory(hook=hook)
        self.assertEqual(self.reasons(result, 'wt/later/App/bin'), ['activity_changed'])

    def test_race_cache_swapped_for_symlink(self):
        path = self.worker('swap')
        target = self.root.parent / 'elsewhere'
        target.mkdir()

        def hook(event, _detail):
            if event == 'before_present':
                shutil.rmtree(path / 'App/bin')
                (path / 'App/bin').symlink_to(target)
        result = self.inventory(hook=hook)
        self.assertEqual(self.paths(result), [])
        self.assertEqual(self.reasons(result, 'wt/swap/App/bin'), ['changing_entries'])

    def test_helper_has_no_mutating_calls(self):
        text = HELPER.read_text()
        for word in ('rmtree', 'os.unlink', 'os.remove', 'os.rmdir', 'os.rename', 'os.replace',
                     'os.mkdir', 'os.makedirs', 'O_CREAT', 'O_WRONLY', 'O_RDWR', 'os.truncate'):
            self.assertNotIn(word, text)
        self.assertEqual(text.count('subprocess.Popen'), 1)
        self.assertIn("subprocess.Popen(('git', '-C', cwd)", text)
        for verb in (b'worktree', b'gc', b'clean', b'checkout', b'reset'):
            self.assertNotIn("'%s'" % verb.decode(), text.replace("'worktrees'", ''))


class CliCase(Fixture):
    @classmethod
    def setUpClass(cls):
        cls.install_temp = tempfile.TemporaryDirectory(prefix='cache install ')
        base = Path(cls.install_temp.name)
        cls.bin = base / 'bin'
        cls.conf = base / 'conf'
        cls.completion = base / 'completion'
        cls.home = base / 'home'
        cls.home.mkdir()
        env = dict(GIT_ENV, HOME=str(cls.home), UNIO_BIN_DIR=str(cls.bin), UNIO_CONF_DIR=str(cls.conf),
                   UNIO_COMPLETION_DIR=str(cls.completion))
        subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], check=True, env=env, cwd=base,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        cls.poison = base / 'poison'
        cls.poison.mkdir()
        cls.sentinel = base / 'provider-called'
        for name in ('claude', 'codex', 'opencode', 'gemini', 'copilot', 'vibe', 'curl', 'wget'):
            tool = cls.poison / name
            tool.write_text('#!/bin/sh\necho called >> "%s"\nexit 9\n' % cls.sentinel)
            tool.chmod(0o755)

    @classmethod
    def tearDownClass(cls):
        cls.install_temp.cleanup()

    def cli(self, *args, cwd=None):
        env = dict(GIT_ENV, HOME=str(self.home), UNIO_CONF_DIR=str(self.conf),
                   PATH=str(self.poison) + os.pathsep + GIT_ENV['PATH'])
        return subprocess.run([str(self.bin / 'unio'), 'cache', *args], env=env, text=True,
                              cwd=cwd or self.root, capture_output=True, timeout=120)

    def test_installed_helper_is_byte_identical(self):
        self.assertEqual((self.conf / 'lib/worktree-cache.py').read_bytes(), HELPER.read_bytes())
        check = subprocess.run(['python3', '-B', str(SOURCE / 'tools/embed-worktree-cache.py'), '--check'],
                               capture_output=True, text=True)
        self.assertEqual(check.returncode, 0, check.stderr)
        completion = (self.completion / 'unio').read_text()
        self.assertRegex(completion, r'cache\) COMPREPLY.*--dry-run --json --project')
        self.assertIn(' cache ', completion)

    def test_help_mentions_command_and_never_deletes(self):
        env = dict(GIT_ENV, HOME=str(self.home), UNIO_CONF_DIR=str(self.conf))
        text = subprocess.run([str(self.bin / 'unio'), 'help'], env=env, text=True, capture_output=True).stdout
        self.assertIn('unio cache [--dry-run] [--json] [--project PATH]', text)
        self.assertEqual(self.cli('--help').returncode, 0)

    def test_stop_no_provider_no_writes_exit_zero(self):
        self.worker('idle', cache_bytes=7)
        (self.root / 'coord/STOP').touch()
        before = snapshot(self.root)
        done = self.cli('--json')
        self.assertEqual(done.returncode, 0, done.stderr)
        result = json.loads(done.stdout)
        self.assertIs(result['stop_active'], True)
        self.assertEqual(self.paths(result), ['wt/idle/App/bin'])
        self.assertEqual(snapshot(self.root), before)
        self.assertFalse(self.sentinel.exists())

    def test_human_output_exact_path_and_no_deletion_command(self):
        self.worker('idle')
        done = self.cli('--dry-run', cwd=self.root / 'wt/idle')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('wt/idle/App/bin', done.stdout)
        self.assertIn('STOP: clear', done.stdout)
        self.assertNotRegex(done.stdout, re.compile(r'\b(rm|del|rmdir|unio cache --apply)\b'))

    def test_invalid_input_and_unsafe_workspace_exit_two(self):
        self.assertEqual(self.cli('--apply').returncode, 2)
        self.assertEqual(self.cli('--dry').returncode, 2)
        self.assertEqual(self.cli('--project', str(self.root.parent)).returncode, 2)
        self.assertEqual(self.cli(cwd='/').returncode, 2)
        # No main clone with linked worktrees: unsafe, not an empty success.
        self.assertEqual(self.cli().returncode, 2)
        second = self.root / 'second'
        second.mkdir()
        run_git(second, 'init', '-q')
        (second / '.git/worktrees').mkdir()
        self.worker('idle')
        self.assertEqual(self.cli().returncode, 2)

    def test_symlinked_coordination_refused(self):
        self.worker('idle')
        results = self.root / 'coord/results'
        moved = self.root.parent / 'moved results'
        results.rename(moved)
        results.symlink_to(moved)
        self.assertEqual(self.cli('--json').returncode, 2)


if __name__ == '__main__':
    unittest.main(verbosity=1)
