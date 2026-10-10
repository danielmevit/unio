#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed managed dashboard: real detached HTTP service; no live AI calls."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import http.client
import http.server
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SOURCE = Path(__file__).resolve().parent.parent
RELEASE_VERSION = re.search(r'^UNIO_VERSION="([^"]+)"$',
                            (SOURCE / 'unio-install.sh').read_text(), re.MULTILINE).group(1)
HELPER = SOURCE / 'tools' / 'runtime' / 'dashboard.py'
BROWSER_FILES = ('server.py', 'readiness.py', 'launcher.py', 'progress.py', 'worker_files.py',
                 'plan_store.py', 'job_store.py', 'execution_service.py', 'index.html',
                 'activity.js', 'activity.css', 'drafts.js', 'jobs.js', 'worker_console.js')
spec = importlib.util.spec_from_file_location('unio_dashboard_helper', HELPER)
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    return helper.start_ticks(pid) is not None


class DashboardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='unio dashboard ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.conf = self.base / 'configuration with spaces'
        self.bin = self.base / 'bin with spaces'
        self.conf.mkdir()
        self.provider_marker = self.base / 'provider unexpectedly called'
        (self.conf / 'agents.conf').write_text('mock=touch ' + shlex.quote(str(self.provider_marker)) + '\n')
        self.opened = self.base / 'opened urls.txt'
        opener = self.base / 'fake opener'
        opener.write_text('#!/bin/sh\nprintf "%s\\n" "$1" >> ' + shlex.quote(str(self.opened)) + '\n')
        opener.chmod(0o755)
        env = {k: v for k, v in os.environ.items()
               if k not in ('DISPLAY', 'WAYLAND_DISPLAY', 'BROWSER', helper.NONCE_ENV)}
        self.env = dict(env, UNIO_BIN_DIR=str(self.bin), UNIO_CONF_DIR=str(self.conf),
                        UNIO_COMPLETION_DIR=str(self.base / 'completion with spaces'),
                        UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0',
                        BROWSER=str(opener))
        installer = self.base / 'standalone installer.sh'
        shutil.copyfile(SOURCE / 'unio-install.sh', installer)
        result = subprocess.run(['bash', str(installer)], cwd=self.base, env=self.env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.installer = installer
        self.engine = self.bin / 'unio'
        self.project = self.make_project('workspace with spaces')
        self.decoy_marker = self.base / 'wrong engine called'
        decoys = self.base / 'decoy bin'
        decoys.mkdir()
        (decoys / 'unio').write_text('#!/bin/sh\ntouch ' + shlex.quote(str(self.decoy_marker)) + '\nexit 93\n')
        (decoys / 'unio').chmod(0o755)
        self.env['PATH'] = str(decoys) + os.pathsep + os.environ['PATH']
        self.pids = set()
        self.addCleanup(self.reap)

    def make_project(self, name):
        project = self.base / name
        for part in ('repo/nested dir', 'coord/tasks', 'wt/example'):
            (project / part).mkdir(parents=True)
        (project / 'coord' / 'STOP').write_text('operator stop\n')
        (project / 'coord' / 'base').write_text('main\n')
        return project

    def reap(self):
        for project in [p for p in self.base.iterdir() if (p / 'coord').is_dir()]:
            subprocess.run([str(self.engine), 'dashboard', 'stop', '--project', str(project)],
                           cwd=self.base, env=self.env, capture_output=True, timeout=40)
        for pid in self.pids:  # Only processes this test itself observed being launched.
            if alive(pid):
                os.kill(pid, signal.SIGKILL)

    def dashboard(self, *args, cwd=None, env=None, code=0, project=None):
        command = [str(self.engine), 'dashboard', *args]
        if project is not False:
            command += ['--project', str(project or self.project)]
        started = time.monotonic()
        # Captured pipes: a detached child holding them would hang this call.
        result = subprocess.run(command, cwd=cwd or self.base, env=env or self.env,
                                capture_output=True, text=True, timeout=40)
        self.assertLess(time.monotonic() - started, 31)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def json_call(self, *args, **kwargs):
        result = self.dashboard(*args, '--json', **kwargs)
        value = json.loads(result.stdout)
        if value.get('pid'):
            self.pids.add(value['pid'])
        return value

    def state(self, project=None):
        return json.loads(((project or self.project) / 'coord/dashboard/state.json').read_text())

    def request(self, port, path, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=10)
        try:
            connection.request('GET', path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def assert_no_dispatch(self):
        self.assertFalse(self.provider_marker.exists())
        self.assertFalse(self.decoy_marker.exists())

    def port(self, url):
        match = re.fullmatch(r'http://127\.0\.0\.1:([0-9]+)', url)
        self.assertIsNotNone(match, url)
        return int(match.group(1))

    @contextmanager
    def foreground(self, *args, env=None):
        log = self.base / ('foreground-' + str(time.monotonic_ns()) + '.log')
        with log.open('w') as output:
            process = subprocess.Popen([str(self.engine), 'browser', '--project', str(self.project), *args],
                                       cwd=self.base, env=env or self.env, stdin=subprocess.DEVNULL,
                                       stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline, match = time.monotonic() + 30, None
            while time.monotonic() < deadline and match is None and process.poll() is None:
                try:
                    match = re.search(r'http://127\.0\.0\.1:(\d+)', log.read_text())
                except OSError:
                    pass  # Some mounts briefly fail reads during a concurrent write.
                time.sleep(0.05)
            self.assertIsNotNone(match, log.read_text())
            yield process, int(match.group(1))
        finally:
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    # ------------------------------------------------------------------ tests
    def test_packaging_is_separate_and_byte_identical(self):
        self.assertEqual((self.conf / 'lib' / 'dashboard.py').read_bytes(), HELPER.read_bytes())
        self.assertEqual(sorted(p.name for p in (self.conf / 'lib' / 'browser').iterdir()), sorted(BROWSER_FILES))
        for name in BROWSER_FILES:
            self.assertEqual((self.conf / 'lib/browser' / name).read_bytes(), (SOURCE / 'bridge' / name).read_bytes())
        subprocess.run(['bash', '-n', str(self.engine)], check=True)
        if shutil.which('shellcheck'):
            subprocess.run(['shellcheck', '-S', 'warning', str(self.engine)], check=True)
        help_text = self.dashboard('--help', project=False).stdout
        self.assertIn('usage: unio dashboard', help_text)
        self.assertIn('ensure', help_text)
        self.assertIn('unio dashboard', subprocess.run([str(self.engine), 'help'], env=self.env,
                                                     capture_output=True, text=True, timeout=30).stdout)

    def test_unsafe_install_destination_refused(self):
        foreign = self.base / 'foreign helper'
        foreign.write_bytes(b'foreign bytes must survive\n')
        target = self.conf / 'lib' / 'dashboard.py'
        target.unlink()
        os.link(foreign, target)
        result = subprocess.run(['bash', str(self.installer)], cwd=self.base, env=self.env,
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 1)
        self.assertIn('refusing unsafe dashboard file', result.stderr)
        self.assertEqual(foreign.read_bytes(), b'foreign bytes must survive\n')

    def test_ensure_http_reuse_and_read_only(self):
        before = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*') if p.is_file()}
        # Inferred from a nested repo directory containing spaces.
        first = self.dashboard(cwd=self.project / 'repo/nested dir', project=False)
        url = re.search(r'http://127\.0\.0\.1:[0-9]+', first.stdout).group(0)
        self.assertIn('Unio dashboard (read-only): ' + url, first.stdout)
        self.assertIn('Started a new managed dashboard for ' + str(self.project), first.stdout)
        record = self.state()
        self.pids.add(record['pid'])
        self.assertEqual(record['status'], 'running')
        self.assertEqual(oct((self.project / 'coord/dashboard').stat().st_mode & 0o777), '0o700')
        self.assertEqual(oct((self.project / 'coord/dashboard/state.json').stat().st_mode & 0o777), '0o600')
        port = self.port(url)
        code, raw = self.request(port, '/api/dashboard')
        self.assertEqual(code, 200)
        document = json.loads(raw)
        self.assertEqual(document, dict(schema_version=1, managed=True, mode='read-only', version=RELEASE_VERSION,
                                        project_hash=helper.project_hash(self.project),
                                        launch_nonce=record['launch_nonce']))
        self.assertNotIn(str(self.project).encode(), raw)
        code, raw = self.request(port, '/api/session')
        self.assertEqual(json.loads(raw), dict(schema_version=1, manual_drafts=False, execution=False,
                                               progress_output=False, worker_files=False, token=None))
        self.assertEqual(self.request(port, '/')[0], 200)
        self.assertEqual(self.request(port, '/api/dashboard', {'Host': 'evil.example'})[0], 403)
        self.assertEqual(self.request(port, '/api/dashboard', {'Origin': 'https://evil.example'})[0], 403)
        # Observer children never inherit the launch nonce.
        environ = Path('/proc/' + str(record['pid']) + '/environ').read_bytes()
        self.assertIn((helper.NONCE_ENV + '=' + record['launch_nonce']).encode(), environ.split(b'\0'))
        for _ in range(3):
            again = self.json_call('ensure', '--open-browser')
            self.assertEqual((again['state'], again['url'], again['pid']), ('reused', url, record['pid']))
            self.assertEqual(again['browser'], 'not_new')
        self.assertFalse(self.opened.exists())
        status = self.json_call('status')
        self.assertEqual((status['state'], status['url'], status['pid']), ('running', url, record['pid']))
        after = {str(p.relative_to(self.project)): p.read_bytes() for p in self.project.rglob('*') if p.is_file()
                 if not str(p.relative_to(self.project)).startswith('coord/dashboard/')}
        self.assertEqual(before, after)  # STOP and every other project file untouched.
        self.assert_no_dispatch()

    def test_open_browser_only_for_new_instance_and_failure_keeps_link(self):
        started = self.json_call('ensure', '--open-browser')
        self.assertEqual((started['state'], started['browser']), ('started', 'opened'))
        self.assertEqual(self.opened.read_text().splitlines(), [started['url']])
        self.json_call('ensure', '--open-browser')
        self.assertEqual(self.opened.read_text().splitlines(), [started['url']])  # no duplicate tab
        self.json_call('stop')
        failing = dict(self.env, BROWSER=str(self.base / 'missing opener'))
        result = self.dashboard('ensure', '--open-browser', env=failing)
        url = re.search(r'http://127\.0\.0\.1:[0-9]+', result.stdout).group(0)
        self.pids.add(self.state()['pid'])
        self.assertIn('No desktop browser could be opened; open the link above manually.', result.stdout)
        self.assertEqual(self.request(self.port(url), '/api/dashboard')[0], 200)
        self.assert_no_dispatch()

    def test_concurrent_ensures_produce_one_server(self):
        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: self.json_call('ensure'), range(5)))
        self.assertEqual(sorted(r['state'] for r in results), ['reused'] * 4 + ['started'])
        self.assertEqual(len({(r['url'], r['pid']) for r in results}), 1)
        self.assertEqual(self.state()['pid'], results[0]['pid'])
        self.assert_no_dispatch()

    def test_status_never_launches(self):
        result = self.dashboard('status', code=3)
        self.assertIn('No managed dashboard is recorded', result.stdout)
        self.assertFalse((self.project / 'coord/dashboard').exists())
        self.assertEqual(self.json_call('status', code=3)['state'], 'none')
        self.assertEqual(self.json_call('stop')['state'], 'none')
        self.assertFalse((self.project / 'coord/dashboard').exists())
        self.assert_no_dispatch()

    def test_stop_then_restart_and_other_project_isolated(self):
        first = self.json_call('ensure')
        other = self.make_project('second workspace')
        second = self.json_call('ensure', project=other)
        self.assertNotEqual(first['url'], second['url'])
        stopped = self.json_call('stop')
        self.assertEqual((stopped['state'], stopped['pid'], stopped['was_healthy']), ('stopped', first['pid'], True))
        self.assertFalse(alive(first['pid']))
        self.assertFalse((self.project / 'coord/dashboard/state.json').exists())
        self.assertTrue((self.project / 'coord/STOP').exists())
        self.assertEqual(self.json_call('status', code=3)['state'], 'none')
        self.assertEqual(self.json_call('status', project=other)['url'], second['url'])
        restarted = self.json_call('ensure')
        self.assertEqual((restarted['state'], restarted['previous']), ('started', 'none'))
        self.assertNotEqual(restarted['pid'], first['pid'])
        self.assert_no_dispatch()

    def test_stale_and_reused_pid_never_signalled(self):
        first = self.json_call('ensure')
        os.kill(first['pid'], signal.SIGKILL)  # This test launched it; simulate a crash.
        deadline = time.monotonic() + 10
        while alive(first['pid']) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(self.json_call('status', code=3)['state'], 'stale')
        restarted = self.json_call('ensure')
        self.assertEqual((restarted['state'], restarted['previous']), ('started', 'stale'))
        self.json_call('stop')
        # A live unrelated process occupies the recorded PID, with and without matching start time.
        bystander = subprocess.Popen(['sleep', '60'], start_new_session=True)
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)
        record = dict(schema_version=1, status='running', project_hash=helper.project_hash(self.project),
                      launch_nonce='a' * 32, pid=bystander.pid, boot_id=helper.boot_id(), start_ticks=0,
                      port=1, version='0.5.7', started_at='2026-10-09T00:00:00Z', reason=None)
        for ticks in (0, helper.start_ticks(bystander.pid)):
            with self.subTest(ticks=ticks):
                record['start_ticks'] = ticks
                (self.project / 'coord/dashboard/state.json').write_text(json.dumps(record))
                self.assertEqual(self.json_call('status', code=3)['state'], 'stale')
                self.assertEqual(self.json_call('stop')['state'], 'stale')
                self.assertIsNone(bystander.poll())
        self.assert_no_dispatch()

    def test_foreign_and_foreground_servers_are_not_adopted(self):
        with self.foreground() as (process, port):
            self.assertEqual(self.request(port, '/api/dashboard')[0], 404)
            record = dict(schema_version=1, status='running', project_hash=helper.project_hash(self.project),
                          launch_nonce='b' * 32, pid=process.pid, boot_id=helper.boot_id(),
                          start_ticks=helper.start_ticks(process.pid), port=port, version='0.5.7',
                          started_at='2026-10-09T00:00:00Z', reason=None)
            (self.project / 'coord/dashboard').mkdir(mode=0o700)
            (self.project / 'coord/dashboard/state.json').write_text(json.dumps(record))
            self.assertEqual(self.json_call('status', code=3)['state'], 'stale')
            self.assertEqual(self.json_call('stop')['state'], 'stale')
            (self.project / 'coord/dashboard/state.json').write_text(json.dumps(record))
            started = self.json_call('ensure')
            self.assertEqual((started['state'], started['previous']), ('started', 'stale'))
            self.assertNotEqual(self.port(started['url']), port)
            self.assertIsNone(process.poll())
            self.assertEqual(self.request(port, '/api/session')[0], 200)
        # A nonce in a foreground environment never turns explicit grants into a managed view.
        granted = dict(self.env, **{helper.NONCE_ENV: 'c' * 32})
        with self.foreground('--enable-plan-drafts', env=granted) as (_, port):
            self.assertEqual(self.request(port, '/api/dashboard')[0], 404)
        self.assert_no_dispatch()

    def test_health_refuses_foreign_metadata(self):
        expected = helper.project_hash(self.project)
        good = dict(schema_version=1, managed=True, mode='read-only', version='0.5.7',
                    project_hash=expected, launch_nonce='d' * 32)
        variants = [good, dict(good, launch_nonce='e' * 32), dict(good, managed=False),
                    dict(good, mode='execution'), dict(good, project_hash='f' * 64), dict(good, token='x'),
                    'x' * 5000]
        current = {}

        class Foreign(http.server.BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_GET(self):
                body = json.dumps(current['value']).encode()
                self.send_response(200)
                self.send_header('Content-Length', str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Foreign)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        results = []
        for value in variants:
            current['value'] = value
            results.append(helper.health(server.server_port, expected, 'd' * 32) is not None)
        self.assertEqual(results, [True] + [False] * (len(variants) - 1))

    def test_corrupt_and_unsafe_state_refused(self):
        directory = self.project / 'coord/dashboard'
        outside = self.base / 'outside state'
        outside.write_text('{}')
        cases = ('garbage', 'duplicate', 'oversized', 'other-project', 'symlink', 'hardlink', 'fifo',
                 'directory', 'dir-symlink')
        for kind in cases:
            with self.subTest(kind=kind):
                shutil.rmtree(directory, ignore_errors=True)
                if directory.is_symlink():
                    directory.unlink()
                directory.mkdir(mode=0o700)
                state = directory / 'state.json'
                if kind == 'garbage':
                    state.write_text('not json')
                elif kind == 'duplicate':
                    state.write_text('{"schema_version": 1, "schema_version": 1}')
                elif kind == 'oversized':
                    state.write_text(' ' * 5000)
                elif kind == 'other-project':
                    record = dict(schema_version=1, status='failed', project_hash='0' * 64, launch_nonce='a' * 32,
                                  pid=2, boot_id=helper.boot_id(), start_ticks=0, port=None, version='0.5.7',
                                  started_at='x', reason='readiness_timeout')
                    state.write_text(json.dumps(record))
                elif kind == 'symlink':
                    state.symlink_to(outside)
                elif kind == 'hardlink':
                    os.link(outside, state)
                elif kind == 'fifo':
                    os.mkfifo(state)
                elif kind == 'directory':
                    state.mkdir()
                else:
                    directory.rmdir()
                    elsewhere = self.base / 'elsewhere dir'
                    elsewhere.mkdir(exist_ok=True)
                    directory.symlink_to(elsewhere, target_is_directory=True)
                for action in ('status', 'ensure', 'stop'):
                    value = self.json_call(action, code=1)
                    self.assertEqual(value['state'], 'unsafe', (action, value))
                    self.assertNotIn('url', value)
                self.assertEqual(outside.read_text(), '{}')
                if kind == 'dir-symlink':
                    self.assertEqual(list((self.base / 'elsewhere dir').iterdir()), [])
                    directory.unlink()
                else:
                    self.assertFalse((directory / 'server.log').exists())
        self.assert_no_dispatch()

    def test_readiness_failure_cleans_only_owned_child(self):
        launcher = self.conf / 'lib/browser/launcher.py'
        original = launcher.read_bytes()
        launcher.write_text('import sys\nprint("broken launch", flush=True)\nsys.exit(5)\n')
        result = self.dashboard('ensure', code=1)
        self.assertIn('did not become ready (exited_before_ready)', result.stderr)
        record = self.state()
        self.assertEqual((record['status'], record['reason']), ('failed', 'exited_before_ready'))
        self.assertIn('broken launch', (self.project / 'coord/dashboard/server.log').read_text())
        status = self.json_call('status', code=3)
        self.assertEqual((status['state'], status['reason']), ('failed', 'exited_before_ready'))
        # A silent hung launch is killed at the readiness deadline, process group included.
        launcher.write_text('import os, subprocess, time\n'
                            'child = subprocess.Popen(["sleep", "300"])\n'
                            'print("hung child", child.pid, flush=True)\ntime.sleep(300)\n')
        started = time.monotonic()
        result = self.dashboard('ensure', code=1)
        self.assertLess(time.monotonic() - started, 31)
        self.assertIn('readiness_timeout', result.stderr)
        record = self.state()
        self.assertFalse(alive(record['pid']))
        grandchild = int(re.search(r'hung child (\d+)', (self.project / 'coord/dashboard/server.log').read_text()).group(1))
        deadline = time.monotonic() + 5
        while alive(grandchild) and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertFalse(alive(grandchild))
        launcher.write_bytes(original)
        recovered = self.json_call('ensure')
        self.assertEqual((recovered['state'], recovered['previous']), ('started', 'failed'))
        self.assert_no_dispatch()

    def test_invalid_invocations(self):
        self.dashboard('status', '--open-browser', code=2)
        self.dashboard('restart', code=2)
        result = self.dashboard(cwd=Path('/'), project=False, code=2)
        self.assertIn('pass --project PATH', result.stderr)
        link = self.base / 'linked workspace'
        link.symlink_to(self.project, target_is_directory=True)
        self.assertIn('real enclosing Unio workspace', self.dashboard(project=link, code=2).stderr)
        self.assertFalse((self.project / 'coord/dashboard').exists())
        self.assert_no_dispatch()


if __name__ == '__main__':
    if sys.platform != 'linux':
        raise SystemExit('unio dashboard tests require Linux /proc')
    unittest.main(verbosity=2)
