# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Disposable real Git/PlanStore/JobStore fixtures; native mock, zero providers."""
import concurrent.futures
from contextlib import contextmanager
import copy
import fcntl
import hashlib
import importlib.util
import inspect
import io
import json
import multiprocessing
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import uuid

sys.path.insert(0, str(Path(__file__).parents[1]))
from execution_service import ExecutionService, ExecutionError
import execution_service as service
from job_store import JobStore
from plan_store import PlanStore

MOCK = r'''#!/usr/bin/env python3
import hashlib, json, os, pathlib, subprocess, sys, time
root = pathlib.Path.cwd().parent
assert pathlib.Path.cwd() == root / 'repo'
assert os.environ['UNIO_CONF_DIR'] == str(root / 'config')
assert all(os.environ[k] == '0' for k in ('UNIO_AUTO_OFF','UNIO_AUTO_VERIFY','UNIO_AUTO_SYNC'))
assert sys.stdin.buffer.read() == b''
args = sys.argv[1:]
worker = 'mock-worker'
reviewer = 'other'
if args[0] == 'run':
    assert len(args) == 4 and args[1:3] == ['-b',worker]
    task = args[3]
elif args[0] == 'review':
    assert len(args) == 4 and args[1] == worker and args[3] == reviewer
    task = args[2]
elif args[0] in ('result', 'verify'):
    assert args[1] == worker
    assert len(args) == 3
    task = args[2]
elif args[0] == 'kill':
    assert len(args) == 2
    task = args[1]
else:
    raise AssertionError('unsupported native operation')
assert task.startswith('ui-') and len(task) == 35
with (root / 'calls.jsonl').open('a') as output:
    output.write(json.dumps(dict(argv=args, pid=os.getpid())) + '\n')
control_path = root / 'control.json'
control = json.loads(control_path.read_text()) if control_path.exists() else {}
wt = root / 'wt' / worker
tf = root / 'coord/tasks' / (task + '.md')
result_path = root / 'coord/results' / worker / (task + '.json')
def git(*a):
    return subprocess.check_output(['git','-C',str(wt),*a]).decode().strip()
def revision():
    content = (wt / 'source.txt').read_bytes()
    work = hashlib.sha256(content + str((wt / 'source.txt').stat().st_mode).encode()).hexdigest()
    base = (root / 'coord/base').read_text().strip()
    return dict(base_commit=git('rev-parse',base), candidate_commit=git('rev-parse','HEAD'),
                task_sha256=hashlib.sha256(tf.read_bytes()).hexdigest(),worktree_sha256=work)
def write(d):
    result_path.parent.mkdir(parents=True, exist_ok=True)
    temp = result_path.with_suffix('.tmp')
    temp.write_text(json.dumps(d))
    temp.replace(result_path)
def current(d):
    rev = revision()
    d['current_revision'] = rev
    d['stale'] = any(s['revision'] != rev for s in [d[k] for k in ('process','validation','review')]
                     if s['state'] != 'not_run')
    d['ready_for_human_review'] = not d['stale'] and all(d[k]['state'] == state and d[k]['revision'] == rev
        for k,state in [('process','succeeded'),('validation','passed'),('review','approved')])
    return d
if args[0] == 'result':
    if control.get('result') == 'flood':
        sys.stdout.write('x' * (2 * 1024 * 1024)); sys.exit(0)
    if control.get('result') == 'hang': time.sleep(5)
    if control.get('result') == 'bad': print('{bad PRIVATE'); sys.exit(0)
    if not result_path.exists(): sys.exit(2)
    d = json.loads(result_path.read_text())
    if control.get('result') != 'raw': d = current(d)
    d.update(human={'state':'pending','private':'SECRET'}, integration={'state':'not_attempted'}, raw_log='SECRET')
    print(json.dumps(d)); sys.exit(0)
if args[0] == 'run':
    assert tf.is_file()
    if control.get('run') != 'running':
        (wt / 'source.txt').write_text('implemented\n')
        subprocess.check_call(['git','-C',str(wt),'add','source.txt'], stdout=subprocess.DEVNULL)
        subprocess.check_call(['git','-C',str(wt),'commit','-qm','mock work'], stdout=subprocess.DEVNULL)
    rev = revision()
    d = dict(schema_version=1,worker=worker,task=task,updated_at='2026-10-05T21:00:00+00:00',
        current_revision=rev,process=dict(state='running' if control.get('run') == 'running' else 'succeeded',
        exit_code=None if control.get('run') == 'running' else 0,revision=rev),
        validation=dict(state='not_run',scope='UNCHECKED',checks_run=0,checks_failed=0,reasons=[],revision=None),
        review=dict(state='not_run',reviewer=None,process_exit_code=None,material_complete=False,reasons=[],revision=None),
        stale=False,ready_for_human_review=False)
    write(d)
else:
    d = current(json.loads(result_path.read_text()))
    rev = d['current_revision']
    if args[0] == 'verify':
        assert d['process']['state'] == 'succeeded' and d['process']['exit_code'] == 0
        sections = {}; active = None
        for line in tf.read_text().split('\n'):
            if line.startswith('## '): active = line[3:]; sections.setdefault(active, []); continue
            if active: sections[active].append(line)
        scope = [s[2:] for s in sections['Allowed scope'] if s.startswith('- ')]
        checks = [s[2:] for s in sections['Validate'] if s.startswith('$ ')]
        assert scope == ['source.txt'] and checks
        failures = sum(subprocess.run(command, shell=True, cwd=wt, stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0 for command in checks)
        d['validation'] = dict(state='failed' if failures else 'passed',scope='OK',checks_run=len(checks),
             checks_failed=failures,reasons=['check_failed'] if failures else [],revision=rev)
        d['review'] = dict(state='not_run',reviewer=None,process_exit_code=None,material_complete=False,reasons=[],revision=None)
        write(current(d))
    elif args[0] == 'review':
        assert d['validation']['state'] == 'passed' and d['validation']['revision'] == rev and not d['stale']
        failed = control.get('review') == 'fail'
        d['review'] = dict(state='failed' if failed else 'approved',reviewer=reviewer,
            process_exit_code=7 if failed else 0,material_complete=True,
            reasons=['reviewer_process_failed'] if failed else [],revision=rev)
        write(current(d))
    elif args[0] == 'kill':
        if control.get('kill') != 'unknown':
            d['process'] = dict(state='failed',exit_code=143,revision=rev)
            write(current(d))
if control.get('pause') == args[0]:
    (root / 'entered').write_text(args[0])
    end = time.monotonic() + 8
    while not (root / 'release').exists() and time.monotonic() < end: time.sleep(.01)
if control.get('hang') == args[0]: time.sleep(5)
(root / ('finished-' + args[0])).write_text('done')
if args[0] == 'review' and control.get('review') == 'fail': sys.exit(7)
if args[0] == 'verify' and d['validation']['checks_failed']: sys.exit(1)
if args[0] == 'run' and control.get('run') == 'nonzero': sys.exit(9)
'''


def call_in_process(arguments, method, inputs, ready, output):
    try:
        instance = ExecutionService(*arguments)
        ready.wait(5)
        try:
            output.put(('ok', getattr(instance, method)(*inputs)))
        except ExecutionError as error:
            output.put(('error', error.code))
        finally:
            instance.close()
    except BaseException as error:
        if isinstance(error, ExecutionError):
            output.put(('error', error.code))
        else:
            output.put(('unexpected', type(error).__name__))


class ExecutionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='execution-service-')
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        for name in ('repo', 'coord/tasks', 'wt', 'config'):
            (self.workspace / name).mkdir(parents=True)
        self.repo = self.workspace / 'repo'
        self.git(self.repo, 'init', '-q', '-b', 'main')
        self.git(self.repo, 'config', 'user.email', 'mock@invalid')
        self.git(self.repo, 'config', 'user.name', 'Mock')
        (self.repo / 'source.txt').write_text('base\n')
        self.git(self.repo, 'add', 'source.txt')
        self.git(self.repo, 'commit', '-qm', 'base')
        self.wt = self.workspace / 'wt/mock-worker'
        self.git(self.repo, 'worktree', 'add', '-q', '-b', 'agent/mock-worker', str(self.wt))
        (self.workspace / 'coord/base').write_text('main\n')
        self.engine = self.workspace / 'engine'
        self.engine.write_text(MOCK)
        self.engine.chmod(0o700)
        self.config = self.workspace / 'config'
        (self.config / 'agents.conf').write_text('mock=NEVER_REAL_PROVIDER\nother=NEVER_REAL_PROVIDER\n')
        self.template = self.workspace / 'template.json'
        self.write_template()
        self.arguments = (self.workspace, self.engine, 'mock-worker', 'other', self.config,
                          self.template, 'Mock Company', 'Another Company')
        self.plans = PlanStore(self.workspace)
        self.addCleanup(self.plans.close)
        self.instance = self.open()

    def open(self, arguments=None):
        instance = ExecutionService(*(arguments or self.arguments))
        self.addCleanup(instance.close)
        return instance

    def git(self, directory, *args):
        return subprocess.check_output(['git', '-C', str(directory), *args], stderr=subprocess.PIPE).decode().strip()

    def write_template(self, **changes):
        self.template.write_text(json.dumps(dict(schema_version=1, instructions='Implement the literal saved request.',
            scope=['source.txt'], validate=["test -s 'source.txt'"], **changes)))

    def key(self):
        return uuid.uuid4().hex

    def error(self, code, function, *args, **kwargs):
        with self.assertRaises(ExecutionError) as caught:
            function(*args, **kwargs)
        self.assertEqual((caught.exception.code, caught.exception.status), (code, service.ERRORS[code]))
        self.assertEqual(str(caught.exception), code)

    def control(self, **values):
        (self.workspace / 'control.json').write_text(json.dumps(values))

    def calls(self, operation=None):
        path = self.workspace / 'calls.jsonl'
        calls = [json.loads(line)['argv'] for line in path.read_text().splitlines()] if path.exists() else []
        return [args for args in calls if operation is None or args[0] == operation]

    def prepared(self, request='Implement this.', key=None):
        draft = self.plans.create(request)
        view = self.instance.prepare(draft['id'], draft['content_sha256'], key or self.key())
        return draft, view

    def approved(self, request='Implement this.'):
        draft, view = self.prepared(request)
        approval = self.key()
        view = self.instance.approve(view['job']['id'], draft['content_sha256'], approval, view['preview']['preview_hash'])
        return draft, view, approval

    def started(self):
        draft, view, approval = self.approved()
        reservation = self.key()
        view = self.instance.start(view['job']['id'], approval, reservation)
        return draft, view, approval, reservation

    def reviewed(self):
        draft, view, approval, reservation = self.started()
        identity = view['job']['id']
        view = self.instance.verify(identity, self.key())
        view = self.instance.review(identity, self.key())
        return draft, view, approval, reservation

    def native_path(self, view):
        return self.workspace / 'coord/results/mock-worker' / (view['preview']['task_id'] + '.json')

    def state_path(self, view):
        return self.workspace / 'coord/ui-execution/states' / (view['job']['id'] + '.json')

    def binding_path(self, view):
        return self.workspace / 'coord/ui-execution/bindings' / (view['job']['id'] + '.json')

    def concurrency(self, method, first, second):
        context = multiprocessing.get_context('fork')
        ready, output = context.Event(), context.Queue()
        children = [context.Process(target=call_in_process,
            args=(self.arguments, method, inputs, ready, output)) for inputs in (first, second)]
        for child in children: child.start()
        ready.set()
        results = [output.get(timeout=45) for _ in children]
        for child in children:
            child.join(5)
            self.assertEqual(child.exitcode, 0)
        output.close()
        return results

    def wait_for(self, path):
        end = time.monotonic() + 45
        while not path.exists() and time.monotonic() < end:
            time.sleep(.01)
        self.assertTrue(path.exists(), str(path.name))

    @contextmanager
    def observe_engine_starts(self, operation):
        with patch('subprocess.Popen', wraps=subprocess.Popen) as popen:
            yield lambda: [call.args[0] for call in popen.call_args_list
                           if call.args and call.args[0] and call.args[0][0] == str(self.engine)
                           and len(call.args[0]) > 1 and call.args[0][1] == operation]

    def test_frozen_signatures_and_errors(self):
        signatures = dict(prepare='draft_id expected_hash request_key', approve='job_id expected_hash approval_key preview_hash',
            start='job_id approval_key reservation_key preflight', verify='job_id action_key', review='job_id action_key',
            accept='job_id revision_hash action_key', stop='job_id action_key', cancel='job_id', get='job_id', jobs='', close='')
        for name, names in signatures.items():
            self.assertEqual(list(inspect.signature(getattr(ExecutionService, name)).parameters), ['self'] + names.split())
        # The only deliberate extension: an optional keyword-only start hook.
        # Existing HTTP callers keep their three-positional-argument behavior.
        hook = inspect.signature(ExecutionService.start).parameters['preflight']
        self.assertIs(hook.kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(hook.default, None)
        self.assertEqual(list(inspect.signature(ExecutionService).parameters),
            ['workspace','engine','worker','reviewer','config_dir','template_path','worker_company','reviewer_company'])
        for code, status in service.ERRORS.items():
            self.assertEqual(ExecutionError(code).status, status)

    def test_start_preflight_refusal_preserves_approval_and_task_absence(self):
        draft, view, approval = self.approved()
        identity = view['job']['id']
        def refuse(_binding):
            raise ExecutionError('not_ready')
        self.error('not_ready', self.instance.start, identity, approval, self.key(), preflight=refuse)
        after = self.instance.get(identity)
        self.assertEqual(after['job']['state'], 'approved')
        self.assertEqual(after['execution'], dict(state='not_started', launcher_exit=None))
        self.assertFalse((self.workspace / 'coord/tasks' / (view['preview']['task_id'] + '.md')).exists())
        with JobStore(self.workspace) as store:
            self.assertIsNone(store.get(identity)['reservation_key'])
        self.assertEqual(self.calls(), [])
        # A noncallable hook is refused before any coordination or mutation.
        self.error('invalid_request', self.instance.start, identity, approval, self.key(), preflight=object())
        self.assertEqual(self.instance.get(identity)['job']['state'], 'approved')
        self.assertEqual(self.calls(), [])

    def test_start_preflight_runs_under_lock_and_only_on_fresh_start(self):
        draft, view = self.prepared()
        identity = view['job']['id']
        seen = []
        def under_lock(binding):
            seen.append(binding['job_id'])
            binding['preview']['worker'] = 'mutated'  # a private copy, never the stored binding
            descriptor = os.open(self.workspace / 'coord/ui-execution/lock', os.O_RDWR)
            try:
                with self.assertRaises(BlockingIOError):
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(descriptor)
        # Not approved yet: the callback never runs for a refused start.
        self.error('conflict', self.instance.start, identity, self.key(), self.key(), preflight=under_lock)
        self.assertEqual(seen, [])
        approval = self.key()
        self.instance.approve(identity, draft['content_sha256'], approval, view['preview']['preview_hash'])
        reservation = self.key()
        started = self.instance.start(identity, approval, reservation, preflight=under_lock)
        self.assertEqual(seen, [identity])
        self.assertEqual(started['execution'], dict(state='launch_accepted', launcher_exit=0))
        # A same-key replay returns the existing evidence without the callback.
        replay = self.instance.start(identity, approval, reservation, preflight=under_lock)
        self.assertEqual(seen, [identity])
        self.assertEqual(replay['execution'], started['execution'])
        self.assertEqual(len(self.calls('run')), 1)

    def test_start_preflight_replay_keeps_unknown_without_callback(self):
        draft, view, approval = self.approved()
        identity = view['job']['id']; key = self.key()
        seen = []
        def record(binding):
            seen.append(binding['job_id'])
        write = self.instance._state_write
        failed = False
        def fail_receipt_once(state):
            nonlocal failed
            if state['execution']['state'] == 'launch_accepted' and not failed:
                failed = True
                raise OSError('PRIVATE receipt failure')
            return write(state)
        with patch.object(self.instance, '_state_write', side_effect=fail_receipt_once):
            self.error('outcome_unknown', self.instance.start, identity, approval, key, preflight=record)
        self.assertEqual(seen, [identity])
        # The lost receipt stays unknown; its replay never reruns the callback
        # or launches again, and a changed key never retries.
        got = self.open().start(identity, approval, key, preflight=record)
        self.assertEqual(seen, [identity])
        self.assertEqual(got['job']['state'], 'completion_unknown')
        self.assertIn('outcome_unknown', got['warnings'])
        self.assertEqual(len(self.calls('run')), 1)
        self.error('conflict', self.open().start, identity, approval, self.key(), preflight=record)
        self.assertEqual(seen, [identity])
        self.assertEqual(len(self.calls('run')), 1)

    def test_queue_backed_happy_flow_exact_public_view_and_acceptance(self):
        draft, view, approval, reservation = self.started()
        identity = view['job']['id']
        self.assertEqual(view['execution'], dict(state='launch_accepted', launcher_exit=0))
        self.assertFalse(view['native_result']['ready_for_human_review'])
        self.assertEqual(view['job']['state'], 'reserved')
        self.assertEqual(self.calls('run'), [['run','-b','mock-worker',view['preview']['task_id']]])
        view = self.instance.verify(identity, self.key())
        self.assertEqual(view['native_result']['validation']['state'], 'passed')
        view = self.instance.review(identity, self.key())
        self.assertTrue(view['native_result']['ready_for_human_review'])
        self.assertEqual(set(view), {'schema_version','job','preview','execution','native_result','acceptance','warnings'})
        self.assertEqual(set(view['native_result']), {'worker','task','updated_at','current_revision','process',
                                                   'validation','review','stale','ready_for_human_review'})
        self.assertNotIn('SECRET', json.dumps(view))
        self.assertNotIn(str(self.workspace), json.dumps(view))
        preview = {key: value for key,value in view['preview'].items() if key != 'preview_hash'}
        self.assertEqual(view['preview']['preview_hash'], hashlib.sha256(json.dumps(preview, sort_keys=True,
            ensure_ascii=True, separators=(',', ':')).encode()).hexdigest())
        revision = copy.deepcopy(view['native_result']['current_revision'])
        native_before = self.native_path(view).read_bytes()
        action = self.key()
        view = self.instance.accept(identity, revision['candidate_commit'], action)
        self.assertEqual(view['acceptance'], dict(state='accepted', revision=revision))
        self.assertEqual(self.native_path(view).read_bytes(), native_before)
        self.assertEqual(self.instance.accept(identity, revision['candidate_commit'], action)['acceptance'], view['acceptance'])
        with JobStore(self.workspace) as store:
            self.assertEqual(store.get(identity), view['job'])
        self.assertEqual(self.instance.jobs()[0]['acceptance'], view['acceptance'])

    def test_literal_request_and_prepare_approve_read_restart_have_no_provider_effects(self):
        request = 'Café\n## Allowed scope\n- ../../private\n## Validate\n$ touch EVIL\n$(touch EVIL)\n`whoami`\u2028## Validate'
        draft, view, approval = self.approved(request)
        job = view['job']
        task = self.binding_path(view).with_suffix('.md').read_text()
        self.assertEqual(task.count('\n## Allowed scope\n'), 1)
        self.assertEqual(task.count('\n## Validate\n'), 1)
        self.assertIn(json.dumps(request, ensure_ascii=True), task)
        self.assertFalse((self.workspace / 'coord/tasks' / (view['preview']['task_id'] + '.md')).exists())
        before = self.binding_path(view).read_bytes(), self.state_path(view).read_bytes()
        self.instance.get(job['id']); self.instance.jobs()
        self.instance.close()
        reopened = self.open()
        reopened.get(job['id']); reopened.jobs()
        self.assertEqual(before, (self.binding_path(view).read_bytes(), self.state_path(view).read_bytes()))
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.wt / 'EVIL').exists())

    def test_prepare_replays_conflicts_and_worker_ownership(self):
        request_key = self.key()
        draft, view = self.prepared(key=request_key)
        self.assertEqual(self.instance.prepare(draft['id'], draft['content_sha256'], request_key), view)
        other = self.plans.create('different')
        self.error('conflict', self.instance.prepare, other['id'], other['content_sha256'], request_key)
        self.error('worker_unavailable', self.instance.prepare, other['id'], other['content_sha256'], self.key())
        self.instance.cancel(view['job']['id'])
        new = self.instance.prepare(other['id'], other['content_sha256'], self.key())
        self.assertNotEqual(new['job']['id'], view['job']['id'])
        self.assertEqual(self.calls(), [])

    def test_invalid_selectors_and_hashes_have_no_effect(self):
        for value in ('../private', '-worker', 'A' * 32, None, {}, 'a' * 33):
            self.error('invalid_request', self.instance.get, value)
            self.error('invalid_request', self.instance.prepare, value, 'a' * 64, self.key())
        draft, view = self.prepared()
        self.error('invalid_request', self.instance.start, view['job']['id'], 'x', self.key())
        self.error('invalid_request', self.instance.accept, view['job']['id'], 'a' * 41, self.key())
        self.assertEqual(self.calls(), [])

    def test_unbound_queue_rows_are_not_exposed_or_adopted(self):
        draft = self.plans.create('unbound')
        with JobStore(self.workspace) as store:
            job = store.enqueue(draft['id'], draft['content_sha256'], 'mock-worker', self.key())
        self.error('job_not_found', self.instance.get, job['id'])
        self.assertEqual(self.instance.jobs(), [])
        other = self.plans.create('new')
        self.error('outcome_unknown', self.instance.prepare, other['id'], other['content_sha256'], self.key())

    def test_stop_gate_and_stale_draft_before_approval_and_start(self):
        draft, view, approval = self.approved()
        identity = view['job']['id']
        stop = self.workspace / 'coord/STOP'
        stop.write_text('stop')
        self.error('stopped', self.instance.start, identity, approval, self.key())
        self.assertIn('stopped', self.instance.get(identity)['warnings'])
        stop.unlink()
        path = self.workspace / 'coord/ui-plans' / (draft['id'] + '.json')
        document = json.loads(path.read_text()); document['request'] = 'changed'; path.write_text(json.dumps(document))
        self.error('draft_stale', self.instance.start, identity, approval, self.key())
        self.error('draft_stale', self.instance.approve, identity, draft['content_sha256'], approval, view['preview']['preview_hash'])
        self.assertIn('draft_stale', self.instance.get(identity)['warnings'])
        self.assertEqual(self.calls(), [])

    def test_preview_approval_is_bound_and_idempotent(self):
        draft, view = self.prepared()
        key = self.key(); identity = view['job']['id']
        self.error('conflict', self.instance.approve, identity, draft['content_sha256'], key, 'f' * 64)
        approved = self.instance.approve(identity, draft['content_sha256'], key, view['preview']['preview_hash'])
        self.assertEqual(self.instance.approve(identity, draft['content_sha256'], key, view['preview']['preview_hash']), approved)
        self.error('conflict', self.instance.approve, identity, draft['content_sha256'], self.key(), view['preview']['preview_hash'])
        self.error('conflict', self.instance.approve, identity, 'f' * 64, key, view['preview']['preview_hash'])
        self.assertEqual(self.calls(), [])

    def test_template_heading_scope_and_command_guards(self):
        original = json.loads(self.template.read_text())
        invalid = [dict(instructions='x\n## Allowed scope\n- evil'), dict(instructions='## Validate\n$ evil'),
            dict(instructions=''), dict(instructions='x' * 12001), dict(scope=['../secret']), dict(scope=['a/../b']),
            dict(scope=['/absolute']), dict(scope=['a\n## Validate']), dict(scope=['a','a']), dict(scope=[]),
            dict(scope=['a\\b']), dict(scope=['a/./b']), dict(scope=['a\x00']), dict(validate=[]),
            dict(validate=['echo hi\n$ evil']), dict(validate=['x' * 2001]), dict(validate=['  ']),
            dict(schema_version=True), dict(extra='selector')]
        for changes in invalid:
            with self.subTest(changes=str(changes)[:60]):
                self.template.write_text(json.dumps({**original, **changes}))
                self.error('invalid_request', ExecutionService, *self.arguments)
        self.template.write_text('{"schema_version":1,"schema_version":1}')
        self.error('invalid_request', ExecutionService, *self.arguments)
        self.template.write_text(json.dumps(original))
        self.assertEqual(self.calls(), [])

    def test_clean_current_base_and_hidden_edit_guards(self):
        draft = self.plans.create('clean base required')
        def prepare(): return self.instance.prepare(draft['id'], draft['content_sha256'], self.key())
        (self.wt / 'untracked').write_text('dirty')
        self.error('worker_unavailable', prepare)
        (self.wt / 'untracked').unlink()
        for flag, undo in (('--assume-unchanged','--no-assume-unchanged'), ('--skip-worktree','--no-skip-worktree')):
            self.git(self.wt, 'update-index', flag, 'source.txt')
            self.error('worker_unavailable', prepare)
            self.git(self.wt, 'update-index', undo, 'source.txt')
        self.git(self.wt, 'config', 'core.sparseCheckout', 'true')
        self.error('worker_unavailable', prepare)
        self.git(self.wt, 'config', 'core.sparseCheckout', 'false')
        (self.repo / 'source.txt').write_text('new base')
        self.git(self.repo, 'add', 'source.txt'); self.git(self.repo, 'commit', '-qm', 'base advanced')
        self.error('worker_unavailable', prepare)
        self.assertEqual(self.calls(), [])

    def test_sparse_boolean_bare_true_refused(self):
        _, view, approval = self.approved()
        with (self.repo / '.git/config').open('a') as config:
            config.write('\n[core]\n\tsparseCheckout\n')
        self.assertEqual(self.git(self.wt, 'config', '--get-all', 'core.sparseCheckout'), '')
        self.assertEqual(self.git(self.wt, 'config', '--type=bool', '--get-all',
                                  'core.sparseCheckout'), 'true')
        self.error('worker_unavailable', self.instance._worker_revision)
        self.error('worker_unavailable', self.instance.start, view['job']['id'], approval, self.key())
        self.assertEqual(self.calls(), [])

    def test_sparse_boolean_empty_false_allowed(self):
        expected = self.git(self.wt, 'rev-parse', 'HEAD')
        self.assertEqual(self.instance._worker_revision(), expected)  # missing key remains allowed
        self.git(self.wt, 'config', 'core.sparseCheckout', '')
        self.assertEqual(self.git(self.wt, 'config', '--get-all', 'core.sparseCheckout'), '')
        self.assertEqual(self.git(self.wt, 'config', '--type=bool', '--get-all',
                                  'core.sparseCheckout'), 'false')
        original = self.instance._call
        with patch.object(self.instance, '_call', wraps=original) as calls:
            self.assertEqual(self.instance._worker_revision(), expected)
            self.assertEqual(calls.call_count, 4)
            self.assertEqual(calls.call_args_list[-1].args,
                             (['git', '-C', str(self.wt), 'config', '--type=bool',
                               '--get-all', 'core.sparseCheckout'], 15))
        _, view, _, _ = self.started()
        self.assertEqual(view['execution']['state'], 'launch_accepted')
        self.assertEqual(view['native_result']['process']['state'], 'succeeded')
        self.assertEqual(len(self.calls('run')), 1)
        self.assertEqual(view['native_result']['current_revision']['candidate_commit'],
                         self.git(self.wt, 'rev-parse', 'HEAD'))

    def test_sparse_boolean_malformed_and_duplicate_refused(self):
        _, view, approval = self.approved()
        for values in (('not-a-boolean',), ('false', 'false'), ('true', 'false'),
                       ('false', 'true'), ('', 'false')):
            with self.subTest(values=values):
                self.git(self.wt, 'config', '--replace-all', 'core.sparseCheckout', values[0])
                for value in values[1:]:
                    self.git(self.wt, 'config', '--add', 'core.sparseCheckout', value)
                typed = subprocess.run(['git', '-C', str(self.wt), 'config', '--type=bool',
                                        '--get-all', 'core.sparseCheckout'],
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if len(values) == 1:
                    self.assertNotEqual(typed.returncode, 0)
                else:
                    self.assertEqual(typed.returncode, 0)
                    self.assertEqual(typed.stdout.count(b'\n'), len(values))
                self.error('worker_unavailable', self.instance._worker_revision)
                self.error('worker_unavailable', self.instance.start, view['job']['id'], approval, self.key())
                self.assertEqual(self.calls(), [])
        self.git(self.wt, 'config', '--replace-all', 'core.sparseCheckout', 'false')
        original = self.instance._call
        for code, raw in ((0, b''), (0, b'\n'), (0, b'FALSE\n'), (0, b'false\r\n'),
                          (0, b'false'), (0, b'false\nfalse\n'), (0, b'false\0'),
                          (1, b'false\n'), (128, b'false\n'), (2, b'')):
            with self.subTest(code=code, raw=raw):
                def call(argv, timeout):
                    if 'config' in argv:
                        return code, raw
                    return original(argv, timeout)
                with patch.object(self.instance, '_call', side_effect=call):
                    self.error('worker_unavailable', self.instance.start,
                               view['job']['id'], approval, self.key())
                self.assertEqual(self.calls(), [])

    def test_worker_observation_cost_and_fresh_head_branch(self):
        original = self.instance._call
        with patch.object(self.instance, '_call', wraps=original) as calls:
            initial = self.instance._worker_revision()
            self.assertLessEqual(calls.call_count, 4)  # formerly seven Git processes
            self.assertTrue(all(call.args[0][0] == 'git' and call.args[1] == 15
                                for call in calls.call_args_list))
        (self.wt / 'source.txt').write_text('new head\n')
        self.git(self.wt, 'add', 'source.txt'); self.git(self.wt, 'commit', '-qm', 'advance')
        self.assertNotEqual(self.instance._worker_revision(), initial)
        self.error('worker_unavailable', self.instance._worker_revision, clean=True)
        self.git(self.wt, 'checkout', '--detach', '-q')
        self.error('worker_unavailable', self.instance._worker_revision)
        self.git(self.wt, 'checkout', '-qb', 'foreign')
        self.error('worker_unavailable', self.instance._worker_revision)

    def test_worker_observation_refuses_foreign_common_directory_and_unmerged_index(self):
        foreign = self.workspace / 'foreign'
        foreign.mkdir()
        self.git(foreign, 'init', '-q', '-b', 'agent/mock-worker')
        self.git(foreign, 'config', 'user.email', 'mock@invalid')
        self.git(foreign, 'config', 'user.name', 'Mock')
        (foreign / 'source.txt').write_text('foreign')
        self.git(foreign, 'add', 'source.txt'); self.git(foreign, 'commit', '-qm', 'foreign')
        git_file = self.wt / '.git'; original = git_file.read_bytes()
        try:
            git_file.write_text('gitdir: ' + str(foreign / '.git') + '\n')
            self.error('worker_unavailable', self.instance._worker_revision)
        finally:
            git_file.write_bytes(original)
        blob = self.git(self.wt, 'rev-parse', 'HEAD:source.txt')
        subprocess.run(['git', '-C', str(self.wt), 'update-index', '--index-info'],
                       input=f'0 {"0" * 40}\tsource.txt\n100644 {blob} 1\tsource.txt\n'.encode(),
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.error('worker_unavailable', self.instance._worker_revision)
        self.assertEqual(self.calls(), [])

    def test_batched_git_output_requires_unambiguous_framing(self):
        original = self.instance._git
        metadata = original(self.wt, 'rev-parse', '--path-format=absolute', '--git-common-dir',
                            'HEAD^{commit}', '--symbolic-full-name', 'HEAD')
        index = original(self.wt, 'ls-files', '--stage', '-v', '-z')
        common, commit, branch, _ = metadata.split(b'\n')
        invalid_metadata = [metadata.rstrip(b'\n'), metadata + b'extra\n',
                            metadata.replace(commit, b'g' * 40),
                            metadata.replace(branch, b'HEAD'),
                            b'relative\n' + commit + b'\n' + branch + b'\n',
                            common + b'\r\n' + commit + b'\n' + branch + b'\n',
                            metadata.replace(branch, b'\xff')]
        invalid_index = [index.rstrip(b'\0'), index + index, b'\0', b'H garbage\0',
                         index.replace(b' 0\t', b' 2\t'), index.replace(b'H ', b'h '),
                         index.replace(b'H ', b'S '), index.replace(b'100644', b'040000'),
                         index.replace(b'\tsource.txt', b'\t'),
                         index.replace(b'100644 ', b'100644 ' + b'g' * 40)]
        for command, bad_outputs in (('rev-parse', invalid_metadata), ('ls-files', invalid_index)):
            for raw in bad_outputs:
                with self.subTest(command=command, raw=raw):
                    def git(directory, *arguments):
                        if directory == self.wt and arguments[0] == command:
                            return raw
                        return original(directory, *arguments)
                    with patch.object(self.instance, '_git', side_effect=git):
                        self.error('worker_unavailable', self.instance._worker_revision)

    def test_batched_index_accepts_literal_unusual_paths_and_sparse_config_refuses_ambiguity(self):
        for name in ('tab\tfile', 'line\nfile'):
            (self.wt / name).write_text('literal')
            self.git(self.wt, 'add', name)
        self.instance._worker_revision()
        original = self.instance._call
        for code, raw in ((0, b'true\n'), (0, b'false\ntrue\n'), (0, b'false'),
                          (1, b'false\n'), (2, b'')):
            with self.subTest(code=code, raw=raw):
                def call(argv, timeout):
                    if 'config' in argv:
                        return code, raw
                    return original(argv, timeout)
                with patch.object(self.instance, '_call', side_effect=call):
                    self.error('worker_unavailable', self.instance._worker_revision)

    def test_initial_cleanliness_is_not_required_for_start_replay_or_reopen(self):
        _, view, approval, reservation = self.started()
        identity = view['job']['id']
        (self.wt / 'source.txt').write_text('dirty after native run')
        self.instance.close()
        reopened = self.open()
        self.assertEqual(reopened.get(identity)['execution']['state'], 'launch_accepted')
        replay = reopened.start(identity, approval, reservation)
        self.assertTrue(replay['native_result']['stale'])
        self.assertEqual(len(self.calls('run')), 1)
        self.error('conflict', reopened.start, identity, approval, self.key())
        self.error('conflict', reopened.cancel, identity)

    def test_launcher_acceptance_never_implies_worker_completion(self):
        self.control(run='running')
        _, view, _, _ = self.started()
        self.assertEqual(view['execution']['state'], 'launch_accepted')
        self.assertEqual(view['native_result']['process']['state'], 'running')
        self.error('not_ready', self.instance.verify, view['job']['id'], self.key())
        self.error('not_ready', self.instance.review, view['job']['id'], self.key())
        self.assertEqual(self.calls('verify'), [])
        self.assertEqual(self.calls('review'), [])

    def test_task_publication_is_exclusive_and_immutable(self):
        draft, view, approval = self.approved()
        task_path = self.workspace / 'coord/tasks' / (view['preview']['task_id'] + '.md')
        task_path.write_text('conflict')
        self.error('binding_stale', self.instance.start, view['job']['id'], approval, self.key())
        self.assertEqual(task_path.read_text(), 'conflict')
        self.assertEqual(self.calls('run'), [])
        task_path.unlink()
        task_path.symlink_to(self.template)
        self.error('binding_stale', self.instance.start, view['job']['id'], approval, self.key())
        self.assertTrue(task_path.is_symlink())

    def test_binding_changes_refused_before_validate_commands(self):
        _, view, _, _ = self.started()
        identity = view['job']['id']
        mutations = [(self.config / 'agents.conf', b'changed config'), (self.template, b'{}'),
                     (self.engine, self.engine.read_bytes() + b'\n# changed'),
                     (self.workspace / 'coord/tasks' / (view['preview']['task_id'] + '.md'), b'tampered')]
        for path, replacement in mutations:
            with self.subTest(path=path.name):
                original = path.read_bytes(); path.write_bytes(replacement)
                self.error('binding_stale', self.instance.verify, identity, self.key())
                self.assertIn('binding_stale', self.instance.get(identity)['warnings'])
                path.write_bytes(original)
        (self.workspace / 'coord/agents.conf').write_text('new override')
        self.error('binding_stale', self.instance.verify, identity, self.key())
        (self.workspace / 'coord/agents.conf').unlink()
        self.assertEqual(self.calls('verify'), [])

    def test_two_process_concurrent_starts_and_reviews_spend_once(self):
        draft, view, approval = self.approved()
        identity, key = view['job']['id'], self.key()
        results = self.concurrency('start', (identity,approval,key), (identity,approval,key))
        self.assertTrue(any(result[0] == 'ok' for result in results), results)
        self.assertTrue(all(result[0] == 'ok' or result == ('error','worker_unavailable') for result in results), results)
        # The service deliberately bounds lock waits. A slow filesystem may
        # return busy to the overlapping caller; explicit identical replay
        # must still read the same attempt without another native invocation.
        self.instance.start(identity,approval,key)
        self.assertEqual(len(self.calls('run')), 1)
        self.instance.verify(identity, self.key())
        key = self.key()
        results = self.concurrency('review', (identity,key), (identity,key))
        self.assertTrue(any(result[0] == 'ok' for result in results), results)
        self.assertTrue(all(result[0] == 'ok' or result == ('error','worker_unavailable') for result in results), results)
        self.instance.review(identity,key)
        self.assertEqual(len(self.calls('review')), 1)
        self.error('conflict', self.open().review, identity, self.key())

    def test_two_process_different_review_keys_reserve_one_paid_intent(self):
        _, view, _, _ = self.started()
        identity = view['job']['id']; self.instance.verify(identity, self.key())
        results = self.concurrency('review', (identity,self.key()), (identity,self.key()))
        self.assertEqual(sorted(r[0] for r in results), ['error','ok'])
        self.assertTrue(any(result in (('error','conflict'), ('error','worker_unavailable')) for result in results), results)
        self.error('conflict', self.instance.review, identity,self.key())
        self.assertEqual(len(self.calls('review')), 1)

    def lost_response(self, method, inputs):
        self.control(pause=method)
        context = multiprocessing.get_context('fork')
        ready, output = context.Event(), context.Queue()
        child = context.Process(target=call_in_process, args=(self.arguments,method,inputs,ready,output))
        child.start(); ready.set()
        self.wait_for(self.workspace / 'entered')
        os.kill(child.pid, signal.SIGKILL); child.join(5)
        (self.workspace / 'release').write_text('release')
        self.wait_for(self.workspace / ('finished-' + method))
        output.close()

    def test_lost_start_response_restart_and_reads_do_not_relaunch_or_repair(self):
        draft, view, approval = self.approved(); identity = view['job']['id']; key = self.key()
        # The public method is start while the native pause operation is run.
        self.control(pause='run')
        context = multiprocessing.get_context('fork'); ready, output = context.Event(), context.Queue()
        child = context.Process(target=call_in_process,args=(self.arguments,'start',(identity,approval,key),ready,output))
        child.start(); ready.set(); self.wait_for(self.workspace / 'entered')
        os.kill(child.pid, signal.SIGKILL); child.join(5)
        (self.workspace / 'release').write_text('release'); self.wait_for(self.workspace / 'finished-run'); output.close()
        reopened = self.open()
        before = self.state_path(view).read_bytes()
        got = reopened.get(identity)
        self.assertEqual(got['execution']['state'], 'completion_unknown')
        self.assertEqual(got['job']['state'], 'reserved')
        reopened.jobs()
        self.assertEqual(self.state_path(view).read_bytes(), before)
        replay = reopened.start(identity, approval, key)
        self.assertEqual(replay['job']['state'], 'completion_unknown')
        self.assertEqual(len(self.calls('run')), 1)
        other = self.plans.create('another')
        self.error('worker_unavailable', reopened.prepare, other['id'], other['content_sha256'], self.key())
        self.error('outcome_unknown', reopened.verify, identity, self.key())

    def test_lost_review_response_never_grants_another_paid_review(self):
        _, view, _, _ = self.started(); identity = view['job']['id']
        self.instance.verify(identity, self.key()); key = self.key()
        self.lost_response('review', (identity,key))
        reopened = self.open(); before = self.state_path(view).read_bytes()
        got = reopened.get(identity)
        self.assertIn('outcome_unknown', got['warnings'])
        self.assertFalse(got['native_result']['ready_for_human_review'])
        self.assertEqual(self.state_path(view).read_bytes(), before)
        self.error('outcome_unknown', reopened.review, identity, self.key())
        reopened.review(identity,key)
        self.assertEqual(len(self.calls('review')), 1)

    def test_failed_review_and_native_exit_are_preserved_without_paid_retry(self):
        _, view, _, _ = self.started(); identity = view['job']['id']; self.instance.verify(identity, self.key())
        self.control(review='fail'); key = self.key()
        view = self.instance.review(identity,key)
        self.assertEqual(view['native_result']['review']['process_exit_code'], 7)
        action = json.loads((self.workspace / 'coord/ui-execution/actions' / (key + '.json')).read_text())
        self.assertEqual(action['exit_code'], 7)
        self.open().review(identity,key)
        self.error('conflict', self.instance.review, identity, self.key())
        self.assertEqual(len(self.calls('review')), 1)

    def test_bounded_launch_timeout_and_nonzero_are_unknown_not_retryable(self):
        draft, view, approval = self.approved(); identity = view['job']['id']; key = self.key()
        self.control(hang='run')
        with self.observe_engine_starts('run') as attempts:
            with patch.dict(service.DEADLINES, run=.15):
                self.error('outcome_unknown', self.instance.start, identity, approval, key)
            replay = self.open().start(identity,approval,key)
        self.assertEqual(replay['job']['state'], 'completion_unknown')
        self.assertLessEqual(len(self.calls('run')), 1, 'killed mock may not have logged')
        self.assertEqual(len(attempts()), 1, 'must have exactly one native Popen attempt')

    def test_unavailable_engine_after_intent_maps_failure_without_retry(self):
        draft, view, approval = self.approved(); identity = view['job']['id']; key = self.key()
        original = self.instance._call
        def call(argv, timeout):
            if argv[0] == str(self.engine) and argv[1] == 'run': raise service._NativeFailure(False)
            return original(argv,timeout)
        with patch.object(self.instance, '_call', side_effect=call):
            self.error('native_unavailable', self.instance.start, identity, approval, key)
        replay = self.instance.start(identity,approval,key)
        self.assertEqual(replay['job']['state'], 'completion_unknown')
        self.assertEqual(replay['execution']['state'], 'launch_failed')
        self.assertEqual(self.calls('run'), [])

    def test_native_malformed_private_fields_and_readiness_are_filtered(self):
        _, view, _, _ = self.reviewed(); identity = view['job']['id']; path = self.native_path(view)
        self.control(result='raw')
        original = json.loads(path.read_text())
        mutations = [dict(schema_version=True), dict(worker='other'), dict(task='other'),
            dict(updated_at='private text'), dict(stale='false'), dict(ready_for_human_review=1),
            dict(process={**original['process'],'exit_code':True}),
            dict(validation={**original['validation'],'scope':'PRIVATE'}),
            dict(validation={**original['validation'],'reasons':['SECRET /private/path']}),
            dict(validation={**original['validation'],'checks_run':True}),
            dict(review={**original['review'],'material_complete':'yes'}),
            dict(review={**original['review'],'process_exit_code':3}),
            dict(current_revision={**original['current_revision'],'task_sha256':'a' * 40}),
            dict(process={**original['process'],'revision':None})]
        for mutation in mutations:
            with self.subTest(mutation=repr(mutation)[:60]):
                path.write_text(json.dumps({**original,**mutation}))
                got = self.instance.get(identity)
                self.assertIsNone(got['native_result'])
                self.assertIn('native_result_invalid', got['warnings'])
                self.assertNotIn('SECRET', json.dumps(got))
        path.write_text(json.dumps(original))
        self.assertTrue(self.instance.get(identity)['native_result']['ready_for_human_review'])

    def test_bounded_result_output_and_deadline_do_not_change_ownership(self):
        _, view, _, _ = self.started(); identity = view['job']['id']; before = self.state_path(view).read_bytes()
        for mode in ('bad','flood','hang'):
            self.control(result=mode)
            with patch.dict(service.DEADLINES, result=.15):
                got = self.instance.get(identity)
            self.assertIsNone(got['native_result'])
            self.assertEqual(self.state_path(view).read_bytes(), before)
        self.assertEqual(len(self.calls('run')), 1)

    def test_acceptance_is_stale_after_any_full_revision_or_binding_change(self):
        _, view, _, _ = self.reviewed(); identity = view['job']['id']; revision = view['native_result']['current_revision']
        self.error('not_ready', self.instance.accept, identity, 'f' * 40, self.key())
        action = self.key(); accepted = self.instance.accept(identity,revision['candidate_commit'],action)
        (self.wt / 'source.txt').write_text('edit without a new commit')
        stale = self.instance.get(identity)
        self.assertEqual(stale['acceptance']['state'], 'stale')
        self.assertEqual(stale['acceptance']['revision'], accepted['acceptance']['revision'])
        self.error('not_ready', self.instance.accept, identity,revision['candidate_commit'],action)
        (self.wt / 'source.txt').write_text('implemented\n')
        (self.config / 'agents.conf').write_text('config drift')
        self.assertEqual(self.instance.get(identity)['acceptance']['state'], 'stale')

    def test_explicit_stop_is_exact_kill_and_does_not_release_ownership(self):
        self.control(run='running')
        _, view, _, _ = self.started(); identity = view['job']['id']; key = self.key()
        (self.workspace / 'coord/STOP').write_text('stop')
        view = self.instance.stop(identity,key)
        self.assertEqual(self.calls('kill'), [['kill',view['preview']['task_id']]])
        self.instance.stop(identity,key)
        self.assertEqual(len(self.calls('kill')), 1)
        self.error('conflict', self.instance.cancel, identity)
        self.assertEqual(view['native_result']['process']['state'], 'failed')

    def test_uncertain_kill_retains_ownership_and_unknown_state(self):
        self.control(run='running',kill='unknown')
        _, view, _, _ = self.started(); identity = view['job']['id']
        got = self.instance.stop(identity,self.key())
        self.assertEqual(got['job']['state'], 'completion_unknown')
        self.assertIn('outcome_unknown', got['warnings'])

    def test_cancel_before_reservation_is_idempotent_and_releases_binding(self):
        _, view, _ = self.approved(); identity = view['job']['id']
        got = self.instance.cancel(identity)
        self.assertEqual(got['job']['state'], 'cancelled')
        self.assertEqual(self.instance.cancel(identity), got)
        self.assertEqual(self.calls(), [])
        self.prepared()
        self.assertEqual(len(self.instance.jobs()), 2)

    def test_corrupt_ownership_binding_and_symlink_state_are_refused(self):
        _, view = self.prepared(); identity = view['job']['id']
        state = self.state_path(view); raw = state.read_bytes(); state.write_text('{}')
        self.error('storage_unavailable', self.instance.get, identity)
        state.write_bytes(raw)
        state.unlink(); state.symlink_to(self.template)
        self.error('storage_unavailable', self.instance.get, identity)
        state.unlink(); state.write_bytes(raw)
        owner = self.workspace / 'coord/ui-execution/mock-worker.json'
        owner.write_text('{}')
        self.error('storage_unavailable', ExecutionService, *self.arguments)

    def test_config_symlinks_special_files_and_bounds_are_refused(self):
        file = self.config / 'link'; file.symlink_to(self.template)
        self.error('invalid_request', ExecutionService, *self.arguments); file.unlink()
        os.mkfifo(file)
        self.error('invalid_request', ExecutionService, *self.arguments); file.unlink()
        for i in range(128): (self.config / ('file-' + str(i))).write_text('x')
        self.error('invalid_request', ExecutionService, *self.arguments)
        for i in range(128): (self.config / ('file-' + str(i))).unlink()
        file.write_bytes(b'x' * (service.CONFIG_LIMIT + 1))
        self.error('invalid_request', ExecutionService, *self.arguments); file.unlink()
        self.template.write_bytes(b'x' * (service.JSON_LIMIT + 1))
        self.error('invalid_request', ExecutionService, *self.arguments)

    def test_same_company_and_symlink_startup_paths_are_refused(self):
        arguments = list(self.arguments); arguments[-1] = arguments[-2]
        self.error('invalid_request', ExecutionService, *arguments)
        link = self.workspace / 'engine-link'; link.symlink_to(self.engine)
        arguments = list(self.arguments); arguments[1] = link
        self.error('invalid_request', ExecutionService, *arguments)

    def test_close_releases_descriptors_and_refuses_operations(self):
        self.instance.close(); self.instance.close()
        self.error('storage_unavailable', self.instance.jobs)
        self.assertIsNone(self.instance._fd)
        self.assertEqual(self.open().jobs(), [])

    def test_unknown_keyword_selectors_are_invalid_requests(self):
        _, view = self.prepared()
        for selector in ('worker', 'engine', 'config_dir', 'task', 'request'):
            self.error('invalid_request', self.instance.get, view['job']['id'], **{selector: '../private'})
        self.assertEqual(self.calls(), [])

    def test_threaded_prepare_uses_per_operation_queue_connections(self):
        draft = self.plans.create('threaded request'); key = self.key()
        def prepare(_):
            return self.instance.prepare(draft['id'], draft['content_sha256'], key)
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            views = list(pool.map(prepare, range(4)))
        self.assertTrue(all(view == views[0] for view in views))
        self.assertEqual(len(self.instance.jobs()), 1)
        self.assertEqual(self.calls(), [])

    def test_nonzero_launcher_is_not_completed_or_requeued(self):
        self.control(run='nonzero')
        _, view, approval, key = self.started(); identity = view['job']['id']
        self.assertEqual(view['execution'], dict(state='completion_unknown', launcher_exit=9))
        self.assertEqual(view['job']['state'], 'completion_unknown')
        self.assertFalse(view['native_result']['ready_for_human_review'])
        self.open().start(identity,approval,key)
        self.assertEqual(len(self.calls('run')), 1)

    def test_verify_failure_exit_and_replay_are_retained(self):
        original = json.loads(self.template.read_text()); original['validate'] = ['exit 4']
        self.template.write_text(json.dumps(original))
        _, view, _, _ = self.started(); identity = view['job']['id']; key = self.key()
        got = self.instance.verify(identity,key)
        self.assertEqual(got['native_result']['validation']['state'], 'failed')
        action_path = self.workspace / 'coord/ui-execution/actions' / (key + '.json')
        self.assertEqual(json.loads(action_path.read_text())['exit_code'], 1)
        self.open().verify(identity,key)
        self.assertEqual(len(self.calls('verify')), 1)
        self.error('conflict', self.instance.review, identity,key)
        self.error('not_ready', self.instance.review, identity,self.key())
        self.assertEqual(self.calls('review'), [])

    def test_review_timeout_preserves_paid_intent_after_restart(self):
        _, view, _, _ = self.started(); identity = view['job']['id']; self.instance.verify(identity,self.key())
        self.control(hang='review'); key = self.key()
        with self.observe_engine_starts('review') as attempts:
            with patch.dict(service.DEADLINES, review=.15):
                self.error('outcome_unknown', self.instance.review, identity,key)
            reopened = self.open(); reopened.review(identity,key)
            self.error('outcome_unknown', reopened.review, identity,self.key())
        self.assertLessEqual(len(self.calls('review')), 1, 'killed mock may not have logged')
        self.assertEqual(len(attempts()), 1, 'must have exactly one native Popen attempt')

    def test_orphan_review_intent_refuses_other_keys_without_a_provider_call(self):
        _, view, _, _ = self.started(); identity = view['job']['id']; self.instance.verify(identity,self.key())
        with patch.object(self.instance, '_state_write', side_effect=OSError('PRIVATE storage failure')):
            self.error('storage_unavailable', self.instance.review, identity,self.key())
        self.error('storage_unavailable', self.instance.review, identity,self.key())
        self.assertEqual(self.calls('review'), [])

    def test_unresolved_prepare_ownership_is_never_repaired_by_reads_or_restart(self):
        draft = self.plans.create('new'); key = self.key()
        owner = self.workspace / 'coord/ui-execution/mock-worker.json'
        owner.write_text(json.dumps(dict(schema_version=1,worker='mock-worker',phase='preparing',job_id=None,request_key=key)))
        raw = owner.read_bytes(); reopened = self.open()
        self.assertEqual(reopened.jobs(), [])
        self.error('outcome_unknown', reopened.prepare, draft['id'],draft['content_sha256'],key)
        self.assertEqual(owner.read_bytes(), raw)
        self.assertEqual(self.calls(), [])

    def test_hidden_flags_branch_and_base_drift_refused_before_verify(self):
        _, view, _, _ = self.started(); identity = view['job']['id']
        self.git(self.wt,'update-index','--assume-unchanged','source.txt')
        self.error('worker_unavailable', self.instance.verify, identity,self.key())
        self.git(self.wt,'update-index','--no-assume-unchanged','source.txt')
        self.git(self.wt,'checkout','-qb','wrong-branch')
        self.error('worker_unavailable', self.instance.verify, identity,self.key())
        self.git(self.wt,'checkout','-q','agent/mock-worker')
        (self.repo / 'source.txt').write_text('base advanced')
        self.git(self.repo,'add','source.txt'); self.git(self.repo,'commit','-qm','base drift')
        self.error('binding_stale', self.instance.verify, identity,self.key())
        self.assertEqual(self.calls('verify'), [])

    def test_stop_cannot_hide_engine_drift_on_read(self):
        _, view, _, _ = self.started(); identity = view['job']['id']
        (self.workspace / 'coord/STOP').write_text('stop')
        self.engine.write_text(self.engine.read_text() + '\n# changed')
        calls_before = len(self.calls('result')); got = self.instance.get(identity)
        self.assertIn('binding_stale', got['warnings']); self.assertIn('stopped', got['warnings'])
        self.assertEqual(len(self.calls('result')), calls_before)

    def test_accept_compares_the_full_revision_twice_before_recording(self):
        _, view, _, _ = self.reviewed(); identity = view['job']['id']; native = view['native_result']
        changed = copy.deepcopy(native); changed['current_revision']['worktree_sha256'] = 'f' * 64
        with patch.object(self.instance,'_native',side_effect=[(native,None),(changed,None)]):
            self.error('not_ready', self.instance.accept, identity,native['current_revision']['candidate_commit'],self.key())
        self.assertEqual(self.instance.get(identity)['acceptance']['state'], 'pending')

    def test_accept_refuses_readiness_and_all_revision_changes_between_fresh_reads(self):
        _, view, _, _ = self.reviewed(); identity = view['job']['id']; native = view['native_result']
        changes = [None, *sorted(service.REVISION_FIELDS)]
        for field in changes:
            latest = copy.deepcopy(native)
            if field is None:
                latest['ready_for_human_review'] = False
            else:
                latest['current_revision'][field] = ('f' if native['current_revision'][field][0] != 'f' else 'e') * len(
                    native['current_revision'][field])
            key = self.key()
            with self.subTest(field=field), patch.object(self.instance, '_native',
                    side_effect=[(native, None), (latest, None)]) as reads:
                self.error('not_ready', self.instance.accept, identity,
                           native['current_revision']['candidate_commit'], key)
                self.assertEqual(reads.call_count, 2)
            self.assertFalse((self.workspace / 'coord/ui-execution/actions' / (key + '.json')).exists())
        self.assertEqual(self.instance.get(identity)['acceptance']['state'], 'pending')

    def test_accept_rechecks_hidden_index_between_native_observations(self):
        _, view, _, _ = self.reviewed(); identity = view['job']['id']
        original = self.instance._native
        def observe(binding):
            result = original(binding)
            self.git(self.wt, 'update-index', '--skip-worktree', 'source.txt')
            return result
        key = self.key()
        with patch.object(self.instance, '_native', side_effect=observe) as reads:
            self.error('worker_unavailable', self.instance.accept, identity,
                       view['native_result']['current_revision']['candidate_commit'], key)
            self.assertEqual(reads.call_count, 1)
        self.assertFalse((self.workspace / 'coord/ui-execution/actions' / (key + '.json')).exists())
        self.git(self.wt, 'update-index', '--no-skip-worktree', 'source.txt')
        self.assertEqual(self.instance.get(identity)['acceptance']['state'], 'pending')

    def test_cancel_replay_does_not_release_a_new_job(self):
        _, old = self.prepared(); self.instance.cancel(old['job']['id'])
        draft, new = self.prepared(); self.instance.cancel(old['job']['id'])
        other = self.plans.create('other')
        self.error('worker_unavailable', self.instance.prepare, other['id'],other['content_sha256'],self.key())
        self.assertEqual(self.instance.get(new['job']['id'])['job']['state'], 'awaiting_owner_approval')

    def test_large_valid_template_and_request_use_bounded_immutable_companions(self):
        template = dict(schema_version=1,instructions='Implement.',
                        scope=['source-' + str(i) + '-' + 'x' * 620 for i in range(100)],
                        validate=['true #' + 'x' * 1994 for _ in range(30)])
        self.template.write_text(json.dumps(template))
        self.assertLess(self.template.stat().st_size, service.JSON_LIMIT)
        draft, view = self.prepared('\U0001f600' * 4000)
        self.assertGreater(self.binding_path(view).with_suffix('.md').stat().st_size, service.JSON_LIMIT)
        for path in (self.workspace / 'coord/ui-execution').rglob('*.json'):
            self.assertLessEqual(path.stat().st_size, service.JSON_LIMIT)
        self.assertEqual(self.open().get(view['job']['id'])['preview'], view['preview'])
        self.assertEqual(self.calls(), [])

    def unicode_template(self):
        # The lead's reproduced maximum: 15 commands of 2000 characters with
        # three-byte UTF-8 text. Escaped ASCII validate JSON exceeds the bound.
        template = dict(schema_version=1, instructions='I' * 12000, scope=['source.txt', 'docs/文档 ü.md'],
                        validate=[': ' + '字' * 1998] * 15)
        self.template.write_text(json.dumps(template, ensure_ascii=False))
        self.assertLess(self.template.stat().st_size, service.JSON_LIMIT)
        self.assertGreater(len(service._json_bytes(template['validate'])), service.JSON_LIMIT)
        return template

    def evidence(self):
        directory = self.workspace / 'coord/ui-execution'
        files = {str(path.relative_to(directory)): path.read_bytes()
                 for path in sorted(directory.rglob('*')) if path.is_file() and path.name != 'lock'}
        files.update({'tasks/' + path.name: path.read_bytes() for path in (self.workspace / 'coord/tasks').iterdir()})
        with JobStore(self.workspace) as store:
            return files, store.jobs()

    def test_maximum_unicode_commands_request_and_scope_publish_with_stable_hashes(self):
        template = self.unicode_template()
        instance = self.open()
        request = 'Ünïcode 字 request \U0001f600\n## Validate\n$ touch EVIL ## Allowed scope'
        draft = self.plans.create(request); key = self.key()
        view = instance.prepare(draft['id'], draft['content_sha256'], key)
        self.assertEqual(view['job']['state'], 'awaiting_owner_approval')
        self.assertEqual((view['preview']['request'], view['preview']['scope'], view['preview']['validate']),
                         (request, template['scope'], template['validate']))
        public = {k: v for k, v in view['preview'].items() if k != 'preview_hash'}
        self.assertEqual(view['preview']['preview_hash'], hashlib.sha256(json.dumps(public, sort_keys=True,
            ensure_ascii=True, separators=(',', ':')).encode()).hexdigest())
        task = self.binding_path(view).with_suffix('.md').read_bytes()
        self.assertEqual(hashlib.sha256(task).hexdigest(), view['preview']['task_sha256'])
        text = task.decode()
        self.assertEqual((text.count('\n## Allowed scope\n'), text.count('\n## Validate\n')), (1, 1))
        self.assertIn('\n' + json.dumps(request, ensure_ascii=True) + '\n', text)
        self.assertTrue(text.endswith('\n## Validate\n' + ''.join('$ ' + c + '\n' for c in template['validate'])))
        for path in (self.workspace / 'coord/ui-execution').rglob('*.json'):
            self.assertLessEqual(path.stat().st_size, service.JSON_LIMIT)
        self.assertEqual(json.loads(self.binding_path(view).with_suffix('.validate.json').read_bytes()),
                         template['validate'])
        self.assertEqual(json.loads((self.workspace / 'coord/ui-execution/mock-worker.json').read_text())['phase'], 'owned')
        # Replay, list, restart and approval all agree on the same canonical preview.
        self.assertEqual(instance.prepare(draft['id'], draft['content_sha256'], key), view)
        self.assertEqual(instance.jobs(), [view])
        instance.close()
        reopened = self.open()
        self.assertEqual(reopened.get(view['job']['id']), view)
        self.assertEqual(reopened.prepare(draft['id'], draft['content_sha256'], key), view)
        approved = reopened.approve(view['job']['id'], draft['content_sha256'], self.key(), view['preview']['preview_hash'])
        self.assertEqual(approved['job']['state'], 'approved')
        self.assertEqual(approved['preview'], view['preview'])
        self.assertEqual(self.calls(), [])
        self.assertFalse((self.wt / 'EVIL').exists())

    def test_maximum_ascii_commands_and_instructions_publish(self):
        self.template.write_text(json.dumps(dict(schema_version=1, instructions='I' * 12000,
                                                 scope=['source.txt'], validate=[': ' + 'x' * 1998] * 30)))
        self.instance = self.open()
        _, view = self.prepared()
        self.assertEqual(view['job']['state'], 'awaiting_owner_approval')
        self.assertEqual(self.open().get(view['job']['id']), view)
        self.assertEqual(self.calls(), [])

    def test_existing_escaped_companions_keep_their_hashes_on_read_and_replay(self):
        request = 'Café 字 \U0001f600'; key = self.key()
        draft, view = self.prepared(request, key)
        bindings = self.workspace / 'coord/ui-execution/bindings'
        for name, value in (('request', request), ('scope', ['source.txt']), ('validate', ["test -s 'source.txt'"])):
            # Records published before UTF-8 companions used escaped ASCII JSON.
            (bindings / (view['job']['id'] + '.' + name + '.json')).write_bytes(service._json_bytes(value))
        reopened = self.open()
        self.assertEqual(reopened.get(view['job']['id']), view)
        self.assertEqual(reopened.prepare(draft['id'], draft['content_sha256'], key), view)
        reopened.approve(view['job']['id'], draft['content_sha256'], self.key(), view['preview']['preview_hash'])
        self.assertEqual(self.calls(), [])

    def assert_refused_before_ownership(self, instance, patches, before):
        draft = self.plans.create('Does not fit.'); key = self.key()
        with patch.multiple(service, **patches):
            self.error('invalid_request', instance.prepare, draft['id'], draft['content_sha256'], key)
        self.assertEqual(self.evidence(), before)
        return draft, key

    def test_unfit_documents_are_refused_before_ownership_or_queue_changes(self):
        template = self.unicode_template()
        instance = self.open()
        validate = len(service._stored(template['validate']))
        empty = ({}, [])
        self.assertEqual(self.evidence(), empty)
        # Each bound is checked exactly: a companion one byte over, and the compiled task.
        self.assert_refused_before_ownership(instance, dict(JSON_LIMIT=validate - 1), empty)
        self.assert_refused_before_ownership(instance, dict(OUTPUT_LIMIT=12000), empty)
        self.assertFalse((self.workspace / 'coord/ui-execution/mock-worker.json').exists())
        # Nothing was orphaned: the same worker prepares at the exact bound afterwards.
        draft, key = self.assert_refused_before_ownership(instance, dict(JSON_LIMIT=validate - 1), empty)
        with patch.multiple(service, JSON_LIMIT=validate):
            view = instance.prepare(draft['id'], draft['content_sha256'], key)
        self.assertEqual(view['job']['state'], 'awaiting_owner_approval')
        self.assertEqual(self.open().get(view['job']['id']), view)
        self.assertEqual(self.calls(), [])

    def test_refusal_preserves_released_cancelled_and_accepted_evidence(self):
        _, old = self.prepared()
        cancelled = self.instance.cancel(old['job']['id'])
        before = self.evidence()
        self.assertEqual(json.loads(before[0]['mock-worker.json'])['phase'], 'released')
        self.assert_refused_before_ownership(self.instance, dict(JSON_LIMIT=200), before)
        self.assertEqual(self.instance.get(old['job']['id']), cancelled)
        self.assertEqual(self.open().get(old['job']['id']), cancelled)
        _, view, _, _ = self.reviewed(); identity = view['job']['id']
        self.instance.accept(identity, view['native_result']['current_revision']['candidate_commit'], self.key())
        # The owner integrates the accepted candidate, so the worker is clean at base again.
        self.git(self.repo, 'merge', '-q', '--ff-only', 'agent/mock-worker')
        before = self.evidence(); calls = self.calls(); accepted = self.instance.get(identity)
        self.assertEqual(json.loads(before[0]['mock-worker.json'])['job_id'], identity)
        self.assertEqual(json.loads(before[0]['mock-worker.json'])['phase'], 'released')
        self.assert_refused_before_ownership(self.instance, dict(JSON_LIMIT=300), before)
        self.assertEqual(self.calls(), calls)
        self.assertEqual(self.open().get(identity), accepted)

    def test_launch_receipt_storage_failure_marks_unknown_without_relaunch(self):
        _, view, approval = self.approved(); identity = view['job']['id']; key = self.key()
        write = self.instance._state_write
        failed = False
        def fail_receipt_once(state):
            nonlocal failed
            if state['execution']['state'] == 'launch_accepted' and not failed:
                failed = True
                raise OSError('PRIVATE receipt failure')
            return write(state)
        with patch.object(self.instance, '_state_write', side_effect=fail_receipt_once):
            self.error('outcome_unknown', self.instance.start, identity,approval,key)
        got = self.open().start(identity,approval,key)
        self.assertEqual(got['job']['state'], 'completion_unknown')
        self.assertEqual(got['execution']['launcher_exit'], 0)
        self.assertEqual(len(self.calls('run')), 1)

    def test_timeout_terminates_descendant_groups_in_its_own_session(self):
        script = ("import os,pathlib,subprocess,sys,time; "
                  "child=subprocess.Popen([sys.executable,'-c','import time; time.sleep(10)'],preexec_fn=os.setpgrp); "
                  "pathlib.Path('../descendant.pid').write_text(str(child.pid)); time.sleep(10)")
        started = time.monotonic()
        with self.assertRaises(service._NativeFailure):
            self.instance._call([sys.executable,'-c',script],1)
        self.assertLess(time.monotonic() - started, 3)
        identity = int((self.workspace / 'descendant.pid').read_text())
        path = Path('/proc') / str(identity) / 'stat'
        if path.exists():
            self.assertEqual(path.read_text().split(') ',1)[1].split()[0], 'Z')

    def test_another_workers_bound_job_is_not_exposed(self):
        worker = 'mock-two'
        self.git(self.repo,'worktree','add','-q','-b','agent/' + worker,str(self.workspace / 'wt' / worker))
        arguments = list(self.arguments); arguments[2] = worker
        other = self.open(arguments)
        draft = self.plans.create('other worker')
        view = other.prepare(draft['id'],draft['content_sha256'],self.key())
        self.error('job_not_found', self.instance.get, view['job']['id'])
        self.assertEqual(self.instance.jobs(), [])
        self.assertEqual(other.jobs()[0]['job']['id'], view['job']['id'])
        self.assertEqual(self.calls(), [])


def run_isolated_test(name):
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(ExecutionServiceTests(name))
    return name, result.testsRun, result.wasSuccessful(), stream.getvalue()


if __name__ == '__main__':
    if len(sys.argv) > 1:
        unittest.main(verbosity=2)
    else:
        # Every case owns its real Git and coordination fixture. Isolate cases
        # in processes to keep the full gate practical on the workspace drive;
        # native-action concurrency is still exercised inside its own cases.
        names = unittest.defaultTestLoader.getTestCaseNames(ExecutionServiceTests)
        started, count, failures = time.monotonic(), 0, 0
        with concurrent.futures.ProcessPoolExecutor(max_workers=4,
                mp_context=multiprocessing.get_context('fork')) as pool:
            pending = [pool.submit(run_isolated_test,name) for name in names]
            for future in concurrent.futures.as_completed(pending):
                name, ran, passed, output = future.result()
                count += ran
                failures += not passed
                print(name + (' ... ok' if passed else ' ... FAILED'), flush=True)
                if not passed:
                    print(output, flush=True)
        print('\nRan %d tests in %.3fs\n\n%s' % (count,time.monotonic() - started,
              'OK' if not failures else 'FAILED (cases=%d)' % failures), flush=True)
        sys.exit(bool(failures))
