#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed command smoke/refusal tests; no provider invocations."""
import importlib.util
import json
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('installed_effort_tests',
    Path(__file__).with_name('unio-codex-worker.py'))
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)


class CommandTests(bundle.InstalledCase):
    def test_get_does_not_invent_identity_or_configuration(self):
        result = self.call('codex-1', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertEqual(data['state'], 'unsupported')
        self.assertEqual(data['worker'], 'codex-1')
        self.assertIsNone(data['requested_effort'])
        self.assertIsNone(data['configured_effort'])
        self.assertFalse(data['native_acknowledged'])
        self.assertFalse(data['pending_next_supported_turn'])
        for key in ('effective_effort', 'model', 'task', 'managed_worker_identity',
                    'subscription_route', 'cli_version'):
            self.assertEqual(data[key], 'Unknown')
        self.assertIn('subsequent turns', data['application_boundary'])
        self.assertIn('+00:00', data['observed_at'])

    def test_request_rejected_without_writes_or_provider_calls(self):
        def snapshot():
            return {str(p.relative_to(self.project)): p.read_bytes()
                    for p in self.project.rglob('*') if p.is_file()}
        before = snapshot()
        for effort in ('low', 'medium', 'high', 'xhigh'):
            with self.subTest(effort=effort):
                result = self.call('codex-1', effort, '--json')
                self.assertEqual(result.returncode, 2, result.stderr)
                data = json.loads(result.stdout)
                self.assertEqual(data['requested_effort'], effort)
                self.assertEqual(data['state'], 'unsupported')
                self.assertFalse(data['native_acknowledged'])
                self.assertFalse(data['pending_next_supported_turn'])
                self.assertIsNone(data['configured_effort'])
        self.assertEqual(before, snapshot())

    def test_invalid_levels_settings_ids_and_overbound_input(self):
        for args in (('codex-1', 'max'), ('codex-1', 'ultra'),
                     ('codex-1', 'low', '--model', 'other'),
                     ('codex-1', 'low', '--service-tier', 'fast'),
                     ('codex-1', 'low', '--sandbox', 'none'),
                     ('../codex-1',), ('x' * 129,), ('codex-1', 'x' * 65536),
                     ('codex-1', 'low', 'high'), ('codex-1', '--project', '/tmp')):
            with self.subTest(args=tuple(a[:40] for a in args)):
                result = self.call(*args)
                self.assertEqual(result.returncode, 2)

    def test_foreign_missing_and_replaced_workers(self):
        self.assertEqual(self.call('claude-1', 'low').returncode, 2)
        self.assertEqual(self.call('codex-missing').returncode, 2)
        alias = self.project / 'wt' / 'codex-alias'
        alias.symlink_to(self.project / 'wt' / 'codex-1', target_is_directory=True)
        try:
            self.assertEqual(self.call('codex-alias').returncode, 2)
        finally:
            alias.unlink()

    def test_unmanaged_or_forged_channels_cannot_enable_requests(self):
        forged = self.project / 'coord' / 'worker-effort.json'
        forged.write_text('{"managed":true,"threadId":"foreign","effort":"high"}')
        try:
            result = self.call('codex-1', 'low', '--json')
            self.assertEqual(result.returncode, 2)
            self.assertEqual(json.loads(result.stdout)['state'], 'unsupported')
            forged.write_text('{malformed')
            self.assertEqual(self.call('codex-1', 'low').returncode, 2)
        finally:
            forged.unlink()

    def test_human_request_and_outside_project(self):
        result = self.call('codex-1', 'low')
        self.assertEqual(result.returncode, 2)
        self.assertIn('No effort request was queued or sent', result.stdout)
        self.assertNotEqual(self.call('codex-1', cwd=self.root).returncode, 0)


if __name__ == '__main__':
    unittest.main()
