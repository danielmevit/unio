#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Managed session CLI test suite: status, output reconnect, and steering."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]

FAKE_APP_SERVER = r'''#!/usr/bin/env python3
import json, os, select, signal, sys, time
from pathlib import Path
assert sys.argv[1:] == ['app-server', '--listen', 'stdio://']
receipt = Path(os.environ['FAKE_RECEIPT'])
with receipt.open('a') as f: f.write(json.dumps({'launch': os.getpid()})+'\n')
effort = 'low'
started = False
def emit(v): print(json.dumps(v), flush=True)
for line in sys.stdin:
    msg = json.loads(line)
    with receipt.open('a') as f: f.write(json.dumps(msg)+'\n')
    method = msg.get('method')
    if method == 'initialized': continue
    if method == 'initialize': result = {}
    elif method == 'account/read': result = {'account':{'type':os.environ.get('FAKE_AUTH','chatgpt')}}
    elif method == 'model/list': result = {'data':[{'id':os.environ.get('FAKE_MODEL','test-sol'),'model':os.environ.get('FAKE_MODEL','test-sol'),'supportedReasoningEfforts':[{'reasoningEffort':v} for v in ['low','high','xhigh','ultra']]}]}
    elif method == 'thread/start': result = {'thread':{'id':'private-thread','reasoningEffort':effort}}
    elif method == 'turn/start':
        assert not started
        started = True
        assert msg['params']['effort'] == 'low'
        assert 'NATIVE-TASK-SENTINEL' in msg['params']['input'][0]['text']
        Path('task-output.txt').write_text('useful edit\n')
        result = {'turn':{'id':'one-turn'}}
        emit({'id':msg['id'],'result':result})
        emit({'method':'item/agentMessage/delta','params':{'threadId':'private-thread','delta':'worker streamed useful output\n'}})
        mode = os.environ.get('FAKE_MODE','hold')
        if mode == 'exit': sys.exit(7)
        if mode == 'failed':
            emit({'method':'turn/completed','params':{'threadId':'private-thread','turn':{'id':'one-turn','status':'failed'}}})
        if mode == 'success':
            emit({'method':'turn/completed','params':{'threadId':'private-thread','turn':{'id':'one-turn','status':'completed'}}})
        continue
    elif method == 'thread/settings/update':
        effort = msg['params']['effort']
        emit({'method':'thread/settings/updated','params':{'threadId':'private-thread','threadSettings':{'effort':effort}}})
        result = {}
    elif method == 'thread/read': result = {'thread':{'reasoningEffort':effort}}
    elif method == 'turn/steer':
        assert set(msg['params']) == {'threadId', 'expectedTurnId', 'input'}
        assert msg['params']['threadId'] == 'private-thread'
        assert msg['params']['expectedTurnId'] == 'one-turn'
        steer_input = msg['params']['input'][0]['text']
        if os.environ.get('FAKE_REJECT_STEER'):
            emit({'id':msg['id'],'error':{'code':-32601,'message':'provider rejected steering'}})
            continue
        if os.environ.get('FAKE_TIMEOUT_STEER'): continue
        result = {'turnId':'wrong-turn' if os.environ.get('FAKE_WRONG_TURN') else 'one-turn'}
        emit({'id':msg['id'],'result':result})
        emit({'method':'item/agentMessage/delta','params':{'threadId':'private-thread','delta':f'steered: {steer_input}\n'}})
        continue
    else: raise AssertionError(method)
    emit({'id':msg['id'],'result':result})
'''


class SessionHarness:
    def __init__(self, directory):
        self.worker = 'mock'
        self.base = Path(directory)
        self.root = self.base / 'project'
        self.repo = self.root / 'repo'
        self.repo.mkdir(parents=True)
        self.receipt = self.base / 'rpc.jsonl'
        fake = self.base / 'fake-bin'
        fake.mkdir()
        (fake / 'codex').write_text(FAKE_APP_SERVER)
        (fake / 'codex').chmod(0o755)
        self.env = dict(os.environ, UNIO_BIN_DIR=str(self.base/'bin'), UNIO_CONF_DIR=str(self.base/'conf'),
            UNIO_COMPLETION_DIR=str(self.base/'completion'), UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0',
            UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='180', FAKE_RECEIPT=str(self.receipt),
            GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock', GIT_AUTHOR_EMAIL='mock@example.invalid',
            GIT_COMMITTER_EMAIL='mock@example.invalid', PATH=str(fake)+os.pathsep+os.environ['PATH'])
        for key in list(self.env):
            if key.startswith('UNIO_CODEX_'):
                self.env.pop(key)
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
            self.env.pop(key, None)
        subprocess.run(['bash', str(SOURCE/'unio-install.sh')], env=self.env, check=True, capture_output=True)
        self.unio = str(self.base / 'bin/unio')
        (self.base/'conf/agents.conf').write_text(
            'mock=python3 -I -S -B "$UNIO_CONF_DIR/lib/codex-worker.py" run --model test-sol --effort low\nlegacy=true\ncodex=true\n')
        for args in [('init','-q','-b','main'), ('config','user.name','mock'), ('config','user.email','mock@example.invalid')]:
            subprocess.run(['git', *args], cwd=self.repo, env=self.env, check=True, capture_output=True)
        (self.repo / 'seed').write_text('seed')
        for args in [('add', 'seed'), ('commit', '-qm', 'seed')]:
            subprocess.run(['git', *args], cwd=self.repo, env=self.env, check=True, capture_output=True)
        self.call('init', self.worker, 'legacy')
        self.call('account', self.worker, 'codex')
        self.call('account', 'legacy', 'codex')
        self.call('tier', 'medium')
        self.call('lead', 'codex')
        self.manifest = self.root / ('coord/.locks/codex-worker-' + self.worker + '.json')
        self.process = None
        self.task = 0

    def call(self, *args, code=0):
        result = subprocess.run([self.unio, *args], cwd=self.repo, env=self.env, capture_output=True, text=True, timeout=35)
        assert result.returncode == code, (args, result.returncode, result.stdout[-2500:], result.stderr[-2500:])
        return result

    def start(self, mode='hold', extra=None, timeout='180'):
        self.task += 1
        name = 'TASK-' + str(self.task)
        (self.root / 'coord/tasks' / (name + '.md')).write_text(
            '# Task\nNATIVE-TASK-SENTINEL\n## Allowed scope\n- task-output.txt\n## Validate\n$ test -f task-output.txt\n')
        self.call('lead-budget', 'grant', self.worker, self.worker, name, 'run')
        self.process = subprocess.Popen([self.unio, 'run', self.worker, name], cwd=self.repo,
            env=dict(self.env, FAKE_MODE=mode, UNIO_TIMEOUT=timeout, **(extra or {})),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if mode == 'hold':
            deadline = time.monotonic() + 12
            while not self.manifest.exists() and time.monotonic() < deadline and self.process.poll() is None:
                time.sleep(.05)
            assert self.manifest.exists(), self.process.communicate(timeout=5)
            # Wait for socket to be ready
            deadline = time.monotonic() + 5
            ready = False
            while time.monotonic() < deadline:
                try:
                    res = json.loads(self.call('session', 'status', self.worker, '--json').stdout)
                    if res.get('state') == 'active':
                        ready = True
                        break
                except Exception:
                    pass
                time.sleep(.05)
            assert ready, 'session status did not become active'
        return name

    def finish(self, code=None):
        out, err = self.process.communicate(timeout=25)
        if code is not None:
            assert self.process.returncode == code, (self.process.returncode, out[-3000:], err[-3000:])
        assert not self.manifest.exists(), 'owned manifest left behind'
        return out, err

    def terminate(self):
        self.process.send_signal(signal.SIGTERM)
        self.finish(143)

    def messages(self):
        if not self.receipt.exists():
            return []
        return [json.loads(line) for line in self.receipt.read_text().splitlines()]


def regressions():
    """Private fake transports and owned process fixtures; never call an AI."""
    import io
    import runpy
    import unittest
    from types import SimpleNamespace
    from unittest.mock import patch
    helper = Path(os.environ.get('MANAGED_HELPER_UNDER_TEST', SOURCE / 'tools/codex-worker.py'))
    m = runpy.run_path(str(helper))
    Server, Refusal = m['Server'], m['Refusal']
    g = Server.run.__globals__

    class Boundaries(unittest.TestCase):
        def setUp(self):
            for number in (signal.SIGTERM, signal.SIGINT):
                self.addCleanup(signal.signal, number, signal.getsignal(number))
            self.tmp = tempfile.TemporaryDirectory(prefix='session-boundary-')
            self.addCleanup(self.tmp.cleanup)
            self.root = Path(self.tmp.name)

        def server(self):
            s = Server(SimpleNamespace(effort='low', model='test-sol', binary='never-invoke'))
            s.doc = {'worker': 'mock', 'task': 'TASK-1', 'nonce': 'nonce'}
            s.session_id, s.turn, s.thread = 'sess-test', 'one-turn', 'thread'
            s.manifest_inode, s.manifest = (1, 2), self.root / 'manifest'
            s.output_fd = os.open(self.root / 'output', os.O_CREAT | os.O_WRONLY, 0o600)
            self.addCleanup(os.close, s.output_fd)
            return s

        def read(self, raw):
            p = self.root / 'transcript'
            p.write_bytes(raw)
            p.chmod(0o600)
            return m['read_session_output'](p)

        def rec(self, cursor):
            return json.dumps({'cursor': cursor, 'kind': 'lifecycle', 'data': {}}).encode() + b'\n'

        def test_corrupt_middle_is_not_skipped(self):
            records, _, _, truncated, gap = self.read(self.rec(1) + b'broken\n' + self.rec(3))
            self.assertTrue(gap and truncated)
            self.assertEqual([r['cursor'] for r in records], [1])

        def test_array_torn_tail_and_cursor_reversal(self):
            for tail in (b'[]\n', b'{"cursor":2', self.rec(1), self.rec(3)):
                with self.subTest(tail=tail):
                    records, _, _, truncated, gap = self.read(self.rec(1) + tail)
                    self.assertTrue(gap and truncated)
                    self.assertEqual(len(records), 1)

        def test_byte_bounds_and_unsupported_records(self):
            for tail in (b'x' * 65537 + b'\n', b'{"cursor":2,"kind":"unknown","data":{}}\n'):
                records, _, _, truncated, gap = self.read(self.rec(1) + tail)
                self.assertTrue(gap and truncated)
                self.assertEqual(len(records), 1)

        def test_page_and_total_archive_bytes_are_bounded(self):
            raw = b''.join((json.dumps({'cursor': n, 'kind': 'agent_message',
                'data': {'delta': 'x' * 50000}}) + '\n').encode() for n in range(1, 41))
            records, _, last, truncated, gap = self.read(raw)
            self.assertLess(sum(len(json.dumps(r)) for r in records), 1024 * 1024)
            self.assertEqual(last, 40)
            self.assertTrue(truncated)
            self.assertFalse(gap)
            # Once the page is full, a later small record must not skip an omitted one.
            records, _, _, truncated, gap = self.read(raw + self.rec(41))
            self.assertEqual([r['cursor'] for r in records], list(range(1, len(records) + 1)))
            p = self.root / 'transcript'
            with p.open('ab') as f: f.truncate(16 * 1024 * 1024 + 1)
            _, _, _, truncated, gap = m['read_session_output'](p)
            self.assertTrue(truncated and gap)

        def test_input_descriptor_refuses_replaced_symlink_and_fifo(self):
            self.archive('active')
            path = self.root / 'input'
            target = self.root / 'target'
            target.write_text('private'); target.chmod(0o600)
            original = os.open
            for kind in ('symlink', 'fifo'):
                path.write_text('hello'); path.chmod(0o600)
                def replace(name, flags, *args):
                    if Path(name) == path:
                        self.assertTrue(flags & os.O_NOFOLLOW)
                        self.assertTrue(flags & os.O_NONBLOCK)
                        path.unlink()
                        if kind == 'symlink': path.symlink_to(target)
                        else: os.mkfifo(path, 0o600)
                    return original(name, flags, *args)
                with patch.object(g['os'], 'open', side_effect=replace):
                    with self.assertRaises((Refusal, OSError)):
                        m['session_client'](self.args('send'))
                path.unlink()

        def test_recorder_cap_keeps_success(self):
            s = self.server()
            s.done = 0
            s.record_output('agent_message', {'delta': 'x' * 70000})
            self.assertLess(os.fstat(s.output_fd).st_size, 65536)
            self.assertEqual(s.done, 0)
            self.assertTrue(s.archive_limited)

        def test_all_group_signals_precede_reap(self):
            s = Server(SimpleNamespace(effort='low'))
            events = []
            s.child = SimpleNamespace(pid=123, wait=lambda **kw: events.append('reap'))
            with patch.object(g['signal'], 'signal'), patch.object(g['os'], 'killpg', side_effect=lambda *a: events.append(a[1])):
                s.close()
            self.assertEqual(events, [signal.SIGTERM, signal.SIGKILL, 'reap'])

        def test_leader_exits_first_cleanup_spares_detached_worker(self):
            s = Server(SimpleNamespace(effort='low'))
            code = "import subprocess; p=subprocess.Popen(['sleep','30'],stdout=subprocess.DEVNULL); print(p.pid,flush=True)"
            child = subprocess.Popen(['python3', '-c', code], stdout=subprocess.PIPE, start_new_session=True)
            descendant = int(child.stdout.readline())
            detached = subprocess.Popen(['sleep', '30'], start_new_session=True)
            s.child = child
            try:
                with self.assertRaises(Refusal): s.message(time.monotonic() + 3)
                s.close()
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    path = Path('/proc', str(descendant), 'stat')
                    if not path.exists() or path.read_text().rsplit(')', 1)[1].split()[0] == 'Z': break
                    time.sleep(.02)
                else: self.fail('owned descendant survived cleanup')
                self.assertIsNone(detached.poll(), 'detached native worker was signalled')
            finally:
                if child.returncode is None: s.close()
                child.stdout.close()
                detached.terminate(); detached.wait()

        def test_eof_does_not_reap(self):
            s = Server(SimpleNamespace(effort='low'))
            child = subprocess.Popen(['python3', '-c', 'raise SystemExit(7)'], stdout=subprocess.PIPE, start_new_session=True)
            s.child = child
            try:
                with self.assertRaises(Refusal):
                    s.message(time.monotonic() + 3)
                self.assertIsNone(child.returncode, 'EOF reaped the leader')
                self.assertEqual(s.done, 7)
            finally:
                s.close()
                child.stdout.close()

        def steer(self, s, text='hello', request_id='req'):
            class Conn:
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def settimeout(self, value): pass
                def recv(self, size):
                    return (json.dumps({'nonce': 'nonce', 'steer': {'request_id': request_id, 'text': text}}) + '\n').encode()
                def sendall(self, data): self.result = json.loads(data)
            c = Conn()
            s.listener = SimpleNamespace(accept=lambda: (c, None))
            with patch.dict(g, read_private=lambda path: (s.doc, s.manifest_inode), identity=lambda doc: None), patch('sys.stderr', io.StringIO()):
                s.control()
            return c.result

        def test_ack_then_archive_error_stays_accepted(self):
            s = self.server()
            calls = []
            s.rpc = lambda *args: calls.append(args) or {'turnId': s.turn}
            original = s.record_output
            def record(kind, data):
                if calls: raise OSError('disk unavailable after acknowledgement')
                original(kind, data)
            s.record_output = record
            self.assertEqual(self.steer(s)['state'], 'accepted')
            self.assertEqual(self.steer(s)['state'], 'accepted')
            self.assertEqual(len(calls), 1)
            self.assertEqual(self.steer(s, text='changed')['state'], 'rejected')

        def test_timeout_and_wrong_turn_are_uncertain_without_replay(self):
            for mode in ('timeout', 'wrong-turn'):
                s = self.server()
                calls = []
                def rpc(*args):
                    calls.append(args)
                    if mode == 'timeout': raise Refusal('provider RPC timeout')
                    return {'turnId': 'wrong-turn'}
                s.rpc = rpc
                self.assertEqual(self.steer(s)['state'], 'uncertain')
                self.assertEqual(self.steer(s)['state'], 'uncertain')
                self.assertEqual(self.steer(s, text='changed')['state'], 'rejected')
                self.assertEqual(len(calls), 1)

        def archive(self, state='completed'):
            d = self.root / 'coord/sessions'
            d.mkdir(parents=True)
            latest = {'session_id': 'sess-test', 'worker': 'mock', 'task': 'TASK-1',
                      'active': state == 'active', 'exit_code': 0 if state == 'completed' else None}
            meta = dict({k: latest[k] for k in ('session_id', 'worker', 'task')},
                        route='codex-app-server', model='test-sol', requested='low', configured=None, effective='Unknown',
                        state=state, exit_code=0 if state == 'completed' else None, output_cursor=0)
            for name, doc in [('latest-mock.json', latest), ('sess-test.json', meta)]:
                p = d / name
                p.write_text(json.dumps(doc)); p.chmod(0o600)
            return d, meta

        def args(self, action):
            return SimpleNamespace(project=str(self.root), worker='mock', session_action=action,
                                   after=0, limit=100, request_id='req', file=str(self.root / 'input'))

        def test_cross_worker_binding_refuses_all_commands(self):
            d, meta = self.archive()
            meta['worker'] = 'other'
            (d / 'sess-test.json').write_text(json.dumps(meta))
            for action in ('status', 'output', 'send'):
                with self.subTest(action=action), self.assertRaises(Refusal):
                    m['session_client'](self.args(action))

        def test_binding_replacement_between_archive_and_control_reads(self):
            _, meta = self.archive('active')
            path = self.root / 'input'
            path.write_text('hello'); path.chmod(0o600)
            manifest = self.root / 'coord/.locks/codex-worker-mock.json'
            manifest.parent.mkdir(parents=True)
            doc = dict(meta, project=str(self.root), pid=os.getpid(), pid_stamp='stamp')
            manifest.write_text(json.dumps(doc)); manifest.chmod(0o600)
            original = g['read_private']
            for action in ('status', 'send'):
                reads = []
                def replaced(path, *args):
                    value, inode = original(path, *args)
                    if Path(path) == manifest:
                        reads.append(1)
                        if len(reads) > 1: value['session_id'] = 'sess-replaced'
                    return value, inode
                def identity(doc):
                    self.fail('replaced binding reached native control validation')
                with patch.dict(g, read_private=replaced, identity=identity, process_stamp=lambda pid: 'stamp'):
                    if action == 'status':
                        self.assertEqual(m['session_client'](self.args(action))['state'], 'stale')
                    else:
                        with self.assertRaises(Refusal): m['session_client'](self.args(action))

        def test_unobserved_active_exit_stays_unknown(self):
            self.archive('active')
            result = m['session_client'](self.args('status'))
            self.assertEqual(result['state'], 'stale')
            self.assertIsNone(result['exit_code'])

        def test_terminal_not_overridden_by_live_cleanup(self):
            _, meta = self.archive()
            manifest = self.root / 'coord/.locks/codex-worker-mock.json'
            manifest.parent.mkdir(parents=True)
            manifest.write_text(json.dumps(dict(meta, project=str(self.root), pid=os.getpid(), pid_stamp='stamp')))
            manifest.chmod(0o600)
            with patch.dict(g, identity=lambda d: None, process_stamp=lambda pid: 'stamp'):
                self.assertEqual(m['session_client'](self.args('status'))['state'], 'completed')

        def test_refused_start_does_not_touch_history(self):
            d, _ = self.archive()
            before = {p.name: p.read_bytes() for p in d.iterdir()}
            slot = self.root / 'slot'
            slot.write_text('{}'); slot.chmod(0o600)
            env = dict(UNIO_CODEX_PROJECT=str(self.root), UNIO_CODEX_WORKER='mock', UNIO_CODEX_TASK='TASK-1',
                       UNIO_CODEX_SLOT=str(slot), UNIO_CODEX_HOLDER=str(os.getpid()), UNIO_CODEX_SUPERVISOR='0')
            s = Server(SimpleNamespace(effort='low', model='test-sol'))
            with patch.dict(os.environ, env), patch.dict(g, identity=lambda d: None):
                with self.assertRaises(Refusal): s.run()
                with patch.object(g['signal'], 'signal'): s.close()
            self.assertEqual(before, {p.name: p.read_bytes() for p in d.iterdir()})

    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Boundaries))
    if not result.wasSuccessful():
        raise AssertionError('managed boundary regressions failed')


def main():
    regressions()
    with tempfile.TemporaryDirectory(prefix='unio-session-test-') as directory:
        h = SessionHarness(directory)
        try:
            # 1. Pre-launch checks: unsupported routes and invalid arguments refuse with no provider launch
            res = json.loads(h.call('session', 'status', 'legacy', '--json', code=2).stdout)
            assert res['state'] == 'unsupported' and res['worker'] == 'legacy'
            res = json.loads(h.call('session', 'output', 'legacy', '--json', code=2).stdout)
            assert res['state'] == 'unsupported'
            h.call('session', 'status', 'nonexistent', '--json', code=2)
            h.call('session', 'status', 'bad/label', '--json', code=2)
            h.call('session', 'output', 'mock', '--after', '-1', '--json', code=2)
            h.call('session', 'output', 'mock', '--limit', '0', '--json', code=2)
            h.call('session', 'output', 'mock', '--limit', '501', '--json', code=2)
            dummy_file = h.base / 'dummy.txt'
            dummy_file.write_text('test')
            dummy_file.chmod(0o600)
            h.call('session', 'send', 'legacy', '--file', str(dummy_file), '--request-id', 'req1', '--json', code=2)
            h.call('session', 'send', 'mock', '--file', str(dummy_file), '--request-id', 'bad id spaces', '--json', code=2)
            h.call('session', 'send', 'mock', '--file', str(h.base / 'nonexistent'), '--request-id', 'req1', '--json', code=2)

            empty_file = h.base / 'empty.txt'
            empty_file.write_text('')
            empty_file.chmod(0o600)
            h.call('session', 'send', 'mock', '--file', str(empty_file), '--request-id', 'req1', '--json', code=2)

            large_file = h.base / 'large.txt'
            large_file.write_text('x' * 8193)
            large_file.chmod(0o600)
            h.call('session', 'send', 'mock', '--file', str(large_file), '--request-id', 'req1', '--json', code=2)

            symlink_file = h.base / 'symlink.txt'
            symlink_file.symlink_to(dummy_file)
            h.call('session', 'send', 'mock', '--file', str(symlink_file), '--request-id', 'req1', '--json', code=2)

            world_readable = h.base / 'world.txt'
            world_readable.write_text('content')
            world_readable.chmod(0o644)
            h.call('session', 'send', 'mock', '--file', str(world_readable), '--request-id', 'req1', '--json', code=2)

            invalid_utf8 = h.base / 'invalid-utf8.txt'
            invalid_utf8.write_bytes(b'\xff')
            invalid_utf8.chmod(0o600)
            h.call('session', 'send', 'mock', '--file', str(invalid_utf8), '--request-id', 'req1', '--json', code=2)

            # Before launch: sending to mock refuses
            h.call('session', 'send', 'mock', '--file', str(dummy_file), '--request-id', 'req1', '--json', code=2)
            assert len(h.messages()) == 0, 'pre-checks emitted provider calls'
            print('ok unsupported routes, invalid bounds, unsafe files refuse before launch', flush=True)

            # 2. Live managed run: status, active-turn steering, duplicate idempotency, output reconnect
            task_name = h.start('hold')
            status = json.loads(h.call('session', 'status', 'mock', '--json').stdout)
            assert status['state'] == 'active' and status['exit_code'] is None
            assert status['worker'] == 'mock' and status['task'] == task_name
            assert status['route'] == 'codex-app-server' and status['effective'] == 'Unknown'
            assert status['model'] == 'test-sol'
            session_id = status['session_id']
            assert session_id.startswith('sess-')
            assert status['output_cursor'] >= 1

            # Plain text status formatting
            status_text = h.call('session', 'status', 'mock').stdout
            assert f'session_id={session_id}' in status_text and 'state=active' in status_text

            # A second helper with the same live native slot must lose the exclusive claim
            # without altering any archive bytes or latest pointer.
            owned_doc = json.loads(h.manifest.read_text())
            archive = h.root / 'coord/sessions'
            snapshot = {p.name: p.read_bytes() for p in archive.iterdir()}
            duplicate_env = dict(h.env, UNIO_CODEX_PROJECT=str(h.root), UNIO_CODEX_WORKER='mock',
                UNIO_CODEX_TASK=task_name, UNIO_CODEX_SLOT=owned_doc['slot'],
                UNIO_CODEX_HOLDER=str(owned_doc['holder']), UNIO_CODEX_SUPERVISOR=str(os.getpid()),
                TASKFILE=str(h.root / 'coord/reports' / (task_name + '.prompt.md')))
            duplicate = subprocess.run(['python3', '-I', '-S', '-B', str(SOURCE / 'tools/codex-worker.py'),
                'run', '--model', 'test-sol', '--effort', 'low'], cwd=h.root / 'wt/mock',
                env=duplicate_env, capture_output=True, timeout=5)
            assert duplicate.returncode == 2, duplicate.stderr
            assert snapshot == {p.name: p.read_bytes() for p in archive.iterdir()}, 'duplicate changed owned history'
            assert len([m for m in h.messages() if 'launch' in m]) == 1
            print('ok duplicate native startup preserves existing archive bytes', flush=True)

            # Send valid steering text
            steer_file = h.base / 'steer1.txt'
            steer_file.write_text('focus on test validation first\n')
            steer_file.chmod(0o600)
            send_res = json.loads(h.call('session', 'send', 'mock', '--file', str(steer_file),
                                         '--request-id', 'steer-01', '--json').stdout)
            assert send_res['state'] == 'accepted'
            assert send_res['session_id'] == session_id
            assert send_res['request_id'] == 'steer-01'

            steer_msgs = [m for m in h.messages() if m.get('method') == 'turn/steer']
            assert len(steer_msgs) == 1
            assert steer_msgs[0]['params']['input'][0]['text'] == 'focus on test validation first\n'
            assert steer_msgs[0]['params']['expectedTurnId'] == 'one-turn'
            assert steer_msgs[0]['params']['threadId'] == 'private-thread'

            # Repeated identical steering request: returns recorded result without second provider RPC
            send_repeat = json.loads(h.call('session', 'send', 'mock', '--file', str(steer_file),
                                            '--request-id', 'steer-01', '--json').stdout)
            assert send_repeat['state'] == 'accepted'
            assert send_repeat['request_id'] == 'steer-01'
            assert len([m for m in h.messages() if m.get('method') == 'turn/steer']) == 1, 'repeated identical request triggered RPC'

            # Changed content for existing request-id refuses without provider call
            changed_file = h.base / 'changed.txt'
            changed_file.write_text('different content\n')
            changed_file.chmod(0o600)
            send_conflict = json.loads(h.call('session', 'send', 'mock', '--file', str(changed_file),
                                              '--request-id', 'steer-01', '--json', code=2).stdout)
            assert send_conflict['state'] == 'rejected'
            assert len([m for m in h.messages() if m.get('method') == 'turn/steer']) == 1, 'conflicting request triggered RPC'

            # Second distinct steering request
            steer2_file = h.base / 'steer2.txt'
            steer2_file.write_text('next steering message\n')
            steer2_file.chmod(0o600)
            send_res2 = json.loads(h.call('session', 'send', 'mock', '--file', str(steer2_file),
                                          '--request-id', 'steer-02', '--json').stdout)
            assert send_res2['state'] == 'accepted'
            assert len([m for m in h.messages() if m.get('method') == 'turn/steer']) == 2

            # Output retrieval
            out = json.loads(h.call('session', 'output', 'mock', '--json').stdout)
            assert out['session_id'] == session_id
            assert out['worker'] == 'mock'
            assert len(out['records']) >= 3
            assert out['truncated'] is False
            assert out['gap'] is False
            kinds = [r['kind'] for r in out['records']]
            assert 'lifecycle' in kinds and 'agent_message' in kinds and 'steer' in kinds

            # Output reconnect pagination
            p1 = json.loads(h.call('session', 'output', 'mock', '--after', '0', '--limit', '2', '--json').stdout)
            assert len(p1['records']) == 2
            assert p1['next_cursor'] == p1['records'][-1]['cursor']
            assert p1['truncated'] is True

            p2 = json.loads(h.call('session', 'output', 'mock', '--after', str(p1['next_cursor']), '--limit', '10', '--json').stdout)
            assert len(p2['records']) > 0
            assert p2['records'][0]['cursor'] > p1['next_cursor']

            # Gap reporting
            gap_out = json.loads(h.call('session', 'output', 'mock', '--after', '500', '--json').stdout)
            assert gap_out['gap'] is True
            assert len(gap_out['records']) == 0

            # Text format output
            text_out = h.call('session', 'output', 'mock').stdout
            assert f'session_id={session_id}' in text_out and 'output_cursor=' in text_out

            # Full 8 KiB UTF-8 and worst-case JSON escaping must fit the wire unchanged.
            for request_id, content in [('unicode-8k', 'é' * 4096), ('escaped-8k', '\x00' * 8192)]:
                steer_file.write_text(content)
                wide = json.loads(h.call('session', 'send', 'mock', '--file', str(steer_file),
                                         '--request-id', request_id, '--json').stdout)
                assert wide['state'] == 'accepted'
                last = [m for m in h.messages() if m.get('method') == 'turn/steer'][-1]
                assert last['params']['input'][0]['text'] == content
            print('ok full 8KiB UTF-8 and JSON-escaped input delivered unchanged', flush=True)

            h.terminate()
            print('ok live status, active-turn steering, duplicate idempotency, output reconnect', flush=True)

            # 3. Post-run historical inspection: survives termination and normal exit
            hist = json.loads(h.call('session', 'status', 'mock', '--json').stdout)
            assert hist['state'] == 'interrupted' and hist['exit_code'] == 143
            assert hist['session_id'] == session_id

            hist_out = json.loads(h.call('session', 'output', 'mock', '--json').stdout)
            assert hist_out['session_id'] == session_id
            last_record = hist_out['records'][-1]
            assert last_record['kind'] == 'lifecycle'
            assert last_record['data']['event'] == 'session_completed'
            assert last_record['data']['exit_code'] == 143

            # Completed source refuses new steering
            before_steer = len([m for m in h.messages() if m.get('method') == 'turn/steer'])
            h.call('session', 'send', 'mock', '--file', str(steer_file), '--request-id', 'steer-late', '--json', code=2)
            assert len([m for m in h.messages() if m.get('method') == 'turn/steer']) == before_steer

            # Observation works under STOP
            stop_file = h.root / 'coord/STOP'
            stop_file.touch()
            stop_hist = json.loads(h.call('session', 'status', 'mock', '--json').stdout)
            assert stop_hist['state'] == 'interrupted' and stop_hist['exit_code'] == 143
            stop_out = json.loads(h.call('session', 'output', 'mock', '--json').stdout)
            assert stop_out['session_id'] == session_id
            stop_file.unlink()
            print('ok historical inspection survives completion and works under STOP; late input refuses', flush=True)

            # 4. Normal success and failure exits preserved in session records
            h.start('success')
            h.finish(0)
            succ_status = json.loads(h.call('session', 'status', 'mock', '--json').stdout)
            assert succ_status['state'] == 'completed' and succ_status['exit_code'] == 0

            h.start('exit')
            h.finish(7)
            fail_status = json.loads(h.call('session', 'status', 'mock', '--json').stdout)
            assert fail_status['state'] == 'failed' and fail_status['exit_code'] == 7
            print('ok real success and failed exit statuses preserved in session records', flush=True)

            # 5. Failed transport steering: no silent replay of uncertain request
            h.start('hold', extra={'FAKE_REJECT_STEER': '1'})
            before = len([m for m in h.messages() if m.get('method') == 'turn/steer'])
            reject_file = h.base / 'reject.txt'
            reject_file.write_text('reject steer\n')
            reject_file.chmod(0o600)
            res = json.loads(h.call('session', 'send', 'mock', '--file', str(reject_file),
                                    '--request-id', 'steer-fail', '--json', code=2).stdout)
            assert res['state'] == 'rejected'
            assert len([m for m in h.messages() if m.get('method') == 'turn/steer']) == before + 1

            # Replaying the failed request ID must NOT send another provider RPC
            res2 = json.loads(h.call('session', 'send', 'mock', '--file', str(reject_file),
                                     '--request-id', 'steer-fail', '--json', code=2).stdout)
            assert res2['state'] == 'rejected'
            assert len([m for m in h.messages() if m.get('method') == 'turn/steer']) == before + 1, 'uncertain/failed request was replayed'
            h.terminate()
            print('ok failed steering transport is not silently replayed', flush=True)

            for extra in ({'FAKE_TIMEOUT_STEER': '1'}, {'FAKE_WRONG_TURN': '1'}):
                h.start('hold', extra=extra)
                before = len([m for m in h.messages() if m.get('method') == 'turn/steer'])
                for _ in range(2):
                    res = json.loads(h.call('session', 'send', 'mock', '--file', str(reject_file),
                        '--request-id', 'uncertain', '--json', code=2).stdout)
                    assert res['state'] == 'uncertain'
                assert len([m for m in h.messages() if m.get('method') == 'turn/steer']) == before + 1
                h.terminate()
            print('ok native timeout and mismatched acknowledgement stay uncertain without replay', flush=True)


        finally:
            if h.process is not None and h.process.poll() is None:
                h.process.terminate()
                h.process.communicate(timeout=25)


if __name__ == '__main__':
    main()
