# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
import concurrent.futures
import copy
import http.client
import importlib.util
import json
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

spec = importlib.util.spec_from_file_location('activity_server', Path(__file__).parents[1] / 'server.py')
server = importlib.util.module_from_spec(spec)
spec.loader.exec_module(server)


def sample():
    return dict(schema_version=1, observed_at='2026-10-04T21:00:00Z', stopped=True,
                agents=[], results=[], retries=[], recent_events=[], warnings=[],
                evidence='recorded; use result to recheck revision and readiness')


class ObserverTests(unittest.TestCase):
    def observer(self):
        return server.Observer(Path('/fixed/workspace'), Path('/fixed/engine'), timeout=3)

    def test_default_budget_allows_a_slow_valid_workspace_scan(self):
        def scan(*args, **kwargs):
            if kwargs['timeout'] < 15:
                raise subprocess.TimeoutExpired('/fixed/engine', kwargs['timeout'])
            return subprocess.CompletedProcess([], 0, json.dumps(sample()).encode())
        with patch.object(server.subprocess, 'run', side_effect=scan):
            default = server.Observer(Path('/fixed/workspace'), Path('/fixed/engine'))
            self.assertIsNotNone(default.read())
            self.assertIsNone(self.observer().read())

    def test_invalid_budget_rejects_before_any_observation_or_server(self):
        for value in (0, -1, 121, True, None, 'bad', float('nan'), float('inf')):
            with self.subTest(value=value), patch.object(server.subprocess, 'run') as invoke:
                with self.assertRaises(server.argparse.ArgumentTypeError):
                    server.Observer(Path('/fixed/workspace'), Path('/fixed/engine'), timeout=value)
                invoke.assert_not_called()
        for value in ('0', '-1', '121', 'nan', 'inf', 'bad'):
            with self.subTest(cli=value), patch.object(sys, 'argv', ['server.py', '--project', '/missing', '--observer-timeout', value]), \
                 patch.object(sys, 'stderr', io.StringIO()), patch.object(server, 'ActivityServer') as build:
                with self.assertRaises(SystemExit) as failure:
                    server.main()
                self.assertEqual(failure.exception.code, 2)
                build.assert_not_called()

    def test_fixed_read_only_command_and_cache(self):
        observer = self.observer()
        document = sample(); document['raw_log'] = 'PRIVATE OMIT'
        process = subprocess.CompletedProcess([], 0, json.dumps(document).encode(), b'PRIVATE STDERR')
        with patch.object(server.subprocess, 'run', return_value=process) as invoke:
            with concurrent.futures.ThreadPoolExecutor(max_workers=8) as workers:
                values = list(workers.map(lambda _: observer.read(), range(8)))
        self.assertEqual(invoke.call_count, 1)
        args, options = invoke.call_args
        self.assertEqual(args, (['/fixed/engine', 'watch', '--once', '--json'],))
        self.assertEqual(options['cwd'], Path('/fixed/workspace/repo'))
        self.assertEqual(options['stdin'], subprocess.DEVNULL)
        self.assertEqual(options['timeout'], 3)
        self.assertTrue(options['capture_output'])
        self.assertNotIn('shell', options)
        self.assertNotIn('raw_log', values[0])
        self.assertTrue(all(value == values[0] for value in values))

    def test_failed_observation_clears_cached_success(self):
        observer = self.observer()
        with patch.object(server.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, json.dumps(sample()).encode())):
            self.assertIsNotNone(observer.read())
        observer.expires = 0
        with patch.object(server.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, b'PRIVATE STDOUT', b'PRIVATE STDERR')) as invoke:
            self.assertIsNone(observer.read())
            self.assertIsNone(observer.read())
            self.assertEqual(invoke.call_count, 1)

    def test_invalid_or_unavailable_engine_fails_closed(self):
        bad = [b'not json', b'[]', b'{}', json.dumps({**sample(), 'schema_version': True}).encode(),
               json.dumps({**sample(), 'schema_version': 2}).encode(),
               json.dumps({**sample(), 'results': {}}).encode(), b'x' * (8 * 1024 * 1024 + 1)]
        for output in bad:
            with self.subTest(output=output[:50]):
                with patch.object(server.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output)):
                    self.assertIsNone(self.observer().read())
        for exception in (OSError('PRIVATE PATH'), subprocess.TimeoutExpired('/fixed/engine', 3)):
            with self.subTest(exception=type(exception).__name__):
                with patch.object(server.subprocess, 'run', side_effect=exception):
                    self.assertIsNone(self.observer().read())


class StubObserver:
    def __init__(self):
        self.calls = 0
        self.value = sample()

    def read(self):
        self.calls += 1
        return copy.deepcopy(self.value)


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.observer = StubObserver()
        self.server = server.ActivityServer(0, self.observer)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close)

    def close(self):
        self.server.shutdown()
        self.thread.join(timeout=2)
        self.server.server_close()

    def request(self, method='GET', path='/api/activity', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=3)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, dict(response.getheaders()), response.read()
        finally:
            connection.close()

    def test_activity_and_assets_are_loopback_only(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        code, headers, body = self.request(headers={'Origin': self.server.origin})
        self.assertEqual(code, 200)
        self.assertEqual(json.loads(body), sample())
        self.assertEqual(headers['Cache-Control'], 'no-store')
        self.assertEqual(headers['X-Content-Type-Options'], 'nosniff')
        self.assertIn("frame-ancestors 'none'", headers['Content-Security-Policy'])
        self.assertNotIn('Access-Control-Allow-Origin', headers)
        for path, kind in (('/', 'text/html'), ('/activity.js', 'text/javascript'), ('/drafts.js', 'text/javascript'),
                           ('/worker_console.js', 'text/javascript'), ('/activity.css', 'text/css'),
                           ('/theme.js', 'text/javascript')):
            with self.subTest(path=path):
                code, headers, body = self.request(path=path)
                self.assertEqual(code, 200)
                self.assertTrue(headers['Content-Type'].startswith(kind))
                self.assertTrue(body)
        self.assertEqual(self.observer.calls, 1)

    def test_remote_host_origin_and_request_paths_never_observe(self):
        for headers in ({'Host': 'evil.example'}, {'Host': 'localhost:' + str(self.server.server_port)},
                        {'Origin': 'https://evil.example'}, {'Origin': 'null'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(headers=headers)[0], 403)
        for path in ('/api/activity?engine=evil', '/api/run', '/server.py', '/../server.py', '/%2e%2e/coord/AGENT-LOG.md'):
            with self.subTest(path=path):
                self.assertEqual(self.request(path=path)[0], 404)
        self.assertEqual(self.observer.calls, 0)

    def test_mutating_methods_are_refused_without_observation(self):
        for method in ('POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'HEAD'):
            with self.subTest(method=method):
                self.assertEqual(self.request(method=method)[0], 405)
        self.assertEqual(self.observer.calls, 0)

    def test_unavailable_observation_has_no_stale_or_raw_payload(self):
        self.assertEqual(self.request()[0], 200)
        self.observer.value = None
        code, _, body = self.request()
        self.assertEqual(code, 503)
        self.assertEqual(json.loads(body), dict(schema_version=1, error='activity_unavailable'))
        self.assertNotIn(b'observed_at', body)

    def test_foreground_has_no_managed_dashboard_metadata(self):
        self.assertEqual(self.request(path='/api/dashboard')[0], 404)
        self.server.dashboard = dict(schema_version=1, managed=True, mode='read-only', version='0.5.6',
                                     project_hash='a' * 64, launch_nonce='b' * 32)
        code, _, body = self.request(path='/api/dashboard')
        self.assertEqual((code, json.loads(body)), (200, self.server.dashboard))
        for headers in ({'Host': 'evil.example'}, {'Origin': 'https://evil.example'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request(path='/api/dashboard', headers=headers)[0], 403)
        self.assertEqual(self.request(method='POST', path='/api/dashboard')[0], 405)
        self.assertEqual(self.observer.calls, 0)


class ManagedDashboardTests(unittest.TestCase):
    def test_metadata_only_for_valid_read_only_managed_launch(self):
        project = Path('/fixed/workspace with spaces')
        plain = Mock(plans=None, execution=None, progress=None, files=None)
        value = server.managed_dashboard('c' * 32, plain, project, '0.5.6')
        self.assertEqual(set(value), {'schema_version', 'managed', 'mode', 'version', 'project_hash', 'launch_nonce'})
        self.assertEqual(value['project_hash'], server.hashlib.sha256(str(project).encode()).hexdigest())
        self.assertNotIn(str(project), json.dumps(value))
        for launch, version in ((None, '0.5.6'), ('C' * 32, '0.5.6'), ('c' * 31, '0.5.6'), ('c' * 32, None),
                                ('c' * 32, 'bad version\n')):
            with self.subTest(launch=launch, version=version):
                self.assertIsNone(server.managed_dashboard(launch, plain, project, version))
        for grant in ('plans', 'execution', 'progress', 'files'):
            with self.subTest(grant=grant):
                granted = Mock(plans=None, execution=None, progress=None, files=None)
                setattr(granted, grant, object())
                self.assertIsNone(server.managed_dashboard('c' * 32, granted, project, '0.5.6'))

    def test_launch_nonce_is_removed_before_observer_children(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory).resolve()
            for part in ('repo', 'coord', 'wt'):
                (workspace / part).mkdir()
            (workspace / 'coord' / 'agents.conf').write_text('')
            engine = workspace / 'engine'
            engine.write_text('#!/bin/sh\n')
            captured = []
            with patch.dict(server.os.environ, {server.DASHBOARD_LAUNCH: 'd' * 32}), \
                 patch.object(server, 'serve_preview', side_effect=lambda s, _: captured.append(s)), \
                 patch('builtins.print'):
                server.main([], engine_override=engine, project_default=workspace, installed_version='0.5.6')
                self.assertNotIn(server.DASHBOARD_LAUNCH, server.os.environ)
            captured[0].server_close()
            self.assertEqual(captured[0].dashboard['launch_nonce'], 'd' * 32)
            with patch.dict(server.os.environ, {server.DASHBOARD_LAUNCH: 'd' * 32}), \
                 patch.object(server, 'serve_preview', side_effect=lambda s, _: captured.append(s)), \
                 patch('builtins.print'):
                server.main(['--project', str(workspace), '--engine', str(engine)])
            captured[1].server_close()
            self.assertIsNone(captured[1].dashboard)  # Source launches have no installed version.


class PreviewLaunchTests(unittest.TestCase):
    def test_default_does_not_open_browser(self):
        preview = Mock(origin='http://127.0.0.1:12345')
        with patch.object(server.webbrowser, 'open') as opener, patch('builtins.print'):
            server.serve_preview(preview)
        opener.assert_not_called()
        preview.serve_forever.assert_called_once_with()
        preview.server_close.assert_called_once_with()

    def test_opt_in_opens_only_fixed_bound_origin(self):
        preview = Mock(origin='http://127.0.0.1:12345')
        opened = threading.Event()
        def opener(origin, new):
            self.assertEqual(origin, preview.origin)
            self.assertEqual(new, 2)
            opened.set()
            return True
        preview.serve_forever.side_effect = lambda: self.assertTrue(opened.wait(1))
        with patch.object(server.webbrowser, 'open', side_effect=opener) as launch, patch('builtins.print'):
            server.serve_preview(preview, open_browser=True)
        launch.assert_called_once_with(preview.origin, new=2)
        preview.server_close.assert_called_once_with()

    def test_browser_failures_leave_manual_url(self):
        for exception in (None, server.webbrowser.Error('unconfigured browser'), OSError('missing browser')):
            with self.subTest(exception=exception):
                with patch.object(server.webbrowser, 'open', return_value=False, side_effect=exception), patch('builtins.print') as output:
                    server.open_preview('http://127.0.0.1:12345')
                self.assertIn('Open http://127.0.0.1:12345 manually', output.call_args.args[0])

    def test_slow_opener_does_not_block_service_or_shutdown(self):
        preview = Mock(origin='http://127.0.0.1:12345')
        started, release = threading.Event(), threading.Event()
        def slow_opener(*args, **kwargs):
            started.set()
            release.wait(2)
            return True
        try:
            with patch.object(server.webbrowser, 'open', side_effect=slow_opener), patch('builtins.print'):
                preview.serve_forever.side_effect = lambda: self.assertTrue(started.wait(1))
                server.serve_preview(preview, open_browser=True)
                self.assertFalse(release.is_set())
                preview.server_close.assert_called_once_with()
        finally:
            release.set()


class EngineSelectionTests(unittest.TestCase):
    def test_default_engine_is_unio_on_path(self):
        with tempfile.TemporaryDirectory() as directory:
            unio = Path(directory) / 'unio'
            unio.write_text('#!/bin/sh\n', encoding='utf-8')
            with patch.object(server.shutil, 'which', return_value=str(unio)) as which:
                self.assertEqual(server.resolve_engine(None), unio.absolute())
            which.assert_called_once_with('unio')

    def test_explicit_engine_overrides_the_unio_default(self):
        with tempfile.TemporaryDirectory() as directory:
            other = Path(directory) / 'other'
            other.write_text('#!/bin/sh\n', encoding='utf-8')
            with patch.object(server.shutil, 'which') as which:
                self.assertEqual(server.resolve_engine(other), other.absolute())
            which.assert_not_called()

    def test_missing_unio_default_names_the_override(self):
        with patch.object(server.shutil, 'which', return_value=None):
            with self.assertRaises(ValueError) as raised:
                server.resolve_engine(None)
        self.assertIn('pass --engine', str(raised.exception))

    def test_missing_explicit_engine_is_rejected(self):
        missing = Path('/no/such/unio-engine')
        with patch.object(server.shutil, 'which') as which:
            with self.assertRaises(ValueError) as raised:
                server.resolve_engine(missing)
        which.assert_not_called()
        self.assertEqual(str(raised.exception), 'engine executable not found')


if __name__ == '__main__':
    unittest.main(verbosity=2)
