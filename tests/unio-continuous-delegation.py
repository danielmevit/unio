#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline bounded scheduler fixtures. No provider, adapter or quota probes."""
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import signal
import tempfile
import types
import sys
import time
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]

def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

BASE = module('dispatch_fixtures', ROOT / 'tests/unio-task-dispatch.py')
SCHED = module('schedule', ROOT / 'tools/continuous-delegation.py')
HELPER = ROOT / 'tools/continuous-delegation.py'


class CollectionOwnershipTests(unittest.TestCase):
    def test_group_signals_precede_only_reap(self):
        # EOF streams and a fake wait reproduce the original success-path
        # defect without ever sending a signal to a numeric real PID.
        for mode, code in (('exit', 0), ('exit', 7), ('exit', -signal.SIGTERM),
                           ('timeout', 0), ('overflow', 0)):
            with self.subTest(mode=mode, code=code):
                events = []
                pipes = []
                for _ in range(2):
                    read, write = os.pipe()
                    os.close(write)
                    pipes.append(os.fdopen(read, 'rb'))
                def reap(timeout):
                    events.append('reap')
                    return code
                process = types.SimpleNamespace(pid=12345, stdout=pipes[0],
                                                stderr=pipes[1], wait=reap)
                status = types.SimpleNamespace(
                    si_code=os.CLD_EXITED if code >= 0 else os.CLD_KILLED,
                    si_status=code if code >= 0 else -code)
                def observe(kind, pid, flags):
                    self.assertEqual((kind, pid), (os.P_PID, process.pid))
                    self.assertTrue(flags & os.WNOWAIT)
                    self.assertNotIn('reap', events)
                    events.append('observe')
                    return status
                def group_signal(pid, sig):
                    self.assertEqual(pid, process.pid)
                    self.assertNotIn('reap', events)
                    events.append(sig)
                real_read = os.read
                def read(descriptor, size):
                    return b'x' * (1024 * 1024 + 1) if mode == 'overflow' else real_read(descriptor, size)
                with mock.patch.object(os, 'waitid', side_effect=observe), mock.patch.object(
                        os, 'killpg', side_effect=group_signal), mock.patch.object(
                        os, 'read', side_effect=read):
                    expected = (code, b'') if mode == 'exit' else (None, None)
                    self.assertEqual(SCHED.collect(process, 0 if mode == 'timeout' else 1), expected)
                self.assertEqual(events.count('reap'), 1)
                self.assertLess(events.index(signal.SIGTERM), events.index(signal.SIGKILL))
                self.assertLess(events.index(signal.SIGKILL), events.index('reap'))
                self.assertTrue(all(pipe.closed for pipe in pipes))

    def collect_program(self, program, timeout=1):
        process = subprocess.Popen([sys.executable, '-c', program],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
        result = SCHED.collect(process, timeout)
        self.assertIsNotNone(process.returncode)
        self.assertTrue(process.stdout.closed and process.stderr.closed)
        return result

    def test_clean_exit_and_stderr_preserve_status_and_stdout(self):
        for code in (0, 9):
            with self.subTest(code=code):
                self.assertEqual(self.collect_program(
                    'import sys;print("result");print("diagnostic",file=sys.stderr);'
                    f'sys.exit({code})'), (code, b'result\n'))

    def test_eof_before_leader_exit_is_bounded(self):
        start = time.monotonic()
        self.assertEqual(self.collect_program(
            'import os,time;os.close(1);os.close(2);time.sleep(5)', .15), (None, None))
        self.assertLess(time.monotonic() - start, 2)

    def test_pipe_holding_descendant_and_output_bounds(self):
        for program in (
                'import os,time;p=os.fork();time.sleep(5) if p==0 else None',
                'import time;time.sleep(5)',
                'import sys;sys.stdout.write("x"*1100000)',
                'import sys;sys.stderr.write("x"*1100000)'):
            with self.subTest(program=program):
                start = time.monotonic()
                self.assertEqual(self.collect_program(program, .15), (None, None))
                self.assertLess(time.monotonic() - start, 2)

    def test_detached_worker_survives_observer_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            marker = Path(directory) / 'survived'
            gate = Path(directory) / 'observer-collected'
            worker = ('import pathlib,time;'
                      f'gate=pathlib.Path({str(gate)!r});end=time.monotonic()+3;'
                      '\nwhile not gate.exists() and time.monotonic()<end: time.sleep(.01)'
                      f'\nif gate.exists(): pathlib.Path({str(marker)!r}).write_text("done")')
            observer = ('import subprocess,sys;subprocess.Popen([sys.executable,"-c",'
                        f'{worker!r}],start_new_session=True,stdin=subprocess.DEVNULL,'
                        'stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);print("launched")')
            self.assertEqual(self.collect_program(observer), (0, b'launched\n'))
            gate.touch()
            deadline = time.monotonic() + 3
            while not marker.exists() and time.monotonic() < deadline:
                time.sleep(.02)
            self.assertEqual(marker.read_text(), 'done')


class SchedulerTests(unittest.TestCase):
    def setUp(self):
        self.fixture = BASE.TaskDispatchTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.f = self.fixture
        # A native launch returns immediately. Result stays unavailable until
        # the fixture explicitly exposes the corresponding completion receipt.
        engine = BASE.MOCK_ENGINE.replace("assert args[0] in ('run', 'result'),", """if args[0] == 'result' and not (root / ('done-' + args[1])).exists():
    sys.exit(1)
assert args[0] in ('run', 'result'),""")
        engine = engine.replace("if args[0] == 'run':\n    assert len(args)",
                                "if args[0] == 'run':\n    if (root / 'deny-consent').exists(): sys.exit(9)\n    assert len(args)")
        engine = engine.replace("    control = root / 'engine-control.json'", '''    import time
    sleeper = subprocess.Popen([sys.executable, '-c',
        'import pathlib,time,sys; root=pathlib.Path(sys.argv[1]); end=time.monotonic()+30; '
        + '\\nwhile root.exists() and not (root/sys.argv[2]).exists() and time.monotonic()<end: time.sleep(.05)',
        str(root), 'done-' + worker], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, start_new_session=True)
    with (root / 'fake-sessions').open('a') as sessions: sessions.write(str(sleeper.pid) + '\\n')
    control = root / 'engine-control.json' ''')
        self.f.engine.write_text(engine)
        self.jobs, self.rows = [], []
        self.add_job('dispatch-worker', 'a.txt')
        self.add_job('other-worker', 'b.txt')
        self.grant_path = self.batch_grant()
        self.runner = None
        self.addCleanup(self.release_sessions)

    def release_sessions(self):
        for path in (self.f.project / 'wt').iterdir():
            (self.f.project / ('done-' + path.name)).touch()
        time.sleep(0.1)

    def add_job(self, worker, scope):
        f = self.f
        original = f.worker, f.wt, f.template, f.grant
        f.worker = worker
        f.wt = f.project / 'wt' / worker
        if not f.wt.exists():
            BASE.git(f.repo, 'worktree', 'add', '-q', '-b', 'agent/' + worker, str(f.wt))
        f.template = f.project / ('template-' + worker + '.json')
        f.write_template((scope,))
        f.grant = f.write_grant()
        _, report, approval, _ = f.approved()
        self.rows.append(f.job_row(report))
        self.jobs.append(dict(job_id=report['job']['id'], grant=str(f.grant),
                             grant_sha256=hashlib.sha256(f.grant.read_bytes()).hexdigest(),
                             approval_key=approval, reservation_key=f.key()))
        f.worker, f.wt, f.template, f.grant = original

    def batch_grant(self, **changes):
        inv, sha = self.f.inventory(self.rows)
        value = dict(schema_version=1, project=str(self.f.project), inventory=str(inv),
                     inventory_sha256=sha, expires_at=(SCHED.now() + datetime.timedelta(hours=1)).isoformat(),
                     max_launches=128, poll_seconds=1, run_seconds=30, jobs=self.jobs)
        value.update(changes)
        path = self.f.root / ('batch-' + self.f.key() + '.json')
        path.write_text(json.dumps(value))
        return path

    def command(self, *args):
        env = dict(os.environ)
        env.pop('UNIO_CONF_DIR', None)
        return [sys.executable, '-B', str(HELPER), str(self.f.engine), '--project',
                str(self.f.project), '--json', *args], env

    def cli(self, *args, ok=True):
        command, env = self.command(*args)
        result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=90)
        if ok:
            self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def create(self, path=None):
        return self.cli('create', '--grant', str(path or self.grant_path))['id']

    def launches(self):
        return self.f.engine_calls('run')

    def status(self, ident):
        return self.cli('status', ident)

    def start_loop(self, ident):
        command, env = self.command('run', ident)
        self.runner = subprocess.Popen(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.cleanup_runner)
        return self.runner

    def cleanup_runner(self):
        if self.runner is not None:
            if self.runner.poll() is None:
                self.runner.terminate()
            self.runner.communicate(timeout=10)

    def wait_launch(self, count=1):
        deadline = time.monotonic() + 15
        while len(self.launches()) < count and time.monotonic() < deadline:
            time.sleep(0.05)
        self.assertEqual(len(self.launches()), count)

    def state_path(self, ident):
        return self.f.coord / 'schedules' / ident / 'state.json'

    def mutate_state(self, ident, update):
        path = self.state_path(ident)
        value = json.loads(path.read_text())
        update(value)
        path.write_text(json.dumps(value))

    def test_disjoint_groups_launch_before_completion_and_no_replay(self):
        ident = self.create()
        result = self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 2)
        sessions = (self.f.project / 'fake-sessions').read_text().splitlines()
        self.assertEqual(len(sessions), 2)
        self.assertTrue(all(Path('/proc/' + pid).exists() for pid in sessions))
        self.assertTrue(all(j['launcher'] == 'launch_accepted' and j['source'] == 'unknown' for j in result['jobs']))
        self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 2)
        self.assertEqual(self.status(ident)['attempts'], 2)

    def shared(self):
        data = json.loads((self.f.project / 'engine-data.json').read_text())
        data['policy --json']['accounts']['other'] = 'dispatch'
        (self.f.project / 'engine-data.json').write_text(json.dumps(data))

    def test_same_group_pending_starts_after_confirmed_completion(self):
        self.shared()
        ident = self.create()
        self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 1)
        self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 1)
        worker = self.launches()[0][2]
        (self.f.project / ('done-' + worker)).touch()
        result = self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 2)
        self.assertTrue(any(j['source'] == 'succeeded' and j['source_exit'] == 0 for j in result['jobs']))

    def test_pause_resume_stop_terminal(self):
        ident = self.create()
        self.cli('pause', ident)
        self.cli('run', ident, '--once')
        self.assertEqual(self.launches(), [])
        self.cli('resume', ident)
        self.cli('stop', ident)
        self.cli('run', ident, '--once')
        self.cli('resume', ident, ok=False)
        self.assertEqual(self.launches(), [])

    def test_controls_while_runner_active(self):
        self.shared()
        ident = self.create()
        runner = self.start_loop(ident)
        self.wait_launch()
        self.cli('pause', ident)
        self.assertEqual(self.status(ident)['control'], 'paused')
        runner.communicate(timeout=10)
        self.assertEqual(len(self.launches()), 1)
        self.assertEqual(self.status(ident)['control'], 'paused')

    def test_STOP_while_runner_active(self):
        self.shared()
        ident = self.create()
        runner = self.start_loop(ident)
        self.wait_launch()
        (self.f.coord / 'STOP').touch()
        runner.communicate(timeout=10)
        self.assertEqual(len(self.launches()), 1)

    def test_stop_while_runner_active(self):
        self.shared()
        ident = self.create()
        runner = self.start_loop(ident)
        self.wait_launch()
        self.cli('stop', ident)
        runner.communicate(timeout=10)
        self.assertEqual(self.status(ident)['control'], 'stopped')
        self.assertEqual(len(self.launches()), 1)

    def test_concurrent_runner_refuses(self):
        self.shared()
        ident = self.create()
        self.start_loop(ident)
        self.wait_launch()
        self.cli('run', ident, '--once', ok=False)
        self.cli('stop', ident)

    def test_crash_after_attempt_before_dispatch_never_replays(self):
        ident = self.create()
        def update(state):
            state['attempts'] = 1
            state['jobs'][self.jobs[0]['job_id']].update(attempted=True, launcher='unknown', group='dispatch')
        self.mutate_state(ident, update)
        self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 1)
        self.assertEqual(self.launches()[0][2], 'other-worker')
        self.assertEqual(self.status(ident)['attempts'], 2)

    def test_cross_batch_scope_and_group_claims(self):
        ident = self.create()
        # Distinct approved jobs in another batch, not present in the first inventory.
        self.jobs, self.rows = [], []
        self.add_job('other-next', 'a.txt')
        path = self.batch_grant()
        other = self.create(path)
        self.cli('run', ident, '--once')
        result = self.cli('run', other, '--once')
        self.assertEqual(result['attempts'], 0)
        self.assertEqual(len(self.launches()), 2)
        self.assertIn(result['jobs'][0]['reason'], ('scheduled_scope_held', 'scheduled_group_occupied'))

    def test_finite_launch_budget(self):
        ident = self.create(self.batch_grant(max_launches=1))
        self.cli('run', ident, '--once')
        self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 1)
        self.assertEqual(self.status(ident)['attempts'], 1)

    def test_expired_creation(self):
        self.cli('create', '--grant', str(self.batch_grant(expires_at=(SCHED.now()-datetime.timedelta(seconds=1)).isoformat())), ok=False)

    def test_grant_validation(self):
        for changes in ({'schema_version': True}, {'poll_seconds': True}, {'run_seconds': 7201},
                        {'max_launches': 0}, {'unknown': 1}, {'expires_at': '2026-10-16T12:00:00'},
                        {'jobs': [self.jobs[0], self.jobs[0]]}, {'inventory_sha256': '0'*64}):
            with self.subTest(changes=list(changes)):
                self.cli('create', '--grant', str(self.batch_grant(**changes)), ok=False)
        self.assertEqual(self.launches(), [])

    def test_duplicate_nan_nonutf8_oversized(self):
        for raw in (b'{"schema_version":1,"schema_version":1}', b'{"x":NaN}', b'\xff', b' '* (SCHED.MAX_GRANT+1)):
            with self.subTest(size=len(raw)):
                path = self.f.root / 'invalid.json'
                path.write_bytes(raw)
                self.cli('create', '--grant', str(path), ok=False)

    def test_link_special_inputs(self):
        link = self.f.root / 'link.json'
        link.symlink_to(self.grant_path)
        self.cli('create', '--grant', str(link), ok=False)
        fifo = self.f.root / 'fifo.json'
        os.mkfifo(fifo)
        self.cli('create', '--grant', str(fifo), ok=False)
        hard = self.f.root / 'hard.json'
        os.link(self.grant_path, hard)
        self.cli('create', '--grant', str(hard), ok=False)

    def test_missing_approval_and_scope_binding(self):
        bad = [dict(self.jobs[0], approval_key='0'*32)]
        self.cli('create', '--grant', str(self.batch_grant(jobs=bad)), ok=False)
        self.rows[0]['task_sha256'] = '0'*64
        self.cli('create', '--grant', str(self.batch_grant()), ok=False)

    def test_configuration_drift_refuses(self):
        ident = self.create()
        (self.f.config / 'agents.conf').write_text('changed=NEVER_REAL_PROVIDER\n')
        self.cli('run', ident, '--once', ok=False)
        self.assertEqual(self.launches(), [])

    def test_engine_drift_refuses(self):
        ident = self.create()
        with self.f.engine.open('a') as out:
            out.write('\n# drift\n')
        self.cli('run', ident, '--once', ok=False)
        self.assertEqual(self.launches(), [])

    def test_inventory_drift_refuses(self):
        ident = self.create()
        inv = Path(json.loads(self.grant_path.read_text())['inventory'])
        with inv.open('a') as out:
            out.write(' ')
        self.cli('run', ident, '--once', ok=False)
        self.assertEqual(self.launches(), [])

    def test_changed_base_refuses(self):
        ident = self.create()
        BASE.git(self.f.repo, 'commit', '-q', '--allow-empty', '-m', 'new base')
        self.cli('run', ident, '--once', ok=False)
        self.assertEqual(self.launches(), [])

    def test_corrupt_and_link_state(self):
        ident = self.create()
        path = self.state_path(ident)
        content = path.read_bytes()
        path.write_text('{')
        self.cli('status', ident, ok=False)
        path.unlink()
        target = self.f.root / 'saved-state'
        target.write_bytes(content)
        path.symlink_to(target)
        self.cli('status', ident, ok=False)

    def test_no_secrets_in_ordinary_output(self):
        ident = self.create()
        for args in (('status', ident), ('run', ident, '--once'), ('status',)):
            result = self.cli(*args)
            output = json.dumps(result)
            for job in self.jobs:
                self.assertNotIn(job['approval_key'], output)
                self.assertNotIn(job['reservation_key'], output)
            self.assertNotIn('Implement this.', output)

    def test_whole_observation_output_and_timeout_bounds(self):
        env = str(self.f.config)
        for program in ('import time;time.sleep(5)', 'import sys;sys.stdout.write("x"*1100000)',
                        'import os,time; p=os.fork();time.sleep(5) if p==0 else None'):
            with self.subTest(program=program):
                start = time.monotonic()
                process = SCHED.spawn([sys.executable, '-c', program], self.f.project, env)
                code, raw = SCHED.collect(process, 0.15)
                self.assertIsNone(raw)
                self.assertLess(time.monotonic()-start, 2)

    def inprocess(self, ident, replacement):
        planner = SCHED.load('task-plan')
        dispatch = SCHED.load('task-dispatch')
        store = SCHED.Store(str(self.f.project), planner)
        original = SCHED.spawn
        def controlled(argv, project, config):
            if any(str(arg).endswith('/task-dispatch.py') for arg in argv):
                return replacement(original, project, config)
            return original(argv, project, config)
        with mock.patch.object(SCHED, 'spawn', controlled), mock.patch.dict(
                os.environ, {'UNIO_CONF_DIR': str(self.f.config)}):
            SCHED.run(store, planner, dispatch, ident, str(self.f.engine), True)

    def test_launch_failure_consumes_without_replay(self):
        ident = self.create()
        self.inprocess(ident, lambda original, project, config:
                       original([sys.executable, '-c', 'import sys;sys.exit(1)'], project, config))
        self.assertEqual(self.status(ident)['attempts'], 2)
        self.cli('run', ident, '--once')
        self.assertEqual(self.launches(), [])

    def test_malformed_stdout_consumes_without_replay(self):
        programs = iter(('print("not JSON")', 'print(' + repr(json.dumps({'job': None})) + ')'))
        ident = self.create()
        self.inprocess(ident, lambda original, project, config:
                       original([sys.executable, '-c', next(programs)], project, config))
        result = self.status(ident)
        self.assertEqual(result['attempts'], 2)
        self.assertTrue(all(j['launcher'] == 'unknown' for j in result['jobs']))
        self.cli('run', ident, '--once')
        self.assertEqual(self.launches(), [])

    def test_actual_crash_boundary_after_durable_attempt(self):
        ident = self.create()
        def crash(original, project, config):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.inprocess(ident, crash)
        result = self.status(ident)
        self.assertEqual(result['attempts'], 1)
        self.assertEqual(self.launches(), [])
        self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 1)
        self.assertEqual(self.status(ident)['attempts'], 2)

    def test_missing_native_consent_keeps_consumed_attempt(self):
        # Native refusal is authoritative. Scheduling supplies no consent and
        # a refusal cannot manufacture a retry budget.
        (self.f.project / 'deny-consent').touch()
        ident = self.create()
        result = self.cli('run', ident, '--once')
        self.assertEqual(result['attempts'], 2)
        self.assertTrue(all(j['launcher'] == 'unknown' for j in result['jobs']))
        self.cli('run', ident, '--once')
        self.assertEqual(len(self.launches()), 2)

    def test_expiry_after_creation_and_run_duration(self):
        path = self.batch_grant(expires_at=(SCHED.now()+datetime.timedelta(seconds=60)).isoformat(),
                                run_seconds=1)
        ident = self.create(path)
        with mock.patch.object(SCHED, 'now', return_value=SCHED.now()+datetime.timedelta(seconds=120)):
            planner = SCHED.load('task-plan')
            SCHED.run(SCHED.Store(str(self.f.project), planner), planner, SCHED.load('task-dispatch'),
                      ident, str(self.f.engine), True)
        self.assertEqual(self.launches(), [])
        # A zero-readiness loop is bounded by the frozen one-second duration.
        data_path = self.f.project / 'engine-data.json'
        data = json.loads(data_path.read_text())
        data['policy --json']['active_with_lead'] = {'dispatch': 1, 'other': 1}
        data_path.write_text(json.dumps(data))
        start = time.monotonic()
        self.cli('run', ident)
        self.assertLess(time.monotonic()-start, 10)

    def test_account_route_drift(self):
        ident = self.create()
        self.shared()
        self.cli('run', ident, '--once', ok=False)
        # One matching-route job may launch before encountering the changed job.
        self.assertLessEqual(len(self.launches()), 1)

    def test_template_and_dispatch_grant_drift(self):
        ident = self.create()
        grant = Path(self.jobs[0]['grant'])
        with grant.open('a') as out:
            out.write(' ')
        self.cli('run', ident, '--once', ok=False)
        self.assertEqual(self.launches(), [])

    def test_template_drift_and_special_state_refuse(self):
        ident = self.create()
        single = json.loads(Path(self.jobs[0]['grant']).read_text())
        template = Path(single['template_path'])
        template.write_text(template.read_text() + ' ')
        self.cli('run', ident, '--once', ok=False)
        self.assertEqual(self.launches(), [])
        path = self.state_path(ident)
        content = path.read_bytes()
        path.unlink()
        os.mkfifo(path)
        self.cli('status', ident, ok=False)
        path.unlink()
        path.write_bytes(content)
        lock = path.parent / 'runner.lock'
        if lock.exists():
            lock.unlink()
        target = self.f.root / 'lock-target'
        target.touch()
        lock.symlink_to(target)
        self.cli('status', ident, ok=False)
        self.cli('run', ident, '--once', ok=False)

    def test_helper_identity_drift(self):
        ident = self.create()
        path = self.f.coord / 'schedules' / ident / 'frozen.json'
        frozen = json.loads(path.read_text())
        frozen['helpers'][str(HELPER)] = '0'*64
        path.write_text(json.dumps(frozen))
        self.mutate_state(ident, lambda state: state.update(frozen_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        self.cli('run', ident, '--once', ok=False)
        self.assertEqual(self.launches(), [])


class SchedulerPackagingTests(unittest.TestCase):
    def test_installed_payload_help_completions_and_standalone_thin_refusal(self):
        install = module('dispatch_install_fixtures', ROOT / 'tests/unio-task-dispatch-install.py')
        fixture = install.DispatchInstallCase()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        binary, config, completion = (fixture.base / name for name in ('bin', 'conf', 'completion'))
        fixture.run_install(binary, config, completion)
        engine = binary / 'unio'
        self.assertEqual((config / 'lib/continuous-delegation.py').read_bytes(), HELPER.read_bytes())
        installed = module('installed_schedule', config / 'lib/continuous-delegation.py')
        pinned = installed.helpers(installed.load('task-plan'))
        self.assertIn(str(config / 'lib/browser/execution_service.py'), pinned)
        for arguments in (['schedule', '--help'], ['schedule', 'run', '--help'], ['help']):
            result = subprocess.run([str(engine), *arguments], cwd=fixture.base, env=fixture.env,
                                    capture_output=True, text=True, timeout=15)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('schedule' if arguments == ['help'] else 'unio schedule', result.stdout)
        self.assertIn('schedule', (completion / 'unio').read_text())
        source = (ROOT / 'unio-install.sh').read_text()
        text = source.split("cat > \"$BIN_DIR/unio\" <<'UNIO_BIN_EOF'\n", 1)[1].split('\nUNIO_BIN_EOF\n', 1)[0] + '\n'
        standalone = fixture.base / 'standalone engine'
        standalone.write_text(text)
        standalone.chmod(0o700)
        thin = fixture.base / 'thin configuration'
        thin.mkdir()
        (thin / 'agents.conf').write_text('mock=NEVER_REAL_PROVIDER\n')
        env = dict(fixture.env, UNIO_CONF_DIR=str(thin))
        for executable in (engine, standalone):
            result = subprocess.run([str(executable), 'schedule', '--help'], cwd=fixture.base,
                                    env=env, capture_output=True, text=True, timeout=15)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('schedule payload missing', result.stderr)
        (config / 'lib/continuous-delegation.py').unlink()
        result = subprocess.run([str(engine), 'schedule', '--help'], cwd=fixture.base,
                                env=fixture.env, capture_output=True, text=True, timeout=15)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('schedule payload missing', result.stderr)


if __name__ == '__main__':
    unittest.main()
