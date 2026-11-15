#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Adaptive lead effort policy — importable decision component.

Owned policy backend for the experimental `unio lead-session` vertical
slice (contract 0532-ADAPTIVE-LEAD-EFFORT-V1). It decides which explicit
reasoning effort to request per lead turn and never talks to a provider
itself: the supported model efforts are queried exactly once through an
injected callable that represents one already authorized owned connection
(the `model/list` seam of the Codex app-server), and every decision is
handed to the caller to send explicitly with `turn/start`.

Enforced by this component:
- a fixed known effort rank (low, medium, high, xhigh); the configurable
  ceiling must be a known rank no higher than xhigh. Advertised values
  outside the known rank (for example max or ultra) are refused for
  selection; nothing is invented and there is no fallback effort;
- the supported set is queried exactly once per policy instance; a second
  query returns the recorded set without another call. The ceiling and the
  coordination effort (low) must both be advertised and selectable, or the
  policy refuses rather than substituting;
- automatic mode selects low for routine coordination and the ceiling for
  substantive planning/review; the work kind comes only from the explicit
  caller request or a recorded worker-terminal wakeup event, never from
  arbitrary prose;
- a manual owner override suspends automatic selection until auto is
  selected again; an explicit next-turn request is recorded as pending and
  consumed by the next decided turn only (the active turn is never steered;
  the app-server schema has no effort override on turn/steer);
- every decided turn gets one immutable decision record (turn id, kind,
  effort, source, reason); records are append-only and bounded;
- worker terminal events queue at most one review wakeup each; a wakeup is
  consumed exactly once and heartbeats or status polling cannot create one;
- the effective provider-side effort remains Unknown everywhere; only the
  requested effort is recorded.

The caller still owns: the owned connection, sending turn/start on the
owned thread, authority/ownership admission, STOP semantics and counting
the registered lead exactly once. See docs/ADAPTIVE-LEAD-EFFORT.md.
"""
import re

RANK = ('low', 'medium', 'high', 'xhigh')
KINDS = ('coordination', 'planning', 'review')
DEFAULT_CEILING = 'xhigh'
COORDINATION_EFFORT = 'low'
MAX_DECISIONS = 64
MAX_WAKEUPS = 8
REASON_BOUND = 256
EFFORT_BOUND = 32
TURN_ID = re.compile(r'turn-[0-9a-f]{16}')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
CAUTION = ('requested effort only; the effective provider effort remains Unknown')


class Refusal(Exception):
    """A controlled policy refusal; no effect was applied."""


def _rank(effort):
    return RANK.index(effort)


def _bounded_effort(value):
    if not isinstance(value, str) or not value or '\x00' in value:
        raise Refusal('invalid effort')
    if len(value.encode('utf-8', 'replace')) > EFFORT_BOUND:
        raise Refusal('effort bound exceeded')
    return value


def _bounded_reason(value):
    if value is None:
        return ''
    if not isinstance(value, str) or '\x00' in value:
        raise Refusal('invalid reason')
    if len(value.encode('utf-8', 'replace')) > REASON_BOUND:
        raise Refusal('reason bound exceeded')
    return value


class AdaptiveEffortPolicy:
    """Per-session adaptive effort decisions; zero provider calls."""

    def __init__(self, *, ceiling=DEFAULT_CEILING):
        if ceiling not in RANK or _rank(ceiling) > _rank('xhigh'):
            raise Refusal('ceiling must be a known effort no higher than xhigh')
        self._ceiling = ceiling
        self._supported = None
        self._queried = False
        self._mode = 'auto'
        self._manual = None
        self._pending = None
        self._wakeups = []
        self._wakeups_consumed = 0
        self._decisions = []

    # -- supported effort query (once) ------------------------------------

    def query_supported(self, query):
        """Query the advertised efforts once through the owned connection.

        ``query`` is an injected callable returning the advertised effort
        strings for the pinned model. The first call records the set; every
        later call returns the recorded set without invoking ``query``.
        """
        if self._queried:
            return tuple(self._supported)
        try:
            advertised = query()
        except Exception as exc:
            raise Refusal('supported effort query failed') from exc
        if not isinstance(advertised, (list, tuple)) or not advertised:
            raise Refusal('no advertised efforts')
        seen = []
        for item in advertised:
            item = _bounded_effort(item)
            if item not in seen:
                seen.append(item)
        self._supported = tuple(seen)
        self._queried = True
        # Both automatic choices must be genuinely selectable; no fallback.
        self._require_selectable(COORDINATION_EFFORT, 'coordination effort')
        self._require_selectable(self._ceiling, 'ceiling effort')
        return tuple(self._supported)

    def supported(self):
        if not self._queried:
            raise Refusal('supported efforts not queried')
        return tuple(self._supported)

    def _selectable(self, effort):
        return (self._queried and effort in RANK
                and effort in self._supported
                and _rank(effort) <= _rank(self._ceiling))

    def _require_selectable(self, effort, name):
        if not self._selectable(effort):
            raise Refusal('unsupported ' + name + ': ' + str(effort))

    # -- controls -----------------------------------------------------------

    def select_for_kind(self, kind):
        """Automatic choice for one explicit work kind."""
        if kind not in KINDS:
            raise Refusal('unknown work kind')
        if kind == 'coordination':
            effort = COORDINATION_EFFORT
        else:
            effort = self._ceiling
        self._require_selectable(effort, 'effort for ' + kind)
        return effort

    def set_manual(self, effort, reason=None):
        """Manual owner override; suspends auto until auto is selected."""
        effort = _bounded_effort(effort)
        self._require_selectable(effort, 'manual effort')
        self._manual = effort
        self._mode = 'manual'
        self._pending = None
        return self.status()

    def set_auto(self, reason=None):
        """Re-enable automatic selection."""
        self._mode = 'auto'
        self._manual = None
        self._pending = None
        return self.status()

    def request_next_turn(self, effort, reason=None):
        """Record an explicit pending effort for the next turn only."""
        effort = _bounded_effort(effort)
        self._require_selectable(effort, 'requested effort')
        self._pending = {'effort': effort, 'reason': _bounded_reason(reason)}
        return self.status()

    # -- worker wakeups -----------------------------------------------------

    def record_wakeup(self, worker_id, reason=None):
        """One registered worker terminal event wakes the lead once."""
        if not isinstance(worker_id, str) or not LABEL.fullmatch(worker_id):
            raise Refusal('invalid worker id')
        if len(self._wakeups) >= MAX_WAKEUPS:
            raise Refusal('wakeup queue exhausted')
        self._wakeups.append({'worker': worker_id,
                              'reason': _bounded_reason(reason)})
        return self.status()

    def consume_wakeup(self):
        """Consume one pending wakeup exactly once; None when none pending."""
        if not self._wakeups:
            return None
        wakeup = self._wakeups.pop(0)
        self._wakeups_consumed += 1
        return dict(wakeup)

    def pending_wakeups(self):
        return len(self._wakeups)

    # -- per-turn decision ---------------------------------------------------

    def decide_turn(self, turn_id, kind, reason=None):
        """Decide the explicit effort for one new turn; immutable record.

        Priority: pending explicit request, then manual override, then the
        automatic choice for the work kind. The decision is recorded once
        and can never be rewritten.
        """
        if not isinstance(turn_id, str) or not TURN_ID.fullmatch(turn_id):
            raise Refusal('invalid turn id')
        if kind not in KINDS:
            raise Refusal('unknown work kind')
        if self._pending is not None:
            effort = self._pending['effort']
            source = 'pending'
            why = self._pending['reason'] or ('pending owner request')
            self._require_selectable(effort, 'pending effort')
            self._pending = None
        elif self._mode == 'manual':
            effort = self._manual
            source = 'manual'
            why = 'manual owner override'
            self._require_selectable(effort, 'manual effort')
        else:
            effort = self.select_for_kind(kind)
            source = 'auto'
            why = 'automatic ' + kind + ' effort'
        decision = {'turn_id': turn_id, 'kind': kind, 'effort': effort,
                    'source': source, 'reason': _bounded_reason(reason) or why}
        self._decisions.append(decision)
        del self._decisions[:-MAX_DECISIONS]
        return dict(decision)

    def decisions(self):
        """Bounded immutable per-turn decision records (copies)."""
        return tuple(dict(item) for item in self._decisions)

    # -- views and persistence ------------------------------------------------

    def status(self):
        return {
            'mode': self._mode,
            'ceiling': self._ceiling,
            'supported_efforts': list(self._supported) if self._queried else None,
            'queried': self._queried,
            'requested': (self._pending['effort'] if self._pending
                         else self._manual if self._mode == 'manual'
                         else None),
            'pending_next_turn': dict(self._pending) if self._pending else None,
            'manual_effort': self._manual,
            'pending_wakeups': len(self._wakeups),
            'wakeups_consumed': self._wakeups_consumed,
            'decisions': len(self._decisions),
            'effective': 'Unknown',
            'caution': CAUTION,
        }

    def snapshot(self):
        return {
            'ceiling': self._ceiling,
            'supported': list(self._supported) if self._queried else None,
            'queried': self._queried,
            'mode': self._mode,
            'manual': self._manual,
            'pending': dict(self._pending) if self._pending else None,
            'wakeups': [dict(item) for item in self._wakeups],
            'wakeups_consumed': self._wakeups_consumed,
            'decisions': [dict(item) for item in self._decisions],
        }

    @classmethod
    def load(cls, doc):
        """Restore a policy from a persisted snapshot; refuses tampering."""
        if not isinstance(doc, dict) or set(doc) != {
                'ceiling', 'supported', 'queried', 'mode', 'manual',
                'pending', 'wakeups', 'wakeups_consumed', 'decisions'}:
            raise Refusal('invalid policy snapshot')
        policy = cls(ceiling=doc['ceiling'])
        if doc['queried']:
            if (not isinstance(doc['supported'], list) or not doc['supported']):
                raise Refusal('invalid policy snapshot')
            policy.query_supported(lambda: list(doc['supported']))
        else:
            if doc['supported'] is not None:
                raise Refusal('invalid policy snapshot')
        if doc['mode'] not in ('auto', 'manual'):
            raise Refusal('invalid policy snapshot')
        if doc['mode'] == 'manual':
            if not isinstance(doc['manual'], str):
                raise Refusal('invalid policy snapshot')
            policy.set_manual(doc['manual'])
        elif doc['manual'] is not None:
            raise Refusal('invalid policy snapshot')
        if doc['pending'] is not None:
            if not isinstance(doc['pending'], dict):
                raise Refusal('invalid policy snapshot')
            policy.request_next_turn(doc['pending'].get('effort'),
                                     doc['pending'].get('reason'))
        if not isinstance(doc['wakeups'], list) or len(doc['wakeups']) > MAX_WAKEUPS:
            raise Refusal('invalid policy snapshot')
        for item in doc['wakeups']:
            if not isinstance(item, dict):
                raise Refusal('invalid policy snapshot')
            policy.record_wakeup(item.get('worker'), item.get('reason'))
        if type(doc['wakeups_consumed']) is not int or doc['wakeups_consumed'] < 0:
            raise Refusal('invalid policy snapshot')
        policy._wakeups_consumed = doc['wakeups_consumed']
        if not isinstance(doc['decisions'], list) or len(doc['decisions']) > MAX_DECISIONS:
            raise Refusal('invalid policy snapshot')
        for item in doc['decisions']:
            if not (isinstance(item, dict)
                    and set(item) == {'turn_id', 'kind', 'effort', 'source', 'reason'}
                    and isinstance(item['turn_id'], str)
                    and TURN_ID.fullmatch(item['turn_id'])
                    and item['kind'] in KINDS
                    and isinstance(item['effort'], str)
                    and item['effort'] in RANK
                    and item['source'] in ('pending', 'manual', 'auto')
                    and (item['reason'] is None or isinstance(item['reason'], str))):
                raise Refusal('invalid policy snapshot')
            policy._decisions.append(dict(item))
        return policy
