#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed CLI-update facts, refusals, awareness and packaging regression.

Offline fixtures only: fake CLI executables, a local metadata canary and
throwaway caches. No real CLI installation, provider, account or unmanaged
session is touched, executed or updated. PATH is restricted to the fixture
bin plus /usr/bin:/bin, so a missing fake can never fall back to the real
~/.local/bin, ~/.opencode, ~/.grok or nvm CLIs.
"""
from datetime import datetime, timedelta, timezone
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]

FAKE_TEMPLATE = '''#!/usr/bin/env python3
import json, os, sys, time
NAME = {name!r}
VERSION = {version!r}
args = sys.argv[1:]


def note(tag, args):
    record = os.environ.get('FAKE_RECORD')
    if record:
        with open(record, 'a') as fh:
            fh.write(json.dumps({{'name': NAME, 'tag': tag, 'args': args}}) + '\\n')


if args == ['--version']:
    note('version', args)
    print(VERSION)
    raise SystemExit({vexit})
note('called', args)
if NAME == 'grok' and args[:3] == ['update', '--check', '--json']:
    print(json.dumps({{'currentVersion': VERSION, 'latestVersion': {latest!r}}}))
    raise SystemExit(0)
if args == {update_args!r}:
    time.sleep({update_delay})
    raise SystemExit({update_exit})
if not args:
    time.sleep(30)   # a native session of this exact executable
raise SystemExit({update_exit})
'''


def now_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def seed_cache(conf, routes=None, startup_checked_at=None):
    directory = Path(conf) / 'cli-updates'
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'cache.json'
    if path.exists() or path.is_symlink():
        path.unlink()  # a leftover symlink from a hostile fixture never survives
    document = {'schema_version': 1, 'kind': 'unio-cli-updates',
                'startup_checked_at': startup_checked_at or now_iso(),
                'routes': routes or {}}
    path.write_text(json.dumps(document, indent=2) + '\n')


def seeded_latest(version, age_seconds=0):
    return {'version': version, 'status': 'ok',
            'source': 'github-release:google-antigravity/antigravity-cli',
            'checked_at': (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
                           ).replace(microsecond=0).isoformat()}


class ProxyCanary:
    """Local-only HTTP canary: records whether a network metadata fetch
    was even attempted; it answers nothing useful."""

    def __init__(self):
        self.attempts = 0
        canary = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def _refuse(self):
                canary.attempts += 1
                try:
                    self.send_response(400)
                    self.end_headers()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

            do_CONNECT = do_GET = do_POST = _refuse

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.port = self.server.server_port
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def url(self):
        return 'http://127.0.0.1:%d' % self.port

    def stop(self):
        self.server.shutdown()
        self.server.server_close()


class CliUpdatesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='unio cli updates ')
        cls.root = Path(cls.tmp.name).resolve()
        cls.home = cls.root / 'isolated home'
        cls.bin = cls.root / 'installed bin with  spaces'
        cls.conf = cls.root / 'configuration with spaces'
        cls.fakebin = cls.root / 'fake clis'
        cls.outside = cls.root / 'outside any project'
        cls.record = cls.root / 'fake cli calls.jsonl'
        cls.home.mkdir()
        cls.fakebin.mkdir()
        cls.outside.mkdir()
        cls.env = dict(os.environ, HOME=str(cls.home),
                       UNIO_BIN_DIR=str(cls.bin), UNIO_CONF_DIR=str(cls.conf),
                       UNIO_COMPLETION_DIR=str(cls.root / 'completion'),
                       TMPDIR=str(cls.root), PYTHONDONTWRITEBYTECODE='1',
                       UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0',
                       UNIO_CLI_UPDATES_OFFLINE='1', FAKE_RECORD=str(cls.record),
                       GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1')
        cls.env['PATH'] = str(cls.fakebin) + ':/usr/bin:/bin'
        subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=cls.env,
                       check=True, capture_output=True, timeout=180)
        cls.unio = cls.bin / 'unio'
        cls.installed_helper = cls.conf / 'lib' / 'cli-updates.py'
        cls.canary = ProxyCanary()

    @classmethod
    def tearDownClass(cls):
        cls.canary.stop()
        cls.tmp.cleanup()

    def fake(self, name, *, version, vexit=0, latest=None, update_args=None,
             update_exit=0, update_delay=0):
        path = self.fakebin / name
        path.write_text(FAKE_TEMPLATE.format(
            name=name, version=version, vexit=vexit, latest=latest,
            update_args=update_args, update_exit=update_exit,
            update_delay=update_delay))
        path.chmod(0o755)
        return path

    def fresh_fakes(self):
        """Standard machine-like route set, all fake; recording resets."""
        if self.record.exists():
            self.record.unlink()
        self.fake('agy', version='1.5.4', update_args=['update'], update_exit=0)
        self.fake('grok', version='grok 1.0.77 (hash)', latest='1.0.77',
                  update_args=['update', '--stable'], update_exit=0)
        self.fake('copilot', version='GitHub Copilot CLI 1.0.108.',
                  update_args=['update', 'stable'], update_exit=0)
        self.fake('opencode', version='1.19.5', update_args=['upgrade'], update_exit=0)
        self.fake('claude', version='2.1.322 (Claude Code)',
                  update_args=['nonexistent-subcommand'], update_exit=0)
        self.fake('codex', version='codex-cli 0.167.0',
                  update_args=['nonexistent-subcommand'], update_exit=0)
        self.fake('vibe', version='vibe 3.1.1',
                  update_args=['upgrade would never be used'], update_exit=0)
        (self.fakebin / 'uv').unlink(missing_ok=True)

    def helper(self, file, conf, *args, env=None, cwd=None, timeout=120):
        return subprocess.run([sys.executable, '-I', '-S', '-B', str(file),
                               '--conf', str(conf), *args],
                              env=env or self.env, cwd=cwd or self.outside,
                              capture_output=True, text=True, timeout=timeout)

    def module(self, *args, **kwargs):
        return self.helper(self.installed_helper, self.conf, *args, **kwargs)

    def engine(self, *args, env=None, cwd=None, timeout=180):
        # Non-project engine calls run from /: the harness tree sits inside
        # the owner's real Unio project, whose holds must not gate fixture
        # runs (and fixtures are on a private restricted PATH anyway).
        return subprocess.run([str(self.unio), *args], env=env or self.env,
                              cwd=cwd or '/', capture_output=True,
                              text=True, timeout=timeout)

    @staticmethod
    def stop_proc(proc):
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=10)

    def calls(self, name=None, tag=None):
        if not self.record.exists():
            return []
        rows = [json.loads(line) for line in self.record.read_text().splitlines()]
        return [row for row in rows
                if (name is None or row['name'] == name) and (tag is None or row['tag'] == tag)]

    def make_project(self, name='project with  spaces'):
        project = self.root / name
        (project / 'coord').mkdir(parents=True)
        (project / 'wt').mkdir()
        doctor_repo = project / 'repo'
        doctor_repo.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(doctor_repo)],
                       check=True, capture_output=True)
        subprocess.run(['git', '-C', str(doctor_repo),
                        '-c', 'user.email=fixture@invalid', '-c', 'user.name=fixture',
                        'commit', '-q', '--allow-empty', '-m', 'fixture'],
                       check=True, capture_output=True)
        return project

    # ---------------------------------------------------------------- check

    def test_check_reports_facts_and_never_calls_an_updater(self):
        self.fresh_fakes()
        (self.fakebin / 'claude').unlink()  # an explicit request still checks absent tools
        done = self.module('check', '--json', 'antigravity', 'grok', 'claude')
        self.assertEqual(done.returncode, 0, done.stderr)
        document = json.loads(done.stdout)
        self.assertEqual(set(document), {'schema_version', 'checked_at', 'source',
                                         'fresh_within_seconds', 'project', 'routes',
                                         'cache_writable'})
        rows = {row['name']: row for row in document['routes']}
        self.assertEqual(set(rows), {'antigravity', 'grok', 'claude'})
        self.assertEqual(rows['antigravity']['installed_version'], '1.5.4')
        self.assertEqual(rows['antigravity']['update_state'], 'maintenance_not_implemented')
        self.assertEqual(rows['antigravity']['compatibility'], 'unknown')
        self.assertEqual(rows['grok']['latest_version'], '1.0.77')
        self.assertEqual(rows['grok']['latest_source'], 'grok-update-check')
        self.assertFalse(rows['claude']['present'])
        self.assertEqual(rows['claude']['update_state'], 'absent')
        # Contact surface: version probes plus grok's read-only check only.
        self.assertEqual([row['args'] for row in self.calls(tag='called')],
                         [['update', '--check', '--json']],
                         'a check must never run an updater argument')
        self.assertEqual([row['args'] for row in self.calls(tag='version')
                         if row['name'] == 'claude'], [],
                         'absent tools are never probed')

    def test_fresh_cache_avoids_network_and_stale_asks_once(self):
        self.fresh_fakes()
        env = dict(self.env, UNIO_CLI_UPDATES_OFFLINE='0',
                   https_proxy=self.canary.url(), http_proxy=self.canary.url())
        seed_cache(self.conf, routes={'antigravity': {'latest': seeded_latest('9.9.9', 60)}})
        done = self.module('check', '--json', 'antigravity', env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        row = json.loads(done.stdout)['routes'][0]
        self.assertEqual((row['latest_version'], row['latest_from_cache']), ('9.9.9', True))
        self.assertEqual(self.canary.attempts, 0, 'a fresh cache must not touch the network')
        # A stale cache refetches once; the refused canary is reported honestly.
        seed_cache(self.conf, routes={'antigravity': {'latest': seeded_latest('9.9.9', 30 * 86400)}})
        done = self.module('check', '--json', 'antigravity', env=env)
        self.assertEqual(done.returncode, 0, done.stderr)
        row = json.loads(done.stdout)['routes'][0]
        self.assertIsNone(row['latest_version'])
        self.assertEqual(row['latest_status'], 'unavailable')
        self.assertEqual(self.canary.attempts, 1, 'a stale cache tries metadata exactly once')

    def test_corrupt_or_hostile_cache_is_unknown_and_never_executed(self):
        self.fresh_fakes()
        directory = Path(self.conf) / 'cli-updates'
        seed_cache(self.conf)
        (directory / 'cache.json').write_text('{corrupt bytes, not json at all')
        done = self.module('check', '--json', 'antigravity')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(json.loads(done.stdout)['routes'][0]['installed_version'], '1.5.4')
        self.assertEqual(json.loads((directory / 'cache.json').read_text())['schema_version'], 1,
                         'a corrupt cache is rebuilt as Unknown, never trusted')
        # A symlinked hostile cache: never executed, never written through.
        (directory / 'cache.json').unlink()
        threat = self.root / 'hostile cache.json'
        threat.write_text(json.dumps({
            'schema_version': 1, 'kind': 'unio-cli-updates', 'startup_checked_at': now_iso(),
            'routes': {'antigravity': {'latest': {'version': '9.9.9', 'status': 'ok',
                                                   'source': 'evil', 'checked_at': now_iso()},
                                        'command': ['rm', 'a-hostile-cached-command']}}}) + '\n')
        (directory / 'cache.json').symlink_to(threat)
        done = self.module('check', '--json', 'antigravity')
        self.assertEqual(done.returncode, 0, done.stderr)
        document = json.loads(done.stdout)
        self.assertFalse(document['cache_writable'], 'writing through a symlink must be refused')
        self.assertNotEqual(document['routes'][0]['latest_source'], 'evil',
                            'a refused cache contributes no facts')
        self.assertIn('a-hostile-cached-command', threat.read_text(),
                      'no cached command text was executed or removed')

    def test_aliases_dedupe_onto_one_route_report(self):
        self.fresh_fakes()
        done = self.module('check', '--json', 'antigravity', 'agy', 'vibe', 'mistral-vibe')
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = json.loads(done.stdout)['routes']
        self.assertEqual([row['name'] for row in rows], ['antigravity', 'vibe'],
                         'aliases deduplicate; each route is reported once')
        self.assertEqual(set(rows[0]['aliases']), {'antigravity', 'agy'})
        self.assertEqual(rows[0]['group'], 'google')
        self.assertEqual(rows[1]['group'], 'mistral')

    def test_unknown_route_and_hostile_names_fail_as_usage(self):
        self.fresh_fakes()
        done = self.module('check', 'not-a-known-cli')
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("unknown agent 'not-a-known-cli'", done.stderr)
        done = self.module('check', 'agy; rm -rf (never evaluated)')
        self.assertEqual(done.returncode, 2, done.stderr)

    # --------------------------------------------------------------- update

    def test_update_refuses_ordinary_and_failure_routes_with_zero_updater_calls(self):
        self.fresh_fakes()
        # Ordinary case: every present target is refused, nothing is executed.
        done = self.module('update', '--json', 'copilot', 'grok', 'vibe')
        self.assertEqual(done.returncode, 1, done.stdout)
        document = json.loads(done.stdout)
        self.assertEqual(document['install_policy'], document['install_policy'])
        self.assertIn('maintenance_not_implemented', document['install_policy'])
        rows = {row['name']: row for row in document['routes']}
        for name in ('copilot', 'grok', 'vibe'):
            self.assertEqual((rows[name]['action'], rows[name]['reason']),
                             ('refused', 'maintenance_not_implemented'), name)
            self.assertIs(rows[name]['updater_executed'], False, name)
            self.assertIsNone(rows[name]['updater_exit'], name)
            self.assertEqual(rows[name]['compatibility'], 'unknown', name)
        self.assertIn('copilot update stable', rows['copilot']['manual'])
        self.assertIn('grok update --stable', rows['grok']['manual'])
        self.assertIn('uv tool upgrade mistral-vibe', rows['vibe']['manual'],
                      'a refused route keeps its frozen manual plan')
        self.assertEqual(self.calls(), [], 'no updater and no probe may run at all')
        # Failure case: a CLI whose updater would exit nonzero is never invoked.
        self.fresh_fakes()
        self.fake('opencode', version='1.19.5', update_args=['upgrade'], update_exit=7)
        done = self.module('update', '--json', 'opencode')
        self.assertEqual(done.returncode, 1, done.stdout)
        row = json.loads(done.stdout)['routes'][0]
        self.assertEqual((row['action'], row['reason'], row['updater_executed']),
                         ('refused', 'maintenance_not_implemented', False))
        self.assertEqual([entry['args'] for entry in self.calls(name='opencode')],
                         [], 'a would-fail updater must never be invoked')

    def test_update_refuses_every_route_under_all_busy_states_with_zero_calls(self):
        # STOP owner hold.
        self.fresh_fakes()
        stop_project = self.make_project('frozen by owner')
        (stop_project / 'coord' / 'STOP').write_text('frozen\n')
        done = subprocess.run([sys.executable, '-I', '-S', '-B', str(self.installed_helper),
                              '--conf', str(self.conf), '--project', str(stop_project),
                              'update', 'copilot', 'grok'],
                             env=self.env, cwd=self.outside, capture_output=True,
                             text=True, timeout=120)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn('copilot: refused — maintenance_not_implemented', done.stdout)
        self.assertIn('grok: refused — maintenance_not_implemented', done.stdout)
        self.assertIn('manual plan', done.stdout)
        self.assertEqual(self.calls(), [], 'no updater and no probe ran during a STOP hold')
        # Held project worker lock.
        lock_project = self.make_project('busy worker')
        locks = lock_project / 'coord' / '.locks'
        locks.mkdir()
        marker = self.root / 'lock ready'
        if marker.exists():
            marker.unlink()
        helper = subprocess.Popen(
            [sys.executable, '-c',
             'import fcntl, sys, time\n'
             'f = open(sys.argv[1], "w+")\n'
             'fcntl.flock(f.fileno(), fcntl.LOCK_EX)\n'
             'open(sys.argv[2], "w").write("held")\n'
             'time.sleep(60)\n',
             str(locks / 'mock.lock'), str(marker)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_proc, helper)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not marker.exists():
            time.sleep(0.05)
        self.assertTrue(marker.exists(), 'lock-holder fixture never started')
        done = subprocess.run([sys.executable, '-I', '-S', '-B', str(self.installed_helper),
                               '--conf', str(self.conf), '--project', str(lock_project),
                               'update', 'copilot'],
                              env=self.env, cwd=self.outside, capture_output=True,
                              text=True, timeout=120)
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn('maintenance_not_implemented', done.stdout)
        self.assertEqual(self.calls(), [], 'no updater and no probe ran during a worker run')
        # Native process with the exact executable identity: still refused,
        # never signalled, and never used as permission or idle proof.
        if self.record.exists():
            self.record.unlink()
        native = self.fakebin / 'copilot'
        session = subprocess.Popen([sys.executable, str(native)],
                                   env={k: v for k, v in self.env.items()
                                        if k != 'FAKE_RECORD'},
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self.stop_proc, session)
        time.sleep(0.4)
        done = self.module('update', 'copilot')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn('copilot: refused — maintenance_not_implemented', done.stdout)
        self.assertEqual(self.calls(), [], 'no updater and no probe ran during a native session')
        self.assertIsNone(session.poll(), 'the busy session is never signalled or restarted')

    def test_update_with_hostile_cache_still_refuses_without_reading_or_executing(self):
        self.fresh_fakes()
        seed_cache(self.conf)
        directory = Path(self.conf) / 'cli-updates'
        (directory / 'cache.json').write_text(json.dumps({
            'schema_version': 1, 'kind': 'unio-cli-updates',
            'startup_checked_at': now_iso(),
            'routes': {'antigravity': {'latest': {'version': '9.9.9', 'status': 'ok',
                                                   'source': 'evil', 'checked_at': now_iso()},
                                        'command': ['rm', 'a-hostile-cached-command']}}}) + '\n')
        done = self.module('update', '--json', 'antigravity')
        self.assertEqual(done.returncode, 1, done.stdout)
        row = json.loads(done.stdout)['routes'][0]
        self.assertEqual((row['action'], row['reason'], row['updater_executed']),
                         ('refused', 'maintenance_not_implemented', False))
        self.assertEqual(self.calls(), [], 'a hostile cache never leads to an execution')
        self.assertIn('a-hostile-cached-command', (directory / 'cache.json').read_text(),
                      'no cached command text was executed or removed')

    def test_update_check_only_and_manual_methods_are_reported(self):
        self.fresh_fakes()
        # vibe without a verified uv-managed install stays manual in the check.
        done = self.module('check', '--json', 'vibe')
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = json.loads(done.stdout)['routes']
        self.assertEqual(rows[0]['update_state'], 'manual')
        # The update request still refuses with an exact manual command.
        done = self.module('update', 'vibe')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn('refused — maintenance_not_implemented', done.stdout)
        self.assertIn('uv tool upgrade mistral-vibe', done.stdout,
                      'the refusal carries the exact frozen manual command')
        self.assertEqual(self.calls(name='vibe', tag='called'), [])
        # claude/codex stay check-only; updates refuse them explicitly too.
        done = self.module('check', '--json', 'claude', 'codex')
        self.assertEqual(done.returncode, 0, done.stderr)
        rows = {row['name']: row for row in json.loads(done.stdout)['routes']}
        self.assertEqual(rows['claude']['update_state'], 'check-only')
        self.assertEqual(rows['codex']['update_state'], 'check-only')
        done = self.module('update', 'claude', 'codex')
        self.assertEqual(done.returncode, 1, done.stdout)
        self.assertIn('claude: refused — maintenance_not_implemented', done.stdout)
        self.assertIn('codex: refused — maintenance_not_implemented', done.stdout)
        self.assertEqual(self.calls(name='claude', tag='called'), [])
        self.assertEqual(self.calls(name='codex', tag='called'), [])

    def test_missing_routes_are_skipped_absent(self):
        self.fresh_fakes()
        for name in ('opencode', 'claude', 'codex'):
            (self.fakebin / name).unlink(missing_ok=True)
        done = self.module('update', 'claude', 'codex')
        self.assertEqual(done.returncode, 0, 'absent routes are skipped: %s' % done.stdout)
        self.assertIn('claude: skipped', done.stdout)
        self.assertIn('codex: skipped', done.stdout)
        done = self.module('update', 'claude', 'agy')
        self.assertEqual(done.returncode, 1,
                         'one present target still refuses: %s' % done.stdout)
        self.assertIn('claude: skipped — absent on PATH', done.stdout)
        self.assertIn('antigravity: refused — maintenance_not_implemented', done.stdout,
                      'the human report uses route names, not aliases')

    def test_unverifiable_version_probe_is_unknown_and_nonzero(self):
        self.fresh_fakes()
        self.fake('agy', version='broken output', vexit=3)
        done = self.module('check', '--json', 'agy')
        self.assertEqual(done.returncode, 1, done.stdout)
        row = json.loads(done.stdout)['routes'][0]
        self.assertIsNone(row['installed_version'])
        self.assertEqual(row['version_exit'], 3)
        done = self.module('check', 'agy')
        self.assertIn('installed Unknown', done.stdout)

    # ------------------------------------------------------------- startup

    def test_startup_line_isolated_and_bounded_refresh_needs_no_cli(self):
        self.fresh_fakes()
        shutil.rmtree(Path(self.conf) / 'cli-updates', ignore_errors=True)
        done = self.module('startup')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(done.stdout.strip().splitlines()), 1, done.stdout)
        self.assertTrue(done.stdout.startswith('cli-updates:'), done.stdout)
        self.assertIn('unio update clis --check', done.stdout)
        cache = Path(self.conf) / 'cli-updates' / 'cache.json'
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and not cache.exists():
            time.sleep(0.1)
        self.assertTrue(cache.exists(), 'the bounded background refresh wrote the cache')
        written = json.loads(cache.read_text())
        self.assertEqual(written['schema_version'], 1)
        self.assertIn('antigravity', written['routes'], 'presence facts are recorded')
        self.assertEqual(self.calls(tag='called'), [],
                         'the background refresh never executes a CLI or updater')
        done = self.module('startup')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('(fresh)', done.stdout)
        self.assertEqual(len(done.stdout.strip().splitlines()), 1, done.stdout)

    def test_startup_env_opt_out_is_silent_and_spawns_nothing(self):
        self.fresh_fakes()
        other = self.root / 'opted out conf'
        if other.exists():
            shutil.rmtree(other)
        other.mkdir()
        shutil.copy(self.installed_helper, other / 'cli-updates.py')  # routed by helper()
        done = self.helper(other / 'cli-updates.py', other, 'startup',
                           env=dict(self.env, UNIO_CLI_UPDATES_OFF='1'))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, '')
        time.sleep(1.0)
        self.assertFalse((other / 'cli-updates').exists(),
                         'an opted-out startup spawns no refresh job')

    # ------------------------------------------------- engine and packaging

    def test_engine_command_surface_and_awareness_entries(self):
        self.fresh_fakes()
        project = self.make_project()
        done = self.engine('update', 'clis', '--check', 'agy')
        self.assertEqual(done.returncode, 0, (done.stdout, done.stderr))
        self.assertIn('AI CLI update check', done.stdout)
        self.assertIn('antigravity: installed 1.5.4', done.stdout)
        done = self.engine('update', 'clis', 'agy')
        self.assertEqual(done.returncode, 1, (done.stdout, done.stderr))
        self.assertIn('antigravity: refused — maintenance_not_implemented', done.stdout)
        self.assertIn('manual plan', done.stdout)
        self.assertEqual(self.calls(name='agy', tag='called'), [],
                         'the engine update surface never reaches an updater')
        done = self.engine('update')
        self.assertEqual(done.returncode, 2, done.stdout)
        done = self.engine('update', 'something else')
        self.assertEqual(done.returncode, 2, done.stdout)
        done = self.engine('update', 'clis', 'unknown-route')
        self.assertEqual(done.returncode, 2, done.stdout)
        # doctor prints exactly one awareness line and keeps its verdict.
        done = self.engine('doctor', cwd=project, timeout=240)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = [line for line in done.stdout.splitlines() if line.startswith('cli-updates:')]
        self.assertEqual(len(lines), 1, done.stdout)
        # resume clears STOP and shows the awareness line.
        (project / 'coord' / 'STOP').write_text('frozen\n')
        done = self.engine('resume', cwd=project)
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn('STOP cleared', done.stdout)
        lines = [line for line in done.stdout.splitlines() if line.startswith('cli-updates:')]
        self.assertEqual(len(lines), 1, done.stdout)
        # Explicit opt-out makes the awareness silent everywhere.
        (project / 'coord' / 'STOP').write_text('frozen\n')
        done = self.engine('resume', cwd=project,
                           env=dict(self.env, UNIO_CLI_UPDATES_OFF='1'))
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertEqual([line for line in done.stdout.splitlines()
                          if line.startswith('cli-updates:')], [], done.stdout)
        # doctor's machine audit stays untouched output.
        (project / 'coord' / 'agents.conf').write_text('mock=/bin/true\n')
        done = self.engine('doctor', '--commands', '--json', cwd=project)
        self.assertNotIn('cli-updates:', done.stdout)

    def test_help_completion_and_payload_consistency(self):
        self.fresh_fakes()
        (self.fakebin / 'agy').unlink(missing_ok=True)
        done = self.engine('help')
        self.assertIn('update clis [--check] [--json]', done.stdout)
        self.assertIn('docs/CLI-UPDATES.md', done.stdout)
        completion = (self.root / 'completion' / 'unio').read_text()
        self.assertIn('update', completion)
        self.assertIn('clis', completion)
        self.assertEqual((self.conf / 'lib' / 'cli-updates.py').read_bytes(),
                         (SOURCE / 'tools' / 'cli-updates.py').read_bytes(),
                         'the installed payload must be the exact reviewed bytes')
        embed = subprocess.run([sys.executable, '-B', str(SOURCE / 'tools' / 'embed-cli-updates.py'),
                                 '--check'], cwd=SOURCE, capture_output=True, text=True, timeout=60)
        self.assertEqual(embed.returncode, 0, embed.stdout + embed.stderr)
        # No recognized CLI on PATH: the default check is empty and truthful.
        for name in ('agy', 'vibe', 'grok', 'copilot', 'opencode', 'claude', 'codex', 'uv'):
            (self.fakebin / name).unlink(missing_ok=True)
        done = self.engine('update', 'clis', '--check')
        self.assertEqual(done.returncode, 0, done.stdout)
        self.assertIn('no recognized CLI installed', done.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
