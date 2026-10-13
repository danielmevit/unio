#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline installed bundle tests for the bounded, unsupported first slice.

No managed backend exists here: app-server interleaving/slot/cleanup acceptance
is deliberately not represented as passed by these tests.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class InstalledCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='unio-effort-')
        cls.root = Path(cls.temp.name)
        cls.bin = cls.root / 'bin'
        cls.conf = cls.root / 'conf'
        cls.completion = cls.root / 'completion'
        cls.project = cls.root / 'project with spaces'
        (cls.project / 'coord').mkdir(parents=True)
        (cls.project / 'wt' / 'codex-1').mkdir(parents=True)
        (cls.project / 'wt' / 'claude-1').mkdir()
        cls.fake = cls.root / 'fake'
        cls.fake.mkdir()
        cls.sentinel = cls.root / 'provider-called'
        for name in ('codex', 'claude', 'opencode', 'vibe'):
            binary = cls.fake / name
            binary.write_text('#!/bin/sh\n: > "$EFFORT_PROVIDER_SENTINEL"\nexit 99\n')
            binary.chmod(0o755)
        cls.env = dict(os.environ, UNIO_BIN_DIR=str(cls.bin),
            UNIO_CONF_DIR=str(cls.conf), UNIO_COMPLETION_DIR=str(cls.completion),
            EFFORT_PROVIDER_SENTINEL=str(cls.sentinel),
            PATH=str(cls.fake) + os.pathsep + os.environ['PATH'])
        # Use only a standalone copy, not adjacent source helper paths.
        cls.installer = cls.root / 'standalone-install.sh'
        cls.installer.write_bytes((SOURCE / 'unio-install.sh').read_bytes())
        result = subprocess.run(['bash', str(cls.installer)], env=cls.env,
                                capture_output=True, text=True, timeout=60)
        if result.returncode:
            cls.temp.cleanup()
            raise RuntimeError(result.stderr)
        cls.helper = cls.conf / 'lib' / 'codex-worker.py'

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def call(self, *args, cwd=None):
        result = subprocess.run([str(self.bin / 'unio'), 'worker-effort', *args],
            cwd=cwd or self.project, env=self.env,
            capture_output=True, text=True, timeout=10)
        self.assertFalse(self.sentinel.exists(), 'a provider was invoked')
        return result


class BundleTests(InstalledCase):
    def test_payload_and_outside_help(self):
        self.assertEqual(self.helper.read_bytes(), (SOURCE / 'tools/codex-worker.py').read_bytes())
        self.assertEqual((self.conf / 'lib/WORKER-EFFORT.md').read_bytes(),
                         (SOURCE / 'docs/WORKER-EFFORT.md').read_bytes())
        result = self.call('--help', cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('unsupported', result.stdout)

    def test_completion_and_help(self):
        self.assertIn('worker-effort', (self.completion / 'unio').read_text())
        result = subprocess.run([str(self.bin / 'unio'), 'help'], env=self.env,
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0)
        self.assertIn('worker-effort WORKER', result.stdout)

    def test_preserves_owned_config_on_reinstall(self):
        profile = self.conf / 'agents.conf'
        profile.write_text('codex=owner-custom-command\n')
        result = subprocess.run(['bash', str(self.installer)], env=self.env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(profile.read_text(), 'codex=owner-custom-command\n')
        self.assertFalse(self.sentinel.exists())

    def test_refuses_replaced_helper_at_install(self):
        # The generated helper cannot overwrite a foreign symlink destination.
        target = self.root / 'foreign'
        target.write_text('preserve')
        original = self.helper.read_bytes()
        self.helper.unlink()
        self.helper.symlink_to(target)
        try:
            result = subprocess.run(['bash', str(self.installer)], env=self.env,
                                    capture_output=True, text=True, timeout=60)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), 'preserve')
        finally:
            self.helper.unlink()
            self.helper.write_bytes(original)


if __name__ == '__main__':
    unittest.main()
