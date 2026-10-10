#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Tests for agent readiness CLI and bridge."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge.readiness import ReadinessStore, ReadinessError

spec = importlib.util.spec_from_file_location("readiness_cli", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools", "agent-readiness.py"))
readiness_cli = importlib.util.module_from_spec(spec)
sys.modules["readiness_cli"] = readiness_cli
spec.loader.exec_module(readiness_cli)

class FakeSubprocessRun:
    def __init__(self):
        self.commands = []
        self.version_stdout = '2.1.296 (Claude Code)\n'
        self.version_returncode = 0
        self.status_stdout = '{"loggedIn": true, "authMethod": "claude.ai", "privateSentinel": "secret123"}\n'
        self.status_returncode = 0
        self.timeout_on = None

    def __call__(self, args, **kwargs):
        self.commands.append(args)
        if self.timeout_on and self.timeout_on in args:
            raise subprocess.TimeoutExpired(args, kwargs.get('timeout'))
        
        class Result:
            pass
        res = Result()
        if args == ['claude', '--version']:
            res.stdout = self.version_stdout
            res.returncode = self.version_returncode
        elif args == ['claude', 'auth', 'status', '--json']:
            res.stdout = self.status_stdout
            res.returncode = self.status_returncode
        else:
            res.stdout = ''
            res.returncode = 1
        return res

class TestReadiness(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix='unio-test-')
        self.store = ReadinessStore(self.temp_dir)
        self.original_run = subprocess.run
        self.fake_run = FakeSubprocessRun()
        subprocess.run = self.fake_run

    def tearDown(self):
        subprocess.run = self.original_run
        shutil.rmtree(self.temp_dir)

    def test_invalid_path(self):
        with self.assertRaises(ReadinessError):
            ReadinessStore('/nonexistent/path/that/is/not/real')

    def test_refresh_success_drops_private_fields(self):
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now)
        
        with open(os.path.join(self.temp_dir, 'coord', 'readiness', 'observations.json')) as f:
            data = json.load(f)
        
        latest = data['agents']['claude']['latest']
        self.assertTrue(latest['loggedIn'])
        self.assertEqual(latest['authMethod'], 'claude.ai')
        self.assertNotIn('privateSentinel', latest)
        
        view = self.store.show(now=now)
        self.assertEqual(view['agents']['claude']['status'], 'fresh')

    def test_refresh_unsupported_version(self):
        self.fake_run.version_stdout = '1.0.0 (Old)\n'
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now)
        
        view = self.store.show(now=now)
        self.assertEqual(view['agents']['claude']['status'], 'failed')
        self.assertIn('unsupported version', view['agents']['claude']['latest_observation']['error'])

    def test_refresh_timeout(self):
        self.fake_run.timeout_on = 'status'
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now)
        
        view = self.store.show(now=now)
        self.assertEqual(view['agents']['claude']['status'], 'failed')
        self.assertEqual(view['agents']['claude']['latest_observation']['error'], 'timeout')

    def test_historical_evidence_retained(self):
        now1 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now1)
        
        self.fake_run.status_returncode = 1
        now2 = datetime(2026, 10, 10, 12, 5, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now2)
        
        view = self.store.show(now=now2)
        self.assertEqual(view['agents']['claude']['status'], 'failed')
        self.assertEqual(view['agents']['claude']['last_good_observation']['observed_at'], now1.isoformat())
        self.assertTrue(view['agents']['claude']['last_good_observation']['loggedIn'])

    def test_stale(self):
        now1 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now1)
        
        now2 = now1 + timedelta(seconds=2000)
        view = self.store.show(now=now2)
        self.assertEqual(view['agents']['claude']['status'], 'stale')
        
    def test_future_clock_skew(self):
        now1 = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now1)
        
        now2 = now1 - timedelta(seconds=600)
        view = self.store.show(now=now2)
        self.assertEqual(view['agents']['claude']['status'], 'unknown')
        
    def test_invalid_json(self):
        self.fake_run.status_stdout = '{"loggedIn": true'
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now)
        
        view = self.store.show(now=now)
        self.assertEqual(view['agents']['claude']['status'], 'failed')
        self.assertTrue('malformed' in view['agents']['claude']['latest_observation']['error'])
        
    def test_duplicate_keys(self):
        self.fake_run.status_stdout = '{"loggedIn": true, "loggedIn": false}'
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now)
        
        view = self.store.show(now=now)
        self.assertEqual(view['agents']['claude']['status'], 'failed')
        self.assertTrue('duplicate JSON key' in view['agents']['claude']['latest_observation']['error'])
        
    def test_read_only_show(self):
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        view = self.store.show(now=now)
        self.assertEqual(view['state'], 'missing')
        self.assertEqual(len(view['agents']), 0)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, 'coord', 'readiness')))

if __name__ == '__main__':
    unittest.main()
