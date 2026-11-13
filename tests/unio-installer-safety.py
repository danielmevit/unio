#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installer accident-containment regressions.

Two properties of the standalone installer:
1. Accidental sourcing is refused before any installation filesystem write
   or caller-shell setting change, with a nonzero status and an actionable
   message, and the caller shell keeps running.
2. The main runtime publishes through a private staging file and one atomic
   rename: interpreters that already opened the previous runtime keep a
   complete read, new invocations always see a complete file, and a failure
   before publication leaves the existing runtime byte-identical while
   cleaning up only this invocation's own staging path.

Standard library only, offline. Every installer invocation in this file,
including refused sourcing, receives explicit UNIO_BIN_DIR, UNIO_CONF_DIR and
UNIO_COMPLETION_DIR values inside a private temporary fixture, plus a fixture
HOME: no default global destination is ever created, read or written.
"""
import errno
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / 'unio-install.sh'
ENGINE_OPEN = "cat > \"$BIN_DIR/unio\" <<'UNIO_BIN_EOF'\n"
ENGINE_TIMEOUT = 180


def engine_text():
    source = INSTALLER.read_text()
    return source.split(ENGINE_OPEN, 1)[1].split('\nUNIO_BIN_EOF\n', 1)[0] + '\n'


def heredoc_payload_sizes():
    """Sizes of every heredoc payload the installer writes, by delimiter."""
    source = INSTALLER.read_text()
    pattern = re.compile(r"^ *cat > \"[^\n]*<<'([A-Z0-9_]+)'\n", re.M)
    sizes = {}
    for match in pattern.finditer(source):
        end = source.find('\n' + match.group(1) + '\n', match.end())
        if end != -1:
            sizes[match.group(1)] = end - match.end() + 1
    return sizes


class InstallerSafetyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix='unio-installer-safety-')
        self.base = Path(self._tmp.name)
        self.bin_dir = self.base / 'installed bin'
        self.conf_dir = self.base / 'configuration'
        self.completion_dir = self.base / 'completion dir'
        self.home = self.base / 'fixture home'
        for directory in (self.bin_dir, self.conf_dir, self.completion_dir, self.home):
            directory.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def environment(self, **changes):
        env = {
            'PATH': '/usr/bin:/bin',
            'HOME': str(self.home),
            'UNIO_BIN_DIR': str(self.bin_dir),
            'UNIO_CONF_DIR': str(self.conf_dir),
            'UNIO_COMPLETION_DIR': str(self.completion_dir),
            'UNIO_AUTO_VERIFY': '0',
            'UNIO_AUTO_SYNC': '0',
            'UNIO_AUTO_OFF': '0',
            'UNIO_CLI_UPDATES_OFFLINE': '1',
        }
        env.update(changes)
        return env

    def invoke(self, args, env, **kwargs):
        for name in ('UNIO_BIN_DIR', 'UNIO_CONF_DIR', 'UNIO_COMPLETION_DIR'):
            self.assertIn(name, env, 'explicit destinations required before any installer call')
        return subprocess.run([str(a) for a in args], env=env, capture_output=True, text=True,
                             timeout=kwargs.pop('timeout', ENGINE_TIMEOUT), **kwargs)

    def snapshot(self):
        state = {}
        for directory in (self.bin_dir, self.conf_dir, self.completion_dir, self.home):
            for path, dirs, files in os.walk(directory):
                for name in sorted(dirs):
                    state[os.path.join(path, name)] = 'dir'
                for name in sorted(files):
                    full = os.path.join(path, name)
                    with open(full, 'rb') as handle:
                        state[full] = hashlib.sha256(handle.read()).hexdigest()
        return state

    def seed_fixture_outputs(self):
        (self.bin_dir / 'unio').write_text('#!/usr/bin/env bash\nexit 7\n')
        os.chmod(self.bin_dir / 'unio', 0o755)
        (self.conf_dir / 'agents.conf').write_text('mock=SENTINEL\n')
        (self.completion_dir / 'unio').write_text('# completion sentinel\n')

    def assert_refusal(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('Unio installed', result.stdout)
        self.assertIn('refusing', result.stderr)
        self.assertIn('sourced', result.stderr)
        self.assertIn('nothing was installed', result.stderr)
        self.assertIn('run it instead', result.stderr)
        self.assertIn('bash', result.stderr)

    def test_sourced_refusal_is_side_effect_free_and_actionable(self):
        self.seed_fixture_outputs()
        before = self.snapshot()
        caller = self.base / 'source caller.sh'
        caller.write_text(
            'echo "state $- $(set +o | md5sum)"\n'
            'source ' + shlex.quote(str(INSTALLER)) + '\n'
            'rc=$?\n'
            'echo "state $- $(set +o | md5sum)"\n'
            'echo "sourced-rc=$rc caller-alive"\n'
        )
        result = self.invoke(['bash', caller], self.environment())
        self.assert_refusal(result)
        lines = result.stdout.splitlines()
        self.assertEqual(lines[0], lines[1], 'caller shell state must not change')
        self.assertIn('sourced-rc=1 caller-alive', lines)
        self.assertEqual(self.snapshot(), before)

    def test_sourced_refusal_holds_for_strict_dash_c_and_function_callers(self):
        self.seed_fixture_outputs()
        before = self.snapshot()
        quote = shlex.quote(str(INSTALLER))
        cases = (
            ('plain bash -c', 'source %s; rc=$?; echo "rc=$rc"' % quote, ('rc=1',)),
            ('strict caller', 'set -u; source %s; rc=$?; echo "rc=$rc"' % quote, ('rc=1',)),
            ('unset BASH_SOURCE', 'set -u; unset BASH_SOURCE; source %s; rc=$?; echo "rc=$rc"' % quote, ('rc=1',)),
            ('inside a function', 'f() { source %s; echo "in-func $?"; }; f; echo caller-alive' % quote,
             ('in-func 1', 'caller-alive')),
        )
        for label, command, expected in cases:
            with self.subTest(case=label):
                result = self.invoke(['bash', '-c', command], self.environment())
                self.assert_refusal(result)
                for fragment in expected:
                    self.assertIn(fragment, result.stdout)
        self.assertEqual(self.snapshot(), before)

    def test_executed_stdin_and_dash_c_installs_still_work(self):
        for label, args, kwargs in (
            ('executed file', ['bash', INSTALLER], {}),
            ('piped stdin', ['bash'], {'input': INSTALLER.read_text()}),
            ('bash -c executed', ['bash', '-c', 'bash "$1"', 'install', INSTALLER], {}),
        ):
            with self.subTest(mode=label):
                result = self.invoke(args, self.environment(), **kwargs)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('Unio installed', result.stdout)
                self.assertTrue((self.bin_dir / 'unio').exists())
                self.assertTrue((self.conf_dir / 'agents.conf').exists())
                self.assert_installed_runtime_works()
        # Private operator configuration is preserved by a normal install.
        (self.conf_dir / 'agents.conf').write_text('mock=KEPT\n')
        result = self.invoke(['bash', INSTALLER], self.environment())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('keeping existing', result.stdout)
        self.assertEqual((self.conf_dir / 'agents.conf').read_text(), 'mock=KEPT\n')

    def assert_installed_runtime_works(self):
        runtime = self.bin_dir / 'unio'
        self.assertTrue(runtime.exists())
        self.assertGreater(os.stat(runtime).st_mode & 0o777, 0o600,
                           'published runtime must be executable')
        self.assertEqual(runtime.read_text(), engine_text())
        result = self.invoke(['bash', str(runtime), 'help'], self.environment(), timeout=90)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Unio', result.stdout)

    def test_replacement_keeps_open_reader_and_inflight_cli_stable(self):
        old_runtime = (
            '#!/usr/bin/env bash\n'
            'sleep 4\n'
            'echo INFLIGHT_COMPLETE > "$UNIO_TEST_OUT"\n'
            '# ' + 'OLD-RUNTIME-FILLER ' * 15000 + '\n'
            'exit 0\n'
        )
        runtime = self.bin_dir / 'unio'
        runtime.write_text(old_runtime)
        os.chmod(runtime, 0o755)
        marker = self.base / 'inflight marker.txt'
        reader = open(runtime, 'rb')
        self.addCleanup(reader.close)
        prefix = reader.read(4096)
        child = subprocess.Popen(['bash', str(runtime)], env=self.environment(
            UNIO_TEST_OUT=str(marker)), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(child.kill)
        time.sleep(0.5)
        result = self.invoke(['bash', INSTALLER], self.environment())
        self.assertEqual(result.returncode, 0, result.stderr)
        child_out, child_err = child.communicate(timeout=30)
        self.assertEqual(child.returncode, 0, child_err)
        self.assertEqual(marker.read_text(), 'INFLIGHT_COMPLETE\n')
        self.assertNotEqual(os.fstat(reader.fileno()).st_ino,
                            os.stat(runtime).st_ino,
                            'publication must replace the runtime entry, not reuse it')
        self.assert_old_inode_serves_only_old_bytes(reader, old_runtime.encode(), prefix)
        self.assertEqual(sorted(os.listdir(self.bin_dir)), ['unio'])
        self.assert_installed_runtime_works()

    def assert_old_inode_serves_only_old_bytes(self, reader, old_bytes, prefix):
        """The old inode must keep serving its own old bytes, never the new file.

        Some local filesystems (seen on WSL crosses of an open unlinked inode
        after publishing a much larger replacement) may refuse to re-serve
        paged-out regions of the old inode with ENODATA. Such an environmental
        refusal is tolerated here; serving any NEW byte is never tolerated.
        """
        self.assertEqual(prefix, old_bytes[:len(prefix)])
        try:
            self.assertEqual(prefix + reader.read(), old_bytes)
        except OSError as error:
            if error.errno != errno.ENODATA:
                raise
            served = 0
            for offset in range(0, len(old_bytes), 4096):
                try:
                    chunk = os.pread(reader.fileno(), 4096, offset)
                except OSError as probe_error:
                    self.assertEqual(probe_error.errno, errno.ENODATA)
                    continue
                self.assertEqual(chunk, old_bytes[offset:offset + 4096])
                served += len(chunk)
            self.assertGreater(served, 0, 'old inode must remain readable at all')

    def test_failure_before_publish_keeps_runtime_and_cleans_only_own_temp(self):
        runtime = self.bin_dir / 'unio'
        runtime.write_text('#!/usr/bin/env bash\nexit 7\n')
        os.chmod(runtime, 0o711)
        # Foreign leftovers from other invocations must never be touched.
        foreign_stage = self.bin_dir / '.unio-install-stage.foreignleftover'
        foreign_stage.mkdir()
        (foreign_stage / 'keep me').write_text('foreign payload\n')
        (self.bin_dir / '.unio.older.tmp.99').write_text('foreign tmp\n')
        before = self.snapshot()
        sizes = heredoc_payload_sizes()
        engine_size = len(engine_text())
        self.assertIn('UNIO_BIN_EOF', sizes, 'engine payload must be heredoc-written')
        self.assertEqual(sizes['UNIO_BIN_EOF'], engine_size)
        largest_other = max(size for name, size in sizes.items() if name != 'UNIO_BIN_EOF')
        blocks = largest_other // 1024 + 16
        self.assertGreater(engine_size, (blocks + 16) * 1024,
                           'engine payload must clearly exceed every earlier payload')
        result = self.invoke(['bash', '-c', 'ulimit -f %d; exec bash "$1"' % blocks,
                           'bounded', INSTALLER], self.environment())
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Unio installed', result.stdout)
        self.assertNotIn('refusing unsafe runtime path', result.stderr,
                         'failure must come from the bounded write, not a preflight refusal')
        self.assertTrue((self.conf_dir / 'lib/browser/server.py').exists(),
                        'installer must get past earlier payloads to reach the runtime')
        self.assertFalse((self.conf_dir / 'lib/lead_cooldown.py').exists(),
                         'installer must fail while publishing the runtime')
        self.assertFalse((self.completion_dir / 'unio').exists())
        self.assertEqual(sorted(os.listdir(self.bin_dir)),
                         ['.unio-install-stage.foreignleftover', '.unio.older.tmp.99', 'unio'])
        self.assertEqual(runtime.read_text(), '#!/usr/bin/env bash\nexit 7\n')
        self.assertEqual(oct(os.stat(runtime).st_mode & 0o777), oct(0o711))
        self.assertEqual((foreign_stage / 'keep me').read_text(), 'foreign payload\n')
        self.assertEqual((self.bin_dir / '.unio.older.tmp.99').read_text(), 'foreign tmp\n')

    def test_runtime_destination_preflight_refuses_non_regular_files(self):
        runtime = self.bin_dir / 'unio'
        runtime.mkdir()
        (runtime / 'unrelated').write_text('not a runtime\n')
        result = self.invoke(['bash', INSTALLER], self.environment())
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('Unio installed', result.stdout)
        self.assertIn('refusing unsafe runtime path', result.stderr)
        self.assertEqual((runtime / 'unrelated').read_text(), 'not a runtime\n')
        self.assertEqual(sorted(os.listdir(runtime)), ['unrelated'])


if __name__ == '__main__':
    unittest.main()
