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
  completed turn (or an explicit ``--turn-wait 0`` asynchronous
  acknowledgement labelled ``pending``), nonzero for rejected,
  uncertain, failed, interrupted or timed-out work, and a process exit
  is never inferred as model success;
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
FAKE_LOG_BOUND = 256 * 1024
THREAD_FAKE = 'fake-owned-thread-1'
ROUTE_DEFAULT = 'codex-app-server'
BUDGET_DEFAULT = 'codex-shared'
STATE_KEYS = frozenset(
    'session_id workspace route budget_label model thread_id baseline_effort '
    'transport codex_binary fake_efforts goal_sha256 max_requests max_mappings '
    'provider_turns policy stopped waiting workers created_at updated_at'.split())
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
                'thread_id', 'baseline_effort', 'transport', 'goal_sha256',
                'created_at', 'updated_at'):
        if not isinstance(doc.get(key), str) or not doc[key] or '\x00' in doc[key]:
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


class EffortTransport:
    """Core transport seam deciding the explicit effort at send time."""

    def __init__(self, bridge, policy, kind, reason):
        self.bridge = bridge
        self.policy = policy
        self.kind = kind
        self.reason = reason
        self.last_decision = None

    def send_turn(self, facts):
        if self.bridge is None:
            raise ml.Refusal('owned transport unavailable')
        if self.kind is not None:
            kind, reason = self.kind, self.reason
        else:
            wakeup = self.policy.consume_wakeup()
            if wakeup is not None:
                kind = 'review'
                reason = 'worker terminal wakeup: ' + wakeup['worker']
            else:
                kind = 'coordination'
                reason = None
        decision = self.policy.decide_turn(facts['turn_id'], kind, reason)
        self.last_decision = dict(decision)
        out = dict(facts)
        out['effort'] = decision['effort']
        return self.bridge.send_turn(out)


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
    try:
        bridge = bx.CodexLeadTransport(
            rpc if rpc is not None else _closed_rpc,
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
            rpc if rpc is not None else _closed_rpc,
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


def _merge_policy_snapshot(base, disk, live):
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
    """
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


def _persist_run(root, base_state, policy, bridge, session):
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
        disk['policy'] = _merge_policy_snapshot(base_state['policy'],
                                                 disk['policy'],
                                                 policy.snapshot())
        _save_state(root, disk)
    return disk


def _session_view(root, state, session, bridge, policy):
    view = session.status(session_id=state['session_id'])
    return {
        'session_id': state['session_id'],
        'workspace': state['workspace'],
        'route': state['route'], 'budget_label': state['budget_label'],
        'model': state['model'], 'thread_id': state['thread_id'],
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
        'stopped': state['stopped'], 'waiting': state['waiting'],
        'workers': {wid: dict(worker) for wid, worker in
                    state['workers'].items()},
        'effort': policy.status(),
        'decisions': [dict(item) for item in policy.decisions()],
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


def _cmd_start(root, args):
    goal = _read_input(args.goal, MAX_INPUT_BYTES)
    goal_sha = hashlib.sha256(goal.encode('utf-8')).hexdigest()
    owner = _load_owner(root)
    if isinstance(owner, dict) and owner['session_id']:
        try:
            existing = _load_state(root, owner['session_id'])
        except Refusal:
            existing = None
        if existing is not None and not existing['stopped']:
            raise Refusal('workspace already has an active managed lead '
                          'session: ' + owner['session_id'])
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
    }
    _save_state(root, state)
    _save_owner(root, sid)
    view = _session_view(root, state, session, bridge, policy)
    _emit(args, view, 'lead session started: %s (model %s, ceiling %s, '
                      'baseline effort %s)'
          % (sid, args.model, args.ceiling, baseline))
    return 0


def _cmd_start_owned(root, args, goal_sha, baseline):
    """Start one owned app-server connection and ONE new owned thread.

    Contention, STOP, policy and owner holds are checked before the owned
    process is spawned; the ownership claim is atomic under the workspace
    owner lock, so a concurrent start refuses honestly instead of creating a
    second managed owner. The exact provider thread id is persisted; no
    turn is started here.
    """
    policy_doc, lead_group, lease = lp.admit_lead(
        root, expected_agent='codex', budget_label=args.budget_label)
    try:
        with _owner_guard(root):
            owner = _load_owner(root)
            if isinstance(owner, dict) and owner['session_id']:
                try:
                    existing = _load_state(root, owner['session_id'])
                except Refusal:
                    existing = None
                if existing is not None and not existing['stopped']:
                    raise Refusal('workspace already has an active managed '
                                  'lead session: ' + owner['session_id'])
            conn = cx.OwnedCodexConnection(args.codex_binary, cwd=str(root))
            try:
                conn.initialize()
                efforts = conn.query_model_efforts(args.model)
                thread_id = conn.start_thread(args.model)
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
                'model': args.model, 'thread_id': thread_id,
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
    _emit(args, view, 'lead session started: %s (model %s, ceiling %s, '
                      'baseline effort %s, owned thread %s)'
          % (sid, args.model, args.ceiling, baseline, thread_id))
    return 0


def _reconcile_active(root, state, session, conn, view):
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


def _delivery_state(ack, turn_status, turn_wait):
    """Explicit delivery state and truthful exit code for one run.

    Submission acknowledgement, actual turn outcome and completion stay
    distinct: ``status`` keeps the provider's acknowledgement while
    ``delivery`` states what actually happened to the turn. Exit code 0
    means the turn was observed completed — or, with ``--turn-wait 0``,
    that the owner explicitly chose an asynchronous acknowledgement
    (delivery stays ``pending``; the owned process is terminated at
    command end, so no background execution is promised). Failed,
    rejected, interrupted, uncertain and timed-out work all exit
    nonzero. A process exit is never inferred as model success.
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
    if turn_wait > 0:
        return 'pending', 6
    return 'pending', 0


def _cmd_run_owned(root, state, args, text):
    """One explicit owner turn over the owned production transport.

    Admission (STOP, owner holds, policy, capacity) is checked before the
    owned process is spawned. The command then owns ONE app-server process:
    initialize, account, exact thread/resume, optional reconciliation of a
    proven active turn, one turn/start with the decided effort, and bounded
    waiting for the turn's terminal notification. The core's idempotent
    request check and its open-state check decide replays and uncertain
    sessions; nothing is ever resent, and an unacknowledged turn is
    never reconciled. The connection is closed in a finally so no owned
    process outlives the command. The payload separates the submission
    acknowledgement (``status``) from the actual turn outcome
    (``turn_status``, ``delivery``) and the observed native exit
    (``provider_exited``); the exit code is truthful: 0 only for an
    observed completed turn (or an explicit ``--turn-wait 0``
    asynchronous acknowledgement), nonzero for rejected, uncertain,
    failed, interrupted and timed-out work.
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
            conn.resume_thread(state['thread_id'])
            view = _reconcile_active(root, state, session, conn, view)
            try:
                live = bx.CodexLeadTransport(
                    conn.rpc, state['thread_id'], model=state['model'],
                    effort=state['baseline_effort'],
                    supported_efforts=policy.supported(),
                    max_mappings=state['max_mappings'],
                    prior_mappings=dict(state['provider_turns']),
                    rejection=cx.ProviderRejected)
                live.bind(session)
            except (bx.Refusal, ml.Refusal):
                # Unproven handoff (for example an unacknowledged turn):
                # inspection only. The core still returns recorded replay
                # results; every new send refuses with zero turn starts.
                live = bx.CodexLeadTransport(
                    conn.rpc, state['thread_id'], model=state['model'],
                    effort=state['baseline_effort'],
                    supported_efforts=policy.supported(),
                    max_mappings=state['max_mappings'],
                    rejection=cx.ProviderRejected)
                live.bind(session)
            conn.on_notification = live.handle_notification
            wrapper.bridge = live
            generation = view['generation']
            try:
                result = session.submit_next_turn(
                    session_id=state['session_id'], generation=generation,
                    request_id=args.request_id, text=text)
            finally:
                # Locked merge-persist: concurrent pending effort requests,
                # worker terminal wakeups and STOP flags written while this
                # turn was in flight survive; the lock is held only for this
                # short transaction, never across the turn itself.
                state = _persist_run(root, state, policy, live, session)
            decision = wrapper.last_decision
            if decision is None:
                for item in policy.decisions():
                    if item['turn_id'] == result.get('turn_id'):
                        decision = item
            completed = False
            turn_status = None
            if result.get('state') == 'accepted':
                turn_id = result['turn_id']
                view = session.status(session_id=state['session_id'])
                turn_status = _turn_terminal_status(view, turn_id)
                if turn_status is None and args.turn_wait > 0:
                    deadline = time.monotonic() + args.turn_wait
                    while True:
                        view = session.status(session_id=state['session_id'])
                        if view['turn'] is None:
                            turn_status = _turn_terminal_status(view,
                                                                turn_id)
                            break
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        conn.pump(min(0.2, remaining))
                        if conn.exited:
                            # Child death: stop waiting promptly (no tight
                            # polling, no inferred success); the actual
                            # process outcome, partial output and Unknown
                            # model completion stay honest.
                            break
                completed = turn_status == 'completed'
            provider_exited = conn.exited
            delivery, code = _delivery_state(result.get('state'),
                                              turn_status, args.turn_wait)
            payload = {
                'session_id': state['session_id'], 'request_id': args.request_id,
                'generation': result.get('generation'),
                'turn_id': result.get('turn_id'), 'status': result.get('state'),
                'effort': decision['effort'] if decision else None,
                'kind': decision['kind'] if decision else None,
                'source': decision['source'] if decision else None,
                'turn_completed': completed, 'turn_status': turn_status,
                'delivery': delivery,
                'provider_exited': provider_exited,
                'thread_id': state['thread_id'],
                'bridge': live.status(), 'effective': 'Unknown',
                'caution': CAUTION,
            }
            if provider_exited:
                payload['stderr_tail'] = conn.stderr_tail()
            _emit(args, payload, 'turn %s: %s (effort %s, kind %s, source %s, '
                                 'delivery %s, owned thread %s)'
                  % (result.get('turn_id'), result.get('state'),
                     payload['effort'], payload['kind'], payload['source'],
                     delivery, state['thread_id']))
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
        # Fake-only lifecycle release of a held turn: a pure terminal
        # notification for an already proven provider turn; zero rpc calls.
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
    try:
        result = session.submit_next_turn(
            session_id=state['session_id'], generation=generation,
            request_id=args.request_id, text=text)
    finally:
        # Same locked merge-persist as the owned path: concurrent control
        # state written during this turn is never overwritten.
        state = _persist_run(root, state, policy, bridge, session)
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
    delivery, code = _delivery_state(result.get('state'), turn_status,
                                     args.turn_wait)
    payload = {
        'session_id': state['session_id'], 'request_id': args.request_id,
        'generation': result.get('generation'),
        'turn_id': result.get('turn_id'), 'status': result.get('state'),
        'effort': decision['effort'] if decision else None,
        'kind': decision['kind'] if decision else None,
        'source': decision['source'] if decision else None,
        'turn_completed': completed, 'turn_status': turn_status,
        'delivery': delivery, 'provider_exited': False,
        'effective': 'Unknown',
        'caution': CAUTION,
    }
    _emit(args, payload, 'turn %s: %s (effort %s, kind %s, source %s, '
                         'delivery %s)'
          % (result.get('turn_id'), result.get('state'),
             payload['effort'], payload['kind'], payload['source'], delivery))
    return code


def _cmd_status(root, args):
    state = _load_state(root, args.session)
    session, bridge, rpc, policy, wrapper = _open(root, state)
    view = _session_view(root, state, session, bridge, policy)
    _emit(args, view, 'lead session %s: state %s, generation %d, effort mode '
                      '%s, stopped %s, waiting %s%s'
          % (state['session_id'], view['state'], view['generation'],
             view['effort']['mode'], view['stopped'], view['waiting'],
             '' if not view['historical'] else ' (historical: not the '
             'current workspace owner)'))
    return 0


def _cmd_effort(root, args):
    with _control_guard(root, args.session):
        state = _load_state(root, args.session)
        if args.control != 'show':
            _require_owner(root, args.session)
        session, bridge, rpc, policy, wrapper = _open(root, state)
        if args.control == 'show':
            status = policy.status()
            status['session_id'] = state['session_id']
            status['stopped'] = state['stopped']
            status['historical'] = _historical(root, state['session_id'])
            _emit(args, status, 'effort mode %s, ceiling %s, requested %s'
                  % (status['mode'], status['ceiling'], status['requested']))
            return 0
        if args.control == 'auto':
            policy.set_auto(args.reason)
            human = 'automatic effort selection resumed'
        elif args.control == 'manual':
            policy.set_manual(args.effort, args.reason)
            human = 'manual effort override: %s (auto suspended)' % args.effort
        else:
            policy.request_next_turn(args.effort, args.reason)
            human = ('pending next-turn effort request: %s (applied only '
                     'after the active turn ends)' % args.effort)
        _persist(root, state, policy, bridge, session)
        status = policy.status()
        status['session_id'] = state['session_id']
        status['stopped'] = state['stopped']
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
    run.add_argument('--turn-wait', type=int, default=600,
                     help='owned transport: seconds to wait for the turn '
                          'terminal notification (0 returns right after '
                          'the acknowledgement; default 600)')
    run.add_argument('--session', default=None)
    run.add_argument('--json', action='store_true')

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
        if not 0 <= args.turn_wait <= 86400:
            raise Refusal('turn wait must be 0..86400 seconds')
    if args.command == 'start':
        return _cmd_start(root, args)
    if args.command == 'run':
        return _cmd_run(root, args)
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
