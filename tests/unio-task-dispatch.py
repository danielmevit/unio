#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline CLI tests for explicit owner-granted dispatch over the service.

Every case owns a real tiny Git workspace and drives the actual helper as a
subprocess against the real PlanStore/JobStore/ExecutionService with a mocked
native runner and mocked fleet observation. Zero provider or AI calls.
"""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / 'bridge'))
from execution_service import ExecutionService
from job_store import JobStore
from plan_store import PlanStore

DISPATCH_HELPER = SOURCE_ROOT / 'tools/task-dispatch.py'

MOCK_ENGINE = r'''#!/usr/bin/env python3
import hashlib, json, os, pathlib, subprocess, sys
cwd = pathlib.Path.cwd()
root = cwd.parent if cwd.name == 'repo' and (cwd.parent / 'coord').is_dir() else cwd
args = sys.argv[1:]
with (root / 'engine-calls.jsonl').open('a') as log:
    log.write(json.dumps(dict(argv=args, pid=os.getpid())) + '\n')
if args[0] in ('policy', 'agents', 'capacity', 'readiness'):
    key = ' '.join(args)
    data = json.loads((root / 'engine-data.json').read_text()) if (root / 'engine-data.json').exists() else {}
    if key not in data:
        sys.exit(1)
    sys.stdout.write(json.dumps(data[key]))
    sys.exit(0)
assert args[0] in ('run', 'result'), 'unsupported native operation'
if args[0] == 'run':
    assert len(args) == 4 and args[1] == '-b'
    worker, task = args[2], args[3]
else:
    assert len(args) == 3
    worker, task = args[1], args[2]
wt = root / 'wt' / worker
tf = root / 'coord/tasks' / (task + '.md')
result_path = root / 'coord/results' / worker / (task + '.json')
def git(*a):
    return subprocess.check_output(['git', '-C', str(wt), *a]).decode().strip()
def revision():
    content = (wt / 'source.txt').read_bytes()
    work = hashlib.sha256(content + str((wt / 'source.txt').stat().st_mode).encode()).hexdigest()
    base = (root / 'coord/base').read_text().strip()
    return dict(base_commit=git('rev-parse', base), candidate_commit=git('rev-parse', 'HEAD'),
                task_sha256=hashlib.sha256(tf.read_bytes()).hexdigest(), worktree_sha256=work)
if args[0] == 'run':
    assert tf.is_file()
    (wt / 'source.txt').write_text('implemented ' + task + '\n')
    subprocess.check_call(['git', '-C', str(wt), 'add', 'source.txt'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.check_call(['git', '-C', str(wt), 'commit', '-qm', 'mock work'],
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rev = revision()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(dict(schema_version=1, worker=worker, task=task,
        updated_at='2026-10-11T12:00:00+00:00', current_revision=rev,
        process=dict(state='succeeded', exit_code=0, revision=rev),
        validation=dict(state='not_run', scope='UNCHECKED', checks_run=0, checks_failed=0, reasons=[], revision=None),
        review=dict(state='not_run', reviewer=None, process_exit_code=None, material_complete=False, reasons=[], revision=None),
        stale=False, ready_for_human_review=False)))
    control = root / 'engine-control.json'
    if control.exists() and json.loads(control.read_text()).get('run') == 'nonzero':
        sys.exit(9)
    sys.exit(0)
d = json.loads(result_path.read_text())
rev = revision()
d['current_revision'] = rev
d['stale'] = any(s['revision'] != rev for s in [d[k] for k in ('process','validation','review')]
                 if s['state'] != 'not_run')
d['ready_for_human_review'] = False
sys.stdout.write(json.dumps(d))
sys.exit(0)
'''


def git(directory, *args):
    result = subprocess.run(['git', '-C', str(directory), *args],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError('git failed: ' + result.stderr)
    return result.stdout.strip()


class TaskDispatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='task_dispatch_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'dispatch project'
        self.coord = self.project / 'coord'
        self.repo = self.project / 'repo'
        for name in ('coord/tasks', 'repo', 'wt', 'config'):
            (self.project / name).mkdir(parents=True)
        git(self.repo, 'init', '-q', '-b', 'main')
        git(self.repo, 'config', 'user.email', 'mock@invalid')
        git(self.repo, 'config', 'user.name', 'Mock')
        git(self.repo, 'commit', '-q', '--allow-empty', '-m', 'initial')
        self.commit0 = git(self.repo, 'rev-parse', 'HEAD')
        (self.repo / 'source.txt').write_text('base\n')
        git(self.repo, 'add', 'source.txt')
        git(self.repo, 'commit', '-qm', 'base')
        self.base_revision = git(self.repo, 'rev-parse', 'HEAD')
        self.worker = 'dispatch-worker'
        self.wt = self.project / 'wt' / self.worker
        git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/' + self.worker, str(self.wt))
        (self.coord / 'base').write_text('main\n')
        self.config = self.project / 'config'
        (self.config / 'agents.conf').write_text('dispatch=NEVER_REAL_PROVIDER\n')
        self.template = self.project / 'template.json'
        self.write_template()
        self.engine = self.project / 'engine'
        self.engine.write_text(MOCK_ENGINE)
        self.engine.chmod(0o700)
        self.write_fleet()
        self.grant = self.write_grant()
        self.plans = PlanStore(self.project)
        self.addCleanup(self.plans.close)

    def write_template(self, scope=('source.txt',)):
        self.template.write_text(json.dumps(dict(
            schema_version=1, instructions='Implement the literal saved request.',
            scope=list(scope), validate=['test -s source.txt'])))

    def write_fleet(self, active=None):
        data = {
            'policy --json': dict(schema_version=1, mode='yolo', tier='low', lead_agent='codex',
                lead_group='codex', workflow_enforcement='native_workflows',
                workflow_limit_per_group=1, accounts={'dispatch': 'dispatch', 'other': 'other'},
                active_with_lead=active or {}),
            'agents --json': dict(schema_version=1, agents=[
                dict(name='dispatch', binary=dict(present=True), bench=dict(off=False)),
                dict(name='other', binary=dict(present=True), bench=dict(off=False))]),
            'capacity show --json': dict(schema_version=1, state='ok', groups={}),
            'capacity show --provider codex --json': dict(schema_version=1, provider='codex',
                                                         state='ok', groups={}),
            'readiness show --json': dict(schema_version=1, state='ok', agents={}),
        }
        (self.project / 'engine-data.json').write_text(json.dumps(data))

    def write_grant(self, **changes):
        grant = dict(schema_version=1, project=str(self.project), engine=str(self.engine),
                     config_dir=str(self.config), template_path=str(self.template),
                     worker=self.worker, reviewer='other', worker_lab='Mock Company',
                     reviewer_lab='Another Company')
        grant.update(changes)
        path = self.root / ('grant-%d.json' % time.monotonic_ns())
        path.write_text(json.dumps(grant))
        return path

    def dispatch(self, *arguments, grant=None, json_output=True, env=None, check_code=0):
        command = [sys.executable, '-B', str(DISPATCH_HELPER), str(self.engine),
                   '--grant', str(grant or self.grant)]
        if json_output:
            command.append('--json')
        command.extend(arguments)
        environment = dict(os.environ)
        environment.pop('UNIO_CONF_DIR', None)
        if env:
            environment.update(env)
        result = subprocess.run(command, capture_output=True, text=True,
                                timeout=120, env=environment)
        self.assertEqual(result.returncode, check_code,
                        'exit %d\nstdout: %s\nstderr: %s' % (result.returncode,
                                                             result.stdout, result.stderr))
        return result

    def key(self):
        return uuid.uuid4().hex

    def engine_calls(self, operation=None):
        path = self.project / 'engine-calls.jsonl'
        calls = ([json.loads(line)['argv'] for line in path.read_text().splitlines()]
                 if path.exists() else [])
        return [argv for argv in calls if operation is None or argv[0] == operation]

    def prepared(self, request='Implement this.'):
        draft = self.plans.create(request)
        result = self.dispatch('prepare', '--draft-id', draft['id'], '--draft-sha256',
                               draft['content_sha256'], '--request-key', self.key())
        return draft, json.loads(result.stdout)

    def approved(self, request='Implement this.'):
        draft, report = self.prepared(request)
        approval = self.key()
        result = self.dispatch('approve', '--job-id', report['job']['id'], '--draft-sha256',
                               draft['content_sha256'], '--preview-sha256',
                               report['preview_sha256'], '--approval-key', approval)
        return draft, report, approval, json.loads(result.stdout)

    def inventory(self, rows, base_revision=None, accepted=()):
        data = dict(schema_version=1, base_revision=base_revision or self.base_revision,
                    tasks=rows, accepted=list(accepted))
        path = self.root / ('inventory-%d.json' % time.monotonic_ns())
        path.write_text(json.dumps(data))
        return path, hashlib.sha256(path.read_bytes()).hexdigest()

    def job_row(self, report, **changes):
        row = dict(id=report['task']['id'], task_sha256=report['task']['sha256'],
                   worker=self.worker, depends_on=[], job_id=report['job']['id'])
        row.update(changes)
        return row

    def start(self, report, approval, inv, inv_hash, reservation=None, **kwargs):
        return self.dispatch('start', '--job-id', report['job']['id'],
                             '--approval-key', approval, '--reservation-key',
                             reservation or self.key(), '--inventory', str(inv),
                             '--inventory-sha256', inv_hash, **kwargs)

    def queue_job(self, job_id):
        with JobStore(self.project) as store:
            return store.get(job_id)

    def test_prepare_approve_start_from_absent_native_task_and_exact_replay(self):
        draft, prepared, approval, approved = self.approved()
        identity = prepared['job']['id']
        self.assertEqual(prepared['outcome'], 'prepared')
        self.assertEqual(prepared['job']['state'], 'awaiting_owner_approval')
        self.assertEqual(approved['outcome'], 'approved')
        self.assertEqual(approved['job']['state'], 'approved')
        task_id = prepared['task']['id']
        self.assertEqual(task_id, 'ui-' + identity)
        native = self.coord / 'tasks' / (task_id + '.md')
        # Prepare and approve publish only the prepared binding material; the
        # native task stays absent and no launch happens.
        self.assertFalse(native.exists())
        self.assertFalse((self.project / 'engine-calls.jsonl').exists())
        binding = json.loads((self.coord / 'ui-execution' / 'bindings'
                             / (identity + '.json')).read_text())
        self.assertEqual(binding['job_id'], identity)

        inv, inv_hash = self.inventory([self.job_row(prepared)])
        reservation = self.key()
        result = self.start(prepared, approval, inv, inv_hash, reservation=reservation)
        report = json.loads(result.stdout)
        self.assertEqual(report['outcome'], 'launch_accepted')
        self.assertEqual(report['execution'], dict(state='launch_accepted', launcher_exit=0))
        self.assertEqual(report['job']['state'], 'reserved')
        self.assertEqual(report['plan']['status'], 'ready')
        self.assertFalse(report['replay'])
        self.assertTrue(native.exists())
        self.assertEqual(self.engine_calls('run'), [['run', '-b', self.worker, task_id]])

        # Same-key replay returns the existing evidence; exactly one launch.
        replay = json.loads(self.start(prepared, approval, inv, inv_hash,
                                       reservation=reservation).stdout)
        self.assertEqual(replay['outcome'], 'launch_accepted')
        self.assertTrue(replay['replay'])
        self.assertEqual(replay['execution'], report['execution'])
        self.assertEqual(len(self.engine_calls('run')), 1)
        # A changed reservation key never retries the launch.
        refused = self.start(prepared, approval, inv, inv_hash, check_code=1)
        self.assertEqual(json.loads(refused.stdout)['outcome'], 'refused')
        self.assertEqual(len(self.engine_calls('run')), 1)

    def test_unknown_outcome_is_retained_and_never_relaunched(self):
        draft, prepared, approval, _ = self.approved()
        (self.project / 'engine-control.json').write_text(json.dumps(dict(run='nonzero')))
        inv, inv_hash = self.inventory([self.job_row(prepared)])
        reservation = self.key()
        unknown = json.loads(self.start(prepared, approval, inv, inv_hash,
                                        reservation=reservation, check_code=3).stdout)
        self.assertEqual(unknown['outcome'], 'unknown')
        self.assertIsNone(unknown['error'])
        self.assertEqual(unknown['job']['state'], 'completion_unknown')
        self.assertEqual(unknown['execution'], dict(state='completion_unknown', launcher_exit=9))
        self.assertIn('outcome_unknown', unknown['warnings'])
        self.assertFalse(unknown['replay'])
        self.assertEqual(len(self.engine_calls('run')), 1)
        # The unknown outcome is retained: replay keeps it without a new launch.
        replay = json.loads(self.start(prepared, approval, inv, inv_hash,
                                       reservation=reservation, check_code=3).stdout)
        self.assertEqual(replay['outcome'], 'unknown')
        self.assertTrue(replay['replay'])
        self.assertEqual(replay['job']['state'], 'completion_unknown')
        self.assertEqual(replay['execution'], dict(state='completion_unknown', launcher_exit=9))
        self.assertEqual(len(self.engine_calls('run')), 1)
        # A changed reservation key does not retry an unknown launch.
        refused = self.start(prepared, approval, inv, inv_hash, check_code=1)
        self.assertEqual(json.loads(refused.stdout)['outcome'], 'refused')
        self.assertEqual(len(self.engine_calls('run')), 1)

    def test_invalid_grant_and_arguments_never_initialize_coordination(self):
        coordination = self.coord / 'ui-execution'
        base = json.loads(self.grant.read_text())

        def refused(*arguments, grant=None, env=None, code=2, fragment=None):
            result = self.dispatch(*arguments, grant=grant, env=env, check_code=code)
            if fragment:
                self.assertIn(fragment, result.stderr)
            self.assertFalse(coordination.exists())
            return result

        # Strict JSON: duplicate fields, constants and non-objects are not grants.
        duplicate = self.root / 'grant-duplicate.json'
        duplicate.write_text(json.dumps(base)[:-1] + ', "schema_version": 1}')
        refused('--grant', str(duplicate), 'prepare', '--draft-id', 'a' * 32,
                '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='not a strict UTF-8 JSON object')
        constant = self.root / 'grant-constant.json'
        constant.write_text('{"schema_version": NaN}')
        refused('--grant', str(constant), 'prepare', '--draft-id', 'a' * 32,
                '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='not a strict UTF-8 JSON object')
        (self.root / 'grant-array.json').write_text('[1, 2]')
        refused('--grant', str(self.root / 'grant-array.json'), 'prepare',
                '--draft-id', 'a' * 32, '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='not a strict UTF-8 JSON object')
        # Unknown and missing fields are refused.
        unknown = self.root / 'grant-unknown.json'
        unknown.write_text(json.dumps(base)[:-1] + ', "extra": 1}')
        refused('--grant', str(unknown), 'prepare', '--draft-id', 'a' * 32,
                '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='must contain exactly')
        missing = self.root / 'grant-missing.json'
        del base['reviewer_lab']
        missing.write_text(json.dumps(base))
        refused('--grant', str(missing), 'prepare', '--draft-id', 'a' * 32,
                '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='must contain exactly')
        base = json.loads(self.grant.read_text())
        # The grant is bounded at 16 KiB.
        oversized = self.write_grant(worker_lab='x' * 20000)
        refused('--grant', str(oversized), 'prepare', '--draft-id', 'a' * 32,
                '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='exceeds 16 KiB limit')
        # Symlinked grant and granted paths are refused.
        link = self.root / 'grant-link.json'
        link.symlink_to(self.grant)
        refused('--grant', str(link), 'prepare', '--draft-id', 'a' * 32,
                '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='must not be a symlink')
        config_link = self.root / 'config-link'
        config_link.symlink_to(self.config)
        refused('prepare', '--draft-id', 'a' * 32, '--draft-sha256', 'b' * 64,
                '--request-key', 'c' * 32, grant=self.write_grant(config_dir=str(config_link)),
                fragment='must be an absolute physical path')
        # Engine mismatch: the grant must name the invoked executable.
        second = self.root / 'engine-copy'
        second.write_text(self.engine.read_text())
        second.chmod(0o700)
        refused('prepare', '--draft-id', 'a' * 32, '--draft-sha256', 'b' * 64,
                '--request-key', 'c' * 32, grant=self.write_grant(engine=str(second)),
                fragment='does not match the invoked Unio executable')
        plain = self.root / 'not-executable'
        plain.write_text('# not executable\n')
        refused('prepare', '--draft-id', 'a' * 32, '--draft-sha256', 'b' * 64,
                '--request-key', 'c' * 32, grant=self.write_grant(engine=str(plain)),
                fragment='must be executable')
        # Configured environment and --project must match the grant.
        refused('prepare', '--draft-id', 'a' * 32, '--draft-sha256', 'b' * 64,
                '--request-key', 'c' * 32, env={'UNIO_CONF_DIR': str(self.root)},
                fragment='UNIO_CONF_DIR does not match')
        refused('--project', str(self.root), 'prepare', '--draft-id', 'a' * 32,
                '--draft-sha256', 'b' * 64, '--request-key', 'c' * 32,
                fragment='--project does not match')
        # Argument formats are validated before any coordination.
        refused('prepare', '--draft-id', 'not-hex', '--draft-sha256', 'b' * 64,
                '--request-key', 'c' * 32, fragment='32 lowercase hex characters')
        refused('start', '--job-id', 'a' * 32, '--approval-key', 'b' * 32,
                '--reservation-key', 'c' * 32, '--inventory', str(self.grant),
                '--inventory-sha256', 'd' * 64, '--timeout', '0',
                fragment='--timeout must be 1..60 seconds')
        refused(fragment='OPERATION')
        # Help works without a project or coordination.
        result = self.dispatch('--help', check_code=0)
        self.assertIn('prepare', result.stdout)
        self.assertIn('start', result.stdout)
        self.assertFalse(coordination.exists())
        # A start with an unreadable or hash-mismatched inventory is refused
        # before the service exists.
        inv, inv_hash = self.inventory([])
        inv_link = self.root / 'inventory-link.json'
        inv_link.symlink_to(inv)
        refused('start', '--job-id', 'a' * 32, '--approval-key', 'b' * 32,
                '--reservation-key', 'c' * 32, '--inventory', str(inv_link),
                '--inventory-sha256', inv_hash, code=1, fragment='inventory_unreadable')
        refused('start', '--job-id', 'a' * 32, '--approval-key', 'b' * 32,
                '--reservation-key', 'c' * 32, '--inventory', str(inv),
                '--inventory-sha256', 'e' * 64, code=1, fragment='inventory_hash_mismatch')

    def test_start_refusals_preserve_approval_without_reservation_or_task(self):
        draft, prepared, approval, _ = self.approved()
        identity = prepared['job']['id']
        task_file = self.coord / 'tasks' / (prepared['task']['id'] + '.md')
        row = self.job_row(prepared)

        def refused(inv, inv_hash, reason=None, error=None, fleet_active=None):
            if fleet_active is not None:
                self.write_fleet(active=fleet_active)
            result = self.start(prepared, approval, inv, inv_hash, check_code=1)
            if fleet_active is not None:
                self.write_fleet()
            report = json.loads(result.stdout)
            self.assertEqual(report['outcome'], 'refused')
            if error is not None:
                self.assertEqual(report['error'], error)
            if reason is not None:
                self.assertEqual(report['reason'], reason)
            job = self.queue_job(identity)
            self.assertEqual(job['state'], 'approved')
            self.assertIsNone(job['reservation_key'])
            self.assertFalse(task_file.exists())
            self.assertEqual(self.engine_calls('run'), [])
            return report

        # Identity: no inventory row binds this job.
        inv, inv_hash = self.inventory([dict(id='ui-' + 'b' * 32, task_sha256='0' * 64,
                                             worker=self.worker, depends_on=[],
                                             job_id='b' * 32)])
        refused(inv, inv_hash, reason='inventory_row_missing')
        # Identity: the row binds another job or worker.
        inv, inv_hash = self.inventory([dict(row, job_id='c' * 32)])
        refused(inv, inv_hash, reason='inventory_binding_mismatch')
        inv, inv_hash = self.inventory([dict(row, worker='other-worker')])
        refused(inv, inv_hash, reason='inventory_binding_mismatch')
        # Hash: the row's compiled-task hash does not match the binding.
        inv, inv_hash = self.inventory([dict(row, task_sha256='0' * 64)])
        refused(inv, inv_hash, reason='inventory_binding_mismatch')
        # Base: the inventory is bound to another base revision.
        inv, inv_hash = self.inventory([row], base_revision=self.commit0)
        refused(inv, inv_hash, reason='inventory_base_mismatch')
        # Dependency: acceptance evidence for a dependency is missing.
        inv, inv_hash = self.inventory([dict(row, depends_on=[
            dict(id='TASK-X', task_sha256='f' * 64, revision=self.commit0)])])
        report = refused(inv, inv_hash, reason='plan_unresolved')
        self.assertIn('missing_acceptance_evidence:TASK-X', report['plan']['reasons'])
        # Scope: an earlier sorted plain task already holds the write scope.
        plain = self.coord / 'tasks' / 'aaa-plain.md'
        plain.write_text('# Task aaa-plain\n\n## Allowed scope\n- source.txt\n\n'
                         '## Validate\n$ echo check\n')
        inv, inv_hash = self.inventory([row, dict(id='aaa-plain',
            task_sha256=hashlib.sha256(plain.read_bytes()).hexdigest(),
            worker='other-worker', depends_on=[])])
        report = refused(inv, inv_hash, reason='plan_blocked')
        self.assertIn('scope_conflict', report['plan']['reasons'])
        # Full group: the shared budget group shows every slot occupied.
        inv, inv_hash = self.inventory([row])
        report = refused(inv, inv_hash, reason='plan_blocked', fleet_active={'dispatch': 1})
        self.assertIn('group_full', report['plan']['reasons'])
        # STOP gate refuses before the preflight.
        (self.coord / 'STOP').write_text('stop')
        inv, inv_hash = self.inventory([row])
        refused(inv, inv_hash, error='stopped')
        (self.coord / 'STOP').unlink()
        # Config mismatch: the granted template drifted from the binding.
        saved = self.template.read_bytes()
        self.write_template(scope=('other.txt',))
        inv, inv_hash = self.inventory([row])
        refused(inv, inv_hash, error='binding_stale')
        self.template.write_bytes(saved)
        # Base drift: the repository head moved past the bound base.
        (self.repo / 'source.txt').write_text('moved\n')
        git(self.repo, 'add', 'source.txt')
        git(self.repo, 'commit', '-qm', 'moved')
        inv, inv_hash = self.inventory([row])
        refused(inv, inv_hash, error='binding_stale')

    def reserved_other_job(self, scope=('source.txt',)):
        """Start a second worker's job so it holds queue state reserved."""
        other = 'other-worker'
        git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/' + other,
            str(self.project / 'wt' / other))
        template = self.project / 'template-other.json'
        template.write_text(json.dumps(dict(
            schema_version=1, instructions='Implement the literal saved request.',
            scope=list(scope), validate=['test -s source.txt'])))
        service = ExecutionService(str(self.project), str(self.engine), other, 'another',
                                    str(self.config), str(template), 'Mock Company',
                                    'Another Company')
        self.addCleanup(service.close)
        draft = self.plans.create('other worker job')
        view = service.prepare(draft['id'], draft['content_sha256'], self.key())
        approval = self.key()
        view = service.approve(view['job']['id'], draft['content_sha256'], approval,
                               view['preview']['preview_hash'])
        view = service.start(view['job']['id'], approval, self.key())
        self.assertEqual(view['execution']['state'], 'launch_accepted')
        return view

    def test_reserved_job_with_intersecting_scope_refuses_even_with_zero_slots(self):
        other = self.reserved_other_job()
        other_id = other['job']['id']
        other_task = other['preview']['task_id']
        self.assertTrue((self.coord / 'tasks' / (other_task + '.md')).exists())
        # Both native groups show zero occupied slots in the fleet observation.
        draft, prepared, approval, _ = self.approved()
        identity = prepared['job']['id']
        rows = [self.job_row(prepared),
                dict(id=other_task, task_sha256=other['preview']['task_sha256'],
                     worker='other-worker', depends_on=[], job_id=other_id)]
        inv, inv_hash = self.inventory(rows)
        result = self.start(prepared, approval, inv, inv_hash, check_code=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['outcome'], 'refused')
        self.assertEqual(report['reason'], 'reserved_scope_conflict')
        self.assertEqual(self.queue_job(identity)['state'], 'approved')
        self.assertIsNone(self.queue_job(identity)['reservation_key'])
        self.assertFalse((self.coord / 'tasks' / (prepared['task']['id'] + '.md')).exists())
        self.assertEqual(len(self.engine_calls('run')), 1)
        # Conservative refusal when the possibly active job's published task
        # (its scope evidence) cannot be established.
        published = self.coord / 'tasks' / (other_task + '.md')
        saved = published.read_bytes()
        published.unlink()
        result = self.start(prepared, approval, inv, inv_hash, check_code=1)
        report = json.loads(result.stdout)
        self.assertEqual(report['reason'], 'plan_unresolved')
        self.assertIn('disjointness_unknown', report['plan']['reasons'])
        self.assertEqual(self.queue_job(identity)['state'], 'approved')
        self.assertIsNone(self.queue_job(identity)['reservation_key'])
        self.assertFalse((self.coord / 'tasks' / (prepared['task']['id'] + '.md')).exists())
        self.assertEqual(len(self.engine_calls('run')), 1)
        published.write_bytes(saved)

    def test_integrated_reserved_job_releases_scope_for_accepted_dependency(self):
        other = self.reserved_other_job()
        # Integration is explicit evidence, separate from the still-reserved
        # queue record and from the mocked successful native run.
        git(self.repo, 'merge', '--ff-only', 'agent/other-worker')
        self.base_revision = git(self.repo, 'rev-parse', 'HEAD')
        git(self.wt, 'merge', '--ff-only', 'main')
        other_task = other['preview']['task_id']
        accepted = dict(id=other_task, task_sha256=other['preview']['task_sha256'],
                        revision=self.base_revision)
        draft, prepared, approval, _ = self.approved()
        rows = [self.job_row(prepared, depends_on=[accepted]),
                dict(id=other_task, task_sha256=accepted['task_sha256'],
                     worker='other-worker', depends_on=[], job_id=other['job']['id'])]
        inv, inv_hash = self.inventory(rows, accepted=[accepted])
        self.assertEqual(self.queue_job(other['job']['id'])['state'], 'reserved')
        result = self.start(prepared, approval, inv, inv_hash)
        report = json.loads(result.stdout)
        self.assertEqual(report['outcome'], 'launch_accepted')
        self.assertEqual(report['plan']['status'], 'ready')
        self.assertEqual(len(self.engine_calls('run')), 2)

    def test_reserved_job_with_disjoint_scope_does_not_block(self):
        other = self.reserved_other_job(scope=('other.txt',))
        draft, prepared, approval, _ = self.approved()
        rows = [self.job_row(prepared),
                dict(id=other['preview']['task_id'],
                     task_sha256=other['preview']['task_sha256'],
                     worker='other-worker', depends_on=[],
                     job_id=other['job']['id'])]
        inv, inv_hash = self.inventory(rows)
        result = self.start(prepared, approval, inv, inv_hash)
        report = json.loads(result.stdout)
        self.assertEqual(report['outcome'], 'launch_accepted')
        self.assertEqual(len(self.engine_calls('run')), 2)
        self.assertTrue((self.coord / 'tasks' / (prepared['task']['id'] + '.md')).exists())

    def test_public_output_is_sanitized(self):
        marker = 'PRIVATE-REQUEST-9f2a1c'
        draft = self.plans.create('Implement this. ' + marker)
        request_key = self.key()
        result = self.dispatch('prepare', '--draft-id', draft['id'], '--draft-sha256',
                               draft['content_sha256'], '--request-key', request_key,
                               json_output=False)
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn('test -s', result.stdout)
        self.assertNotIn(request_key, result.stdout)
        self.assertNotIn(str(self.project), result.stdout)
        prepared = json.loads(self.dispatch('prepare', '--draft-id', draft['id'],
                                            '--draft-sha256', draft['content_sha256'],
                                            '--request-key', request_key).stdout)
        self.assertEqual(prepared['outcome'], 'prepared')
        approval = self.key()
        result = self.dispatch('approve', '--job-id', prepared['job']['id'],
                               '--draft-sha256', draft['content_sha256'],
                               '--preview-sha256', prepared['preview_sha256'],
                               '--approval-key', approval, json_output=False)
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn('test -s', result.stdout)
        self.assertNotIn(approval, result.stdout)
        inv, inv_hash = self.inventory([self.job_row(prepared)])
        reservation = self.key()
        result = self.start(prepared, approval, inv, inv_hash,
                            reservation=reservation, json_output=False)
        self.assertNotIn(marker, result.stdout)
        self.assertNotIn('test -s', result.stdout)
        self.assertNotIn('## Allowed scope', result.stdout)
        self.assertNotIn(reservation, result.stdout)
        self.assertNotIn(approval, result.stdout)
        self.assertNotIn(str(self.project), result.stdout)
        report = json.loads(self.start(prepared, approval, inv, inv_hash,
                                       reservation=reservation).stdout)
        self.assertEqual(report['outcome'], 'launch_accepted')
        self.assertNotIn(marker, json.dumps(report))
        self.assertNotIn('test -s', json.dumps(report))
        self.assertNotIn(reservation, json.dumps(report))
        self.assertNotIn(str(self.project), json.dumps(report))


if __name__ == '__main__':
    unittest.main(verbosity=2)
