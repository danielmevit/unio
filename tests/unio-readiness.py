#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Tests for agent readiness CLI and bridge."""
import importlib.util
import fcntl
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
        self.original_native = readiness_cli._native
        self.fake_run = FakeSubprocessRun()
        readiness_cli._native = self.fake_run

    def tearDown(self):
        readiness_cli._native = self.original_native
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
        self.assertEqual('unsupported_version', view['agents']['claude']['latest_observation']['error'])

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
        self.assertEqual('invalid_status', view['agents']['claude']['latest_observation']['error'])
        
    def test_duplicate_keys(self):
        self.fake_run.status_stdout = '{"loggedIn": true, "loggedIn": false}'
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir, now=now)
        
        view = self.store.show(now=now)
        self.assertEqual(view['agents']['claude']['status'], 'failed')
        self.assertEqual('invalid_status', view['agents']['claude']['latest_observation']['error'])
        
    def test_read_only_show(self):
        now = datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)
        view = self.store.show(now=now)
        self.assertEqual(view['state'], 'missing')
        self.assertEqual(len(view['agents']), 0)
        self.assertFalse(os.path.exists(os.path.join(self.temp_dir, 'coord', 'readiness')))

    def test_fixed_argv_and_distinct_authentication_capacity(self):
        self.assertEqual(readiness_cli.run_refresh(self.temp_dir), 0)
        self.assertEqual(self.fake_run.commands, [['claude', '--version'], ['claude', 'auth', 'status', '--json']])
        agent = self.store.show(agent='claude')['agents']['claude']
        self.assertEqual(agent['authentication'], 'signed_in')
        self.assertEqual(agent['capacity'], 'unknown')
        self.assertEqual(agent['dispatch_readiness'], 'unknown')

    def test_boolean_and_native_labels_never_coerced(self):
        for value in ('false', 1, {}, None):
            with self.subTest(value=value), self.assertRaises(ReadinessError):
                self.store.record_good('claude', 'native', value)
        for value in ('PRIVATE_SENTINEL', {'credential': 'PRIVATE_SENTINEL'}, 1):
            with self.subTest(value=value), self.assertRaises(ReadinessError):
                self.store.record_good('claude', 'native', True, auth_method=value)
        self.assertFalse((Path(self.temp_dir)/'coord/readiness').exists())

    def test_invalid_native_fields_are_private_failures(self):
        for index, data in enumerate([
            {'loggedIn': True, 'authMethod': 'PRIVATE_SENTINEL'},
            {'loggedIn': True, 'authMethod': {'credential': 'PRIVATE_SENTINEL'}},
            {'loggedIn': 'false'}, {'loggedIn': True, 'apiProvider': 1},
        ]):
            self.fake_run.status_stdout = json.dumps(data)
            now = datetime(2026,10,10,12,0,tzinfo=timezone.utc)+timedelta(seconds=index)
            self.assertEqual(readiness_cli.run_refresh(self.temp_dir,now=now),1)
            agent = self.store.show(agent='claude',now=now)['agents']['claude']
            self.assertEqual(agent['authentication'],'unknown')
            self.assertEqual(agent['latest_observation']['error'],'invalid_status')
            self.assertNotIn('PRIVATE_SENTINEL',json.dumps(agent))

    def test_version_suffix_and_raw_diagnostic_never_accepted_or_saved(self):
        for index, value in enumerate(('2.1.296evil (Claude Code)', 'PRIVATE_NATIVE_DIAGNOSTIC')):
            self.fake_run.version_stdout=value
            now=datetime(2026,10,10,12,0,tzinfo=timezone.utc)+timedelta(seconds=index)
            self.assertEqual(readiness_cli.run_refresh(self.temp_dir,now=now),1)
            agent=self.store.show(agent='claude',now=now)['agents']['claude']
            self.assertEqual(agent['authentication'],'unknown')
            self.assertEqual(agent['latest_observation']['error'],'unsupported_version')
            self.assertNotIn(value, (Path(self.temp_dir)/'coord/readiness/observations.json').read_text())
        self.assertEqual(self.fake_run.commands,[['claude','--version']]*2)

    def test_any_clock_rollback_is_unknown_and_signed_out_is_valid(self):
        now=datetime(2026,10,10,12,0,tzinfo=timezone.utc)
        self.fake_run.status_stdout='{"loggedIn":false}'
        readiness_cli.run_refresh(self.temp_dir,now=now)
        self.assertEqual(self.store.show(agent='claude',now=now)['agents']['claude']['authentication'],'signed_out')
        for seconds in (1,60,600):
            agent=self.store.show(agent='claude',now=now-timedelta(seconds=seconds))['agents']['claude']
            self.assertEqual(agent['authentication'],'unknown')
            self.assertEqual(agent['status'],'unknown')

    def test_nonprivate_and_hardlinked_state_refused_without_mutation(self):
        readiness_cli.run_refresh(self.temp_dir)
        state=Path(self.temp_dir)/'coord/readiness/observations.json'; before=state.read_bytes()
        state.chmod(0o644)
        self.assertEqual(self.store.show(agent='claude')['state'],'invalid')
        self.assertEqual(state.read_bytes(),before);state.chmod(0o600)
        link=Path(self.temp_dir)/'second-link';os.link(state,link)
        self.assertEqual(self.store.show(agent='claude')['state'],'invalid')
        self.assertEqual(state.read_bytes(),before)

    def test_unsafe_directory_and_symlink_state_refused(self):
        readiness_cli.run_refresh(self.temp_dir)
        directory=Path(self.temp_dir)/'coord/readiness'; directory.chmod(0o755)
        with self.assertRaises(ReadinessError):self.store.show(agent='claude')
        directory.chmod(0o700); state=directory/'observations.json'
        backup=directory/'old.json';state.rename(backup);state.symlink_to(backup)
        self.assertEqual(self.store.show(agent='claude')['state'],'invalid')

    def test_locked_write_is_bounded_and_retains_previous_state(self):
        now=datetime(2026,10,10,12,0,tzinfo=timezone.utc)
        readiness_cli.run_refresh(self.temp_dir,now=now)
        directory=Path(self.temp_dir)/'coord/readiness'; state=directory/'observations.json'
        before=state.read_bytes()
        with (directory/'.observations.lock').open('r+') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            started=time.monotonic()
            with self.assertRaises(ReadinessError):
                self.store.record_good('claude','native',False,now=now+timedelta(seconds=1))
            self.assertLess(time.monotonic()-started,3)
        self.assertEqual(state.read_bytes(),before)

    def test_native_output_is_bounded_while_reading(self):
        for stream in ('stdout','stderr'):
            code='import sys;sys.'+stream+'.write("x"*1000000);sys.'+stream+'.flush()'
            with self.assertRaises(readiness_cli.NativeFailure) as error:
                self.original_native([sys.executable,'-c',code],timeout=1,limit=1024)
            self.assertEqual(error.exception.reason,'output_overflow')

    def test_native_timeout_cleans_owned_descendant_holding_pipes(self):
        pidfile=Path(self.temp_dir)/'child.pid'
        code=('import pathlib,subprocess,sys; p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"]);'
              'pathlib.Path('+repr(str(pidfile))+').write_text(str(p.pid))')
        with self.assertRaises(readiness_cli.NativeFailure) as error:
            self.original_native([sys.executable,'-c',code],timeout=0.4,limit=1024)
        self.assertEqual(error.exception.reason,'timeout')
        pid=int(pidfile.read_text());proc=Path('/proc')/str(pid)/'stat'
        for _ in range(30):
            if not proc.exists() or proc.read_text().split()[2]=='Z':break
            time.sleep(0.01)
        self.assertTrue(not proc.exists() or proc.read_text().split()[2]=='Z')

if __name__ == '__main__':
    unittest.main()
