#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Existing-session attach suite: executable fake daemon proxy, zero providers.

Every check drives the production attach branch of tools/lead-session.py
end to end through its real CLI `main()` against an executable fake
`codex app-server proxy` that implements the PROVEN shared-daemon
control transport: an RFC 6455 websocket upgrade over the proxy's stdio
byte pipe and one JSON-RPC message per websocket TEXT frame. The fake
records every received RPC to a wire log and persists applied efforts
to durable state, so framing, exact-id acknowledgements, read bounds,
pending/requested display, manual precedence, STOP/admission semantics
and forbidden-RPC guarantees are asserted from OUTSIDE the CLI.

Nothing here starts or stops any real daemon: the fake proxy is this
test's own child process and dies with the connector's own proxy kill.
No Codex binary, account or model call is ever touched.
"""
import contextlib
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile

SOURCE = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, SOURCE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load('lead_session', 'tools/lead-session.py')
ml = cli.ml
pe = cli.pe
lp = cli.lp
at = cli.at

REFUSALS = (cli.Refusal, ml.Refusal, pe.Refusal, lp.Refusal, at.Refusal)
MODEL = 'gpt-5.4-codex'
THREAD = 'fake-shared-thread-1'
OTHER = 'fake-shared-thread-2'
FOREIGN = 'fake-foreign-thread-9'

FAKE_PROXY_TEMPLATE = '''#!/usr/bin/env python3
"""Generated fake `codex app-server proxy` for offline attach tests."""
import base64
import hashlib
import json
import os
import select
import sys
import time
from pathlib import Path

LOG_PATH = Path(__LOG__)
BEHAVIOR_PATH = Path(__BEHAVIOR__)
STATE_PATH = Path(__STATE__)
WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
LOADED_DEFAULT = __LOADED__
MODEL = __MODEL__
FOREIGN_ID = __FOREIGN__
IDLE_DEADLINE = 120.0


def log(event, **facts):
    rec = {'event': event, 'pid': os.getpid()}
    rec.update(facts)
    line = (json.dumps(rec) + chr(10)).encode()
    fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'ab') as stream:
        stream.write(line)
        stream.flush()


def behavior():
    if BEHAVIOR_PATH.exists():
        try:
            doc = json.loads(BEHAVIOR_PATH.read_text())
        except ValueError:
            doc = {}
        if isinstance(doc, dict):
            return doc
    return {}


def loaded_ids():
    loaded = behavior().get('loaded')
    return LOADED_DEFAULT if loaded is None else loaded


def load_state():
    if STATE_PATH.exists():
        try:
            doc = json.loads(STATE_PATH.read_text())
            return doc if isinstance(doc, dict) else {}
        except ValueError:
            return {}
    return {}


def save_state(doc):
    tmp = STATE_PATH.with_name(STATE_PATH.name + '.tmp')
    tmp.write_text(json.dumps(doc))
    os.replace(tmp, STATE_PATH)


INPUT_BUFFER = b''


def read_bytes(count, deadline):
    global INPUT_BUFFER
    while len(INPUT_BUFFER) < count:
        if time.monotonic() > deadline:
            sys.exit(3)
        ready, _, _ = select.select([sys.stdin.buffer], [], [], 0.2)
        if not ready:
            continue
        chunk = os.read(sys.stdin.buffer.fileno(), 65536)
        if not chunk:
            log('eof')
            sys.exit(0)
        INPUT_BUFFER += chunk
    out, INPUT_BUFFER = INPUT_BUFFER[:count], INPUT_BUFFER[count:]
    return out


def write(data):
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def frame(code, payload):
    header = bytearray([code])
    length = len(payload)
    if length < 126:
        header.append(length)
    elif length < 65536:
        header.append(126)
        header += length.to_bytes(2, 'big')
    else:
        header.append(127)
        header += length.to_bytes(8, 'big')
    write(bytes(header) + payload)


def read_frame(deadline):
    head = read_bytes(2, deadline)
    opcode = head[0] & 0x0f
    length = head[1] & 0x7f
    masked = bool(head[1] & 0x80)
    if length == 126:
        length = int.from_bytes(read_bytes(2, deadline), 'big')
    elif length == 127:
        length = int.from_bytes(read_bytes(8, deadline), 'big')
    mark = read_bytes(4, deadline) if masked else b''
    payload = read_bytes(length, deadline)
    if masked:
        payload = bytes(byte ^ mark[index % 4]
                        for index, byte in enumerate(payload))
    return opcode, payload


def reply(doc):
    frame(0x81, json.dumps(doc).encode())


def main():
    log('argv', argv=sys.argv)
    deadline = time.monotonic() + IDLE_DEADLINE
    head = b''
    while b'\\r\\n\\r\\n' not in head:
        if time.monotonic() > deadline:
            sys.exit(3)
        ready, _, _ = select.select([sys.stdin.buffer], [], [], 0.2)
        if not ready:
            continue
        chunk = os.read(sys.stdin.buffer.fileno(), 65536)
        if not chunk:
            log('eof')
            sys.exit(0)
        head += chunk
        if len(head) > 8192:
            sys.exit(4)
    key = None
    for line in head.split(b'\\r\\n')[1:]:
        name, _, value = line.partition(b':')
        if name.strip().lower() == b'sec-websocket-key':
            key = value.strip().decode('ascii', 'replace')
    if key is None:
        write(b'HTTP/1.1 400 Bad Request\\r\\n\\r\\n')
        sys.exit(5)
    log('handshake', head_len=len(head))
    if behavior().get('handshake_reject'):
        write(b'HTTP/1.1 403 Forbidden\\r\\n\\r\\n')
        log('handshake_refused')
        sys.exit(0)
    accept = base64.b64encode(hashlib.sha1(
        (key + WS_GUID).encode('ascii')).digest()).decode('ascii')
    write(('HTTP/1.1 101 Switching Protocols\\r\\n'
           'Upgrade: websocket\\r\\nConnection: Upgrade\\r\\n'
           'Sec-WebSocket-Accept: ' + accept + '\\r\\n\\r\\n').encode())
    if behavior().get('exit_after_handshake'):
        sys.exit(0)
    while True:
        opcode, payload = read_frame(deadline)
        if opcode == 0x8:
            frame(0x88, b'')
            log('closed')
            sys.exit(0)
        if opcode == 0x9:
            frame(0x8A, payload)
            continue
        if opcode != 0x1:
            continue
        try:
            doc = json.loads(payload)
        except ValueError:
            continue
        if not isinstance(doc, dict):
            continue
        method = doc.get('method')
        params = doc.get('params')
        if not isinstance(params, dict):
            params = {}
        if 'id' not in doc:
            log('notification', method=method)
            continue
        log('rpc', method=method, params=params)
        request_id = doc.get('id')
        if method == 'initialize':
            if behavior().get('oversize'):
                frame(0x81, b'{"id": ' + str(request_id).encode()
                      + b', "result": "' + b'x' * (3 * 1024 * 1024) + b'"}')
                continue
            reply({'id': request_id, 'result': {
                'codexHome': '/fake', 'platformFamily': 'unix',
                'platformOs': 'linux', 'userAgent': 'fake-app-server/0'}})
        elif method == 'thread/loaded/list':
            reply({'id': request_id, 'result': {
                'data': loaded_ids(), 'nextCursor': None}})
        elif method == 'model/list':
            models = behavior().get('models', {MODEL: ['low', 'xhigh']})
            data = [{'id': name, 'model': name,
                     'supportedReasoningEfforts': [
                         {'reasoningEffort': effort}
                         for effort in efforts]}
                    for name, efforts in models.items()]
            reply({'id': request_id, 'result': {'data': data,
                                                 'nextCursor': None}})
        elif method == 'thread/read':
            thread_id = params.get('threadId')
            state = load_state()
            effort = behavior().get('read_effort')
            if effort is None:
                effort = state.get('efforts', {}).get(thread_id, 'medium')
            read_id = behavior().get('read_foreign_id', thread_id)
            if (behavior().get('read_foreign_id_after_settings')
                    and thread_id in state.get('efforts', {})):
                read_id = FOREIGN_ID
            reply({'id': request_id, 'result': {'thread': {
                'id': read_id,
                'status': {'type': behavior().get('read_status', 'idle')},
                'reasoningEffort': effort,
                'model': behavior().get('read_model', MODEL),
                'turns': []}}})
        elif method == 'thread/settings/update':
            mode = behavior().get('settings', 'ok')
            if mode == 'silence':
                log('settings_silence')
                continue
            if mode == 'reject':
                reply({'id': request_id, 'error': {
                    'code': -32602,
                    'message': 'fake daemon rejects this effort'}})
                continue
            state = load_state()
            state.setdefault('efforts', {})[params.get('threadId')] = \\
                params.get('effort')
            save_state(state)
            reply({'id': request_id, 'result': {}})
        else:
            reply({'id': request_id, 'error': {
                'code': -32601, 'message': 'fake method unsupported'}})


main()
'''


def refuses(argv):
    try:
        cli.main(argv)
    except REFUSALS as exc:
        return str(exc)
    raise AssertionError('expected Refusal for %r' % (argv,))


def invoke(argv):
    """Run one CLI command; return (payload, human text, exit code)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli.main(argv)
    text = buffer.getvalue()
    if '--json' in argv:
        start = text.index('{')
        return json.loads(text[start:]), text, code
    return None, text, code


def call(argv):
    payload, _, code = invoke(argv)
    assert code == 0, (argv, code)
    return payload


class Workspace:
    counter = 0

    def __init__(self, base):
        Workspace.counter += 1
        self.root = Path(base) / ('lead-attach-' + str(Workspace.counter))
        self.root.mkdir(mode=0o700)
        coord = self.root / 'coord'
        coord.mkdir(mode=0o700)
        (coord / 'work-policy.json').write_text(json.dumps({
            'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
            'lead_agent': 'codex', 'accounts': {'codex': 'codex-shared'},
        }) + '\n', encoding='utf-8')
        self.binary = self.root / 'fake-codex-proxy.py'
        self.log_path = self.root / 'fake-wire-log.jsonl'
        self.state_path = self.root / 'fake-state.json'
        self.behavior_path = self.root / 'fake-behavior.json'
        script = (FAKE_PROXY_TEMPLATE
                  .replace('__LOG__', json.dumps(str(self.log_path)))
                  .replace('__BEHAVIOR__', json.dumps(str(self.behavior_path)))
                  .replace('__STATE__', json.dumps(str(self.state_path)))
                  .replace('__LOADED__',
                           json.dumps([THREAD, OTHER]))
                  .replace('__FOREIGN__', json.dumps(FOREIGN))
                  .replace('__MODEL__', json.dumps(MODEL)))
        self.binary.write_text(script, encoding='utf-8')
        os.chmod(self.binary, 0o700)
        self.behavior_path.write_text('{}', encoding='utf-8')

    # -- fixtures ----------------------------------------------------------

    def behavior(self, doc):
        self.behavior_path.write_text(json.dumps(doc), encoding='utf-8')

    def set_stop(self, active=True):
        stop_file = self.root / 'coord' / 'STOP'
        if active:
            stop_file.write_text('STOP\n')
        elif stop_file.exists():
            stop_file.unlink()

    def set_off(self, agent='codex'):
        off_dir = self.root / 'coord' / 'off'
        off_dir.mkdir(mode=0o700, exist_ok=True)
        (off_dir / agent).write_text('')

    def managed_owner(self, stopped):
        directory = self.root / 'coord' / 'lead-effort'
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        sid = 'lead-' + '0123456789abcdef01234567'
        owner_path = directory / 'owner.json'
        owner_path.write_text(json.dumps({'session_id': sid}),
                              encoding='utf-8')
        os.chmod(owner_path, 0o600)
        state_path = directory / (sid + '.json')
        state_path.write_text(json.dumps({
            'session_id': sid, 'stopped': stopped, 'transport': 'owned',
        }), encoding='utf-8')
        os.chmod(state_path, 0o600)

    @contextlib.contextmanager
    def occupy_lease(self):
        locks_dir = self.root / 'coord' / '.locks'
        locks_dir.mkdir(parents=True, exist_ok=True)
        lease_path = locks_dir / 'lead-session.lock'
        fd = os.open(lease_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield lease_path
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    @contextlib.contextmanager
    def occupy_slot(self, group='codex-shared'):
        slot_dir = (self.root / 'coord' / '.locks'
                    / 'work-policy-slots' / group)
        slot_dir.mkdir(parents=True, exist_ok=True)
        slot_path = slot_dir / 'wpslot-attach-1.json'
        slot_path.write_text(json.dumps({
            'schema_version': 1, 'group': group, 'agent': 'worker-1',
            'worker': 'w1', 'task': 't1', 'kind': 'run',
            'created_at': '2026-11-15T10:00:00Z',
        }) + '\n', encoding='utf-8')
        fd = os.open(slot_path, os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield slot_path
        finally:
            fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)
            if slot_path.exists():
                slot_path.unlink()

    # -- CLI helpers -------------------------------------------------------

    def argv(self, control, *extra):
        return ['--project', str(self.root), 'attach', control,
                '--codex-binary', str(self.binary)] + list(extra)

    def inspect(self, thread_id=THREAD, *extra):
        return invoke(self.argv('inspect', '--thread-id', thread_id,
                                '--rpc-timeout', '3', '--json', *extra))

    def attach(self, thread_id=THREAD, *extra):
        return invoke(self.argv('attach', '--thread-id', thread_id,
                                '--rpc-timeout', '3', '--json', *extra))

    def refuses_attach(self, *extra):
        return refuses(self.argv('attach', *extra))

    def phase(self, *extra):
        return invoke(self.argv('phase', '--rpc-timeout', '3',
                                '--json', *extra))

    def refuses_phase(self, *extra):
        return refuses(self.argv('phase', *extra))

    def manual(self, *extra):
        return invoke(self.argv('manual', '--rpc-timeout', '3',
                                '--json', *extra))

    def refuses_manual(self, *extra):
        return refuses(self.argv('manual', *extra))

    def status(self, *extra):
        return invoke(['--project', str(self.root), 'attach', 'status',
                       '--json'] + list(extra))

    def auto(self, *extra):
        return invoke(['--project', str(self.root), 'attach', 'auto',
                       '--json'] + list(extra))

    def detach(self, *extra):
        return invoke(['--project', str(self.root), 'attach', 'detach',
                       '--json'] + list(extra))

    def journal_path(self, thread_id=THREAD):
        return at._journal_path(Path(self.root), thread_id)

    def journal_bytes(self, thread_id=THREAD):
        path = self.journal_path(thread_id)
        return path.read_bytes() if path.exists() else b''

    def journal_entries(self, thread_id=THREAD):
        return [json.loads(line)
                for line in self.journal_bytes(thread_id).splitlines()
                if line.strip()]

    # -- observation -------------------------------------------------------

    def wire(self, after=None):
        if not self.log_path.exists():
            return []
        records = [json.loads(line)
                    for line in self.log_path.read_text().splitlines()
                    if line.strip()]
        return records if after is None else records[after:]

    def rpc_names(self, records):
        return [rec.get('method') for rec in records
                if rec.get('event') == 'rpc']

    def settings_calls(self, records):
        return [rec for rec in records
                if rec.get('event') == 'rpc'
                and rec.get('method') == 'thread/settings/update']

    def record_files(self):
        directory = self.root / 'coord' / 'lead-session-attach'
        if not directory.exists():
            return []
        return sorted(path for path in directory.glob('*.json')
                       if not path.name.startswith('.'))

    def record(self, thread_id=THREAD):
        for path in self.record_files():
            doc = json.loads(path.read_text())
            if doc.get('thread_id') == thread_id:
                return doc
        return None

    def has_record(self, thread_id):
        return any(json.loads(path.read_text()).get('thread_id') == thread_id
                   for path in self.record_files())


def run_suite(base):
    ws = Workspace(base)

    print('handshake, framing and read bounds', flush=True)
    payload, _, code = ws.inspect()
    assert code == 0 and payload['loaded'] is True
    assert payload['status'] == 'idle'
    assert payload['native_requested_effort'] == 'medium'
    assert payload['native_model'] == MODEL
    assert payload['control_capability'] == 'untested'
    assert payload['stop_active'] is False
    assert payload['effective'] == 'Unknown'
    names = ws.rpc_names(ws.wire())
    assert names == ['initialize', 'thread/loaded/list', 'thread/read']
    read_call = [rec for rec in ws.wire()
                 if rec.get('event') == 'rpc'
                 and rec.get('method') == 'thread/read'][0]
    assert read_call['params'] == {'threadId': THREAD, 'includeTurns': False}
    print('  ok    inspect completes the proven websocket transport '
          'read-only (includeTurns false)', flush=True)

    ws.behavior({'handshake_reject': True})
    message = refuses(ws.argv('inspect', '--thread-id', THREAD,
                              '--rpc-timeout', '3', '--json'))
    assert 'refused the websocket upgrade' in message
    ws.behavior({})
    print('  ok    a refused websocket upgrade is one honest refusal '
          '(no invented transport)', flush=True)

    ws.behavior({'exit_after_handshake': True})
    message = refuses(ws.argv('inspect', '--thread-id', THREAD,
                              '--rpc-timeout', '3', '--json'))
    assert 'not reachable' in message
    ws.behavior({})
    print('  ok    a proxy exit right after the upgrade is honest (never '
          'a silent hang or fake success)', flush=True)

    ws.behavior({'oversize': True})
    message = refuses(ws.argv('inspect', '--thread-id', THREAD,
                              '--rpc-timeout', '3', '--json'))
    assert 'message bound exceeded' in message
    ws.behavior({})
    print('  ok    an oversize reply exceeds the read bound and refuses',
          flush=True)

    message = refuses(ws.argv('inspect', '--thread-id', THREAD,
                              '--rpc-timeout', '0.1', '--json'))
    assert '0.5..60' in message
    print('  ok    --rpc-timeout is bounded 0.5..60 seconds', flush=True)

    print('inspect honesty: never resumes, starts or creates', flush=True)
    before = len(ws.wire())
    ws.behavior({'loaded': []})
    payload, _, code = ws.inspect()
    assert code == 0 and payload['loaded'] is False
    assert 'never resumes' in payload['note']
    delta = ws.rpc_names(ws.wire(after=before))
    assert set(delta) <= {'initialize', 'thread/loaded/list'}
    ws.behavior({})
    print('  ok    a not-loaded thread is reported honestly with zero '
          'load calls', flush=True)

    before = len(ws.wire())
    ws.behavior({'read_foreign_id': FOREIGN})
    message = refuses(ws.argv('inspect', '--thread-id', THREAD,
                              '--rpc-timeout', '3', '--json'))
    assert 'foreign' in message and 'no fallback' in message
    ws.behavior({})
    print('  ok    a foreign thread/read acknowledgement refuses without '
          'a fallback thread', flush=True)

    print('explicit initial attach', flush=True)
    before = len(ws.wire())
    payload, _, code = ws.attach()
    assert code == 0 and payload['attached'] is True
    assert payload['thread_status'] == 'idle'
    assert payload['ceiling'] == 'xhigh'
    assert payload['requested'] is None
    record = ws.record()
    assert record is not None
    assert record['auto'] is True and record['detached'] is False
    assert record['thread_id'] == THREAD
    assert record['native']['effort'] == 'medium'
    assert record['effort']['requested'] is None
    assert record['effort']['ack'] is None
    delta = ws.rpc_names(ws.wire(after=before))
    assert 'thread/settings/update' not in delta
    assert set(delta) <= {'initialize', 'thread/loaded/list', 'thread/read'}
    print('  ok    attach records one exact loaded idle thread with zero '
          'control calls', flush=True)

    message = ws.refuses_attach('--thread-id', THREAD, '--rpc-timeout', '3',
                                '--json')
    assert 'duplicate attachment' in message
    print('  ok    duplicate attachment refuses', flush=True)

    fresh = Workspace(base)
    for behavior_doc, wording, target in (
            ({'read_status': 'active'}, 'idle boundary', THREAD),
            ({'loaded': []}, 'not loaded', THREAD),
            ({'read_status': 'systemError'}, 'idle thread', THREAD)):
        fresh.behavior(behavior_doc)
        message = fresh.refuses_attach('--thread-id', target,
                                       '--rpc-timeout', '3', '--json')
        assert wording in message, (behavior_doc, message)
        assert not fresh.has_record(target)
    fresh.behavior({})
    print('  ok    active / not-loaded / system-error threads refuse to '
          'attach; no record was written', flush=True)

    message = fresh.refuses_attach('--thread-id', THREAD, '--effort', 'high',
                                   '--rpc-timeout', '3', '--json')
    assert 'only low and xhigh' in message
    print('  ok    manual high/medium is never substituted through '
          'attach', flush=True)

    payload, _, code = fresh.attach()
    assert code == 0
    message = fresh.refuses_attach('--thread-id', OTHER, '--rpc-timeout',
                                   '3', '--json')
    assert 'already attached' in message
    fresh.detach()
    print('  ok    a second concurrent thread attachment refuses (one '
          'active attach per workspace)', flush=True)

    print('admission: STOP, off hold, policy, capacity, lease', flush=True)
    adm = Workspace(base)
    adm.set_stop(True)
    message = adm.refuses_attach('--thread-id', THREAD, '--rpc-timeout',
                                 '3', '--json')
    assert 'STOP' in message
    assert adm.record_files() == []
    assert adm.wire() == []
    payload, _, code = adm.inspect()
    assert code == 0 and payload['stop_active'] is True
    assert 'blocked' in payload['stop_note']
    print('  ok    STOP blocks attaching (admission before any proxy '
          'spawn) while inspect explains it', flush=True)
    adm.set_stop(False)

    adm.set_off('codex')
    message = adm.refuses_attach('--thread-id', THREAD, '--rpc-timeout',
                                 '3', '--json')
    assert "is off" in message
    (adm.root / 'coord' / 'off' / 'codex').unlink()
    print('  ok    an off hold blocks attaching', flush=True)

    (adm.root / 'coord' / 'work-policy.json').write_text(json.dumps({
        'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
        'lead_agent': 'claude', 'accounts': {'claude': 'group'}}) + '\n')
    message = adm.refuses_attach('--thread-id', THREAD, '--rpc-timeout',
                                 '3', '--json')
    assert 'registered lead mismatch' in message
    (adm.root / 'coord' / 'work-policy.json').write_text(json.dumps({
        'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
        'lead_agent': 'codex', 'accounts': {'codex': 'codex-shared'}}) + '\n')
    print('  ok    a foreign registered lead refuses attach admission',
          flush=True)

    with adm.occupy_slot():
        message = adm.refuses_attach('--thread-id', THREAD, '--rpc-timeout',
                                     '3', '--json')
        assert 'capacity' in message
    print('  ok    native slot capacity counts the lead exactly once '
          '(no new worker slot)', flush=True)

    with adm.occupy_lease():
        message = adm.refuses_attach('--thread-id', THREAD, '--rpc-timeout',
                                     '3', '--json')
        assert 'already running' in message
    print('  ok    a busy owned lead lease refuses a concurrent attach',
          flush=True)

    owner_ws = Workspace(base)
    owner_ws.managed_owner(stopped=False)
    message = owner_ws.refuses_attach('--thread-id', THREAD, '--rpc-timeout',
                                      '3', '--json')
    assert 'active managed owned lead' in message
    owner_ws.managed_owner(stopped=True)
    payload, _, code = owner_ws.attach()
    assert code == 0
    print('  ok    an unstopped managed owned lead refuses attach; a '
          'stopped one does not', flush=True)

    print('explicit phase signals', flush=True)
    before = len(ws.wire())
    payload, _, code = ws.phase('--effort', 'xhigh')
    assert code == 0
    assert payload['requested']['effort'] == 'xhigh'
    assert payload['requested']['ack'] == 'acknowledged'
    assert payload['active_turn'] is False
    assert payload['advertised'] == ['low', 'xhigh']
    calls = ws.settings_calls(ws.wire(after=before))
    assert calls and calls[-1]['params'] == {'threadId': THREAD,
                                             'effort': 'xhigh'}
    record = ws.record()
    assert record['effort']['requested'] == 'xhigh'
    assert record['effort']['ack'] == 'acknowledged'
    assert record['native']['effort'] == 'xhigh'
    print('  ok    explicit phase xhigh applies to future turns with '
          'exactly threadId+effort params', flush=True)

    payload, _, code = ws.phase('--kind', 'coordination')
    assert code == 0 and payload['requested']['effort'] == 'low'
    payload, _, code = ws.phase('--kind', 'review')
    assert code == 0 and payload['requested']['effort'] == 'xhigh'
    payload, _, code = ws.phase('--kind', 'planning')
    assert code == 0 and payload['requested']['effort'] == 'xhigh'
    print('  ok    coordination requests low; planning and review request '
          'the ceiling', flush=True)

    message = ws.refuses_phase('--effort', 'medium', '--rpc-timeout', '3',
                               '--json')
    assert 'only low and xhigh' in message
    print('  ok    medium through phase refuses without substitution',
          flush=True)

    empty_ws = Workspace(base)
    message = empty_ws.refuses_phase('--effort', 'xhigh', '--rpc-timeout',
                                     '3', '--json')
    assert 'no active attach record' in message
    print('  ok    phase without an attach record refuses', flush=True)

    print('manual precedence and suspension', flush=True)
    before = len(ws.wire())
    ws.behavior({'read_effort': 'low'})  # native manual change
    message = ws.refuses_phase('--effort', 'xhigh', '--rpc-timeout', '3',
                               '--json')
    assert 'native manual change detected' in message
    assert 'attach auto' in message
    delta = ws.wire(after=before)
    assert all(rec.get('method') != 'thread/settings/update' for rec in delta)
    record = ws.record()
    assert record['auto'] is False
    print('  ok    a detected native manual change suspends AUTO without '
          'overwriting the native value', flush=True)

    print('persistent suspension across separate commands', flush=True)
    before = len(ws.wire())
    message = ws.refuses_phase('--kind', 'review', '--rpc-timeout', '3',
                               '--json')
    assert 'stays suspended' in message
    assert 'NO setter and NO pending automatic write' in message
    assert 'attach auto' in message
    assert ws.wire(after=before) == []
    record = ws.record()
    assert record['auto'] is False and record['pending'] is None
    message = ws.refuses_phase('--kind', 'planning', '--rpc-timeout', '3',
                               '--json')
    assert 'stays suspended' in message
    message = ws.refuses_phase('--effort', 'low', '--rpc-timeout', '3',
                               '--json')
    assert 'stays suspended' in message
    assert ws.wire(after=before) == []
    assert ws.record()['auto'] is False
    print('  ok    a suspended automatic phase stays suspended across '
          'separate commands: repeated kind and explicit signals make '
          'zero settings calls and write no pending automatic request '
          'until the owner re-enables', flush=True)

    payload, _, code = ws.auto()
    assert code == 0 and payload['auto'] is True
    ws.behavior({})
    payload, _, code = ws.phase('--effort', 'xhigh')
    assert code == 0
    calls = ws.settings_calls(ws.wire())
    assert calls[-1]['params']['effort'] == 'xhigh'
    print('  ok    explicit attach auto re-enables control from the '
          'fresh native anchor', flush=True)

    print('a running turn is never relabelled', flush=True)
    before = len(ws.wire())
    ws.behavior({'read_status': 'active'})
    payload, _, code = ws.phase('--effort', 'low', '--rpc-timeout', '3',
                                '--json')
    assert code == 0
    assert payload['pending']['effort'] == 'low'
    assert payload['active_turn'] is True
    delta = ws.wire(after=before)
    assert all(rec.get('method') != 'thread/settings/update' for rec in delta)
    record = ws.record()
    assert record['pending']['effort'] == 'low'
    assert record['effort']['requested'] == 'xhigh'
    payload, _, code = ws.status()
    assert payload['requested']['effort'] == 'xhigh'
    assert payload['pending']['effort'] == 'low'
    assert payload['effective'] == 'Unknown'
    ws.behavior({})
    print('  ok    an active turn records pending separately and changes '
          'no settings', flush=True)

    print('advertisement honesty', flush=True)
    before = len(ws.wire())
    ws.behavior({'models': {MODEL: ['low']}})
    message = ws.refuses_phase('--effort', 'xhigh', '--rpc-timeout', '3',
                               '--json')
    assert 'does not advertise' in message
    assert 'no effort substitution' in message
    assert all(rec.get('method') != 'thread/settings/update'
               for rec in ws.wire(after=before))
    ws.behavior({})
    print('  ok    an unadvertised level refuses with no substitution',
          flush=True)

    ws.behavior({'read_model': None, 'read_effort': 'xhigh'})
    message = ws.refuses_phase('--effort', 'low', '--rpc-timeout', '3',
                               '--json')
    assert 'cannot verify' in message
    ws.behavior({})
    print('  ok    a thread that hides its model cannot verify '
          'advertisement and refuses', flush=True)

    before = len(ws.wire())
    ws.behavior({'loaded': []})
    message = ws.refuses_phase('--effort', 'low', '--rpc-timeout', '3',
                               '--json')
    assert 'no longer loaded' in message
    ws.behavior({})
    print('  ok    a thread unloaded between commands refuses control '
          'without a fallback', flush=True)

    print('typed rejection and uncertain acknowledgement', flush=True)
    reject_ws = Workspace(base)
    reject_ws.attach()
    before = len(reject_ws.wire())
    reject_ws.behavior({'settings': 'reject'})
    payload, _, code = reject_ws.phase('--effort', 'xhigh',
                                       '--rpc-timeout', '3', '--json')
    assert code == 5
    assert payload['requested']['ack'] == 'unavailable'
    assert 'unavailable' in payload['note']
    assert reject_ws.record()['effort']['ack'] == 'unavailable'
    reject_ws.behavior({})
    payload, _, code = reject_ws.phase('--effort', 'xhigh')
    assert code == 0 and payload['requested']['ack'] == 'acknowledged'
    rejected = [entry for entry in reject_ws.journal_entries()
                if entry['kind'] == 'result'
                and entry['ack'] == 'unavailable']
    assert len(rejected) == 1 and rejected[0]['attempt'] == 1
    print('  ok    a typed settings rejection is unavailable (exit 5) and '
          'recovers only through a new explicit signal while its original '
          'rejected receipt stays durably in the journal', flush=True)

    silent_ws = Workspace(base)
    silent_ws.attach()
    before = len(silent_ws.wire())
    silent_ws.behavior({'settings': 'silence'})
    payload, _, code = silent_ws.phase('--effort', 'xhigh',
                                       '--rpc-timeout', '1', '--json')
    assert code == 6
    assert payload['requested']['ack'] == 'uncertain'
    assert 'Unknown' in payload['note']
    delta = silent_ws.wire(after=before)
    assert len(silent_ws.settings_calls(delta)) == 1
    assert silent_ws.record()['effort']['ack'] == 'uncertain'
    print('  ok    an uncertain acknowledgement (timeout) is preserved '
          'once, never retried blindly', flush=True)

    silent_ws.behavior({})
    message = silent_ws.refuses_phase('--effort', 'xhigh',
                                       '--rpc-timeout', '3', '--json')
    assert 'still Unknown' in message and 'attach auto' in message
    payload, _, code = silent_ws.auto()
    assert code == 0
    # Owner re-enable acknowledges AUTHORITY, never delivery: the
    # original uncertain attempt keeps its truthful acknowledgement
    # (this corrects the earlier rewrite-to-acknowledged-by-owner:
    # an unresolved Unknown must not become a successful delivery).
    fresh_record = silent_ws.record()
    assert fresh_record['effort']['ack'] == 'uncertain'
    assert fresh_record['effort']['owner_acknowledged']
    assert fresh_record['effort']['requested'] == 'xhigh'
    payload, _, code = silent_ws.phase('--effort', 'xhigh')
    assert code == 0 and payload['requested']['ack'] == 'acknowledged'
    assert silent_ws.record()['native']['effort'] == 'xhigh'
    # the original uncertain receipt is retained in the journal
    kinds = [entry['kind'] for entry in silent_ws.journal_entries()]
    assert kinds[:2] == ['intent', 'result']
    uncertain_receipts = [entry for entry in silent_ws.journal_entries()
                          if entry['kind'] == 'result'
                          and entry['ack'] == 'uncertain']
    assert len(uncertain_receipts) == 1
    assert uncertain_receipts[0]['attempt'] == 1
    print('  ok    an unresolved uncertain receipt blocks updates until '
          'the owner re-enables explicitly; re-enable acknowledges '
          'authority only and the original uncertain attempt is kept '
          'truthfully with its journal receipt', flush=True)

    print('explicit owner manual override pins automatic selection', flush=True)
    pin_ws = Workspace(base)
    pin_ws.attach()
    before = len(pin_ws.wire())
    payload, _, code = pin_ws.manual('--effort', 'low',
                                     '--reason', 'owner choice')
    assert code == 0
    assert payload['requested']['effort'] == 'low'
    assert payload['requested']['source'] == 'manual'
    assert payload['requested']['ack'] == 'acknowledged'
    assert payload['auto'] is False
    assert payload['owner_pin']['effort'] == 'low'
    calls = pin_ws.settings_calls(pin_ws.wire(after=before))
    assert calls and calls[-1]['params'] == {'threadId': THREAD,
                                             'effort': 'low'}
    record = pin_ws.record()
    assert record['auto'] is False and record['owner_pin']['effort'] == 'low'
    print('  ok    the owner manual override applies one concrete level '
          'and pins/suspends automatic phase selection in one explicit '
          'step', flush=True)

    message = pin_ws.refuses_manual('--effort', 'medium', '--rpc-timeout',
                                    '3', '--json')
    assert 'only low and xhigh' in message
    print('  ok    the owner override exposes exactly low and xhigh with '
          'no substitution', flush=True)

    before = len(pin_ws.wire())
    message = pin_ws.refuses_phase('--kind', 'review', '--rpc-timeout', '3',
                                   '--json')
    assert 'owner manual pin' in message and 'stays suspended' in message
    assert pin_ws.wire(after=before) == []
    message = pin_ws.refuses_phase('--kind', 'coordination', '--rpc-timeout',
                                   '3', '--json')
    assert 'owner manual pin' in message
    message = pin_ws.refuses_phase('--effort', 'low', '--rpc-timeout', '3',
                                   '--json')
    assert 'owner manual pin' in message
    assert pin_ws.wire(after=before) == []
    record = pin_ws.record()
    assert record['auto'] is False and record['pending'] is None
    payload, _, code = pin_ws.status()
    assert code == 0
    assert payload['auto'] is False
    assert payload['owner_pin']['effort'] == 'low'
    print('  ok    the owner pin persists across separate CLI commands: '
          'every automatic phase signal (kind or explicit) refuses with '
          'zero settings calls and no pending automatic write', flush=True)

    pin_ws.behavior({'read_status': 'active'})
    before = len(pin_ws.wire())
    payload, _, code = pin_ws.manual('--effort', 'xhigh', '--rpc-timeout',
                                     '3', '--json')
    assert code == 0 and payload['active_turn'] is True
    assert payload['owner_pin']['effort'] == 'xhigh'
    assert pin_ws.settings_calls(pin_ws.wire(after=before)) == []
    record = pin_ws.record()
    assert record['owner_pin']['effort'] == 'xhigh'
    assert record['pending'] is None and record['auto'] is False
    pin_ws.behavior({})
    payload, _, code = pin_ws.manual('--effort', 'xhigh')
    assert code == 0 and payload['requested']['effort'] == 'xhigh'
    print('  ok    an owner override during a running turn keeps pinning '
          'without relabelling the turn and applies at the next explicit '
          'idle boundary', flush=True)

    payload, _, code = pin_ws.auto()
    assert code == 0 and payload['auto'] is True
    assert payload['owner_pin'] is None
    payload, _, code = pin_ws.phase('--kind', 'review')
    assert code == 0 and payload['requested']['effort'] == 'xhigh'
    print('  ok    `attach auto` lifts the pin and automatic kind phase '
          'selection resumes from the persisted ceiling', flush=True)

    print('the persisted ceiling actually binds automatic selection', flush=True)
    ceil_ws = Workspace(base)
    payload, _, code = ceil_ws.attach(THREAD, '--ceiling', 'low')
    assert code == 0 and payload['ceiling'] == 'low'
    for kind in ('planning', 'review'):
        before = len(ceil_ws.wire())
        payload, _, code = ceil_ws.phase('--kind', kind, '--rpc-timeout',
                                         '3', '--json')
        assert code == 0 and payload['requested']['effort'] == 'low'
        calls = ceil_ws.settings_calls(ceil_ws.wire(after=before))
        assert calls and calls[-1]['params']['effort'] == 'low'
    payload, _, code = ceil_ws.phase('--kind', 'coordination', '--json')
    assert code == 0 and payload['requested']['effort'] == 'low'
    message = ceil_ws.refuses_phase('--effort', 'xhigh', '--rpc-timeout', '3',
                                    '--json')
    assert 'exceeds the configured ceiling low' in message
    print('  ok    attach --ceiling low binds kind planning/review and the '
          'explicit phase signal across separate CLI commands: review '
          'resolves low from the persisted record and never sends xhigh '
          'above the promised bound', flush=True)

    payload, _, code = ceil_ws.manual('--effort', 'xhigh')
    assert code == 0
    assert payload['ceiling_exceeded'] is True
    assert 'exceeds the configured ceiling' in payload['note']
    calls = ceil_ws.settings_calls(ceil_ws.wire())
    assert calls[-1]['params']['effort'] == 'xhigh'
    payload, _, code = ceil_ws.auto()
    assert code == 0
    payload, _, code = ceil_ws.phase('--kind', 'review', '--json')
    assert code == 0 and payload['requested']['effort'] == 'low'
    print('  ok    the explicit owner override is the only path above the '
          'ceiling - reported, never silent - and the ceiling binds again '
          'after the owner re-enables', flush=True)

    message = ceil_ws.refuses_attach('--thread-id', OTHER, '--ceiling',
                                     'low', '--effort', 'xhigh',
                                     '--rpc-timeout', '3', '--json')
    assert 'exceeds the requested ceiling' in message
    print('  ok    an attach request above its own ceiling refuses before '
          'any connection or record', flush=True)

    print('optional initial attach effort is advertisement-checked', flush=True)
    adv_ws = Workspace(base)
    adv_ws.behavior({'models': {MODEL: ['low']}})
    before = len(adv_ws.wire())
    message = adv_ws.refuses_attach('--thread-id', THREAD, '--effort',
                                    'xhigh', '--rpc-timeout', '3',
                                    '--json')
    assert 'does not advertise' in message
    assert 'no effort substitution' in message
    assert adv_ws.settings_calls(adv_ws.wire(after=before)) == []
    assert not adv_ws.has_record(THREAD)
    adv_ws.behavior({})
    payload, _, code = adv_ws.attach(THREAD, '--ceiling', 'low',
                                     '--effort', 'low')
    assert code == 0
    assert payload['requested']['effort'] == 'low'
    assert payload['requested']['ack'] == 'acknowledged'
    entries = adv_ws.journal_entries()
    assert [entry['kind'] for entry in entries] == ['intent', 'result']
    assert entries[0]['source'] == 'attach'
    assert entries[0]['requested'] == 'low'
    assert entries[0]['thread_id'] == THREAD
    assert entries[1]['ack'] == 'acknowledged'
    print('  ok    an unadvertised initial attach effort refuses with zero '
          'settings calls and no record; an advertised one keeps its '
          'full attempt receipt', flush=True)

    print('attempt journal: durable byte-identical receipts', flush=True)
    jr_ws = Workspace(base)
    jr_ws.attach()
    jr_ws.behavior({'settings': 'silence'})
    payload, _, code = jr_ws.phase('--effort', 'xhigh', '--rpc-timeout',
                                   '1', '--json')
    assert code == 6 and payload['requested']['ack'] == 'uncertain'
    original = jr_ws.journal_bytes()
    entries = jr_ws.journal_entries()
    assert [entry['kind'] for entry in entries] == ['intent', 'result']
    assert entries[0]['attempt'] == 1
    assert entries[0]['requested'] == 'xhigh'
    assert entries[0]['thread_id'] == THREAD
    assert entries[0]['source'] == 'phase'
    assert entries[0]['at']
    assert entries[1]['ack'] == 'uncertain'
    print('  ok    an uncertain settings attempt persists its intent '
          'before the RPC and its actual Unknown outcome afterward', flush=True)

    jr_ws.behavior({})
    payload, _, code = jr_ws.auto()
    assert code == 0
    kinds = [entry['kind'] for entry in jr_ws.journal_entries()]
    assert kinds == ['intent', 'result', 'owner-resolution']
    assert jr_ws.journal_bytes().startswith(original)
    assert jr_ws.record()['effort']['ack'] == 'uncertain'
    payload, _, code = jr_ws.phase('--effort', 'xhigh')
    assert code == 0 and payload['requested']['ack'] == 'acknowledged'
    assert jr_ws.journal_bytes().startswith(original)

    jr_ws.behavior({'settings': 'reject'})
    payload, _, code = jr_ws.phase('--effort', 'low', '--rpc-timeout', '3',
                                   '--json')
    assert code == 5 and payload['requested']['ack'] == 'unavailable'
    rejected = jr_ws.journal_bytes()
    jr_ws.behavior({})
    payload, _, code = jr_ws.phase('--effort', 'low')
    assert code == 0 and payload['requested']['ack'] == 'acknowledged'
    assert jr_ws.journal_bytes().startswith(rejected)

    jr_ws.detach()
    payload, _, code = jr_ws.attach()
    assert code == 0
    record = jr_ws.record()
    assert record['effort']['requested'] is None
    assert record['effort']['ack'] is None
    payload, _, code = jr_ws.phase('--effort', 'low')
    assert code == 0
    final = jr_ws.journal_entries()
    attempts = [entry['attempt'] for entry in final
                if entry['kind'] == 'intent']
    assert attempts == [1, 2, 3, 4, 5]
    results = {entry['attempt']: entry['ack'] for entry in final
               if entry['kind'] == 'result'}
    assert results == {1: 'uncertain', 2: 'acknowledged',
                       3: 'unavailable', 4: 'acknowledged',
                       5: 'acknowledged'}
    assert [entry['kind'] for entry in final
            if entry['kind'] == 'owner-resolution']
    assert jr_ws.journal_bytes().startswith(original)
    print('  ok    the original unknown and rejected attempt receipts stay '
          'byte-identical through auto re-enable, later successes, typed '
          'rejection, detach and re-attach; the re-attached record starts '
          'fresh and never inherits delivery', flush=True)

    print('crash-aware receipts: recording failure and dangling attempts',
          flush=True)
    crash_ws = Workspace(base)
    crash_ws.attach()
    crash_ws.journal_path().mkdir()
    before = len(crash_ws.wire())
    message = crash_ws.refuses_phase('--effort', 'xhigh', '--rpc-timeout',
                                     '3', '--json')
    assert crash_ws.settings_calls(crash_ws.wire(after=before)) == []
    record = crash_ws.record()
    assert record['effort']['requested'] is None
    assert record['effort']['ack'] is None
    print('  ok    a settings attempt whose receipt cannot be recorded '
          'refuses safely BEFORE the setter: zero settings calls are '
          'made and the record is unchanged', flush=True)

    dangling_ws = Workspace(base)
    dangling_ws.attach()
    at._journal_append(Path(dangling_ws.root), THREAD, {
        'v': 1, 'kind': 'intent', 'attempt': 1,
        'at': '2026-11-16T00:00:00Z', 'thread_id': THREAD,
        'source': 'phase', 'requested': 'xhigh', 'reason': 'simulated '
        'crash right after the intent receipt'})
    before = len(dangling_ws.wire())
    message = dangling_ws.refuses_phase('--effort', 'low', '--rpc-timeout',
                                        '3', '--json')
    assert 'no completion receipt' in message
    assert 'remains Unknown' in message
    assert dangling_ws.settings_calls(
        dangling_ws.wire(after=before)) == []
    payload, _, code = dangling_ws.auto()
    assert code == 0
    payload, _, code = dangling_ws.phase('--effort', 'low')
    assert code == 0 and payload['requested']['ack'] == 'acknowledged'
    entries = dangling_ws.journal_entries()
    assert [entry['kind'] for entry in entries] == [
        'intent', 'owner-resolution', 'intent', 'result']
    assert [entry['attempt'] for entry in entries
            if entry['kind'] == 'result'] == [2]
    print('  ok    a dangling intent (interrupted run) is never completed '
          'silently: it blocks updates, needs the explicit owner '
          'resolution, and keeps its unresolved receipt untouched', flush=True)

    print('status, detach and STOP interactions', flush=True)
    before = len(ws.wire())
    payload, _, code = ws.status()
    assert code == 0
    assert len(ws.wire(after=before)) == 0
    assert payload['attached'] is True
    assert payload['stop_active'] is False
    assert payload['effective'] == 'Unknown'
    print('  ok    status is a zero-connection local view with the '
          'requested/pending/effective display', flush=True)

    before = len(ws.wire())
    ws.set_stop(True)
    message = ws.refuses_phase('--effort', 'low', '--rpc-timeout', '3',
                               '--json')
    assert 'STOP' in message
    assert len(ws.wire(after=before)) == 0
    payload, _, code = ws.status()
    assert code == 0 and payload['stop_active'] is True
    payload, _, code = ws.detach()
    assert code == 0 and payload['detached'] is True
    record = ws.record()
    assert record['detached'] is True and record['detached_at']
    print('  ok    STOP blocks phase control while status and detach stay '
          'available', flush=True)
    ws.set_stop(False)

    message = ws.refuses_phase('--effort', 'low', '--rpc-timeout', '3',
                               '--json')
    assert 'no active attach record' in message
    payload, _, code = ws.attach()
    assert code == 0
    record = ws.record()
    assert record['detached'] is False and record['auto'] is True
    payload, _, code = ws.phase('--effort', 'low')
    assert code == 0
    print('  ok    after detach, phase refuses until an explicit '
          're-attach; history stays additive', flush=True)

    none_ws = Workspace(base)
    payload, _, code = none_ws.status()
    assert code == 0 and payload['attached'] is False
    assert payload['note']
    print('  ok    status with no record is an honest local answer',
          flush=True)

    print('initial attach persists the FRESH post-apply observation',
          flush=True)
    obs_ws = Workspace(base)
    payload, _, code = obs_ws.attach(THREAD, '--effort', 'xhigh')
    assert code == 0
    record = obs_ws.record()
    assert record['effort']['requested'] == 'xhigh'
    assert record['effort']['ack'] == 'acknowledged'
    # dd570c0 saved the record before observing, so disk kept the stale
    # pre-apply anchor 'medium' while the requested level was xhigh.
    assert record['native']['effort'] == 'xhigh'
    # the fresh anchor keeps later manual-change detection honest: a
    # native return to the old level is now CAUGHT as a manual change.
    obs_ws.behavior({'read_effort': 'medium'})
    message = obs_ws.refuses_phase('--effort', 'xhigh', '--rpc-timeout',
                                   '3', '--json')
    assert 'native manual change detected' in message
    after = obs_ws.record()
    assert after['auto'] is False
    obs_ws.behavior({})
    print('  ok    the post-apply native anchor is observed BEFORE the '
          'record is saved, so a later native manual change back to the '
          'old level is detected instead of missed', flush=True)

    honest_ws = Workspace(base)
    honest_ws.behavior({'read_foreign_id_after_settings': True})
    payload, _, code = honest_ws.attach(THREAD, '--effort', 'xhigh')
    assert code == 0 and payload['requested']['ack'] == 'acknowledged'
    record = honest_ws.record()
    assert record['effort']['requested'] == 'xhigh'
    assert record['effort']['ack'] == 'acknowledged'
    # the post-apply reread failed: uncertainty stays honest - an
    # explicitly Unknown anchor (never the knowingly stale pre-apply
    # 'medium') and the acknowledged delivery fact itself unchanged.
    assert record['native']['effort'] is None
    assert record['native']['updated_at']
    honest_ws.behavior({})
    print('  ok    a failed post-apply reread persists an explicitly '
          'Unknown anchor instead of a knowingly stale pre-apply '
          'effort; the acknowledged delivery fact never changes', flush=True)

    print('a queued pending choice is consumed, never discarded',
          flush=True)
    pend_ws = Workspace(base)
    pend_ws.attach()
    pend_ws.behavior({'read_status': 'active'})
    payload, _, code = pend_ws.phase('--effort', 'xhigh', '--rpc-timeout',
                                     '3', '--json')
    assert code == 0 and payload['active_turn'] is True
    assert payload['pending']['effort'] == 'xhigh'
    # no explicit new choice at a STILL-active boundary keeps the queue
    # (dd570c0 overwrote it with the coordination default low).
    payload, _, code = pend_ws.phase('--rpc-timeout', '3', '--json')
    assert code == 0 and payload['pending']['effort'] == 'xhigh'
    record = pend_ws.record()
    assert record['pending']['effort'] == 'xhigh'
    assert record['effort']['requested'] is None
    # the queued choice is consumed at the idle boundary instead of the
    # coordination default low being applied (the dd570c0 defect).
    pend_ws.behavior({})
    before = len(pend_ws.wire())
    payload, _, code = pend_ws.phase('--rpc-timeout', '3', '--json')
    assert code == 0
    calls = pend_ws.settings_calls(pend_ws.wire(after=before))
    assert calls and calls[-1]['params'] == {'threadId': THREAD,
                                             'effort': 'xhigh'}
    assert payload['requested']['effort'] == 'xhigh'
    assert payload['requested']['ack'] == 'acknowledged'
    assert payload['pending'] is None
    record = pend_ws.record()
    assert record['effort']['requested'] == 'xhigh'
    assert record['pending'] is None
    # an explicit new choice intentionally wins over the queued one
    pend_ws.behavior({'read_status': 'active'})
    payload, _, code = pend_ws.phase('--effort', 'xhigh', '--rpc-timeout',
                                     '3', '--json')
    assert code == 0 and payload['pending']['effort'] == 'xhigh'
    pend_ws.behavior({})
    payload, _, code = pend_ws.phase('--effort', 'low', '--rpc-timeout',
                                     '3', '--json')
    assert code == 0 and payload['requested']['effort'] == 'low'
    assert payload['pending'] is None
    pend_ws.behavior({'read_status': 'active'})
    payload, _, code = pend_ws.phase('--effort', 'xhigh', '--rpc-timeout',
                                     '3', '--json')
    assert code == 0 and payload['pending']['effort'] == 'xhigh'
    pend_ws.behavior({})
    payload, _, code = pend_ws.phase('--kind', 'coordination',
                                     '--rpc-timeout', '3', '--json')
    assert code == 0 and payload['requested']['effort'] == 'low'
    assert payload['pending'] is None
    print('  ok    a queued pending request applies at a later explicit '
          'idle phase command with NO explicit choice (an explicit '
          '--effort or --kind intentionally wins), stays queued at '
          'active boundaries and stays separate from the current '
          'requested level', flush=True)

    # the consumed pending choice revalidates the persisted ceiling at
    # the apply boundary (here a record tampered above its ceiling).
    ceilpend_ws = Workspace(base)
    ceilpend_ws.attach(THREAD, '--ceiling', 'low')
    doc = at._load_record(Path(ceilpend_ws.root), THREAD)
    doc['pending'] = {'effort': 'xhigh',
                      'reason': 'tampered queued request above ceiling',
                      'updated_at': at._now()}
    at._save_record(Path(ceilpend_ws.root), doc)
    before = len(ceilpend_ws.wire())
    message = ceilpend_ws.refuses_phase('--rpc-timeout', '3', '--json')
    assert 'exceeds the configured ceiling low' in message
    assert ceilpend_ws.settings_calls(ceilpend_ws.wire(after=before)) == []
    assert ceilpend_ws.record()['pending']['effort'] == 'xhigh'
    print('  ok    consuming the queue revalidates the persisted '
          'ceiling: a queued level above the ceiling refuses with zero '
          'settings calls and the queue is kept', flush=True)

    # a queued AUTOMATIC choice is never consumed while AUTO is
    # suspended (manual pin or a detected native manual change).
    susp_ws = Workspace(base)
    susp_ws.attach()
    susp_ws.behavior({'read_status': 'active'})
    payload, _, code = susp_ws.phase('--effort', 'xhigh', '--rpc-timeout',
                                     '3', '--json')
    assert code == 0 and payload['pending']['effort'] == 'xhigh'
    susp_ws.behavior({'read_effort': 'low'})
    message = susp_ws.refuses_phase('--rpc-timeout', '3', '--json')
    assert 'native manual change detected' in message
    before = len(susp_ws.wire())
    message = susp_ws.refuses_phase('--rpc-timeout', '3', '--json')
    assert 'stays suspended' in message
    assert susp_ws.settings_calls(susp_ws.wire(after=before)) == []
    record = susp_ws.record()
    assert record['auto'] is False
    assert record['pending']['effort'] == 'xhigh'
    print('  ok    a queued automatic choice is never consumed while '
          'AUTO is suspended by a native manual change: no setter and '
          'no pending automatic write until the explicit re-enable',
          flush=True)

    print('read-only commands never create or change attach state',
          flush=True)
    ro_ws = Workspace(base)
    absent = ro_ws.root / 'coord' / 'lead-session-attach'
    payload, _, code = ro_ws.inspect()
    assert code == 0 and payload['loaded'] is True
    assert not absent.exists()
    payload, _, code = ro_ws.status()
    assert code == 0 and payload['attached'] is False
    assert not absent.exists()
    ro_ws.set_stop(True)
    message = refuses(ro_ws.argv('attach', '--thread-id', THREAD,
                                 '--rpc-timeout', '3', '--json'))
    assert 'STOP' in message
    assert not absent.exists()
    payload, _, code = ro_ws.status()
    assert code == 0 and payload['stop_active'] is True
    payload, _, code = ro_ws.inspect()
    assert code == 0 and payload['stop_active'] is True
    assert not absent.exists()
    ro_ws.set_stop(False)
    message = ro_ws.refuses_phase('--effort', 'xhigh', '--rpc-timeout',
                                  '3', '--json')
    assert 'no active attach record' in message
    message = refuses(['--project', str(ro_ws.root), 'attach', 'auto',
                       '--json'])
    assert 'no active attach record' in message
    message = refuses(['--project', str(ro_ws.root), 'attach', 'detach',
                       '--json'])
    assert 'no active attach record' in message
    assert not absent.exists()
    print('  ok    inspect, status and pre-record refusals keep an '
          'absent attach store absent (including under an active STOP)',
          flush=True)

    ro_ws.attach()
    directory = ro_ws.root / 'coord' / 'lead-session-attach'
    assert directory.is_dir()
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    dir_meta = (stat.S_IMODE(directory.stat().st_mode),
                directory.stat().st_ctime_ns, directory.stat().st_mtime_ns)
    entry_meta = {path.name: (stat.S_IMODE(path.stat().st_mode),
                              path.stat().st_ctime_ns,
                              path.stat().st_mtime_ns)
                  for path in directory.iterdir()}
    payload, _, code = ro_ws.status()
    assert code == 0
    payload, _, code = ro_ws.inspect()
    assert code == 0
    assert (stat.S_IMODE(directory.stat().st_mode),
            directory.stat().st_ctime_ns,
            directory.stat().st_mtime_ns) == dir_meta
    for path in directory.iterdir():
        assert entry_meta[path.name] == (stat.S_IMODE(path.stat().st_mode),
                                         path.stat().st_ctime_ns,
                                         path.stat().st_mtime_ns)
    print('  ok    existing attach state metadata and modes are '
          'unchanged by status and inspect (no chmod, no rewrite)',
          flush=True)

    unsafe_ro = Workspace(base)
    unsafe_ro.attach()
    store = unsafe_ro.root / 'coord' / 'lead-session-attach'
    os.chmod(store, 0o755)
    message = refuses(['--project', str(unsafe_ro.root), 'attach',
                       'status', '--json'])
    assert 'unsafe attach state directory' in message
    os.chmod(store, 0o700)
    print('  ok    a non-private existing store refuses read commands '
          'instead of silently repairing it (fail closed)', flush=True)

    print('the persisted transport selection governs later control',
          flush=True)
    end_ws = Workspace(base)
    saved_sock = end_ws.root / 'fake-control.sock'
    payload, _, code = end_ws.attach(THREAD, '--sock', str(saved_sock))
    assert code == 0
    record = end_ws.record()
    assert record['codex_binary'] == str(end_ws.binary)
    assert record['sock'] == str(saved_sock)
    # omitted later flags CANNOT run the default real codex: the saved
    # endpoint (fake) is re-used (dd570c0 ignored the saved selection).
    before = len(end_ws.wire())
    payload, _, code = invoke(['--project', str(end_ws.root), 'attach',
                               'phase', '--effort', 'xhigh',
                               '--rpc-timeout', '3', '--json'])
    assert code == 0
    calls = end_ws.settings_calls(end_ws.wire(after=before))
    assert calls and calls[-1]['params'] == {'threadId': THREAD,
                                             'effort': 'xhigh'}
    argvs = [rec for rec in end_ws.wire(after=before)
             if rec.get('event') == 'argv']
    assert argvs and argvs[0]['argv'] == [str(end_ws.binary),
                                          'app-server', 'proxy',
                                          '--sock', str(saved_sock)]
    # an explicit conflicting endpoint refuses with ZERO setter calls
    # anywhere: no thread/settings/update runs on either endpoint.
    alt_ws = Workspace(base)
    before_ws = len(end_ws.wire())
    message = refuses(['--project', str(end_ws.root), 'attach', 'phase',
                       '--effort', 'low', '--codex-binary',
                       str(alt_ws.binary), '--rpc-timeout', '3', '--json'])
    assert 'conflicts with the transport selection persisted' in message
    assert 'detach' in message
    message = refuses(['--project', str(end_ws.root), 'attach', 'phase',
                       '--effort', 'low', '--sock',
                       str(alt_ws.root / 'other.sock'),
                       '--rpc-timeout', '3', '--json'])
    assert 'conflicts with the transport selection persisted' in message
    assert end_ws.settings_calls(end_ws.wire(after=before_ws)) == []
    assert alt_ws.wire() == []
    # matching repeated flags stay allowed, and inspect keeps free
    # transport flags (read-only exploration is not record-bound).
    payload, _, code = invoke(['--project', str(end_ws.root), 'attach',
                               'phase', '--effort', 'low',
                               '--codex-binary', str(end_ws.binary),
                               '--sock', str(saved_sock),
                               '--rpc-timeout', '3', '--json'])
    assert code == 0
    before_alt = len(alt_ws.wire())
    payload, _, code = invoke(['--project', str(end_ws.root), 'attach',
                               'inspect', '--thread-id', OTHER,
                               '--codex-binary', str(alt_ws.binary),
                               '--rpc-timeout', '3', '--json'])
    assert code == 0 and payload['thread_id'] == OTHER
    assert alt_ws.wire(after=before_alt)
    print('  ok    later control re-uses the endpoint saved at attach '
          '(omitted flags can never run a default real codex or a '
          'different implicit daemon), an explicit conflicting endpoint '
          'refuses with zero settings calls until the owner detaches '
          'and re-attaches, matching repeated flags stay allowed and '
          'inspect keeps free transport flags', flush=True)

    print('human and JSON displays', flush=True)
    human_ws = Workspace(base)
    _, text, code = invoke(['--project', str(human_ws.root), 'attach',
                            'inspect', '--thread-id', THREAD,
                            '--codex-binary', str(human_ws.binary),
                            '--rpc-timeout', '3'])
    assert code == 0 and 'loaded' in text and 'idle' in text
    human_ws.attach()
    _, text, code = invoke(['--project', str(human_ws.root), 'attach',
                            'status'])
    assert code == 0 and 'requested' in text and 'Unknown' in text
    _, text, code = invoke(['--project', str(human_ws.root), 'attach',
                            'phase', '--effort', 'xhigh',
                            '--codex-binary', str(human_ws.binary),
                            '--rpc-timeout', '3'])
    assert code == 0 and 'future turns' in text
    print('  ok    human output keeps the requested/pending/Unknown '
          'wording', flush=True)

    print('wire safety across the whole suite', flush=True)
    forbidden = {'thread/start', 'thread/fork', 'thread/resume',
                 'turn/start', 'turn/steer', 'turn/interrupt',
                 'config/value/write', 'config/batch/write',
                 'account/read', 'account/session/switch'}
    permitted = {'initialize', 'thread/loaded/list', 'thread/read',
                 'model/list', 'thread/settings/update'}
    for space in (ws, fresh, adm, owner_ws, reject_ws, silent_ws,
                  human_ws, empty_ws, none_ws, pin_ws, ceil_ws, adv_ws,
                  jr_ws, crash_ws, dangling_ws, obs_ws, honest_ws,
                  pend_ws, ceilpend_ws, susp_ws, ro_ws, unsafe_ro,
                  end_ws, alt_ws):
        names = space.rpc_names(space.wire())
        assert not (set(names) & forbidden), set(names) & forbidden
        assert set(names) <= permitted, set(names) - permitted
        for rec in space.settings_calls(space.wire()):
            assert rec['params'] == {'threadId': rec['params']['threadId'],
                                      'effort': rec['params']['effort']}
    print('  ok    only permitted read and settings RPCs ever cross the '
          'wire; settings params are always exactly threadId+effort',
          flush=True)

    print('state containment and permissions', flush=True)
    directory = ws.root / 'coord' / 'lead-session-attach'
    assert directory.is_dir()
    assert stat.S_IMODE(directory.stat().st_mode) == 0o700
    records = 0
    journals = 0
    for item in directory.iterdir():
        assert stat.S_IMODE(item.stat().st_mode) == 0o600, (
            item.name, oct(stat.S_IMODE(item.stat().st_mode)))
        if item.name.endswith('.json'):
            doc = json.loads(item.read_text())
            at._validate_record(doc)
            records += 1
        elif item.name.endswith('.jsonl'):
            # The attempt journal is part of the additive attach state:
            # every durable receipt line is validated, never truncated.
            for entry in ws.journal_entries():
                at._validate_journal_entry(entry, item.name)
            journals += 1
        else:
            assert item.name == 'attach.lock', item.name
    assert records == 1, records
    assert journals == 1, journals
    print('  ok    attach state is separate, private, additive and valid '
          '(records and the attempt journal together)',
          flush=True)

    print('the fake daemon survived every command (only the proxy is '
          'killed)', flush=True)
    payload, _, code = ws.inspect()
    assert code == 0 and payload['loaded'] is True
    print('  ok    the shared daemon is never stopped, restarted or '
          'signalled', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='lead-attach-') as base:
        run_suite(base)
    print()
    print('all existing-session attach checks passed')


if __name__ == '__main__':
    main()
