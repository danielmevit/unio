#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional attribution/origin terms in NOTICE.
"""Failed/interrupted report-only handoff recovery contract.

Real mock-only native lifecycle (install + `unio init mock`); no provider
calls. Strict verify/review/readness defaults must stay refused for a failed
or missing Source; only `unio handoff` may publish an explicitly incomplete
context packet from genuinely bound material.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(os.environ.get('TMPDIR', str(ROOT / 'tmp')))
FIXTURES.mkdir(parents=True, exist_ok=True)


class HandoffIncompleteIntegration(unittest.TestCase):
    """End-to-end report-only handoff recovery with the installed mock engine."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='handoff-incomplete-', dir=FIXTURES)
        cls.base = Path(cls.tmp.name)
        cls.env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('UNIO_', 'GIT_', 'PYTHON')) and k != 'BASH_ENV'}
        cls.env.update(
            UNIO_BIN_DIR=str(cls.base / 'bin'), UNIO_CONF_DIR=str(cls.base / 'conf'),
            UNIO_COMPLETION_DIR=str(cls.base / 'completion'),
            UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
            UNIO_TIMEOUT='30', GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
            GIT_AUTHOR_NAME='fixture', GIT_COMMITTER_NAME='fixture',
            GIT_AUTHOR_EMAIL='fixture@example.invalid',
            GIT_COMMITTER_EMAIL='fixture@example.invalid', PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['bash', str(ROOT / 'unio-install.sh')], env=cls.env,
                       capture_output=True, check=True, timeout=100)
        cls.at = cls.base / 'bin' / 'unio'
        cls.root = cls.base / 'project'
        cls.repo = cls.root / 'repo'
        cls.repo.mkdir(parents=True)
        cls.raw(['git', 'init', '-q', '-b', 'main'])
        cls.raw(['git', 'commit', '--allow-empty', '-qm', 'initial'])
        cls.raw([cls.at, 'init', 'mock'])
        cls.wt = cls.root / 'wt' / 'mock'
        cls.conf = cls.base / 'conf' / 'agents.conf'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def raw(cls, argv, cwd=None):
        return subprocess.run(list(map(str, argv)), cwd=str(cwd or cls.repo),
                              env=cls.env, capture_output=True, text=True, timeout=100)

    def call(self, *args, code=0):
        cp = self.raw([self.at] + list(args))
        self.assertEqual((cp.returncode, cp.stdout, cp.stderr), (code, cp.stdout, cp.stderr),
                        (args, cp.returncode, cp.stdout, cp.stderr))
        return cp

    def fails(self, *args):
        cp = self.raw([self.at] + list(args))
        self.assertNotEqual(cp.returncode, 0, (args, cp.stdout, cp.stderr))
        return cp

    def configure(self, source, reviewer=None):
        self.conf.write_text('mock=' + source + '\n')
        if reviewer:
            with self.conf.open('a') as stream:
                stream.write('rev=' + reviewer + '\n')

    def data(self, name):
        return json.loads(self.raw([self.at, 'result', 'mock', name]).stdout)

    def task(self, name, artifacts, mode='report-only'):
        tf = self.root / 'coord' / 'tasks' / (name + '.md')
        content = ('# task\n' + ('## Outcome\n' + mode + '\n' if mode else ''))
        if artifacts:
            content += '## Required artifacts\n' + ''.join(a + '\n' for a in artifacts)
        content += '## Allowed scope\n- *\n## Validate\n$ true\n'
        tf.write_text(content)
        return tf

    def outcome_path(self, name, filename):
        run_id = self.data(name)['outcome']['run_id']
        return (self.root / 'coord' / 'results' / 'mock'
                / (name + '.outcomes') / run_id / filename)

    def test_success_unchanged_complete_report(self):
        self.configure('mkdir -p "$UNIO_DELIVERY_DIR" && '
                        'printf "full artifact" > "$UNIO_DELIVERY_DIR/report.txt" && '
                        'printf "native report"')
        name = 'recovery-success'
        self.task(name, ['report.txt'])
        self.call('run', 'mock', name)
        self.call('verify', 'mock', name)
        cp = self.raw([self.at, 'handoff', 'mock', name])
        self.assertEqual(cp.returncode, 0, cp.stderr)
        packet = Path(cp.stdout.strip().splitlines()[0])
        report = (packet / 'report.md').read_bytes()
        self.assertIn(b'COMPLETE SOURCE REPORT', report)
        self.assertNotIn(b'RECOVERY', report)
        self.assertNotIn(b'MISSING ARTIFACT', report)
        self.assertEqual((packet / 'delivery' / 'report.txt').read_bytes(), b'full artifact')
        handoff = (packet / 'HANDOFF.md').read_text()
        self.assertNotIn('recovery packet', handoff)

    def test_failed_source_partial_report_and_artifacts(self):
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "partial delivery" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'printf "real partial report" && exit 7')
        self.configure(source, reviewer='true')
        name = 'recovery-partial'
        self.task(name, ['report.txt', 'summary.md'])
        self.call('run', 'mock', name, code=7)
        # Strict defaults still refuse the failed/missing delivery everywhere.
        self.call('verify', 'mock', name, code=1)
        self.fails('review', 'mock', name, 'rev')
        d = self.data(name)
        self.assertEqual(d['process'], dict(state='failed', exit_code=7,
                                            revision=d['process']['revision']))
        self.assertFalse(d['ready_for_human_review'])
        self.assertEqual(d['outcome_current']['state'], 'invalid')
        # Handoff publishes a clearly incomplete context packet.
        cp = self.raw([self.at, 'handoff', 'mock', name])
        self.assertEqual(cp.returncode, 0, cp.stderr)
        packet = Path(cp.stdout.strip().splitlines()[0])
        report = (packet / 'report.md').read_bytes()
        self.assertIn(b'INCOMPLETE RECOVERY SOURCE (recorded failure preserved)', report)
        self.assertIn(b'"exit_code": 7', report)
        self.assertIn(b'INCOMPLETE SOURCE REPORT', report)
        self.assertIn(b'real partial report', report)
        self.assertNotIn(b'\nCOMPLETE SOURCE REPORT\n', report)
        self.assertIn(b'ARTIFACT report.txt\npartial delivery\nEND ARTIFACT', report)
        self.assertIn(b'MISSING ARTIFACT summary.md', report)
        self.assertEqual((packet / 'delivery' / 'report.txt').read_bytes(), b'partial delivery')
        self.assertFalse((packet / 'delivery' / 'summary.md').exists())
        handoff = (packet / 'HANDOFF.md').read_text()
        self.assertIn('incomplete recovery packet', handoff)
        # The recorded truth stays: original failure, never ready.
        packed = json.loads((packet / 'result.json').read_text())
        self.assertEqual(packed['process']['exit_code'], 7)
        self.assertFalse(packed['ready_for_human_review'])
        self.assertEqual(packed['delivery']['state'], 'incomplete')
        self.assertEqual(packed['outcome_current']['state'], 'invalid')
        self.assertEqual(self.data(name)['process']['exit_code'], 7)
        self.assertFalse(self.data(name)['ready_for_human_review'])

    def test_recovery_refuses_changed_evidence(self):
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "partial delivery" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'printf "real partial report" && exit 7')
        self.configure(source)
        name = 'recovery-changed'
        self.task(name, ['report.txt'])
        self.call('run', 'mock', name, code=7)
        cp0 = self.raw([self.at, 'handoff', 'mock', name])
        self.assertEqual(cp0.returncode, 0, cp0.stderr)
        # Tampered bound report refuses a recovery packet.
        report = self.outcome_path(name, 'report.txt')
        original = report.read_bytes()
        report.chmod(0o600)
        report.write_text('tampered\n')
        self.call('handoff', 'mock', name, code=2)
        # Byte-identical restoration keeps genuine binding and recovers again.
        report.write_bytes(original)
        self.assertEqual(self.raw([self.at, 'handoff', 'mock', name]).returncode, 0)
        # A changed snapshot (late worktree content) refuses; removing it
        # restores the snapshot and recovery works again.
        marker = self.wt / 'changed-by-failure.txt'
        marker.write_text('late worktree edit\n')
        try:
            cp = self.raw([self.at, 'handoff', 'mock', name])
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn('changed since dispatch', cp.stdout + cp.stderr)
        finally:
            marker.unlink()
        self.assertEqual(self.raw([self.at, 'handoff', 'mock', name]).returncode, 0)

    def test_recovery_refuses_unsafe_delivery_artifact_evidence(self):
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "partial delivery" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'printf "real partial report" && exit 7')
        self.configure(source)
        for name, mutate in (('recovery-tampered', 'bytes'), ('recovery-linked', 'symlink')):
            with self.subTest(name=name):
                self.task(name, ['report.txt'])
                self.call('run', 'mock', name, code=7)
                self.assertEqual(self.raw([self.at, 'handoff', 'mock', name]).returncode, 0)
                published_before = list((self.root / 'coord' / 'handoffs' / 'mock'
                                         / name).iterdir())
                run_id = self.data(name)['outcome']['run_id']
                artifact = (self.root / 'coord' / 'results' / 'mock'
                            / (name + '.outcomes') / run_id / 'delivery' / 'report.txt')
                if mutate == 'bytes':
                    artifact.chmod(0o600)
                    artifact.write_text('tampered delivery\n')
                else:
                    target = self.base / (name + '-outside')
                    target.write_text('outside evidence\n')
                    artifact.unlink()
                    artifact.symlink_to(target)
                self.call('handoff', 'mock', name, code=2)
                # Unproven evidence refuses rather than publishing a packet.
                self.assertEqual(list((self.root / 'coord' / 'handoffs' / 'mock'
                                       / name).iterdir()), published_before)

    def test_missing_report_is_labeled_not_fabricated(self):
        # Nonzero Source that never produced report text.
        self.configure('exit 7')
        name = 'recovery-missing'
        self.task(name, ['report.txt'])
        self.call('run', 'mock', name, code=7)
        self.call('verify', 'mock', name, code=1)
        d = self.data(name)
        self.assertIsNone(d['outcome']['report_sha256'])
        self.assertTrue(d['outcome']['error'])
        cp = self.raw([self.at, 'handoff', 'mock', name])
        self.assertEqual(cp.returncode, 0, cp.stderr)
        packet = Path(cp.stdout.strip().splitlines()[0])
        report = (packet / 'report.md').read_bytes()
        self.assertIn(b'INCOMPLETE RECOVERY SOURCE (recorded failure preserved)', report)
        self.assertIn(b'MISSING SOURCE REPORT', report)
        self.assertIn(b'report_artifact_unavailable', report)
        self.assertNotIn(b'\nCOMPLETE SOURCE REPORT\n', report)
        # No raw log text is scraped into the packet.
        self.assertNotIn(b'\nARTIFACT ', report)
        handoff = (packet / 'HANDOFF.md').read_text()
        self.assertIn('incomplete recovery packet', handoff)

    def test_running_and_stale_recovery_refused_offline(self):
        # Frozen engine definitions: interrupted (running) and stale recorded
        # states never become recovery provenance.
        engine = (ROOT / 'unio-install.sh').read_text().split(" <<'QUALITY_PY'\n", 1)[1] \
            .split('\nQUALITY_PY\n', 1)[0]
        definitions = engine.rsplit('\ntry:\n    cmd,*a=sys.argv[1:]', 1)[0]
        ns = {'__name__': 'offline_quality_fixture'}
        exec(compile(definitions, 'QUALITY_PY', 'exec'), ns)
        name = 'offline-recovery'
        tf = self.task(name, ['report.txt'])
        root = str(self.root)
        rev = ns['snapshot'](root, 'mock', name)
        o = ns['outcome_start'](root, 'mock', name, rev, 'cmd', str(tf), 'native')
        directory = Path(ns['outcome_directory'](root, 'mock', name, o['run_id']))
        (directory / 'incoming.txt').write_text('partial unfinished report')
        d = dict(outcome=o, dispatch_revision=rev)
        for state in ('running', 'succeeded', None):
            if state is None:
                d['process'] = dict(state='failed', exit_code=0, revision=rev)
            else:
                d['process'] = dict(state=state, exit_code=None, revision=rev)
            with self.subTest(state=state):
                with self.assertRaises(ValueError):
                    ns['report_evidence'](root, 'mock', name, d, rev, recovery=True)
        # A current terminal failure with a genuinely bound report recovers.
        d['process'] = dict(state='failed', exit_code=7, revision=rev)
        ns['outcome_finish'](root, 'mock', name, d)
        self.assertIsNone(o['error'])
        bound, data = ns['report_evidence'](root, 'mock', name, d, rev, recovery=True)
        self.assertEqual(data, b'partial unfinished report')
        # Unbound content next to an unbound missing report still refuses.
        artifact = Path(ns['outcome_directory'](root, 'mock', name, o['run_id'])) / 'report.txt'
        artifact.unlink()
        o2 = ns['outcome_start'](root, 'mock', name, rev, 'cmd', str(tf), 'native')
        directory2 = Path(ns['outcome_directory'](root, 'mock', name, o2['run_id']))
        d2 = dict(outcome=o2, dispatch_revision=rev,
                  process=dict(state='failed', exit_code=7, revision=rev))
        ns['outcome_finish'](root, 'mock', name, d2)
        self.assertTrue(o2['error'])
        stray = directory2 / 'report.txt'
        if stray.exists():
            stray.chmod(0o600)
        stray.write_text('unbound content\n')
        with self.assertRaises(ValueError):
            ns['report_evidence'](root, 'mock', name, d2, rev, recovery=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
