#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Observational report-review link tests (docs/REVIEW-REPORTS.md).

Offline installed-engine fixtures only: mock providers, isolated temp
projects, no real provider, billing or global writes. Proves the positive
packet -> frozen reviewer Source -> bind -> view chain, idempotency, the
separate semantic/format facts, refusal paths, unchanged default native
interfaces, and that the pre-change 0.5.29 reader ignores the new
namespaces with decisions/readiness unchanged.
"""
import fcntl
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
OLD_READER_FIXTURE = ROOT / 'tests' / 'fixtures' / 'report-review-reader-0529'
OLD_READER = OLD_READER_FIXTURE / 'unio-reader'

PROVIDER = '''import json, os, sys
control = json.loads(open(sys.argv[1]).read())
action = control.get('action')
deliv = os.environ.get('UNIO_DELIVERY_DIR', '')

def write(name, data):
    with open(os.path.join(deliv, name), 'w') as stream:
        stream.write(data)

if action != 'no_artifacts':
    write('summary.md', control.get('summary', 'review summary\\n'))
    write('verdict.json', json.dumps({'schema_version': 1,
                                     'verdict': control.get('verdict', 'APPROVE')}))
    write('findings.json', json.dumps({'schema_version': 1,
                                      'findings': control.get('findings', [])}))
if action == 'bad_verdict':
    write('verdict.json', '{"schema_version":1,"verdict":"APPROVE","extra":1}')
if action == 'bool_schema':
    write('verdict.json', '{"schema_version":true,"verdict":"APPROVE"}')
if action == 'bad_findings':
    write('findings.json', '{"schema_version":1,"findings":[{"severity":"nope",'
          '"path":null,"line":null,"summary":"s","detail":"d"}]}')
print(control.get('report', 'independent review report'))
if action == 'fail':
    raise SystemExit(7)
'''


class ReportReviews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='report reviews install ')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.install = Path(cls.temp.name)
        cls.env = {k: v for k, v in os.environ.items()
                   if not k.startswith(('UNIO_', 'PYTHON', 'GIT_')) and k != 'BASH_ENV'}
        cls.env.update(UNIO_BIN_DIR=str(cls.install / 'bin'),
                       UNIO_CONF_DIR=str(cls.install / 'conf'),
                       UNIO_COMPLETION_DIR=str(cls.install / 'completion'),
                       UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0',
                       UNIO_CLI_UPDATES_OFFLINE='1',
                       UNIO_TIMEOUT='30', GIT_CONFIG_GLOBAL='/dev/null',
                       GIT_CONFIG_NOSYSTEM='1', GIT_AUTHOR_NAME='mock',
                       GIT_COMMITTER_NAME='mock', GIT_AUTHOR_EMAIL='mock@test.invalid',
                       GIT_COMMITTER_EMAIL='mock@test.invalid',
                       PYTHONDONTWRITEBYTECODE='1')
        copy = cls.install / 'copied standalone installer.sh'
        copy.write_bytes((ROOT / 'unio-install.sh').read_bytes())
        p = subprocess.run(['bash', str(copy)], cwd=cls.install, env=cls.env,
                           capture_output=True, text=True, timeout=120)
        assert p.returncode == 0, p.stderr
        cls.engine = str(cls.install / 'bin' / 'unio')
        assert OLD_READER.is_file(), 'portable 0.5.29 reader fixture is required'
        assert os.access(OLD_READER, os.X_OK), '0.5.29 reader fixture must be executable'
        cls.old_engine = str(OLD_READER)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='report project ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / 'project' / 'repo'
        self.repo.mkdir(parents=True)
        self.env = dict(self.__class__.env)
        self.env['UNIO_CONF_DIR'] = str(self.root / 'conf')
        conf = self.root / 'conf'
        conf.mkdir()
        shutil.copytree(self.install / 'conf' / 'templates', conf / 'templates')
        self.provider = self.root / 'provider.py'
        self.provider.write_text(PROVIDER)
        self.conf = conf / 'agents.conf'
        self.conf.write_text(
            "mock=bash -c 'printf work > hello.txt; git add hello.txt; git commit -qm work'\n")
        self.call(['git', 'init', '-q', '-b', 'dev'])
        (self.repo / 'baseline.txt').write_text('unchanged baseline\n')
        self.call(['git', 'add', 'baseline.txt'])
        self.call(['git', 'commit', '-qm', 'initial'])
        self.unio('init', 'mock')
        self.coord = self.root / 'project' / 'coord'
        self.tasks = self.coord / 'tasks'
        self.target = 'evidence'
        self.task(self.target)
        self.unio('run', 'mock', self.target)
        self.unio('verify', 'mock', self.target)

    def call(self, args, code=0, env=None, cwd=None):
        p = subprocess.run(args, cwd=cwd or self.repo, env=env or self.env,
                           capture_output=True, text=True, timeout=120)
        if code is not None:
            self.assertEqual(p.returncode, code, (args, p.stdout[-3000:], p.stderr[-2000:]))
        return p

    def unio(self, *args, code=0):
        return self.call([self.engine, *args], code)

    def git_wt(self, *args):
        return self.call(['git', *args], cwd=self.root / 'project' / 'wt' / 'mock')

    def task(self, name, scope='- hello.txt', validate='$ test -s hello.txt'):
        (self.tasks / (name + '.md')).write_text(
            '# Task\n## Allowed scope\n' + scope + '\n## Validate\n' + validate + '\n')

    def packet(self, *paths, code=0, target=None, worker='mock'):
        args = ['review-packet', worker, target or self.target]
        for path in paths:
            args += ['--path', path]
        p = self.unio(*args, code=code)
        return json.loads(p.stdout) if code == 0 else p

    def reviewer(self, suffix, packet=None, verdict='APPROVE', findings=None,
                 action=None, verify=True, declare=True, artifacts=True, run_code=0):
        name = 'revtask' + suffix
        control = self.root / ('control-%s.json' % suffix)
        control.write_text(json.dumps(dict(verdict=verdict, findings=findings or [],
                                            action=action)))
        with self.conf.open('a') as stream:
            stream.write('rev%s=%s\n' % (suffix, shlex.join(
                ['python3', str(self.provider), str(control)])))
        self.unio('init', 'rev' + suffix)
        text = '# Reviewer task\n## Outcome\nreport-only\n'
        if declare and packet is not None:
            text += packet['declaration']
        if artifacts:
            text += '## Required artifacts\nsummary.md\nverdict.json\nfindings.json\n'
        text += '## Allowed scope\n- *\n## Validate\n$ true\n'
        (self.tasks / (name + '.md')).write_text(text)
        self.unio('run', 'rev' + suffix, name, code=run_code)
        if verify:
            self.unio('verify', 'rev' + suffix, name)
        return name

    def bind(self, reviewer, code=0, target=None):
        return self.unio('reviews-bind', 'mock', target or self.target,
                         'rev' + reviewer[-1], reviewer, code=code)

    def view(self, *extra, code=0):
        return self.unio('reviews', 'mock', self.target, '--reports', *extra, code=code)

    def hold_lock(self, worker):
        path = self.coord / '.locks' / (worker + '.lock')
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path, 'a+')
        os.chmod(path, 0o600)
        fcntl.flock(handle, fcntl.LOCK_EX)
        self.addCleanup(handle.close)

    def tree_bytes(self, path):
        items = {}
        for child in sorted(path.rglob('*')):
            rel = str(child.relative_to(path))
            if child.is_symlink():
                items[rel] = ('link', os.readlink(child))
            elif child.is_dir():
                items[rel] = ('dir', None)
            else:
                items[rel] = ('file', child.read_bytes())
        return items

    def test_positive_flow_idempotency_and_unchanged_defaults(self):
        packet = self.packet()
        self.assertEqual(packet['coverage'], 'task_material')
        manifest_dir = self.coord / 'review-packets' / packet['id']
        self.assertTrue((manifest_dir / 'manifest.json').is_file())
        self.assertTrue((manifest_dir / 'material.txt').is_file())
        reviewer = self.reviewer('1', packet)
        watched = (('reviews', 'mock', self.target),
                   ('reviews', 'mock', self.target, '--findings'),
                   ('reviews', 'mock', self.target, '--json'),
                   ('result', 'mock', self.target))
        before = {args: self.call([self.engine, *args], code=None) for args in watched}
        old_env = dict(self.env, UNIO_BIN_DIR=str(Path(self.old_engine).parent))
        old_before = {args: self.call([self.old_engine, *args], code=None, env=old_env)
                      for args in watched}
        attached = json.loads(self.bind(reviewer).stdout)
        self.assertEqual((attached['attached'], attached['replay'], attached['verdict'],
                          attached['human_acceptance'], attached['native_readiness_effect']),
                         (True, False, 'APPROVE', False, 'none'))
        receipt_dir = self.coord / 'reports' / (self.target + '.report-review.' + attached['id'])
        for name in ('receipt.json', 'summary.md', 'verdict.json', 'findings.json'):
            self.assertTrue((receipt_dir / name).is_file(), name)
        replay = json.loads(self.bind(reviewer).stdout)
        self.assertEqual((replay['replay'], replay['id']), (True, attached['id']))
        view = self.view()
        self.assertIn('verdict APPROVE', view.stdout)
        self.assertIn('no native-readiness or human-acceptance effect', view.stdout)
        rows = json.loads(self.view('--json').stdout)['rows']
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['state'], rows[0]['verdict'], rows[0]['current'],
                          rows[0]['human_acceptance'], rows[0]['native_readiness_effect']),
                         ('current', 'APPROVE', True, False, 'none'))
        for args, result in before.items():
            after = self.call([self.engine, *args], code=None)
            self.assertEqual(after.stdout, result.stdout, args)
            self.assertEqual(after.returncode, result.returncode, args)
        result = json.loads(self.unio('result', 'mock', self.target).stdout)
        self.assertFalse(result['ready_for_human_review'])
        self.assertEqual(result['review']['state'], 'not_run')
        for args, result in old_before.items():
            after = self.call([self.old_engine, *args], code=None, env=old_env)
            self.assertEqual(after.stdout, result.stdout, args)
            self.assertEqual(after.returncode, result.returncode, args)

    def test_explicit_paths_packet(self):
        wt = self.root / 'project' / 'wt' / 'mock'
        self.conf.write_text(self.conf.read_text().replace(
            'printf work > hello.txt; git add hello.txt; git commit -qm work',
            'printf work > hello.txt; printf extra > extra.txt; '
            'git add hello.txt extra.txt; git commit -qm work'))
        self.task('paths', scope='- hello.txt\n- extra.txt\n- big.txt')
        self.unio('run', 'mock', 'paths')
        self.unio('verify', 'mock', 'paths')
        self.target = 'paths'
        packet = self.packet('hello.txt', 'extra.txt')
        self.assertEqual(packet['coverage'], 'paths')
        self.assertEqual(packet['declared_paths'], ['hello.txt', 'extra.txt'])
        reviewer = self.reviewer('1', packet)
        attached = json.loads(self.bind(reviewer).stdout)
        self.assertEqual(attached['coverage'], 'paths')
        self.assertIn('coverage paths', self.view().stdout)
        for bad in ('hello.*', '../hello.txt', '/etc/passwd', 'missing.txt'):
            self.packet(bad, code=2)
        p = self.packet('baseline.txt', code=2)
        self.assertIn('not relevant to the target material', p.stderr)
        p = self.packet('hello.txt', 'hello.txt', code=2)
        self.assertIn('duplicate explicit packet path', p.stderr)
        (wt / 'uncommitted.txt').write_text('dirty\n')
        self.packet(code=2)
        (wt / 'uncommitted.txt').unlink()
        link = wt / 'link.txt'
        link.symlink_to(wt / 'hello.txt')
        self.packet('link.txt', code=2)
        link.unlink()
        big = wt / 'big.txt'
        big.write_text('oversized path material line\n' * 9500)
        self.git_wt('add', 'big.txt')
        self.git_wt('commit', '-qm', 'big')
        self.unio('verify', 'mock', self.target)
        p = self.packet('big.txt', code=2)
        self.assertIn('bounded readable text file', p.stderr)

    def test_declaration_negatives(self):
        packet = self.packet()
        missing = self.reviewer('1', packet, declare=False)
        p = self.bind(missing, code=2)
        self.assertIn('missing original Review packet binding', p.stderr)
        forged = dict(packet)
        forged['declaration'] = packet['declaration'].replace(packet['id'], 'f' * 32)
        absent = self.reviewer('2', forged)
        p = self.bind(absent, code=2)
        self.assertIn('packet is missing', p.stderr)
        wrong = dict(packet)
        wrong['declaration'] = packet['declaration'].replace(
            packet['manifest_sha256'], '0' * 64)
        mismatch = self.reviewer('3', wrong)
        p = self.bind(mismatch, code=2)
        self.assertIn('manifest digest does not match', p.stderr)
        late = self.reviewer('4', packet)
        task_file = self.tasks / 'revtask4.md'
        task_file.write_text(task_file.read_text() + packet['declaration'])
        p = self.bind(late, code=2)
        self.assertIn('changed since dispatch', p.stderr)
        bool_decl = dict(packet)
        bool_decl['declaration'] = packet['declaration'].replace(
            '"schema_version":1', '"schema_version":true')
        bool_src = self.reviewer('6', bool_decl)
        p = self.bind(bool_src, code=2)
        self.assertIn('Review packet declaration must be exactly', p.stderr)

    def test_target_and_packet_drift(self):
        packet = self.packet()
        reviewer = self.reviewer('1', packet)
        material = self.coord / 'review-packets' / packet['id'] / 'material.txt'
        original = material.read_bytes()
        material.chmod(0o644)
        material.write_bytes(original + b'tampered\n')
        material.chmod(0o400)
        p = self.bind(reviewer, code=2)
        self.assertIn('material bytes do not match', p.stderr)
        material.chmod(0o644)
        material.write_bytes(original)
        material.chmod(0o400)
        wt = self.root / 'project' / 'wt' / 'mock'
        (wt / 'hello.txt').write_text('changed target\n')
        self.git_wt('add', 'hello.txt')
        self.git_wt('commit', '-qm', 'advance')
        self.unio('verify', 'mock', self.target)
        p = self.bind(reviewer, code=2)
        self.assertIn('target revision changed', p.stderr)
        with self.conf.open('a') as stream:
            stream.write("mock2=bash -c 'printf work > hello2.txt; "
                         "git add hello2.txt; git commit -qm other'\n")
        self.unio('init', 'mock2')
        self.task('other', scope='- hello2.txt', validate='$ test -s hello2.txt')
        self.unio('run', 'mock2', 'other')
        self.unio('verify', 'mock2', 'other')
        other_packet = self.packet(target='other', worker='mock2')
        other_reviewer = self.reviewer('5', other_packet)
        p = self.unio('reviews-bind', 'mock', self.target, 'rev5', other_reviewer, code=2)
        self.assertIn('different worker/task', p.stderr)

    def test_source_negatives(self):
        packet = self.packet()
        failed = self.reviewer('1', packet, action='fail', run_code=7, verify=False)
        p = self.bind(failed, code=2)
        self.assertIn('successful Source', p.stderr)
        unverified = self.reviewer('2', packet, verify=False)
        p = self.bind(unverified, code=2)
        self.assertIn('verify PASS', p.stderr)
        tampered = self.reviewer('3', packet)
        delivery = next((self.coord / 'results' / 'rev3' / 'revtask3.outcomes')
                        .glob('*/delivery/verdict.json'))
        delivery.chmod(0o644)
        delivery.write_text('{"schema_version":1,"verdict":"REQUEST-CHANGES"}\n')
        delivery.chmod(0o400)
        p = self.bind(tampered, code=2)
        self.assertIn('delivery artifact changed', p.stderr)
        bad_verdict = self.reviewer('4', packet, action='bad_verdict')
        p = self.bind(bad_verdict, code=2)
        self.assertIn('verdict.json must be exactly', p.stderr)
        bad_findings = self.reviewer('5', packet, action='bad_findings')
        p = self.bind(bad_findings, code=2)
        self.assertIn('invalid findings block schema', p.stderr)
        bool_verdict = self.reviewer('6', packet, action='bool_schema')
        p = self.bind(bool_verdict, code=2)
        self.assertIn('verdict.json must be exactly', p.stderr)
        implementation = 'impltask'
        (self.tasks / (implementation + '.md')).write_text(
            '# Task\n## Allowed scope\n- *\n## Validate\n$ true\n')
        p = self.unio('reviews-bind', 'mock', self.target, 'mock', implementation, code=2)
        self.assertIn('report-only source tasks', p.stderr)

    def test_stop_and_busy_states(self):
        packet = self.packet()
        reviewer = self.reviewer('1', packet)
        stop = self.coord / 'STOP'
        stop.write_text('stop\n')
        self.packet(code=2)
        self.bind(reviewer, code=2)
        self.view()
        stop.unlink()
        attached = json.loads(self.bind(reviewer).stdout)
        self.assertTrue(attached['attached'])
        self.hold_lock('mock')
        p = self.packet(code=2)
        self.assertIn('target worker is busy', p.stderr)
        self.hold_lock('rev1')
        p = self.bind(reviewer, code=2)
        self.assertIn('worker is busy', p.stderr)

    def test_publication_interruption_preserves_pending_evidence(self):
        leftover = self.coord / 'review-packets' / ('.pending-' + 'ab' * 16)
        leftover.mkdir(parents=True)
        junk = leftover / 'junk.txt'
        junk.write_text('partial packet\n')
        leftover_bytes = self.tree_bytes(leftover)
        packet = self.packet()
        self.assertEqual(self.tree_bytes(leftover), leftover_bytes)
        self.assertTrue((self.coord / 'review-packets' / packet['id'] / 'manifest.json').is_file())
        pending_names = sorted(p.name for p in leftover.parent.iterdir()
                               if p.name.startswith('.pending-'))
        self.assertEqual(pending_names, [leftover.name])
        reviewer = self.reviewer('1', packet)
        attached = json.loads(self.bind(reviewer).stdout)
        receipt_dir = self.coord / 'reports' / (self.target + '.report-review.' + attached['id'])
        pending = self.coord / 'reports' / ('.pending-report-review-' + 'cd' * 8)
        pending.mkdir()
        (pending / 'receipt.json').write_text('{}\n')
        pending_bytes = self.tree_bytes(pending)
        replay = json.loads(self.bind(reviewer).stdout)
        self.assertTrue(replay['replay'])
        self.assertEqual(self.tree_bytes(pending), pending_bytes)
        self.assertEqual(self.tree_bytes(leftover), leftover_bytes)
        findings = receipt_dir / 'findings.json'
        findings.unlink()
        p = self.bind(reviewer, code=2)
        self.assertIn('incomplete', p.stderr)
        self.assertTrue((receipt_dir / 'receipt.json').is_file())
        self.assertFalse(findings.exists())
        p = self.packet('baseline.txt', code=2)
        self.assertIn('not relevant to the target material', p.stderr)
        self.assertEqual(self.tree_bytes(leftover), leftover_bytes)
        self.assertEqual(self.tree_bytes(pending), pending_bytes)

    def test_other_worker_pending_records_stay_byte_identical_under_lock(self):
        with self.conf.open('a') as stream:
            stream.write("mock2=bash -c 'printf work > hello2.txt; "
                         "git add hello2.txt; git commit -qm other'\n")
        self.unio('init', 'mock2')
        self.task('other', scope='- hello2.txt', validate='$ test -s hello2.txt')
        self.unio('run', 'mock2', 'other')
        self.unio('verify', 'mock2', 'other')
        packets = self.coord / 'review-packets'
        packets.mkdir(parents=True, exist_ok=True)
        other_packet = packets / ('.pending-' + '11' * 16)
        other_packet.mkdir()
        (other_packet / 'material.txt').write_text('other worker unpublished packet\n')
        (other_packet / 'manifest.json').write_text('{"writer":"mock2"}\n')
        packet_before = self.tree_bytes(other_packet)
        self.hold_lock('mock2')
        packet = self.packet()
        self.assertEqual(self.tree_bytes(other_packet), packet_before)
        self.assertTrue((packets / packet['id'] / 'manifest.json').is_file())
        reports = self.coord / 'reports'
        other_bind = reports / ('.pending-report-review-' + '22' * 8)
        other_bind.mkdir()
        (other_bind / 'receipt.json').write_text('{"writer":"mock2-bind"}\n')
        (other_bind / 'summary.md').write_text('other unpublished bind\n')
        bind_before = self.tree_bytes(other_bind)
        leftover = packets / ('.pending-' + 'ab' * 16)
        leftover.mkdir()
        (leftover / 'junk.txt').write_text('interrupted leftover\n')
        leftover_before = self.tree_bytes(leftover)
        reviewer = self.reviewer('1', packet)
        attached = json.loads(self.bind(reviewer).stdout)
        self.assertTrue(attached['attached'])
        self.assertEqual(self.tree_bytes(other_packet), packet_before)
        self.assertEqual(self.tree_bytes(other_bind), bind_before)
        self.assertEqual(self.tree_bytes(leftover), leftover_before)
        p = self.packet(target='other', worker='mock2', code=2)
        self.assertIn('worker is busy', p.stderr)
        self.assertEqual(self.tree_bytes(other_packet), packet_before)

    def test_frozen_0529_reader_is_portable_offline_and_genuine(self):
        self.assertEqual(Path(self.old_engine).resolve(), OLD_READER.resolve())
        self.assertTrue(OLD_READER.resolve().is_relative_to(ROOT.resolve()))
        self.assertEqual(self.env['UNIO_CLI_UPDATES_OFFLINE'], '1')
        provenance = (OLD_READER_FIXTURE / 'PROVENANCE.md').read_text()
        self.assertIn('65d2a2975d71adb16362f33ac0f6e06027d378fd', provenance)
        self.assertIn('2543b26a84235d4c5b8057d3106d0f3f3a84cdf9f398a4b036fb3d695ad01cb3', provenance)
        self.assertIn("r'\\.review\\.[A-Za-z0-9]{8}'", provenance)
        quality = (OLD_READER_FIXTURE / 'quality.py').read_text()
        self.assertIn("re.escape(task)+r'\\.review\\.[A-Za-z0-9]{8}'", quality)
        self.assertNotIn('report-review', quality)
        self.assertNotIn('review-packet', quality)

    def test_request_changes_retained_alongside_approval(self):
        packet = self.packet()
        findings = [dict(severity='medium', path='hello.txt', line=1,
                         summary='polish', detail='minor wording')]
        changes = self.reviewer('1', packet, verdict='REQUEST-CHANGES', findings=findings)
        attached = json.loads(self.bind(changes).stdout)
        self.assertEqual(attached['verdict'], 'REQUEST-CHANGES')
        approve = self.reviewer('2', packet)
        self.bind(approve)
        rows = json.loads(self.view('--json').stdout)['rows']
        self.assertEqual(sorted(row['verdict'] for row in rows),
                         ['APPROVE', 'REQUEST-CHANGES'])
        self.assertEqual(sorted(row['findings_count'] for row in rows), [0, 1])
        self.assertEqual(self.view().returncode, 0)
        result = json.loads(self.unio('result', 'mock', self.target).stdout)
        self.assertFalse(result['ready_for_human_review'])
        self.assertEqual(result['review']['state'], 'not_run')

    def test_view_staleness_and_corruption(self):
        packet = self.packet()
        reviewer = self.reviewer('1', packet)
        attached = json.loads(self.bind(reviewer).stdout)
        self.assertEqual(self.view().returncode, 0)
        receipt = (self.coord / 'reports'
                   / (self.target + '.report-review.' + attached['id']) / 'receipt.json')
        original = receipt.read_bytes()
        receipt.chmod(0o644)
        receipt.write_text('{"schema_version":1,"kind":"other"}\n')
        receipt.chmod(0o400)
        p = self.view(code=1)
        self.assertIn('invalid receipt', p.stdout)
        p = self.bind(reviewer, code=2)
        self.assertIn('report review receipt', p.stderr)
        receipt.chmod(0o644)
        receipt.write_bytes(original)
        receipt.chmod(0o400)
        self.assertEqual(self.view().returncode, 0)
        wt = self.root / 'project' / 'wt' / 'mock'
        (wt / 'hello.txt').write_text('advanced\n')
        self.git_wt('add', 'hello.txt')
        self.git_wt('commit', '-qm', 'advance')
        self.unio('verify', 'mock', self.target)
        p = self.view(code=1)
        self.assertIn('target_revision_changed', p.stdout)
        shutil.rmtree(self.coord / 'review-packets' / packet['id'])
        p = self.view(code=1)
        self.assertIn('evidence_unavailable', p.stdout)

    def test_cli_surface(self):
        self.unio('review-packet', '--help')
        self.unio('reviews-bind', '--help')
        self.assertIn('--reports', self.unio('reviews', '--help').stdout)
        self.unio('reviews', 'mock', self.target, '--reports', '--findings', code=2)
        self.unio('reviews', 'mock', self.target, '--reports', '--expect', 'rev', code=2)
        self.unio('reviews', 'mock', self.target, '--reports', '--reports', code=2)
        self.unio('review-packet', 'mock', code=2)
        self.unio('review-packet', 'mock', self.target, '--wrong', code=2)
        self.unio('review-packet', 'mock', self.target, '--path', code=2)
        self.unio('reviews-bind', 'mock', self.target, 'rev', code=2)
        self.view()
        completion = (self.install / 'completion' / 'unio').read_text()
        self.assertIn('review-packet', completion)
        self.assertIn('reviews-bind', completion)


if __name__ == '__main__':
    unittest.main()
