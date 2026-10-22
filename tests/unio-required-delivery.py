#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Required delivery artifact contract tests.

Additive opt-in contract: tasks without ## Required artifacts retain
legacy behavior. All tests use installed mock-only native acceptance;
no provider calls.
"""
import hashlib
import importlib.util
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


class RequiredDeliveryContract(unittest.TestCase):
    """Parse and validate required artifact declarations."""

    def test_parse_empty_and_legacy(self):
        """No section means legacy; empty section is malformed."""
        spec = importlib.util.spec_from_file_location(
            'delivery', ROOT / 'tools/required-delivery.py')
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)

        # Legacy: no section
        self.assertIsNone(d.parse('## Task\nDo work.\n'))
        self.assertIsNone(d.parse(''))

        # Empty section is malformed
        with self.assertRaises(d.DeliveryError):
            d.parse('## Required artifacts\n')

        # Only comments and blank lines
        with self.assertRaises(d.DeliveryError):
            d.parse('## Required artifacts\n# comment\n')

    def test_parse_valid_artifacts(self):
        """Valid artifact lists."""
        spec = importlib.util.spec_from_file_location(
            'delivery', ROOT / 'tools/required-delivery.py')
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)

        # Single artifact
        result = d.parse('## Required artifacts\nreport.txt\n')
        self.assertEqual(result, ['report.txt'])

        # Multiple artifacts
        result = d.parse('## Required artifacts\nreport.txt\nsummary.md\ndata/results.json\n')
        self.assertEqual(result, ['report.txt', 'summary.md', 'data/results.json'])

        # With comments and blank lines
        result = d.parse('## Required artifacts\n# Delivery files\nreport.txt\n\nsummary.md\n')
        self.assertEqual(result, ['report.txt', 'summary.md'])

    def test_parse_invalid_artifacts(self):
        """Invalid artifact names and duplicates."""
        spec = importlib.util.spec_from_file_location(
            'delivery', ROOT / 'tools/required-delivery.py')
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)

        # Duplicate
        with self.assertRaises(d.DeliveryError):
            d.parse('## Required artifacts\nreport.txt\nreport.txt\n')

        # Invalid characters
        for name in ('report..txt', 'report/.txt', '../report.txt', '/absolute.txt',
                      'report$.txt', 'report#.txt', 'a' * 129):
            with self.subTest(name=name):
                with self.assertRaises(d.DeliveryError):
                    d.parse('## Required artifacts\n' + name + '\n')

        # Empty name
        with self.assertRaises(d.DeliveryError):
            d.validate_artifact_path('')

    def test_parse_multiple_sections(self):
        """Duplicate sections are refused."""
        spec = importlib.util.spec_from_file_location(
            'delivery', ROOT / 'tools/required-delivery.py')
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)

        with self.assertRaises(d.DeliveryError):
            d.parse('## Required artifacts\nreport.txt\n## Required artifacts\nother.txt\n')


class RequiredDeliveryIntegration(unittest.TestCase):
    """End-to-end required delivery with installed mock engine."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='required-delivery-', dir=FIXTURES)
        cls.base = Path(cls.tmp.name)
        cls.env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('UNIO_', 'GIT_', 'PYTHON')) and k != 'BASH_ENV'}
        cls.env.update(
            UNIO_BIN_DIR=str(cls.base / 'bin'),
            UNIO_CONF_DIR=str(cls.base / 'conf'),
            UNIO_COMPLETION_DIR=str(cls.base / 'completion'),
            UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_SYNC='0',
            UNIO_AUTO_OFF='0',
            UNIO_TIMEOUT='30',
            GIT_CONFIG_GLOBAL='/dev/null',
            GIT_CONFIG_NOSYSTEM='1',
            GIT_AUTHOR_NAME='fixture',
            GIT_COMMITTER_NAME='fixture',
            GIT_AUTHOR_EMAIL='fixture@example.invalid',
            GIT_COMMITTER_EMAIL='fixture@example.invalid',
            PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['bash', str(ROOT / 'unio-install.sh')],
                       env=cls.env, capture_output=True, check=True)
        cls.at = cls.base / 'bin' / 'unio'
        cls.root = cls.base / 'project'
        cls.repo = cls.root / 'repo'
        cls.repo.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', '-b', 'main'],
                       cwd=cls.repo, env=cls.env,
                       capture_output=True, check=True)
        subprocess.run(['git', 'commit', '--allow-empty', '-qm', 'initial'],
                       cwd=cls.repo, env=cls.env,
                       capture_output=True, check=True)
        subprocess.run([cls.at, 'init', 'mock'],
                       cwd=cls.repo, env=cls.env,
                       capture_output=True, check=True)
        cls.wt = cls.root / 'wt' / 'mock'
        cls.conf = cls.base / 'conf' / 'agents.conf'

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def raw(self, argv, cwd=None, code=0):
        cp = subprocess.run(list(map(str, argv)),
                            cwd=cwd or self.repo, env=self.env,
                            capture_output=True, text=True, timeout=100)
        if cp.returncode != code:
            raise AssertionError((argv, cp.returncode, code, cp.stdout, cp.stderr))
        return cp

    def call(self, *args, code=0):
        return self.raw([self.at] + list(args), code=code)

    def task(self, name, artifacts=None, mode='report-only', validate='$ true', scope='- *'):
        """Create a task file with optional required artifacts declaration."""
        tf = self.root / 'coord' / 'tasks' / (name + '.md')
        content = '# task\n'
        if mode:
            content += '## Outcome\n' + mode + '\n'
        if artifacts:
            content += '## Required artifacts\n'
            for artifact in artifacts:
                content += artifact + '\n'
        content += '## Allowed scope\n' + scope + '\n'
        content += '## Validate\n' + validate + '\n'
        tf.write_text(content)
        return tf

    def configure(self, source='printf "native report"'):
        self.conf.write_text('mock=' + source + '\n')

    def data(self, name):
        return json.loads(self.call('result', 'mock', name).stdout)

    def test_legacy_no_declaration_unknown_delivery(self):
        """Tasks without ## Required artifacts have Unknown/undeclared delivery."""
        self.configure()
        self.task('legacy-no-decl')
        self.call('run', 'mock', 'legacy-no-decl')
        self.call('verify', 'mock', 'legacy-no-decl')
        result = self.data('legacy-no-decl')
        # Legacy tasks have no delivery declaration
        self.assertNotIn('delivery', result)
        # Or delivery is explicitly Unknown
        if 'delivery' in result:
            self.assertEqual(result['delivery']['state'], 'Unknown')

    def test_empty_artifacts_malformed(self):
        """Empty required artifacts section is malformed."""
        self.configure()
        tf = self.task('empty-artifacts')
        tf.write_text(tf.read_text() + '\n## Required artifacts\n')
        cp = self.call('run', 'mock', 'empty-artifacts', code=2)
        self.assertIn('Required artifacts', cp.stderr)
        self.assertIn('malformed', cp.stderr.lower())

    def test_duplicate_artifacts_refused(self):
        """Duplicate artifact names are refused before provider call."""
        self.configure()
        tf = self.task('duplicate-artifacts', artifacts=['report.txt', 'report.txt'])
        cp = self.call('run', 'mock', 'duplicate-artifacts', code=2)
        self.assertIn('duplicate', cp.stderr.lower())

    def test_invalid_artifact_name_refused(self):
        """Invalid artifact names are refused before provider call."""
        self.configure()
        for name in ('../report.txt', '/absolute.txt', 'report$.txt'):
            with self.subTest(name=name):
                tf = self.task('invalid-name', artifacts=[name])
                cp = self.call('run', 'mock', 'invalid-name', code=2)
                self.assertIn('invalid', cp.stderr.lower())

    def test_source_writes_artifacts_complete_delivery(self):
        """Source writes all declared artifacts => complete delivery."""
        # Configure mock to write artifacts
        artifact_dir = self.wt / 'delivery'
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "report content" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'printf "summary content" > "$UNIO_DELIVERY_DIR/summary.md" && '
                  'printf "native report"')
        self.configure(source)
        self.task('complete-delivery', artifacts=['report.txt', 'summary.md'])
        self.call('run', 'mock', 'complete-delivery')
        self.call('verify', 'mock', 'complete-delivery')
        result = self.data('complete-delivery')
        # Delivery should be complete
        self.assertIn('delivery', result)
        self.assertEqual(result['delivery']['state'], 'complete')
        self.assertEqual(result['delivery']['artifact_count'], 2)

    def test_source_missing_artifact_incomplete_delivery(self):
        """Source exits zero but missing artifact => incomplete delivery, not ready."""
        # Configure mock to write only one artifact
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "report content" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'printf "acknowledged"')
        self.configure(source)
        self.task('incomplete-delivery', artifacts=['report.txt', 'summary.md'])
        self.call('run', 'mock', 'incomplete-delivery')
        self.call('verify', 'mock', 'incomplete-delivery', code=1)
        result = self.data('incomplete-delivery')
        # Delivery should be incomplete
        self.assertIn('delivery', result)
        self.assertEqual(result['delivery']['state'], 'incomplete')
        self.assertEqual(result['delivery']['artifact_count'], 1)
        self.assertEqual(result['delivery']['missing_artifacts'], ['summary.md'])
        # Not ready for human review
        self.assertFalse(result.get('ready_for_human_review', False))

    def test_source_nonzero_exit_partial_artifacts(self):
        """Source exits nonzero => partial artifacts preserved, delivery incomplete."""
        # Configure mock to fail and write one artifact
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "partial report" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'exit 7')
        self.configure(source)
        self.task('failed-source', artifacts=['report.txt', 'summary.md'])
        cp = self.call('run', 'mock', 'failed-source', code=7)
        self.call('verify', 'mock', 'failed-source', code=1)
        result = self.data('failed-source')
        # Process failed
        self.assertEqual(result['process']['exit_code'], 7)
        # Delivery should show partial artifacts
        self.assertIn('delivery', result)
        self.assertEqual(result['delivery']['state'], 'incomplete')
        self.assertEqual(result['delivery']['artifact_count'], 1)

    def test_artifact_bounds_oversized(self):
        """Oversized artifact fails validation."""
        # Write an oversized artifact (262145 bytes > 262144 limit)
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'python3 -c "print(chr(120)*262145, end=\\"\\")" > "$UNIO_DELIVERY_DIR/report.txt"')
        self.configure(source)
        self.task('oversized-artifact', artifacts=['report.txt'])
        self.call('run', 'mock', 'oversized-artifact')
        self.call('verify', 'mock', 'oversized-artifact', code=1)
        result = self.data('oversized-artifact')
        self.assertIn('delivery', result)
        # Oversized artifact should fail validation
        self.assertEqual(result['delivery']['state'], 'incomplete')

    def test_artifact_bounds_utf8(self):
        """Non-UTF-8 artifact fails validation."""
        # Write invalid UTF-8
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "\\xff\\xfe" > "$UNIO_DELIVERY_DIR/report.txt"')
        self.configure(source)
        self.task('invalid-utf8-artifact', artifacts=['report.txt'])
        self.call('run', 'mock', 'invalid-utf8-artifact')
        self.call('verify', 'mock', 'invalid-utf8-artifact', code=1)
        result = self.data('invalid-utf8-artifact')
        self.assertIn('delivery', result)
        self.assertEqual(result['delivery']['state'], 'incomplete')

    def test_artifact_tamper_stale_delivery(self):
        """Artifact modification after verification makes delivery stale."""
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "original content" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'printf "native report"')
        self.configure(source)
        self.task('tamper-test', artifacts=['report.txt'])
        self.call('run', 'mock', 'tamper-test')
        self.call('verify', 'mock', 'tamper-test')
        result = self.data('tamper-test')
        self.assertEqual(result['delivery']['state'], 'complete')

        # Tamper with the artifact
        delivery_dir = self.root / 'coord' / 'results' / 'mock' / ('tamper-test.outcomes')
        if not delivery_dir.exists():
            delivery_dir = self.wt / 'coord' / 'results' / 'mock' / ('tamper-test.outcomes')
        for run_dir in delivery_dir.iterdir():
            if run_dir.is_dir():
                for artifact in (run_dir / 'delivery' / 'report.txt', run_dir / 'report.txt'):
                    if artifact.exists():
                        artifact.write_text('tampered content')
                        break

        # Re-verify should show stale
        self.call('verify', 'mock', 'tamper-test', code=1)
        result = self.data('tamper-test')
        self.assertIn('delivery', result)
        self.assertEqual(result['delivery']['state'], 'stale')

    def test_delivery_directory_exposed(self):
        """UNIO_DELIVERY_DIR is exposed to Source."""
        source = ('test -n "$UNIO_DELIVERY_DIR" && '
                  'mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "test" > "$UNIO_DELIVERY_DIR/test.txt"')
        self.configure(source)
        self.task('dir-exposed', artifacts=['test.txt'])
        cp = self.call('run', 'mock', 'dir-exposed')
        self.assertIn('UNIO_DELIVERY_DIR', cp.stdout + cp.stderr)

    def test_artifact_count_bound(self):
        """More than 32 artifacts is refused."""
        self.configure()
        artifacts = [f'artifact{i}.txt' for i in range(33)]
        tf = self.task('too-many-artifacts', artifacts=artifacts)
        cp = self.call('run', 'mock', 'too-many-artifacts', code=2)
        self.assertIn('bound', cp.stderr.lower())

    def test_report_only_with_artifacts(self):
        """Report-only task with required artifacts: both must be present."""
        source = ('mkdir -p "$UNIO_DELIVERY_DIR" && '
                  'printf "report content" > "$UNIO_DELIVERY_DIR/report.txt" && '
                  'printf "native report"')
        self.configure(source)
        self.task('report-only-artifacts', artifacts=['report.txt'], mode='report-only')
        self.call('run', 'mock', 'report-only-artifacts')
        self.call('verify', 'mock', 'report-only-artifacts')
        result = self.data('report-only-artifacts')
        # Both report channel and artifacts must be present
        self.assertIn('delivery', result)
        self.assertEqual(result['delivery']['state'], 'complete')

    def test_implementation_with_artifacts(self):
        """Implementation task with required artifacts."""
        adapters = self.base / 'conf' / 'lib' / 'adapters'
        self.configure('python3 ' + shlex.quote(str(adapters / 'copilot-worker.py')))
        self.task('impl-artifacts', artifacts=['report.txt'], mode='implementation')
        cp = self.call('run', 'mock', 'impl-artifacts', code=2)
        self.assertIn('blocked', cp.stderr.lower())


class RequiredDeliveryBinding(unittest.TestCase):
    """Binding and hash validation for required artifacts."""

    def test_binding_includes_artifacts(self):
        """Delivery binding includes artifact metadata."""
        spec = importlib.util.spec_from_file_location(
            'delivery', ROOT / 'tools/required-delivery.py')
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)

        # Create a binding
        binding = d.create_binding(
            task='test-task',
            worker='test-worker',
            run='a' * 32,
            task_sha256='b' * 64,
            command_sha256='c' * 64,
            prompt_sha256='d' * 64,
            route='vibe',
            started_at='2026-10-22T00:00:00Z',
            artifacts=['report.txt', 'summary.md'])

        self.assertEqual(binding['task'], 'test-task')
        self.assertEqual(binding['worker'], 'test-worker')
        self.assertEqual(binding['run'], 'a' * 32)
        self.assertEqual(binding['artifacts'], ['report.txt', 'summary.md'])
        self.assertEqual(binding['schema_version'], 1)

    def test_artifact_hash_validation(self):
        """Artifact hashes are validated against binding."""
        spec = importlib.util.spec_from_file_location(
            'delivery', ROOT / 'tools/required-delivery.py')
        d = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(d)

        with tempfile.TemporaryDirectory(prefix='hash-test-', dir=FIXTURES) as tmp:
            tmp = Path(tmp)
            delivery_dir = tmp / 'delivery'
            delivery_dir.mkdir()
            (delivery_dir / 'report.txt').write_text('test content')

            # Valid hash
            expected_hash = hashlib.sha256(b'test content').hexdigest()
            self.assertTrue(d.validate_artifact(
                delivery_dir / 'report.txt',
                expected_hash,
                262144))

            # Invalid hash
            self.assertFalse(d.validate_artifact(
                delivery_dir / 'report.txt',
                '0' * 64,
                262144))


if __name__ == '__main__':
    unittest.main(verbosity=2)
