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
  pending and consumed by the later explicit idle command — with NO
  explicit new choice the queued choice itself is applied, an explicit
  choice wins, and the queue is never silently replaced by the
  coordination default);
- native manual changes win: before applying, the freshly read native
  effort is compared with this record's last acknowledged request and
  last observation; a mismatch means a native manual change (for example
  the owner's own ``/model --reasoning`` in the TUI) and the connector
  suspends AUTO control and refuses to overwrite it; every acknowledged
  apply also RE-OBSERVES the native anchor and persists the fresh
  POST-apply evidence (a failed reread persists an explicitly Unknown
  anchor — never a knowingly stale pre-apply value); a suspended
  automatic phase STAYS suspended across commands - NO setter and NO
  pending automatic write happens - until the explicit ``attach auto``
  command re-enables it, and the explicit owner ``attach manual
  --effort low|xhigh`` override applies a concrete owner level while
  pinning automatic phase selection off;
- the configured ceiling actually binds automatic planning/review phase
  resolution: it is read from the validated persisted attach record
  (never from a per-command flag), an automatic kind never exceeds it,
  an explicit phase request above it refuses, and only the explicit
  owner ``attach manual`` override - always reported, never silent -
  may go above the promised bound;
- an acknowledged-because-typed-rejection setter is recorded as
  ``unavailable`` and an uncertain (timeout/exit) acknowledgement as
  ``uncertain`` - and every settings attempt is a durable two-line
  journal receipt (``coord/lead-session-attach/attempts-*.jsonl``):
  the intent entry persists BEFORE the mutating RPC (a refusal to
  record means ZERO settings calls) and the result entry records the
  actual acknowledgement afterward, so old unknown/rejected/
  acknowledged attempt facts stay separate from the current control
  state, byte-identical and never truncated, deleted or rewritten by
  later setters, ``auto`` re-enables, successes, detaches or
  re-attaches; an owner re-enable acknowledges AUTHORITY only, never
  delivery - the original uncertain acknowledgement is kept intact,
  and a dangling intent (interrupted run) blocks further updates until
  the owner resolves it explicitly; no invented completion ever
  happens;
- admission uses the SAME policy controller as the owned path
  (``lead-session-policy.py``): project STOP, off holds, the configured
  registered lead's real account group mapping, native slot counting
  (the lead is counted exactly once) and the owned lead lease are
  enforced before any proxy process is spawned, for ``attach`` and every
  mutating control; read-only ``inspect`` reports an active STOP instead
  of enforcing it, and READ commands (inspect/status) create or change
  NOTHING on disk — an absent attach store stays absent, a present
  unsafe store refuses, and only mutating writes create the private
  0700/0600 store;
- the transport selection (codex binary and control socket) is PERSISTED
  at attach and re-used by every later record-bound control command:
  omitted flags keep the attached endpoint instead of silently
  defaulting to a possibly different local daemon/client, and an
  explicit CONFLICTING endpoint refuses until the owner deliberately
  detaches and re-attaches; the saved selection is a name, never an
  identity proof (the implicit PATH ``codex`` default is resolved again
  per command and its continuity across installations cannot be
  established; the native CLI keeps updating normally with no
  binary-hash allowlist), and no daemon or fallback service is ever
  started;
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
import stat
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

SCHEMA_VERSION = 2
RECORD_KEYS = frozenset(('schema_version', 'thread_id', 'workspace', 'route',
                         'codex_binary', 'sock', 'ceiling', 'auto', 'effort',
                         'native', 'pending', 'owner_pin', 'created_at',
                         'updated_at', 'detached', 'detached_at'))
LEGACY_RECORD_KEYS = RECORD_KEYS - frozenset(('owner_pin',))
EFFORT_KEYS = frozenset(('requested', 'source', 'ack', 'owner_acknowledged',
                         'updated_at'))
LEGACY_EFFORT_KEYS = EFFORT_KEYS - frozenset(('owner_acknowledged',))
OWNER_PIN_KEYS = frozenset(('effort', 'reason', 'updated_at'))
NATIVE_KEYS = frozenset(('effort', 'updated_at'))
PENDING_KEYS = frozenset(('effort', 'reason', 'updated_at'))
ACKS = ('acknowledged', 'unavailable', 'uncertain',
        'acknowledged-by-owner')
SOURCES = ('attach', 'phase', 'manual')
STATE_BOUND = 65536

# -- bounded attempt journal (crash-aware per-attempt receipts) ---------
#
# Every settings attempt is a two-line receipt: the intent entry is
# persisted BEFORE the mutating RPC (a refusal to record means ZERO
# settings calls) and the result entry records the ACTUAL acknowledgement
# class afterward. An attempt interrupted between the two stays visibly
# unresolved (dangling) and blocks further updates until the owner
# resolves it explicitly — never an invented completion. Entries are
# appended only: old unknown/rejected/acknowledged attempts are never
# rewritten, truncated or deleted, byte-identical across unrelated later
# control-state changes, auto re-enables, successes, detach and re-attach.

JOURNAL_VERSION = 1
JOURNAL_INTENT_KEYS = frozenset(('v', 'kind', 'attempt', 'at', 'thread_id',
                                 'source', 'requested', 'reason'))
JOURNAL_RESULT_KEYS = frozenset(('v', 'kind', 'attempt', 'at', 'thread_id',
                                 'ack', 'error'))
JOURNAL_RESOLUTION_KEYS = frozenset(('v', 'kind', 'at', 'thread_id',
                                      'acknowledged'))
JOURNAL_ACKS = ('acknowledged', 'unavailable', 'uncertain')
JOURNAL_ENTRIES_BOUND = 256
JOURNAL_BYTES_BOUND = 65536
JOURNAL_ERROR_BOUND = 256


def _journal_name(thread_id):
    digest = hashlib.sha256(thread_id.encode('utf-8')).hexdigest()
    return 'attempts-' + digest[:32] + '.jsonl'


def _journal_path(root, thread_id):
    return _attach_dir_path(root) / _journal_name(thread_id)


def _validate_journal_entry(entry, name):
    def refuse():
        raise Refusal('invalid attach attempt journal entry: ' + name)

    if not isinstance(entry, dict):
        refuse()
    keys = set(entry)
    if entry.get('v') != JOURNAL_VERSION:
        refuse()
    if keys == JOURNAL_INTENT_KEYS:
        if entry['kind'] != 'intent':
            refuse()
        if (not isinstance(entry.get('attempt'), int)
                or entry['attempt'] < 1):
            refuse()
        if entry['source'] not in SOURCES:
            refuse()
        if entry['requested'] not in pe.INTERFACE_EFFORTS:
            refuse()
        if (not isinstance(entry.get('reason'), str)
                or '\x00' in entry['reason']
                or len(entry['reason'].encode('utf-8', 'replace'))
                > pe.REASON_BOUND):
            refuse()
    elif keys == JOURNAL_RESULT_KEYS:
        if entry['kind'] != 'result':
            refuse()
        if (not isinstance(entry.get('attempt'), int)
                or entry['attempt'] < 1):
            refuse()
        if entry['ack'] not in JOURNAL_ACKS:
            refuse()
        error = entry['error']
        if (error is not None and (not isinstance(error, str)
                                   or '\x00' in error
                                   or len(error.encode('utf-8', 'replace'))
                                   > JOURNAL_ERROR_BOUND)):
            refuse()
    elif keys == JOURNAL_RESOLUTION_KEYS:
        if entry['kind'] != 'owner-resolution':
            refuse()
        try:
            _bounded(entry['acknowledged'], JOURNAL_ERROR_BOUND,
                     'owner acknowledgement')
        except Refusal:
            refuse()
    else:
        refuse()
    try:
        _bounded(entry['at'], 32, 'timestamp')
        _bounded(entry['thread_id'], cx.ID_BOUND, 'thread id')
    except Refusal:
        refuse()
    return entry


def _journal_entries(root, thread_id):
    """Every journal entry of one thread; fail closed on unsafe state."""
    path = _journal_path(root, thread_id)
    if not path.exists():
        return []
    data = ml._read_owned_file(path, JOURNAL_BYTES_BOUND)
    entries = []
    for line in data.splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise Refusal('invalid attach attempt journal (unreadable '
                          'entry; refusing any settings call)') from exc
        entries.append(_validate_journal_entry(entry, path.name))
    if len(entries) > JOURNAL_ENTRIES_BOUND:
        raise Refusal('attach attempt journal bound exceeded')
    return entries


def _journal_append(root, thread_id, entry):
    """Append ONE durable receipt line; refuse without ever truncating.

    Journal writes are single-writer: every mutating command holds the
    lead admission lease, so no lock is taken here (which also keeps it
    safely callable while the short record guard is held).
    """
    _validate_journal_entry(entry, _journal_name(thread_id))
    path = _journal_path(root, thread_id)
    _attach_dir(root)  # mutating path: private 0700 store, fail closed
    ml.safe_path(path)
    entries = _journal_entries(root, thread_id)
    if len(entries) >= JOURNAL_ENTRIES_BOUND:
        raise Refusal('the attach attempt journal is full (%d entries); '
                      'no new attempt is recorded and no settings call is '
                      'made; old failures are never truncated or deleted - '
                      'archive the journal file before continuing'
                      % JOURNAL_ENTRIES_BOUND)
    line = (json.dumps(entry, ensure_ascii=False) + '\n').encode('utf-8')
    if path.exists() and path.stat().st_size + len(line) > JOURNAL_BYTES_BOUND:
        raise Refusal('the attach attempt journal is full (%d bytes); '
                      'no new attempt is recorded and no settings call is '
                      'made; old failures are never truncated or deleted - '
                      'archive the journal file before continuing'
                      % JOURNAL_BYTES_BOUND)
    fd = None
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND
                     | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid() or st.st_mode & 0o077):
            raise OSError('unsafe attach attempt journal')
        view = memoryview(line)
        while view:
            written = os.write(fd, view)
            if not written:
                raise OSError('short journal write')
            view = view[written:]
        os.fsync(fd)
    except OSError as exc:
        raise Refusal('the attach attempt journal cannot be written (%s); '
                      'refusing BEFORE any settings call; no invented '
                      'completion is possible' % exc) from exc
    finally:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass


def _journal_dangling(root, thread_id):
    """The newest attempt whose intent has no completion receipt yet.

    Crash-aware: an intent entry without its result entry (and without a
    later explicit owner resolution) means the run died around the
    mutating RPC and the attempt's outcome stays Unknown - it is never
    completed by the owner's later choices and blocks new updates.
    """
    outstanding = []
    for entry in _journal_entries(root, thread_id):
        if entry['kind'] == 'owner-resolution':
            outstanding = []
        elif entry['kind'] == 'intent':
            outstanding.append(entry)
        elif entry['kind'] == 'result':
            outstanding = [item for item in outstanding
                           if item['attempt'] != entry['attempt']]
    return outstanding[-1] if outstanding else None


def _journal_next_attempt(root, thread_id):
    entries = _journal_entries(root, thread_id)
    numbers = [entry['attempt'] for entry in entries
               if 'attempt' in entry]
    return (max(numbers) + 1) if numbers else 1


def _attach_dir_path(root):
    """The attach record directory path; NEVER created or changed here."""
    return ml.safe_path(root / 'coord' / 'lead-session-attach')


def _attach_dir_read(root):
    """The attach record directory for READ paths: existing safe state only.

    Returns None when the store does not exist yet — an absent state IS
    the honest answer for a read-only view. A present but unsafe
    directory (symlink inside the path is refused by ``safe_path``, a
    non-directory, a foreign owner or a non-private mode) refuses
    instead of being silently repaired: ``inspect`` and ``status``
    never mkdir, chmod or write ANYTHING.
    """
    path = _attach_dir_path(root)
    if not path.exists():
        return None
    try:
        st = os.stat(path)
    except OSError as exc:
        raise Refusal('attach state directory unreadable') from exc
    if (not stat.S_ISDIR(st.st_mode) or st.st_uid != os.getuid()
            or st.st_mode & 0o077):
        raise Refusal('unsafe attach state directory: read commands refuse '
                      'instead of repairing or ignoring it')
    return path


def _attach_dir(root):
    """The attach record directory for MUTATING paths (private 0700).

    Only through here may the store be created or chmodded; both fail
    closed when the directory is unavailable or unsafe.
    """
    path = _attach_dir_path(root)
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
    return _attach_dir_path(root) / _record_name(thread_id)


def _validate_record(doc):
    def refuse():
        raise Refusal('invalid attach record')

    if not isinstance(doc, dict):
        refuse()
    if (doc.get('schema_version') == 1
            and set(doc) == LEGACY_RECORD_KEYS):
        # Additive migration of an own prototype v1 record: the new
        # control fields are added with neutral defaults and NOTHING
        # existing is rewritten; it is persisted as v2 only on the next
        # explicit save. Owned legacy records are never read here.
        doc['schema_version'] = SCHEMA_VERSION
        doc['owner_pin'] = None
        doc['effort'] = dict(doc['effort'], owner_acknowledged=None)
    if doc.get('schema_version') != SCHEMA_VERSION or set(doc) != RECORD_KEYS:
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
    elif (effort['source'] is not None or effort['ack'] is not None
            or effort['owner_acknowledged'] is not None):
        refuse()
    if not isinstance(effort['updated_at'], str):
        refuse()
    if effort['owner_acknowledged'] is not None:
        try:
            _bounded(effort['owner_acknowledged'], 32,
                     'owner acknowledgement')
        except Refusal:
            refuse()
    pin = doc.get('owner_pin')
    if pin is not None:
        if not isinstance(pin, dict) or set(pin) != OWNER_PIN_KEYS:
            refuse()
        if pin['effort'] not in pe.INTERFACE_EFFORTS:
            refuse()
        if (not isinstance(pin['reason'], str) or '\x00' in pin['reason']
                or len(pin['reason'].encode('utf-8', 'replace'))
                > pe.REASON_BOUND):
            refuse()
        if not isinstance(pin['updated_at'], str):
            refuse()
        if doc['auto'] is not False:
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
    _attach_dir(root)  # mutating path: private 0700 store, fail closed
    ml._atomic_write(_record_path(root, doc['thread_id']), data)


def _active_records(root):
    """Active (not detached) attach records; fail closed on unsafe state.

    Read-only: the store is resolved WITHOUT creating or changing it, and
    an absent store is simply an empty active-record set.
    """
    directory = _attach_dir_read(root)
    if directory is None:
        return []
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
    pin = record['owner_pin']
    return {
        'thread_id': record['thread_id'],
        'route': record['route'],
        'ceiling': record['ceiling'],
        'auto': record['auto'],
        'owner_pin': dict(pin) if pin else None,
        'detached': record['detached'],
        'requested': {
            'effort': record['effort']['requested'],
            'source': record['effort']['source'],
            'ack': record['effort']['ack'],
            'owner_acknowledged': record['effort']['owner_acknowledged'],
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


def _connect(args, record=None):
    """One attach connection for read-only exploration or record-bound control.

    Control commands that operate on an ACTIVE attach record re-use its
    PERSISTED transport selection (codex binary and control socket, saved
    at attach): omitted flags keep the attached endpoint instead of
    silently defaulting to a possibly different local daemon, and an
    EXPLICIT conflicting endpoint refuses until the owner deliberately
    detaches and re-attaches. The saved selection is a NAME, never an
    identity proof: an implicit PATH ``codex`` default is resolved again
    per command (the native CLI keeps updating normally; there is no
    binary-hash or version allowlist), and continuity of an implicit
    default across installations cannot be established - qualified in the
    docs. No daemon is ever started by this connector.
    """
    rpc_timeout = getattr(args, 'rpc_timeout', None)
    if rpc_timeout is None:
        rpc_timeout = RPC_TIMEOUT
    if not 0.5 <= rpc_timeout <= 60.0:
        raise Refusal('--rpc-timeout must be 0.5..60 seconds')
    binary = getattr(args, 'codex_binary', None) or 'codex'
    sock = getattr(args, 'sock', None) or None
    if record is not None:
        saved_binary = record['codex_binary'] or 'codex'
        saved_sock = record['sock'] or None
        explicit_binary = ((getattr(args, 'codex_binary', None) or 'codex')
                           != 'codex')
        explicit_sock = getattr(args, 'sock', None) is not None
        if ((explicit_binary and binary != saved_binary)
                or (explicit_sock and sock != saved_sock)):
            raise Refusal('the explicit endpoint (binary %r, socket %r) '
                          'conflicts with the transport selection persisted '
                          'at attach (binary %r, socket %r) for thread %s; '
                          'control never switches endpoints implicitly or '
                          'explicitly: detach and re-attach to change it '
                          'deliberately'
                          % (binary, sock, saved_binary, saved_sock,
                             record['thread_id']))
        binary, sock = saved_binary, saved_sock
    return AttachConnection(binary, sock=sock,
                            rpc_timeout=float(rpc_timeout))


def _resolve_effort(args, record=None):
    """Resolve the explicit cooperating-lead phase signal.

    Automatic kind resolution is bound by the VALIDATED PERSISTED
    ceiling of the attached record (never by a per-command flag): an
    explicit effort (low or xhigh only) wins for the concrete level but
    must not exceed that promised bound; coordination is low, planning
    and review are exactly the stored ceiling. The promised bound is
    never silently exceeded - going above it is an explicit owner
    decision (`attach manual`), reported as such. Intermediate levels
    are never substituted for a level the interface does not expose.
    """
    effort = getattr(args, 'effort', None)
    kind = getattr(args, 'kind', None) or 'coordination'
    if kind not in pe.KINDS:
        raise Refusal('unknown work kind: ' + str(kind))
    ceiling = None
    if record is not None:
        ceiling = record['ceiling']  # validated when the record loaded
    if effort is None:
        if kind == 'coordination':
            effort = pe.COORDINATION_EFFORT
        elif ceiling is not None:
            effort = ceiling
        else:
            effort = pe.DEFAULT_CEILING
    if effort not in pe.RANK:
        raise Refusal('unknown effort: ' + str(effort))
    if effort not in pe.INTERFACE_EFFORTS:
        raise Refusal('only low and xhigh are exposed in this first '
                      'adaptive interface; no medium/high substitution: '
                      + effort)
    if ceiling is not None and pe.RANK.index(effort) > pe.RANK.index(ceiling):
        raise Refusal('explicit effort %s exceeds the configured ceiling %s; '
                      'the promised bound is never silently exceeded: '
                      're-attach with a higher ceiling or apply the '
                      'explicit owner override `unio lead-session attach '
                      'manual --effort %s`' % (effort, ceiling, effort))
    return effort, kind


def _refuse_suspended(record):
    """Persistent manual precedence (a stored bool is not enforcement:
    the gate that refuses every automatic write is)."""
    if record['auto']:
        return
    pin = record['owner_pin']
    if pin is not None:
        raise Refusal('the owner manual pin %s is active: automatic phase '
                      'selection stays suspended across commands with NO '
                      'setter and NO pending automatic write; re-enable '
                      'explicitly with `unio lead-session attach auto` or '
                      'apply a concrete owner override with `unio '
                      'lead-session attach manual --effort low|xhigh`'
                      % pin['effort'])
    raise Refusal('automatic phase control is suspended after a native '
                  'manual change (native requested effort %r observed at %s) '
                  'and stays suspended across commands: NO setter and NO '
                  'pending automatic write happens until the owner '
                  'explicitly re-enables with `unio lead-session attach '
                  'auto`; the native value is never overwritten blindly'
                  % (record['native']['effort'],
                     record['native']['updated_at']))


def _observe(record, reading):
    record['native'] = {'effort': reading['reasoning_effort'],
                       'updated_at': _now()}


def _apply_effort(root, conn, record, thread_id, effort, source, reason):
    """One bounded thread/settings/update with a durable attempt receipt.

    The intent entry is persisted BEFORE the mutating RPC: if required
    recording cannot be made, the call refuses and ZERO settings RPCs
    happen. The result entry records the ACTUAL acknowledgement class
    ('acknowledged' 0, 'unavailable' 5 typed provider rejection,
    'uncertain' 6 timeout/exit: the update may or may not have landed).
    Every attempt keeps its requested effort, exact thread id, request
    timestamp and truthful outcome separately and durably; a previous
    unknown/rejected attempt is never rewritten by a later setter, and a
    dangling intent (interrupted run) blocks further updates until the
    owner resolves it explicitly - no invented completion ever happens.
    """
    dangling = _journal_dangling(root, thread_id)
    if dangling is not None:
        raise Refusal('the settings attempt %d (requested %s at %s) has no '
                      'completion receipt - its outcome remains Unknown '
                      'after an interrupted run and is never completed '
                      'silently; verify it in the TUI, then resolve it '
                      'explicitly with `unio lead-session attach auto` '
                      'before any further update'
                      % (dangling['attempt'], dangling['requested'],
                         dangling['at']))
    attempt = _journal_next_attempt(root, thread_id)
    intent = {'v': JOURNAL_VERSION, 'kind': 'intent', 'attempt': attempt,
              'at': _now(), 'thread_id': thread_id, 'source': source,
              'requested': effort, 'reason': reason}
    _journal_append(root, thread_id, intent)
    try:
        conn.update_thread_effort(thread_id, effort)
        ack, code, error = 'acknowledged', 0, None
    except ProviderRejected as exc:
        ack, code, error = 'unavailable', 5, str(exc)
    except Refusal as exc:
        ack, code, error = 'uncertain', 6, str(exc)
    if error is not None and len(error) > JOURNAL_ERROR_BOUND:
        error = error[:JOURNAL_ERROR_BOUND]
    _apply_effort.last_error = error
    _journal_append(root, thread_id,
                    {'v': JOURNAL_VERSION, 'kind': 'result',
                     'attempt': attempt, 'at': _now(),
                     'thread_id': thread_id, 'ack': ack, 'error': error})
    record['effort'] = {'requested': effort, 'source': source,
                        'ack': ack, 'owner_acknowledged': None,
                        'updated_at': _now()}
    if ack == 'acknowledged':
        record['pending'] = None
    return ack, code


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
        if args.effort not in pe.RANK:
            raise Refusal('unknown effort: ' + str(args.effort))
        if args.effort not in pe.INTERFACE_EFFORTS:
            raise Refusal('only low and xhigh are exposed in this first '
                          'adaptive interface; no medium/high substitution: '
                          + args.effort)
        if pe.RANK.index(args.effort) > pe.RANK.index(ceiling):
            raise Refusal('the requested effort %s exceeds the requested '
                          'ceiling %s; the promised bound is never silently '
                          'exceeded at attach either'
                          % (args.effort, ceiling))
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
        if requested is not None:
            # A crash-aware journal must be able to record this attempt:
            # refuse safely BEFORE any setter if it cannot.
            dangling = _journal_dangling(root, thread_id)
            if dangling is not None:
                raise Refusal('the settings attempt %d (requested %s at %s) '
                              'has no completion receipt - its outcome '
                              'remains Unknown after an interrupted run; '
                              'verify it in the TUI, then resolve it '
                              'explicitly with `unio lead-session attach '
                              'auto` before requesting a new effort'
                              % (dangling['attempt'], dangling['requested'],
                                 dangling['at']))
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
            advertised = None
            if requested is not None:
                # Advertisement honesty for the optional initial effort
                # too, not just phase: no level substitution, ever.
                model = reading['model']
                if not isinstance(model, str) or not model:
                    raise Refusal('the thread does not expose its native '
                                  'model; cannot verify that %s is '
                                  'advertised; refusing to set it'
                                  % requested)
                advertised = conn.read_model_efforts(model)
                if requested not in advertised:
                    raise Refusal('the thread\'s native model does not '
                                  'advertise %s; no effort substitution is '
                                  'made (advertised: %s)'
                                  % (requested, ', '.join(advertised)))
            now = _now()
            record = {
                'schema_version': SCHEMA_VERSION, 'thread_id': thread_id,
                'workspace': str(root), 'route': ROUTE_DEFAULT,
                'codex_binary': args.codex_binary or 'codex',
                'sock': args.sock or '', 'ceiling': ceiling, 'auto': True,
                'effort': {'requested': None, 'source': None, 'ack': None,
                           'owner_acknowledged': None, 'updated_at': ''},
                'native': {'effort': reading['reasoning_effort'],
                           'updated_at': now},
                'pending': None, 'owner_pin': None, 'created_at': now,
                'updated_at': now, 'detached': False, 'detached_at': None,
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
            if advertised is not None:
                payload['advertised'] = advertised
            exit_code = 0
            human_note = ''
            if requested is not None:
                ack, exit_code = _apply_effort(
                    root, conn, record, thread_id, requested, 'attach',
                    _bounded_reason(args.reason))
                # Observe FIRST, persist second: the disk anchor must be
                # the fresh POST-apply evidence (or an explicitly Unknown
                # anchor when the reread failed), never the stale
                # pre-apply effort - exactly like phase and manual.
                _observe_record_after_apply(conn, record, thread_id)
                with _record_guard(root):
                    _save_record(root, record)
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
            'owner_acknowledged': record['effort']['owner_acknowledged'],
            'updated_at': record['effort']['updated_at']}


def _observe_record_after_apply(conn, record, thread_id):
    """Re-read the native effort after an acknowledged apply so the manual
    precedence comparison stays anchored on fresh evidence.

    When the reread fails, the pre-apply observation is KNOWINGLY stale
    (the settings update was acknowledged), so the anchor becomes
    explicitly Unknown instead of keeping a value the record knows is
    outdated: uncertainty stays honest, no fresh observation is claimed
    for the old effort, and the acknowledged delivery fact itself never
    changes. An unavailable or uncertain acknowledgement keeps the
    existing anchor untouched (nothing is known to have landed).
    """
    if record['effort']['ack'] != 'acknowledged':
        return
    try:
        reading = conn.read_loaded_thread(thread_id)
        _observe(record, reading)
    except Exception:
        record['native'] = {'effort': None, 'updated_at': _now()}


def cmd_phase(root, args):
    """Explicit cooperating-lead phase signal (auto or concrete effort).

    A suspended automatic phase stays suspended across commands: this
    gate refuses with NO setter and NO pending automatic write until the
    owner explicitly re-enables AUTO or applies the explicit owner
    manual override (`attach manual`). With NO explicit new choice
    (`--kind`/`--effort` both absent), a previously QUEUED pending
    request (recorded while the turn was running) IS the choice: it is
    consumed at an idle boundary instead of being silently replaced by
    the coordination default, and it stays queued untouched at a
    still-active boundary; an explicit new choice intentionally wins.
    Honours STOP via admission, keeps native manual changes in control,
    never relabels a running turn, revalidates the persisted ceiling,
    manual pin and model advertisement at apply, and validates the
    requested level against the thread's model advertisement before
    changing anything.
    """
    record = _find_record(root, args.thread_id)
    if record is None:
        raise Refusal('no active attach record in this workspace; attach '
                      'first')
    _refuse_suspended(record)
    thread_id = record['thread_id']
    explicit_choice = (getattr(args, 'effort', None) is not None
                       or getattr(args, 'kind', None) is not None)
    consuming = not explicit_choice and record['pending'] is not None
    if consuming:
        # The queued pending choice (kept separate from the current
        # requested level) is consumed; the persisted ceiling is
        # revalidated at this apply boundary.
        pending = record['pending']
        effort = pending['effort']
        kind = 'pending'
        reason = _bounded_reason(pending['reason'])
        if pe.RANK.index(effort) > pe.RANK.index(record['ceiling']):
            raise Refusal('the queued pending request %s exceeds the '
                          'configured ceiling %s; it is not applied: the '
                          'promised bound is never silently exceeded - '
                          're-attach with a higher ceiling or apply the '
                          'explicit owner override `unio lead-session '
                          'attach manual --effort %s`'
                          % (effort, record['ceiling'], effort))
    else:
        effort, kind = _resolve_effort(args, record)
        reason = _bounded_reason(args.reason)
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=None)
    try:
        conn = _connect(args, record)
        try:
            conn.initialize()
            loaded = conn.loaded_thread_ids()
            if thread_id not in loaded:
                raise Refusal('the attached thread is no longer loaded in '
                              'the shared daemon (the TUI may have closed '
                              'it); control refused without a fallback')
            reading = conn.read_loaded_thread(thread_id)
            if reading['status_type'] == 'active':
                # Never relabel a running turn: the request is shown as
                # pending and applies only at a later explicit idle
                # command. A QUEUED choice is never silently replaced by
                # a re-resolved default: without an explicit new choice
                # the queue stays exactly as it is.
                if not consuming:
                    record['pending'] = {'effort': effort, 'reason': reason,
                                         'updated_at': _now()}
                    with _record_guard(root):
                        _save_record(root, record)
                payload = {
                    'thread_id': thread_id,
                    'requested': _requested_view(record),
                    'pending': dict(record['pending'])
                               if record['pending'] else None,
                    'active_turn': True,
                    'native_requested_effort': reading['reasoning_effort'],
                    'note': (('the thread still has a running turn: it is '
                              'never relabelled and no settings changed; '
                              'the queued pending choice %s stays queued '
                              'and applies at the next explicit idle '
                              'attach phase command' % effort)
                             if consuming else
                             ('the thread has a running turn: its active '
                              'effort is never relabelled; %s is recorded '
                              'as pending and applies only at a later '
                              'explicit idle attach phase command'
                              % effort)),
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
                              'with `unio lead-session attach auto` or '
                              'apply a concrete owner override with '
                              '`unio lead-session attach manual --effort '
                              'low|xhigh`'
                              % (fresh,))
            # An unresolved uncertain acknowledgement blocks new updates
            # until the native reading resolves it (evidence) or the owner
            # re-enables explicitly (authority, never delivery); it is
            # never retried silently and is never rewritten as delivered.
            if record['effort']['ack'] == 'uncertain':
                previous = record['effort']['requested']
                owner_ack = record['effort']['owner_acknowledged']
                if (owner_ack is None and (fresh is None
                                           or fresh != previous)):
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
            ack, exit_code = _apply_effort(root, conn, record, thread_id,
                                           effort, 'phase', reason)
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
            human = ('attach phase: the queued pending choice %s was '
                     'consumed and set for future turns (acknowledged; '
                     'effective Unknown; the owner TUI keeps manual '
                     'control)' % effort) if consuming else (
                'attach phase: requested %s set for future turns '
                '(acknowledged; kind %s; effective Unknown; the '
                'owner TUI keeps manual control)' % (effort, kind))
            return _emit(args, payload, human)
        finally:
            conn.close()
    finally:
        lease.release()


def cmd_auto(root, args):
    """Explicit re-enable of AUTO control after a suspend or owner pin.

    Owner re-enable acknowledges AUTHORITY, never delivery: an
    unresolved Unknown attempt keeps its original uncertain
    acknowledgement in the record and its byte-identical journal
    receipt; only the block on further updates is lifted, and the
    durable owner-resolution receipt is journaled before the record
    changes. A dangling attempt (interrupted run, no completion
    receipt) is resolved the same way - it never silently becomes a
    successful delivery merely because the owner chooses auto.
    """
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
            uncertain = fresh['effort']['ack'] == 'uncertain'
            dangling = _journal_dangling(root, fresh['thread_id'])
            if uncertain or dangling is not None:
                _journal_append(root, fresh['thread_id'], {
                    'v': JOURNAL_VERSION, 'kind': 'owner-resolution',
                    'at': _now(), 'thread_id': fresh['thread_id'],
                    'acknowledged': ('owner acknowledged authority to '
                                     'continue; delivery stays Unknown')})
            fresh['auto'] = True
            fresh['owner_pin'] = None
            if uncertain:
                # Authority only: the ORIGINAL uncertain acknowledgement
                # is kept intact on the record and in the journal; it is
                # never rewritten as acknowledged-by-owner.
                fresh['effort']['owner_acknowledged'] = _now()
            _save_record(root, fresh)
        payload = _record_view(fresh)
        payload['note'] = ('AUTO re-enabled; native manual changes keep '
                           'winning over automatic control and suspend it '
                           'again when detected; a re-enabled owner '
                           'acknowledges authority to continue, not the '
                           'delivery of any earlier Unknown attempt')
        return _emit(args, payload, 'attach auto: AUTO control re-enabled')
    finally:
        lease.release()


def cmd_manual(root, args):
    """Explicit owner manual LOW/XHIGH override; it pins AUTO selection.

    The owner requirement: a concrete owner choice sets the requested
    effort for future turns (validated against the thread's own model
    advertisement) AND pins/suspends automatic phase selection until
    the owner explicitly re-enables with `attach auto`. It is DISTINCT
    from the one-off cooperating-lead phase signal, it works while AUTO
    is suspended (the owner, not the stored bool, is the authority) and
    it is the one explicit path that may exceed the configured ceiling
    - always reported, never silent. Every attempt keeps its durable
    receipt like any other settings write.
    """
    record = _find_record(root, args.thread_id)
    if record is None:
        raise Refusal('no active attach record in this workspace; attach '
                      'first')
    thread_id = record['thread_id']
    effort = args.effort
    if effort not in pe.RANK:
        raise Refusal('unknown effort: ' + str(effort))
    if effort not in pe.INTERFACE_EFFORTS:
        raise Refusal('only low and xhigh are exposed in this first '
                      'adaptive interface; no medium/high substitution: '
                      + str(effort))
    reason = _bounded_reason(args.reason)
    ceiling = record['ceiling']
    exceeded = pe.RANK.index(effort) > pe.RANK.index(ceiling)
    note = None
    if exceeded:
        note = ('explicit owner override %s exceeds the configured ceiling '
                '%s; applied because the owner is the authority here - '
                'explicit and reported, never silent'
                % (effort, ceiling))
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=None)
    try:
        pin = {'effort': effort, 'reason': reason, 'updated_at': _now()}
        conn = _connect(args, record)
        try:
            conn.initialize()
            loaded = conn.loaded_thread_ids()
            if thread_id not in loaded:
                raise Refusal('the attached thread is no longer loaded in '
                              'the shared daemon (the TUI may have closed '
                              'it); control refused without a fallback')
            reading = conn.read_loaded_thread(thread_id)
            if reading['status_type'] == 'active':
                # A running turn is never relabelled: the owner pin is
                # still pinned locally; re-run this override when the
                # TUI shows the thread idle to apply the concrete level.
                record['auto'] = False
                record['owner_pin'] = pin
                with _record_guard(root):
                    _save_record(root, record)
                payload = {
                    'thread_id': thread_id,
                    'requested': _requested_view(record),
                    'owner_pin': dict(pin),
                    'auto': False,
                    'active_turn': True,
                    'native_requested_effort': reading['reasoning_effort'],
                    'note': ('the thread has a running turn: it is never '
                             'relabelled and no settings changed; the '
                             'owner pin %s is recorded and automatic '
                             'phase selection stays suspended (no pending '
                             'automatic write); re-run this override when '
                             'idle to apply it for future turns' % effort),
                    'effective': 'Unknown',
                    'caution': CAUTION,
                }
                return _emit(args, payload, 'attach manual: owner pin %s '
                                            'recorded; the running turn '
                                            'is never relabelled (no '
                                            'settings call); AUTO '
                                            'suspended; effective Unknown'
                                            % effort)
            if reading['status_type'] != 'idle':
                raise Refusal('the attached thread status is %s; control '
                              'requires an idle thread'
                              % reading['status_type'])
            # Advertisement honesty, same as phase: no level substitution.
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
            ack, exit_code = _apply_effort(root, conn, record, thread_id,
                                           effort, 'manual', reason)
            if ack == 'acknowledged':
                # The owner override replaces any earlier pending
                # automatic request and pins AUTO selection off.
                record['auto'] = False
                record['owner_pin'] = pin
                record['pending'] = None
            else:
                record['auto'] = False
                record['owner_pin'] = pin
            _observe_record_after_apply(conn, record, thread_id)
            with _record_guard(root):
                _save_record(root, record)
            payload = {
                'thread_id': thread_id,
                'requested': _requested_view(record),
                'owner_pin': dict(pin),
                'auto': False,
                'active_turn': False,
                'ceiling': ceiling,
                'advertised': advertised,
                'ceiling_exceeded': exceeded,
                'note': (note if note is not None else
                         ('the owner override %s applies to the thread\'s '
                          'future turns only; automatic phase selection is '
                          'now suspended (pinned) until the owner '
                          're-enables it with `unio lead-session attach '
                          'auto`; the effective provider effort remains '
                          'Unknown' % effort)),
                'effective': 'Unknown',
                'caution': CAUTION,
            }
            if ack == 'unavailable':
                payload['note'] = ('the shared daemon rejected '
                                   'thread/settings/update; effort control '
                                   'is unavailable on this daemon; the '
                                   'owner pin stays recorded: '
                                   + _apply_effort.last_error)
                return _emit(args, payload, 'attach manual: requested %s '
                                            'UNAVAILABLE (typed rejection '
                                            'recorded; owner pin kept): %s'
                                            % (effort,
                                               _apply_effort.last_error),
                                            exit_code=5)
            if ack == 'uncertain':
                payload['note'] = ('the effort update acknowledgement is '
                                   'Unknown; the receipt is preserved and '
                                   'never silently retried; the owner pin '
                                   'stays recorded: '
                                   + _apply_effort.last_error)
                return _emit(args, payload, 'attach manual: requested %s '
                                            'acknowledgement UNKNOWN; '
                                            'verify in the TUI (owner pin '
                                            'kept)' % effort, exit_code=6)
            human = ('attach manual: owner override %s set for future '
                     'turns (acknowledged); AUTO phase selection '
                     'suspended by owner pin; effective Unknown'
                     % effort)
            if exceeded:
                human += ('; explicit request above the configured '
                          'ceiling %s - reported, never silent' % ceiling)
            return _emit(args, payload, human)
        finally:
            conn.close()
    finally:
        lease.release()


def cmd_status(root, args):
    """Local-only status view: zero proxy connections, zero daemon calls.

    Read-only on disk too: the attach store is inspected WITHOUT mkdir,
    chmod or write — an absent store is reported honestly as no record,
    and a present unsafe store refuses instead of being repaired.
    """
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
    pin = record['owner_pin']
    requested = record['effort']['requested'] or 'none'
    ack = record['effort']['ack'] or 'none'
    if record['effort']['ack'] == 'uncertain':
        ack += (' (owner acknowledged authority at %s)'
                % record['effort']['owner_acknowledged']) \
            if record['effort']['owner_acknowledged'] else ''
    pending = record['pending']['effort'] if record['pending'] else 'none'
    auto = ('suspended (owner pin %s)' % pin['effort']
            if pin else ('on' if record['auto'] else 'suspended'))
    native = record['native']['effort'] or 'Unknown'
    human = ('attach status: thread attached, requested %s (ack %s), '
             'pending %s, AUTO %s, native observed %s, effective Unknown'
             % (requested, ack, pending, auto, native))
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
    """Dispatch one ``unio lead-session attach`` control.

    No store is created here: read-only commands (inspect/status) never
    touch the filesystem, and mutating commands create the private store
    only through their own writes, failing closed on unsafe state.
    """
    if args.control == 'inspect':
        return cmd_inspect(root, args)
    if args.control == 'attach':
        return cmd_attach(root, args)
    if args.control == 'phase':
        return cmd_phase(root, args)
    if args.control == 'manual':
        return cmd_manual(root, args)
    if args.control == 'auto':
        return cmd_auto(root, args)
    if args.control == 'status':
        return cmd_status(root, args)
    if args.control == 'detach':
        return cmd_detach(root, args)
    raise Refusal('unknown attach control: ' + str(args.control))
