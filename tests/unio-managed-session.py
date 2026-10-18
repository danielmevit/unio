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
        result = {'turnId':'one-turn'}
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


def main():
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

        finally:
            if h.process is not None and h.process.poll() is None:
                h.process.terminate()
                h.process.communicate(timeout=25)


if __name__ == '__main__':
    main()
