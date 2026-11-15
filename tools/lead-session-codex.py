#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Owned Codex app-server connection for the native lead-session CLI.

Importable transport component (contract 0532-ADAPTIVE-LEAD-EFFORT-V3)
that owns ONE new Codex app-server process per command: it spawns
``codex app-server --listen stdio://``, initializes the JSON-RPC
connection, verifies the ChatGPT subscription account, queries the model
catalog, starts or resumes the exact owned thread and routes every
notification to a caller-bound handler. It never adopts an existing
unmanaged TUI or connection, never reads auth tokens, never touches
billing and has no paid API fallback.

Process model (explicitly allowed by the V3 contract): one owned process
per CLI command plus the exact durable thread. ``start`` creates the
thread; every later ``run`` resumes the same thread id before its one
``turn/start``. No daemon, desktop app or supervisor is built here, and
nothing from ``tools/codex-worker.py`` is copied wholesale — only the
small proven framing/timeout pieces of its ``Server.rpc`` seam.

Enforced by this component:
- the binary is an explicit owner choice (default ``codex``); an API-key
  environment (``OPENAI_API_KEY``/``CODEX_API_KEY``) is refused like the
  subscription Source refuses it — there is no paid fallback;
- ``initialize`` + ``initialized`` + ``account/read`` happen before any
  thread or turn operation; a non-chatgpt account refuses honestly;
- ``thread/start`` and ``thread/resume`` acknowledgements must carry the
  exact expected thread id; anything missing, malformed or foreign refuses
  — no fallback thread, no adoption, no retry;
- ``thread/read`` returns the provider's own turn statuses for
  reconciliation of an already acknowledged provider turn; it never
  invents a status for an unknown turn;
- every RPC is id-correlated; a provider error reply raises the typed
  ``ProviderRejected`` (injected into the bridge as its rejection class),
  which subclasses ``Refusal`` and preserves the method, code and bounded
  reason: a rejection on initialize/account/model/thread operations
  surfaces as one controlled CLI refusal, never a raw traceback, while
  the bridge still catches it first for ``turn/start`` so typed turn
  rejection stays distinct from missing/uncertain acknowledgements;
  timeouts, exits and malformed wire data raise ``Refusal`` and stay
  untyped/uncertain — the bridge decides how they settle;
- the child's stderr is captured (never discarded) into a bounded
  private most-recent tail so startup and crash diagnostics stay
  actionable without printing unbounded output;
- notifications arriving while an RPC waits are routed in arrival order
  to the bound handler (the bridge holds and replays them itself); the
  connection adds no buffering of its own beyond one line;
- a child exit during a turn wait is flagged promptly (``exited``): the
  final buffered terminal events and stderr diagnostics are drained, the
  caller stops waiting without a tight polling loop, and no success is
  ever inferred from the process exit;
- ``close()`` terminates the owned process group (TERM, brief wait,
  KILL) and never raises; the caller invokes it in a ``finally`` so no
  owned process outlives its command. If the host process is killed
  outright the session leader child can survive; the next command's
  thread/resume reconciliation discovers the turn's real status.

The caller (``tools/lead-session.py``) still owns: admission (STOP,
owner holds, contention) before spawning this connection, the effort
policy, the bridge/core wiring and counting the registered lead exactly
once. See docs/ADAPTIVE-LEAD-EFFORT.md and
docs/development/MANAGED-LEAD-CODEX.md.
"""
import json
import os
import select
import signal
import subprocess
import sys
import time

RPC_TIMEOUT = 8.0
READ_CHUNK = 65536
WIRE_BOUND = 2 * 1024 * 1024
ID_BOUND = 128
LABEL_BOUND = 128
BINARY_BOUND = 1024
MODEL_PAGES = 16
STDERR_CAPTURE_BOUND = 8 * 1024
STDERR_TAIL_BOUND = 512
STDERR_DRAIN_GRACE = 0.05
ERROR_MESSAGE_BOUND = 256
TERMINAL_TURN_STATUS = ('completed', 'failed', 'interrupted')
CAUTION = ('owned connection metadata only; effective model/effort remain '
           'Unknown and no unmanaged TUI is adopted')


class Refusal(Exception):
    """A controlled owned-connection failure; the original error is kept."""


class ProviderRejected(Refusal):
    """Typed explicit provider rejection of one owned RPC call.

    Subclasses ``Refusal`` so a rejection on initialize/account/model/
    thread operations exits as one controlled CLI refusal instead of a
    raw traceback. The bridge still catches it first as its injected
    typed-rejection class, keeping typed ``turn/start`` rejection
    distinct from missing or uncertain acknowledgements.
    """


def _bounded(value, bound, name):
    if (not isinstance(value, str) or not value or '\x00' in value
            or len(value.encode('utf-8', 'replace')) > bound):
        raise Refusal('invalid ' + name)
    return value


class OwnedCodexConnection:
    """One owned app-server process bound to one CLI command.

    The caller sets ``on_notification`` (the bridge's handler) before any
    turn operation; construction itself only spawns the process.
    """

    def __init__(self, binary, *, cwd, rpc_timeout=RPC_TIMEOUT):
        _bounded(binary, BINARY_BOUND, 'codex binary')
        if not isinstance(cwd, str) or not cwd or '\x00' in cwd:
            raise Refusal('invalid owned cwd')
        if os.environ.get('OPENAI_API_KEY') or os.environ.get('CODEX_API_KEY'):
            raise Refusal('subscription owned connection refuses '
                          'API-key environment')
        if type(rpc_timeout) is not float or not 0.1 <= rpc_timeout <= 600.0:
            raise Refusal('invalid owned rpc timeout')
        self._cwd = cwd
        self._rpc_timeout = rpc_timeout
        self.on_notification = None
        self._buffer = b''
        self._counter = 0
        self._closed = False
        self._eof = False
        self._stderr_tail = b''
        self._stderr_eof = False
        try:
            self._child = subprocess.Popen(
                [binary, 'app-server', '--listen', 'stdio://'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, start_new_session=True)
        except OSError as exc:
            raise Refusal('owned app-server connection failed: '
                          '%s: %s' % (type(exc).__name__, exc)) from exc

    # -- wire framing (small reuse of the codex-worker Server seam) ----

    def _send(self, data):
        try:
            self._child.stdin.write((json.dumps(data) + '\n').encode())
            self._child.stdin.flush()
        except (OSError, ValueError) as exc:
            raise Refusal('owned app-server write failed: %s' % exc) from exc

    def _watch(self):
        """Fds worth selecting: stdout plus stderr while it is open."""
        watch = [self._child.stdout]
        if not self._stderr_eof:
            watch.append(self._child.stderr)
        return watch

    def _pump_stderr(self, timeout):
        """Drain pending child stderr into the bounded most-recent tail.

        Only the first select may block for ``timeout`` seconds; the
        capture is bounded so diagnostics stay actionable without
        unbounded memory or output.
        """
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
        """Bounded actionable stderr tail for a refusal message, or ''."""
        if not self._stderr_tail:
            return ''
        tail = self._stderr_tail[-STDERR_TAIL_BOUND:]
        return '; stderr: ' + tail.decode('utf-8', 'replace')

    def stderr_tail(self, bound=STDERR_TAIL_BOUND):
        """The bounded private most-recent stderr diagnostics (or '')."""
        if not isinstance(bound, int) or not 1 <= bound <= STDERR_CAPTURE_BOUND:
            raise Refusal('invalid stderr tail bound')
        return self._stderr_tail[-bound:].decode('utf-8', 'replace')

    @property
    def exited(self):
        """True once the owned process's stdout reached EOF."""
        return self._eof

    def _message(self, deadline):
        while b'\n' not in self._buffer:
            if time.monotonic() >= deadline:
                raise Refusal('owned rpc timeout')
            ready, _, _ = select.select(self._watch(), [], [],
                                       min(.2, max(0.0, deadline - time.monotonic())))
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
                raise Refusal('owned app-server exited' + self._stderr_note())
            self._buffer += data
            if len(self._buffer) > WIRE_BOUND:
                raise Refusal('owned message bound exceeded')
        line, self._buffer = self._buffer.split(b'\n', 1)
        try:
            msg = json.loads(line)
        except (ValueError, UnicodeError, RecursionError) as exc:
            raise Refusal('invalid owned message') from exc
        if (not isinstance(msg, dict)
                or ('method' in msg and (not isinstance(msg['method'], str)
                                          or not isinstance(msg.get('params', {}),
                                                            dict)))):
            raise Refusal('invalid owned message')
        return msg

    def _route(self, msg):
        """One provider message that is not our pending reply."""
        if msg.get('method') is not None:
            if self.on_notification is not None:
                self.on_notification(msg)
        if 'id' in msg and msg.get('method'):
            # Noninteractive owned lead: never auto-approve provider requests.
            self._send({'id': msg['id'],
                        'error': {'code': -32601,
                                  'message': 'Noninteractive owned lead request '
                                             'unsupported'}})

    def rpc(self, method, params):
        """One id-correlated owned RPC call; typed rejection on error reply."""
        self._counter += 1
        request_id = self._counter
        self._send({'id': request_id, 'method': method, 'params': params})
        deadline = time.monotonic() + self._rpc_timeout
        while True:
            msg = self._message(deadline)
            if msg.get('id') == request_id and 'method' not in msg:
                if 'error' in msg:
                    raise self._rejection_error(method, msg['error'])
                return msg.get('result', {})
            self._route(msg)

    @staticmethod
    def _rejection_error(method, error):
        """Typed rejection preserving the provider's method, code, reason."""
        code = None
        message = ''
        if isinstance(error, dict):
            if isinstance(error.get('code'), int):
                code = error['code']
            if isinstance(error.get('message'), str):
                message = error['message'].replace('\x00', '')
        if len(message) > ERROR_MESSAGE_BOUND:
            message = message[:ERROR_MESSAGE_BOUND]
        return ProviderRejected('owned app-server rejected %s (code %s): %s'
                                % (method, code, message))

    def pump(self, timeout):
        """Route pending notifications until the timeout elapses.

        Returns after routing whatever arrived; never raises for a quiet
        connection. A provider exit is flagged (``exited``) after the
        final buffered terminal events and stderr diagnostics are
        drained, so the caller stops waiting promptly without a tight
        polling loop and without inferring any outcome. A malformed wire
        line raises Refusal with the original reason.
        """
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            while b'\n' in self._buffer:
                line, self._buffer = self._buffer.split(b'\n', 1)
                try:
                    msg = json.loads(line)
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise Refusal('invalid owned message') from exc
                if not isinstance(msg, dict):
                    raise Refusal('invalid owned message')
                self._route(msg)
            if self._eof:
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            ready, _, _ = select.select(self._watch(), [], [],
                                       min(.2, remaining))
            if not ready:
                continue
            if self._child.stderr in ready:
                self._pump_stderr(0.0)
            if self._child.stdout not in ready:
                continue
            data = os.read(self._child.stdout.fileno(), READ_CHUNK)
            if not data:
                # Provider exited: drain the final buffered terminal
                # events and last stderr diagnostics, then flag the exit
                # so the caller stops waiting promptly.
                self._eof = True
                self._pump_stderr(STDERR_DRAIN_GRACE)
                continue
            self._buffer += data
            if len(self._buffer) > WIRE_BOUND:
                raise Refusal('owned message bound exceeded')

    # -- owned lifecycle operations ---------------------------------------

    def initialize(self):
        """Initialize the connection and verify the subscription account."""
        self.rpc('initialize', {'clientInfo': {'name': 'unio-managed-lead',
                                               'version': '1'},
                                'capabilities': {'experimentalApi': True}})
        self._send({'method': 'initialized', 'params': {}})
        reply = self.rpc('account/read', {'refreshToken': False})
        account = reply.get('account') if isinstance(reply, dict) else None
        if not isinstance(account, dict) or account.get('type') != 'chatgpt':
            raise Refusal('ChatGPT subscription login required')

    def query_model_efforts(self, model):
        """Advertised reasoning efforts for the pinned model (paged list)."""
        _bounded(model, LABEL_BOUND, 'model')
        cursor = None
        for _ in range(MODEL_PAGES):
            catalog = self.rpc('model/list', {'cursor': cursor, 'limit': 100})
            data = catalog.get('data') if isinstance(catalog, dict) else None
            for entry in data or []:
                if (isinstance(entry, dict)
                        and (entry.get('model') == model
                             or entry.get('id') == model)):
                    efforts = []
                    for opt in entry.get('supportedReasoningEfforts') or []:
                        if (isinstance(opt, dict)
                                and isinstance(opt.get('reasoningEffort'), str)):
                            efforts.append(opt['reasoningEffort'])
                    return efforts
            cursor = catalog.get('nextCursor') if isinstance(catalog, dict) else None
            if not cursor:
                break
        raise Refusal('owned model not advertised: ' + model)

    def start_thread(self, model):
        """Start ONE new owned thread; its exact id is returned and persisted."""
        _bounded(model, LABEL_BOUND, 'model')
        startup = {'model': model, 'modelProvider': 'openai', 'cwd': self._cwd,
                   'allowProviderModelFallback': False,
                   'experimentalRawEvents': False}
        reply = self.rpc('thread/start', startup)
        thread = reply.get('thread') if isinstance(reply, dict) else None
        thread_id = thread.get('id') if isinstance(thread, dict) else None
        _bounded(thread_id, ID_BOUND, 'thread/start acknowledgement')
        return thread_id

    def resume_thread(self, thread_id):
        """Resume the EXACT persisted thread; anything else refuses."""
        _bounded(thread_id, ID_BOUND, 'thread id')
        reply = self.rpc('thread/resume', {'threadId': thread_id})
        thread = reply.get('thread') if isinstance(reply, dict) else None
        resumed = thread.get('id') if isinstance(thread, dict) else None
        if resumed != thread_id:
            raise Refusal('thread/resume acknowledgement missing, malformed '
                          'or foreign; no fallback thread')
        return thread_id

    def read_thread_turns(self, thread_id):
        """The provider's own turn statuses for the exact owned thread."""
        _bounded(thread_id, ID_BOUND, 'thread id')
        reply = self.rpc('thread/read', {'threadId': thread_id,
                                         'includeTurns': True})
        thread = reply.get('thread') if isinstance(reply, dict) else None
        if not isinstance(thread, dict) or thread.get('id') != thread_id:
            raise Refusal('thread/read acknowledgement missing, malformed '
                          'or foreign')
        turns = {}
        for turn in thread.get('turns') or []:
            if (isinstance(turn, dict) and isinstance(turn.get('id'), str)
                    and isinstance(turn.get('status'), str)):
                turns[turn['id']] = turn['status']
        return turns

    # -- teardown -----------------------------------------------------------

    def close(self):
        """Terminate the owned process group; never raises."""
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


def reconcile_status(status):
    """Map one provider turn status to a core terminal status, or None."""
    if status in TERMINAL_TURN_STATUS:
        return status
    return None
