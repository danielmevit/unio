#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Adaptive lead effort policy test suite: no providers, no connections.

Every check imports tools/lead-effort.py directly through importlib so old
embedded installer bytes cannot make these tests pass accidentally.
"""
import importlib.util
from pathlib import Path
import tempfile

SOURCE = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, SOURCE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pe = _load('lead_effort', 'tools/lead-effort.py')


def refuses(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except pe.Refusal as exc:
        return str(exc)
    raise AssertionError('expected Refusal')


class Query:
    """Counting fake owned-connection query."""

    def __init__(self, efforts):
        self.efforts = list(efforts)
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return list(self.efforts)


def policy_with(efforts, **kwargs):
    query = Query(efforts)
    policy = pe.AdaptiveEffortPolicy(**kwargs)
    policy.query_supported(query)
    return policy, query


def run_suite(base):
    # 0. Module surface: importable policy only, no process/network launch.
    assert not any(hasattr(pe, name) for name in
                   ('subprocess', 'socket', 'pty', 'Popen', 'system', 'fork'))
    assert pe.RANK == ('low', 'medium', 'high', 'xhigh')
    assert 'max' not in pe.RANK and 'ultra' not in pe.RANK
    assert pe.KINDS == ('coordination', 'planning', 'review')
    print('ok module exposes no process/network launch surface', flush=True)

    # 1. Ceiling must be a known rank no higher than xhigh.
    assert 'ceiling must be a known effort' in refuses(
        pe.AdaptiveEffortPolicy, ceiling='max')
    assert 'ceiling must be a known effort' in refuses(
        pe.AdaptiveEffortPolicy, ceiling='ultra')
    assert 'ceiling must be a known effort' in refuses(
        pe.AdaptiveEffortPolicy, ceiling='')
    pe.AdaptiveEffortPolicy(ceiling='xhigh')
    pe.AdaptiveEffortPolicy(ceiling='low')
    print('ok ceiling is a known rank no higher than xhigh', flush=True)

    # 2. Supported efforts are queried exactly once; repeats never re-query.
    policy, query = policy_with(['low', 'medium', 'high', 'xhigh'])
    assert query.calls == 1
    assert policy.supported() == ('low', 'medium', 'high', 'xhigh')
    again = policy.query_supported(query)
    assert again == ('low', 'medium', 'high', 'xhigh')
    assert query.calls == 1
    print('ok supported efforts queried exactly once', flush=True)

    # 3. Invalid, empty or unadvertised query results refuse.
    policy = pe.AdaptiveEffortPolicy()
    assert 'no advertised efforts' in refuses(
        policy.query_supported, Query([]))
    def broken():
        raise RuntimeError('owned connection lost')
    assert 'supported effort query failed' in refuses(
        policy.query_supported, broken)
    assert 'no advertised efforts' in refuses(
        policy.query_supported, lambda: 'low')
    assert 'invalid effort' in refuses(
        policy.query_supported, lambda: [b'low'])
    assert 'effort bound exceeded' in refuses(
        policy.query_supported, lambda: ['low' * 100])
    print('ok invalid advertised effort sets refuse', flush=True)

    # 4. Missing low or ceiling refuses; no fallback effort is invented.
    assert 'unsupported ceiling effort' in refuses(
        policy_with, ['low', 'medium', 'high'])
    assert 'unsupported coordination effort' in refuses(
        policy_with, ['medium', 'high', 'xhigh'])
    policy, _ = policy_with(['low', 'xhigh'])
    assert policy.select_for_kind('planning') == 'xhigh'
    print('ok missing low or ceiling refuses without fallback', flush=True)

    # 5. Automatic selection by explicit work kind only.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh'])
    assert policy.select_for_kind('coordination') == 'low'
    assert policy.select_for_kind('planning') == 'xhigh'
    assert policy.select_for_kind('review') == 'xhigh'
    assert 'unknown work kind' in refuses(policy.select_for_kind, 'vibes')
    assert 'unknown work kind' in refuses(policy.select_for_kind, None)
    low_policy, _ = policy_with(['low'], ceiling='low')
    assert low_policy.select_for_kind('review') == 'low'
    print('ok auto selects low for coordination and ceiling for planning/review',
          flush=True)

    # 6. Unsupported choices (max/ultra/unadvertised) refuse everywhere.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh', 'max'])
    assert 'max' in policy.supported()  # advertised but never selectable
    assert 'unsupported manual effort' in refuses(policy.set_manual, 'max')
    assert 'unsupported requested effort' in refuses(
        policy.request_next_turn, 'ultra')
    assert 'unsupported manual effort' in refuses(policy.set_manual, 'minimal')
    assert 'effort bound exceeded' in refuses(
        policy.request_next_turn, 'medium' * 30)
    print('ok max/ultra/unadvertised efforts refuse with no fallback', flush=True)

    # 7. decide_turn records immutable per-turn decisions.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh'])
    first = policy.decide_turn('turn-0123456789abcdef', 'coordination')
    assert first == {'turn_id': 'turn-0123456789abcdef', 'kind': 'coordination',
                      'effort': 'low', 'source': 'auto',
                      'reason': 'automatic coordination effort'}
    first['effort'] = 'xhigh'  # a returned copy must never rewrite history
    again = policy.decisions()[0]
    assert again['effort'] == 'low'
    assert 'invalid turn id' in refuses(
        policy.decide_turn, 'turn-nothex', 'coordination')
    assert 'unknown work kind' in refuses(
        policy.decide_turn, 'turn-0123456789abcdef', 'guessing')
    for index in range(pe.MAX_DECISIONS + 4):
        policy.decide_turn('turn-%016x' % index, 'coordination')
    assert len(policy.decisions()) == pe.MAX_DECISIONS
    print('ok per-turn decisions are immutable and bounded', flush=True)

    # 8. Manual override suspends auto until auto is selected again.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh'])
    policy.set_manual('high', 'owner wants high')
    assert policy.status()['mode'] == 'manual'
    decision = policy.decide_turn('turn-0123456789abcdef', 'coordination')
    assert decision['effort'] == 'high' and decision['source'] == 'manual'
    policy.set_auto()
    decision = policy.decide_turn('turn-0123456789abcdee', 'coordination')
    assert decision['effort'] == 'low' and decision['source'] == 'auto'
    print('ok manual override suspends auto; auto selection resumes it', flush=True)

    # 9. Pending next-turn request applies once, then auto resumes.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh'])
    policy.request_next_turn('medium', 'owner request')
    assert policy.status()['pending_next_turn']['effort'] == 'medium'
    decision = policy.decide_turn('turn-0123456789abcdef', 'coordination')
    assert decision['effort'] == 'medium' and decision['source'] == 'pending'
    assert policy.status()['pending_next_turn'] is None
    decision = policy.decide_turn('turn-0123456789abcdee', 'coordination')
    assert decision['effort'] == 'low' and decision['source'] == 'auto'
    policy.request_next_turn('high')
    policy.request_next_turn('medium')  # a newer explicit request replaces
    assert policy.status()['pending_next_turn']['effort'] == 'medium'
    policy.set_manual('low')  # manual clears any pending request
    assert policy.status()['pending_next_turn'] is None
    print('ok pending request applies exactly once at the next turn', flush=True)

    # 10. Worker terminal wakeups: one review wakeup per event, once each.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh'])
    assert 'invalid worker id' in refuses(policy.record_wakeup, 'bad id!')
    assert policy.consume_wakeup() is None
    policy.record_wakeup('worker-a')
    policy.record_wakeup('worker-b')
    assert policy.pending_wakeups() == 2
    assert policy.consume_wakeup() == {'worker': 'worker-a', 'reason': ''}
    assert policy.consume_wakeup() == {'worker': 'worker-b', 'reason': ''}
    assert policy.consume_wakeup() is None
    assert policy.status()['wakeups_consumed'] == 2
    for index in range(pe.MAX_WAKEUPS):
        policy.record_wakeup('worker-%d' % index)
    assert 'wakeup queue exhausted' in refuses(policy.record_wakeup, 'worker-x')
    print('ok one wakeup per worker terminal event, consumed exactly once',
          flush=True)

    # 11. Snapshot/load roundtrip and tamper refusal.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh'])
    policy.set_manual('high', 'hold')
    policy.set_auto()
    policy.request_next_turn('medium', 'next phase')
    policy.record_wakeup('worker-a')
    policy.decide_turn('turn-0123456789abcdef', 'review')
    restored = pe.AdaptiveEffortPolicy.load(policy.snapshot())
    assert restored.status() == policy.status()
    assert restored.decisions() == policy.decisions()
    snapshot = policy.snapshot()
    snapshot.pop('ceiling')
    assert 'invalid policy snapshot' in refuses(pe.AdaptiveEffortPolicy.load,
                                                snapshot)
    snapshot = policy.snapshot()
    snapshot['mode'] = 'vibes'
    assert 'invalid policy snapshot' in refuses(pe.AdaptiveEffortPolicy.load,
                                                snapshot)
    snapshot = policy.snapshot()
    snapshot['decisions'][0]['effort'] = 'ultra'
    assert 'invalid policy snapshot' in refuses(pe.AdaptiveEffortPolicy.load,
                                                snapshot)
    assert 'invalid policy snapshot' in refuses(pe.AdaptiveEffortPolicy.load, {})
    print('ok snapshot roundtrip refuses tampered persistence', flush=True)

    # 12. Effective effort stays Unknown everywhere.
    policy, _ = policy_with(['low', 'medium', 'high', 'xhigh'])
    status = policy.status()
    assert status['effective'] == 'Unknown'
    assert 'effective provider effort remains Unknown' in status['caution']
    decision = policy.decide_turn('turn-0123456789abcdef', 'planning')
    assert 'effective' not in decision
    print('ok effective provider effort remains Unknown', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='lead-effort-') as base:
        run_suite(base)
    print('all adaptive lead effort policy checks passed')


if __name__ == '__main__':
    main()
