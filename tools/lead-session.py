#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Native `unio lead-session` CLI — adaptive-effort owned lead controller.

Experimental vertical slice for contracts 0532-ADAPTIVE-LEAD-EFFORT
V1/V2/V3. It wires the managed lead core (`tools/managed-lead.py`), the
owned Codex app-server bridge (`tools/managed-lead-codex.py`), the
adaptive effort policy (`tools/lead-effort.py`) and the owned connection
(`tools/lead-session-codex.py`) into one explicit owner-controlled lead
session per workspace. It is NOT a replacement dashboard and it never
adopts an unmanaged TUI or connection: the operator must close or retire
their unmanaged lead before `start`, and there is no supported setter
for the current TUI.

Guarantees kept by this controller:
- explicit owner start with a goal file and model; one managed owner per
  workspace recorded under `coord/lead-effort/owner.json`, claimed
  atomically under the workspace owner lock (owner lock before session
  lock); conflicting or unknown ownership refuses;
- the owned transport (default) owns ONE new Codex app-server process
  per command: `start` initializes the connection, verifies the
  subscription account, queries the model catalog once and starts ONE
  new owned thread whose exact id is persisted; every later `run`
  resumes that exact thread before its one `turn/start`. A per-command
  process plus the exact durable thread is the supported process model;
  no daemon is built. Admission (STOP, owner holds, contention) is
  checked before the owned process is spawned;
- every turn is one explicit `run` with bounded owner input; the decided
  effort is sent explicitly with `turn/start` on the same owned thread;
  nothing is ever sent automatically, so zero model calls happen while
  the lead waits for workers, and status/effort/worker/stop/output open
  no owned connection at all;
- a `run` keeps its owned app-server alive until the turn's terminal
  event or a bounded `--turn-wait` deadline (default 3600s; 0 refuses
  before launch because the process cannot outlive the command). At the
  deadline it requests `turn/interrupt` for the exact proven thread/turn,
  drains terminal events for `--interrupt-drain` seconds and reads the
  provider's own thread state; the interrupt acknowledgement is never
  terminal proof, so without a terminal the turn stays active/Unknown
  (exit 6) and `recover [--interrupt]` handles it later on the SAME
  thread without resending or resetting context;
- a provably never-delivered attempt (typed rejection without
  contradicting activity, a local mapping-bound or policy refusal before
  any turn/start) does not persist its pending-effort or review-wakeup
  consumption; newer concurrent controls are kept and the attempted
  decision stays as evidence;
- a proven active turn is reconciled only inside an explicit `run` from
  the provider's own thread state (`thread/read`), for the exact
  acknowledged provider turn id; an unacknowledged turn is never
  reconciled, replayed or resent;
- STOP blocks new turns (both here and in the injected authority) without
  killing workers, and nothing resumes it automatically: no command in
  this slice clears a STOP, a stopped session stays stopped;
- worker terminal events are explicit controlled events; each queues at
  most one review wakeup consumed by exactly one later turn;
- control state changes are short locked transactions: a per-session
  control lock is held only for the bounded read-modify-write of the
  control state, never across a model/RPC turn, and a run merges its own
  effects into the freshly re-read control state at persist time — so a
  pending effort request, worker terminal wakeup or STOP arriving during
  an active turn survives and is never overwritten by a stale pre-turn
  snapshot (a pending effort applies only from the next turn on);
- mutating controls (run, effort auto/manual/request, worker, stop)
  require the current workspace owner session even when ``--session`` is
  supplied; read-only status/output/effort show stay available for a
  retired session but are explicitly labelled ``historical``;
- run payloads separate the submission acknowledgement (``status``),
  the actual turn outcome (``turn_status``, ``delivery``) and the
  observed native exit (``provider_exited`` plus a bounded private
  stderr tail); exit codes are truthful — 0 only for an observed
  completed turn, nonzero for rejected (2), uncertain (3), failed (4),
  interrupted (5) or unknown (6: accepted but no terminal observed)
  work, and a process exit is never inferred as model success;
- the provider-id mappings its own acknowledgements validated are
  recorded durably (outside the core) and handed explicitly to the next
  bridge; an unproven, incomplete or mismatched handoff refuses instead
  of inventing recovery, and an uncertain (outcome_unknown) turn can
  never be handed over;
- the effective provider model/effort stay Unknown; only requested
  efforts, reasons and immutable per-turn decisions are recorded;
- this first adaptive interface exposes only auto, low and xhigh
  (contract 0532-ADAPTIVE-LEAD-EFFORT-V2): medium and high are not
  choices in adaptive mode, while advertised sets containing them and
  fixed legacy worker/core settings stay compatible.

`--transport fake` keeps the deterministic in-process fake connection as
a test seam. The owned path is the production path; it is exercised
offline against an executable fake Codex app-server speaking the same
JSON-RPC protocol (tests/unio-lead-session-codex.py). No real Codex
model call happens during development or validation. See
docs/ADAPTIVE-LEAD-EFFORT.md.
"""
import argparse
import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import sys
import time

HERE = Path(__file__).resolve().parent
MAX_INPUT_BYTES = 8192
MAX_WORKERS = 32
FAKE_BEHAVIOR_BOUND = 4096
TURN_WAIT_DEFAULT = 3600
INTERRUPT_DRAIN_DEFAULT = 30
FAKE_LOG_BOUND = 256 * 1024
THREAD_FAKE = 'fake-owned-thread-1'
ROUTE_DEFAULT = 'codex-app-server'
BUDGET_DEFAULT = 'codex-shared'
STATE_KEYS = frozenset(
    'session_id workspace route budget_label model thread_id baseline_effort '
    'transport codex_binary fake_efforts goal_sha256 max_requests max_mappings '
    'provider_turns policy stopped waiting workers created_at updated_at '
    'thread_lifecycle'.split())
# Control state written before contract 0532-FIRST-TURN-PERSISTENCE has no
# lifecycle field; it stays readable as ``legacy`` (owned) or ``eager``
# (in-process fake) without rewriting any historical receipt.
LEGACY_STATE_KEYS = STATE_KEYS - {'thread_lifecycle'}
# Owned thread lifecycle. The native app-server materializes a thread's
# rollout only with its first turn (observed with codex-cli 0.169.0 by a
# zero-inference control: no rollout file after thread/start or after a
# graceful exit, and even same-process thread/resume refuses -32600 "no
# rollout found"). So:
#   deferred      start recorded ownership but created no thread yet;
#   started       the first run created the exact thread and persisted its
#                 id BEFORE its first turn/start (delivery may be Unknown);
#   acknowledged  a turn/start on that exact thread was acknowledged;
#   legacy        an earlier start created the thread and closed it;
#   eager         the in-process fake transport (always resumable).
THREAD_LIFECYCLES = ('deferred', 'started', 'acknowledged', 'legacy', 'eager')
WORKER_STATES = ('registered', 'terminal')
CAUTION = ('requested effort only; the effective provider effort remains Unknown; '
           'no unmanaged TUI is adopted')


class Refusal(Exception):
    """A controlled CLI refusal."""


def _load_module(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ml = _load_module('unio_managed_lead', 'managed-lead.py')
bx = _load_module('unio_managed_lead_codex', 'managed-lead-codex.py')
pe = _load_module('unio_lead_effort', 'lead-effort.py')
cx = _load_module('unio_lead_session_codex', 'lead-session-codex.py')
lp = _load_module('unio_lead_session_policy', 'lead-session-policy.py')


def _now():
    import time
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def _state_dir(root):
    path = ml.safe_path(Path(root) / 'coord' / 'lead-effort')
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    except OSError as exc:
        raise Refusal('lead effort state directory unavailable') from exc
    return path


def _state_path(root, session_id):
    return _state_dir(root) / (session_id + '.json')


def _owner_path(root):
    return _state_dir(root) / 'owner.json'


def _validate_state(doc):
    def refuse():
        raise Refusal('invalid lead session control state')

    if not isinstance(doc, dict) or set(doc) != STATE_KEYS:
        refuse()
    for key in ('session_id', 'workspace', 'route', 'budget_label', 'model',
                'baseline_effort', 'transport', 'goal_sha256',
                'created_at', 'updated_at'):
        if not isinstance(doc.get(key), str) or not doc[key] or '\x00' in doc[key]:
            refuse()
    lifecycle = doc.get('thread_lifecycle')
    if lifecycle not in THREAD_LIFECYCLES:
        refuse()
    if (lifecycle == 'eager') != (doc['transport'] == 'fake'):
        refuse()
    if lifecycle == 'deferred':
        if doc.get('thread_id') is not None or doc.get('provider_turns'):
            refuse()
    else:
        thread_id = doc.get('thread_id')
        if (not isinstance(thread_id, str) or not thread_id
                or '\x00' in thread_id
                or len(thread_id.encode('utf-8')) > cx.ID_BOUND):
            refuse()
    if doc['baseline_effort'] not in pe.INTERFACE_EFFORTS:
        refuse()
    if not ml.SESSION_ID.fullmatch(doc['session_id']):
        refuse()
    if doc['transport'] not in ('owned', 'fake'):
        refuse()
    binary = doc.get('codex_binary')
    if not isinstance(binary, str) or '\x00' in binary:
        refuse()
    if doc['transport'] == 'owned':
        if not binary or len(binary.encode('utf-8')) > 1024:
            refuse()
    elif binary != '':
        refuse()
    efforts = doc.get('fake_efforts')
    if doc['transport'] == 'fake':
        if not isinstance(efforts, list) or not efforts:
            refuse()
    elif efforts != []:
        refuse()
    for item in efforts:
        if not isinstance(item, str) or not item or '\x00' in item:
            refuse()
    for key in ('max_requests', 'max_mappings'):
        if type(doc.get(key)) is not int or not 1 <= doc[key] <= 256:
            refuse()
    if doc['max_mappings'] > bx.OWNED_MAPPING_BOUND:
        refuse()
    turns = doc.get('provider_turns')
    if not isinstance(turns, dict) or len(turns) > doc['max_mappings']:
        refuse()
    seen = set()
    for provider_turn, local in turns.items():
        if (not isinstance(provider_turn, str) or not provider_turn
                or not isinstance(local, dict)
                or set(local) != {'turn_id', 'generation'}
                or not isinstance(local.get('turn_id'), str)
                or not ml.TURN_ID.fullmatch(local['turn_id'])
                or type(local.get('generation')) is not int
                or local['generation'] < 1):
            refuse()
        if local['turn_id'] in seen:
            refuse()
        seen.add(local['turn_id'])
    if type(doc.get('stopped')) is not bool or type(doc.get('waiting')) is not bool:
        refuse()
    workers = doc.get('workers')
    if not isinstance(workers, dict) or len(workers) > MAX_WORKERS:
        refuse()
    for worker_id, worker in workers.items():
        if (not isinstance(worker_id, str) or not ml.LABEL.fullmatch(worker_id)
                or not isinstance(worker, dict)
                or set(worker) != {'state', 'updated_at'}
                or worker['state'] not in WORKER_STATES
                or not isinstance(worker['updated_at'], str)):
            refuse()
    if not isinstance(doc.get('policy'), dict):
        refuse()
    return doc


def _load_state(root, session_id):
    path = _state_path(root, session_id)
    if not path.exists():
        raise Refusal('unknown lead session control state')
    data = ml._read_owned_file(path, ml.STATE_BOUND)
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal('invalid lead session control state')
    if isinstance(doc, dict) and set(doc) == LEGACY_STATE_KEYS:
        # Readable pre-0532 state; the next control write adds the field.
        doc['thread_lifecycle'] = ('eager' if doc.get('transport') == 'fake'
                                   else 'legacy')
    _validate_state(doc)
    if doc['session_id'] != session_id:
        raise Refusal('lead session identity mismatch')
    return doc


def _save_state(root, doc):
    _validate_state(doc)
    doc['updated_at'] = _now()
    data = json.dumps(doc, ensure_ascii=False).encode('utf-8')
    if len(data) > ml.STATE_BOUND:
        raise Refusal('lead session control state bound exceeded')
    ml._atomic_write(_state_path(root, doc['session_id']), data)


def _load_owner(root):
    path = _owner_path(root)
    if not path.exists():
        return None
    data = ml._read_owned_file(path, 4096)
    try:
        doc = json.loads(data)
    except (ValueError, UnicodeError, RecursionError):
        raise Refusal('invalid workspace owner record')
    if (not isinstance(doc, dict) or set(doc) != {'session_id'}
            or not isinstance(doc['session_id'], str)
            or not ml.SESSION_ID.fullmatch(doc['session_id'])):
        raise Refusal('invalid workspace owner record')
    return doc


def _save_owner(root, session_id):
    ml._atomic_write(_owner_path(root),
                     json.dumps({'session_id': session_id}).encode('utf-8'))


@contextlib.contextmanager
def _owner_guard(root):
    """Serialize the workspace ownership claim (owner lock before the
    per-session core lock; no other command takes both)."""
    fd = ml._acquire_lock(_state_dir(root) / 'owner.lock')
    try:
        yield
    finally:
        os.close(fd)


@contextlib.contextmanager
def _control_guard(root, session_id):
    """Short per-session control-state transaction lock.

    Held only for the bounded read-modify-write of one session's control
    state — never across a model/RPC turn — so concurrent control
    commands (effort requests, worker terminal events, STOP) serialize
    briefly while an active turn keeps running and its wait loop is
    never blocked by a long lock.
    """
    fd = ml._acquire_lock(_state_dir(root) / (session_id + '.lock'))
    try:
        yield
    finally:
        os.close(fd)


def _require_owner(root, session_id):
    """Mutating controls require the current workspace owner session.

    An explicit ``--session`` for a retired or foreign session can never
    mutate controls or submit turns; only the session recorded under
    ``coord/lead-effort/owner.json`` may.
    """
    owner = _load_owner(root)
    if not isinstance(owner, dict) or owner.get('session_id') != session_id:
        raise Refusal('workspace owner mismatch: mutating lead session '
                      'controls require the current managed owner session')


def _historical(root, session_id):
    """True when this session is not the current workspace owner."""
    try:
        owner = _load_owner(root)
    except Refusal:
        return True
    return not (isinstance(owner, dict)
                and owner.get('session_id') == session_id)


def _closed_rpc(method, params):
    """Rpc callable for read-only commands: zero provider calls, ever."""
    raise Refusal('owned connection not open in this command; read-only '
                  'commands make zero provider calls')


def _read_input(path, bound):
    """Read one bounded private regular file as UTF-8 text."""
    path = ml.safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise Refusal('unsafe input file')
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid()):
            raise Refusal('unsafe input file')
        if st.st_size > bound:
            raise Refusal('input bound exceeded')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            data = stream.read(bound + 1)
    except OSError as exc:
        raise Refusal('input read failed') from exc
    finally:
        if fd is not None:
            os.close(fd)
    if len(data) > bound:
        raise Refusal('input bound exceeded')
    try:
        text = data.decode('utf-8')
    except UnicodeError:
        raise Refusal('input must be UTF-8 text')
    if not text or '\x00' in text:
        raise Refusal('invalid input')
    return text


class FakeLeadRPC:
    """Deterministic fake owned app-server connection (test transport).

    Records every rpc call to a bounded JSONL log so tests can prove call
    counts. Implements only `model/list` and `turn/start`; lifecycle
    notifications are delivered through the bound bridge exactly like the
    real notification loop would. The behavior sidecar selects ok, reject,
    raise or hold per call; `release_held` lets a held turn complete later
    as a pure lifecycle event (zero model calls).
    """

    def __init__(self, log_path, thread, model, efforts, behavior_path):
        self._log_path = log_path
        self._thread = thread
        self._model = model
        self._efforts = tuple(efforts)
        self._behavior_path = behavior_path
        self.bridge = None
        self.last_provider_turn = None

    def _behavior(self):
        if not self._behavior_path.exists():
            return {'behavior': 'ok'}
        data = ml._read_owned_file(self._behavior_path, FAKE_BEHAVIOR_BOUND)
        try:
            doc = json.loads(data)
        except (ValueError, UnicodeError, RecursionError):
            raise Refusal('invalid fake behavior record')
        if not isinstance(doc, dict) or doc.get('behavior') not in (
                None, 'ok', 'reject', 'raise', 'hold'):
            raise Refusal('invalid fake behavior record')
        if 'release_held' in doc and type(doc['release_held']) is not bool:
            raise Refusal('invalid fake behavior record')
        return doc

    def _log(self, method, params):
        line = (json.dumps({'method': method, 'params': params},
                           ensure_ascii=False) + '\n').encode('utf-8')
        if not self._log_path.exists():
            try:
                fd = os.open(self._log_path, os.O_WRONLY | os.O_CREAT
                             | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            except OSError:
                raise Refusal('unsafe fake rpc log')
            os.close(fd)
        else:
            try:
                size = os.stat(self._log_path).st_size
            except OSError:
                raise Refusal('fake rpc log unavailable')
            if size + len(line) > FAKE_LOG_BOUND:
                raise Refusal('fake rpc log bound exceeded')
        ml._append_owned(self._log_path, line)

    def _count_turn_starts(self):
        if not self._log_path.exists():
            return 0
        data = ml._read_owned_file(self._log_path, FAKE_LOG_BOUND)
        count = 0
        for line in data.splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                raise Refusal('fake rpc log corrupt')
            if rec.get('method') == bx.START_METHOD:
                count += 1
        return count

    def _notify(self, method, params):
        if self.bridge is None:
            raise Refusal('fake transport bridge not bound')
        return self.bridge.handle_notification({'method': method,
                                                 'params': params})

    def _emit_started(self, provider_turn):
        self._notify('turn/started', {'threadId': self._thread,
                                       'turn': {'id': provider_turn,
                                                'status': 'inProgress'}})

    def __call__(self, method, params):
        self._log(method, params)
        if method == 'model/list':
            return {'data': [{'id': self._model,
                              'supportedReasoningEfforts': [
                                  {'reasoningEffort': effort,
                                   'description': 'fake effort ' + effort}
                                  for effort in self._efforts]}]}
        if method == bx.START_METHOD:
            behavior = self._behavior().get('behavior') or 'ok'
            if behavior == 'reject':
                raise bx.RPCRejected('fake provider rejected turn/start')
            if behavior == 'raise':
                raise RuntimeError('fake owned connection failed')
            provider_turn = 'provider-turn-%d' % (self._count_turn_starts())
            self._emit_started(provider_turn)
            self._notify('item/agentMessage/delta',
                         {'threadId': self._thread, 'turnId': provider_turn,
                          'itemId': 'item-1', 'delta': 'fake turn output'})
            self.last_provider_turn = provider_turn
            return {'turn': {'id': provider_turn, 'status': 'inProgress'}}
        raise Refusal('fake transport method unsupported: ' + str(method))

    def behavior(self):
        """Read the fake behavior sidecar (a test fixture, never a secret)."""
        return self._behavior()

    def notify_terminal(self, provider_turn, status='completed'):
        """Deliver one terminal lifecycle notification (zero rpc calls)."""
        return self._notify('turn/completed',
                            {'threadId': self._thread,
                             'turn': {'id': provider_turn,
                                      'status': status}})

    def complete_last(self):
        """Deliver the held fake turn's terminal lifecycle event."""
        if self.last_provider_turn is None:
            return False
        if (self._behavior().get('behavior') or 'ok') != 'ok':
            return False
        self._notify('turn/completed',
                     {'threadId': self._thread,
                      'turn': {'id': self.last_provider_turn,
                               'status': 'completed'}})
        return True


class SendProbe:
    """Counting wrapper around one owned rpc callable.

    Counts ``turn/start`` calls so the effort transport can prove that a
    refusal raised by the bridge happened before any turn was sent (known
    non-delivery) instead of trusting code inspection alone.
    """

    def __init__(self, rpc):
        self._rpc = rpc
        self.turn_starts = 0

    def __call__(self, method, params):
        if method == bx.START_METHOD:
            self.turn_starts += 1
        return self._rpc(method, params)


class EffortTransport:
    """Core transport seam deciding the explicit effort at send time.

    Records exactly what this attempt consumed (at most one review wakeup
    and at most one pending effort request) so a provably never-delivered
    attempt can restore only its own consumption at persist time. A policy
    or bridge refusal raised before any ``turn/start`` is returned as a
    known non-delivery (``rejected``, ``rpc_sent: False``); the core still
    upgrades it to uncertain on contradicting activity.
    """

    def __init__(self, bridge, policy, kind, reason):
        self.bridge = bridge
        self.policy = policy
        self.kind = kind
        self.reason = reason
        self.probe = None
        self.last_decision = None
        self.attempted = False
        self.consumed = None

    def _not_sent(self, reason):
        return {'status': 'rejected', 'rpc_sent': False,
                'reason': 'known non-delivery before any turn/start: '
                          + str(reason)}

    def send_turn(self, facts):
        self.attempted = True
        self.consumed = {'wakeup': None, 'pending': None}
        if self.bridge is None:
            return self._not_sent('owned transport unavailable')
        try:
            if self.kind is not None:
                kind, reason = self.kind, self.reason
            else:
                wakeup = self.policy.consume_wakeup()
                if wakeup is not None:
                    self.consumed['wakeup'] = dict(wakeup)
                    kind = 'review'
                    reason = 'worker terminal wakeup: ' + wakeup['worker']
                else:
                    kind = 'coordination'
                    reason = None
            pending = self.policy.status()['pending_next_turn']
            decision = self.policy.decide_turn(facts['turn_id'], kind, reason)
        except pe.Refusal as exc:
            return self._not_sent(exc)
        if decision['source'] == 'pending':
            self.consumed['pending'] = pending
        self.last_decision = dict(decision)
        out = dict(facts)
        out['effort'] = decision['effort']
        before = self.probe.turn_starts if self.probe is not None else None
        try:
            return self.bridge.send_turn(out)
        except bx.Refusal as exc:
            if before is None or self.probe.turn_starts != before:
                raise  # a turn/start may exist: stays uncertain in the core
            return self._not_sent(exc)


def _authority(root, session_id):
    def authority(facts):
        state = _load_state(root, session_id)
        owner = _load_owner(root)
        if not isinstance(owner, dict) or owner.get('session_id') != session_id:
            raise Refusal('workspace owner mismatch')
        if facts.get('action') == 'next_turn':
            if state['stopped']:
                raise Refusal('lead session stopped: new turns are blocked')
            if lp.is_project_stop_active(root):
                raise Refusal('project STOP is active: new turns are blocked')
        return {'role': 'lead', 'authorized': True}
    return authority


def _ownership(root, session_id):
    def ownership(facts):
        state = _load_state(root, session_id)
        if state['workspace'] != str(ml.safe_path(Path(root))):
            raise Refusal('workspace mismatch')
        return True
    return ownership


def _open(root, state):
    """Rebuild the session, bridge and policy from durable state.

    Zero provider calls in every read-only command: the owned transport
    gets a closed rpc callable that refuses if anything ever tries to
    send. The proven provider mappings are handed over explicitly. A
    session with an unacknowledged (outcome_unknown) turn cannot be
    handed over; it reopens for inspection only, so an identical request
    replay can still return its recorded result while every new turn
    refuses.
    """
    policy = pe.AdaptiveEffortPolicy.load(state['policy'])
    wrapper = EffortTransport(None, policy, None, None)
    session = ml.LeadSession(ml.safe_path(Path(root)), state['session_id'],
                             transport=wrapper,
                             authority=_authority(root, state['session_id']),
                             ownership=_ownership(root, state['session_id']))
    if state['transport'] == 'fake':
        directory = _state_dir(root)
        rpc = FakeLeadRPC(directory / (state['session_id'] + '.rpclog.jsonl'),
                          state['thread_id'], state['model'],
                          state['fake_efforts'],
                          directory / (state['session_id'] + '.fake.json'))
    else:
        rpc = None
    probe = SendProbe(rpc if rpc is not None else _closed_rpc)
    wrapper.probe = probe
    try:
        bridge = bx.CodexLeadTransport(
            probe,
            state['thread_id'], model=state['model'],
            effort=state['baseline_effort'],
            supported_efforts=policy.supported(),
            max_mappings=state['max_mappings'],
            prior_mappings=state['provider_turns'])
        if rpc is not None:
            rpc.bridge = bridge
        bridge.bind(session)
    except (bx.Refusal, ml.Refusal):
        # Inspection-only reopen: no sending is possible from this bind
        # (the core refuses new turns on non-open states and the bridge
        # refuses sends), but recorded replay results stay readable.
        bridge = bx.CodexLeadTransport(
            probe,
            state['thread_id'], model=state['model'],
            effort=state['baseline_effort'],
            supported_efforts=policy.supported(),
            max_mappings=state['max_mappings'])
        if rpc is not None:
            rpc.bridge = bridge
        bridge.bind(session)
    wrapper.bridge = bridge
    return session, bridge, rpc, policy, wrapper


def _persist(root, state, policy, bridge, session):
    """Persist policy and exactly the proven mappings for recorded turns.

    The caller holds the per-session control lock and loaded ``state``
    inside that same short transaction, so this plain save is consistent.
    """
    view = session.status(session_id=state['session_id'])
    recorded = set()
    for item in view['history']:
        if item['status'] != 'rejected':
            recorded.add(item['turn_id'])
    if view['last_turn']:
        recorded.add(view['last_turn']['turn_id'])
    if view['turn']:
        recorded.add(view['turn']['turn_id'])
    merged = dict(state['provider_turns'])
    for provider_turn, local in bridge.status()['mappings'].items():
        merged[provider_turn] = local
    state['provider_turns'] = {
        provider_turn: local for provider_turn, local in merged.items()
        if local['turn_id'] in recorded}
    if len(state['provider_turns']) > state['max_mappings']:
        raise Refusal('provider turn mapping bound exceeded')
    state['policy'] = policy.snapshot()
    _save_state(root, state)


def _merge_policy_snapshot(base, disk, live, restore=False):
    """Merge one run's own policy effects into the concurrent disk state.

    ``base`` is the snapshot the run loaded when it started, ``disk`` the
    current on-disk snapshot (possibly changed by concurrent control
    commands during the active turn) and ``live`` the run's in-memory
    snapshot after its own effects. Concurrent pending effort requests,
    worker wakeups and manual/auto mode changes are never overwritten by
    the stale pre-turn snapshot; the run's own consumption (at most one
    pending request, at most one wakeup) and its immutable decisions are
    applied on top. A pending effort arriving after the current turn's
    decision therefore survives persistence and applies only next turn.

    With ``restore`` (this attempt was provably never delivered: a typed
    rejection without contradicting activity, or a known local refusal
    before any turn/start) none of this attempt's consumption is applied:
    its wakeup and pending request stay exactly as they are on disk (the
    run never wrote them away), newer concurrent pending/mode/wakeup
    changes are kept, and only its decision record is appended as attempt
    evidence. Uncertain or accepted attempts are never restored.
    """
    if restore:
        merged = dict(disk)
        disk_ids = {item['turn_id'] for item in disk['decisions']}
        merged['decisions'] = (disk['decisions']
                               + [item for item in live['decisions']
                                  if item['turn_id'] not in disk_ids])
        merged['decisions'] = merged['decisions'][-pe.MAX_DECISIONS:]
        return merged
    merged = dict(live)
    if disk['mode'] != base['mode'] or disk['manual'] != base['manual']:
        merged['mode'] = disk['mode']
        merged['manual'] = disk['manual']
    if disk['pending'] != base['pending']:
        # A newer concurrent request wins over this turn's consumption.
        merged['pending'] = disk['pending']
    if disk['wakeups'] != base['wakeups']:
        consumed_count = len(base['wakeups']) - len(live['wakeups'])
        consumed = base['wakeups'][:consumed_count]
        merged['wakeups'] = list(disk['wakeups'])
        for item in consumed:
            for index, candidate in enumerate(merged['wakeups']):
                if candidate == item:
                    del merged['wakeups'][index]
                    break
        merged['wakeups_consumed'] = disk['wakeups_consumed'] + consumed_count
    disk_ids = {item['turn_id'] for item in disk['decisions']}
    merged['decisions'] = (disk['decisions']
                           + [item for item in live['decisions']
                              if item['turn_id'] not in disk_ids])
    merged['decisions'] = merged['decisions'][-pe.MAX_DECISIONS:]
    return merged


def _persist_run(root, base_state, policy, bridge, session, restore=False):
    """Locked merge-persist for one run command; returns the fresh state.

    The run's pre-turn in-memory snapshot is never written over the
    control state: under the short per-session control lock the current
    on-disk state is re-read and only this run's own effects (proven
    provider mappings, its policy decisions and consumption) are merged
    in. Concurrent pending effort requests, worker terminal wakeups and
    STOP flags written during the active turn survive; the lock is never
    held across the model/RPC turn itself.
    """
    view = session.status(session_id=base_state['session_id'])
    recorded = set()
    for item in view['history']:
        if item['status'] != 'rejected':
            recorded.add(item['turn_id'])
    if view['last_turn']:
        recorded.add(view['last_turn']['turn_id'])
    if view['turn']:
        recorded.add(view['turn']['turn_id'])
    proven = dict(bridge.status()['mappings'])
    with _control_guard(root, base_state['session_id']):
        disk = _load_state(root, base_state['session_id'])
        merged = dict(disk['provider_turns'])
        for provider_turn, local in proven.items():
            merged[provider_turn] = local
        disk['provider_turns'] = {
            provider_turn: local for provider_turn, local in merged.items()
            if local['turn_id'] in recorded}
        if len(disk['provider_turns']) > disk['max_mappings']:
            raise Refusal('provider turn mapping bound exceeded')
        if disk['thread_lifecycle'] == 'started' and disk['provider_turns']:
            # A turn/start on the exact recorded thread was acknowledged.
            disk['thread_lifecycle'] = 'acknowledged'
        disk['policy'] = _merge_policy_snapshot(base_state['policy'],
                                                 disk['policy'],
                                                 policy.snapshot(),
                                                 restore=restore)
        _save_state(root, disk)
    return disk


def _compute_effort_display(view, policy, state):
    pol_status = policy.status()
    decisions = policy.decisions()
    active_turn = view.get('turn')
    is_active = (active_turn is not None
                 and view.get('state') in ('pending', 'running', 'outcome_unknown'))

    active_decision = None
    if is_active:
        tid = active_turn['turn_id']
        for d in decisions:
            if d.get('turn_id') == tid:
                active_decision = d
                break

    is_not_started = (
        not is_active
        and view.get('requests_recorded', 0) == 0
        and view.get('turns_completed', 0) == 0
        and view.get('turns_failed', 0) == 0
        and not view.get('history')
        and not decisions
    )

    last_attempt = None
    if decisions:
        last_d = decisions[-1]
        outcome = _turn_terminal_status(view, last_d.get('turn_id'))
        last_attempt = {
            'turn_id': last_d.get('turn_id'),
            'effort': last_d.get('effort'),
            'kind': last_d.get('kind'),
            'source': last_d.get('source'),
            'status': outcome or 'unknown',
        }
    elif view.get('last_turn'):
        lt = view['last_turn']
        last_attempt = {
            'turn_id': lt.get('turn_id'),
            'effort': 'Unknown',
            'kind': None,
            'source': None,
            'status': lt.get('status', 'unknown'),
        }

    pending_next = pol_status.get('pending_next_turn')
    mode = pol_status.get('mode', 'auto')
    policy_mode = 'adaptive' if mode == 'auto' else 'manual'

    if is_active:
        active_effort = active_decision['effort'] if active_decision else 'Unknown'
        active_kind = active_decision.get('kind') if active_decision else None
        active_source = active_decision.get('source') if active_decision else None
        active_status = view.get('state')
    elif is_not_started:
        active_effort = None
        active_kind = None
        active_source = None
        active_status = 'not started'
    else:
        active_effort = None
        active_kind = None
        active_source = None
        active_status = 'waiting' if _waiting_on_workers(state) else 'idle'

    # Delivery of the exact active turn's request stays distinct from its
    # requested effort: 'accepted' (acknowledged, running), 'pending' (not
    # yet acknowledged) or 'uncertain' (outcome_unknown: never shown as an
    # ordinary confirmed active turn; effective remains Unknown).
    delivery = None
    if is_active:
        delivery = {'running': 'accepted', 'pending': 'pending',
                    'outcome_unknown': 'uncertain'}[view.get('state')]

    current_request = {
        'active': is_active,
        'state': active_status,
        'delivery': delivery,
        'effort': active_effort,
        'kind': active_kind,
        'source': active_source,
        'turn_id': active_turn['turn_id'] if is_active else None,
        'pending_next_turn': dict(pending_next) if pending_next else None,
    }

    return {
        'active_effort': active_effort,
        'active_status': active_status,
        'current_request': current_request,
        'policy_mode': policy_mode,
        'mode': mode,
        'ceiling': pol_status.get('ceiling'),
        'manual_effort': pol_status.get('manual_effort'),
        'pending_next_turn': dict(pending_next) if pending_next else None,
        'last_attempt': last_attempt,
        'effective': 'Unknown',
        'caution': CAUTION,
    }


def _waiting_on_workers(state):
    """Truthful waiting: flagged AND at least one registered worker is not
    terminal, or a terminal worker's review wakeup is still unconsumed."""
    if not state.get('waiting'):
        return False
    if any(w.get('state') != 'terminal'
           for w in state.get('workers', {}).values()):
        return True
    return bool(state.get('policy', {}).get('wakeups'))


def _active_delivery_note(disp):
    delivery = disp['current_request'].get('delivery')
    if delivery == 'uncertain':
        return '; delivery uncertain, effective Unknown'
    if delivery == 'pending':
        return '; delivery not yet acknowledged'
    return ''


def _clear_waiting_after_completion(root, session_id):
    """After an observed completed turn, clear a stale `waiting` flag.

    Under the short control lock the fresh disk state is re-read, so a
    concurrent `worker register`/`wait` on a non-terminal worker (or a
    still-unconsumed review wakeup) keeps the lead waiting. Zero calls.
    """
    with _control_guard(root, session_id):
        disk = _load_state(root, session_id)
        if disk['waiting'] and not _waiting_on_workers(disk):
            disk['waiting'] = False
            _save_state(root, disk)


def _format_status_human(view, disp, state):
    hist_str = (' (historical: not the current workspace owner)'
                if view.get('historical') else '')
    pending = disp.get('pending_next_turn')
    pending_str = (', pending next: %s' % pending['effort']) if pending else ''
    mode = disp['policy_mode']
    if mode == 'manual' and disp.get('manual_effort'):
        policy_label = 'manual (%s)' % disp['manual_effort']
    else:
        policy_label = mode

    last_str = ''
    if disp.get('last_attempt'):
        la = disp['last_attempt']
        eff = la['effort']
        st = la['status']
        if st == 'rejected':
            last_str = '; last attempt: %s (rejected, not delivered)' % eff
        else:
            last_str = '; last requested: %s (%s)' % (eff, st)

    if disp['current_request']['active']:
        effort_part = 'effort %s (policy %s%s%s)' % (
            disp['active_effort'], policy_label, pending_str,
            _active_delivery_note(disp))
    elif disp['active_status'] == 'not started':
        effort_part = 'effort not started (policy %s%s)' % (
            policy_label, pending_str)
    else:
        effort_part = 'effort no active turn (policy %s%s%s)' % (
            policy_label, pending_str, last_str)

    return ('lead session %s: state %s, generation %d, %s, stopped %s, '
            'waiting %s%s'
            % (state['session_id'], view['state'], view['generation'],
               effort_part, view['stopped'], _waiting_on_workers(state),
               hist_str))


def _format_effort_show(disp, status):
    hist_str = (' (historical: not the current workspace owner)'
                if status.get('historical') else '')
    pending = disp.get('pending_next_turn')
    pending_str = (', pending next: %s' % pending['effort']) if pending else ''
    mode = disp['policy_mode']
    ceiling = disp.get('ceiling')
    if mode == 'manual' and disp.get('manual_effort'):
        policy_label = 'manual (%s)' % disp['manual_effort']
    else:
        policy_label = mode

    last_str = ''
    if disp.get('last_attempt'):
        la = disp['last_attempt']
        eff = la['effort']
        st = la['status']
        if st == 'rejected':
            last_str = '; last attempt: %s (rejected, not delivered)' % eff
        else:
            last_str = '; last requested: %s (%s)' % (eff, st)

    if disp['current_request']['active']:
        req = disp['current_request']
        return ('requested effort: %s (active turn %s, kind %s; '
                'policy %s, ceiling %s%s%s)%s'
                % (disp['active_effort'], req.get('turn_id'), req.get('kind'),
                   policy_label, ceiling, pending_str,
                   _active_delivery_note(disp), hist_str))
    elif disp['active_status'] == 'not started':
        return ('requested effort: not started (policy %s, ceiling %s%s)%s'
                % (policy_label, ceiling, pending_str, hist_str))
    else:
        return ('requested effort: no active turn (policy %s, ceiling %s%s%s)%s'
                % (policy_label, ceiling, pending_str, last_str, hist_str))


def _session_view(root, state, session, bridge, policy):
    view = session.status(session_id=state['session_id'])
    effort_disp = _compute_effort_display(view, policy, state)
    return {
        'session_id': state['session_id'],
        'workspace': state['workspace'],
        'route': state['route'], 'budget_label': state['budget_label'],
        'model': state['model'], 'thread_id': state['thread_id'],
        'thread_lifecycle': state['thread_lifecycle'],
        'transport': state['transport'],
        'baseline_effort': state['baseline_effort'],
        'generation': view['generation'], 'state': view['state'],
        'turn': view['turn'], 'last_turn': view['last_turn'],
        'turns_completed': view['turns_completed'],
        'turns_failed': view['turns_failed'],
        'requests_recorded': view['requests_recorded'],
        'max_requests': view['max_requests'],
        'max_mappings': state['max_mappings'],
        'provider_turns_recorded': len(state['provider_turns']),
        'stopped': state['stopped'], 'waiting': _waiting_on_workers(state),
        'workers': {wid: dict(worker) for wid, worker in
                    state['workers'].items()},
        'effort': policy.status(),
        'effort_display': effort_disp,
        'current_request': effort_disp['current_request'],
        'decisions': [dict(item, outcome=_turn_terminal_status(
            view, item['turn_id'])) for item in policy.decisions()],
        'goal_sha256': state['goal_sha256'],
        'created_at': state['created_at'], 'updated_at': state['updated_at'],
        'historical': _historical(root, state['session_id']),
        'effective': 'Unknown',
        'caution': CAUTION,
    }


def _emit(args, payload, human):
    if getattr(args, 'json', False):
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(human)


def _refuse_owner_replacement(root):
    """Fail-closed check before a new start may replace the recorded owner.

    Runs before any new process, thread or inference (zero calls). Refuses
    when the owner record or the owner's control state is unreadable or
    unknown (no implicit reset or forged ownership), when the owner is not
    stopped, and when a stopped owner still has a PROVEN unresolved active
    turn (an acknowledged provider turn id without an observed terminal):
    replacing it would make same-thread `recover` impossible. A stopped
    owner whose active turn was never acknowledged (no provider id) has no
    recovery path by design and may be replaced; its views stay readable
    as historical.
    """
    owner = _load_owner(root)  # an invalid/unreadable record refuses here
    if not isinstance(owner, dict):
        return
    sid = owner['session_id']
    try:
        existing = _load_state(root, sid)
        session = _open(root, existing)[0]
        view = session.status(session_id=sid)
    except (Refusal, ml.Refusal, bx.Refusal) as exc:
        raise Refusal('current workspace owner %s has unreadable or unknown '
                      'control state (%s); refusing to replace it. Inspect '
                      'coord/lead-effort/; nothing was reset or started'
                      % (sid, exc))
    if not existing['stopped']:
        raise Refusal('workspace already has an active managed lead '
                      'session: ' + sid)
    turn = view.get('turn')
    if (turn is not None
            and view.get('state') in ('pending', 'running', 'outcome_unknown')
            and _provider_turn_for(existing, turn['turn_id']) is not None):
        if existing['transport'] == 'owned':
            hint = ('recover it on the same thread first: unio lead-session '
                    'recover --session %s --interrupt' % sid)
        else:
            hint = 'the fake transport has no recovery path'
        raise Refusal('stopped owner session %s still has a proven '
                      'unresolved active turn %s; refusing to replace it '
                      '(%s)' % (sid, turn['turn_id'], hint))


def _cmd_start(root, args):
    goal = _read_input(args.goal, MAX_INPUT_BYTES)
    goal_sha = hashlib.sha256(goal.encode('utf-8')).hexdigest()
    _refuse_owner_replacement(root)
    if args.ceiling not in pe.RANK:
        raise Refusal('ceiling must be a known effort no higher than xhigh')
    if args.ceiling not in pe.INTERFACE_EFFORTS:
        raise Refusal('ceiling must be low or xhigh in this first adaptive '
                      'interface: ' + args.ceiling)
    if args.effort != 'auto':
        if args.effort not in pe.RANK:
            raise Refusal('unknown effort: ' + args.effort)
        if args.effort not in pe.INTERFACE_EFFORTS:
            raise Refusal('only auto, low and xhigh are exposed in this '
                          'first adaptive interface: ' + args.effort)
    baseline = args.ceiling if args.effort == 'auto' else args.effort
    if args.transport == 'owned':
        return _cmd_start_owned(root, args, goal_sha, baseline)
    efforts = [item.strip() for item in args.fake_efforts.split(',') if item.strip()]
    if not efforts:
        raise Refusal('no fake efforts advertised')
    budget_label = args.budget_label or BUDGET_DEFAULT
    policy = pe.AdaptiveEffortPolicy(ceiling=args.ceiling)
    wrapper = EffortTransport(None, policy, None, None)
    session = ml.create_lead_session(
        ml.safe_path(Path(root)), transport=wrapper,
        authority=_authority(root, 'pending'),
        ownership=_ownership(root, 'pending'),
        workspace=args.workspace, budget_label=budget_label,
        route=args.route, model=args.model, effort=baseline,
        max_requests=args.max_requests)
    sid = session.session_id
    directory = _state_dir(root)
    rpc = FakeLeadRPC(directory / (sid + '.rpclog.jsonl'),
                      THREAD_FAKE, args.model, efforts,
                      directory / (sid + '.fake.json'))

    def query():
        reply = rpc('model/list', {'modelProvider': None, 'includeHidden': False})
        data = reply.get('data') if isinstance(reply, dict) else None
        if not isinstance(data, list):
            raise Refusal('model/list returned no models')
        for entry in data:
            if isinstance(entry, dict) and entry.get('id') == args.model:
                options = entry.get('supportedReasoningEfforts') or []
                return [opt.get('reasoningEffort') for opt in options
                        if isinstance(opt, dict)]
        raise Refusal('owned model not advertised: ' + args.model)

    policy.query_supported(query)
    if args.effort != 'auto':
        policy.set_manual(args.effort, 'explicit owner start effort')
    bridge = bx.CodexLeadTransport(
        rpc, THREAD_FAKE, model=args.model, effort=baseline,
        supported_efforts=policy.supported(),
        max_mappings=args.max_mappings, prior_mappings={})
    rpc.bridge = bridge
    bridge.bind(session)
    wrapper.bridge = bridge
    now = _now()
    state = {
        'session_id': sid, 'workspace': args.workspace, 'route': args.route,
        'budget_label': budget_label, 'model': args.model,
        'thread_id': THREAD_FAKE, 'baseline_effort': baseline,
        'transport': 'fake', 'codex_binary': '', 'fake_efforts': efforts,
        'goal_sha256': goal_sha,
        'max_requests': args.max_requests, 'max_mappings': args.max_mappings,
        'provider_turns': {}, 'policy': policy.snapshot(), 'stopped': False,
        'waiting': False, 'workers': {}, 'created_at': now, 'updated_at': now,
        'thread_lifecycle': 'eager',
    }
    _save_state(root, state)
    _save_owner(root, sid)
    view = _session_view(root, state, session, bridge, policy)
    pol_mode = 'adaptive' if args.effort == 'auto' else ('manual (%s)' % args.effort)
    _emit(args, view, 'lead session started: %s (model %s, effort not started, '
                      'policy %s, ceiling %s)'
          % (sid, args.model, pol_mode, args.ceiling))
    return 0


def _cmd_start_owned(root, args, goal_sha, baseline):
    """Start one owned app-server connection and record the owned session.

    Contention, STOP, policy and owner holds are checked before the owned
    process is spawned; the ownership claim is atomic under the workspace
    owner lock, so a concurrent start refuses honestly instead of creating a
    second managed owner. The connection verifies the subscription account
    and the model catalog; no thread and no turn is started here. The
    native app-server materializes a thread only with its first turn, and
    a thread whose creating process has closed can never be resumed, so
    the exact thread is created by the first ``run`` in its own process,
    immediately before its first turn/start (``thread_lifecycle``
    ``deferred``). No bootstrap or dummy model request exists.
    """
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=args.budget_label)
    try:
        with _owner_guard(root):
            _refuse_owner_replacement(root)
            conn = cx.OwnedCodexConnection(args.codex_binary, cwd=str(root))
            try:
                conn.initialize()
                efforts = conn.query_model_efforts(args.model)
            finally:
                conn.close()
            policy = pe.AdaptiveEffortPolicy(ceiling=args.ceiling)
            policy.query_supported(lambda: list(efforts))
            if args.effort != 'auto':
                policy.set_manual(args.effort, 'explicit owner start effort')
            wrapper = EffortTransport(None, policy, None, None)
            session = ml.create_lead_session(
                ml.safe_path(Path(root)), transport=wrapper,
                authority=_authority(root, 'pending'),
                ownership=_ownership(root, 'pending'),
                workspace=args.workspace, budget_label=lead_group,
                route=args.route, model=args.model, effort=baseline,
                max_requests=args.max_requests)
            sid = session.session_id
            state = {
                'session_id': sid, 'workspace': args.workspace,
                'route': args.route, 'budget_label': lead_group,
                'model': args.model, 'thread_id': None,
                'thread_lifecycle': 'deferred',
                'baseline_effort': baseline, 'transport': 'owned',
                'codex_binary': args.codex_binary, 'fake_efforts': [],
                'goal_sha256': goal_sha,
                'max_requests': args.max_requests,
                'max_mappings': args.max_mappings,
                'provider_turns': {}, 'policy': policy.snapshot(),
                'stopped': False, 'waiting': False, 'workers': {},
                'created_at': _now(), 'updated_at': _now(),
            }
            _save_state(root, state)
            _save_owner(root, sid)
    finally:
        lease.release()
    session, bridge, rpc, policy, wrapper = _open(root, state)
    view = _session_view(root, state, session, bridge, policy)
    pol_mode = 'adaptive' if args.effort == 'auto' else ('manual (%s)' % args.effort)
    _emit(args, view, 'lead session started: %s (model %s, effort not started, '
                      'policy %s, ceiling %s, owned thread created by the '
                      'first turn)'
          % (sid, args.model, pol_mode, args.ceiling))
    return 0


def _reconcile_active(root, state, session, conn, view, turns=None):
    """Reconcile one proven active turn from the provider's own thread state.

    Only the exact provider turn id validated by a previous acknowledgement
    can be reconciled, and only inside this explicit owner `run`. An
    unacknowledged turn, a provider that no longer reports the turn, or a
    still-running turn changes nothing: the core refuses the new turn
    honestly instead of inventing recovery.
    """
    if view['state'] not in ('pending', 'running', 'outcome_unknown'):
        return view
    active = view['turn']
    if active is None:
        return view
    provider_turn = None
    for provider_id, local in state['provider_turns'].items():
        if local['turn_id'] == active['turn_id']:
            provider_turn = provider_id
    if provider_turn is None:
        return view
    if turns is None:
        turns = conn.read_thread_turns(state['thread_id'])
    status = cx.reconcile_status(turns.get(provider_turn))
    if status is None:
        return view
    session.observe_terminal(session_id=state['session_id'],
                             generation=active['generation'],
                             turn_id=active['turn_id'], status=status,
                             exit_code=None)
    return session.status(session_id=state['session_id'])


def _turn_terminal_status(view, turn_id):
    """The recorded terminal status of one turn from a core view, or None.

    Covers the active turn (still running), the latest turn and the
    bounded history, so an idempotent replay of an already recorded turn
    reports its real recorded outcome instead of an inferred one.
    """
    if not isinstance(turn_id, str):
        return None
    if view.get('turn') and view['turn']['turn_id'] == turn_id:
        return None
    if view.get('last_turn') and view['last_turn']['turn_id'] == turn_id:
        return view['last_turn']['status']
    for item in view.get('history') or []:
        if item['turn_id'] == turn_id:
            return item['status']
    return None


def _delivery_state(ack, turn_status):
    """Explicit delivery state and truthful exit code for one run.

    Submission acknowledgement, actual turn outcome and completion stay
    distinct: ``status`` keeps the provider's acknowledgement while
    ``delivery`` states what actually happened to the turn. Exit code 0
    means the turn was observed completed. Rejected (2), uncertain (3),
    failed (4), interrupted (5) and an accepted turn without an observed
    terminal event (``unknown``, 6) all exit nonzero. A process exit or an
    interrupt acknowledgement is never inferred as a terminal outcome.
    """
    if ack == 'rejected':
        return 'rejected', 2
    if ack != 'accepted':
        return 'uncertain', 3
    if turn_status == 'completed':
        return 'completed', 0
    if turn_status == 'failed':
        return 'failed', 4
    if turn_status == 'interrupted':
        return 'interrupted', 5
    return 'unknown', 6


def _active_turn_id(session, session_id):
    view = session.status(session_id=session_id)
    return view['turn']['turn_id'] if view['turn'] else None


def _await_terminal(session, session_id, turn_id, conn, seconds):
    """Keep the owned process and route events until the turn ends.

    Returns ``terminal`` once the core no longer has ``turn_id`` active,
    ``provider_exited`` when the owned app-server exits (no outcome is
    inferred) or ``deadline`` after ``seconds``.
    """
    deadline = time.monotonic() + seconds
    while True:
        if _active_turn_id(session, session_id) != turn_id:
            return 'terminal'
        if conn.exited:
            return 'provider_exited'
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return 'deadline'
        conn.pump(min(0.2, remaining))


def _provider_turn_for(state, turn_id):
    for provider_turn, local in state['provider_turns'].items():
        if local['turn_id'] == turn_id:
            return provider_turn
    return None


def _interrupt_and_drain(root, state, session, conn, turn_id, provider_turn,
                         drain):
    """Exact ``turn/interrupt``, bounded terminal drain, provider read.

    The ``{}`` acknowledgement only acknowledges the request: success is
    recorded only from a terminal ``turn/completed`` event for this exact
    turn or the provider's own ``thread/read`` status. Without either the
    turn stays active (Unknown) in the core; nothing is resent and no
    terminal is fabricated.
    """
    info = {'requested': True, 'thread_id': state['thread_id'],
            'provider_turn_id': provider_turn, 'acknowledged': False,
            'error': None, 'drain_seconds': drain, 'drain_outcome': None,
            'provider_status': None, 'terminal_observed': False,
            'note': ('an interrupt acknowledgement is not terminal proof')}
    try:
        conn.interrupt_turn(state['thread_id'], provider_turn)
        info['acknowledged'] = True
    except cx.ProviderRejected as exc:
        info['error'] = 'rejected: ' + str(exc)
    except cx.Refusal as exc:
        info['error'] = 'uncertain: ' + str(exc)
    info['drain_outcome'] = _await_terminal(session, state['session_id'],
                                            turn_id, conn, drain)
    if info['drain_outcome'] != 'terminal' and not conn.exited:
        try:
            turns = conn.read_thread_turns(state['thread_id'])
            info['provider_status'] = turns.get(provider_turn)
            view = session.status(session_id=state['session_id'])
            _reconcile_active(root, state, session, conn, view, turns=turns)
        except (cx.Refusal, ml.Refusal) as exc:
            info['error'] = ((info['error'] + '; ') if info['error'] else '') \
                + 'thread/read: ' + str(exc)
    info['terminal_observed'] = (
        _active_turn_id(session, state['session_id']) != turn_id)
    return info


def _restore_for(result, wrapper):
    """True only for an attempt of THIS command provably never delivered."""
    return (wrapper.attempted and isinstance(result, dict)
            and result.get('state') == 'rejected')


def _restored_view(restore, wrapper):
    if not restore or not wrapper.consumed:
        return None
    return {'wakeup': (wrapper.consumed['wakeup'] or {}).get('worker'),
            'pending': wrapper.consumed['pending'],
            'note': ('attempt provably not delivered: its consumption was not '
                     'persisted; newer concurrent controls were kept')}


def _run_note(bridge_status, delivery, wait):
    last = (bridge_status or {}).get('last_send') or {}
    if 'mapping capacity exhausted' in str(last.get('reason', '')):
        return ('provider turn mapping bound reached: no turn was sent; stop '
                'this session and start a new one (new thread, no carried '
                'context) to continue')
    if delivery == 'unknown':
        return ('no terminal event observed (%s); the provider turn state is '
                'Unknown and the session keeps it active; run `unio '
                'lead-session recover` (optionally --interrupt) on the same '
                'thread; nothing was resent' % (wait or 'not waited'))
    return None


def _resume_owned_thread(conn, state):
    """Resume the EXACT recorded thread; a refusal never falls back.

    The original provider error is preserved verbatim; only a lifecycle
    explanation is appended. No replacement thread is ever created here.
    """
    try:
        conn.resume_thread(state['thread_id'])
    except cx.ProviderRejected as exc:
        lifecycle = state['thread_lifecycle']
        if lifecycle == 'legacy' and not state['provider_turns']:
            hint = ('this session was started by an earlier Unio whose start '
                    'created the thread and closed its process before any '
                    'turn; the native app-server materializes a thread only '
                    'with its first turn, so it cannot be resumed')
        elif lifecycle == 'started':
            hint = ('the first turn/start on this exact thread was never '
                    'acknowledged, so the native thread may never have been '
                    'materialized')
        else:
            hint = 'the exact owned thread could not be resumed'
        raise Refusal('%s; %s. No replacement thread is created and nothing '
                      'is resent; stop this session and start a new one '
                      '(thread %s)' % (exc, hint, state['thread_id'])) from exc


def _first_thread_creator(root, state, conn):
    """One-shot creator of the exact owned thread for a deferred session.

    Called by the bridge only inside the first real send, after every local
    refusal and immediately before that turn/start, in the same owned
    process (native same-process resume of a fresh thread also refuses, so
    the thread is never resumed in this command). The new id is durably
    recorded under the per-session control lock BEFORE it is returned, so a
    turn/start is never sent on an unrecorded thread. If another command
    already recorded a thread, this refuses (before any turn/start) instead
    of using a second thread.
    """
    def create():
        thread_id = conn.start_thread(state['model'])
        with _control_guard(root, state['session_id']):
            disk = _load_state(root, state['session_id'])
            if (disk['thread_lifecycle'] != 'deferred'
                    or disk['thread_id'] is not None):
                raise Refusal('owned thread already recorded by another '
                              'command; refusing a second thread')
            disk['thread_id'] = thread_id
            disk['thread_lifecycle'] = 'started'
            _save_state(root, disk)
        state['thread_id'] = thread_id
        state['thread_lifecycle'] = 'started'
        return thread_id
    return create


def _cmd_run_owned(root, state, args, text):
    """One explicit owner turn over the owned production transport.

    Admission (STOP, owner holds, policy, capacity) is checked before the
    owned process is spawned. The command then owns ONE app-server process:
    initialize, account, exact thread/resume, optional reconciliation of a
    proven active turn, one turn/start with the decided effort, and waiting
    for the turn's terminal notification while KEEPING the process alive
    (``--turn-wait``, default 3600s). At the deadline it requests an exact
    ``turn/interrupt`` for the proven thread/turn, drains terminal events
    for ``--interrupt-drain`` seconds and reads the provider's own thread
    state before teardown; an acknowledgement alone is never terminal
    proof. The core's idempotent request check and its open-state check
    decide replays and uncertain sessions; nothing is ever resent, a
    replay never waits or interrupts, and an unacknowledged turn is never
    reconciled. The connection is closed in a finally. A provably
    rejected/never-sent attempt does not persist its effort/wakeup
    consumption. Exit codes are truthful (see ``_delivery_state``).
    """
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=state['budget_label'])
    try:
        owner = _load_owner(root)
        if not isinstance(owner, dict) or owner.get('session_id') != state['session_id']:
            raise Refusal('workspace owner mismatch')
        session, bridge, _rpc, policy, wrapper = _open(root, state)
        view = session.status(session_id=state['session_id'])
        wrapper.kind = args.kind
        wrapper.reason = args.reason
        conn = cx.OwnedCodexConnection(state['codex_binary'], cwd=str(root))
        try:
            conn.initialize()
            creator = None
            if state['thread_lifecycle'] == 'deferred':
                # First owned turn: the exact thread is created inside the
                # send itself (see _first_thread_creator); nothing to
                # resume or reconcile yet.
                creator = _first_thread_creator(root, state, conn)
            else:
                _resume_owned_thread(conn, state)
                view = _reconcile_active(root, state, session, conn, view)
            probe = SendProbe(conn.rpc)
            try:
                live = bx.CodexLeadTransport(
                    probe, state['thread_id'], model=state['model'],
                    effort=state['baseline_effort'],
                    supported_efforts=policy.supported(),
                    max_mappings=state['max_mappings'],
                    prior_mappings=dict(state['provider_turns']),
                    rejection=cx.ProviderRejected,
                    create_thread=creator)
                live.bind(session)
            except (bx.Refusal, ml.Refusal):
                # Unproven handoff (for example an unacknowledged turn):
                # inspection only. The core still returns recorded replay
                # results; every new send refuses with zero turn starts.
                live = bx.CodexLeadTransport(
                    probe, state['thread_id'], model=state['model'],
                    effort=state['baseline_effort'],
                    supported_efforts=policy.supported(),
                    max_mappings=state['max_mappings'],
                    rejection=cx.ProviderRejected)
                live.bind(session)
            conn.on_notification = live.handle_notification
            wrapper.bridge = live
            wrapper.probe = probe
            generation = view['generation']
            result = None
            try:
                result = session.submit_next_turn(
                    session_id=state['session_id'], generation=generation,
                    request_id=args.request_id, text=text)
            finally:
                # Locked merge-persist: concurrent pending effort requests,
                # worker terminal wakeups and STOP flags written while this
                # turn was in flight survive; the lock is held only for this
                # short transaction, never across the turn itself. Mappings
                # are durable BEFORE the long wait, so recover stays possible.
                state = _persist_run(root, state, policy, live, session,
                                     restore=_restore_for(result, wrapper))
            restore = _restore_for(result, wrapper)
            decision = wrapper.last_decision
            if decision is None:
                for item in policy.decisions():
                    if item['turn_id'] == result.get('turn_id'):
                        decision = item
            turn_status = None
            wait = None
            interrupt = None
            if result.get('state') == 'accepted':
                turn_id = result['turn_id']
                view = session.status(session_id=state['session_id'])
                turn_status = _turn_terminal_status(view, turn_id)
                sent_now = wrapper.attempted and probe.turn_starts > 0
                if (turn_status is None and sent_now
                        and _active_turn_id(session,
                                            state['session_id']) == turn_id):
                    wait = _await_terminal(session, state['session_id'],
                                           turn_id, conn, args.turn_wait)
                    provider_turn = _provider_turn_for(state, turn_id)
                    if wait == 'deadline' and provider_turn is not None:
                        interrupt = _interrupt_and_drain(
                            root, state, session, conn, turn_id,
                            provider_turn, args.interrupt_drain)
                    view = session.status(session_id=state['session_id'])
                    turn_status = _turn_terminal_status(view, turn_id)
                elif turn_status is None:
                    wait = 'replay_not_waited'
            completed = turn_status == 'completed'
            provider_exited = conn.exited
            delivery, code = _delivery_state(result.get('state'), turn_status)
            if delivery == 'completed':
                _clear_waiting_after_completion(root, state['session_id'])
            live_status = live.status()
            payload = {
                'session_id': state['session_id'], 'request_id': args.request_id,
                'generation': result.get('generation'),
                'turn_id': result.get('turn_id'), 'status': result.get('state'),
                'effort': decision['effort'] if decision else None,
                'kind': decision['kind'] if decision else None,
                'source': decision['source'] if decision else None,
                'turn_completed': completed, 'turn_status': turn_status,
                'delivery': delivery,
                'wait': {'seconds': args.turn_wait, 'outcome': wait},
                'interrupt': interrupt,
                'restored': _restored_view(restore, wrapper),
                'note': _run_note(live_status, delivery, wait),
                'provider_exited': provider_exited,
                'thread_id': state['thread_id'],
                'bridge': live_status, 'effective': 'Unknown',
                'caution': CAUTION,
            }
            if provider_exited:
                payload['stderr_tail'] = conn.stderr_tail()
            _emit(args, payload, 'turn %s: %s (effort %s, kind %s, source %s, '
                                 'delivery %s, owned thread %s)%s'
                  % (result.get('turn_id'), result.get('state'),
                     payload['effort'], payload['kind'], payload['source'],
                     delivery, state['thread_id'],
                     ('; ' + payload['note']) if payload['note'] else ''))
            return code
        finally:
            conn.close()
    finally:
        lease.release()


def _cmd_run(root, args):
    state = _load_state(root, args.session)
    _require_owner(root, args.session)
    if state['stopped']:
        raise Refusal('lead session stopped: new turns are blocked')
    if lp.is_project_stop_active(root):
        raise Refusal('project STOP is active: lead session operations are blocked')
    text = _read_input(args.file, MAX_INPUT_BYTES)
    if args.kind is not None and args.kind not in pe.KINDS:
        raise Refusal('unknown work kind: ' + args.kind)
    if state['transport'] == 'owned':
        return _cmd_run_owned(root, state, args, text)
    session, bridge, rpc, policy, wrapper = _open(root, state)
    wrapper.kind = args.kind
    wrapper.reason = args.reason
    view = session.status(session_id=state['session_id'])
    if (view['state'] == 'running' and view['turn'] is not None
            and rpc.behavior().get('release_held')):
        # In-process fake seam only (no process exists to kill): a pure
        # terminal notification for an already proven provider turn; zero
        # rpc calls. Killed-turn semantics are exercised through the owned
        # path against the executable fake app-server instead.
        active = view['turn']['turn_id']
        provider_turn = None
        for pid, local in bridge.status()['mappings'].items():
            if local['turn_id'] == active:
                provider_turn = pid
        if provider_turn is None:
            raise Refusal('held turn has no proven provider mapping; '
                          'refusing to invent a release')
        rpc.notify_terminal(provider_turn)
        view = session.status(session_id=state['session_id'])
    generation = view['generation']
    result = None
    try:
        result = session.submit_next_turn(
            session_id=state['session_id'], generation=generation,
            request_id=args.request_id, text=text)
    finally:
        # Same locked merge-persist as the owned path: concurrent control
        # state written during this turn is never overwritten.
        state = _persist_run(root, state, policy, bridge, session,
                             restore=_restore_for(result, wrapper))
    restore = _restore_for(result, wrapper)
    decision = wrapper.last_decision
    if decision is None:
        for item in policy.decisions():
            if item['turn_id'] == result.get('turn_id'):
                decision = item
    completed = False
    turn_status = None
    if result.get('state') == 'accepted':
        view = session.status(session_id=state['session_id'])
        turn_status = _turn_terminal_status(view, result.get('turn_id'))
        if turn_status is None and rpc.complete_last():
            turn_status = 'completed'
        completed = turn_status == 'completed'
    delivery, code = _delivery_state(result.get('state'), turn_status)
    if delivery == 'completed':
        _clear_waiting_after_completion(root, state['session_id'])
    bridge_status = bridge.status()
    payload = {
        'session_id': state['session_id'], 'request_id': args.request_id,
        'generation': result.get('generation'),
        'turn_id': result.get('turn_id'), 'status': result.get('state'),
        'effort': decision['effort'] if decision else None,
        'kind': decision['kind'] if decision else None,
        'source': decision['source'] if decision else None,
        'turn_completed': completed, 'turn_status': turn_status,
        'delivery': delivery, 'provider_exited': False,
        'restored': _restored_view(restore, wrapper),
        'note': _run_note(bridge_status, delivery, None),
        'effective': 'Unknown',
        'caution': CAUTION,
    }
    _emit(args, payload, 'turn %s: %s (effort %s, kind %s, source %s, '
                         'delivery %s)'
          % (result.get('turn_id'), result.get('state'),
             payload['effort'], payload['kind'], payload['source'], delivery))
    return code


def _cmd_recover(root, args):
    """Explicit owner recovery of ONE proven active turn on the SAME thread.

    For a turn whose provider id was proven by an acknowledgement but whose
    terminal event was never observed (for example a controller deadline
    or an app-server exit). Admission runs first; then one owned process:
    initialize, exact thread/resume and the provider's own ``thread/read``.
    A terminal provider status is recorded; with ``--interrupt`` a still
    in-progress turn gets one exact ``turn/interrupt`` plus a bounded
    terminal drain and a second ``thread/read``. Nothing is ever resent,
    no ``turn/start`` is made, no terminal is fabricated and the thread is
    never replaced or reset. An unacknowledged (unproven) turn refuses.
    Exit 0 only when a provider terminal for the exact turn was recorded;
    6 when it stays Unknown/in progress.
    """
    state = _load_state(root, args.session)
    _require_owner(root, args.session)
    if state['transport'] != 'owned':
        raise Refusal('recover is supported only on the owned transport')
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=state['budget_label'])
    try:
        session, bridge, _rpc, policy, wrapper = _open(root, state)
        view = session.status(session_id=state['session_id'])
        if (view['state'] not in ('pending', 'running', 'outcome_unknown')
                or view['turn'] is None):
            raise Refusal('no active turn to recover (session state %s)'
                          % view['state'])
        turn_id = view['turn']['turn_id']
        provider_turn = _provider_turn_for(state, turn_id)
        if provider_turn is None:
            raise Refusal('active turn has no proven provider turn id '
                          '(unacknowledged): it can never be reconciled, '
                          'interrupted or resent; stop this session and '
                          'start a new one')
        conn = cx.OwnedCodexConnection(state['codex_binary'], cwd=str(root))
        try:
            conn.initialize()
            _resume_owned_thread(conn, state)
            live = bx.CodexLeadTransport(
                SendProbe(conn.rpc), state['thread_id'], model=state['model'],
                effort=state['baseline_effort'],
                supported_efforts=policy.supported(),
                max_mappings=state['max_mappings'],
                prior_mappings=dict(state['provider_turns']),
                rejection=cx.ProviderRejected)
            live.bind(session)
            conn.on_notification = live.handle_notification
            turns = conn.read_thread_turns(state['thread_id'])
            before = turns.get(provider_turn)
            _reconcile_active(root, state, session, conn, view, turns=turns)
            interrupt = None
            if (_active_turn_id(session, state['session_id']) == turn_id
                    and before is not None and args.interrupt):
                interrupt = _interrupt_and_drain(
                    root, state, session, conn, turn_id, provider_turn,
                    args.drain)
            view = session.status(session_id=state['session_id'])
            turn_status = _turn_terminal_status(view, turn_id)
            if turn_status is not None:
                outcome, code = 'reconciled', 0
            elif before is None:
                outcome, code = 'provider_does_not_report_turn', 6
            elif interrupt is None:
                outcome, code = 'still_in_progress', 6
            else:
                outcome, code = 'interrupt_unconfirmed', 6
            payload = {
                'session_id': state['session_id'], 'turn_id': turn_id,
                'provider_turn_id': provider_turn,
                'thread_id': state['thread_id'],
                'provider_status_before': before, 'turn_status': turn_status,
                'outcome': outcome, 'interrupt': interrupt,
                'turn_starts': 0, 'provider_exited': conn.exited,
                'note': ('no turn was started or resent; an unresolved turn '
                         'stays active (Unknown); rerun with --interrupt to '
                         'request turn/interrupt for this exact turn'
                         if code else 'provider terminal recorded'),
                'effective': 'Unknown', 'caution': CAUTION,
            }
            if conn.exited:
                payload['stderr_tail'] = conn.stderr_tail()
            _emit(args, payload, 'recover %s: %s (provider status before %s, '
                                 'turn status %s)'
                  % (turn_id, outcome, before, turn_status))
            return code
        finally:
            conn.close()
    finally:
        lease.release()


def _cmd_status(root, args):
    state = _load_state(root, args.session)
    session, bridge, rpc, policy, wrapper = _open(root, state)
    view = _session_view(root, state, session, bridge, policy)
    disp = view['effort_display']
    _emit(args, view, _format_status_human(view, disp, state))
    return 0


def _cmd_effort(root, args):
    if args.control == 'show':
        # Read-only: zero provider calls, no control lock needed.
        state = _load_state(root, args.session)
        session, bridge, rpc, policy, wrapper = _open(root, state)
        status = policy.status()
        status['session_id'] = state['session_id']
        status['stopped'] = state['stopped']
        status['historical'] = _historical(root, state['session_id'])
        view = session.status(session_id=state['session_id'])
        disp = _compute_effort_display(view, policy, state)
        status['effort_display'] = disp
        status['current_request'] = disp['current_request']
        _emit(args, status, _format_effort_show(disp, status))
        return 0
    with _control_guard(root, args.session):
        _require_owner(root, args.session)
        state = _load_state(root, args.session)
        session, bridge, rpc, policy, wrapper = _open(root, state)
        if args.control == 'auto':
            policy.set_auto(args.reason)
            human = 'effort policy: adaptive (automatic selection resumed; next turn selected by kind)'
        elif args.control == 'manual':
            policy.set_manual(args.effort, args.reason)
            human = 'requested effort override: %s (policy manual; auto suspended)' % args.effort
        else:
            policy.request_next_turn(args.effort, args.reason)
            human = ('requested next-turn effort: %s (pending next turn only; '
                     'applied after active turn ends)' % args.effort)
        _persist(root, state, policy, bridge, session)
        status = policy.status()
        status['session_id'] = state['session_id']
        status['stopped'] = state['stopped']
        view = session.status(session_id=state['session_id'])
        disp = _compute_effort_display(view, policy, state)
        status['effort_display'] = disp
        status['current_request'] = disp['current_request']
        _emit(args, status, human)
    return 0


def _cmd_worker(root, args):
    with _control_guard(root, args.session):
        _require_owner(root, args.session)
        state = _load_state(root, args.session)
        session, bridge, rpc, policy, wrapper = _open(root, state)
        if args.control == 'register':
            if not ml.LABEL.fullmatch(args.worker):
                raise Refusal('invalid worker id')
            if args.worker in state['workers']:
                raise Refusal('worker already registered: ' + args.worker)
            if len(state['workers']) >= MAX_WORKERS:
                raise Refusal('worker registry bound exceeded')
            state['workers'][args.worker] = {'state': 'registered',
                                            'updated_at': _now()}
            human = 'worker registered: ' + args.worker
        elif args.control == 'wait':
            if not state['workers']:
                raise Refusal('no registered workers to wait on')
            state['waiting'] = True
            human = ('lead waiting on %d registered worker(s); no model '
                     'calls happen while waiting' % len(state['workers']))
        else:
            worker = state['workers'].get(args.worker)
            if worker is None:
                raise Refusal('unknown worker: ' + args.worker)
            if worker['state'] == 'terminal':
                raise Refusal('worker terminal event already recorded: '
                              + args.worker)
            worker['state'] = 'terminal'
            worker['updated_at'] = _now()
            policy.record_wakeup(args.worker, 'worker terminal event')
            human = ('worker terminal event recorded: %s (one review wakeup '
                     'queued)' % args.worker)
        _persist(root, state, policy, bridge, session)
        payload = {
            'session_id': state['session_id'], 'control': args.control,
            'worker': getattr(args, 'worker', None),
            'workers': {wid: dict(w) for wid, w in
                        state['workers'].items()},
            'waiting': state['waiting'],
            'pending_wakeups': policy.pending_wakeups(),
            'stopped': state['stopped'], 'effective': 'Unknown',
        }
        _emit(args, payload, human)
    return 0


def _cmd_stop(root, args):
    with _control_guard(root, args.session):
        _require_owner(root, args.session)
        state = _load_state(root, args.session)
        session, bridge, rpc, policy, wrapper = _open(root, state)
        state['stopped'] = True
        _persist(root, state, policy, bridge, session)
        payload = {
            'session_id': state['session_id'], 'stopped': True,
            'workers': {wid: dict(w) for wid, w in state['workers'].items()},
            'note': ('STOP blocks new turns; workers are not killed and '
                     'nothing resumes automatically; no command in this '
                     'slice clears a STOP'),
        }
        _emit(args, payload, 'lead session stopped: new turns are blocked; '
                              'workers keep running; no automatic resume')
    return 0


def _cmd_output(root, args):
    state = _load_state(root, args.session)
    session, bridge, rpc, policy, wrapper = _open(root, state)
    page = session.read_output(session_id=state['session_id'],
                               after=args.after, limit=args.limit)
    page['historical'] = _historical(root, state['session_id'])
    _emit(args, page, '%d journal record(s) after cursor %d%s'
          % (len(page['records']), args.after,
             '' if not page['historical'] else ' (historical: not the '
             'current workspace owner)'))
    return 0


def build_parser():
    parser = argparse.ArgumentParser(
        prog='unio lead-session',
        description='Adaptive-effort managed lead session controller '
                    '(experimental; see docs/ADAPTIVE-LEAD-EFFORT.md)')
    parser.add_argument('--project', required=True,
                        help='native workspace root')
    sub = parser.add_subparsers(dest='command', required=True)

    start = sub.add_parser('start', help='explicit owner start with a goal '
                                         'file, model and adaptive effort')
    start.add_argument('--goal', required=True, help='owner goal file')
    start.add_argument('--model', required=True, help='owned model id')
    start.add_argument('--route', default=ROUTE_DEFAULT)
    start.add_argument('--budget-label', default=None,
                       help='optional explicit budget group label (must match '
                            'policy mapping if specified)')
    start.add_argument('--workspace', default=None,
                       help='workspace label (default: project root)')
    start.add_argument('--ceiling', default=pe.DEFAULT_CEILING,
                       help='planning/review ceiling; this first interface '
                            'exposes only low and xhigh (default: xhigh)')
    start.add_argument('--effort', default='auto',
                       help='auto, low or xhigh (default: auto); this first '
                            'adaptive interface exposes no intermediate '
                            'levels')
    start.add_argument('--max-requests', type=int, default=ml.MAX_REQUESTS)
    start.add_argument('--max-mappings', type=int,
                       default=bx.OWNED_MAPPING_BOUND,
                       help='explicit provider-turn mapping bound (1..64)')
    start.add_argument('--transport', default='owned', choices=('owned', 'fake'),
                       help='owned: one real owned app-server process per '
                            'command and the exact durable thread (default); '
                            'fake: deterministic in-process test transport')
    start.add_argument('--codex-binary', default='codex',
                       help='owned app-server binary (default: codex on PATH)')
    start.add_argument('--fake-efforts', default='low,medium,high,xhigh',
                       help='comma-separated efforts advertised by the fake '
                            'owned connection')
    start.add_argument('--json', action='store_true')

    run = sub.add_parser('run', help='submit one explicit owner turn')
    run.add_argument('--file', required=True, help='bounded turn input file')
    run.add_argument('--request-id', required=True)
    run.add_argument('--kind', choices=pe.KINDS, default=None,
                     help='explicit work kind (default: review when a '
                          'worker wakeup is pending, else coordination)')
    run.add_argument('--reason', default=None)
    run.add_argument('--turn-wait', type=int, default=TURN_WAIT_DEFAULT,
                     help='owned transport: seconds the command keeps the '
                          'owned app-server alive waiting for the turn '
                          'terminal event (1..86400, default %d); at the '
                          'deadline it requests turn/interrupt for the exact '
                          'turn. 0 is refused: the owned process cannot '
                          'outlive the command' % TURN_WAIT_DEFAULT)
    run.add_argument('--interrupt-drain', type=int,
                     default=INTERRUPT_DRAIN_DEFAULT,
                     help='seconds to drain terminal events after a deadline '
                          'turn/interrupt (1..600, default %d)'
                          % INTERRUPT_DRAIN_DEFAULT)
    run.add_argument('--session', default=None)
    run.add_argument('--json', action='store_true')

    recover = sub.add_parser(
        'recover', help='owned transport: reconcile (and with --interrupt, '
                        'request turn/interrupt for) the proven active turn '
                        'on the SAME thread; never starts or resends a turn')
    recover.add_argument('--interrupt', action='store_true',
                         help='request turn/interrupt for the exact proven '
                              'turn when the provider still reports it in '
                              'progress')
    recover.add_argument('--drain', type=int, default=INTERRUPT_DRAIN_DEFAULT,
                         help='seconds to drain terminal events after the '
                              'interrupt request (1..600, default %d)'
                              % INTERRUPT_DRAIN_DEFAULT)
    recover.add_argument('--session', default=None)
    recover.add_argument('--json', action='store_true')

    status = sub.add_parser('status', help='read-only session view')
    status.add_argument('--session', default=None)
    status.add_argument('--json', action='store_true')

    effort = sub.add_parser('effort', help='effort controls')
    effort_sub = effort.add_subparsers(dest='control', required=True)
    for name, help_text in (
            ('show', 'show the effort policy state'),
            ('auto', 'resume automatic selection'),
            ('manual', 'manual override (suspends auto)'),
            ('request', 'pending effort for the next turn only')):
        sub_parser = effort_sub.add_parser(name, help=help_text)
        if name in ('manual', 'request'):
            sub_parser.add_argument('effort',
                                    help='interface effort: low or xhigh')
        sub_parser.add_argument('--reason', default=None)
        sub_parser.add_argument('--session', default=None)
        sub_parser.add_argument('--json', action='store_true')

    worker = sub.add_parser('worker', help='worker registration and waiting')
    worker_sub = worker.add_subparsers(dest='control', required=True)
    for name, help_text in (
            ('register', 'register one worker'),
            ('wait', 'mark the lead as waiting (zero model calls)'),
            ('terminal', 'record one worker terminal event (one wakeup)')):
        sub_parser = worker_sub.add_parser(name, help=help_text)
        if name in ('register', 'terminal'):
            sub_parser.add_argument('worker', help='worker id')
        sub_parser.add_argument('--session', default=None)
        sub_parser.add_argument('--json', action='store_true')

    stop = sub.add_parser('stop', help='STOP: block new turns without '
                                      'killing workers; never auto-resumes')
    stop.add_argument('--session', default=None)
    stop.add_argument('--json', action='store_true')

    output = sub.add_parser('output', help='read the bounded output journal')
    output.add_argument('--after', type=int, default=0)
    output.add_argument('--limit', type=int, default=ml.DEFAULT_LIMIT)
    output.add_argument('--session', default=None)
    output.add_argument('--json', action='store_true')
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    root = ml.safe_path(Path(args.project))
    if getattr(args, 'workspace', None) is None:
        args.workspace = str(root)
    if hasattr(args, 'session') and args.session is None:
        owner = _load_owner(root)
        if owner is None:
            raise Refusal('no managed lead session in this workspace; '
                          'start one first')
        args.session = owner['session_id']
    if getattr(args, 'turn_wait', None) is not None:
        if args.turn_wait == 0:
            raise Refusal('--turn-wait 0 is refused before launch: the owned '
                          'app-server cannot outlive this command, so an '
                          'asynchronous acknowledgement would be killed; use '
                          'a bounded wait (default %d seconds)'
                          % TURN_WAIT_DEFAULT)
        if not 1 <= args.turn_wait <= 86400:
            raise Refusal('turn wait must be 1..86400 seconds')
    for name in ('interrupt_drain', 'drain'):
        value = getattr(args, name, None)
        if value is not None and not 1 <= value <= 600:
            raise Refusal('interrupt drain must be 1..600 seconds')
    if args.command == 'start':
        return _cmd_start(root, args)
    if args.command == 'run':
        return _cmd_run(root, args)
    if args.command == 'recover':
        return _cmd_recover(root, args)
    if args.command == 'status':
        return _cmd_status(root, args)
    if args.command == 'effort':
        return _cmd_effort(root, args)
    if args.command == 'worker':
        return _cmd_worker(root, args)
    if args.command == 'stop':
        return _cmd_stop(root, args)
    if args.command == 'output':
        return _cmd_output(root, args)
    raise Refusal('unknown command: ' + str(args.command))


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (Refusal, ml.Refusal, pe.Refusal, bx.Refusal, cx.Refusal, lp.Refusal) as exc:
        print('unio lead-session: ' + str(exc), file=sys.stderr)
        sys.exit(1)
