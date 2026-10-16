#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed and extracted engine contracts with thin, isolated config overrides."""
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]


class ThinConfig(unittest.TestCase):
    def test_installed_and_standalone(self):
        with tempfile.TemporaryDirectory(prefix="thin config's spaced ",
                                         dir=os.environ.get('TMPDIR', str(SOURCE))) as tmp:
            base = Path(tmp)
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('UNIO_', 'GIT_', 'PYTHON')) and k != 'BASH_ENV'}
            env.update(UNIO_BIN_DIR=str(base / 'installed bin'),
                       UNIO_CONF_DIR=str(base / 'installed conf'),
                       UNIO_COMPLETION_DIR=str(base / 'completion'),
                       UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
                       GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                       GIT_AUTHOR_NAME='fixture', GIT_COMMITTER_NAME='fixture',
                       GIT_AUTHOR_EMAIL='fixture@example.invalid',
                       GIT_COMMITTER_EMAIL='fixture@example.invalid')

            def run(args, cwd=base, input=None, code=0):
                cp = subprocess.run(list(map(str, args)), cwd=cwd, env=env, input=input,
                                    capture_output=True, text=True, timeout=90)
                self.assertEqual(cp.returncode, code, (args, cp.stdout, cp.stderr))
                return cp

            run(['bash', SOURCE / 'unio-install.sh'])
            installer = (SOURCE / 'unio-install.sh').read_text()
            engine_text = installer.split("cat > \"$BIN_DIR/unio\" <<'UNIO_BIN_EOF'\n", 1)[1].split('\nUNIO_BIN_EOF\n', 1)[0] + '\n'
            standalone = base / "standalone engine's bin/unio"
            standalone.parent.mkdir()
            standalone.write_text(engine_text)
            standalone.chmod(0o755)
            canonical = (SOURCE / 'tools/remote-guard.py').read_bytes()
            embedded = engine_text.split("cat <<'UNIO_REMOTE_GUARD_CORE_PY'\n", 1)[1].split('UNIO_REMOTE_GUARD_CORE_PY\n', 1)[0].encode()
            self.assertEqual(embedded, canonical)
            self.assertEqual((base / 'installed conf/lib/remote-guard.py').read_bytes(), canonical)
            self.assertEqual((base / 'installed bin/unio').read_bytes(), standalone.read_bytes())
            (base / 'installed conf/lib/remote-guard.py').unlink()
            # A permissive decoy must never become the guard through config/PATH.
            decoy = base / 'decoy bin'
            decoy.mkdir()
            trap = decoy / 'unio'
            trap.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(base / 'wrong-helper')) + '\nexit 0\n')
            trap.chmod(0o755)
            env['PATH'] = str(decoy) + os.pathsep + env['PATH']
            for mode, engine in [('installed', base / 'installed bin/unio'), ('standalone', standalone)]:
                with self.subTest(mode=mode):
                    root = base / (mode + " project's root")
                    repo = root / 'repo'
                    repo.mkdir(parents=True)
                    thin = base / (mode + ' thin conf')
                    thin.mkdir()
                    shutil.copytree(base / 'installed conf/templates', thin / 'templates')
                    (thin / 'agents.conf').write_text('mock=printf mock\n')
                    env['UNIO_CONF_DIR'] = str(thin)
                    self.assertFalse((thin / 'lib').exists())
                    run(['git', 'init', '-q', '-b', 'main'], repo)
                    run(['git', 'commit', '--allow-empty', '-qm', 'fixture'], repo)
                    oid = run(['git', 'rev-parse', 'HEAD'], repo).stdout.strip()
                    hook = repo / '.git/hooks/pre-push'
                    owner = '#!/bin/sh\ncat > "$PWD/owner-input"\nprintf "%s\\n" "$@" > "$PWD/owner-args"\nexit 0\n'
                    hook.write_text(owner)
                    hook.chmod(0o755)
                    run([engine, 'init', 'mock'], repo)
                    self.assertEqual(hook.with_name('pre-push.owner').read_text(), owner)
                    self.assertIn(shlex.quote(str(engine)), hook.read_text())
                    dest = base / (mode + ' bare destination.git')
                    run(['git', 'init', '--bare', '-q', dest])
                    run(['git', 'remote', 'add', 'origin', dest], repo)
                    run(['git', 'push', 'origin', 'main'], repo)
                    owner_refs = (repo / 'owner-input').read_text()
                    self.assertIn('refs/heads/main', owner_refs)
                    self.assertIn(str(dest), (repo / 'owner-args').read_text())
                    worker = root / 'wt/mock'
                    run(['git', 'commit', '--allow-empty', '-qm', 'own branch'], worker)
                    run(['git', 'checkout', '--detach', '-q'], worker)
                    cp = run(['git', 'commit', '--allow-empty', '-qm', 'wrong branch'], worker, code=1)
                    self.assertIn('must commit on agent/mock', cp.stderr)
                    run(['git', 'checkout', '-q', 'agent/mock'], worker)
                    cp = run(['git', 'update-ref', 'refs/heads/main', oid], worker, code=128)
                    self.assertIn('may not move refs/heads/main', cp.stderr)
                    run(['git', 'branch', 'dev'], repo)
                    run([engine, 'remote-policy', 'set', 'origin', 'release'], repo)
                    run([engine, 'remote-policy', 'install-guard'], repo)
                    # Both dispatchers preserve ref input, including a forbidden
                    # second record. An stdin-fed Python script would lose it.
                    refs = f'refs/heads/main {oid} refs/heads/main {"0" * 40}\nrefs/heads/dev {oid} refs/heads/dev {"0" * 40}\n'
                    for command in ([hook, 'origin', dest], [engine, '_remote-guard', 'check', repo, 'origin', dest]):
                        cp = run(command, repo, input=refs, code=1)
                        self.assertIn('non-release branch', cp.stderr)
                    cp = run(['git', 'push', 'origin', 'dev'], repo, code=1)
                    self.assertIn('non-release branch', cp.stderr)
                    self.assertEqual(run(['git', '--git-dir', dest, 'for-each-ref', 'refs/heads/dev']).stdout, '')
                    self.assertEqual((repo / 'owner-input').read_text(), owner_refs)
                    cp = run([hook, 'origin', dest], root / 'wt/mock', input=refs, code=1)
                    self.assertIn('workers do not push', cp.stderr)
                    # Hostile override helpers cannot disable configured policy.
                    (thin / 'lib').mkdir()
                    (thin / 'lib/remote-guard.py').write_text('raise SystemExit(0)\n')
                    run([hook, 'origin', dest], repo, input=refs, code=1)
                    (root / 'coord/remote-policy.json').write_text('{broken')
                    run([hook, 'origin', dest], repo, input='', code=1)
                    # Missing pinned core must fail closed even with a decoy
                    # unio on PATH and an external permissive helper present.
                    engine.rename(engine.with_name('hidden engine'))
                    cp = run([hook, 'origin', dest], repo, input='', code=1)
                    self.assertIn('requires an executable helper', cp.stderr)
                    (root / 'coord/remote-policy.json').unlink()
                    run([hook, 'origin', dest], repo, input=refs)
                    self.assertEqual((repo / 'owner-input').read_text(), refs)
                    hook.with_name('pre-push.owner').write_text('#!/bin/sh\nexit 37\n')
                    run([hook, 'origin', dest], repo, input=refs, code=37)
                    self.assertFalse((base / 'wrong-helper').exists())


if __name__ == '__main__':
    unittest.main()
