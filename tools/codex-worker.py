#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Owned native Codex app-server Source and bounded local effort client."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import uuid

LEVELS = ('low', 'medium', 'high', 'xhigh')
BOUND = 16384
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')

class Refusal(Exception):
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
        return json.loads(data), (st.st_dev, st.st_ino)
    finally:
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

    def stop(self, number, frame):
        self.stop_code = 128 + number
        raise Refusal('interrupted')

    def send(self, data):
        self.child.stdin.write((json.dumps(data) + '\n').encode())
        self.child.stdin.flush()

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
        if method in ('item/agentMessage/delta', 'item/commandExecution/outputDelta'):
            delta = p.get('delta')
            if isinstance(delta, str):
                print(delta, end='', flush=True)
        if method == 'turn/completed':
            turn = p.get('turn', {})
            if self.turn is None or turn.get('id') == self.turn:
                self.done = {'completed': 0, 'failed': 1, 'interrupted': 130}.get(turn.get('status'), 1)

    def message(self, deadline):
        while b'\n' not in self.buffer:
            if time.monotonic() >= deadline:
                raise Refusal('provider RPC timeout')
            ready, _, _ = select.select([self.child.stdout], [], [], min(.2, max(0, deadline-time.monotonic())))
            if not ready:
                continue
            data = os.read(self.child.stdout.fileno(), 65536)
            if not data:
                code = self.child.wait()
                self.done = code if code > 0 else (128-code if code < 0 else 1)
                raise Refusal('provider exited')
            self.buffer += data
            if len(self.buffer) > 2 * 1024 * 1024:
                raise Refusal('provider message bound exceeded')
        line, self.buffer = self.buffer.split(b'\n', 1)
        msg = json.loads(line)
        if not isinstance(msg, dict):
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
                    raise Refusal('provider rejected RPC')
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
            try:
                data = b''
                while b'\n' not in data:
                    chunk = conn.recv(BOUND + 1 - len(data))
                    if not chunk or len(data) + len(chunk) > BOUND:
                        raise Refusal('invalid request bounds')
                    data += chunk
                if data.count(b'\n') != 1 or not data.endswith(b'\n'):
                    raise Refusal('invalid request framing')
                req = json.loads(data)
                if not isinstance(req, dict) or set(req) not in ({'nonce'}, {'nonce', 'effort'}):
                    raise Refusal('forbidden settings')
                current, inode = read_private(self.manifest)
                if current != self.doc or inode != self.manifest_inode or req['nonce'] != self.doc['nonce']:
                    raise Refusal('stale or replaced channel')
                identity(self.doc)
                state = 'observed'
                if 'effort' in req:
                    effort = req['effort']
                    if effort not in self.supported:
                        raise Refusal('unsupported effort')
                    if self.done is not None:
                        raise Refusal('turn already finished')
                    self.requested = effort
                    self.pending = True
                    self.rpc('thread/settings/update', {'threadId': self.thread, 'effort': effort})
                    # Empty response is only RPC success; readback establishes configuration.
                    thread = self.rpc('thread/read', {'threadId': self.thread, 'includeTurns': False}).get('thread', {})
                    if thread.get('reasoningEffort') in LEVELS:
                        self.configured = thread['reasoningEffort']
                    state = 'acknowledged' if self.configured == effort else 'unverified'
                result = self.view(state)
            except (Refusal, OSError, ValueError, KeyError, TypeError):
                result = self.view('rejected')
            conn.sendall((json.dumps(result) + '\n').encode())

    def run(self):
        env = os.environ
        root, worker, task, slot, holder = [env.get('UNIO_CODEX_' + k) for k in ('PROJECT', 'WORKER', 'TASK', 'SLOT', 'HOLDER')]
        if not all((root, worker, task, slot, holder)):
            raise Refusal('managed native run required')
        meta, inode = read_private(slot)
        self.doc = {'project': root, 'worker': worker, 'task': task, 'slot': slot,
                    'slot_inode': list(inode), 'holder': int(holder), 'holder_stamp': process_stamp(int(holder)),
                    'pid': os.getpid(), 'pid_stamp': process_stamp(os.getpid()), 'nonce': uuid.uuid4().hex}
        identity(self.doc)
        supervisor = int(env.get('UNIO_CODEX_SUPERVISOR', '0'))
        ancestor = os.getppid()
        while ancestor > 1 and ancestor != supervisor:
            ancestor = int(Path('/proc', str(ancestor), 'stat').read_text().rsplit(')', 1)[1].split()[1])
        if supervisor <= 1 or ancestor != supervisor or Path.cwd() != Path(root) / 'wt' / worker:
            raise Refusal('not owned by native Source supervisor')
        prompt_path = safe_path(env['TASKFILE'])
        if prompt_path != Path(root) / 'coord/reports' / (task + '.prompt.md'):
            raise Refusal('task binding mismatch')
        with open(prompt_path, 'rb') as f:
            prompt = f.read(2 * 1024 * 1024 + 1)
        if len(prompt) > 2 * 1024 * 1024:
            raise Refusal('task too large')
        signal.signal(signal.SIGTERM, self.stop)
        signal.signal(signal.SIGINT, self.stop)
        self.child = subprocess.Popen([self.args.binary, 'app-server', '--listen', 'stdio://'],
                                      stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                      start_new_session=True)
        self.rpc('initialize', {'clientInfo': {'name': 'unio-managed-source', 'version': '1'},
                                'capabilities': {'experimentalApi': True}})
        self.send({'method': 'initialized', 'params': {}})
        cursor = None
        for _ in range(16):
            catalog = self.rpc('model/list', {'cursor': cursor, 'limit': 100})
            for model in catalog.get('data', []):
                if model.get('model') == self.args.model or model.get('id') == self.args.model:
                    self.supported = [x['reasoningEffort'] for x in model.get('supportedReasoningEfforts', [])
                                      if x.get('reasoningEffort') in LEVELS]
            cursor = catalog.get('nextCursor')
            if self.supported or not cursor:
                break
        if self.args.effort not in self.supported:
            raise Refusal('initial effort unsupported by model catalog')
        started = self.rpc('thread/start', {'model': self.args.model, 'cwd': str(Path.cwd()),
                           'allowProviderModelFallback': False, 'experimentalRawEvents': False})
        self.thread = started['thread']['id']
        self.configured = started['thread'].get('reasoningEffort')
        turn = self.rpc('turn/start', {'threadId': self.thread, 'effort': self.args.effort,
                                     'input': [{'type': 'text', 'text': prompt.decode('utf-8')}]})
        self.turn = turn['turn']['id']
        self.directory = Path(tempfile.mkdtemp(prefix='unio-codex-'))
        self.listener = socket.socket(socket.AF_UNIX)
        socket_path = self.directory / 'control.sock'
        self.listener.bind(str(socket_path))
        os.chmod(socket_path, 0o600)
        self.listener.listen(4)
        self.doc['socket'] = str(socket_path)
        self.manifest = endpoint(root, worker)
        fd = os.open(self.manifest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as f:
            json.dump(self.doc, f)
        _, self.manifest_inode = read_private(self.manifest)
        while self.done is None:
            if b'\n' in self.buffer:
                self.event(self.message(time.monotonic() + 8))
                continue
            ready, _, _ = select.select([self.child.stdout, self.listener], [], [], .2)
            if self.child.stdout in ready:
                self.event(self.message(time.monotonic() + 8))
            if self.listener in ready and self.done is None:
                self.control()
        return self.done

    def close(self):
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        signal.signal(signal.SIGINT, signal.SIG_IGN)
        if self.child:
            try:
                os.killpg(self.child.pid, signal.SIGTERM)
                self.child.wait(timeout=2)
            except subprocess.TimeoutExpired:
                os.killpg(self.child.pid, signal.SIGKILL)
                self.child.wait()
            except ProcessLookupError:
                pass
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
    if not manifest.exists():
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
        connection.connect(str(path))
        if read_private(manifest) != (doc, inode):
            raise Refusal('replaced channel')
        connection.sendall((json.dumps(request) + '\n').encode())
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
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    run = sub.add_parser('run')
    run.add_argument('--model', required=True)
    run.add_argument('--effort', required=True, choices=LEVELS)
    run.add_argument('--binary', default='codex')
    get = sub.add_parser('effort')
    get.add_argument('worker')
    get.add_argument('effort', nargs='?', choices=LEVELS)
    get.add_argument('--project', required=True)
    get.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.action == 'run':
        server = Server(args)
        try:
            return server.run()
        except (Refusal, OSError, ValueError, KeyError, TypeError):
            print('unio codex Source: failed (no replay)', file=sys.stderr)
            return server.stop_code or server.done or 2
        finally:
            server.close()
    try:
        result = client(args)
    except (Refusal, OSError, ValueError, KeyError, TypeError):
        result = {'worker': args.worker, 'state': 'stale-or-invalid', 'effective': 'Unknown'}
    print(json.dumps(result) if args.json else ' '.join(f'{k}={v}' for k, v in result.items()))
    return 0 if result['state'] in ('observed', 'acknowledged', 'unverified') else 2

if __name__ == '__main__':
    sys.exit(main())
