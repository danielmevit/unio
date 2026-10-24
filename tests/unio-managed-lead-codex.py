#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Owned Codex RPC bridge test suite: fake owned connection, no providers.

Every check calls tools/managed-lead-codex.py and tools/managed-lead.py
directly through importlib so old embedded installer bytes cannot make
these tests pass accidentally. State and RPC call counts are asserted
outside the notification callbacks; no callback swallows a check.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, SOURCE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ml = _load('managed_lead', 'tools/managed-lead.py')
br = _load('managed_lead_codex', 'tools/managed-lead-codex.py')

THREAD = 'thread-owned-1'
MODEL = 'gpt-5.4-codex'
EFFORT = 'high'


def authority_ok(facts):
    return {'role': 'lead', 'authorized': True}


def ownership_ok(facts):
    return True


def started(thread, turn_id):
    return {'method': 'turn/started',
            'params': {'threadId': thread,
                       'turn': {'id': turn_id, 'status': 'inProgress'}}}


def agent_delta(thread, turn_id, delta):
    return {'method': 'item/agentMessage/delta',
            'params': {'threadId': thread, 'turnId': turn_id,
                       'itemId': 'item-1', 'delta': delta}}


def command_delta(thread, turn_id, delta):
    return {'method': 'item/commandExecution/outputDelta',
            'params': {'threadId': thread, 'turnId': turn_id,
                       'itemId': 'item-2', 'delta': delta}}


def completed(thread, turn_id, status='completed'):
    return {'method': 'turn/completed',
            'params': {'threadId': thread,
                       'turn': {'id': turn_id, 'status': status}}}


def ack(turn_id):
    return {'turn': {'id': turn_id, 'status': 'inProgress'}}


class FakeRPC:
    """Deterministic fake owned app-server RPC connection.

    Records every call. ``before`` holds notifications the owned rpc loop
    dispatches through the bridge event sink while the synchronous call is
    still pending, before its reply.
    """

    def __init__(self):
        self.calls = []
        self.bridge = None
        self.before = []
        self.behavior = ('reply', ack('provider-turn-1'))

    def __call__(self, method, params):
        self.calls.append((method, params))
        for msg in self.before:
            self.bridge.handle_notification(msg)
        self.before = []
        kind = self.behavior[0]
        if kind == 'reply':
            return self.behavior[1]
        if kind == 'reject':
            raise br.RPCRejected('provider rejected turn/start')
        if kind == 'raise':
            raise self.behavior[1]
        raise AssertionError('unknown fake behavior')


class Harness:
    counter = 0

    def __init__(self, base, *, authority=authority_ok, ownership=ownership_ok,
                 **bridge):
        Harness.counter += 1
        self.base = Path(base)
        self.root = self.base / ('codex-lead-' + str(Harness.counter))
        self.rpc = FakeRPC()
        self.bridge = br.CodexLeadTransport(
            self.rpc, THREAD, model=MODEL, effort=EFFORT, **bridge)
        self.authority = authority
        self.ownership = ownership
        self.session = ml.create_lead_session(
            self.root, transport=self.bridge, authority=authority,
            ownership=ownership, workspace='/private/lead-ws',
            budget_label='codex-shared', route='codex-app-server',
            model=MODEL, effort=EFFORT)
        self.rpc.bridge = self.bridge
        self.bridge.bind(self.session)
        self.sid = self.session.session_id

    def open(self):
        """Reopen the recorded session with a fresh controller and bridge."""
        rpc = FakeRPC()
        bridge = br.CodexLeadTransport(rpc, THREAD, model=MODEL, effort=EFFORT)
        session = ml.LeadSession(self.root, self.sid, transport=bridge,
                                 authority=self.authority,
                                 ownership=self.ownership)
        rpc.bridge = bridge
        bridge.bind(session)
        return rpc, bridge, session

    def submit(self, request_id, text='next turn input'):
        generation = self.session.status(session_id=self.sid)['generation']
        result = self.session.submit_next_turn(
            session_id=self.sid, generation=generation,
            request_id=request_id, text=text)
        only_turn_start(self.rpc)
        return result

    def notify(self, msg):
        return self.bridge.handle_notification(msg)

    def view(self):
        return self.session.status(session_id=self.sid)

    def output(self):
        return self.session.read_output(session_id=self.sid)


def refuses(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except (ml.Refusal, br.Refusal) as exc:
        return str(exc)
    raise AssertionError('expected Refusal')


def only_turn_start(rpc):
    assert rpc.calls, 'expected at least one owned rpc call'
    assert all(method == br.START_METHOD for method, _ in rpc.calls), rpc.calls
    assert all(params.get('model') == MODEL and params.get('effort') == EFFORT
               for _, params in rpc.calls), rpc.calls


def run_suite(base):
    # 0. Module surface: importable bridge only, no process/network launch.
    assert not any(hasattr(br, name) for name in
                   ('subprocess', 'socket', 'pty', 'Popen', 'system', 'fork'))
    assert br.START_METHOD == 'turn/start'
    assert br.SUPPORTED_METHODS == ('turn/started', 'item/agentMessage/delta',
                                    'item/commandExecution/outputDelta',
                                    'turn/completed')
    assert 'thread/start' not in br.SUPPORTED_METHODS
    print('ok module exposes no process/network launch surface and no thread lifecycle', flush=True)

    # 1. Construction, bind and status make zero RPC calls.
    h = Harness(base)
    assert h.rpc.calls == []
    view = h.bridge.status()
    assert view['bound'] is True and view['session_id'] == h.sid
    assert view['thread_id'] == THREAD and view['model'] == MODEL
    assert view['effort'] == EFFORT and view['effective'] == 'Unknown'
    assert view['turn_mappings'] == 0 and view['inflight'] is False
    assert 'no native lead is claimed' in view['caution']
    assert h.rpc.calls == []
    # A second bind refuses; a mismatched pinned model refuses; both silent.
    assert 'already bound' in refuses(h.bridge.bind, h.session)
    other = br.CodexLeadTransport(FakeRPC(), THREAD, model='other-model',
                                 effort=EFFORT)
    assert 'do not match' in refuses(other.bind, h.session)
    # Invalid constructor shapes refuse before anything is callable.
    assert 'thread id' in refuses(br.CodexLeadTransport, h.rpc, '',
                                 model=MODEL, effort=EFFORT)
    assert 'typed rejection' in refuses(br.CodexLeadTransport, h.rpc, THREAD,
                                        model=MODEL, effort=EFFORT, rejection=int)
    assert 'event buffer bound' in refuses(br.CodexLeadTransport, h.rpc, THREAD,
                                           model=MODEL, effort=EFFORT, buffer_events=0)
    # Direct fact validation refuses before any RPC call.
    for bad in ({}, {'session_id': 'lead-' + '0' * 24, 'generation': 1,
                     'turn_id': 'turn-x', 'text': 'x'},
                {'session_id': h.sid, 'generation': 0,
                 'turn_id': 'turn-x', 'text': 'x'},
                {'session_id': h.sid, 'generation': 1, 'turn_id': 'turn-x',
                 'text': 'x' * 8193},
                {'session_id': h.sid, 'generation': 1, 'turn_id': 'turn-x',
                 'text': ''}):
        error = refuses(h.bridge.send_turn, bad)
        assert any(part in error for part in
                   ('invalid', 'mismatch', 'bound exceeded')), error
    unbound = br.CodexLeadTransport(FakeRPC(), THREAD, model=MODEL, effort=EFFORT)
    assert 'not bound' in refuses(unbound.send_turn,
                                  {'session_id': 'lead-' + '0' * 24,
                                   'generation': 1, 'turn_id': 'turn-x',
                                   'text': 'x'})
    assert h.rpc.calls == []
    print('ok construction, bind, status and fact validation with zero rpc calls', flush=True)

    # 2. Two completed turns on one connection with exact correlations.
    h.rpc.behavior = ('reply', ack('prov-a'))
    r1 = h.submit('turn-one', 'first turn input')
    assert r1['state'] == 'accepted' and r1['generation'] == 1
    only_turn_start(h.rpc)
    method, params = h.rpc.calls[0]
    assert params == {'threadId': THREAD, 'model': MODEL, 'effort': EFFORT,
                      'input': [{'type': 'text', 'text': 'first turn input'}]}
    assert h.view()['state'] == 'running'
    assert h.notify(started(THREAD, 'prov-a'))['action'] == 'observed'
    assert h.notify(agent_delta(THREAD, 'prov-a', 'useful lead text\n'))['action'] == 'observed'
    assert h.notify(command_delta(THREAD, 'prov-a', '$ ls\n'))['action'] == 'observed'
    assert h.notify(completed(THREAD, 'prov-a'))['action'] == 'observed'
    view = h.view()
    assert view['state'] == 'terminal' and view['generation'] == 2
    assert view['last_turn']['status'] == 'completed'
    assert view['last_turn']['exit_code'] is None
    assert view['turns_completed'] == 1
    h.rpc.behavior = ('reply', ack('prov-b'))
    r2 = h.submit('turn-two', 'second turn input')
    assert r2['state'] == 'accepted' and r2['generation'] == 2
    assert len(h.rpc.calls) == 2
    _, params2 = h.rpc.calls[1]
    assert params2['input'] == [{'type': 'text', 'text': 'second turn input'}]
    assert params2['threadId'] == THREAD and params2['effort'] == EFFORT
    h.notify(agent_delta(THREAD, 'prov-b', 'second answer\n'))
    h.notify(completed(THREAD, 'prov-b'))
    view = h.view()
    assert view['generation'] == 3 and view['turns_completed'] == 2
    out = h.output()
    kinds = [rec['kind'] for rec in out['records']]
    assert kinds == ['agent_message', 'command_output', 'lifecycle',
                     'agent_message', 'lifecycle'], kinds
    assert out['gap'] is False and out['output_cursor'] == 5
    assert [rec['turn_id'] for rec in out['records'][:2]] == [r1['turn_id']] * 2
    assert [rec['generation'] for rec in out['records'][:2]] == [1, 1]
    assert out['records'][3]['turn_id'] == r2['turn_id']
    assert out['records'][3]['generation'] == 2
    assert out['records'][2]['data'] == {'event': 'turn_terminal',
                                         'status': 'completed', 'exit_code': None}
    only_turn_start(h.rpc)
    print('ok two completed turns on one connection with exact correlations', flush=True)

    # 3. Idempotent owner replay makes no extra rpc call.
    replay = h.session.submit_next_turn(
        session_id=h.sid, generation=3, request_id='turn-two',
        text='second turn input')
    assert replay['state'] == 'accepted' and replay['turn_id'] == r2['turn_id']
    assert len(h.rpc.calls) == 2
    print('ok idempotent owner replay makes no extra rpc call', flush=True)

    # 4. Refused authority/ownership, changed request and active pending: zero calls.
    h2 = Harness(base)
    h2.session.authority = lambda facts: {'role': 'worker', 'authorized': True}
    assert 'authority' in refuses(h2.submit, 'auth-refused')
    h2.session.authority = authority_ok
    h2.session.ownership = lambda facts: False
    assert 'ownership' in refuses(h2.submit, 'own-refused')
    h2.session.ownership = ownership_ok
    assert h2.rpc.calls == []
    h2.rpc.behavior = ('reply', ack('prov-p'))
    r = h2.submit('pending-one', 'pending turn input')
    assert r['state'] == 'accepted'
    assert len(h2.rpc.calls) == 1
    assert 'not open' in refuses(h2.submit, 'while-active')
    assert 'changed content' in refuses(
        h2.session.submit_next_turn, session_id=h2.sid, generation=1,
        request_id='pending-one', text='different text')
    assert len(h2.rpc.calls) == 1
    print('ok refused authority/ownership, changed request and active pending make zero calls', flush=True)

    # 5. Unbound early activity contradicts rejection without proving binding.
    rejection_cases = (
        ('none', [], False, False),
        ('foreign', [started('other-thread', 'new')], False, False),
        ('early-start', [started(THREAD, 'new')], True, False),
        ('early-output', [agent_delta(THREAD, 'new', 'x')], True, False),
        ('oversized', [agent_delta(THREAD, 'new', 'x' * (br.DELTA_BOUND + 1))], True, True),
        ('overflow-empty', [agent_delta(THREAD, 'new', 'x' * 1025)], True, True),
        ('overflow', [started(THREAD, 'new')] * 3, True, True),
    )
    for name, events, activity, gap in rejection_cases:
        h3 = Harness(base, buffer_events=1, buffer_bytes=1024)
        h3.rpc.before = events
        h3.rpc.behavior = ('reject', None)
        result = h3.submit('rejected-one')
        expected = 'uncertain' if activity else 'rejected'
        assert result['state'] == expected, name
        send = h3.bridge.status()['last_send']
        assert send['status'] == expected and send['gap'] == gap, name
        assert send['unbound_activity'] == activity, name
        assert h3.bridge.status()['gap'] == gap, name
        assert h3.bridge.status()['buffered_events'] == 0, name
        assert h3.bridge.status()['turn_mappings'] == 0, name
        assert h3.view()['state'] == ('outcome_unknown' if activity else 'idle'), name
        assert h3.output()['records'] == [], name
        assert h3.submit('rejected-one')['state'] == expected, name
        assert len(h3.rpc.calls) == 1, name
        if activity:
            assert 'not open' in refuses(h3.submit, 'blocked-new')
            assert h3.notify(completed(THREAD, 'new'))['action'] == 'ignored'
            assert h3.view()['generation'] == 1
        else:
            h3.rpc.behavior = ('reply', ack('after-rejection'))
            assert h3.submit('after-rejection')['state'] == 'accepted'
            assert len(h3.rpc.calls) == 2
        only_turn_start(h3.rpc)
    print('ok typed rejection preserves early uncertainty and empty-buffer gap evidence', flush=True)

    # 6. Timeout/lost/malformed/wrong-thread acknowledgements stay uncertain.
    bad_acks = (
        ('lost call', ('raise', OSError('provider RPC timeout'))),
        ('crashed connection', ('raise', BrokenPipeError('connection lost'))),
        ('missing turn', ('reply', None)),
        ('empty reply', ('reply', {})),
        ('turn not an object', ('reply', {'turn': None})),
        ('turn without id', ('reply', {'turn': {}})),
        ('empty turn id', ('reply', {'turn': {'id': ''}})),
        ('non-string turn id', ('reply', {'turn': {'id': 5}})),
        ('unbounded turn id', ('reply', {'turn': {'id': 'x' * 129}})),
        ('wrong thread ack', ('reply', {'threadId': 'thread-other',
                                         'turn': {'id': 'prov-w'}})),
    )
    for name, behavior in bad_acks:
        h4 = Harness(base)
        h4.rpc.behavior = behavior
        result = h4.submit('uncertain-one')
        assert result['state'] == 'uncertain', name
        assert len(h4.rpc.calls) == 1, name
        assert h4.bridge.status()['turn_mappings'] == 0, name
        assert h4.view()['state'] == 'outcome_unknown', name
        assert h4.view()['turn']['delivery'] == 'unknown', name
        # Replaying the identical request never resends; new ids refuse.
        assert h4.submit('uncertain-one')['state'] == 'uncertain'
        assert 'not open' in refuses(h4.submit, 'while-uncertain')
        assert len(h4.rpc.calls) == 1, name
        # Events for any provider turn stay unattributable.
        res = h4.notify(agent_delta(THREAD, 'prov-anything', 'late\n'))
        assert res['action'] == 'ignored' and 'unbound' in res['reason'], name
        assert h4.output()['records'] == [], name
    print('ok timeout/lost/malformed/wrong-thread acknowledgements stay uncertain', flush=True)

    # 7. Early matching and foreign events around the synchronous rpc call.
    h5 = Harness(base)
    h5.rpc.before = [started(THREAD, 'prov-e'),
                     agent_delta(THREAD, 'prov-e', 'early matching text\n'),
                     agent_delta(THREAD, 'prov-e2', 'foreign same-thread turn\n'),
                     agent_delta('thread-other', 'prov-e', 'foreign thread\n')]
    h5.rpc.behavior = ('reply', ack('prov-e'))
    r = h5.submit('early-one')
    assert r['state'] == 'accepted'
    send = h5.bridge.status()['last_send']
    assert send['status'] == 'accepted' and send['provider_turn_id'] == 'prov-e'
    assert send['replayed_events'] == 2 and send['foreign_events'] == 1
    assert send['dropped_events'] == 0 and send['gap'] is False
    assert h5.view()['state'] == 'running'
    out = h5.output()
    assert [rec['kind'] for rec in out['records']] == ['agent_message']
    assert out['records'][0]['data'] == {'delta': 'early matching text\n'}
    assert out['records'][0]['turn_id'] == r['turn_id']
    # The foreign same-thread turn id was never adopted.
    assert 'prov-e2' not in h5.bridge._local
    h5.notify(completed(THREAD, 'prov-e'))
    assert h5.view()['state'] == 'terminal'
    print('ok early matching events replay in order; foreign events never adopted', flush=True)

    # 8. Wrong, stale and duplicate turns cannot terminate another turn.
    h6 = Harness(base)
    h6.rpc.behavior = ('reply', ack('prov-s1'))
    r1 = h6.submit('stale-one')
    h6.notify(completed(THREAD, 'prov-s1'))
    assert h6.view()['generation'] == 2
    h6.rpc.behavior = ('reply', ack('prov-s2'))
    r2 = h6.submit('stale-two')
    assert h6.view()['state'] == 'running'
    before = h6.output()
    # Duplicate terminal for the already completed turn is refused, not fatal.
    dup = h6.notify(completed(THREAD, 'prov-s1'))
    assert dup['action'] == 'refused' and 'mismatched terminal' in dup['reason']
    assert h6.view()['state'] == 'running' and h6.view()['generation'] == 2
    # Unknown provider turn and unsupported terminal status are ignored.
    assert h6.notify(agent_delta(THREAD, 'prov-unknown', 'x'))['action'] == 'ignored'
    assert h6.notify(completed(THREAD, 'prov-s2', 'inProgress'))['action'] == 'ignored'
    assert h6.notify({'method': 'thread/closed',
                      'params': {'threadId': THREAD}})['action'] == 'ignored'
    assert h6.notify({'method': 'turn/completed',
                      'params': {'threadId': THREAD}})['action'] == 'ignored'
    assert h6.notify('not-a-message')['action'] == 'ignored'
    assert h6.view()['state'] == 'running'
    assert h6.output()['records'] == before['records']
    # The active turn still completes exactly once.
    assert h6.notify(completed(THREAD, 'prov-s2'))['action'] == 'observed'
    view = h6.view()
    assert view['state'] == 'terminal' and view['generation'] == 3
    assert view['last_turn']['turn_id'] == r2['turn_id']
    assert view['history'][0]['turn_id'] == r1['turn_id']
    print('ok wrong, stale and duplicate turns cannot terminate another turn', flush=True)

    # Reused identities never overwrite; capacity never evicts old evidence.
    for count in (1, br.MAX_MAPPINGS):
        reuse = Harness(base)
        for index in range(count):
            provider = 'remember-%d' % index
            reuse.rpc.behavior = ('reply', ack(provider))
            assert reuse.submit('remember-%d' % index)['state'] == 'accepted'
            reuse.notify(completed(THREAD, provider))
        original = dict(reuse.bridge._local['remember-0'])
        reuse.rpc.behavior = ('reply', ack('remember-0'))
        # Known stale activity cannot masquerade as a new unbound turn.
        reuse.rpc.before = [started(THREAD, 'remember-0'),
                            completed(THREAD, 'remember-0')]
        uncertain = reuse.submit('reuse')
        assert uncertain['state'] == 'uncertain'
        assert reuse.bridge._local['remember-0'] == original
        assert reuse.bridge.status()['turn_mappings'] == count
        assert len(reuse.rpc.calls) == count + (count < br.MAX_MAPPINGS)
        assert reuse.view()['state'] == 'outcome_unknown'
        assert reuse.view()['generation'] == count + 1
        before = reuse.output()['records']
        reuse.notify(completed(THREAD, 'remember-0'))
        assert reuse.view()['state'] == 'outcome_unknown'
        assert reuse.view()['generation'] == count + 1
        assert reuse.output()['records'] == before
        assert reuse.submit('reuse')['state'] == 'uncertain'
        assert 'not open' in refuses(reuse.submit, 'reuse-new')
        assert len(reuse.rpc.calls) == count + (count < br.MAX_MAPPINGS)
        assert 'handoff required' in reuse.bridge.status()['last_send']['reason']
        only_turn_start(reuse.rpc)
    # Old known identities alone do not contradict an explicit rejection.
    stale = Harness(base)
    stale.rpc.behavior = ('reply', ack('old'))
    stale.submit('old')
    stale.notify(completed(THREAD, 'old'))
    stale.rpc.before = [started(THREAD, 'old'), completed(THREAD, 'old')]
    stale.rpc.behavior = ('reject', None)
    assert stale.submit('stale-rejected')['state'] == 'rejected'
    assert stale.view()['state'] == 'idle' and stale.view()['generation'] == 2
    assert stale.bridge.status()['unbound_activity'] is False
    only_turn_start(stale.rpc)
    print('ok reused identity stays ambiguous; four mappings require handoff without extra RPC', flush=True)

    # 9. Output bound: oversized delta refuses, marks an explicit gap.
    h7 = Harness(base)
    h7.rpc.behavior = ('reply', ack('prov-b1'))
    r = h7.submit('bound-one')
    big = h7.notify(agent_delta(THREAD, 'prov-b1', 'x' * (br.DELTA_BOUND + 1)))
    assert big['action'] == 'refused' and 'delta bound' in big['reason']
    assert big['gap'] is True
    assert h7.bridge.status()['gap'] is True
    assert h7.bridge.status()['gap_recorded'] is True
    assert h7.notify(agent_delta(THREAD, 'prov-b1', 'kept text\n'))['action'] == 'observed'
    out = h7.output()
    assert [rec['kind'] for rec in out['records']] == ['lifecycle', 'agent_message']
    assert out['records'][0]['data']['event'] == br.GAP_EVENT
    assert 'incomplete' in out['records'][0]['data']['detail']
    assert out['records'][1]['data'] == {'delta': 'kept text\n'}
    h7.notify(completed(THREAD, 'prov-b1'))
    print('ok oversized delta refuses with an explicit recorded gap', flush=True)

    # 10. Early-buffer overflow preserves a gap instead of complete output.
    h8 = Harness(base, buffer_events=4, buffer_bytes=1024)
    h8.rpc.before = [agent_delta(THREAD, 'prov-o', 'chunk-%d\n' % i)
                     for i in range(1, 7)]
    h8.rpc.behavior = ('reply', ack('prov-o'))
    r = h8.submit('overflow-one')
    assert r['state'] == 'accepted'
    send = h8.bridge.status()['last_send']
    assert send['replayed_events'] == 4 and send['dropped_events'] == 2
    assert send['gap'] is True and send['gap_recorded'] is True
    out = h8.output()
    kinds = [rec['kind'] for rec in out['records']]
    assert kinds == ['lifecycle'] + ['agent_message'] * 4, kinds
    assert out['records'][0]['data']['event'] == br.GAP_EVENT
    deltas = [rec['data']['delta'] for rec in out['records'][1:]]
    assert deltas == ['chunk-%d\n' % i for i in range(1, 5)], deltas
    assert h8.bridge.status()['gap'] is True
    h8.notify(completed(THREAD, 'prov-o'))
    print('ok early-buffer overflow preserves an explicit gap with ordered partial replay', flush=True)

    # 11. Failed and interrupted terminal facts carry exit_code=None.
    h9 = Harness(base)
    h9.rpc.behavior = ('reply', ack('prov-f'))
    h9.submit('fail-one')
    h9.notify(completed(THREAD, 'prov-f', 'failed'))
    view = h9.view()
    assert view['last_turn']['status'] == 'failed'
    assert view['last_turn']['exit_code'] is None
    assert view['turns_failed'] == 1 and view['turns_completed'] == 0
    h9.rpc.behavior = ('reply', ack('prov-i'))
    h9.submit('interrupt-one')
    h9.notify(completed(THREAD, 'prov-i', 'interrupted'))
    view = h9.view()
    assert view['last_turn']['status'] == 'interrupted'
    assert view['last_turn']['exit_code'] is None
    assert view['turns_failed'] == 2
    out = h9.output()
    assert out['records'][-1]['data'] == {'event': 'turn_terminal',
                                          'status': 'interrupted', 'exit_code': None}
    print('ok failed/interrupted terminal facts map to turn facts with exit_code None', flush=True)

    # 12. Unknown mapping after reopen: no recovery, no resend, no adoption.
    h10 = Harness(base)
    h10.rpc.behavior = ('raise', OSError('owner connection lost'))
    lost = h10.submit('lost-one')
    assert lost['state'] == 'uncertain'
    rpc2, bridge2, session2 = h10.open()
    assert session2.status(session_id=h10.sid)['state'] == 'outcome_unknown'
    assert rpc2.calls == []
    # Even the real provider turn id, if it surfaces, stays unattributable.
    for msg in (started(THREAD, 'prov-real'), agent_delta(THREAD, 'prov-real', 'x'),
                completed(THREAD, 'prov-real')):
        res = bridge2.handle_notification(msg)
        assert res['action'] == 'ignored' and 'unbound' in res['reason']
    assert rpc2.calls == []
    assert session2.status(session_id=h10.sid)['state'] == 'outcome_unknown'
    again = session2.submit_next_turn(session_id=h10.sid, generation=1,
                                      request_id='lost-one',
                                      text='next turn input')
    assert again['state'] == 'uncertain' and rpc2.calls == []
    assert 'not open' in refuses(session2.submit_next_turn,
                                 session_id=h10.sid, generation=1,
                                 request_id='lost-two', text='new work')
    assert rpc2.calls == []
    print('ok unknown mapping after reopen: no recovery, resend or first-id adoption', flush=True)

    # 13. Core output-write errors stay controlled and never fake process exit.
    h11 = Harness(base)
    h11.rpc.behavior = ('reply', ack('prov-j'))
    r = h11.submit('journal-one')
    journal = h11.root / 'coord' / 'sessions' / (h11.sid + '.jsonl')
    os.chmod(journal, 0o400)
    try:
        lost = h11.notify(agent_delta(THREAD, 'prov-j', 'lost delta\n'))
        assert lost['action'] == 'refused'
        assert h11.view()['state'] == 'running'
        # A saved terminal fact plus a journal-write error is retained
        # verbatim and is never proof of process exit or clean completion.
        saved = h11.notify(completed(THREAD, 'prov-j'))
        assert saved['action'] == 'refused', saved
        assert 'terminal saved' in saved['reason'], saved
        assert 'journal_write_failed' in saved['reason'], saved
        view = h11.view()
        assert view['state'] == 'terminal' and view['generation'] == 2
        assert view['last_turn']['status'] == 'completed'
        assert view['last_turn']['exit_code'] is None
        assert view['journal_error'] == 'journal_write_failed'
        assert h11.bridge.status()['turn_mappings'] == 1
    finally:
        os.chmod(journal, 0o600)
    print('ok core output-write errors stay controlled; saved terminal fact never fakes process exit', flush=True)

    # 14. No thread/process start, resume, fork or adopt anywhere above.
    for harness in (h, h2, h3, h5, h6, h7, h8, h9, h10, h11):
        only_turn_start(harness.rpc)
    print('ok every owned rpc call is exactly one turn/start; no thread lifecycle rpc', flush=True)

    # 15. Identity and attribution invariants (see IDENTITY_CASES).
    for case in IDENTITY_CASES:
        case(base)


def records_for(out, turn_id):
    return [rec for rec in out['records'] if rec.get('turn_id') == turn_id]


def completed_turns(base, count):
    h = Harness(base)
    turns = []
    for index in range(count):
        provider = 'old-%d' % index
        h.rpc.behavior = ('reply', ack(provider))
        turns.append(h.submit('old-%d' % index)['turn_id'])
        assert h.notify(completed(THREAD, provider))['action'] == 'observed'
    return h, turns


def case_reused_ack_quarantine(base):
    """Reused ack: no delta reaches the old turn before, during or after."""
    for reused in (1, 0):  # non-oldest (last) and oldest mapping
        for delta in (agent_delta, command_delta):
            h, turns = completed_turns(base, 2)
            reused_id = 'old-%d' % reused
            other_id = 'old-%d' % (1 - reused)
            original = dict(h.bridge._local[reused_id])
            before = h.output()['records']
            h.rpc.before = [delta(THREAD, reused_id, 'during rpc\n'),
                            started(THREAD, reused_id),
                            completed(THREAD, reused_id)]
            h.rpc.behavior = ('reply', ack(reused_id))
            result = h.submit('reuse')
            assert result['state'] == 'uncertain'
            assert len(h.rpc.calls) == 3
            # Behavior first: no reused-id delta reached any journal turn.
            mid = h.output()['records'][len(before):]
            assert not any('delta' in rec['data'] for rec in mid), mid
            send = h.bridge.status()['last_send']
            assert send['quarantined_events'] == 3, send
            assert 'reused' in send['reason'] and 'handoff' in send['reason']
            assert h.bridge._local[reused_id] == original
            assert reused_id not in h.bridge._provider.values() or \
                h.bridge._provider[original['turn_id']] == reused_id
            assert result['turn_id'] not in h.bridge._provider
            # Late output and stale lifecycle after detection stay quarantined.
            for msg in (delta(THREAD, reused_id, 'after ack\n'),
                        started(THREAD, reused_id), completed(THREAD, reused_id)):
                assert h.notify(msg)['action'] == 'quarantined'
            view = h.view()
            assert view['state'] == 'outcome_unknown' and view['generation'] == 3
            out = h.output()['records']
            added = out[len(before):]
            assert out[:len(before)] == before, 'historical bytes changed'
            assert not any('delta' in rec['data'] for rec in added)
            status = h.bridge.status()
            if reused == 1:
                # The last turn accepts the explicit ambiguity marker.
                assert [rec['data']['event'] for rec in added] == [br.AMBIGUOUS_EVENT], added
                assert added[0]['turn_id'] == turns[reused]
                assert added[0]['generation'] == reused + 1
                assert status['unrecorded_markers'] == 0
            else:
                # The frozen core takes output only for its active/last turn:
                # the marker cannot be written, and that stays explicit.
                assert added == [], added
                assert status['unrecorded_markers'] == 1
            assert records_for(h.output(), result['turn_id']) == []
            status = h.bridge.status()
            assert status['quarantined_ids'] == 1 and status['quarantined_events'] == 6
            assert status['turn_mappings'] == 2
            # A proved distinct old id still targets its own old turn (the
            # core accepts it only for its last turn) and never the new one.
            res = h.notify(delta(THREAD, other_id, 'legit late old\n'))
            if reused == 0:
                assert res['action'] == 'observed', res
                last = h.output()['records'][-1]
                assert last['turn_id'] == turns[1]
                assert last['data'] == {'delta': 'legit late old\n'}
            else:
                assert res['action'] == 'refused' and 'mismatched' in res['reason'], res
            assert records_for(h.output(), result['turn_id']) == []
            assert h.submit('reuse')['state'] == 'uncertain'
            assert len(h.rpc.calls) == 3
    print('ok reused ack quarantines oldest/non-oldest ids before, during and after ack', flush=True)


def case_held_old_output(base):
    """Old-id output during the rpc is written only once attribution is proved."""
    # Fresh distinct ack proves the old id: delivered to the old turn, in order.
    h, turns = completed_turns(base, 1)
    h.rpc.before = [command_delta(THREAD, 'old-0', 'late old\n'),
                    agent_delta(THREAD, 'fresh', 'new text\n')]
    h.rpc.behavior = ('reply', ack('fresh'))
    r = h.submit('fresh')
    assert r['state'] == 'accepted'
    send = h.bridge.status()['last_send']
    assert send['replayed_events'] == 2 and send['quarantined_events'] == 0, send
    tail = h.output()['records'][-2:]
    assert (tail[0]['turn_id'], tail[0]['generation']) == (turns[0], 1)
    assert tail[0]['data'] == {'delta': 'late old\n'}
    assert (tail[1]['turn_id'], tail[1]['generation']) == (r['turn_id'], 2)
    # Activity-free typed rejection proves no new turn exists.
    h, turns = completed_turns(base, 1)
    h.rpc.before = [agent_delta(THREAD, 'old-0', 'late old\n')]
    h.rpc.behavior = ('reject', None)
    assert h.submit('rejected')['state'] == 'rejected'
    assert h.output()['records'][-1]['data'] == {'delta': 'late old\n'}
    assert h.output()['records'][-1]['turn_id'] == turns[0]
    assert h.bridge.status()['quarantined_ids'] == 0
    # Unresolved outcomes prove nothing: every mapped id is quarantined.
    for behavior, events in ((('raise', OSError('lost')), []),
                             (('reply', {'turn': {}}), []),
                             (('reject', None), [started(THREAD, 'unknown-new')])):
        h, turns = completed_turns(base, 2)
        before = h.output()['records']
        h.rpc.before = [agent_delta(THREAD, 'old-1', 'ambiguous\n')] + events
        h.rpc.behavior = behavior
        assert h.submit('unresolved')['state'] == 'uncertain'
        added = h.output()['records'][len(before):]
        assert [rec['data'] for rec in added if 'delta' in rec['data']] == [], added
        assert [(rec['turn_id'], rec['data']['event']) for rec in added] == [
            (turns[1], br.AMBIGUOUS_EVENT)], added
        assert h.bridge.status()['unrecorded_markers'] == 1  # older than last_turn
        assert h.notify(agent_delta(THREAD, 'old-0', 'x'))['action'] == 'quarantined'
        assert h.bridge.status()['quarantined_ids'] == 2
        assert h.view()['state'] == 'outcome_unknown'
    print('ok old-id output during rpc is held until attribution is proved', flush=True)


def case_per_turn_gap(base):
    """An old turn's gap marker never stands in for the current turn's gap."""
    for timing in ('during-rpc', 'before-send', 'after-ack'):
        h, turns = completed_turns(base, 1)
        h.bridge._buffer_events_bound = 2
        big = agent_delta(THREAD, 'old-0', 'x' * (br.DELTA_BOUND + 1))
        if timing == 'before-send':
            assert h.notify(big)['action'] == 'refused'
        h.rpc.before = ([big] if timing == 'during-rpc' else []) + [
            agent_delta(THREAD, 'new', 'chunk-%d\n' % i) for i in range(4)]
        h.rpc.behavior = ('reply', ack('new'))
        r = h.submit('new')
        if timing == 'after-ack':
            assert h.notify(big)['action'] == 'refused'
        send = h.bridge.status()['last_send']
        assert send['gap'] is True and send['gap_recorded'] is True, (timing, send)
        out = h.output()
        old_gaps = [rec for rec in records_for(out, turns[0])
                    if rec['data'].get('event') == br.GAP_EVENT]
        new_gaps = [rec for rec in records_for(out, r['turn_id'])
                    if rec['data'].get('event') == br.GAP_EVENT]
        assert len(old_gaps) == 1 and len(new_gaps) == 1, (timing, out['records'])
        assert 'overflow' in new_gaps[0]['data']['detail']
        assert h.bridge.status()['gap_recorded'] is True
        # A second oversized old delta adds no marker and no current-turn gap.
        h.notify(big)
        assert len(h.output()['records']) == len(out['records'])
        assert h.bridge.status()['gap_turns_recorded'] == 2
    # An old gap alone never claims the current turn had one.
    h, turns = completed_turns(base, 1)
    h.notify(agent_delta(THREAD, 'old-0', 'x' * (br.DELTA_BOUND + 1)))
    h.rpc.behavior = ('reply', ack('clean'))
    h.submit('clean')
    send = h.bridge.status()['last_send']
    assert send['gap'] is False and send['gap_recorded'] is False, send
    assert h.bridge.status()['gap_recorded'] is False
    print('ok gap markers are per local turn; old gaps never prove the current gap', flush=True)


def case_fresh_bridge_rebind(base):
    """A fresh bridge cannot continue a session whose provider ids it never saw."""
    h, turns = completed_turns(base, 1)
    before = h.view()
    records = h.output()['records']
    rpc = FakeRPC()
    bridge = br.CodexLeadTransport(rpc, THREAD, model=MODEL, effort=EFFORT)
    session = ml.LeadSession(h.root, h.sid, transport=bridge,
                             authority=authority_ok, ownership=ownership_ok)
    rpc.bridge = bridge
    assert 'handoff' in refuses(bridge.bind, session)
    assert bridge.status()['bound'] is False
    # Continuing through the core reaches the unbound bridge: refused, no RPC,
    # and the old id cannot terminate anything.
    rpc.behavior = ('reply', ack('old-0'))
    result = session.submit_next_turn(session_id=h.sid, generation=2,
                                      request_id='after-reopen', text='x')
    assert result['state'] == 'uncertain' and rpc.calls == []
    assert bridge.handle_notification(completed(THREAD, 'old-0'))['action'] == 'ignored'
    view = session.status(session_id=h.sid)
    assert view['state'] == 'outcome_unknown' and view['generation'] == 2
    assert view['history'] == before['history']
    assert session.read_output(session_id=h.sid)['records'] == records
    # Pending/uncertain sessions remain bindable for inspection only.
    h2 = Harness(base)
    h2.rpc.behavior = ('raise', OSError('lost'))
    h2.submit('lost')
    rpc2, bridge2, session2 = h2.open()
    assert bridge2.status()['inherited_history'] is True
    assert 'inspection only' in refuses(bridge2.send_turn, {
        'session_id': h2.sid, 'generation': 1, 'turn_id': 'turn-z', 'text': 'x'})
    assert rpc2.calls == []
    print('ok fresh bridge refuses unsafe continuation before any effect', flush=True)


IDENTITY_CASES = (case_reused_ack_quarantine, case_held_old_output,
                  case_per_turn_gap, case_fresh_bridge_rebind)


def negative_control(base, bridge_path):
    """Each identity case must fail against an unfixed bridge source."""
    global br
    fixed = br
    spec = importlib.util.spec_from_file_location('control_bridge', bridge_path)
    br = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(br)
    if not hasattr(br, 'AMBIGUOUS_EVENT'):
        br.AMBIGUOUS_EVENT = fixed.AMBIGUOUS_EVENT
    try:
        for case in IDENTITY_CASES:
            try:
                case(base)
            except (AssertionError, ml.Refusal, br.Refusal) as exc:
                print('ok negative control %s fails: %s: %s'
                      % (case.__name__, type(exc).__name__, str(exc)[:80]), flush=True)
            else:
                raise AssertionError('negative control passed: ' + case.__name__)
    finally:
        br = fixed


def main():
    base = Path(tempfile.mkdtemp(prefix='unio-managed-lead-codex-'))
    os.chmod(base, 0o700)
    try:
        if len(sys.argv) == 3 and sys.argv[1] == '--negative-control':
            negative_control(base, sys.argv[2])
            print('all negative controls failed as expected')
            return
        run_suite(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print('all managed lead codex bridge checks passed')


if __name__ == '__main__':
    main()
