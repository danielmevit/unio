#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Standalone browser packaging and real HTTP startup; no live AI calls."""
from contextlib import contextmanager
import hashlib
import http.client
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parent.parent
# The fixed browser payload; capacity.py is packaged separately (embed-capacity.py).
BROWSER_FILES = ('server.py', 'readiness.py', 'launcher.py', 'progress.py', 'worker_files.py',
                 'plan_store.py', 'job_store.py', 'execution_service.py', 'index.html',
                 'activity.js', 'activity.css', 'drafts.js', 'jobs.js', 'worker_console.js', 'theme.js')
PAYLOAD = {name: (SOURCE / 'bridge' / name).read_bytes() for name in BROWSER_FILES}


class BrowserLauncherTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='browser launcher ')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.conf = self.base / 'configuration with spaces'
        self.bin = self.base / 'bin with spaces'
        self.conf.mkdir()
        self.provider_marker = self.base / 'provider unexpectedly called'
        self.config = ('mock=touch ' + shlex.quote(str(self.provider_marker)) + '\n').encode()
        (self.conf / 'agents.conf').write_bytes(self.config)
        self.env = dict(os.environ, UNIO_BIN_DIR=str(self.bin),
                        UNIO_CONF_DIR=str(self.conf),
                        UNIO_COMPLETION_DIR=str(self.base / 'completion with spaces'),
                        UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0')
        self.installer = self.base / 'standalone installer.sh'
        shutil.copyfile(SOURCE / 'unio-install.sh', self.installer)
        self.install()
        self.engine = self.bin / 'unio'
        self.payload = self.conf / 'lib' / 'browser'
        self.project = self.base / 'workspace with spaces'
        for part in ('repo/nested/deep', 'coord/tasks', 'wt/example/nested'):
            (self.project / part).mkdir(parents=True)
        (self.project / 'coord' / 'STOP').write_text('operator stop\n')
        (self.project / 'coord' / 'base').write_text('main\n')
        self.decoy_marker = self.base / 'wrong engine called'
        decoys = self.base / 'decoy bin'
        decoys.mkdir()
        decoy = decoys / 'unio'
        decoy.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(self.decoy_marker)) + '\nexit 93\n')
        decoy.chmod(0o755)
        self.env['PATH'] = str(decoys) + os.pathsep + os.environ['PATH']

    def install(self, env=None, code=0):
        result = subprocess.run(['bash', str(self.installer)], cwd=self.base,
                                env=env or self.env, capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def call(self, *args, cwd=None, env=None, code=0):
        result = subprocess.run([str(self.engine), 'browser', *args],
                                cwd=cwd or self.base, env=env or self.env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    @contextmanager
    def running(self, *args, cwd=None, env=None):
        log = self.base / ('server-' + str(time.monotonic_ns()) + '.log')
        with log.open('w') as output:
            process = subprocess.Popen([str(self.engine), 'browser', *args],
                                       cwd=cwd or self.base, env=env or self.env,
                                       stdin=subprocess.DEVNULL, stdout=output,
                                       stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic() + 30
            match = None
            while time.monotonic() < deadline:
                text = log.read_text()
                match = re.search(r'http://127\.0\.0\.1:(\d+)', text)
                if match or process.poll() is not None:
                    break
                time.sleep(0.05)
            self.assertIsNotNone(match, log.read_text())
            yield int(match.group(1)), log
        finally:
            # The Popen child is ours and remains unreaped until wait().
            if process.poll() is None:
                process.send_signal(signal.SIGINT)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    def request(self, port, path, method='GET', headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=40)
        try:
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def assert_no_dispatch(self):
        self.assertFalse(self.provider_marker.exists())
        self.assertFalse(self.decoy_marker.exists())

    def test_standalone_bytes_and_shell(self):
        self.assertEqual(len(PAYLOAD), 15)  # includes cached readiness and first-paint theme
        self.assertEqual(sorted(p.name for p in self.payload.iterdir()), sorted(BROWSER_FILES))
        for name, raw in PAYLOAD.items():
            self.assertEqual((self.payload / name).read_bytes(), raw, name)
        subprocess.run(['bash', '-n', str(self.engine)], check=True)
        if shutil.which('shellcheck'):
            subprocess.run(['shellcheck', '-S', 'warning', str(self.engine)], check=True)

    def test_implicit_read_only_context_http_and_fixed_engine(self):
        before = {str(p.relative_to(self.project)): p.read_bytes()
                  for p in self.project.rglob('*') if p.is_file()}
        # Relative configuration must keep its meaning after Observer changes cwd.
        env = dict(self.env, UNIO_CONF_DIR=os.path.relpath(self.conf, self.project / 'repo/nested/deep'))
        with self.running(cwd=self.project / 'repo/nested/deep', env=env) as (port, log):
            self.assertIn('Project: ' + str(self.project), log.read_text())
            self.assertIn('Engine: ' + str(self.engine), log.read_text())
            self.assertIn('Configuration: ' + str(self.conf / 'agents.conf'), log.read_text())
            code, raw = self.request(port, '/api/session')
            self.assertEqual(code, 200)
            self.assertEqual(json.loads(raw), dict(schema_version=1, manual_drafts=False,
                execution=False, progress_output=False, worker_files=False, token=None))
            for path in ('/', '/activity.js', '/activity.css', '/drafts.js', '/jobs.js', '/worker_console.js', '/theme.js'):
                code, raw = self.request(port, path)
                self.assertEqual(code, 200, path)
                self.assertTrue(raw)
            code, raw = self.request(port, '/api/activity')
            self.assertEqual(code, 200, raw)
            document = json.loads(raw)
            self.assertTrue(document['stopped'])
            self.assertEqual([a['name'] for a in document['agents']], ['mock'])
            self.assertEqual(self.request(port, '/api/activity', headers={'Origin': 'https://evil.example'})[0], 403)
            self.assertEqual(self.request(port, '/api/activity', headers={'Host': 'evil.example'})[0], 403)
            self.assertEqual(self.request(port, '/api/activity', method='POST')[0], 405)
            self.assertEqual(self.request(port, '/api/worker-files/workers')[0], 404)
            self.assertEqual(self.request(port, '/server.py')[0], 404)
        after = {str(p.relative_to(self.project)): p.read_bytes()
                 for p in self.project.rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assert_no_dispatch()

    def test_explicit_project_and_effective_project_config(self):
        override = self.project / 'coord' / 'agents.conf'
        override.write_text('projectmock=touch ' + shlex.quote(str(self.provider_marker)) + '\n')
        with self.running('--project', str(self.project)) as (port, log):
            self.assertIn('Configuration: ' + str(override), log.read_text())
            code, raw = self.request(port, '/api/activity')
            self.assertEqual(code, 200, raw)
            self.assertEqual([a['name'] for a in json.loads(raw)['agents']], ['projectmock'])
        self.assert_no_dispatch()

    def test_worktree_inference_and_explicit_drafts(self):
        with self.running('--enable-plan-drafts', cwd=self.project / 'wt/example/nested') as (port, log):
            self.assertIn('Project: ' + str(self.project), log.read_text())
            code, raw = self.request(port, '/api/session')
            self.assertEqual(code, 200)
            state = json.loads(raw)
            self.assertTrue(state['manual_drafts'])
            self.assertFalse(state['execution'])
            self.assertGreater(len(state['token']), 20)
        self.assert_no_dispatch()

    def test_help_and_invalid_startup(self):
        help_text = self.call('--help').stdout
        self.assertIn('usage: unio browser', help_text)
        self.assertIn('--enable-execution', help_text)
        self.assertNotIn('--engine', help_text)
        # Project-local scratch is still inside the real enclosing workspace.
        # Use a neutral cwd to exercise the genuinely outside-project case.
        self.call(cwd=Path('/'), code=2)
        cases = [('--project', str(self.base)), ('--engine', str(self.engine)),
                 ('--engine=' + str(self.engine),), ('--eng', str(self.engine)),
                 ('--port', '65536'), ('--observer-timeout', 'nan'),
                 ('--enable-execution',), ('--worker', 'example'),
                 ('--enable-worker-files',), ('--files-worker', 'example'),
                 ('--enable-progress-output',), ('--progress-worker', 'example')]
        for args in cases:
            with self.subTest(args=args):
                result = self.call('--project', str(self.project), *args, code=2)
                self.assertNotIn('http://127.0.0.1:', result.stdout)
        self.assert_no_dispatch()

    def test_missing_runtime_has_actionable_error(self):
        minimal_path = self.base / 'minimal bin'
        minimal_path.mkdir()
        (minimal_path / 'bash').symlink_to(shutil.which('bash'))
        result = self.call('--help', env=dict(self.env, PATH=str(minimal_path)), code=1)
        self.assertIn('Python 3.9 or newer', result.stderr)
        (self.payload / 'launcher.py').unlink()
        result = self.call('--help', code=1)
        self.assertIn('rerun the matching Unio installer', result.stderr)

    def test_reinstall_preserves_operator_state_and_refreshes_payload(self):
        preserved = {'off/mock': b'operator bench\n', 'playbooks/custom.md': b'keep playbook\n',
                     'lib/browser/user-notes.txt': b'keep unrelated\n'}
        for name, raw in preserved.items():
            target = self.conf / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
        (self.payload / 'activity.js').write_text('damaged old asset\n')
        self.install()
        self.assertEqual((self.conf / 'agents.conf').read_bytes(), self.config)
        for name, raw in preserved.items():
            self.assertEqual((self.conf / name).read_bytes(), raw)
        self.assertEqual((self.payload / 'activity.js').read_bytes(), PAYLOAD['activity.js'])

    def test_unsafe_payload_refused_before_replacement(self):
        original_engine = hashlib.sha256(self.engine.read_bytes()).digest()
        for kind in ('directory-symlink', 'directory-file', 'file-symlink', 'file-hardlink', 'file-directory'):
            with self.subTest(kind=kind):
                profile = self.base / kind
                conf = profile / 'conf'
                browser = conf / 'lib/browser'
                browser.mkdir(parents=True)
                foreign = profile / 'foreign'
                foreign.write_bytes(b'foreign bytes must survive\n')
                witness = browser / 'server.py'
                witness.write_bytes(b'old browser must survive\n')
                target = browser / 'theme.js'  # Last managed name: preflight must scan all.
                if kind == 'directory-symlink':
                    browser.rename(conf / 'lib/original')
                    browser.symlink_to(conf / 'lib/original', target_is_directory=True)
                elif kind == 'directory-file':
                    browser.rename(conf / 'lib/original')
                    browser.write_bytes(b'not a directory\n')
                    witness = conf / 'lib/original/server.py'
                elif kind == 'file-symlink':
                    target.symlink_to(foreign)
                elif kind == 'file-hardlink':
                    os.link(foreign, target)
                else:
                    target.mkdir()
                result = self.install(env=dict(self.env, UNIO_CONF_DIR=str(conf)), code=1)
                self.assertIn('refusing unsafe browser', result.stderr)
                self.assertEqual(foreign.read_bytes(), b'foreign bytes must survive\n')
                self.assertEqual(witness.read_bytes(), b'old browser must survive\n')
                self.assertEqual(hashlib.sha256(self.engine.read_bytes()).digest(), original_engine)


if __name__ == '__main__':
    unittest.main(verbosity=2)
