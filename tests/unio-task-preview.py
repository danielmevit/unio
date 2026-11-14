#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Opt-in task-scope preview tests (docs/TASK-PREVIEW.md).

Offline installed-engine fixtures only: mock providers, isolated temp
projects, never real coord stores or global config. Proves preview
before first Source, classified paths, annotations, fenced examples,
safe JSON filenames, STOP read-only, busy refusal, zero Validate
execution (sentinel vs old engine), no result/report/store writes, and
that unflagged verify still runs Validate.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = 'PREVIEW_SENTINEL'
NOTE = ('preview is an observation; Validate commands were NOT run; '
        'provider calls 0; admission, delivery and acceptance are NOT '
        'established; this does not claim a future dispatch is safe')


class TaskPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='task preview install ')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.install = Path(cls.temp.name)
        cls.env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('UNIO_', 'PYTHON', 'GIT_')) and k != 'BASH_ENV'}
        tmp = cls.install / 'tmp'
        tmp.mkdir()
        cls.env.update(UNIO_BIN_DIR=str(cls.install / 'bin'),
                       UNIO_CONF_DIR=str(cls.install / 'conf'),
                       UNIO_COMPLETION_DIR=str(cls.install / 'completion'),
                       UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0',
                       UNIO_CLI_UPDATES_OFFLINE='1',
                       UNIO_TIMEOUT='30', GIT_CONFIG_GLOBAL='/dev/null',
                       GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='mock',
                       GIT_COMMITTER_NAME='mock', GIT_AUTHOR_EMAIL='mock@test.invalid',
                       GIT_COMMITTER_EMAIL='mock@test.invalid',
                       PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(tmp),
                       LC_ALL='C.UTF-8', LANG='C.UTF-8')
        copy = cls.install / 'copied standalone installer.sh'
        copy.write_bytes((ROOT / 'unio-install.sh').read_bytes())
        p = subprocess.run(['bash', str(copy)], cwd=cls.install, env=cls.env,
                           capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, p.stderr
        cls.engine = str(cls.install / 'bin' / 'unio')
        cls.old_engine = str(cls.install / 'old-verify-unio')
        text = Path(cls.engine).read_text(encoding='utf-8')
        # Frozen 0.5.30 dispatch drops extra argv, so --preview still ran
        # Validate. Keep a copy of that arm as the sentinel old engine.
        old = text.replace(
            '''  verify)
    _preview=0
    for _preview_arg in "${@:2}"; do
      [ "$_preview_arg" = --preview ] && _preview=1
    done
    if [ "$_preview" = 1 ]; then cmd_verify_preview "${@:2}"
    else cmd_verify "${2:-}" "${3:-}"; fi;;''',
            '  verify)   cmd_verify "${2:-}" "${3:-}";;\n',
            1)
        assert old != text, 'old-engine sentinel requires the preview dispatch arm'
        Path(cls.old_engine).write_text(old, encoding='utf-8')
        os.chmod(cls.old_engine, 0o700)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(
            prefix='task preview project ', dir=self.__class__.env['TMPDIR'])
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'project' / 'repo'
        self.repo.mkdir(parents=True)
        self.env = dict(self.__class__.env)
        self.env['UNIO_CONF_DIR'] = str(self.root / 'conf')
        self.env['TMPDIR'] = str(self.root)
        self.sentinel = self.root / SENTINEL
        conf = self.root / 'conf'
        conf.mkdir()
        shutil.copytree(self.install / 'conf' / 'templates', conf / 'templates')
        self.conf = conf / 'agents.conf'
        self.conf.write_text("mock=bash -c 'exit 0'\n")
        self.call(['git', 'init', '-q', '-b', 'dev'])
        (self.repo / 'baseline.txt').write_text('unchanged baseline\n')
        self.call(['git', 'add', 'baseline.txt'])
        self.call(['git', 'commit', '-qm', 'initial'])
        self.unio('init', 'mock')
        self.coord = self.root / 'project' / 'coord'
        self.tasks = self.coord / 'tasks'
        self.wt = self.root / 'project' / 'wt' / 'mock'
        self.reports = self.coord / 'reports'
        self.results = self.coord / 'results'

    def call(self, args, code=0, env=None, cwd=None, engine=None):
        p = subprocess.run(args, cwd=cwd or self.repo, env=env or self.env,
                           capture_output=True, text=True, timeout=60)
        if code is not None:
            self.assertEqual(p.returncode, code, (args, p.stdout[-4000:], p.stderr[-2000:]))
        return p

    def unio(self, *args, code=0, engine=None):
        return self.call([engine or self.engine, *args], code=code)

    def task(self, name, scope=('- hello.txt',), validate=('$ true',),
             extra='', artifacts=None, outcome=None):
        parts = ['# Task %s\n' % name, '## Goal\ntest\n']
        if extra:
            parts.append(extra)
        if outcome:
            parts.append('## Outcome\n%s\n' % outcome)
        parts.append('## Allowed scope\n')
        parts.extend(s + '\n' for s in scope)
        parts.append('## Validate\n')
        parts.extend(v + '\n' for v in validate)
        if artifacts is not None:
            parts.append('## Required artifacts\n')
            parts.extend(a + '\n' for a in artifacts)
        (self.tasks / (name + '.md')).write_text(''.join(parts), encoding='utf-8')

    def snapshot_store(self):
        def digest(path):
            if not path.exists():
                return None
            items = []
            for child in sorted(path.rglob('*')):
                rel = str(child.relative_to(path))
                if child.is_file() and not child.is_symlink():
                    items.append((rel, child.read_bytes()))
            return items
        ledger = self.reports / 'ledger.jsonl'
        return {
            'reports': digest(self.reports),
            'results': digest(self.results),
            'ledger': ledger.read_bytes() if ledger.exists() else b'',
            'task': (self.tasks / 'preview.md').read_bytes()
            if (self.tasks / 'preview.md').exists() else b'',
        }

    def preview(self, task='preview', code=0, json_out=False):
        cmd = ['verify', 'mock', task, '--preview']
        if json_out:
            cmd.append('--json')
        return self.unio(*cmd, code=code)

    def sentinel_validate(self):
        # Absolute path outside the worktree so unflagged verify is not
        # poisoned by an untracked sentinel file.
        return "python3 -B -c \"open(%r, 'w').write('ran')\"" % str(self.sentinel)

    def test_help_and_completion(self):
        help_text = self.unio('help').stdout
        self.assertIn('--preview', help_text)
        self.assertIn('docs/TASK-PREVIEW.md', help_text)
        completion = (self.install / 'completion' / 'unio').read_text(encoding='utf-8')
        self.assertIn('--preview --json', completion)
        self.assertIn('verify)', completion)

    def test_preview_before_first_source_zero_changes(self):
        self.task('preview')
        before = self.snapshot_store()
        p = self.preview('preview', json_out=True, code=0)
        doc = json.loads(p.stdout)
        self.assertEqual(doc['kind'], 'task-preview')
        self.assertEqual(doc['schema_version'], 1)
        self.assertTrue(doc['observation'])
        self.assertFalse(doc['commands_executed'])
        self.assertFalse(doc['validate_executed'])
        self.assertEqual(doc['provider_calls'], 0)
        self.assertFalse(doc['admission_established'])
        self.assertFalse(doc['delivery_established'])
        self.assertFalse(doc['acceptance_established'])
        self.assertFalse(doc['future_dispatch_safe'])
        self.assertEqual(doc['scope_status'], 'in_scope')
        self.assertEqual(doc['note'], NOTE)
        self.assertNotIn('PASS', p.stdout)
        self.assertEqual(doc['changed']['committed'], [])
        self.assertEqual(doc['out_of_scope'], [])
        self.assertEqual(self.snapshot_store()['reports'], before['reports'])
        self.assertEqual(self.snapshot_store()['results'], before['results'])
        self.assertEqual(self.snapshot_store()['ledger'], before['ledger'])
        self.assertFalse(self.sentinel.exists())
        self.assertFalse((self.wt / SENTINEL).exists())

    def test_inherited_committed_out_of_scope(self):
        self.task('preview', scope=('- hello.txt',))
        (self.wt / 'secret.txt').write_text('nope\n')
        self.call(['git', 'add', 'secret.txt'], cwd=self.wt)
        self.call(['git', 'commit', '-qm', 'inherited'], cwd=self.wt)
        p = self.preview('preview', json_out=True, code=1)
        doc = json.loads(p.stdout)
        self.assertEqual(doc['scope_status'], 'mismatch')
        self.assertIn('secret.txt', doc['changed']['committed'])
        self.assertIn('secret.txt', doc['out_of_scope'])
        self.assertIn('scope_mismatch', doc['reasons'])
        self.assertNotIn('verdict  : PASS', p.stdout)
        self.assertNotIn('verdict  : FAIL', p.stdout)

    def test_staged_unstaged_untracked_and_rename(self):
        self.task('preview', scope=('- hello.txt', '- in-scope.txt', '- renamed-in.txt'))
        (self.wt / 'hello.txt').write_text('ok\n')
        self.call(['git', 'add', 'hello.txt'], cwd=self.wt)
        self.call(['git', 'commit', '-qm', 'hello'], cwd=self.wt)
        (self.wt / 'renamed-in.txt').write_text('moved\n')
        self.call(['git', 'add', 'renamed-in.txt'], cwd=self.wt)
        self.call(['git', 'commit', '-qm', 'rename-src'], cwd=self.wt)
        (self.wt / 'in-scope.txt').write_text('staged\n')
        self.call(['git', 'add', 'in-scope.txt'], cwd=self.wt)
        (self.wt / 'hello.txt').write_text('unstaged edit\n')
        (self.wt / 'untracked.txt').write_text('loose\n')
        self.call(['git', 'mv', 'renamed-in.txt', 'renamed-out.txt'], cwd=self.wt)
        p = self.preview('preview', json_out=True, code=1)
        doc = json.loads(p.stdout)
        self.assertIn('hello.txt', doc['changed']['committed'] + doc['changed']['unstaged'])
        self.assertIn('in-scope.txt', doc['changed']['staged'])
        self.assertIn('untracked.txt', doc['changed']['untracked'])
        self.assertIn('renamed-out.txt', doc['changed']['staged'] + doc['out_of_scope'])
        self.assertTrue(doc['out_of_scope'])

    def test_annotations_and_fenced_examples(self):
        extra = ('Example only:\n\n```text\n- secret/out-of-scope.txt\n'
                 '$ python3 -c "open(%r,\\"w\\").write(\\"ran\\")"\n```\n'
                 % str(self.sentinel))
        self.task('preview',
                  scope=('- hello.txt (only layout adjustments)',),
                  validate=('$ true',),
                  extra=extra)
        (self.wt / 'hello.txt').write_text('ok\n')
        self.call(['git', 'add', 'hello.txt'], cwd=self.wt)
        self.call(['git', 'commit', '-qm', 'hello'], cwd=self.wt)
        p = self.preview('preview', json_out=True, code=0)
        doc = json.loads(p.stdout)
        self.assertEqual(doc['scope_patterns'], ['hello.txt'])
        self.assertTrue(any('stripped annotation' in w and 'hello.txt' in w
                            for w in doc['scope_warnings']))
        self.assertNotIn('secret/out-of-scope.txt', doc['scope_patterns'])
        self.assertFalse(any(SENTINEL in c for c in doc['validate_commands']))
        self.assertFalse(self.sentinel.exists())
        self.assertFalse((self.wt / SENTINEL).exists())

    def test_filenames_spaces_and_non_ascii_json(self):
        self.task('preview', scope=('- "my file.txt"', '- café.txt'))
        (self.wt / 'my file.txt').write_text('space\n')
        (self.wt / 'café.txt').write_text('unicode\n')
        self.call(['git', 'add', 'my file.txt', 'café.txt'], cwd=self.wt)
        self.call(['git', 'commit', '-qm', 'names'], cwd=self.wt)
        p = self.preview('preview', json_out=True, code=0)
        doc = json.loads(p.stdout)
        self.assertIn('my file.txt', doc['scope_patterns'])
        self.assertIn('café.txt', doc['changed']['committed'])
        self.assertIn('\\u', p.stdout)  # ensure_ascii JSON escaping
        json.loads(p.stdout)  # strict parse

    def test_missing_scope_and_validate(self):
        self.task('preview', scope=(), validate=())
        p = self.preview('preview', json_out=True, code=2)
        doc = json.loads(p.stdout)
        self.assertEqual(doc['scope_status'], 'incomplete')
        self.assertIn('missing_scope', doc['reasons'])
        self.assertIn('missing_validate', doc['reasons'])

    def test_invalid_required_artifacts(self):
        self.task('preview', artifacts=['../escape.md'])
        p = self.preview('preview', json_out=True, code=2)
        doc = json.loads(p.stdout)
        self.assertEqual(doc['scope_status'], 'incomplete')
        self.assertIn('invalid_required_artifact_syntax', doc['reasons'])

    def test_report_only_unsupported(self):
        self.task('preview', outcome='report-only', artifacts=['summary.md'])
        p = self.preview('preview', json_out=True, code=2)
        doc = json.loads(p.stdout)
        self.assertEqual(doc['scope_status'], 'unsupported')
        self.assertEqual(doc['outcome_mode'], 'report-only')
        self.assertIn('report_only_not_predicted', doc['reasons'])
        self.assertFalse(doc['validate_executed'])

    def test_stop_read_only(self):
        self.task('preview')
        (self.coord / 'STOP').write_text('paused\n')
        p = self.preview('preview', json_out=True, code=0)
        doc = json.loads(p.stdout)
        self.assertTrue(doc['stop_active'])
        self.assertEqual(doc['scope_status'], 'in_scope')
        self.assertTrue((self.coord / 'STOP').exists())
        self.assertEqual((self.coord / 'STOP').read_text(), 'paused\n')

    def test_busy_refusal(self):
        self.task('preview')
        lock = self.coord / '.locks' / 'mock.lock'
        lock.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(lock), os.O_RDWR | os.O_CREAT)
        try:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            p = self.preview('preview', json_out=True, code=2)
            doc = json.loads(p.stdout)
            self.assertEqual(doc['scope_status'], 'busy')
            self.assertIn('worker_busy', doc['reasons'])
            self.assertIn('busy', p.stderr)
        finally:
            os.close(fd)

    def test_sentinel_old_engine_runs_validate_preview_does_not(self):
        self.task('preview', validate=('$ %s' % self.sentinel_validate(),))
        (self.wt / 'hello.txt').write_text('ok\n')
        self.call(['git', 'add', 'hello.txt'], cwd=self.wt)
        self.call(['git', 'commit', '-qm', 'hello'], cwd=self.wt)
        before = self.snapshot_store()
        self.preview('preview', code=0)
        self.assertFalse(self.sentinel.exists(), 'preview must not run Validate')
        self.assertFalse((self.wt / SENTINEL).exists(), 'preview must not run Validate')
        self.assertEqual(self.snapshot_store()['reports'], before['reports'])
        self.assertEqual(self.snapshot_store()['results'], before['results'])
        self.assertEqual(self.snapshot_store()['ledger'], before['ledger'])

        old = self.unio('verify', 'mock', 'preview', '--preview',
                        engine=self.old_engine, code=None)
        self.assertTrue(self.sentinel.exists(),
                        'old unflagged engine given --preview still executes Validate')
        self.assertIn('verdict', old.stdout)
        self.sentinel.unlink()

        gated = self.unio('verify', 'mock', 'preview', code=0)
        self.assertTrue(self.sentinel.exists(),
                        'unflagged verify still runs Validate')
        self.assertIn('verdict  : PASS', gated.stdout)

    def test_change_during_observation_reason_wired(self):
        helper = (ROOT / 'tools' / 'task-preview.sh').read_text(encoding='utf-8')
        self.assertIn('changed_during', helper)
        self.assertIn('candidate_changed_during_observation', helper)
        engine = Path(self.engine).read_text(encoding='utf-8')
        self.assertIn('candidate_changed_during_observation', engine)
        self.task('preview')
        first = self.preview('preview', json_out=True, code=0)
        doc = json.loads(first.stdout)
        head = doc['head']
        (self.wt / 'hello.txt').write_text('later\n')
        self.call(['git', 'add', 'hello.txt'], cwd=self.wt)
        self.call(['git', 'commit', '-qm', 'later'], cwd=self.wt)
        second = self.preview('preview', json_out=True, code=0)
        later = json.loads(second.stdout)
        self.assertNotEqual(later['head'], head)
        self.assertIn('hello.txt', later['changed']['committed'])

    def test_human_and_json_aligned_and_no_pass(self):
        self.task('preview')
        human = self.preview('preview', code=0)
        js = self.preview('preview', json_out=True, code=0)
        doc = json.loads(js.stdout)
        self.assertIn('kind     : task-preview (observation)', human.stdout)
        self.assertIn(NOTE, human.stdout)
        self.assertIn('scope_status: in_scope', human.stdout)
        self.assertIn('provider_calls: 0', human.stdout)
        self.assertNotIn('verdict  : PASS', human.stdout)
        self.assertEqual(doc['kind'], 'task-preview')
        self.assertEqual(doc['scope_status'], 'in_scope')


if __name__ == '__main__':
    os.environ.setdefault('PYTHONDONTWRITEBYTECODE', '1')
    unittest.main()
