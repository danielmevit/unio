#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Optional typed route profiles: offline list/show/compile; no execution, no auth."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parent.parent
HELPER = 'route-profiles.py'
# Executables a careless discovery/installer could reach; none may run.
SENTINELS = ('vibe', 'pwm', 'perplexity-web-mcp', 'pip', 'pip3', 'uv', 'curl', 'wget',
             'copilot', 'codex', 'claude', 'gemini', 'agy', 'opencode', 'grok', 'kimi')
# A secret-shaped value that must never be echoed by a refusal.
SECRET = 'sk-live-abcdefghijklmnop1234567890'
# Hostile receipt directory name: spaces, quotes and shell metacharacters.
HOSTILE_DIR = "receipts 'quoted' & $HOME; rm -rf"


def snapshot(root):
    """Every entry's type, mode, size and content hash below root."""
    state = {}
    for directory, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(directory, name)
            info = os.lstat(path)
            digest = None
            if os.path.isfile(path) and not os.path.islink(path):
                digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            state[path] = (info.st_mode, info.st_size, digest)
    return state


class RouteProfileTests(unittest.TestCase):
    def setUp(self):
        scratch = os.environ.get('UNIO_TEST_SCRATCH') or None
        temporary = tempfile.TemporaryDirectory(prefix='unio route profiles ', dir=scratch)
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.home = self.base / 'home with spaces'
        self.home.mkdir()
        self.marker = self.base / 'sentinel was run'
        decoys = self.base / 'decoy bin'
        decoys.mkdir()
        for name in SENTINELS:
            (decoys / name).write_text('#!/bin/sh\necho "$0" >> ' + shlex.quote(str(self.marker)) + '\nexit 97\n')
            (decoys / name).chmod(0o755)
        self.installer = self.base / 'copied standalone installer.sh'
        shutil.copyfile(SOURCE / 'unio-install.sh', self.installer)
        # Project-owned scratch for every subprocess TMPDIR need.
        self.scratch = self.base / 'scratch tmp'
        self.scratch.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('UNIO_', 'PYTHON'))}
        self.env.update(HOME=str(self.home), PATH=str(decoys) + os.pathsep + os.environ['PATH'],
                        TMPDIR=str(self.scratch),
                        UNIO_BIN_DIR=str(self.base / 'bin with spaces'),
                        UNIO_COMPLETION_DIR=str(self.base / 'completion with spaces'),
                        UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0')
        self.conf = self.base / 'conf with spaces'
        self.engine = self.base / 'bin with spaces' / 'unio'
        self.receipts = self.base / HOSTILE_DIR
        self.receipts.mkdir(mode=0o700)
        self.registry_path = self.conf / 'route-profiles.json'

    def install(self, code=0):
        # Run from an unrelated directory: the copy must not need the checkout.
        result = subprocess.run(['bash', str(self.installer)], cwd=self.home,
                                env=dict(self.env, UNIO_CONF_DIR=str(self.conf)),
                                capture_output=True, text=True, timeout=180)
        if code == 0:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def routes(self, *args, cwd=None, env=None):
        return subprocess.run([str(self.engine), 'routes', *args],
                              cwd=str(cwd or self.home),
                              env=env or dict(self.env, UNIO_CONF_DIR=str(self.conf)),
                              capture_output=True, text=True, timeout=60)

    def registry(self, routes, raw=None):
        if raw is not None:
            self.registry_path.write_bytes(raw if isinstance(raw, bytes) else raw.encode())
        else:
            self.registry_path.write_text(json.dumps({'schema_version': 1, 'routes': routes}))
        return self.registry_path

    def route(self, **overrides):
        base = dict(adapter='vibe', requested_cli_version='3.1.1', model='glm-5-3',
                    thinking='high', receipt_dir=str(self.receipts))
        base.update(overrides)
        return base

    def assert_no_sentinel(self):
        self.assertFalse(self.marker.exists(), self.marker.read_text() if self.marker.exists() else '')

    def installed_adapter(self):
        spec = importlib.util.spec_from_file_location(
            'installed_vibe_worker', str(self.conf / 'lib' / 'adapters' / 'vibe-worker.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    def test_installer_packages_exact_helper_bytes_and_preserves_owner_config(self):
        self.install()
        helper = self.conf / 'lib' / HELPER
        self.assertEqual(helper.read_bytes(), (SOURCE / 'tools' / HELPER).read_bytes())
        custom = 'vibeglm=python3 ' + shlex.quote(str(self.conf / 'lib' / 'adapters' / 'vibe-worker.py')) \
            + ' --model glm-5-3\n'
        (self.conf / 'agents.conf').write_text(custom)
        (self.conf / 'templates' / 'MY-NOTES.md').write_text('owner template\n')
        self.registry({'vibeglm': self.route()})
        self.install()
        self.assertEqual((self.conf / 'agents.conf').read_text(), custom)
        self.assertEqual((self.conf / 'templates' / 'MY-NOTES.md').read_text(), 'owner template\n')
        self.assertEqual(json.loads(self.registry_path.read_text())['routes']['vibeglm']['model'], 'glm-5-3')
        self.assertEqual(helper.read_bytes(), (SOURCE / 'tools' / HELPER).read_bytes())
        self.assert_no_sentinel()

    def test_list_and_show_report_requested_settings_and_unknown(self):
        self.install()
        empty = self.routes()
        self.assertEqual(empty.returncode, 0, empty.stdout + empty.stderr)
        self.assertIn('no route profiles declared', empty.stdout)
        self.assertIn('Unknown', empty.stdout)
        empty_json = self.routes('--json')
        self.assertEqual(empty_json.returncode, 0)
        document = json.loads(empty_json.stdout)
        self.assertEqual(document['schema_version'], 1)
        self.assertEqual(document['routes'], [])
        self.assertFalse(document['registry_present'])
        self.registry({'vibeglm': self.route(max_tokens=2000000, max_price=None),
                      'second': self.route(time_limit=5400.0)})
        listed = self.routes()
        self.assertEqual(listed.returncode, 0)
        for fragment in ('vibeglm', 'second', 'glm-5-3',
                         'thinking=high', 'effective model/effort and remaining allowance: Unknown'):
            self.assertIn(fragment, listed.stdout)
        document = json.loads(self.routes('--json').stdout)
        self.assertEqual([r['name'] for r in document['routes']], ['second', 'vibeglm'])
        view = document['routes'][1]
        self.assertEqual((view['model'], view['thinking'], view['adapter'],
                          view['requested_cli_version']), ('glm-5-3', 'high', 'vibe', '3.1.1'))
        self.assertEqual(view['caps'], {'max_tokens': 2000000, 'max_price': None})
        for key in ('effective_model', 'effective_effort', 'remaining_allowance'):
            self.assertEqual(view[key], 'unknown')
        shown = self.routes('show', 'vibeglm')
        self.assertEqual(shown.returncode, 0)
        self.assertIn('route: vibeglm', shown.stdout)
        self.assertIn('effective effort: Unknown', shown.stdout)
        self.assertIn('max_price: none', shown.stdout)
        shown_json = json.loads(self.routes('show', 'vibeglm', '--json').stdout)
        self.assertEqual(shown_json['route']['name'], 'vibeglm')
        self.assertEqual(shown_json['route']['remaining_allowance'], 'unknown')
        self.assert_no_sentinel()

    def test_compile_matches_trusted_adapter_with_safe_quoting(self):
        self.install()
        self.registry({'vibeglm': self.route(max_tokens=2000000, max_price=None,
                                             time_limit=5400.0, max_turns=None)})
        result = self.routes('compile', 'vibeglm')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        line = lines[0]
        name, _, command = line.partition('=')
        self.assertEqual(name, 'vibeglm')
        adapter_path = self.conf / 'lib' / 'adapters' / 'vibe-worker.py'
        expected = ['python3', '-I', '-S', '-B', str(adapter_path),
                    '--model', 'glm-5-3', '--thinking', 'high',
                    '--receipt-dir', str(self.receipts),
                    '--max-price', 'none', '--max-tokens', '2000000',
                    '--time-limit', '5400.0', '--max-turns', 'none']
        # Exact safe quoting: the line is name=shlex.join(argv) and nothing
        # splits, evaluates or expands differently.
        self.assertEqual(command, shlex.join(expected))
        self.assertEqual(shlex.split(command), expected)
        # The compiled argv is exactly what the installed trusted adapter
        # parser and 3.1.1 bound checks accept.
        module = self.installed_adapter()
        args = module.build_parser().parse_args(expected[5:])
        self.assertEqual(module.check_bounds(args, '3.1.1'), [])
        # Read-only: the receipt parent keeps its declared content and mode,
        # and nothing new appears under the config directory.
        before = snapshot(self.conf)
        receipts_before = snapshot(self.receipts)
        again = self.routes('compile', 'vibeglm')
        self.assertEqual(again.returncode, 0)
        self.assertEqual(again.stdout, result.stdout)
        self.assertEqual(snapshot(self.conf), before)
        self.assertEqual(snapshot(self.receipts), receipts_before)
        self.assert_no_sentinel()

    def test_compile_caps_at_and_outside_adapter_bounds(self):
        self.install()
        module = self.installed_adapter()
        self.registry({'atmax': self.route(max_tokens=module.MAX_TOKENS, max_price=module.MAX_PRICE_USD,
                                          time_limit=module.MAX_TIME_LIMIT, max_turns=module.MAX_TURNS)})
        inside = self.routes('compile', 'atmax')
        self.assertEqual(inside.returncode, 0, inside.stdout + inside.stderr)
        self.assertIn('--max-tokens ' + str(module.MAX_TOKENS), inside.stdout)
        for field, value in (('max_tokens', module.MAX_TOKENS + 1),
                             ('max_price', module.MAX_PRICE_USD + .5),
                             ('time_limit', module.MAX_TIME_LIMIT + 1),
                             ('max_turns', module.MAX_TURNS + 1),
                             ('max_tokens', 0), ('max_tokens', -5),
                             ('max_price', 0), ('time_limit', 99999.0)):
            with self.subTest(field=field, value=value):
                self.registry({'bad': self.route(**{field: value})})
                refused = self.routes('compile', 'bad')
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn('outside the supported bound', refused.stderr)
        self.assert_no_sentinel()

    def test_unsupported_declarations_refuse_with_clear_diagnostics(self):
        self.install()
        cases = (
            ('other adapter', self.route(adapter='codex')),
            ('other version', self.route(requested_cli_version='2.26.1')),
            ('other model', self.route(model='mistral-medium-3-5')),
            ('mistral-large alias', self.route(model='mistral-large-4-0-3')),
            ('unsupported thinking', self.route(thinking='low')),
            ('relative receipt', self.route(receipt_dir='relative/path')),
        )
        for label, route in cases:
            with self.subTest(case=label):
                self.registry({'bad': route})
                for args in ((), ('--json',), ('show', 'bad'), ('compile', 'bad')):
                    result = self.routes(*args)
                    self.assertEqual(result.returncode, 2, label + ': ' + result.stdout)
                    self.assertIn('unio routes:', result.stderr)
        self.assert_no_sentinel()

    def test_invalid_registry_refused_without_echoing_secret_like_values(self):
        self.install()
        good = json.dumps({'schema_version': 1, 'routes': {'vibeglm': self.route()}})
        cases = (
            ('malformed', b'{"schema_version": 1,'),
            ('duplicate key', good.replace('"routes": {', '"routes": {"vibeglm": null, "routes": {', 1).encode()),
            ('nonfinite literal', b'{"schema_version": 1, "routes": {"a": {"max_tokens": NaN}}}'
                                  .replace(b'"a"', json.dumps('vibeglm').encode())),
            ('float overflow', json.dumps({'schema_version': 1, 'routes':
                                          {'vibeglm': self.route(max_tokens=1e400)}}).encode()),
            ('integer overflow', json.dumps({'schema_version': 1, 'routes':
                                             {'vibeglm': self.route(max_tokens=10 ** 400)}}).encode()),
            ('nul byte', good.encode() + b'\0'),
            ('control character', json.dumps({'schema_version': 1, 'routes': {'vibeglm': self.route()}}).replace(
                '"glm-5-3"', '"glm-5-3\\u0007"').encode()),
            ('root unknown field', ('{"schema_version": 1, "extra": 1, "routes": {}}').encode()),
            ('wrong schema version', ('{"schema_version": 2, "routes": {}}').encode()),
            ('routes not a map', ('{"schema_version": 1, "routes": []}').encode()),
            ('route unknown field', json.dumps({'schema_version': 1, 'routes': {
                'vibeglm': dict(self.route(), **{SECRET: 'x'})}}).encode()),
            ('secret-like value', json.dumps({'schema_version': 1, 'routes': {
                'vibeglm': self.route(receipt_dir='/' + SECRET)}}).encode()),
            ('bad route name', json.dumps({'schema_version': 1, 'routes': {
                'Bad Name': self.route()}}).encode()),
            ('missing required field', json.dumps({'schema_version': 1, 'routes': {
                'vibeglm': {k: v for k, v in self.route().items() if k != 'model'}}}).encode()),
            ('cap wrong type', json.dumps({'schema_version': 1, 'routes': {
                'vibeglm': self.route(max_tokens='2000000')}}).encode()),
            ('cap boolean', json.dumps({'schema_version': 1, 'routes': {
                'vibeglm': self.route(max_tokens=True)}}).encode()),
        )
        for label, raw in cases:
            with self.subTest(case=label):
                self.registry(None, raw=raw)
                for args in ((), ('show', 'vibeglm'), ('compile', 'vibeglm')):
                    result = self.routes(*args)
                    self.assertEqual(result.returncode, 2, label + ': ' + result.stdout)
                    self.assertIn('unio routes:', result.stderr)
                    # A refusal never echoes the rejected secret-like value.
                    self.assertNotIn(SECRET, result.stdout + result.stderr)
        self.assert_no_sentinel()

    def test_requested_secret_shaped_names_refuse_without_echo(self):
        self.install()
        # Lowercase credential-shaped dummy (no real credentials): it passes
        # the plain identifier grammar, so the refusal must come from the
        # secret-shape guard and must never echo the rejected value.
        dummy = 'sk-dummy-review-only-000000000000'
        for args in (('show', dummy), ('compile', dummy)):
            with self.subTest(args=args):
                result = self.routes(*args)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn('unio routes:', result.stderr)
                self.assertIn('secret-like', result.stderr)
                self.assertNotIn(dummy, result.stdout + result.stderr)
        # Same refusals with a registry present, plus the grammar-invalid
        # uppercase shape: fixed errors, never the rejected value.
        self.registry({'vibeglm': self.route()})
        upper = 'SK-DUMMY-REVIEW-ONLY-000000000000'
        for args in (('show', dummy), ('compile', dummy),
                     ('show', upper), ('compile', upper)):
            with self.subTest(args=args):
                result = self.routes(*args)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn('unio routes:', result.stderr)
                self.assertNotIn(dummy, result.stdout + result.stderr)
                self.assertNotIn(upper, result.stdout + result.stderr)
        # A plain unknown name is refused with a fixed message that never
        # quotes the requested value either.
        unknown = self.routes('show', 'nosuch')
        self.assertEqual(unknown.returncode, 2)
        self.assertIn('unknown route', unknown.stderr)
        self.assertIn("use 'unio routes' to list declared profiles", unknown.stderr)
        self.assertNotIn('nosuch', unknown.stderr)
        self.assert_no_sentinel()

    def test_pathological_numeric_caps_refuse_bounded_without_traceback(self):
        self.install()
        huge = 10 ** 400
        for field in ('max_tokens', 'max_price', 'time_limit', 'max_turns'):
            with self.subTest(field=field):
                self.registry({'vibeglm': self.route(**{field: huge})})
                for args in ((), ('--json',), ('show', 'vibeglm'), ('compile', 'vibeglm')):
                    result = self.routes(*args)
                    self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
                    self.assertIn('must be a finite number or null', result.stderr)
                    self.assertNotIn('Traceback', result.stderr)
                    self.assertNotIn(str(huge), result.stdout + result.stderr)
        # Legitimate finite caps, null and omissions keep working unchanged.
        self.registry({'vibeglm': self.route(max_tokens=2000000, max_price=None)})
        self.assertEqual(self.routes().returncode, 0)
        self.assertEqual(self.routes('show', 'vibeglm').returncode, 0)
        self.assertEqual(self.routes('compile', 'vibeglm').returncode, 0)
        self.assert_no_sentinel()

    def test_nonregular_and_oversized_registry_refuse(self):
        self.install()
        os.mkfifo(self.registry_path)
        fifo = self.routes()
        self.assertEqual(fifo.returncode, 2, fifo.stdout)
        self.assertIn('not a regular file', fifo.stderr)
        os.unlink(self.registry_path)
        self.registry_path.symlink_to('/etc/hostname')
        linked = self.routes()
        self.assertEqual(linked.returncode, 2, linked.stdout)
        self.assertIn('not a regular file', linked.stderr)
        self.registry_path.unlink()
        self.registry(None, raw=b'{"schema_version": 1, "routes": {}, "padding": "' + b'x' * 1048600 + b'"}')
        oversized = self.routes()
        self.assertEqual(oversized.returncode, 2, oversized.stdout)
        self.registry_path.unlink()
        self.assert_no_sentinel()

    def test_receipt_parent_is_checked_read_only(self):
        self.install()
        self.registry({'vibeglm': self.route(receipt_dir=str(self.base / 'missing receipts'))})
        # list/show stay declarative; only compile checks the parent.
        self.assertEqual(self.routes().returncode, 0)
        self.assertEqual(self.routes('show', 'vibeglm').returncode, 0)
        missing = self.routes('compile', 'vibeglm')
        self.assertEqual(missing.returncode, 2)
        self.assertIn('create the private receipt parent', missing.stderr)
        self.assertFalse((self.base / 'missing receipts').exists())
        public = self.base / 'public receipts'
        public.mkdir(mode=0o750)
        os.chmod(public, 0o750)
        self.registry({'vibeglm': self.route(receipt_dir=str(public))})
        loose = self.routes('compile', 'vibeglm')
        self.assertEqual(loose.returncode, 2)
        self.assertIn('owner-only private directory', loose.stderr)
        as_file = self.base / 'receipt file'
        as_file.write_text('not a directory\n')
        self.registry({'vibeglm': self.route(receipt_dir=str(as_file))})
        not_dir = self.routes('compile', 'vibeglm')
        self.assertEqual(not_dir.returncode, 2)
        self.assertIn('not a directory', not_dir.stderr)
        self.assert_no_sentinel()

    def test_compile_requires_packaged_trusted_adapter(self):
        self.install()
        self.registry({'vibeglm': self.route()})
        (self.conf / 'lib' / 'adapters' / 'vibe-worker.py').unlink()
        result = self.routes('compile', 'vibeglm')
        self.assertEqual(result.returncode, 2)
        self.assertIn('packaged vibe adapter is not installed', result.stderr)
        # list/show remain usable without the adapter.
        self.assertEqual(self.routes().returncode, 0)
        self.assert_no_sentinel()

    def test_works_outside_project_under_stop_and_hostile_environment(self):
        self.install()
        self.registry({'vibeglm': self.route()})
        project = self.base / 'project with spaces'
        (project / 'coord').mkdir(parents=True)
        (project / 'wt').mkdir()
        (project / 'repo').mkdir()
        (project / 'coord' / 'STOP').write_text('stopped\n')
        inside = self.routes(cwd=project / 'repo')
        self.assertEqual(inside.returncode, 0, inside.stdout + inside.stderr)
        self.assertIn('vibeglm', inside.stdout)
        # A planted module directory must never be imported: the helper runs
        # isolated (-I -S -B) and loads only the trusted packaged sibling.
        planted = self.base / 'planted modules'
        planted.mkdir()
        for name, payload in (('json.py', 'import os\nos.system("touch %s")\n' % shlex.quote(str(self.marker))),
                              ('argparse.py', 'raise SystemExit(9)'),
                              ('vibe-worker.py', 'print("planted")\nraise SystemExit(9)\n')):
            (planted / name).write_text(payload)
        hostile = dict(self.env, UNIO_CONF_DIR=str(self.conf), PYTHONPATH=str(planted))
        compiled = subprocess.run([str(self.engine), 'routes', 'compile', 'vibeglm'],
                                  cwd=str(planted), env=hostile,
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(compiled.returncode, 0, compiled.stdout + compiled.stderr)
        self.assertIn(str(self.conf / 'lib' / 'adapters' / 'vibe-worker.py'), compiled.stdout)
        self.assertNotIn('planted', compiled.stdout)
        self.assert_no_sentinel()

    def test_usage_errors_are_bounded(self):
        self.install()
        self.registry({'vibeglm': self.route()})
        for args in (('bogus',), ('show',), ('show', 'a', 'b'), ('compile',),
                     ('compile', 'a', 'b'), ('show', 'vibeglm', '--jso'),
                     ('list', 'extra'), ('show', 'UPPER')):
            with self.subTest(args=args):
                result = self.routes(*args)
                self.assertEqual(result.returncode, 2, result.stdout)
                self.assertIn('unio routes:', result.stderr)
        unknown = self.routes('show', 'nosuch')
        self.assertEqual(unknown.returncode, 2)
        self.assertIn('unknown route', unknown.stderr)
        self.assertNotIn('nosuch', unknown.stderr)
        self.assert_no_sentinel()

    def native_agent_prefix(self, worker):
        """Apply the actual native cmd_run derivation: agent="${worker%%-*}". """
        helper = Path(self.engine).read_text()
        self.assertIn('local agent="${worker%%-*}"', helper)
        applied = subprocess.run(
            ['bash', '-c', 'worker=$1; agent="${worker%%-*}"; printf %s "$agent"',
             'native-prefix', worker],
            capture_output=True, text=True, timeout=10)
        self.assertEqual(applied.returncode, 0, applied.stderr)
        return applied.stdout

    def test_compiled_alias_matches_native_worker_prefix_lookup(self):
        self.install()
        self.registry({'vibeglm_high': self.route()})
        result = self.routes('compile', 'vibeglm_high')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        lines = result.stdout.splitlines()
        self.assertEqual(len(lines), 1)
        alias, sep, command = lines[0].partition('=')
        self.assertEqual(sep, '=')
        self.assertEqual(alias, 'vibeglm_high')
        self.assertTrue(command)
        self.assertEqual(self.native_agent_prefix(alias + '-task'), alias)
        self.assertEqual(self.native_agent_prefix(alias + '-feature'), alias)
        # The hyphenated probe name is not a selectable prefix: native
        # lookup of vibe-high-task yields vibe, so compile must refuse it.
        self.assertEqual(self.native_agent_prefix('vibe-high-task'), 'vibe')
        self.assertNotEqual(self.native_agent_prefix('vibe-high-task'), 'vibe-high')
        for args in (('show', 'vibe-high'), ('compile', 'vibe-high')):
            with self.subTest(args=args):
                refused = self.routes(*args)
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn('native agent prefixes', refused.stderr)
                self.assertIn('no hyphen', refused.stderr)
                self.assertNotIn('vibe-high', refused.stdout + refused.stderr)
                self.assertEqual(refused.stdout, '')
        self.registry({'vibe-high': self.route()})
        for args in ((), ('--json',), ('show', 'vibe-high'), ('compile', 'vibe-high')):
            with self.subTest(registry=args):
                refused = self.routes(*args)
                self.assertEqual(refused.returncode, 2, refused.stdout + refused.stderr)
                self.assertIn('native agent prefixes', refused.stderr)
                self.assertNotIn('vibe-high', refused.stdout + refused.stderr)
                self.assertEqual(refused.stdout, '')
        self.assert_no_sentinel()

    def test_compile_refuses_control_characters_in_configuration_paths(self):
        self.install()
        self.registry({'vibeglm': self.route()})
        normal = self.routes('compile', 'vibeglm')
        self.assertEqual(normal.returncode, 0, normal.stdout + normal.stderr)
        self.assertEqual(len(normal.stdout.splitlines()), 1)
        self.assertTrue(normal.stdout.startswith('vibeglm='))

        newline_conf = self.base / 'conf\nwith newline'
        shutil.copytree(self.conf, newline_conf)
        (newline_conf / 'route-profiles.json').write_text(
            json.dumps({'schema_version': 1, 'routes': {'vibeglm': self.route()}}))
        bel_conf = self.base / 'conf\x07with bel'
        shutil.copytree(self.conf, bel_conf)
        (bel_conf / 'route-profiles.json').write_text(
            json.dumps({'schema_version': 1, 'routes': {'vibeglm': self.route()}}))

        for label, conf in (('newline', newline_conf), ('bel', bel_conf)):
            with self.subTest(conf=label):
                env = dict(self.env, UNIO_CONF_DIR=str(conf))
                before = snapshot(conf)
                receipts_before = snapshot(self.receipts)
                compiled = subprocess.run(
                    [str(self.engine), 'routes', 'compile', 'vibeglm'],
                    cwd=str(self.home), env=env, capture_output=True, text=True,
                    timeout=60)
                self.assertEqual(compiled.returncode, 2, compiled.stdout + compiled.stderr)
                self.assertEqual(compiled.stdout, '')
                self.assertIn('unio routes:', compiled.stderr)
                self.assertIn('control character', compiled.stderr)
                self.assertNotIn('vibeglm=', compiled.stdout + compiled.stderr)
                self.assertNotIn('\nwith newline', compiled.stdout + compiled.stderr)
                self.assertNotIn('\x07', compiled.stdout + compiled.stderr)
                self.assertEqual(compiled.stderr.count('\n'), 1)
                self.assertEqual(snapshot(conf), before)
                self.assertEqual(snapshot(self.receipts), receipts_before)

                listed = subprocess.run(
                    [str(self.engine), 'routes', '--json'],
                    cwd=str(self.home), env=env, capture_output=True, text=True,
                    timeout=60)
                self.assertEqual(listed.returncode, 0, listed.stdout + listed.stderr)
                document = json.loads(listed.stdout)
                self.assertEqual(document['schema_version'], 1)
                self.assertTrue(document['registry_present'])
                self.assertEqual([route['name'] for route in document['routes']], ['vibeglm'])

                text = subprocess.run(
                    [str(self.engine), 'routes'],
                    cwd=str(self.home), env=env, capture_output=True, text=True,
                    timeout=60)
                self.assertEqual(text.returncode, 0, text.stdout + text.stderr)
                self.assertIn('control characters; not shown', text.stdout)
                self.assertNotIn('\nwith newline', text.stdout)
                self.assertNotIn('\x07', text.stdout + text.stderr)

        again = self.routes('compile', 'vibeglm')
        self.assertEqual(again.returncode, 0, again.stdout + again.stderr)
        self.assertEqual(again.stdout, normal.stdout)
        self.assert_no_sentinel()

    def test_legacy_routes_and_runtime_meaning_unchanged(self):
        self.install()
        custom = ('vibeglm=python3 ' + shlex.quote(str(self.conf / 'lib' / 'adapters' / 'vibe-worker.py'))
                  + ' --model glm-5-3 --receipt-dir ' + shlex.quote(str(self.receipts)) + '\n'
                  'claude=claude -p --dangerously-skip-permissions < "$TASKFILE"\n')
        (self.conf / 'agents.conf').write_text(custom)
        self.install()
        self.assertEqual((self.conf / 'agents.conf').read_text(), custom)
        integrations = subprocess.run([str(self.engine), 'integrations'], cwd=str(self.home),
                                       env=dict(self.env, UNIO_CONF_DIR=str(self.conf)),
                                       capture_output=True, text=True, timeout=60)
        self.assertEqual(integrations.returncode, 0, integrations.stdout + integrations.stderr)
        self.assertIn('vibe-worker', integrations.stdout)
        self.assert_no_sentinel()


if __name__ == '__main__':
    unittest.main()
