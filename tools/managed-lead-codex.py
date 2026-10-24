#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Owned Codex app-server RPC bridge for the managed lead core.

Importable transport component connecting the managed lead core's
``send_turn(facts)`` seam to ONE already owned, already initialized Codex
app-server RPC connection and thread. The caller injects the owned RPC
callable (the conceptual ``Server.rpc`` seam of tools/codex-worker.py) and
the explicit typed-rejection exception class. This bridge never launches a
process, never initializes a connection, never starts/resumes/forks/adopts
a thread and never claims the native registered lead; existing single-turn
worker behavior is untouched.

Frozen contract:
- construction, bind, status and refused core authority/ownership make zero
  RPC calls; the bridge infers no human authority from CLI or role and the
  core's authority/ownership callbacks remain required;
- exactly one core session and one known provider thread are bound with
  bounded opaque ids; the pinned requested model/effort must match the
  session record and both requested values are sent explicitly with every
  turn/start (requested config is never treated as effective proof; the
  effective model/effort remain Unknown);
- a core-approved send_turn makes exactly one turn/start for the bound
  thread and text: no retries, resends, automatic resume, extra RPCs or paid
  fallback; a valid acknowledgement binds the returned provider turn id to
  the exact local session/generation/turn from the facts;
- wrong, malformed, foreign-thread or lost acknowledgements and untyped RPC
  failures are uncertain, never rejection or success; an explicit typed RPC
  rejection is rejected only when no matching activity contradicts it (the
  core makes that reconciliation);
- every supported lifecycle or output event must match the bound thread and
  the exact provider turn validated by an acknowledgement; only bounded
  selected delta text and lifecycle fields enter the core, never raw
  envelopes, credentials, account ids or arbitrary event dictionaries;
  completed/failed/interrupted map to terminal turn facts with
  exit_code=None — a turn completing is not Source/adapter/process exit or
  accepted delivery;
- same-thread notifications arriving during the synchronous RPC before its
  reply are held in a bounded event/byte buffer and replayed in order only
  after a valid correlated acknowledgement; early events never prove which
  local turn they belong to and the first observed provider id is never
  adopted; stale, foreign, duplicate and unsupported events cannot
  terminate another turn or impersonate complete history;
- on buffer overflow or an oversized delta the bridge preserves an explicit
  gap instead of inventing complete output: the core has no public gap
  marker, so the bridge records one honest lifecycle fact
  (``bridge_output_gap``) for the bound turn and reports the limitation in
  its status; it never fakes an archive-limit marker of a different kind
  and never silently claims complete history;
- gap markers are tracked per local turn: an old turn's marker never
  stands in for the current turn's gap proof;
- while turn/start is unresolved, events for already mapped provider ids
  are held too, because the acknowledgement may reuse one of them; they are
  delivered to the old turn only once a distinct acknowledgement or an
  activity-free typed rejection proves attribution. A reused id, and every
  mapped id after an unresolved outcome, is quarantined: the mapping stays
  as evidence, one ``bridge_identity_ambiguous`` lifecycle fact is recorded
  for the old turn, and later events for that id are counted, never
  dispatched to any turn;
- identity memory is per bridge instance only. Binding a fresh bridge to an
  idle/terminal session with prior turns is refused before any effect,
  because the provider ids already used are unknown to it; binding a
  pending/running/outcome_unknown session stays possible for inspection
  only and send_turn refuses with zero RPC calls;
- reopening or rebinding never recovers an unproven provider-turn mapping
  and never resends pending work: after owner or connection loss,
  reconciliation stays unsupported/Unknown until the future native owner
  proves it. No persistent provider-id schema is added to the core.

The future native caller still owns: creating the connection and thread,
routing notifications, native admission, the lead reservation and claiming
the registered lead exactly once. See docs/development/MANAGED-LEAD-CODEX.md.
"""
import re

MAX_TEXT_BYTES = 8192
ID_BOUND = 128
LABEL_BOUND = 128
DELTA_BOUND = 16 * 1024
DEFAULT_BUFFER_EVENTS = 64
DEFAULT_BUFFER_BYTES = 256 * 1024
MAX_MAPPINGS = 4
START_METHOD = 'turn/start'
SUPPORTED_METHODS = ('turn/started', 'item/agentMessage/delta',
                     'item/commandExecution/outputDelta', 'turn/completed')
TERMINAL_STATUS = ('completed', 'failed', 'interrupted')
SESSION_ID = re.compile(r'lead-[0-9a-f]{24}')
GAP_EVENT = 'bridge_output_gap'
AMBIGUOUS_EVENT = 'bridge_identity_ambiguous'
OPEN_STATES = ('idle', 'terminal')
CAUTION = ('requested model/effort only; effective settings remain Unknown '
           'and no native lead is claimed')


class Refusal(Exception):
    """A controlled bridge refusal before or around an owned RPC call."""


class RPCRejected(Exception):
    """Typed explicit provider rejection of an owned RPC call.

    The caller may inject its own exception class (or tuple of classes);
    every other raised exception is ambiguous and stays uncertain.
    """


def _bounded(value, bound, name):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise Refusal('invalid ' + name)
    try:
        encoded = value.encode('utf-8')
    except (UnicodeError, RecursionError):
        raise Refusal('invalid ' + name)
    if len(encoded) > bound:
        raise Refusal(name + ' bound exceeded')
    return value


def _bounded_id(value):
    return (isinstance(value, str) and value and '\x00' not in value
            and len(value) <= ID_BOUND)


class CodexLeadTransport:
    """One owned RPC connection/thread bound to one core lead session.

    All provider effects flow through the injected ``rpc`` callable; the
    constructor, ``bind`` and ``status`` make zero RPC calls. The core's
    authority/ownership callbacks remain the only admission path.
    """

    def __init__(self, rpc, thread_id, *, model, effort,
                 rejection=RPCRejected,
                 buffer_events=DEFAULT_BUFFER_EVENTS,
                 buffer_bytes=DEFAULT_BUFFER_BYTES):
        if not callable(rpc):
            raise Refusal('owned rpc callable required')
        self._rpc = rpc
        self._thread = _bounded(thread_id, ID_BOUND, 'thread id')
        self._model = _bounded(model, LABEL_BOUND, 'model')
        self._effort = _bounded(effort, LABEL_BOUND, 'effort')
        if isinstance(rejection, tuple):
            ok = bool(rejection) and all(
                isinstance(item, type) and issubclass(item, BaseException)
                for item in rejection)
        else:
            ok = isinstance(rejection, type) and issubclass(rejection, BaseException)
        if not ok:
            raise Refusal('typed rejection class required')
        self._rejection = rejection
        if type(buffer_events) is not int or not 1 <= buffer_events <= 4096:
            raise Refusal('invalid event buffer bound')
        if type(buffer_bytes) is not int or not 1024 <= buffer_bytes <= 4 * 1024 * 1024:
            raise Refusal('invalid event byte bound')
        self._buffer_events_bound = buffer_events
        self._buffer_bytes_bound = buffer_bytes
        self._session = None
        self._session_id = None
        self._inflight = None
        self._buffer = []
        self._buffer_bytes = 0
        self._dropped = 0
        self._gap = False
        self._overflow = False
        self._marks = set()   # (local turn id, marker event) recorded once
        self._current = None  # local turn id of the latest submission
        self._held_dropped = set()  # mapped provider ids dropped while held
        self._quarantined = {}  # provider id -> reason; mapping kept as evidence
        self._quarantined_events = 0
        self._inherited = False
        self._local = {}      # validated provider turn id -> local turn facts
        self._provider = {}   # local turn id -> validated provider turn id
        self._activity = False  # potential new-turn activity, even if dropped
        self._last_send = None

    # -- binding and status (zero RPC calls) ------------------------------

    def bind(self, session):
        """Bind exactly one core lead session; never makes an RPC call."""
        if self._session is not None:
            raise Refusal('bridge already bound')
        session_id = getattr(session, 'session_id', None)
        if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
            raise Refusal('invalid lead session id')
        view = session.status(session_id=session_id)
        if view.get('role') != 'lead':
            raise Refusal('not a lead session')
        if (view.get('model') != self._model
                or view.get('requested_effort') != self._effort):
            raise Refusal('pinned model/effort do not match the session record')
        prior = (view.get('generation') != 1 or view.get('history')
                 or view.get('last_turn') or view.get('turn'))
        if prior and view.get('state') in OPEN_STATES:
            # Provider ids already used by this session are unknown here;
            # continuing could accept a reused id as a fresh turn.
            raise Refusal('session has prior provider history; explicit handoff required')
        self._inherited = bool(prior)
        self._session = session
        self._session_id = session_id
        return self.status()

    def status(self):
        """Read-only bridge view; never makes an RPC call."""
        return {
            'bound': self._session is not None,
            'session_id': self._session_id,
            'thread_id': self._thread,
            'model': self._model,
            'effort': self._effort,
            'effective': 'Unknown',
            'inflight': self._inflight is not None,
            'buffered_events': len(self._buffer),
            'dropped_events': self._dropped,
            'gap': self._gap,
            'gap_recorded': (self._current, GAP_EVENT) in self._marks,
            'gap_turns_recorded': sum(1 for _, ev in self._marks if ev == GAP_EVENT),
            'turn_mappings': len(self._local),
            'quarantined_ids': len(self._quarantined),
            'quarantined_events': self._quarantined_events,
            'inherited_history': self._inherited,
            'mapping_capacity': MAX_MAPPINGS,
            'handoff_required': len(self._local) >= MAX_MAPPINGS,
            'unbound_activity': self._activity,
            'supported_methods': list(SUPPORTED_METHODS),
            'last_send': dict(self._last_send) if self._last_send else None,
            'caution': CAUTION,
        }

    # -- owned turn submission --------------------------------------------

    def send_turn(self, facts):
        """One turn/start on the bound thread for one core-approved turn.

        Returns ``{'status': 'accepted'|'rejected'|'uncertain'}`` for the
        core plus bounded diagnostic facts. Exactly one RPC call is made on
        the accepted path and at most one on every other path; there are no
        retries, resends or extra RPCs.
        """
        if self._session is None:
            raise Refusal('bridge not bound')
        if self._inflight is not None:
            raise Refusal('bridge already submitting')
        if not isinstance(facts, dict):
            raise Refusal('invalid turn facts')
        if facts.get('session_id') != self._session_id:
            raise Refusal('session mismatch')
        generation = facts.get('generation')
        if type(generation) is not int or generation < 1:
            raise Refusal('invalid generation')
        turn_id = _bounded(facts.get('turn_id'), ID_BOUND, 'turn id')
        text = _bounded(facts.get('text'), MAX_TEXT_BYTES, 'turn input')
        if turn_id in self._provider:
            raise Refusal('turn already mapped')
        if self._inherited:
            raise Refusal('bound for inspection only; explicit handoff required')
        if len(self._local) >= MAX_MAPPINGS:
            self._last_send = {'status': 'uncertain',
                               'reason': 'mapping capacity exhausted; explicit handoff required'}
            return dict(self._last_send)
        params = {'threadId': self._thread, 'model': self._model, 'effort': self._effort,
                  'input': [{'type': 'text', 'text': text}]}
        self._inflight = {'turn_id': turn_id, 'generation': generation}
        self._current = turn_id
        self._buffer = []
        self._buffer_bytes = 0
        self._dropped = 0
        self._gap = False
        self._overflow = False
        self._held_dropped = set()
        self._activity = False
        try:
            reply = self._rpc(START_METHOD, params)
        except self._rejection:
            if self._activity:
                # A new turn may exist under an unknown id, possibly a reused one.
                self._quarantine_all('typed rejection with potential new-turn activity')
            counts = self._settle(None)
            self._last_send = {
                'status': 'uncertain' if self._activity else 'rejected',
                'reason': ('typed rejection with potential new-turn activity'
                           if self._activity else 'typed rejection without new-turn activity'),
                'dropped_events': self._dropped + counts['foreign_events'] + counts['quarantined_events'],
                'gap': self._gap, 'unbound_activity': self._activity, **counts}
            return dict(self._last_send)
        except Exception:
            self._quarantine_all('rpc failed without a typed rejection')
            counts = self._settle(None)
            self._last_send = {'status': 'uncertain',
                               'reason': 'rpc failed without a typed rejection', **counts}
            return dict(self._last_send)
        provider_turn = self._validate_ack(reply)
        if provider_turn is None:
            self._quarantine_all('turn/start acknowledgement missing, malformed or foreign')
            counts = self._settle(None)
            self._last_send = {
                'status': 'uncertain',
                'reason': 'turn/start acknowledgement missing, malformed or foreign', **counts}
            return dict(self._last_send)
        if provider_turn in self._local:
            # Never adopt or rebind: the mapping stays as evidence only.
            self._quarantine(provider_turn, 'reused provider turn id')
            counts = self._settle(None)
            self._last_send = {
                'status': 'uncertain', 'provider_turn_id': provider_turn,
                'reason': 'reused provider turn id; original mapping retained; explicit handoff required',
                **counts}
            return dict(self._last_send)
        self._bind_mapping(turn_id, provider_turn, generation)
        if self._gap:
            self._record_gap(turn_id, generation,
                             'event buffer overflow; output history incomplete')
        counts = self._settle(provider_turn)
        self._last_send = {
            'status': 'accepted', 'provider_turn_id': provider_turn,
            'dropped_events': self._dropped, **counts,
            'gap': self._gap, 'gap_recorded': (turn_id, GAP_EVENT) in self._marks}
        return dict(self._last_send)

    def _validate_ack(self, reply):
        """A valid acknowledgement is a bounded turn id for this thread."""
        if not isinstance(reply, dict):
            return None
        thread = reply.get('threadId')
        if thread is not None and thread != self._thread:
            return None
        turn = reply.get('turn')
        if not isinstance(turn, dict) or not _bounded_id(turn.get('id')):
            return None
        return turn['id']

    def _bind_mapping(self, turn_id, provider_turn, generation):
        self._provider[turn_id] = provider_turn
        self._local[provider_turn] = {'turn_id': turn_id,
                                      'generation': generation}

    def _quarantine(self, provider_turn, reason):
        """Stop trusting one mapped id; keep the mapping, record evidence."""
        if provider_turn in self._quarantined:
            return
        self._quarantined[provider_turn] = reason
        local = self._local[provider_turn]
        self._record_mark(local['turn_id'], local['generation'], AMBIGUOUS_EVENT,
                          reason + '; later events for this provider turn are quarantined')

    def _quarantine_all(self, reason):
        for provider_turn in list(self._local):
            self._quarantine(provider_turn, reason)

    def _settle(self, new_turn):
        """Resolve held events once the submission outcome is known.

        Events for ``new_turn`` (a fresh validated id) and for mapped,
        non-quarantined ids are now proved and replayed in order; quarantined
        ids are counted only; everything else stays foreign and unadopted.
        """
        replayed = foreign = refused = quarantined = 0
        buffer, self._buffer = self._buffer, []
        held_dropped, self._held_dropped = self._held_dropped, set()
        self._buffer_bytes = 0
        self._inflight = None
        for event in buffer:
            provider_turn = event['turn_id']
            if provider_turn in self._quarantined:
                quarantined += 1
                self._quarantined_events += 1
                continue
            if provider_turn not in self._local:
                foreign += 1
                continue
            if event.get('oversized'):
                self._oversized(provider_turn)
                refused += 1
                continue
            result = self._dispatch(event)
            if result['action'] == 'refused':
                refused += 1
            else:
                replayed += 1
        for provider_turn in sorted(held_dropped):
            if provider_turn in self._local and provider_turn not in self._quarantined:
                local = self._local[provider_turn]
                self._record_gap(local['turn_id'], local['generation'],
                                 'event buffer overflow while attribution was unresolved; '
                                 'output history incomplete')
        return {'replayed_events': replayed, 'foreign_events': foreign,
                'refused_events': refused, 'quarantined_events': quarantined}

    def _oversized(self, provider_turn):
        local = self._local[provider_turn]
        if local['turn_id'] == self._current:
            self._gap = True
        self._record_gap(local['turn_id'], local['generation'],
                         'delta bound exceeded; output history incomplete')

    # -- provider notifications --------------------------------------------

    def handle_notification(self, msg):
        """Controlled observation of one provider notification; never raises."""
        try:
            return self._notify(msg)
        except Exception as exc:
            return {'action': 'refused',
                    'reason': 'bridge error: %s: %s' % (type(exc).__name__, exc)}

    def _notify(self, msg):
        if not isinstance(msg, dict):
            return {'action': 'ignored', 'reason': 'malformed notification'}
        method = msg.get('method')
        if method not in SUPPORTED_METHODS:
            return {'action': 'ignored', 'reason': 'unsupported method'}
        params = msg.get('params')
        if not isinstance(params, dict):
            return {'action': 'ignored', 'reason': 'malformed notification'}
        if params.get('threadId') != self._thread:
            return {'action': 'ignored', 'reason': 'foreign thread'}
        event = self._extract(method, params)
        if event is None:
            return {'action': 'ignored', 'reason': 'malformed notification'}
        if event['turn_id'] in self._quarantined:
            # Ambiguous identity: never dispatched to the old or a new turn.
            self._quarantined_events += 1
            return {'action': 'quarantined', 'reason': 'ambiguous provider turn identity',
                    'gap': True}
        attributed = event['turn_id'] in self._local
        inflight = self._inflight is not None
        if not attributed and not inflight:
            # Unknown mapping (for example after reopen) stays unknown; the
            # first observed provider id is never adopted.
            return {'action': 'ignored', 'reason': 'unbound provider turn'}
        oversized = 'delta' in event and event['bytes'] > DELTA_BOUND
        if inflight and attributed:
            # The pending acknowledgement may reuse this id: hold, don't write.
            if oversized:
                event = {'method': event['method'], 'turn_id': event['turn_id'],
                         'bytes': 0, 'oversized': True}
            return self._buffer_event(event)
        if inflight:
            self._activity = True
        if oversized:
            if attributed:
                self._oversized(event['turn_id'])
                return {'action': 'refused', 'reason': 'delta bound exceeded',
                        'gap': True}
            self._gap = True
            self._dropped += 1
            return {'action': 'dropped', 'reason': 'delta bound exceeded',
                    'gap': True}
        if attributed:
            return self._dispatch(event)
        return self._buffer_event(event)

    def _extract(self, method, params):
        """Select only bounded lifecycle/delta fields; never raw envelopes."""
        if method == 'turn/started':
            turn = params.get('turn')
            if not isinstance(turn, dict):
                return None
            return self._event(method, turn.get('id'))
        if method == 'turn/completed':
            turn = params.get('turn')
            if (not isinstance(turn, dict)
                    or turn.get('status') not in TERMINAL_STATUS):
                return None
            event = self._event(method, turn.get('id'))
            if event is None:
                return None
            event['status'] = turn['status']
            return event
        event = self._event(method, params.get('turnId'))
        delta = params.get('delta')
        if event is None or not isinstance(delta, str):
            return None
        try:
            size = len(delta.encode('utf-8'))
        except (UnicodeError, RecursionError):
            return None
        event['delta'] = delta
        event['bytes'] = size
        return event

    @staticmethod
    def _event(method, turn_id):
        if not _bounded_id(turn_id):
            return None
        return {'method': method, 'turn_id': turn_id, 'bytes': 0}

    def _buffer_event(self, event):
        if self._overflow:
            self._held(event)
            self._dropped += 1
            return {'action': 'dropped', 'reason': 'event buffer overflow',
                    'gap': True}
        if (len(self._buffer) >= self._buffer_events_bound
                or self._buffer_bytes + event['bytes'] > self._buffer_bytes_bound):
            self._overflow = True
            self._gap = True
            self._held(event)
            self._dropped += 1
            return {'action': 'dropped', 'reason': 'event buffer overflow',
                    'gap': True}
        self._buffer.append(event)
        self._buffer_bytes += event['bytes']
        return {'action': 'buffered'}

    def _held(self, event):
        if event['turn_id'] in self._local:
            self._held_dropped.add(event['turn_id'])

    def _dispatch(self, event):
        """Deliver one fully attributed event to the bound core session."""
        local = self._local[event['turn_id']]
        session_id = self._session_id
        generation = local['generation']
        turn_id = local['turn_id']
        method = event['method']
        try:
            if method == 'turn/started':
                self._session.observe_turn_started(
                    session_id=session_id, generation=generation, turn_id=turn_id)
                return {'action': 'observed', 'core': 'turn_started'}
            if method == 'turn/completed':
                # A turn completing is not Source/adapter/process exit.
                self._session.observe_terminal(
                    session_id=session_id, generation=generation, turn_id=turn_id,
                    status=event['status'], exit_code=None)
                return {'action': 'observed', 'core': 'terminal',
                        'status': event['status'], 'exit_code': None}
            kind = ('agent_message' if method == 'item/agentMessage/delta'
                    else 'command_output')
            self._session.observe_output(
                session_id=session_id, generation=generation, turn_id=turn_id,
                kind=kind, data={'delta': event['delta']})
            return {'action': 'observed', 'core': kind}
        except Exception as exc:
            # The core's Refusal distinction (for example a saved terminal
            # fact plus a journal-write error) is retained verbatim and is
            # never converted into proof of process exit or delivery.
            return {'action': 'refused',
                    'reason': '%s: %s' % (type(exc).__name__, exc)}

    def _record_gap(self, turn_id, generation, detail):
        """Record one honest gap fact per local turn; never fake completeness."""
        self._record_mark(turn_id, generation, GAP_EVENT, detail)

    def _record_mark(self, turn_id, generation, event, detail):
        """One bounded lifecycle marker per (local turn, kind)."""
        if self._session is None or (turn_id, event) in self._marks:
            return
        try:
            self._session.observe_output(
                session_id=self._session_id, generation=generation,
                turn_id=turn_id, kind='lifecycle',
                data={'event': event, 'detail': detail})
            self._marks.add((turn_id, event))
        except Exception:
            # The core cannot record the marker (for example a closed
            # archive): the limitation stays explicit in status; history is
            # never claimed complete and no marker of another kind is faked.
            pass
