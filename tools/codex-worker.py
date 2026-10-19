#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Owned native Codex app-server Source and bounded local effort client."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import struct
import subprocess
import sys
import tempfile
import time
import uuid

LEVELS = ('low', 'medium', 'high', 'xhigh')
BOUND = 16384
MAX_STEER_TEXT = 8192
WIRE_BOUND = 65536
ARCHIVE_BOUND = 16 * 1024 * 1024
RECORD_BOUND = 65536
PAGE_BOUND = 1024 * 1024
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')

class Refusal(Exception):
    pass


class RPCRejected(Refusal):
    pass


class Cancelled(Exception):
    pass


def safe_path(path):
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise Refusal('unsafe path')
    return path


def read_private(path, private=True):
    safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_uid != os.getuid()
                or st.st_size > BOUND or (private and st.st_mode & 0o077)):
            raise Refusal('unsafe metadata')
        data = os.read(fd, BOUND + 1)
        if len(data) > BOUND:
            raise Refusal('metadata bound exceeded')
        doc = json.loads(data)
        if not isinstance(doc, dict):
            raise Refusal('invalid metadata shape')
        return doc, (st.st_dev, st.st_ino)
    finally:
        os.close(fd)


def sessions_dir(root):
    path = safe_path(Path(root) / 'coord/sessions')
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path


def read_session_output(path, after=0, limit=100):
    safe_path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid() or st.st_mode & 0o077):
            raise Refusal('unsafe output file')
        records, last, size, page = [], 0, 0, 0
        gap, truncated = False, st.st_size > ARCHIVE_BOUND
        page_full = False
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            while size < ARCHIVE_BOUND:
                line = stream.readline(min(RECORD_BOUND + 1, ARCHIVE_BOUND - size))
                if not line:
                    break
                size += len(line)
                # Stop at the first unknown byte range. Never skip corruption.
                if len(line) > RECORD_BOUND or not line.endswith(b'\n'):
                    gap = truncated = True
                    break
                try:
                    rec = json.loads(line)
                    cur = rec.get('cursor') if isinstance(rec, dict) else None
                    if (type(cur) is not int or cur != last + 1
                            or rec.get('kind') not in ('agent_message', 'command_output', 'lifecycle', 'steer', 'archive_limit')
                            or not isinstance(rec.get('data'), dict)
                            or (rec['kind'] in ('agent_message', 'command_output')
                                and not isinstance(rec['data'].get('delta'), str))):
                        raise ValueError('unsupported or unordered record')
                except (ValueError, UnicodeError, RecursionError):
                    gap = truncated = True
                    break
                last = cur
                if rec['kind'] == 'archive_limit':
                    gap = truncated = True
                if cur > after:
                    if not page_full and len(records) < limit and page + len(line) <= PAGE_BOUND:
                        records.append(rec)
                        page += len(line)
                    else:
                        page_full = truncated = True
        gap |= after > last
        return records, records[-1]['cursor'] if records else after, last, truncated, gap
    finally:
        if fd is not None:
            os.close(fd)


def process_stamp(pid):
    return Path('/proc', str(pid), 'stat').read_text().rsplit(')', 1)[1].split()[19]


def identity(doc):
    root = safe_path(doc['project'])
    for key in ('worker', 'task'):
        if not isinstance(doc[key], str) or not LABEL.fullmatch(doc[key]):
            raise Refusal('invalid native label')
    slot = safe_path(doc['slot'])
    if slot.parent.parent != root / 'coord/.locks/work-policy-slots':
        raise Refusal('slot outside native admission')
    meta, inode = read_private(slot)
    if list(inode) != doc['slot_inode'] or any(meta.get(k) != doc[k] for k in ('worker', 'task')) or meta.get('kind') != 'run':
        raise Refusal('stale native slot')
    holder = doc['holder']
    if process_stamp(holder) != doc['holder_stamp']:
        raise Refusal('stale admission holder')
    owned = False
    for path in Path('/proc', str(holder), 'fd').iterdir():
        try:
            st = path.stat()
            owned |= (st.st_dev, st.st_ino) == inode
        except OSError:
            pass
    if not owned:
        raise Refusal('holder does not own slot')
    fd = os.open(slot, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        raise Refusal('native slot is not locked')
    finally:
        os.close(fd)


def endpoint(root, worker):
    if not LABEL.fullmatch(worker):
        raise Refusal('invalid worker')
    return safe_path(Path(root) / 'coord/.locks' / ('codex-worker-' + worker + '.json'))


class Server:
    def __init__(self, args):
        self.args = args
        self.child = None
        self.listener = None
        self.directory = None
        self.manifest = None
        self.manifest_inode = None
        self.buffer = b''
        self.counter = 0
        self.done = None
        self.thread = None
        self.turn = None
        self.requested = args.effort
        self.configured = None
        self.pending = False
        self.supported = []
        self.stop_code = None
        self.doc = None
        self.session_id = None
        self.sessions_directory = None
        self.output_fd = None
        self.output_cursor = 0
        self.steer_history = {}
        self.output_bytes = 0
        self.archive_limited = False

    def stop(self, number, frame):
        # Native supervision and timeout can both forward cancellation. A
        # second exception while unwinding can interrupt entry into close().
        if self.stop_code is not None:
            return
        self.stop_code = 128 + number
        raise Cancelled('interrupted')

    def send(self, data):
        self.child.stdin.write((json.dumps(data) + '\n').encode())
        self.child.stdin.flush()

    def write_meta(self, state=None, exit_code=None):
        if not self.sessions_directory or not self.session_id or not self.doc:
            return
        if state is None:
            state = 'active' if self.done is None else ('completed' if self.done == 0 else ('interrupted' if self.done in (130, 143) else 'failed'))
        if exit_code is None:
            exit_code = self.done
        meta = {
            'session_id': self.session_id,
            'worker': self.doc['worker'],
            'task': self.doc['task'],
            'route': 'codex-app-server',
            'model': self.args.model,
            'requested': self.requested,
            'configured': self.configured,
            'effective': 'Unknown',
            'state': state,
            'exit_code': exit_code,
            'output_cursor': self.output_cursor
        }
        tmp_meta = self.sessions_directory / f".tmp-{self.session_id}.json"
        fd = os.open(tmp_meta, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(meta, f)
        tmp_meta.replace(self.sessions_directory / f"{self.session_id}.json")

        latest = {
            'session_id': self.session_id,
            'worker': self.doc['worker'],
            'task': self.doc['task'],
            'active': (state == 'active'),
            'exit_code': exit_code
        }
        tmp_latest = self.sessions_directory / f".tmp-latest-{self.doc['worker']}.json"
        fd = os.open(tmp_latest, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(latest, f)
        tmp_latest.replace(self.sessions_directory / f"latest-{self.doc['worker']}.json")

    def record_output(self, kind, data):
        if self.output_fd is None:
            return
        if self.archive_limited:
            return
        rec = {'cursor': self.output_cursor + 1, 'kind': kind, 'data': data,
               'timestamp': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}
        line = (json.dumps(rec, ensure_ascii=False) + '\n').encode('utf-8')
        if len(line) > RECORD_BOUND or self.output_bytes + len(line) > ARCHIVE_BOUND - 1024:
            self.archive_limited = True
            rec['kind'], rec['data'] = 'archive_limit', {'history': 'truncated; subsequent output Unknown'}
            line = (json.dumps(rec) + '\n').encode()
        # A recorder failure must not change the provider's observed outcome.
        try:
            view = memoryview(line)
            while view:
                written = os.write(self.output_fd, view)
                if not written:
                    raise OSError('short archive write')
                view = view[written:]
            self.output_cursor += 1
            self.output_bytes += len(line)
            self.write_meta()
        except OSError:
            self.archive_limited = True

    def event(self, msg):
        method, p = msg.get('method'), msg.get('params', {})
        if 'id' in msg and method:
            # Noninteractive Source never auto-approves requests from provider.
            self.send({'id': msg['id'], 'error': {'code': -32601, 'message': 'Noninteractive Source request unsupported'}})
        if p.get('threadId') != self.thread:
            return
        if method == 'thread/settings/updated':
            effort = p.get('threadSettings', {}).get('effort')
            if effort in LEVELS:
                self.configured = effort
                self.write_meta()
        if method in ('item/agentMessage/delta', 'item/commandExecution/outputDelta'):
            delta = p.get('delta')
            if isinstance(delta, str):
                print(delta, end='', flush=True)
                kind = 'agent_message' if method == 'item/agentMessage/delta' else 'command_output'
                self.record_output(kind, {'delta': delta})
        if method == 'turn/completed':
            turn = p.get('turn', {})
            if self.turn is None or turn.get('id') == self.turn:
                self.done = {'completed': 0, 'failed': 1, 'interrupted': 130}.get(turn.get('status'), 1)
                self.record_output('lifecycle', {'event': 'turn_completed', 'status': turn.get('status')})

    def message(self, deadline):
        while b'\n' not in self.buffer:
            if time.monotonic() >= deadline:
                raise Refusal('provider RPC timeout')
            ready, _, _ = select.select([self.child.stdout], [], [], min(.2, max(0, deadline-time.monotonic())))
            if not ready:
                continue
            data = os.read(self.child.stdout.fileno(), 65536)
            if not data:
                exit_deadline = min(deadline, time.monotonic() + .2)
                while True:
                    info = os.waitid(os.P_PID, self.child.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
                    if info is not None or time.monotonic() >= exit_deadline:
                        break
                    time.sleep(.01)
                code = (info.si_status if info.si_code == os.CLD_EXITED else -info.si_status) if info else 2
                self.done = code if code > 0 else (128-code if code < 0 else 1)
                raise Refusal('provider exited')
            self.buffer += data
            if len(self.buffer) > 2 * 1024 * 1024:
                raise Refusal('provider message bound exceeded')
        line, self.buffer = self.buffer.split(b'\n', 1)
        msg = json.loads(line)
        if (not isinstance(msg, dict)
                or ('method' in msg and (not isinstance(msg['method'], str)
                                        or not isinstance(msg.get('params', {}), dict)))):
            raise Refusal('invalid provider message')
        return msg

    def rpc(self, method, params):
        self.counter += 1
        request_id = self.counter
        self.send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + 8
        while True:
            msg = self.message(deadline)
            if msg.get('id') == request_id and 'method' not in msg:
                if 'error' in msg:
                    raise RPCRejected('provider rejected RPC')
                return msg.get('result', {})
            self.event(msg)

    def view(self, state='observed'):
        return {'worker': self.doc['worker'], 'task': self.doc['task'],
                'route': 'codex-app-server', 'model': self.args.model,
                'requested': self.requested, 'configured': self.configured,
                'pending_next_turn': self.pending, 'effective': 'Unknown',
                'supported': self.supported, 'state': state}

    def control(self):
        conn, _ = self.listener.accept()
        with conn:
            conn.settimeout(2)
            is_steer = False
            steer_req_id = None
            try:
                data = b''
                while b'\n' not in data:
                    chunk = conn.recv(WIRE_BOUND + 1 - len(data))
                    if not chunk or len(data) + len(chunk) > WIRE_BOUND:
                        raise Refusal('invalid request bounds')
                    data += chunk
                if data.count(b'\n') != 1 or not data.endswith(b'\n'):
                    raise Refusal('invalid request framing')
                req = json.loads(data)
                if not isinstance(req, dict) or set(req) not in ({'nonce'}, {'nonce', 'effort'}, {'nonce', 'steer'}):
                    raise Refusal('forbidden settings')
                current, inode = read_private(self.manifest)
                if current != self.doc or inode != self.manifest_inode or req['nonce'] != self.doc['nonce']:
                    raise Refusal('stale or replaced channel')
                identity(self.doc)
                if 'steer' in req:
                    is_steer = True
                    steer = req['steer']
                    if not isinstance(steer, dict) or set(steer) != {'request_id', 'text'}:
                        raise Refusal('invalid steer parameters')
                    steer_req_id = steer['request_id']
                    if not isinstance(steer_req_id, str) or not LABEL.fullmatch(steer_req_id):
                        raise Refusal('invalid request id')
                    text = steer['text']
                    if not isinstance(text, str) or not text or len(text.encode('utf-8')) > MAX_STEER_TEXT:
                        raise Refusal('invalid steer text')
                    text_sha = hashlib.sha256(text.encode('utf-8')).hexdigest()
                    if steer_req_id in self.steer_history:
                        prev = self.steer_history[steer_req_id]
                        if prev['sha256'] != text_sha:
                            raise Refusal('changed content for request id')
                        result = prev['result']
                    else:
                        if self.turn is None or self.done is not None:
                            raise Refusal('turn already finished')
                        result = {'session_id': self.session_id, 'worker': self.doc['worker'],
                                  'task': self.doc['task'], 'request_id': steer_req_id, 'state': 'uncertain'}
                        self.steer_history[steer_req_id] = {'sha256': text_sha, 'result': result}
                        # Cache before any effect; refuse if bounded history cannot store intent.
                        if self.archive_limited:
                            result['state'] = 'rejected'
                            raise Refusal('steering history unavailable')
                        try:
                            self.record_output('steer', {'request_id': steer_req_id, 'sha256': text_sha, 'state': 'intent'})
                            if self.archive_limited:
                                raise Refusal('steering history unavailable')
                            os.fsync(self.output_fd)
                        except (Refusal, OSError):
                            result['state'] = 'rejected'
                            raise
                        try:
                            ack = self.rpc('turn/steer', {
                                'threadId': self.thread, 'expectedTurnId': self.turn,
                                'input': [{'type': 'text', 'text': text}]
                            })
                            if not isinstance(ack, dict) or ack.get('turnId') != self.turn:
                                raise Refusal('unverified steering acknowledgement')
                        except RPCRejected:
                            result['state'] = 'rejected'
                        except (Refusal, OSError, ValueError, TypeError, KeyError):
                            pass  # Delivery may have occurred; never replay this ID.
                        else:
                            result['state'] = 'accepted'
                        try:
                            self.record_output('steer', {'request_id': steer_req_id, 'state': result['state']})
                        except OSError:
                            pass  # An acknowledged delivery stays acknowledged.

                else:
                    state = 'observed'
                    if 'effort' in req:
                        effort = req['effort']
                        if effort not in self.supported:
                            raise Refusal('unsupported effort')
                        if self.done is not None:
                            raise Refusal('turn already finished')
                        self.requested = effort
                        self.rpc('thread/settings/update', {'threadId': self.thread, 'effort': effort})
                        self.pending = True
                        # Empty response is only RPC success; readback establishes configuration.
                        state = 'unverified'
                    try:
                        thread = self.rpc('thread/read', {'threadId': self.thread, 'includeTurns': False}).get('thread', {})
                        if thread.get('reasoningEffort') in LEVELS:
                            self.configured = thread['reasoningEffort']
                            self.write_meta()
                    except Refusal:
                        if self.done is not None:
                            raise
                    if 'effort' in req and self.configured == req['effort']:
                        state = 'acknowledged'
                    result = self.view(state)
            except (Refusal, OSError, ValueError, KeyError, TypeError, RecursionError):
                if is_steer:
                    result = {
                        'session_id': self.session_id if self.session_id else 'unknown',
                        'worker': self.doc['worker'] if self.doc else 'unknown',
                        'task': self.doc['task'] if self.doc else 'unknown',
                        'request_id': steer_req_id if steer_req_id else 'unknown',
                        'state': 'rejected'
                    }
                else:
                    result = self.view('rejected')
            if is_steer:
                receipt = dict(result, recorded_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
                print('unio session receipt: ' + json.dumps(receipt), file=sys.stderr, flush=True)
            else:
                receipt = dict(result, recorded_at=time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                               cli='Codex app-server', cli_version='Unknown', effective_model='Unknown')
                print('unio worker-effort receipt: ' + json.dumps(receipt), file=sys.stderr, flush=True)
            try:
                conn.sendall((json.dumps(result) + '\n').encode())
            except OSError:
                pass  # Client disappearance cannot cancel the assigned provider turn.

    def run(self):
        env = os.environ
        root, worker, task, slot, holder = [env.get('UNIO_CODEX_' + k) for k in ('PROJECT', 'WORKER', 'TASK', 'SLOT', 'HOLDER')]
        if not all((root, worker, task, slot, holder)):
            raise Refusal('managed native run required')
        _, inode = read_private(slot)
        self.doc = {'project': root, 'worker': worker, 'task': task, 'slot': slot,
                    'slot_inode': list(inode), 'holder': int(holder), 'holder_stamp': process_stamp(int(holder)),
                    'pid': os.getpid(), 'pid_stamp': process_stamp(os.getpid()), 'nonce': uuid.uuid4().hex}
        identity(self.doc)
        self.session_id = f"sess-{uuid.uuid4().hex[:16]}"
        self.doc['session_id'] = self.session_id
        supervisor = int(env.get('UNIO_CODEX_SUPERVISOR', '0'))
        ancestor = os.getppid()
        while ancestor > 1 and ancestor != supervisor:
            ancestor = int(Path('/proc', str(ancestor), 'stat').read_text().rsplit(')', 1)[1].split()[1])
        if supervisor <= 1 or ancestor != supervisor or Path.cwd() != Path(root) / 'wt' / worker:
            raise Refusal('not owned by native Source supervisor')
        prompt_path = safe_path(env['TASKFILE'])
        if prompt_path != Path(root) / 'coord/reports' / (task + '.prompt.md'):
            raise Refusal('task binding mismatch')
        prompt_fd = os.open(prompt_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(prompt_fd, 'rb') as f:
            st = os.fstat(f.fileno())
            if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid() or st.st_nlink != 1:
                raise Refusal('unsafe task file')
            prompt = f.read(2 * 1024 * 1024 + 1)
        if len(prompt) > 2 * 1024 * 1024:
            raise Refusal('task too large')
        if env.get('OPENAI_API_KEY') or env.get('CODEX_API_KEY'):
            raise Refusal('subscription Source refuses API-key environment')
        # Explicitly retain child zombies even if the launcher ignored SIGCHLD.
        signal.signal(signal.SIGCHLD, signal.SIG_DFL)
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.directory = Path(tempfile.mkdtemp(prefix='unio-codex-'))
        self.listener = socket.socket(socket.AF_UNIX)
        socket_path = self.directory / 'control.sock'
        directory_fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            # Resolve through our own directory fd to honor even a long TMPDIR.
            self.listener.bind(f'/proc/self/fd/{directory_fd}/control.sock')
        finally:
            os.close(directory_fd)
        os.chmod(socket_path, 0o600)
        self.listener.listen(4)
        self.doc['socket'] = str(socket_path)
        self.manifest = endpoint(root, worker)
        fd = os.open(self.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.doc, f)
        _, self.manifest_inode = read_private(self.manifest)
        self.sessions_directory = sessions_dir(root)
        self.output_file = self.sessions_directory / f"{self.session_id}.output.jsonl"
        self.output_fd = os.open(self.output_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        self.doc['session_id'] = self.session_id
        self.write_meta('active')
        self.child = subprocess.Popen([self.args.binary, 'app-server', '--listen', 'stdio://'],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      start_new_session=True)
        self.rpc('initialize', {'clientInfo': {'name': 'unio-managed-source', 'version': '1'},
                                'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized', 'params': {}})
        account = self.rpc('account/read', {'refreshToken': False}).get('account')
        if not isinstance(account, dict) or account.get('type') != 'chatgpt':
            raise Refusal('ChatGPT subscription login required')
        cursor = None
        for _ in range(16):
            catalog = self.rpc('model/list', {'cursor': cursor, 'limit': 100})
            for model in catalog.get('data', []):
                if model.get('model') == self.args.model or model.get('id') == self.args.model:
                    self.supported = list(dict.fromkeys(x['reasoningEffort'] for x in model.get('supportedReasoningEfforts', [])
                                      if x.get('reasoningEffort') in LEVELS))
            cursor = catalog.get('nextCursor')
            if self.supported or not cursor:
                break
        if self.args.effort not in self.supported:
            raise Refusal('initial effort unsupported by model catalog')
        startup = {'model': self.args.model, 'modelProvider': 'openai', 'cwd': str(Path.cwd()),
                   'allowProviderModelFallback': False, 'experimentalRawEvents': False}
        # Omission inherits CLI permissions; only explicit startup choices override them.
        if self.args.sandbox is not None:
            startup['sandbox'] = self.args.sandbox
        if self.args.approval_policy is not None:
            startup['approvalPolicy'] = self.args.approval_policy
        started = self.rpc('thread/start', startup)
        self.thread = started['thread']['id']
        configured = started['thread'].get('reasoningEffort')
        self.configured = configured if configured in LEVELS else None
        turn = self.rpc('turn/start', {'threadId': self.thread, 'effort': self.args.effort,
                                     'input': [{'type': 'text', 'text': prompt.decode('utf-8')}]})
        self.turn = turn['turn']['id']
        self.record_output('lifecycle', {'event': 'turn_started', 'model': self.args.model, 'effort': self.args.effort})
        while self.done is None:
            if b'\n' in self.buffer:
                self.event(self.message(time.monotonic() + 8))
                continue
            ready, _, _ = select.select([self.child.stdout, self.listener], [], [], .2)
            if self.child.stdout in ready:
                self.event(self.message(time.monotonic() + 8))
            if self.listener in ready and self.done is None:
                self.control()
        self.record_output('lifecycle', {'event': 'session_completed', 'exit_code': self.done})
        self.write_meta()
        return self.done

    def close(self):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if self.sessions_directory is not None:
            exit_code = self.stop_code if self.stop_code is not None else (self.done if self.done is not None else 2)
            self.done = exit_code
            state = 'completed' if exit_code == 0 else ('interrupted' if exit_code in (130, 143) else 'failed')
            try:
                self.record_output('lifecycle', {'event': 'session_completed', 'exit_code': exit_code})
            except OSError:
                pass
            try:
                self.write_meta(state, exit_code)
            except OSError:
                pass
        if getattr(self, 'output_fd', None) is not None:
            try:
                os.close(self.output_fd)
            except OSError:
                pass
            self.output_fd = None
        if self.child:
            # Keep the session leader unreaped (including a zombie leader) until
            # every group signal is complete; its PID/PGID cannot be recycled.
            try:
                os.killpg(self.child.pid, signal.SIGTERM)
                deadline = time.monotonic() + .2
                while time.monotonic() < deadline:
                    time.sleep(.01)
                os.killpg(self.child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            finally:
                self.child.wait()
        if self.listener:
            self.listener.close()
        if self.manifest_inode:
            try:
                if read_private(self.manifest)[1] == self.manifest_inode:
                    self.manifest.unlink()
            except (OSError, Refusal, ValueError):
                pass
        if self.directory:
            try:
                (self.directory / 'control.sock').unlink()
                self.directory.rmdir()
            except OSError:
                pass


def client(args):
    manifest = endpoint(args.project, args.worker)
    if not os.path.lexists(manifest):
        return {'state': 'unsupported', 'effective': 'Unknown', 'worker': args.worker}
    doc, inode = read_private(manifest)
    if doc['project'] != str(Path(args.project).absolute()) or doc['worker'] != args.worker:
        raise Refusal('channel binding mismatch')
    identity(doc)
    if process_stamp(doc['pid']) != doc['pid_stamp']:
        raise Refusal('stale backend')
    path = safe_path(doc['socket'])
    st, parent = path.lstat(), path.parent.stat()
    if (not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077
            or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
        raise Refusal('unsafe channel')
    request = {'nonce': doc['nonce']}
    if args.effort:
        request['effort'] = args.effort
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(20)
        directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            if (os.fstat(directory_fd).st_dev, os.fstat(directory_fd).st_ino) != (parent.st_dev, parent.st_ino):
                raise Refusal('replaced socket directory')
            connection.connect(f'/proc/self/fd/{directory_fd}/control.sock')
        finally:
            os.close(directory_fd)
        peer_pid, peer_uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if peer_pid != doc['pid'] or peer_uid != os.getuid():
            raise Refusal('replaced socket peer')
        if read_private(manifest) != (doc, inode):
            raise Refusal('replaced channel')
        wire = (json.dumps(request, ensure_ascii=False) + '\n').encode('utf-8')
        if len(wire) > WIRE_BOUND:
            raise Refusal('request wire bound exceeded')
        connection.sendall(wire)
        data = b''
        while b'\n' not in data:
            chunk = connection.recv(BOUND + 1 - len(data))
            if not chunk or len(data) + len(chunk) > BOUND:
                raise Refusal('invalid response bounds')
            data += chunk
    result = json.loads(data)
    allowed = {'worker', 'task', 'route', 'model', 'requested', 'configured', 'pending_next_turn', 'effective', 'supported', 'state'}
    if not isinstance(result, dict) or set(result) != allowed or result['worker'] != args.worker or result['task'] != doc['task']:
        raise Refusal('invalid response')
    if (result['state'] not in ('observed', 'acknowledged', 'unverified', 'rejected')
            or result['route'] != 'codex-app-server' or result['effective'] != 'Unknown'
            or result['requested'] not in LEVELS or result['configured'] not in (*LEVELS, None)
            or type(result['pending_next_turn']) is not bool
            or not isinstance(result['supported'], list) or any(v not in LEVELS for v in result['supported'])
            or not isinstance(result['model'], str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,127}', result['model'])):
        raise Refusal('invalid response settings')
    return result


def session_binding(args, manifest):
    latest_path = safe_path(Path(args.project) / 'coord/sessions' / f'latest-{args.worker}.json')
    if not os.path.lexists(latest_path):
        if os.path.lexists(manifest):
            doc, _ = read_private(manifest)
            if doc.get('session_id'):
                raise Refusal('missing session binding')
        return None
    latest, _ = read_private(latest_path)
    if (not isinstance(latest, dict)
            or set(latest) != {'session_id', 'worker', 'task', 'active', 'exit_code'}
            or type(latest.get('active')) is not bool
            or latest.get('worker') != args.worker
            or not isinstance(latest.get('session_id'), str)
            or not LABEL.fullmatch(latest['session_id'])
            or not isinstance(latest.get('task'), str) or not LABEL.fullmatch(latest['task'])):
        raise Refusal('invalid latest binding')
    sid = latest['session_id']
    meta, _ = read_private(safe_path(latest_path.parent / f'{sid}.json'))
    if (not isinstance(meta, dict)
            or set(meta) != {'session_id', 'worker', 'task', 'route', 'model', 'requested',
                             'configured', 'effective', 'state', 'exit_code', 'output_cursor'}
            or meta.get('effective') != 'Unknown'
            or latest['active'] != (meta.get('state') == 'active')
            or latest['exit_code'] != meta.get('exit_code')
            or any(meta.get(k) != latest[k] for k in ('session_id', 'worker', 'task'))
            or meta.get('route') != 'codex-app-server'
            or meta.get('state') not in ('active', 'completed', 'failed', 'interrupted')
            or type(meta.get('output_cursor')) is not int or meta['output_cursor'] < 0
            or meta.get('requested') not in LEVELS or meta.get('configured') not in (*LEVELS, None)
            or not isinstance(meta.get('model'), str)
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,127}', meta['model'])
            or (meta.get('exit_code') is not None and type(meta['exit_code']) is not int)
            or (meta['state'] == 'active' and meta.get('exit_code') is not None)
            or (meta['state'] != 'active' and meta.get('exit_code') is None)):
        raise Refusal('invalid archive binding')
    if os.path.lexists(manifest):
        doc, _ = read_private(manifest)
        if (not isinstance(doc, dict) or doc.get('project') != str(Path(args.project).absolute())
                or any(doc.get(k) != latest[k] for k in ('session_id', 'worker', 'task'))):
            raise Refusal('replaced archive binding')
    return meta


def session_client(args):
    if not LABEL.fullmatch(args.worker):
        raise Refusal('invalid worker')
    latest_path = safe_path(Path(args.project) / 'coord/sessions' / f'latest-{args.worker}.json')
    manifest = endpoint(args.project, args.worker)

    meta = session_binding(args, manifest)
    if args.session_action == 'status':
        if meta is None:
            return {'worker': args.worker, 'state': 'unsupported', 'effective': 'Unknown'}
        state = meta['state']
        if state == 'active':
            try:
                doc, _ = read_private(manifest)
                if any(doc.get(k) != meta[k] for k in ('session_id', 'worker', 'task')):
                    raise Refusal('replaced archive binding')
                if process_stamp(doc['pid']) != doc['pid_stamp']:
                    raise Refusal('stale backend')
                identity(doc)
            except (Refusal, OSError, KeyError, ValueError):
                state = 'stale'
        return dict(meta, state=state, effective='Unknown')

    elif args.session_action == 'output':
        after = 0 if args.after is None else args.after
        limit = 100 if args.limit is None else args.limit
        if after < 0 or limit < 1 or limit > 500:
            raise Refusal('invalid bounds')

        if meta is None:
            return {'worker': args.worker, 'state': 'unsupported', 'effective': 'Unknown'}
        session_id = meta['session_id']
        output_file = safe_path(Path(args.project) / 'coord/sessions' / f'{session_id}.output.jsonl')
        if not os.path.lexists(output_file):
            records, next_cursor, last_cursor, truncated, gap = [], after, 0, False, meta['output_cursor'] > 0
        else:
            records, next_cursor, last_cursor, truncated, gap = read_session_output(output_file, after=after, limit=limit)
        # Metadata can precede this read while output appends, so a newer
        # transcript is valid. A shorter validated prefix proves missing history.
        if last_cursor < meta['output_cursor']:
            gap = truncated = True

        return {
            'session_id': session_id,
            'worker': meta['worker'],
            'task': meta['task'],
            'after': after,
            'limit': limit,
            'next_cursor': next_cursor,
            'output_cursor': last_cursor,
            'records': records,
            'truncated': truncated,
            'gap': gap
        }

    elif args.session_action == 'send':
        if meta is None or meta['state'] != 'active':
            raise Refusal('turn already finished')
        if not LABEL.fullmatch(args.request_id):
            raise Refusal('invalid request id')
        file_path = safe_path(args.file)
        fd = os.open(file_path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or st.st_uid != os.getuid() or st.st_mode & 0o077):
                raise Refusal('unsafe file permissions')
            if st.st_size <= 0 or st.st_size > MAX_STEER_TEXT:
                raise Refusal('invalid file bounds')
            data = os.read(fd, MAX_STEER_TEXT + 1)
        finally:
            os.close(fd)
        if len(data) > MAX_STEER_TEXT or not data:
            raise Refusal('invalid file bounds')
        try:
            text = data.decode('utf-8')
        except UnicodeDecodeError:
            raise Refusal('invalid utf-8 text')
        if not text:
            raise Refusal('empty text')

        if not os.path.lexists(manifest):
            raise Refusal('turn already finished')
        doc, inode = read_private(manifest)
        if (doc['project'] != str(Path(args.project).absolute())
                or any(doc.get(k) != meta[k] for k in ('session_id', 'worker', 'task'))):
            raise Refusal('channel binding mismatch')
        identity(doc)
        if process_stamp(doc['pid']) != doc['pid_stamp']:
            raise Refusal('stale backend')
        path = safe_path(doc['socket'])
        st, parent = path.lstat(), path.parent.stat()
        if (not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.getuid() or st.st_mode & 0o077
                or parent.st_uid != os.getuid() or parent.st_mode & 0o077):
            raise Refusal('unsafe channel')

        request = {
            'nonce': doc['nonce'],
            'steer': {
                'request_id': args.request_id,
                'text': text
            }
        }
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(20)
            directory_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                if (os.fstat(directory_fd).st_dev, os.fstat(directory_fd).st_ino) != (parent.st_dev, parent.st_ino):
                    raise Refusal('replaced socket directory')
                connection.connect(f'/proc/self/fd/{directory_fd}/control.sock')
            finally:
                os.close(directory_fd)
            peer_pid, peer_uid, _ = struct.unpack('3i', connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if peer_pid != doc['pid'] or peer_uid != os.getuid():
                raise Refusal('replaced socket peer')
            if read_private(manifest) != (doc, inode):
                raise Refusal('replaced channel')
            wire = (json.dumps(request, ensure_ascii=False) + '\n').encode('utf-8')
            if len(wire) > WIRE_BOUND:
                raise Refusal('request wire bound exceeded')
            try:
                connection.sendall(wire)
                data = b''
                while b'\n' not in data:
                    chunk = connection.recv(BOUND + 1 - len(data))
                    if not chunk or len(data) + len(chunk) > BOUND:
                        raise OSError('unverified control response')
                    data += chunk
            except OSError:
                return {'session_id': doc['session_id'], 'worker': args.worker,
                        'task': doc['task'], 'request_id': args.request_id, 'state': 'uncertain'}
        try:
            result = json.loads(data)
            allowed = {'session_id', 'worker', 'task', 'request_id', 'state'}
            if (not isinstance(result, dict) or set(result) != allowed
                    or result['worker'] != args.worker or result['task'] != doc['task']
                    or result['state'] not in ('accepted', 'rejected', 'uncertain')
                    or result['session_id'] != doc['session_id'] or result['request_id'] != args.request_id):
                raise Refusal('invalid response')
        except (Refusal, ValueError, TypeError, KeyError, RecursionError):
            return {'session_id': doc['session_id'], 'worker': args.worker,
                    'task': doc['task'], 'request_id': args.request_id, 'state': 'uncertain'}
        return result



def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run')
    run.add_argument('--model', required=True)
    run.add_argument('--effort', required=True, choices=LEVELS)
    # Fixed string variants from Codex CLI 0.162.1 ThreadStartParams.
    run.add_argument('--sandbox', choices=('read-only', 'workspace-write', 'danger-full-access'),
                     help='explicit startup sandbox; omitted inherits CLI settings')
    run.add_argument('--approval-policy', choices=('untrusted', 'on-request', 'never'),
                     help='explicit startup approval policy; omitted inherits CLI settings')
    run.add_argument('--binary', default='codex')
    get = sub.add_parser('effort')
    get.add_argument('worker')
    get.add_argument('effort', nargs='?', choices=LEVELS)
    get.add_argument('--project', required=True)
    get.add_argument('--json', action='store_true')

    sess = sub.add_parser('session')
    sess.add_argument('--project', required=True)
    sess_sub = sess.add_subparsers(dest='session_action', required=True)

    st = sess_sub.add_parser('status')
    st.add_argument('worker')
    st.add_argument('--json', action='store_true')

    out = sess_sub.add_parser('output')
    out.add_argument('worker')
    out.add_argument('--after', type=int, default=None)
    out.add_argument('--limit', type=int, default=None)
    out.add_argument('--json', action='store_true')

    snd = sess_sub.add_parser('send')
    snd.add_argument('worker')
    snd.add_argument('--file', required=True)
    snd.add_argument('--request-id', required=True)
    snd.add_argument('--json', action='store_true')

    args = parser.parse_args()
    if args.action == 'run' and not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,127}', args.model):
        parser.error('invalid model label')
    if args.action == 'run':
        server = Server(args)
        try:
            return server.run()
        except (Cancelled, Refusal, OSError, ValueError, KeyError, TypeError, RecursionError) as error:
            reason = str(error) if isinstance(error, (Cancelled, Refusal)) else 'invalid or unavailable provider transport'
            print('unio codex Source: failed (no replay): ' + reason, file=sys.stderr)
            return server.stop_code or server.done or 2
        finally:
            server.close()
    if args.action == 'session':
        try:
            result = session_client(args)
        except (Refusal, OSError, ValueError, KeyError, TypeError, RecursionError):
            result = {'worker': args.worker, 'state': 'stale-or-invalid', 'effective': 'Unknown'}
        if args.json:
            print(json.dumps(result))
        else:
            if args.session_action == 'output' and 'records' in result:
                for rec in result['records']:
                    kind = rec.get('kind', 'unknown')
                    data = rec.get('data', {})
                    if 'delta' in data:
                        print(f"[{rec.get('cursor')}] {kind}: {data['delta']}", end='')
                        if not data['delta'].endswith('\n'):
                            print()
                    else:
                        print(f"[{rec.get('cursor')}] {kind}: {json.dumps(data)}")
                print(f"session_id={result['session_id']} next_cursor={result['next_cursor']} output_cursor={result['output_cursor']} count={len(result['records'])}")
            else:
                print(' '.join(f'{k}={v}' for k, v in result.items()))
        if args.session_action == 'status':
            return 0 if result.get('state') in ('active', 'completed', 'failed', 'interrupted') else 2
        elif args.session_action == 'output':
            return 0 if 'records' in result else 2
        elif args.session_action == 'send':
            return 0 if result.get('state') == 'accepted' else 2
        return 2

    try:
        result = client(args)
    except (Refusal, OSError, ValueError, KeyError, TypeError, RecursionError):
        result = {'worker': args.worker, 'state': 'stale-or-invalid', 'effective': 'Unknown'}
    print(json.dumps(result) if args.json else ' '.join(f'{k}={v}' for k, v in result.items()))
    return 0 if result['state'] in ('observed', 'acknowledged', 'unverified') else 2

if __name__ == '__main__':
    sys.exit(main())
