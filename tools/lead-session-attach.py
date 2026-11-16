#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Shared-daemon attach connector for the native lead-session CLI.

Experimental component of contract 0533-EXISTING-SESSION-ATTACH. Unlike
``lead-session-codex.py`` (which owns ONE NEW app-server process per
command), this connector attaches READ-ONLY metadata/control access to
the CURRENTLY RUNNING shared Codex app-server daemon: it spawns only
its own ``codex app-server proxy`` child (a raw stdio<->unix-socket byte
pump), never starts, restarts, updates or stops the daemon, and closes
ONLY that proxy process group.

Transport provenance (openai/codex rust-v0.169.0, verified live on
2026-11-16 with bounded zero-inference probes; see changelog
0533-EXISTING-SESSION-ATTACH):
- ``codex-rs/stdio-to-uds/src/lib.rs`` — the proxy relays raw bytes
  between stdio and the app-server control socket; it performs NO
  protocol handshake on the client's behalf;
- ``app-server-transport/src/transport/unix_socket.rs`` — the control
  socket accepts ONLY a websocket (HTTP ``Upgrade`` handshake over the
  unix stream via ``accept_hdr_async_with_config``), so plain
  newline-delimited JSON never completes the handshake and stays
  silently unanswered (diagnosed live, receipt preserved);
- ``app-server-transport/src/transport/websocket.rs`` — after the
  upgrade the app-server speaks one JSON-RPC message per websocket TEXT
  frame (``forward_incoming_message`` parses each frame payload as ONE
  ``JSONRPCMessage``).

So this connector implements the minimal RFC 6455 client surface on top
of the proxy's stdio: HTTP/1.1 ``Upgrade`` request, verification of the
server's ``101``+``Sec-WebSocket-Accept`` response, masked client TEXT
frames out, unmasked server frames in (with ping answered by pong and
fragment reassembly), all under bounded reads/writes/time/messages.

Enforced by this component:
- only the exact thread id supplied by the owner is inspected or
  controlled; anything missing, malformed or foreign refuses — no
  fallback thread, no adoption of a different conversation;
- ``inspect`` is read-only metadata: ``initialize``, the daemon's
  loaded-thread list and one ``thread/read`` of the exact ALREADY LOADED
  thread with ``includeTurns: False`` (never turn payload, never full
  history, never pagination of history); a thread absent from the
  loaded list is reported honestly as not loaded — this code NEVER
  calls ``thread/resume``, ``thread/start``, ``thread/fork``,
  ``turn/start``, ``turn/steer`` or ``turn/interrupt``, and NEVER writes
  global config; effective effort/model stay Unknown everywhere;
- the ONLY control RPC is ``thread/settings/update`` with EXACTLY the
  params ``threadId`` and ``effort`` and nothing else: the native model,
  service tier, sandbox, permissions and cwd are never set or changed
  through this connector; the change applies to FUTURE turns only (the
  daemon applies it to the thread's configured effort, which the TUI's
  ``settings.rs`` consumes into its local state — never to a running
  turn; a busy thread is never relabelled, the request is recorded as
  pending and applied only at a later explicit idle command);
- native manual changes win: before applying, the freshly read native
  effort is compared with this record's last acknowledged request and
  last observation; a mismatch means a native manual change (for example
  the owner's own ``/model --reasoning`` in the TUI) and the connector
  suspends AUTO control and refuses to overwrite it; only the explicit
  ``attach auto`` command re-enables control;
- an acknowledged-because-typed-rejection setter is recorded as
  ``unavailable`` and an uncertain (timeout/exit) acknowledgement as
  ``uncertain`` — the receipt is always preserved, never silently
  retried; a still-Unknown acknowledgement blocks further updates until
  the native reading resolves it or the owner re-enables explicitly;
- admission uses the SAME policy controller as the owned path
  (``lead-session-policy.py``): project STOP, off holds, the configured
  registered lead's real account group mapping, native slot counting
  (the lead is counted exactly once) and the owned lead lease are
  enforced before any proxy process is spawned, for ``attach`` and every
  mutating control; read-only ``inspect`` reports an active STOP instead
  of enforcing it;
- the attach record store is strictly additive and separate
  (``coord/lead-session-attach/``): historical managed-owned session
  state under ``coord/lead-effort/`` is never read into control
  decisions beyond the owner-replacement refusal and never rewritten;
- no auth-store or account reads happen through the attach connection:
  the daemon's own authentication is untouched and Unknown to this
  connector; an attached record stores only requested efforts, native
  observations, acknowledgements and timestamps.

Not claimed (follow-ups remain open): no continuous manual-change
monitoring while no command is connected; no per-turn phase
classification or worker watching (control happens only on explicit
``attach phase`` signals); no turn, item or history delivery; the
owner's manual TUI turns are not Unio-admitted turns.
"""
import base64
import contextlib
import hashlib
import json
import os
import select
import signal
import subprocess
import time

RPC_TIMEOUT = 8.0
HEAD_BOUND = 8192
WIRE_BOUND = 2 * 1024 * 1024
READ_CHUNK = 65536
PAGES_BOUND = 16
PAGE_SIZE = 100
LOADED_IDS_BOUND = 4096
MESSAGES_PER_RPC_BOUND = 4096
STDERR_CAPTURE_BOUND = 8 * 1024
STDERR_TAIL_BOUND = 512
STDERR_DRAIN_GRACE = 0.05
ERROR_MESSAGE_BOUND = 256
WS_GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
ACCOUNT_CAUTION = ('attach connection metadata only; no account reads; the '
                   'daemon\'s authentication is untouched')
ROUTE_DEFAULT = 'codex-app-server'
CAUTION = ('requested effort only, for future turns; the effective provider '
           'effort remains Unknown; the owner TUI keeps full manual control')

ml = pe = lp = cx = None


def bind(managed_lead, lead_effort, lead_policy, owned_connection):
    """Inject the already-loaded sibling modules.

    The CLI (``tools/lead-session.py``) loads every component itself so
    exactly one instance of each module exists: exceptions raised here
    are the same class objects the CLI catches, and the shared constants
    (efforts, kinds, id bounds) have a single source of truth.
    """
    global ml, pe, lp, cx
    ml, pe, lp, cx = (managed_lead, lead_effort, lead_policy,
                      owned_connection)


class Refusal(Exception):
    """A controlled attach connector refusal; the original error is kept."""


class ProviderRejected(Refusal):
    """Typed explicit provider rejection of one attach RPC call."""


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _bounded(value, bound, name):
    if (not isinstance(value, str) or not value or '\x00' in value
            or len(value.encode('utf-8', 'replace')) > bound):
        raise Refusal('invalid ' + name)
    return value


def _bounded_reason(value):
    if value is None:
        return ''
    if (not isinstance(value, str) or '\x00' in value
            or len(value.encode('utf-8', 'replace')) > pe.REASON_BOUND):
        raise Refusal('invalid reason')
    return value


class AttachConnection:
    """One owned ``codex app-server proxy`` child speaking websocket to
    the running shared daemon.

    Owns and closes ONLY this proxy process group; the daemon, its
    other clients and the owner TUI are never signalled or killed.
    """

    def __init__(self, binary, *, sock=None, rpc_timeout=RPC_TIMEOUT):
        _bounded(binary, 1024, 'codex binary')
        if sock is not None:
            _bounded(sock, 1024, 'control socket path')
        if type(rpc_timeout) is not float or not 0.1 <= rpc_timeout <= 600.0:
            raise Refusal('invalid attach rpc timeout')
        self._rpc_timeout = rpc_timeout
        self.on_notification = None
        self._buffer = b''
        self._counter = 0
        self._closed = False
        self._eof = False
        self._handshake_done = False
        self._stderr_tail = b''
        self._stderr_eof = False
        command = [binary, 'app-server', 'proxy']
        if sock:
            command += ['--sock', sock]
        try:
            self._child = subprocess.Popen(
                command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True)
        except OSError as exc:
            raise Refusal('attach proxy failed: %s: %s'
                          % (type(exc).__name__, exc)) from exc

    # -- stdio plumbing ------------------------------------------------

    def _send_raw(self, data):
        try:
            self._child.stdin.write(data)
            self._child.stdin.flush()
        except (OSError, ValueError) as exc:
            raise Refusal('attach proxy write failed: %s' % exc) from exc

    def _watch(self):
        watch = [self._child.stdout]
        if not self._stderr_eof:
            watch.append(self._child.stderr)
        return watch

    def _pump_stderr(self, timeout):
        if self._stderr_eof:
            return
        while True:
            try:
                ready, _, _ = select.select([self._child.stderr], [], [],
                                            timeout)
            except OSError:
                return
            if not ready:
                return
            try:
                data = os.read(self._child.stderr.fileno(), READ_CHUNK)
            except OSError:
                return
            if not data:
                self._stderr_eof = True
                return
            self._stderr_tail = (self._stderr_tail
                                 + data)[-STDERR_CAPTURE_BOUND:]
            timeout = 0.0

    def _stderr_note(self):
        if not self._stderr_tail:
            return ''
        tail = self._stderr_tail[-STDERR_TAIL_BOUND:]
        return '; proxy stderr: ' + tail.decode('utf-8', 'replace')

    def _read_bytes(self, deadline, count):
        """Read exactly ``count`` more stdout bytes, bounded in time."""
        while len(self._buffer) < count:
            if time.monotonic() >= deadline:
                raise Refusal('attach rpc timeout')
            ready, _, _ = select.select(self._watch(), [], [],
                                        min(.2, max(0.0, deadline
                                                    - time.monotonic())))
            if not ready:
                continue
            if self._child.stderr in ready:
                self._pump_stderr(0.0)
            if self._child.stdout not in ready:
                continue
            data = os.read(self._child.stdout.fileno(), READ_CHUNK)
            if not data:
                self._eof = True
                self._pump_stderr(STDERR_DRAIN_GRACE)
                raise Refusal('attach proxy exited before the handshake '
                              'completed; the shared daemon is not reachable '
                              'through this transport' + self._stderr_note())
            self._buffer += data
            if len(self._buffer) > WIRE_BOUND:
                raise Refusal('attach message bound exceeded')

    # -- websocket client framing (RFC 6455 over the proxy byte pipe) ---

    def _handshake(self):
        key = base64.b64encode(os.urandom(16)).decode('ascii')
        request = ('GET / HTTP/1.1\r\nHost: localhost\r\n'
                   'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                   'Sec-WebSocket-Key: ' + key + '\r\n'
                   'Sec-WebSocket-Version: 13\r\n\r\n')
        self._send_raw(request.encode('ascii'))
        deadline = time.monotonic() + max(5.0, self._rpc_timeout)
        while b'\r\n\r\n' not in self._buffer:
            self._read_bytes(deadline, len(self._buffer) + 1)
            if len(self._buffer) > HEAD_BOUND:
                raise Refusal('attach handshake head bound exceeded')
        head, self._buffer = self._buffer.split(b'\r\n\r\n', 1)
        lines = head.split(b'\r\n')
        try:
            first = lines[0].decode('ascii', 'replace')
        except (ValueError, UnicodeError):
            first = ''
        if not first.startswith('HTTP/1.1 101'):
            raise Refusal('the control socket refused the websocket upgrade '
                          '(status %r); the shared daemon control transport '
                          'is unavailable' % first[:64])
        expected = base64.b64encode(hashlib.sha1(
            (key + WS_GUID).encode('ascii')).digest()).decode('ascii')
        accept = None
        for line in lines[1:]:
            name, _, value = line.partition(b':')
            if name.strip().lower() == b'sec-websocket-accept':
                accept = value.strip().decode('ascii', 'replace')
        if accept != expected:
            raise Refusal('the control socket websocket handshake is '
                          'unverifiable; refusing to continue')
        self._handshake_done = True

    def _send_frame(self, opcode, payload, mask=True):
        header = bytearray([0x80 | opcode])
        length = len(payload)
        mask_bit = 0x80 if mask else 0x00
        if length < 126:
            header.append(mask_bit | length)
        elif length < 65536:
            header.append(mask_bit | 126)
            header += length.to_bytes(2, 'big')
        else:
            header.append(mask_bit | 127)
            header += length.to_bytes(8, 'big')
        if mask:
            mark = os.urandom(4)
            header += mark
            payload = bytes(byte ^ mark[index % 4]
                            for index, byte in enumerate(payload))
        self._send_raw(bytes(header) + payload)

    def _read_frame(self, deadline):
        """Read one complete server websocket frame (bounded)."""
        self._read_bytes(deadline, 2)
        first, second = self._buffer[0], self._buffer[1]
        opcode = first & 0x0f
        fin = bool(first & 0x80)
        masked = bool(second & 0x80)
        length = second & 0x7f
        offset = 2
        if length == 126:
            self._read_bytes(deadline, 4)
            length = int.from_bytes(self._buffer[2:4], 'big')
            offset = 4
        elif length == 127:
            self._read_bytes(deadline, 10)
            length = int.from_bytes(self._buffer[2:10], 'big')
            offset = 10
        if length > WIRE_BOUND:
            raise Refusal('attach message bound exceeded')
        total = offset + length + (4 if masked else 0)
        self._read_bytes(deadline, total)
        mark = b''
        if masked:
            mark = self._buffer[offset:offset + 4]
            offset += 4
            payload = bytes(byte ^ mark[index % 4]
                            for index, byte
                            in enumerate(self._buffer[offset:offset + length]))
        else:
            payload = self._buffer[offset:offset + length]
        self._buffer = self._buffer[total:]
        return fin, opcode, payload

    def _recv_message(self, deadline):
        """One complete JSON-RPC message, answering control frames inline."""
        routed = 0
        payload = b''
        message_opcode = None
        while True:
            fin, opcode, data = self._read_frame(deadline)
            if opcode == 0x8:  # close
                raise Refusal('the shared daemon closed the attach '
                              'connection' + self._stderr_note())
            if opcode == 0x9:  # ping
                self._send_frame(0xA, data, mask=True)
                routed += 1
            elif opcode == 0xA:  # pong
                routed += 1
            elif opcode in (0x1, 0x2, 0x0):
                if opcode != 0x0:
                    message_opcode = opcode
                payload += data
                if len(payload) > WIRE_BOUND:
                    raise Refusal('attach message bound exceeded')
                if fin:
                    if message_opcode == 0x2:  # binary: only negotiated
                        raise Refusal('unexpected binary frame on the '
                                      'uncompressed attach connection')
                    return payload.decode('utf-8', 'replace')
            else:
                raise Refusal('unsupported attach websocket frame opcode')
            routed += 1
            if routed > MESSAGES_PER_RPC_BOUND:
                raise Refusal('attach control message bound exceeded')

    def _route(self, msg):
        if msg.get('method') is not None and self.on_notification is not None:
            self.on_notification(msg)
        if 'id' in msg and msg.get('method'):
            # Noninteractive attach client: never auto-approve provider
            # requests routed through the shared daemon.
            self._send_frame(0x1, json.dumps({
                'id': msg['id'],
                'error': {'code': -32601,
                          'message': 'Noninteractive attach client request '
                                     'unsupported'}}).encode('utf-8'), True)

    def rpc(self, method, params):
        """One id-correlated attach RPC over a websocket TEXT frame."""
        if not self._handshake_done:
            self._handshake()
        self._counter += 1
        request_id = self._counter
        payload = json.dumps({'id': request_id, 'method': method,
                              'params': params}).encode('utf-8')
        self._send_frame(0x1, payload, mask=True)
        deadline = time.monotonic() + self._rpc_timeout
        for _ in range(MESSAGES_PER_RPC_BOUND):
            msg = self._recv_message(deadline)
            try:
                doc = json.loads(msg)
            except (ValueError, UnicodeError, RecursionError) as exc:
                raise Refusal('invalid attach message') from exc
            if (not isinstance(doc, dict)
                    or ('method' in doc
                        and (not isinstance(doc['method'], str)
                             or not isinstance(doc.get('params', {}),
                                              dict)))):
                raise Refusal('invalid attach message')
            if doc.get('id') == request_id and 'method' not in doc:
                if 'error' in doc:
                    raise self._rejection_error(method, doc['error'])
                return doc.get('result', {})
            self._route(doc)
        raise Refusal('attach message bound exceeded')

    def notify(self, method, params):
        """One client notification frame (fire and forget)."""
        if not self._handshake_done:
            self._handshake()
        payload = json.dumps({'method': method, 'params': params})
        self._send_frame(0x1, payload.encode('utf-8'), mask=True)

    @staticmethod
    def _rejection_error(method, error):
        code = None
        message = ''
        if isinstance(error, dict):
            if isinstance(error.get('code'), int):
                code = error['code']
            if isinstance(error.get('message'), str):
                message = error['message'].replace('\x00', '')
        if len(message) > ERROR_MESSAGE_BOUND:
            message = message[:ERROR_MESSAGE_BOUND]
        return ProviderRejected('the shared daemon rejected %s (code %s): %s'
                               % (method, code, message))

    # -- bounded attach operations --------------------------------------

    def initialize(self):
        """Initialize the attach connection (no account reads, ever)."""
        self.rpc('initialize', {'clientInfo': {'name': 'unio-lead-session-'
                                                'attach', 'version': '1'},
                                'capabilities': {'experimentalApi': True}})
        self.notify('initialized', {})

    def loaded_thread_ids(self):
        """The daemon's currently loaded thread ids (metadata only)."""
        ids = []
        cursor = None
        for _ in range(PAGES_BOUND):
            reply = self.rpc('thread/loaded/list',
                             {'cursor': cursor, 'limit': PAGE_SIZE})
            data = reply.get('data') if isinstance(reply, dict) else None
            if not isinstance(data, list):
                raise Refusal('thread/loaded/list acknowledgement missing '
                              'or malformed')
            for item in data:
                if (not isinstance(item, str) or not item
                        or len(item.encode('utf-8', 'replace')) > cx.ID_BOUND):
                    raise Refusal('thread/loaded/list returned an invalid '
                                  'thread id')
                ids.append(item)
                if len(ids) > LOADED_IDS_BOUND:
                    raise Refusal('thread/loaded/list bound exceeded')
            cursor = (reply.get('nextCursor')
                      if isinstance(reply, dict) else None)
            if not cursor:
                return ids
        raise Refusal('thread/loaded/list pagination bound exceeded')

    def read_loaded_thread(self, thread_id):
        """Read ONE already-loaded thread's control surface (no turns).

        ``includeTurns`` is always False: history payload, turn listing
        and pagination are never requested. The acknowledgement must
        carry the EXACT requested thread id; anything foreign refuses.
        """
        _bounded(thread_id, cx.ID_BOUND, 'thread id')
        reply = self.rpc('thread/read', {'threadId': thread_id,
                                         'includeTurns': False})
        thread = reply.get('thread') if isinstance(reply, dict) else None
        if not isinstance(thread, dict):
            raise Refusal('thread/read acknowledgement missing or malformed')
        if thread.get('id') != thread_id:
            raise Refusal('thread/read acknowledgement foreign; no fallback '
                          'thread')
        status = thread.get('status')
        status_type = (status.get('type')
                       if isinstance(status, dict) else None)
        if status_type not in ('idle', 'active', 'notLoaded', 'systemError'):
            raise Refusal('thread/read returned an unknown thread status')
        effort = thread.get('reasoningEffort')
        if effort is not None:
            try:
                _bounded(effort, 32, 'native reasoning effort')
            except Refusal as exc:
                raise Refusal('thread/read returned an invalid native '
                              'reasoning effort') from exc
        model = thread.get('model')
        if model is not None:
            try:
                _bounded(model, 128, 'native model')
            except Refusal as exc:
                raise Refusal('thread/read returned an invalid native '
                              'model') from exc
        return {'status_type': status_type, 'reasoning_effort': effort,
                'model': model}

    def read_model_efforts(self, model):
        """Advertised reasoning efforts for the thread's model (read-only)."""
        _bounded(model, 128, 'model')
        cursor = None
        for _ in range(PAGES_BOUND):
            catalog = self.rpc('model/list', {'cursor': cursor,
                                               'limit': PAGE_SIZE})
            data = catalog.get('data') if isinstance(catalog, dict) else None
            for entry in data or []:
                if (isinstance(entry, dict)
                        and (entry.get('model') == model
                             or entry.get('id') == model)):
                    efforts = []
                    for opt in entry.get('supportedReasoningEfforts') or []:
                        if (isinstance(opt, dict)
                                and isinstance(opt.get('reasoningEffort'),
                                               str)):
                            efforts.append(opt['reasoningEffort'])
                    return efforts
            cursor = (catalog.get('nextCursor')
                      if isinstance(catalog, dict) else None)
            if not cursor:
                break
        raise Refusal('the thread\'s model is not advertised by the shared '
                      'daemon: ' + model)

    def update_thread_effort(self, thread_id, effort):
        """Set the thread's effort for FUTURE turns; nothing else.

        The params are EXACTLY ``threadId`` and ``effort``: the native
        model, service tier, sandbox, permissions, cwd and every other
        field stay untouched. A typed provider rejection raises
        ``ProviderRejected``; a timeout or exit raises ``Refusal`` and
        the caller MUST treat that acknowledgement as uncertain — it
        may or may not have landed; never retry blindly.
        """
        _bounded(thread_id, cx.ID_BOUND, 'thread id')
        _bounded(effort, 32, 'effort')
        self.rpc('thread/settings/update', {'threadId': thread_id,
                                             'effort': effort})
        return True

    @property
    def exited(self):
        return self._eof

    def close(self):
        """Terminate ONLY this owned proxy process group; never raises.

        The shared daemon and the owner TUI are never touched: closing
        the proxy removes this connector only and cannot interrupt a
        running owner turn or session.
        """
        if self._closed:
            return
        self._closed = True
        child = getattr(self, '_child', None)
        if child is None:
            return
        try:
            os.killpg(child.pid, signal.SIGTERM)
            deadline = time.monotonic() + .2
            while time.monotonic() < deadline:
                time.sleep(.01)
            os.killpg(child.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        finally:
            try:
                child.wait()
            except OSError:
                pass
        for stream in (child.stdin, child.stdout, child.stderr):
            try:
                stream.close()
            except (OSError, ValueError):
                pass


# -- attach record store (strictly additive, separate directory) -------

RECORD_KEYS = frozenset(('schema_version', 'thread_id', 'workspace', 'route',
                         'codex_binary', 'sock', 'ceiling', 'auto', 'effort',
                         'native', 'pending', 'created_at', 'updated_at',
                         'detached', 'detached_at'))
EFFORT_KEYS = frozenset(('requested', 'source', 'ack', 'updated_at'))
NATIVE_KEYS = frozenset(('effort', 'updated_at'))
PENDING_KEYS = frozenset(('effort', 'reason', 'updated_at'))
ACKS = ('acknowledged', 'unavailable', 'uncertain',
        'acknowledged-by-owner')
SOURCES = ('attach', 'phase')
STATE_BOUND = 65536


def _attach_dir(root):
    path = ml.safe_path(root / 'coord' / 'lead-session-attach')
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    except OSError as exc:
        raise Refusal('attach state directory unavailable') from exc
    return path


def _record_name(thread_id):
    digest = hashlib.sha256(thread_id.encode('utf-8')).hexdigest()
    return 'attach-' + digest[:32] + '.json'


def _record_path(root, thread_id):
    return _attach_dir(root) / _record_name(thread_id)


def _validate_record(doc):
    def refuse():
        raise Refusal('invalid attach record')

    if not isinstance(doc, dict) or set(doc) != RECORD_KEYS:
        refuse()
    if doc.get('schema_version') != 1:
        refuse()
    bounds = {'thread_id': cx.ID_BOUND, 'workspace': 1024,
              'route': 256, 'codex_binary': 1024,
              'created_at': 32, 'updated_at': 32}
    for key, bound in bounds.items():
        try:
            _bounded(doc.get(key), bound, key)
        except Refusal:
            refuse()
    if doc['route'] != ROUTE_DEFAULT:
        refuse()
    if doc['ceiling'] not in pe.INTERFACE_EFFORTS:
        refuse()
    if type(doc.get('auto')) is not bool or type(doc.get('detached')) is not bool:
        refuse()
    if not isinstance(doc.get('sock'), str) or len(doc.get('sock', '')) > 1024:
        refuse()
    effort = doc.get('effort')
    if not isinstance(effort, dict) or set(effort) != EFFORT_KEYS:
        refuse()
    if effort['requested'] is not None:
        if effort['requested'] not in pe.INTERFACE_EFFORTS:
            refuse()
        if effort['source'] not in SOURCES:
            refuse()
        if effort['ack'] not in ACKS:
            refuse()
        if not isinstance(effort['updated_at'], str):
            refuse()
    elif effort['source'] is not None or effort['ack'] is not None:
        refuse()
    native = doc.get('native')
    if not isinstance(native, dict) or set(native) != NATIVE_KEYS:
        refuse()
    if native['effort'] is not None:
        try:
            _bounded(native['effort'], 32, 'native reasoning effort')
        except Refusal:
            refuse()
    if not isinstance(native['updated_at'], str):
        refuse()
    pending = doc.get('pending')
    if pending is not None:
        if not isinstance(pending, dict) or set(pending) != PENDING_KEYS:
            refuse()
        if pending['effort'] not in pe.INTERFACE_EFFORTS:
            refuse()
        if (not isinstance(pending['reason'], str)
                or len(pending['reason']) > pe.REASON_BOUND
                or not isinstance(pending['updated_at'], str)):
            refuse()
    if doc['detached'] and not isinstance(doc.get('detached_at'), str):
        refuse()
    if not doc['detached'] and doc.get('detached_at') is not None:
        refuse()
    return doc


def _load_record(root, thread_id):
    path = _record_path(root, thread_id)
    if not path.exists():
        return None
    data = ml._read_owned_file(path, STATE_BOUND)
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal('invalid attach record')
    _validate_record(doc)
    return doc


def _save_record(root, doc):
    _validate_record(doc)
    doc['updated_at'] = _now()
    data = json.dumps(doc, ensure_ascii=False).encode('utf-8')
    if len(data) > STATE_BOUND:
        raise Refusal('attach record bound exceeded')
    ml._atomic_write(_record_path(root, doc['thread_id']), data)


def _active_records(root):
    """Active (not detached) attach records; fail closed on unsafe state."""
    directory = _attach_dir(root)
    records = []
    try:
        names = sorted(os.listdir(directory))
    except OSError as exc:
        raise Refusal('attach state directory unavailable') from exc
    for name in names:
        if len(name.split('.')) > 2:  # <name>.json only; ignore tmp files
            continue
        if not name.startswith('attach-') or not name.endswith('.json'):
            continue
        path = directory / name
        if os.path.islink(path):
            raise Refusal('refusing unsafe attach record (symlink): ' + name)
        data = ml._read_owned_file(path, STATE_BOUND)
        try:
            doc = json.loads(data)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise Refusal('invalid attach record: ' + name) from exc
        _validate_record(doc)
        if not doc['detached']:
            records.append(doc)
        if len(records) > 64:
            raise Refusal('attach record bound exceeded')
    return records


def _find_record(root, thread_id=None):
    """The one active record (optionally by exact thread id)."""
    if thread_id is not None:
        _bounded(thread_id, cx.ID_BOUND, 'thread id')
        record = _load_record(root, thread_id)
        if record is None or record['detached']:
            return None
        return record
    records = _active_records(root)
    if not records:
        return None
    if len(records) > 1:
        raise Refusal('multiple active attach records exist; pass the exact '
                      '--thread-id to select one')
    return records[0]


def _refuse_active_managed_owner(root):
    """Fail-closed refusal while an UNSTOPPED managed owner lead exists.

    The attach path never manages two leads at once and never rewrites
    the owned session's records: an active (not stopped) managed owner
    session under ``coord/lead-effort`` means the workspace lead budget
    is already represented by an owned lead, so attaching refuses. An
    unreadable or unknown owner record also refuses — nothing is reset.
    """
    owner_path = root / 'coord' / 'lead-effort' / 'owner.json'
    if not owner_path.exists():
        return
    try:
        data = ml._read_owned_file(ml.safe_path(owner_path), 4096)
        doc = json.loads(data)
    except Exception as exc:
        raise Refusal('the managed lead owner record is unreadable; refusing '
                      'to attach alongside it (%s)' % exc) from exc
    if (not isinstance(doc, dict) or not isinstance(doc.get('session_id'),
                                                    str)):
        raise Refusal('invalid managed lead owner record; refusing to '
                      'attach alongside it')
    sid = doc['session_id']
    state_path = root / 'coord' / 'lead-effort' / (sid + '.json')
    if not state_path.exists():
        raise Refusal('the managed lead owner session %s has no control '
                      'state; refusing to attach alongside it' % sid[:12])
    try:
        data = ml._read_owned_file(ml.safe_path(state_path),
                                   ml.STATE_BOUND)
        state = json.loads(data)
    except Exception as exc:
        raise Refusal('the managed lead owner state %s is unreadable; '
                      'refusing to attach alongside it' % sid[:12]) from exc
    if not isinstance(state, dict):
        raise Refusal('invalid managed lead owner state; refusing to attach')
    stopped = state.get('stopped')
    if stopped is not True:
        raise Refusal('workspace already has an active managed owned lead '
                      'session (%s); stop it before attaching to the shared '
                      'daemon' % sid[:12])


@contextlib.contextmanager
def _record_guard(root):
    """Short attach record transaction lock; never held across RPCs."""
    fd = ml._acquire_lock(_attach_dir(root) / 'attach.lock')
    try:
        yield
    finally:
        os.close(fd)


def _record_view(record):
    """A truthful HTTP-friendly whitelisted record view."""
    return {
        'thread_id': record['thread_id'],
        'route': record['route'],
        'ceiling': record['ceiling'],
        'auto': record['auto'],
        'detached': record['detached'],
        'requested': {
            'effort': record['effort']['requested'],
            'source': record['effort']['source'],
            'ack': record['effort']['ack'],
            'updated_at': record['effort']['updated_at'],
        },
        'pending': dict(record['pending']) if record['pending'] else None,
        'native_observed': {
            'effort': record['native']['effort'],
            'observed_at': record['native']['updated_at'],
        },
        'created_at': record['created_at'],
        'updated_at': record['updated_at'],
        'effective': 'Unknown',
        'caution': CAUTION,
    }


def _emit(args, payload, human, exit_code=0):
    if getattr(args, 'json', False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(human)
    return exit_code


def _connect(args):
    rpc_timeout = getattr(args, 'rpc_timeout', None)
    if rpc_timeout is None:
        rpc_timeout = RPC_TIMEOUT
    if not 0.5 <= rpc_timeout <= 60.0:
        raise Refusal('--rpc-timeout must be 0.5..60 seconds')
    binary = getattr(args, 'codex_binary', None) or 'codex'
    sock = getattr(args, 'sock', None) or None
    return AttachConnection(binary, sock=sock,
                            rpc_timeout=float(rpc_timeout))


def _resolve_effort(args):
    """Resolve the explicit cooperating-lead phase signal.

    An explicit effort (low or xhigh only) wins; otherwise the explicit
    kind maps exactly like the adaptive lead interface: coordination is
    low, planning and review are the ceiling. Intermediate levels are
    never substituted for a level the interface does not expose.
    """
    effort = getattr(args, 'effort', None)
    kind = getattr(args, 'kind', None) or 'coordination'
    if kind not in pe.KINDS:
        raise Refusal('unknown work kind: ' + str(kind))
    if effort is None:
        if kind == 'coordination':
            effort = pe.COORDINATION_EFFORT
        else:
            effort = getattr(args, 'ceiling', None) or pe.DEFAULT_CEILING
    if effort not in pe.RANK:
        raise Refusal('unknown effort: ' + str(effort))
    if effort not in pe.INTERFACE_EFFORTS:
        raise Refusal('only low and xhigh are exposed in this first '
                      'adaptive interface; no medium/high substitution: '
                      + effort)
    return effort, kind


def _observe(record, reading):
    record['native'] = {'effort': reading['reasoning_effort'],
                       'updated_at': _now()}


def _apply_effort(conn, record, thread_id, effort, source, reason):
    """One bounded thread/settings/update for future turns; truthful ack.

    Returns the acknowledgement class and exit code:
    'acknowledged' (0), 'unavailable' (5, typed provider rejection) or
    'uncertain' (6, timeout/exit: the update may or may not have
    landed; the receipt is preserved, never retried blindly).
    """
    try:
        conn.update_thread_effort(thread_id, effort)
        ack, code = 'acknowledged', 0
    except ProviderRejected as exc:
        record['effort'] = {'requested': effort, 'source': source,
                           'ack': 'unavailable', 'updated_at': _now()}
        _apply_effort.last_error = str(exc)
        return 'unavailable', 5
    except Refusal as exc:
        record['effort'] = {'requested': effort, 'source': source,
                           'ack': 'uncertain', 'updated_at': _now()}
        _apply_effort.last_error = str(exc)
        return 'uncertain', 6
    record['effort'] = {'requested': effort, 'source': source,
                       'ack': 'acknowledged', 'updated_at': _now()}
    record['pending'] = None
    _apply_effort.last_error = None
    return 'acknowledged', 0


def _record_capability(record):
    if record is None or record['effort']['requested'] is None:
        return 'untested'
    return record['effort']['ack']


def cmd_inspect(root, args):
    """Read-only inspection of one exact existing daemon thread.

    Never starts, resumes or creates anything: only the loaded list and,
    when (and only when) the exact thread is already loaded, one
    turn-free ``thread/read``. Works during an active project STOP and
    explains it instead of enforcing it.
    """
    thread_id = _bounded(args.thread_id, cx.ID_BOUND, 'thread id')
    stop_active = lp.is_project_stop_active(root)
    record = None
    try:
        record = _find_record(root, thread_id)
    except Refusal:
        record = None
    conn = _connect(args)
    try:
        conn.initialize()
        loaded = conn.loaded_thread_ids()
        is_loaded = thread_id in loaded
        payload = {
            'thread_id': thread_id,
            'loaded': is_loaded,
            'status': None,
            'native_requested_effort': None,
            'native_model': None,
            'control_capability': _record_capability(record),
            'attach_record': 'active' if record is not None else 'none',
            'loaded_count': len(loaded),
            'stop_active': stop_active,
            'stop_note': ('project STOP is active: attaching and effort '
                          'control are blocked; this inspection stays '
                          'read-only' if stop_active else None),
            'note': None,
            'account': ACCOUNT_CAUTION,
            'effective': 'Unknown',
            'caution': CAUTION,
        }
        if is_loaded:
            reading = conn.read_loaded_thread(thread_id)
            payload['status'] = reading['status_type']
            payload['native_requested_effort'] = reading['reasoning_effort']
            payload['native_model'] = reading['model']
            human = ('attach inspect: thread loaded (status %s, native '
                     'requested effort %s); control %s%s'
                     % (reading['status_type'],
                        reading['reasoning_effort'] or 'Unknown',
                        payload['control_capability'],
                        '; STOP active: control blocked'
                        if stop_active else ''))
        else:
            payload['note'] = ('the exact requested thread is not loaded in '
                               'the shared daemon; this command never '
                               'resumes history, starts or creates a '
                               'thread')
            human = ('attach inspect: thread NOT loaded; no resume, no '
                     'start, no fork; control %s%s'
                     % (payload['control_capability'],
                        '; STOP active: control blocked' if stop_active
                        else ''))
        return _emit(args, payload, human)
    finally:
        conn.close()


def cmd_attach(root, args):
    """Explicit initial attach to ONE exact already-loaded IDLE thread.

    Admission (policy, STOP, off hold, lease, budget counting the lead
    exactly once) runs before the proxy spawns: the attached lead opens
    no owned thread and never reserves a second slot. The thread must be
    loaded in the shared daemon (this command never resumes or creates
    history) and acknowledged IDLE with the exact requested id; an
    optionally requested effort is applied for FUTURE turns only.
    """
    thread_id = _bounded(args.thread_id, cx.ID_BOUND, 'thread id')
    ceiling = args.ceiling or pe.DEFAULT_CEILING
    if ceiling not in pe.INTERFACE_EFFORTS:
        raise Refusal('ceiling must be low or xhigh in this first adaptive '
                      'interface: ' + str(ceiling))
    requested = None
    if args.effort is not None:
        _, _kind = _resolve_effort(args)
        requested = args.effort
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=args.budget_label)
    try:
        _refuse_active_managed_owner(root)
        existing = _load_record(root, thread_id)
        if existing is not None and not existing['detached']:
            raise Refusal('duplicate attachment: this exact thread already '
                          'has an active attach record (detach it first)')
        for other in _active_records(root):
            if other['thread_id'] != thread_id:
                raise Refusal('another thread is already attached in this '
                              'workspace (' + other['thread_id'][:12]
                              + '...); detach it before attaching here')
        conn = _connect(args)
        try:
            conn.initialize()
            loaded = conn.loaded_thread_ids()
            if thread_id not in loaded:
                raise Refusal('the exact requested thread is not loaded in '
                              'the shared daemon; attaching never resumes '
                              'history, starts or creates a thread')
            reading = conn.read_loaded_thread(thread_id)
            if reading['status_type'] == 'active':
                raise Refusal('the thread has a running turn; attaching '
                              'happens only at an idle boundary; no turn was '
                              'touched or interrupted; retry when the TUI '
                              'shows the thread idle')
            if reading['status_type'] != 'idle':
                raise Refusal('the thread status is %s; attaching requires '
                              'an idle thread on the shared daemon'
                              % reading['status_type'])
            now = _now()
            record = {
                'schema_version': 1, 'thread_id': thread_id,
                'workspace': str(root), 'route': ROUTE_DEFAULT,
                'codex_binary': args.codex_binary or 'codex',
                'sock': args.sock or '', 'ceiling': ceiling, 'auto': True,
                'effort': {'requested': None, 'source': None, 'ack': None,
                           'updated_at': ''},
                'native': {'effort': reading['reasoning_effort'],
                           'updated_at': now},
                'pending': None, 'created_at': now, 'updated_at': now,
                'detached': False, 'detached_at': None,
            }
            _save_record(root, record)
            payload = {
                'thread_id': thread_id,
                'attached': True,
                'thread_status': reading['status_type'],
                'native_requested_effort': reading['reasoning_effort'],
                'ceiling': ceiling,
                'requested': None,
                'loaded_count': len(loaded),
                'control_capability': 'untested',
                'note': ('attached; the requested effort applies to future '
                         'turns only; the owner TUI keeps full manual '
                         'control and its manual turns are not '
                         'Unio-admitted'),
                'account': ACCOUNT_CAUTION,
                'effective': 'Unknown',
                'caution': CAUTION,
            }
            exit_code = 0
            human_note = ''
            if requested is not None:
                ack, exit_code = _apply_effort(
                    conn, record, thread_id, requested, 'attach',
                    _bounded_reason(args.reason))
                with _record_guard(root):
                    _save_record(root, record)
                _observe_record_after_apply(conn, record, thread_id)
                payload['requested'] = _requested_view(record)
                payload['control_capability'] = record['effort']['ack']
                if ack == 'acknowledged':
                    human_note = ('; requested effort %s set for future '
                                  'turns (acknowledged)' % requested)
                elif ack == 'unavailable':
                    payload['note'] = ('attached, but the shared daemon '
                                       'rejected thread/settings/update; '
                                       'effort control is unavailable on '
                                       'this daemon: '
                                       + _apply_effort.last_error)
                    human_note = ('; effort control UNAVAILABLE (typed '
                                  'rejection recorded)')
                else:
                    payload['note'] = ('attached, but the effort update '
                                       'acknowledgement is Unknown (preserve '
                                       'receipt, no silent retry): '
                                       + _apply_effort.last_error)
                    human_note = ('; effort update acknowledgement UNKNOWN')
            human = ('attach: thread attached (status idle, native '
                     'requested effort %s, ceiling %s)%s'
                     % (reading['reasoning_effort'] or 'Unknown', ceiling,
                        human_note))
            return _emit(args, payload, human, exit_code=exit_code)
        finally:
            conn.close()
    finally:
        lease.release()


def _requested_view(record):
    return {'effort': record['effort']['requested'],
            'source': record['effort']['source'],
            'ack': record['effort']['ack'],
            'updated_at': record['effort']['updated_at']}


def _observe_record_after_apply(conn, record, thread_id):
    """Re-read the native effort after an acknowledged apply so the manual
    precedence comparison stays anchored on fresh evidence."""
    if record['effort']['ack'] != 'acknowledged':
        return
    try:
        reading = conn.read_loaded_thread(thread_id)
        _observe(record, reading)
    except Exception:
        # Observation is best-effort; the record keeps its prior anchor.
        pass


def cmd_phase(root, args):
    """Explicit cooperating-lead phase signal (auto or concrete effort).

    Honours STOP via admission, keeps native manual changes in control,
    never relabels a running turn (pending is recorded and applied only
    at a later explicit idle command), and validates the requested level
    against the thread's model advertisement before changing anything.
    """
    record = _find_record(root, args.thread_id)
    if record is None:
        raise Refusal('no active attach record in this workspace; attach '
                      'first')
    thread_id = record['thread_id']
    effort, kind = _resolve_effort(args)
    reason = _bounded_reason(args.reason)
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=None)
    try:
        conn = _connect(args)
        try:
            conn.initialize()
            loaded = conn.loaded_thread_ids()
            if thread_id not in loaded:
                raise Refusal('the attached thread is no longer loaded in '
                              'the shared daemon (the TUI may have closed '
                              'it); control refused without a fallback')
            reading = conn.read_loaded_thread(thread_id)
            if reading['status_type'] == 'active':
                # Never relabel a running turn: record the request as
                # pending and show it separately.
                record['pending'] = {'effort': effort, 'reason': reason,
                                     'updated_at': _now()}
                with _record_guard(root):
                    _save_record(root, record)
                payload = {
                    'thread_id': thread_id,
                    'requested': _requested_view(record),
                    'pending': dict(record['pending']),
                    'active_turn': True,
                    'native_requested_effort': reading['reasoning_effort'],
                    'note': ('the thread has a running turn: its active '
                             'effort is never relabelled; %s is recorded as '
                             'pending and applies only at a later explicit '
                             'idle attach phase command' % effort),
                    'effective': 'Unknown',
                    'caution': CAUTION,
                }
                return _emit(args, payload, 'attach phase: turn active; '
                                          'requested %s recorded as pending '
                                          'for the next idle boundary; no '
                                          'settings changed' % effort)
            if reading['status_type'] != 'idle':
                raise Refusal('the attached thread status is %s; control '
                              'requires an idle thread'
                              % reading['status_type'])
            # Native manual precedence: compare the fresh reading with the
            # record's last acknowledged request and last observation.
            anchors = set()
            if (record['effort']['requested'] is not None
                    and record['effort']['ack'] == 'acknowledged'):
                anchors.add(record['effort']['requested'])
            if record['native']['effort'] is not None:
                anchors.add(record['native']['effort'])
            fresh = reading['reasoning_effort']
            if anchors and (fresh is None or fresh not in anchors):
                record['auto'] = False
                with _record_guard(root):
                    record['native'] = {'effort': fresh,
                                        'updated_at': _now()}
                    _save_record(root, record)
                raise Refusal('native manual change detected (native '
                              'requested effort is now %r); AUTO control is '
                              'suspended and the native value is never '
                              'overwritten blindly; re-enable explicitly '
                              'with `unio lead-session attach auto`'
                              % (fresh,))
            # An unresolved uncertain acknowledgement blocks new updates
            # until the native reading resolves it (evidence) or the owner
            # re-enables explicitly; it is never retried silently.
            if record['effort']['ack'] == 'uncertain':
                previous = record['effort']['requested']
                if fresh is None or fresh != previous:
                    raise Refusal('the previous effort update '
                                  'acknowledgement is still Unknown; verify '
                                  'it in the TUI, then re-enable explicitly '
                                  'with `unio lead-session attach auto`; no '
                                  'blind retry')
            # Advertisement honesty: the thread's own model must actually
            # advertise the requested level; no level substitution.
            model = reading['model']
            if not isinstance(model, str) or not model:
                raise Refusal('the thread does not expose its native model; '
                              'cannot verify that %s is advertised; '
                              'refusing to set it' % effort)
            advertised = conn.read_model_efforts(model)
            if effort not in advertised:
                raise Refusal('the thread\'s native model does not advertise '
                              '%s; no effort substitution is made '
                              '(advertised: %s)'
                              % (effort, ', '.join(advertised)))
            ack, exit_code = _apply_effort(conn, record, thread_id, effort,
                                           'phase', reason)
            _observe_record_after_apply(conn, record, thread_id)
            with _record_guard(root):
                _save_record(root, record)
            payload = {
                'thread_id': thread_id,
                'requested': _requested_view(record),
                'pending': dict(record['pending']) if record['pending']
                           else None,
                'active_turn': False,
                'native_requested_effort': record['native']['effort'],
                'advertised': advertised,
                'note': ('the requested effort applies to the thread\'s '
                         'future turns only; a running turn was never '
                         'relabelled; the effective provider effort '
                         'remains Unknown'),
                'effective': 'Unknown',
                'caution': CAUTION,
            }
            if ack == 'unavailable':
                payload['note'] = ('the shared daemon rejected '
                                   'thread/settings/update; effort control '
                                   'is unavailable on this daemon: '
                                   + _apply_effort.last_error)
                return _emit(args, payload, 'attach phase: requested %s '
                                           'UNAVAILABLE (typed rejection '
                                           'recorded): %s'
                                           % (effort,
                                              _apply_effort.last_error),
                                            exit_code=5)
            if ack == 'uncertain':
                payload['note'] = ('the effort update acknowledgement is '
                                   'Unknown; the receipt is preserved and '
                                   'never silently retried: '
                                   + _apply_effort.last_error)
                return _emit(args, payload, 'attach phase: requested %s '
                                           'acknowledgement UNKNOWN; '
                                           'verify in the TUI' % effort,
                                            exit_code=6)
            return _emit(args, payload, 'attach phase: requested %s set '
                                        'for future turns (acknowledged; '
                                        'kind %s; effective Unknown; the '
                                        'owner TUI keeps manual control)'
                         % (effort, kind))
        finally:
            conn.close()
    finally:
        lease.release()


def cmd_auto(root, args):
    """Explicit re-enable of AUTO control after a suspend."""
    record = _find_record(root, args.thread_id)
    if record is None:
        raise Refusal('no active attach record in this workspace')
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=None)
    try:
        with _record_guard(root):
            fresh = _load_record(root, record['thread_id'])
            if fresh is None or fresh['detached']:
                raise Refusal('the attach record is no longer active')
            fresh['auto'] = True
            if fresh['effort']['ack'] == 'uncertain':
                # The owner explicitly intervenes: the uncertain receipt is
                # preserved on disk history but control resumes from the
                # next truthful acknowledgement.
                fresh['effort'] = {'requested': fresh['effort']['requested'],
                                   'source': fresh['effort']['source'],
                                   'ack': 'acknowledged-by-owner',
                                   'updated_at': _now()}
            _save_record(root, fresh)
        payload = _record_view(fresh)
        payload['note'] = ('AUTO re-enabled; native manual changes keep '
                           'winning over automatic control and suspend it '
                           'again when detected')
        return _emit(args, payload, 'attach auto: AUTO control re-enabled')
    finally:
        lease.release()


def cmd_status(root, args):
    """Local-only status view: zero proxy connections, zero daemon calls."""
    stop_active = lp.is_project_stop_active(root)
    record = _find_record(root, args.thread_id)
    if record is None:
        payload = {
            'attached': False,
            'stop_active': stop_active,
            'note': ('no active attach record in this workspace; run '
                     '`unio lead-session attach inspect --thread-id ...` '
                     'first (read-only)'),
            'effective': 'Unknown',
            'caution': CAUTION,
        }
        return _emit(args, payload, 'attach status: no active attach record')
    payload = _record_view(record)
    payload['attached'] = not record['detached']
    payload['stop_active'] = stop_active
    payload['stop_note'] = ('project STOP is active: attaching and effort '
                            'control are blocked; this status stays '
                            'read-only' if stop_active else None)
    payload['note'] = ('requested is the last Unio-requested effort for '
                       'future turns (pending applies at a later explicit '
                       'idle command); the owner TUI keeps full manual '
                       'control and its manual turns are not '
                       'Unio-admitted')
    human = ('attach status: thread attached, requested %s (ack %s), '
             'pending %s, AUTO %s, native observed %s, effective Unknown'
             % (record['effort']['requested'] or 'none',
                record['effort']['ack'] or 'none',
                record['pending']['effort'] if record['pending'] else 'none',
                'on' if record['auto'] else 'suspended',
                record['native']['effort'] or 'Unknown'))
    return _emit(args, payload, human)


def cmd_detach(root, args):
    """Detach explicitly: release the record, keep the history intact.

    Local only (no proxy, no daemon call, no lease): detach is a safe
    release and stays available during an active project STOP.
    """
    record = _find_record(root, args.thread_id)
    if record is None:
        raise Refusal('no active attach record in this workspace')
    with _record_guard(root):
        fresh = _load_record(root, record['thread_id'])
        if fresh is None or fresh['detached']:
            raise Refusal('the attach record is no longer active')
        fresh['detached'] = True
        fresh['detached_at'] = _now()
        _save_record(root, fresh)
    payload = _record_view(fresh)
    payload['detached'] = True
    payload['note'] = ('detached; the attach record stays on disk; the '
                       'shared daemon and the owner TUI were never touched')
    return _emit(args, payload, 'attach detach: released; the shared '
                                 'daemon and the owner TUI are untouched')


def run(root, args):
    """Dispatch one ``unio lead-session attach`` control."""
    _attach_dir(root)  # fail early on an unavailable state directory
    if args.control == 'inspect':
        return cmd_inspect(root, args)
    if args.control == 'attach':
        return cmd_attach(root, args)
    if args.control == 'phase':
        return cmd_phase(root, args)
    if args.control == 'auto':
        return cmd_auto(root, args)
    if args.control == 'status':
        return cmd_status(root, args)
    if args.control == 'detach':
        return cmd_detach(root, args)
    raise Refusal('unknown attach control: ' + str(args.control))
