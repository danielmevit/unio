# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Focused checks for the read-only /api/limits view; only a deterministic fake CLI runs."""
import http.client
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import textwrap
import threading
import time
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('activity_server', Path(__file__).parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)

SECRET = 'secret.person@example.com sk-live-TOPSECRET'

# The fake logs argv and cwd, then answers from FAKE_LIMITS (JSON:
# section -> {"exit", "stdout" (object or raw string), "sleep", "flood"}).
FAKE = textwrap.dedent('''\
    #!/usr/bin/env python3
    import json, os, sys, time
    with open(os.environ['FAKE_LIMITS_LOG'], 'a') as log:
        log.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd()}) + '\\n')
    args = sys.argv[1:]
    key = 'policy' if args[:1] == ['policy'] else 'codex' if '--provider' in args else 'manual'
    plan = json.load(open(os.environ['FAKE_LIMITS']))[key]
    sys.stderr.write('debug token sk-live-TOPSECRET for secret.person@example.com\\n')
    time.sleep(plan.get('sleep', 0))
    if plan.get('flood'):
        sys.stdout.write('x' * plan['flood']); sys.stdout.flush()
    out = plan.get('stdout', '')
    sys.stdout.write(out if isinstance(out, str) else json.dumps(out))
    sys.exit(plan.get('exit', 0))
    ''')

NOW = '2026-10-09T16:00:00+00:00'
POLICY = {'schema_version': 1, 'mode': 'yolo', 'tier': 'low', 'lead_agent': 'codex', 'lead_group': 'codex',
          'accounts': {'codex-reviewer': 'codex'}, 'active_native_workflows': {'claude': 1},
          'active_with_lead': {'claude': 1, 'codex': 1}, 'capacity': 'unknown',
          'workflow_enforcement': 'native_workflows', 'workflow_limit_per_group': 1,
          'updated_at': NOW, 'owner_email': SECRET}


def manual_window(**extra):
    window = {'source': 'manual', 'window_minutes': 300, 'observed_at': NOW, 'age_seconds': 60.0,
              'reset_at': '2026-10-09T19:00:00+00:00', 'status': 'fresh',
              'last_reading_remaining_percent': 42, 'usable_remaining_percent': 42}
    window.update(extra)
    return window


MANUAL = {'schema_version': 1, 'checked_at': NOW, 'max_age_seconds': 900, 'state': 'ok', 'error': '/private/path',
          'groups': {'claude': {'status': 'recorded', 'windows': {
              'five-hour': manual_window(),
              'weekly': manual_window(window_minutes=10080, observed_at='2026-10-09T15:00:00+00:00',
                                      age_seconds=3600.0, status='stale', last_reading_remaining_percent=80,
                                      usable_remaining_percent=None, reset_at=None)}}}}


def codex_window(**extra):
    window = {'status': 'fresh', 'window_minutes': 300, 'reset_at': '2026-10-09T18:00:00+00:00',
              'last_reading_remaining_percent': 69.0, 'usable_remaining_percent': 69.0}
    window.update(extra)
    return window


CODEX = {'schema_version': 1, 'provider': 'codex', 'checked_at': NOW, 'max_age_seconds': 900, 'state': 'ok',
         'error': None, 'groups': {'codex': {
             'source': 'codex', 'state': 'ok', 'reason': None, 'attempted_at': NOW, 'account_kind': 'chatgpt',
             'observed_at': NOW, 'age_seconds': 5.0, 'freshness': 'fresh', 'email': SECRET,
             'buckets': {'codex': {'status': 'ok', 'reason': None, 'windows': {
                 'primary': codex_window(),
                 'secondary': codex_window(window_minutes=10080, reset_at='2026-10-14T00:00:00+00:00',
                                           last_reading_remaining_percent=12.5, usable_remaining_percent=12.5)}}},
             'last_good': None}}}


class LimitsApi(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix='unio-limits-', dir=os.environ.get('TMPDIR'))
        self.project = Path(self.root, 'workspace')
        for part in ('repo', 'coord', 'wt'):
            (self.project / part).mkdir(parents=True)
        self.engine = Path(self.root, 'fake-unio')
        self.engine.write_text(FAKE)
        self.engine.chmod(0o755)
        self.log = Path(self.root, 'log')
        self.plan = Path(self.root, 'plan.json')
        os.environ['FAKE_LIMITS_LOG'] = str(self.log)
        os.environ['FAKE_LIMITS'] = str(self.plan)
        self.script(policy={'stdout': POLICY}, manual={'stdout': MANUAL}, codex={'stdout': CODEX})
        self.limits = server.LimitsObserver(self.project, self.engine, timeout=5)
        observer = Mock()
        observer.read.return_value = None
        self.server = server.ActivityServer(0, observer, limits=self.limits)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        shutil.rmtree(self.root)

    def script(self, **sections):
        self.plan.write_text(json.dumps(sections))

    def calls(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def request(self, method='GET', path='/api/limits', headers=None, body=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=30)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        connection.close()
        return response.status, raw

    def view(self):
        status, raw = self.request()
        self.assertEqual(status, 200)
        self.assertNotIn(b'TOPSECRET', raw)
        self.assertNotIn(b'secret.person', raw)
        self.assertNotIn(b'/private/path', raw)
        return json.loads(raw)

    def fresh(self):
        self.limits.expires = 0

    def test_authentication_uses_only_private_cache_and_adds_no_cli_call(self):
        spec = importlib.util.spec_from_file_location('test_readiness_store',
                                                     Path(__file__).parents[1] / 'readiness.py')
        readiness = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(readiness)
        self.assertEqual(self.view()['authentication']['state'], 'missing')
        store = readiness.ReadinessStore(self.project)
        store.record_good('claude', 'native', True, auth_method='claude.ai')
        self.fresh()
        authentication = self.view()['authentication']['agents']['claude']
        self.assertEqual(authentication['authentication'], 'signed_in')
        self.assertEqual(authentication['capacity'], 'unknown')
        self.assertEqual(authentication['dispatch_readiness'], 'unknown')
        self.assertEqual(len(self.calls()), 6)
        self.assertTrue(all(call['argv'][0] in ('policy', 'capacity') for call in self.calls()))
        (self.project / 'coord/readiness/observations.json').chmod(0o644)
        self.fresh()
        self.assertEqual(self.view()['authentication'], {'state': 'unknown'})
        self.assertEqual(len(self.calls()), 9)

    def test_fresh_manual_codex_multiwindow_and_shared_group(self):
        view = self.view()
        policy = view['policy']
        self.assertEqual((policy['mode'], policy['tier'], policy['lead_agent'], policy['lead_group']),
                         ('yolo', 'low', 'codex', 'codex'))
        self.assertEqual(policy['accounts'], {'codex-reviewer': 'codex'})
        self.assertNotIn('owner_email', policy)
        manual = view['manual']['groups']['claude']['windows']
        self.assertEqual((manual['five-hour']['status'], manual['five-hour']['usable_remaining_percent'],
                          manual['five-hour']['source']), ('fresh', 42, 'manual'))
        self.assertEqual((manual['weekly']['status'], manual['weekly']['usable_remaining_percent'],
                          manual['weekly']['remaining_percent']), ('stale', None, 80))
        group = view['codex']['groups']['codex']
        self.assertNotIn('email', group)
        self.assertNotIn('account_kind', group)
        windows = group['buckets']['codex']['windows']
        self.assertEqual([(w['window_minutes'], w['usable_remaining_percent'], w['source'], w['age_seconds'])
                          for w in (windows['primary'], windows['secondary'])],
                         [(300, 69.0, 'codex', 5.0), (10080, 12.5, 'codex', 5.0)])

    def test_only_the_fixed_reads_run_and_are_cached(self):
        for _ in range(4):
            self.view()
        calls = self.calls()
        self.assertEqual([c['argv'] for c in calls], [
            ['policy', '--json'],
            ['capacity', '--project', str(self.project), 'show', '--json'],
            ['capacity', '--project', str(self.project), 'show', '--provider', 'codex', '--json']])
        self.assertTrue(all(c['cwd'] == str(self.project / 'repo') for c in calls))
        self.assertGreaterEqual(self.limits.ttl, 5)
        self.fresh()
        self.view()
        self.assertEqual(len(self.calls()), 6)

    def test_stale_expired_missing_invalid_stay_unknown(self):
        expired = codex_window(status='expired', usable_remaining_percent=None)
        forged_usable = codex_window(status='stale')  # a usable value outside fresh is refused
        out_of_range = codex_window(last_reading_remaining_percent=150.0, usable_remaining_percent=150.0)
        codex = json.loads(json.dumps(CODEX))
        codex['groups']['codex']['buckets']['codex']['windows'] = {'primary': expired, 'secondary': forged_usable}
        codex['groups']['other'] = dict(codex['groups']['codex'], buckets={'b': {'status': 'ok', 'reason': None,
                                        'windows': {'primary': out_of_range, 'secondary': None}}})
        codex['groups']['gone'] = {'source': 'codex', 'state': 'unknown', 'reason': 'not_signed_in',
                                   'attempted_at': NOW, 'account_kind': None, 'observed_at': None,
                                   'age_seconds': None, 'freshness': 'unknown', 'buckets': {},
                                   'last_good': {'historical': True, 'observed_at': NOW, 'age_seconds': 99.0,
                                                 'buckets': {'codex': {'status': 'ok', 'reason': None, 'windows': {
                                                     'primary': codex_window(status='historical',
                                                                             usable_remaining_percent=None),
                                                     'secondary': None}}}}}
        manual = json.loads(json.dumps(MANUAL))
        manual['groups']['claude']['windows']['five-hour']['last_reading_remaining_percent'] = -1
        self.script(policy={'stdout': POLICY}, manual={'stdout': manual}, codex={'stdout': codex})
        view = self.view()
        windows = view['codex']['groups']['codex']['buckets']['codex']['windows']
        self.assertEqual((windows['primary']['status'], windows['primary']['usable_remaining_percent']),
                         ('expired', None))
        self.assertEqual(windows['secondary'], {'status': 'invalid', 'source': 'codex'})
        self.assertEqual(view['codex']['groups']['other']['buckets']['b']['windows']['primary'],
                         {'status': 'invalid', 'source': 'codex'})
        gone = view['codex']['groups']['gone']
        self.assertEqual((gone['state'], gone['reason'], gone['buckets']), ('unknown', 'not_signed_in', {}))
        historical = gone['last_good']['buckets']['codex']['windows']['primary']
        self.assertEqual((historical['status'], historical['usable_remaining_percent']), ('historical', None))
        self.assertEqual(view['manual']['groups']['claude']['windows']['five-hour'],
                         {'status': 'invalid', 'source': 'manual'})

    def test_unsupported_and_malformed_reads_are_unknown_not_errors(self):
        cases = {
            'old_command': dict(policy={'exit': 2, 'stdout': 'usage'}, manual={'exit': 1}, codex={'exit': 1}),
            'not_json': dict(policy={'stdout': '{bad'}, manual={'stdout': 'NaN'}, codex={'stdout': '[]'}),
            'duplicate_keys': dict(policy={'stdout': '{"schema_version": 1, "schema_version": 1}'},
                                   manual={'stdout': {'schema_version': 2}}, codex={'stdout': {'provider': 'x'}}),
            'bad_labels': dict(policy={'stdout': dict(POLICY, lead_agent='$(id)')},
                               manual={'stdout': dict(MANUAL, groups={'../x': {'windows': {}}})},
                               codex={'stdout': dict(CODEX, provider='claude')}),
            'flood': dict(policy={'flood': server.LIMITS_MAX_OUTPUT + 10}, manual={'exit': 1}, codex={'exit': 1}),
        }
        for name, plan in cases.items():
            with self.subTest(case=name):
                self.script(**plan)
                self.fresh()
                view = self.view()
                self.assertEqual([view[k] for k in ('policy', 'manual', 'codex')], [{'state': 'unknown'}] * 3)

    def test_deadline_bounds_a_hanging_read(self):
        self.limits.timeout = 0.5
        self.script(policy={'sleep': 30, 'stdout': POLICY}, manual={'stdout': MANUAL}, codex={'stdout': CODEX})
        started = time.monotonic()
        view = self.view()
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(view['policy'], {'state': 'unknown'})
        self.assertEqual(view['manual']['state'], 'ok')

    def test_malformed_nested_metadata_is_unknown_without_a_server_error(self):
        # These inputs crashed the observer or accepted an impossible date at
        # 1c953c2. They must produce bounded Unknown JSON, not an HTTP disconnect.
        nested = json.loads(json.dumps(CODEX))
        nested['groups']['codex']['buckets']['codex']['windows']['primary'] = 17
        reason = json.loads(json.dumps(CODEX))
        reason['groups']['codex']['reason'] = []
        integer = json.loads(json.dumps(CODEX))
        integer['groups']['codex']['age_seconds'] = 10 ** 500
        cases = [
            dict(policy={'exit': 2}, manual={'exit': 2}, codex={'stdout': nested}),
            dict(policy={'exit': 2}, manual={'exit': 2}, codex={'stdout': reason}),
            dict(policy={'exit': 2}, manual={'exit': 2}, codex={'stdout': integer}),
            dict(policy={'exit': 2}, manual={'stdout': dict(MANUAL, checked_at='2026-99-99T12:00:00Z')}, codex={'exit': 2}),
            dict(policy={'stdout': dict(POLICY, schema_version=True)}, manual={'exit': 2}, codex={'exit': 2}),
        ]
        for plan in cases:
            with self.subTest(plan=list(plan)):
                self.script(**plan)
                self.fresh()
                view = self.view()
                self.assertEqual([view[k] for k in ('policy', 'manual', 'codex')], [{'state': 'unknown'}] * 3)

    def test_no_injection_cross_origin_or_writes(self):
        origin = '127.0.0.1:' + str(self.server.server_port)
        for method, path, headers, body in (
                ('GET', '/api/limits', {'Host': 'evil.example'}, None),
                ('GET', '/api/limits', {'Origin': 'http://evil.example'}, None),
                ('GET', '/api/limits?command=rm', {}, None),
                ('GET', '/api/limits/../../etc', {}, None),
                ('GET', '/api/limits', {'Content-Length': '2'}, b'{}'),
                ('POST', '/api/limits', {'Content-Type': 'application/json'}, b'{"refresh": true}'),
                ('PUT', '/api/limits', {}, b'x'), ('DELETE', '/api/limits', {}, None)):
            with self.subTest(method=method, path=path, headers=headers):
                status, raw = self.request(method, path, headers, body)
                self.assertIn(status, (400, 403, 404, 405))
                self.assertNotIn(b'TOPSECRET', raw)
        self.assertEqual(self.calls(), [])
        status, _ = self.request(headers={'Host': origin, 'Origin': 'http://' + origin})
        self.assertEqual(status, 200)
        self.assertEqual(len(self.calls()), 3)

    def test_server_without_limits_observer_reports_unknown(self):
        self.server.limits = None
        view = self.view()
        self.assertEqual([view[k] for k in ('policy', 'manual', 'codex')], [{'state': 'unknown'}] * 3)
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main(verbosity=1)
