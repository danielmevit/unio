#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline install tests for the packaged explicit `unio dispatch` helper.

A copied standalone installer runs into a disposable fixture with spaces in
every path; UNIO_BIN_DIR, UNIO_CONF_DIR and UNIO_COMPLETION_DIR point only at
that fixture. No network, no provider calls and no real configuration.
"""

import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SOURCE_ROOT = Path(__file__).resolve().parents[1]
INSTALLER = SOURCE_ROOT / 'unio-install.sh'
DISPATCH_HELPER = SOURCE_ROOT / 'tools/task-dispatch.py'
PLAN_HELPER = SOURCE_ROOT / 'tools/task-plan.py'
EXECUTION_SERVICE = SOURCE_ROOT / 'bridge/execution_service.py'
HEX32, HEX64 = '0' * 32, '0' * 64


class DispatchInstallCase(unittest.TestCase):
    """Copies the marked installer into disposable fixtures with spaces."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='dispatch install ')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def run_install(self, bin_dir, conf, completion, code=0):
        home = self.base / 'home with spaces'
        home.mkdir(exist_ok=True)
        installer = self.base / 'copied standalone installer.sh'
        installer.write_bytes(INSTALLER.read_bytes())
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(('UNIO_', 'PYTHON'))}
        env.update(HOME=str(home), UNIO_BIN_DIR=str(bin_dir),
                   UNIO_CONF_DIR=str(conf), UNIO_COMPLETION_DIR=str(completion),
                   UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0')
        # Run from an unrelated directory: the copy must not need the checkout.
        result = subprocess.run(['bash', str(installer)], cwd=home, env=env,
                                capture_output=True, text=True, timeout=180)
        if code == 0:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.env = env
        return result

    def dispatch(self, engine, *args):
        return subprocess.run([str(engine), 'dispatch', *args], cwd=self.base,
                              env=self.env, capture_output=True, text=True, timeout=60)

    def fixture_project(self):
        project = self.base / 'project with spaces'
        (project / 'coord').mkdir(parents=True)
        (project / 'wt').mkdir(parents=True)
        template = project / 'template.json'
        template.write_text('{"instructions": "offline fixture"}\n')
        return project, template

    def strict_grant(self, project, engine, conf, template):
        return {
            'schema_version': 1,
            'project': str(Path(project).resolve()),
            'engine': str(Path(engine).resolve()),
            'config_dir': str(Path(conf).resolve()),
            'template_path': str(Path(template).resolve()),
            'worker': 'grok',
            'reviewer': 'claude',
            'worker_lab': 'Grok Lab',
            'reviewer_lab': 'Claude Lab',
        }

    def mock_provider(self, conf):
        marker = self.base / 'provider was called'
        sentinel = self.base / 'mock provider'
        sentinel.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(marker)) + '\n')
        sentinel.chmod(0o755)
        (conf / 'agents.conf').write_text('mock=' + shlex.quote(str(sentinel)) + '\n')
        return marker


class InstalledDispatchCli(DispatchInstallCase):
    """Installed packaging, help, completion and argument refusals."""

    def setUp(self):
        super().setUp()
        self.bin = self.base / 'bin with spaces'
        self.conf = self.base / 'conf with spaces'
        self.completion = self.base / 'completion with spaces'
        self.run_install(self.bin, self.conf, self.completion)
        self.engine = self.bin / 'unio'

    def test_copied_installer_packages_exact_bytes(self):
        self.assertEqual((self.conf / 'lib' / 'task-dispatch.py').read_bytes(),
                         DISPATCH_HELPER.read_bytes())
        self.assertEqual((self.conf / 'lib' / 'task-plan.py').read_bytes(),
                         PLAN_HELPER.read_bytes())
        self.assertEqual((self.conf / 'lib' / 'browser' / 'execution_service.py').read_bytes(),
                         EXECUTION_SERVICE.read_bytes())

    def test_help_outside_project_and_bash_completion(self):
        result = self.dispatch(self.engine, '--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('unio dispatch', result.stdout)
        for flag in ('--grant', '--project', '--json'):
            self.assertIn(flag, result.stdout)
        for operation in ('prepare', 'approve', 'start'):
            self.assertIn(operation, result.stdout)

        completion = self.completion / 'unio'
        self.assertTrue(completion.is_file())
        text = completion.read_text()
        self.assertIn('dispatch)', text)
        for word in ('--grant', '--json', 'prepare', 'approve', 'start',
                     '--draft-id', '--draft-sha256', '--request-key',
                     '--job-id', '--preview-sha256', '--approval-key',
                     '--reservation-key', '--inventory', '--inventory-sha256', '--timeout'):
            self.assertIn(word, text)

    def test_invalid_arguments_refuse_without_state_or_provider_calls(self):
        project, template = self.fixture_project()
        marker = self.mock_provider(self.conf)
        grant = self.strict_grant(project, self.engine, self.conf, template)
        grant_file = self.base / 'grant.json'
        grant_file.write_text(json.dumps(grant))
        coord = project / 'coord'

        missing = self.dispatch(self.engine, '--grant', str(grant_file), 'prepare')
        self.assertNotEqual(missing.returncode, 0, missing.stdout)
        missing = self.dispatch(self.engine, '--grant', str(grant_file), 'approve')
        self.assertNotEqual(missing.returncode, 0, missing.stdout)

        invalid = self.dispatch(self.engine, '--grant', str(grant_file), 'prepare',
                                '--draft-id', 'malformed', '--draft-sha256', HEX64,
                                '--request-key', HEX32)
        self.assertNotEqual(invalid.returncode, 0, invalid.stdout)
        self.assertIn('--draft-id must be 32 lowercase hex characters', invalid.stderr)

        self.assertFalse((coord / 'ui-execution').exists())
        self.assertFalse((coord / 'ui-jobs.sqlite3').exists())
        self.assertEqual(sorted(path.name for path in coord.iterdir()), [])
        self.assertFalse(marker.exists())

    def test_strict_grant_refuses_malformed_identity_and_unknown_field(self):
        project, template = self.fixture_project()
        grant = self.strict_grant(project, self.engine, self.conf, template)
        grant_file = self.base / 'owner grant.json'
        grant_file.write_text(json.dumps(grant))
        coord = project / 'coord'

        malformed = self.dispatch(self.engine, '--grant', str(grant_file), 'approve',
                                  '--job-id', 'not-a-job-id', '--draft-sha256', HEX64,
                                  '--preview-sha256', HEX64, '--approval-key', HEX32)
        self.assertNotEqual(malformed.returncode, 0, malformed.stdout)
        self.assertIn('--job-id must be 32 lowercase hex characters', malformed.stderr)

        broken = dict(grant)
        broken['authority'] = 'owner'
        broken_file = self.base / 'broken grant.json'
        broken_file.write_text(json.dumps(broken))
        unknown = self.dispatch(self.engine, '--grant', str(broken_file), 'prepare',
                               '--draft-id', HEX32, '--draft-sha256', HEX64,
                               '--request-key', HEX32)
        self.assertNotEqual(unknown.returncode, 0, unknown.stdout)
        self.assertIn('grant must contain exactly', unknown.stderr)

        self.assertFalse((coord / 'ui-execution').exists())
        self.assertFalse((coord / 'ui-jobs.sqlite3').exists())
        self.assertEqual(sorted(path.name for path in coord.iterdir()), [])


class DispatchDestinationPreflight(DispatchInstallCase):
    """A symlinked or hardlinked dispatch destination is refused, never replaced."""

    def setUp(self):
        super().setUp()
        self.bin = self.base / 'bin with spaces'
        self.conf = self.base / 'conf with spaces'
        self.completion = self.base / 'completion with spaces'
        self.run_install(self.bin, self.conf, self.completion)
        self.destination = self.conf / 'lib' / 'task-dispatch.py'

    def test_symlink_and_hardlink_destinations_refused(self):
        sentinel = self.base / 'sentinel target.py'
        sentinel.write_bytes(b'sentinel owner bytes\n')
        self.destination.unlink()
        self.destination.symlink_to(sentinel)
        result = self.run_install(self.bin, self.conf, self.completion, code=1)
        self.assertIn('refusing unsafe task dispatch file', result.stderr)
        self.assertEqual(sentinel.read_bytes(), b'sentinel owner bytes\n')
        self.assertTrue(self.destination.is_symlink())

        partner = self.base / 'hardlink partner.py'
        partner.write_bytes(b'partner owner bytes\n')
        self.destination.unlink()
        os.link(partner, self.destination)
        result = self.run_install(self.bin, self.conf, self.completion, code=1)
        self.assertIn('refusing unsafe task dispatch file', result.stderr)
        self.assertEqual(partner.read_bytes(), b'partner owner bytes\n')
        self.assertEqual(os.stat(self.destination).st_nlink, 2)
        self.assertEqual(os.stat(self.destination).st_ino, os.stat(partner).st_ino)


if __name__ == '__main__':
    unittest.main()
