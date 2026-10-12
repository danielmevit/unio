#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Packaged optional adapters and read-only `unio integrations`; offline, no auth."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parent.parent
ADAPTERS = ('vibe-worker.py', 'perplexity-worker.py', 'copilot-worker.py')
# Executables a careless discovery/installer could reach; none may run.
SENTINELS = ('vibe', 'pwm', 'perplexity-web-mcp', 'pip', 'pip3', 'uv', 'curl', 'wget',
             'copilot', 'codex', 'claude', 'gemini', 'agy', 'opencode', 'grok', 'kimi')
# Paths with a quote, backslash, newline, tab and ESC must still produce valid JSON.
HOSTILE = 'conf with spaces "q" \\ back\nslash\ttab\x1b esc'


def snapshot(root):
    """Every entry's type, mode, size, mtime and content hash below root."""
    state = {}
    for directory, dirs, files in os.walk(root):
        for name in dirs + files:
            path = os.path.join(directory, name)
            info = os.lstat(path)
            digest = None
            if os.path.isfile(path) and not os.path.islink(path):
                digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()
            state[path] = (info.st_mode, info.st_size, info.st_mtime_ns, digest)
    return state


class AdapterInstallTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='unio adapters ')
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
        self.env = {k: v for k, v in os.environ.items() if not k.startswith(('UNIO_', 'PYTHON'))}
        self.env.update(HOME=str(self.home), PATH=str(decoys) + os.pathsep + os.environ['PATH'],
                        UNIO_BIN_DIR=str(self.base / 'bin with spaces'),
                        UNIO_COMPLETION_DIR=str(self.base / 'completion with spaces'),
                        UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0')
        self.engine = self.base / 'bin with spaces' / 'unio'

    def install(self, conf, code=0):
        # Run from an unrelated directory: the copy must not need the checkout.
        result = subprocess.run(['bash', str(self.installer)], cwd=self.home,
                                env=dict(self.env, UNIO_CONF_DIR=str(conf)),
                                capture_output=True, text=True, timeout=120)
        if code == 0:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def integrations(self, conf, *args, cwd, env=None):
        return subprocess.run([str(self.engine), 'integrations', *args], cwd=cwd,
                              env=env or dict(self.env, UNIO_CONF_DIR=str(conf)),
                              capture_output=True, text=True, timeout=60)

    def assert_no_sentinel(self):
        self.assertFalse(self.marker.exists(), self.marker.read_text() if self.marker.exists() else '')

    def test_copied_installer_packages_exact_bytes_and_preserves_config(self):
        conf = self.base / HOSTILE
        self.install(conf)
        adapters = conf / 'lib' / 'adapters'
        for name in ADAPTERS:
            self.assertEqual((adapters / name).read_bytes(), (SOURCE / 'tools' / name).read_bytes(), name)
        custom = 'vibeglm=python3 ' + shlex.quote(str(adapters / 'vibe-worker.py')) + ' --model glm-5-3\n'
        (conf / 'agents.conf').write_text(custom)
        (conf / 'templates' / 'MY-NOTES.md').write_text('owner template\n')
        for relative in ('docs/development/AGENT-FLEET.md',
                         'docs/development/LEAD-ROUTING.md',
                         'docs/development/MODEL-EFFORT.md',
                         'docs/ai/REASONING-PROFILES.md'):
            name = Path(relative).stem
            self.assertEqual((conf / 'templates' / (name + '.md')).read_bytes(),
                             (SOURCE / relative).read_bytes())
            (conf / 'templates' / (name + '.md')).write_text('owner ' + name + ' notes\n')
        for relative in ('docs/ai/MODEL-ROLES.md', 'docs/development/MODEL-SCOREBOARD.md',
                         'docs/WORK-MODES.md'):
            self.assertEqual((conf / 'templates' / Path(relative).name).read_bytes(), (SOURCE / relative).read_bytes())
        (adapters / 'owner notes.txt').write_text('unrelated\n')
        credential = self.home / '.config' / 'perplexity-web-mcp' / 'token'
        credential.parent.mkdir(parents=True)
        credential.write_text('fake-not-a-token\n')
        (adapters / 'vibe-worker.py').write_text('stale adapter\n')
        self.install(conf)
        self.assertEqual((conf / 'agents.conf').read_text(), custom)
        self.assertEqual((conf / 'templates' / 'MY-NOTES.md').read_text(), 'owner template\n')
        for name in ('AGENT-FLEET', 'LEAD-ROUTING', 'MODEL-EFFORT', 'REASONING-PROFILES'):
            self.assertEqual((conf / 'templates' / (name + '.md')).read_text(), 'owner ' + name + ' notes\n')
        self.assertEqual((adapters / 'owner notes.txt').read_text(), 'unrelated\n')
        self.assertEqual(credential.read_text(), 'fake-not-a-token\n')
        for name in ADAPTERS:
            self.assertEqual((adapters / name).read_bytes(), (SOURCE / 'tools' / name).read_bytes(), name)
        self.assert_no_sentinel()

    def test_discovery_is_read_only_outside_project_and_with_stop(self):
        conf = self.base / HOSTILE
        self.install(conf)
        outside = self.base / 'outside any project'
        project = self.base / 'project with spaces'
        for directory in (outside, project / 'coord', project / 'repo'):
            directory.mkdir(parents=True)
        (project / 'coord' / 'STOP').write_text('operator stop\n')
        # Planted modules: an unisolated interpreter would import them from cwd/PYTHONPATH.
        for where in (outside, project / 'repo'):
            for module in ('json.py', 'sitecustomize.py', 'usercustomize.py'):
                (where / module).write_text('open(' + repr(str(self.marker)) + ', "a").write("python import\\n")\n')
            (where / 'perplexity_web_mcp').mkdir()
            (where / 'perplexity_web_mcp' / '__init__.py').write_text('raise SystemExit(99)\n')
        env = dict(self.env, UNIO_CONF_DIR=str(conf), PYTHONPATH=str(outside),
                   PYTHONSTARTUP=str(outside / 'json.py'))
        before = snapshot(self.base)
        for cwd in (outside, project / 'repo'):
            text = self.integrations(conf, cwd=cwd, env=env)
            self.assertEqual(text.returncode, 0, text.stderr)
            self.assertIn('installed: true', text.stdout)
            self.assertIn('docs/integrations/PERPLEXITY-WEB.md', text.stdout)
            self.assertIn('Manual external installation and sign-in remain required', text.stdout)
            result = self.integrations(conf, '--json', cwd=cwd, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            value = json.loads(result.stdout)
            self.assertEqual(value['schema_version'], 1)
            self.assertEqual([a['name'] for a in value['adapters']], ['vibe-worker', 'perplexity-worker', 'copilot-worker'])
            for adapter, name in zip(value['adapters'], ADAPTERS):
                self.assertEqual(adapter['path'], str(conf / 'lib' / 'adapters' / name))
                self.assertIs(adapter['installed'], True)
                self.assertTrue(adapter['role'])
                self.assertEqual((adapter['authentication'], adapter['capacity']), ('unknown', 'unknown'))
                self.assertTrue(adapter['setup_guide'].startswith('https://github.com/danielmevit/unio/'))
        self.assertEqual(snapshot(self.base), before)
        self.assertTrue((project / 'coord' / 'STOP').exists())
        self.assert_no_sentinel()

        missing = self.base / 'never installed "x"\nconf'
        result = self.integrations(missing, '--json', cwd=outside)
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual([a['installed'] for a in value['adapters']], [False, False, False])
        self.assertFalse(missing.exists())

        for bad in (['--jsn'], ['--json', 'extra'], ['vibe-worker']):
            result = self.integrations(conf, *bad, cwd=outside)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, '')
            self.assertIn('usage: unio integrations [--json]', result.stderr)
        self.assertEqual(snapshot(self.base), before)
        self.assert_no_sentinel()

    def test_unsafe_targets_refused_before_any_adapter_is_replaced(self):
        def prepare(label):
            conf = self.base / ('conf ' + label)
            self.install(conf)
            adapters = conf / 'lib' / 'adapters'
            # The first written adapter carries owner bytes; preflight must keep them.
            (adapters / 'vibe-worker.py').write_text('owner vibe bytes\n')
            return conf, adapters

        def assert_refused(conf, adapters):
            result = self.install(conf, code=1)
            self.assertIn('refusing unsafe adapter', result.stderr)
            self.assertEqual((adapters / 'vibe-worker.py').read_text(), 'owner vibe bytes\n')

        conf, adapters = prepare('symlink file')
        outside = self.base / 'symlink target.py'
        outside.write_text('outside bytes\n')
        (adapters / 'perplexity-worker.py').unlink()
        (adapters / 'perplexity-worker.py').symlink_to(outside)
        assert_refused(conf, adapters)
        self.assertEqual(outside.read_text(), 'outside bytes\n')

        conf, adapters = prepare('copilot last target symlink')
        (adapters / 'copilot-worker.py').unlink()
        (adapters / 'copilot-worker.py').symlink_to(outside)
        assert_refused(conf, adapters)
        self.assertEqual(outside.read_text(), 'outside bytes\n')

        conf, adapters = prepare('hardlink')
        partner = self.base / 'hardlink partner.py'
        partner.write_text('partner bytes\n')
        (adapters / 'perplexity-worker.py').unlink()
        os.link(partner, adapters / 'perplexity-worker.py')
        assert_refused(conf, adapters)
        self.assertEqual(partner.read_text(), 'partner bytes\n')

        conf, adapters = prepare('fifo')
        (adapters / 'perplexity-worker.py').unlink()
        os.mkfifo(adapters / 'perplexity-worker.py')
        assert_refused(conf, adapters)

        conf, adapters = prepare('directory')
        (adapters / 'perplexity-worker.py').unlink()
        (adapters / 'perplexity-worker.py').mkdir()
        assert_refused(conf, adapters)

        conf = self.base / 'conf symlink directory'
        self.install(conf)
        elsewhere = self.base / 'elsewhere adapters'
        elsewhere.mkdir()
        (elsewhere / 'vibe-worker.py').write_text('owner vibe bytes\n')
        shutil.rmtree(conf / 'lib' / 'adapters')
        (conf / 'lib' / 'adapters').symlink_to(elsewhere, target_is_directory=True)
        result = self.install(conf, code=1)
        self.assertIn('refusing unsafe adapter directory', result.stderr)
        self.assertEqual(sorted(p.name for p in elsewhere.iterdir()), ['vibe-worker.py'])
        self.assertEqual((elsewhere / 'vibe-worker.py').read_text(), 'owner vibe bytes\n')
        self.assert_no_sentinel()


if __name__ == '__main__':
    unittest.main()
