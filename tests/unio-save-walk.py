#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Exercise real Git ignore semantics, races and bounded directory handles."""
import json
import os
from pathlib import Path
import resource
import shutil
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]


def helper():
    text = (SOURCE / 'unio-install.sh').read_text()
    body = text.split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY\n', 1)[0]
    body = body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0]
    module = types.ModuleType('save_walk')
    exec(compile(body, 'installed-save-helper', 'exec'), module.__dict__)
    return module


def wide_child(path):
    soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    resource.setrlimit(resource.RLIMIT_NOFILE, (min(64, soft), hard))
    module = helper()
    files = module.walk_worktree(path, module.Budget(120), set())
    print(json.dumps({'files': len(files)}))


class SaveWalk(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='save-walk-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'space and λ project'
        self.repo.mkdir()
        self.module = helper()
        self.git('init', '-q')
        self.write('.gitignore', 'cache/\n*.log\nignored-parent/\n.env\n')
        self.write('plain.txt', b'plain\0bytes\n')
        self.write('keep/tracked.log', 'retained leaf\n')
        self.write('ignored-parent/retained.txt', 'retained parent\n')
        self.git('add', '-f', '.gitignore', 'plain.txt', 'keep/tracked.log',
                 'ignored-parent/retained.txt')
        self.git('-c', 'user.name=mock', '-c', 'user.email=mock@example.invalid',
                 'commit', '-qm', 'seed')
        self.git('rm', '--cached', '-q', 'keep/tracked.log', 'ignored-parent/retained.txt')
        self.tracked = {'.gitignore', 'plain.txt', 'keep/tracked.log',
                        'ignored-parent/retained.txt'}

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args],
                                       stderr=subprocess.PIPE)

    def write(self, name, body):
        p = self.repo / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(body if isinstance(body, bytes) else body.encode())
        return p

    def walk(self):
        return self.module.walk_worktree(str(self.repo), self.module.Budget(120),
                                         self.tracked)

    def refused(self, code):
        with self.assertRaises(self.module.Refuse) as result:
            self.walk()
        self.assertEqual(result.exception.code, code)

    def test_ignore_before_body_and_retained_head_paths(self):
        self.write('cache/.env', 'never opened\n')
        self.write('keep/debug.log', 'never read\n')
        os.mkfifo(self.repo / 'cache' / 'pipe')
        read = self.module.read_at
        seen = []

        def guarded(dfd, name, limit, budget=None, what=None):
            self.assertFalse(what.startswith('cache/') or what == 'keep/debug.log')
            seen.append(what)
            return read(dfd, name, limit, budget, what)

        with patch.object(self.module, 'read_at', guarded):
            files = self.walk()
        self.assertEqual(set(files), self.tracked)
        self.assertEqual(set(seen), self.tracked)
        self.assertEqual(files['plain.txt'][1], b'plain\0bytes\n')
        self.assertEqual(files['keep/tracked.log'][1], b'retained leaf\n')
        self.assertEqual(files['ignored-parent/retained.txt'][1], b'retained parent\n')

    def test_wide_tree_batches_queries_and_fits_low_descriptor_limit(self):
        expected = set(self.tracked)
        for n in range(96):
            name = 'part-%03d/item.txt' % n
            self.write(name, str(n))
            expected.add(name)
        original = self.module.ignored_names
        calls = []

        def counted(wt, budget, rels):
            if rels:
                calls.append(len(rels))
            return original(wt, budget, rels)

        with patch.object(self.module, 'ignored_names', counted):
            files = self.walk()
        self.assertEqual(set(files), expected)
        self.assertLessEqual(len(calls), 6)  # 99 child folders must not mean 99 processes.
        for n in range(96):
            self.assertEqual(files['part-%03d/item.txt' % n][1], str(n).encode())
        child = subprocess.run([sys.executable, '-B', __file__, '--wide', str(self.repo)],
                               capture_output=True, text=True, timeout=120)
        self.assertEqual(child.returncode, 0, child.stderr)
        # No tracked override in the child, so its ignored tracked leaves are absent.
        self.assertEqual(json.loads(child.stdout)['files'], 98)

    def test_query_batches_respect_name_bound(self):
        shutil.rmtree(self.repo / 'keep')
        shutil.rmtree(self.repo / 'ignored-parent')
        for n in range(6):
            for k in range(3):
                self.write('part-%d/item-%d.log' % (n, k), 'ignored\n')
        original = self.module.ignored_names
        sizes = []

        def counted(wt, budget, rels):
            sizes.append(len(rels))
            return original(wt, budget, rels)

        with patch.object(self.module, 'MAX_ENTRIES', 10), \
                patch.object(self.module, 'ignored_names', counted):
            files = self.walk()
        self.assertEqual(set(files), {'.gitignore', 'plain.txt'})
        self.assertLessEqual(max(sizes), 10)

    def mutate_at_child_query(self, mutation):
        self.write('swap/old.txt', 'old\n')
        original = self.module.ignored_names
        changed = []

        def racing(wt, budget, rels):
            result = original(wt, budget, rels)
            if 'swap/old.txt' in rels and not changed:
                mutation()
                changed.append(True)
            return result

        with patch.object(self.module, 'ignored_names', racing):
            self.refused('unstable')
        self.assertTrue(changed)

    def test_replaced_directory_refuses_without_following_replacement(self):
        def mutation():
            (self.repo / 'swap').rename(self.root / 'original')
            self.write('swap/old.txt', 'replacement\n')
        self.mutate_at_child_query(mutation)

    def test_changed_directory_listing_refuses(self):
        self.mutate_at_child_query(lambda: self.write('swap/new.txt', 'new\n'))

    def test_ignored_secret_and_special_files_still_refuse(self):
        self.write('.env', 'secret\n')
        self.refused('secret_name')
        (self.repo / '.env').unlink()
        outside = self.root / 'outside'
        outside.mkdir()
        (self.repo / 'link').symlink_to(outside, target_is_directory=True)
        self.refused('unsupported_type')
        (self.repo / 'link').unlink()
        os.mkfifo(self.repo / 'pipe')
        self.refused('unsupported_type')
        (self.repo / 'pipe').unlink()
        self.write('nested/.git', 'gitdir: /do-not-follow\n')
        self.refused('unsupported_type')


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--wide':
        wide_child(sys.argv[2])
    else:
        unittest.main()
