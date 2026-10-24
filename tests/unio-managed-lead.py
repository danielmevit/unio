#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Managed lead-session core test suite: fake transport, no provider calls.

Every check calls tools/managed-lead.py directly through importlib so old
embedded installer bytes cannot make these tests pass accidentally.
"""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

SOURCE = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    'managed_lead', SOURCE / 'tools' / 'managed-lead.py')
ml = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ml)


class FakeTransport:
    """Deterministic fake owned transport; counts every call."""

    def __init__(self):
        self.calls = []
        self.mode = 'accepted'

    def send_turn(self, facts):
        self.calls.append(dict(facts))
        if self.mode == 'raise':
            raise OSError('transport crashed ambiguously')
        if self.mode == 'sysexit':
            raise SystemExit('host crash mid-submission')
        if self.mode == 'invalid':
            return {'unexpected': True}
        if self.mode == 'rejected':
            return {'status': 'rejected'}
        return {'status': 'accepted'}


def authority_ok(facts):
    return {'role': 'lead', 'authorized': True}


def ownership_ok(facts):
    return True


class Harness:
    counter = 0

    def __init__(self, base, authority=authority_ok, ownership=ownership_ok,
                 **create):
        Harness.counter += 1
        self.base = Path(base)
        self.root = self.base / ('project-' + str(Harness.counter))
        self.transport = FakeTransport()
        self.authority = authority
        self.ownership = ownership
        self.session = ml.create_lead_session(
            self.root, transport=self.transport, authority=authority,
            ownership=ownership, workspace='/private/lead-ws',
            budget_label='mistral-shared', route='codex-app-server',
            model='test-sol', effort='xhigh', **create)
        self.sid = self.session.session_id

    def open(self):
        """Open a second controller instance on the same recorded session."""
        return ml.LeadSession(self.root, self.sid, transport=self.transport,
                              authority=self.authority, ownership=self.ownership)

    def submit(self, request_id, text='next turn input', generation=None):
        gen = self.session.status(session_id=self.sid)['generation'] if generation is None else generation
        return self.session.submit_next_turn(
            session_id=self.sid, generation=gen, request_id=request_id, text=text)

    def finish(self, result, status='completed', exit_code=0):
        self.session.observe_terminal(
            session_id=self.sid, generation=result['generation'],
            turn_id=result['turn_id'], status=status, exit_code=exit_code)


def refuses(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except ml.Refusal as exc:
        return str(exc)
    raise AssertionError('expected Refusal')


def run_suite(base):
    # 0. Module surface: importable backend only, no provider launch surface.
    assert not any(hasattr(ml, name) for name in ('subprocess', 'socket', 'pty'))
    print('ok module exposes no process/network launch surface', flush=True)

    # 1. Creation and read-only status: opaque lead identity, zero transport calls.
    h = Harness(base)
    assert ml.SESSION_ID.fullmatch(h.sid) and h.sid.startswith('lead-')
    view = h.session.status(session_id=h.sid)
    assert view['role'] == 'lead' and view['state'] == 'idle'
    assert view['generation'] == 1 and view['effective'] == 'Unknown'
    assert view['workspace'] == '/private/lead-ws'
    assert view['budget_label'] == 'mistral-shared'
    assert view['route'] == 'codex-app-server' and view['model'] == 'test-sol'
    assert view['requested_effort'] == 'xhigh'
    assert 'caution' in view and 'not proof of task delivery' in view['caution']
    assert h.transport.calls == []
    empty = h.session.read_output(session_id=h.sid)
    assert empty['records'] == [] and empty['gap'] is False and empty['output_cursor'] == 0
    assert h.transport.calls == []
    meta = h.root / 'coord/sessions' / (h.sid + '.json')
    assert stat.S_IMODE(os.stat(meta).st_mode) == 0o600
    print('ok creation, opaque lead identity, read-only status with zero transport calls', flush=True)

    # 2. Input validation refusals happen before any transport call.
    for bad_id in ('', '../x', 'a b', 'x' * 65):
        refuses(h.submit, bad_id)
    refuses(h.session.submit_next_turn, session_id=h.sid, generation=1,
            request_id='ok-id', text='')
    refuses(h.session.submit_next_turn, session_id=h.sid, generation=1,
            request_id='ok-id', text='nul\x00byte')
    refuses(h.session.submit_next_turn, session_id=h.sid, generation=1,
            request_id='ok-id', text='x' * 8193)
    refuses(h.session.submit_next_turn, session_id=h.sid, generation=1,
            request_id='ok-id', text='x' * 8192 + 'é')
    refuses(h.session.submit_next_turn, session_id='lead-' + '0' * 24,
            generation=1, request_id='ok-id', text='other session')
    refuses(h.session.submit_next_turn, session_id='../etc/passwd',
            generation=1, request_id='ok-id', text='traversal')
    assert h.transport.calls == []
    print('ok bounded input, label and session-binding refusals before transport', flush=True)

    # 3. Authority and ownership refusals happen before any transport call.
    for reply in ({'role': 'worker', 'authorized': True},
                  {'role': 'lead', 'authorized': False},
                  {'role': 'lead'}, None, {'authorized': True}):
        h.session.authority = lambda facts, r=reply: r
        assert 'authority' in refuses(h.submit, 'auth-test')
    def boom(facts):
        raise RuntimeError('authority backend down')
    h.session.authority = boom
    assert 'authority' in refuses(h.submit, 'auth-test')
    h.session.authority = authority_ok
    h.session.ownership = lambda facts: False
    assert 'ownership' in refuses(h.submit, 'own-test')
    def boom_own(facts):
        raise RuntimeError('ownership backend down')
    h.session.ownership = boom_own
    assert 'ownership' in refuses(h.submit, 'own-test')
    h.session.ownership = ownership_ok
    assert h.transport.calls == []
    print('ok worker-role, missing authority and missing ownership refuse before transport', flush=True)

    # 4. Multiple completed turns with lifecycle, output and generation advance.
    r1 = h.submit('turn-one', 'first turn input')
    assert r1['state'] == 'accepted' and r1['generation'] == 1
    assert h.session.status(session_id=h.sid)['state'] == 'running'
    h.session.observe_turn_started(session_id=h.sid, generation=1,
                                   turn_id=r1['turn_id'])
    h.session.observe_output(session_id=h.sid, generation=1, turn_id=r1['turn_id'],
                             kind='agent_message', data={'delta': 'useful lead text\n'})
    h.finish(r1, 'completed', 0)
    view = h.session.status(session_id=h.sid)
    assert view['state'] == 'terminal' and view['generation'] == 2
    assert view['turns_completed'] == 1 and view['last_turn']['status'] == 'completed'
    r2 = h.submit('turn-two', 'second turn input')
    assert r2['state'] == 'accepted' and r2['generation'] == 2
    h.finish(r2, 'failed', 7)
    view = h.session.status(session_id=h.sid)
    assert view['generation'] == 3 and view['turns_failed'] == 1
    assert view['last_turn']['exit_code'] == 7 and view['last_turn']['status'] == 'failed'
    assert len(view['history']) == 2
    out = h.session.read_output(session_id=h.sid)
    kinds = [rec['kind'] for rec in out['records']]
    assert kinds == ['agent_message', 'lifecycle', 'lifecycle'], kinds
    assert out['output_cursor'] == 3 and out['gap'] is False
    assert len(h.transport.calls) == 2
    assert all(set(call) == {'session_id', 'generation', 'turn_id', 'text'}
               for call in h.transport.calls)
    print('ok multiple completed turns, preserved failure, generation advance', flush=True)

    # 5. Duplicate request IDs: idempotent replay, changed content refuses.
    replay = h.session.submit_next_turn(session_id=h.sid, generation=3,
                                        request_id='turn-two', text='second turn input')
    assert replay['state'] == 'accepted' and replay['turn_id'] == r2['turn_id']
    assert len(h.transport.calls) == 2
    assert 'changed content' in refuses(h.session.submit_next_turn,
                                        session_id=h.sid, generation=3,
                                        request_id='turn-two', text='different text')
    assert len(h.transport.calls) == 2
    assert 'stale generation' in refuses(h.session.submit_next_turn,
                                         session_id=h.sid, generation=1,
                                         request_id='stale-gen', text='old epoch')
    assert len(h.transport.calls) == 2
    print('ok duplicate idempotency, changed-content and stale-generation refusals', flush=True)

    # 6. Concurrent submissions from two controller instances.
    r3 = h.submit('turn-three', 'third turn input')
    assert r3['state'] == 'accepted'
    other = h.open()
    assert other.status(session_id=h.sid)['state'] == 'running'
    assert 'not open for a next turn' in refuses(other.submit_next_turn,
                                                 session_id=h.sid, generation=3,
                                                 request_id='turn-three-b',
                                                 text='racing second turn')
    replayed = other.submit_next_turn(session_id=h.sid, generation=3,
                                      request_id='turn-three',
                                      text='third turn input')
    assert replayed['state'] == 'accepted' and replayed['turn_id'] == r3['turn_id']
    assert len(h.transport.calls) == 3
    h.finish(r3, 'completed', 0)
    assert other.status(session_id=h.sid)['generation'] == 4
    print('ok concurrent controller instances: one active turn, no duplicate transport', flush=True)

    # 7. Ambiguous send then reopen: outcome stays unknown, zero replay.
    h2 = Harness(base)
    h2.transport.mode = 'raise'
    ambiguous = h2.submit('ambiguous-one', 'ambiguous input')
    assert ambiguous['state'] == 'uncertain'
    assert h2.session.status(session_id=h2.sid)['state'] == 'outcome_unknown'
    reopened = h2.open()
    assert reopened.status(session_id=h2.sid)['state'] == 'outcome_unknown'
    again = reopened.submit_next_turn(session_id=h2.sid, generation=1,
                                      request_id='ambiguous-one',
                                      text='ambiguous input')
    assert again['state'] == 'uncertain'
    assert len(h2.transport.calls) == 1, 'ambiguous request was replayed'
    assert 'not open for a next turn' in refuses(reopened.submit_next_turn,
                                                 session_id=h2.sid, generation=1,
                                                 request_id='ambiguous-two',
                                                 text='new turn while uncertain')
    assert len(h2.transport.calls) == 1
    # Authorized matching reconciliation observation resolves the uncertainty.
    h2.transport.mode = 'accepted'
    reconciled = reopened.observe_terminal(session_id=h2.sid, generation=1,
                                            turn_id=ambiguous['turn_id'],
                                            status='unknown')
    assert reconciled['state'] == 'terminal' and reconciled['generation'] == 2
    after = reopened.submit_next_turn(session_id=h2.sid, generation=2,
                                      request_id='next-after-unknown',
                                      text='turn after reconciliation')
    assert after['state'] == 'accepted' and len(h2.transport.calls) == 2
    print('ok ambiguous send then reopen stays outcome_unknown with zero replay', flush=True)

    # 8. Crash between durable intent and recorded result: pending, zero replay.
    h3 = Harness(base)
    h3.transport.mode = 'sysexit'
    try:
        h3.submit('crash-one', 'crash mid-submission')
        raise AssertionError('SystemExit must propagate')
    except SystemExit:
        pass
    crashed = h3.open()
    view = crashed.status(session_id=h3.sid)
    assert view['state'] == 'pending' and view['turn']['delivery'] == 'unknown'
    h3.transport.mode = 'accepted'
    pending = crashed.submit_next_turn(session_id=h3.sid, generation=1,
                                      request_id='crash-one',
                                      text='crash mid-submission')
    assert pending['state'] == 'uncertain' and 'outcome unknown' in pending['note']
    assert len(h3.transport.calls) == 1, 'crashed request was replayed'
    assert 'not open for a next turn' in refuses(crashed.submit_next_turn,
                                                 session_id=h3.sid, generation=1,
                                                 request_id='crash-two',
                                                 text='new turn while pending')
    crashed.observe_turn_started(session_id=h3.sid, generation=1,
                                 turn_id=pending['turn_id'])
    assert crashed.status(session_id=h3.sid)['state'] == 'running'
    crashed.observe_terminal(session_id=h3.sid, generation=1,
                             turn_id=pending['turn_id'], status='completed')
    resumed = crashed.submit_next_turn(session_id=h3.sid, generation=2,
                                       request_id='after-crash',
                                       text='turn after crash recovery')
    assert resumed['state'] == 'accepted' and len(h3.transport.calls) == 2
    print('ok crash-pending reopen: explicit uncertainty until matching reconciliation', flush=True)

    # 9. Mismatched terminal and observation events refuse without effects.
    h4 = Harness(base)
    good = h4.submit('live-one', 'live turn')
    for kwargs in (
        {'session_id': h4.sid, 'generation': 1, 'turn_id': 'turn-' + '0' * 16,
         'status': 'completed'},
        {'session_id': h4.sid, 'generation': 2, 'turn_id': good['turn_id'],
         'status': 'completed'},
        {'session_id': h4.sid, 'generation': 1, 'turn_id': good['turn_id'],
         'status': 'bogus-status'},
        {'session_id': 'lead-' + '1' * 24, 'generation': 1,
         'turn_id': good['turn_id'], 'status': 'completed'},
    ):
        assert 'mismatch' in refuses(h4.session.observe_terminal, **kwargs) \
            or 'invalid terminal status' in refuses(h4.session.observe_terminal, **kwargs)
    assert h4.session.status(session_id=h4.sid)['state'] == 'running'
    assert 'mismatch' in refuses(h4.session.observe_turn_started,
                                 session_id=h4.sid, generation=2,
                                 turn_id=good['turn_id'])
    assert 'mismatch' in refuses(h4.session.observe_output, session_id=h4.sid,
                                 generation=1, turn_id='turn-' + '2' * 16,
                                 kind='agent_message', data={'delta': 'x'})
    assert 'mismatch' in refuses(h4.session.observe_owner, session_id=h4.sid,
                                 generation=5, owner='codex')
    h4.finish(good, 'completed', 0)
    assert 'mismatch' in refuses(h4.session.observe_terminal, session_id=h4.sid,
                                 generation=1, turn_id=good['turn_id'],
                                 status='completed')
    idle_view = h4.session.status(session_id=h4.sid)
    assert idle_view['state'] == 'terminal' and idle_view['generation'] == 2
    print('ok mismatched terminal/turn/owner/output observations refuse', flush=True)

    # 10. Bounded output: page limits, record bound, archive limit, explicit gaps.
    h5 = Harness(base)
    r = h5.submit('out-turn', 'output turn')
    for i in range(30):
        h5.session.observe_output(session_id=h5.sid, generation=1,
                                  turn_id=r['turn_id'], kind='agent_message',
                                  data={'delta': f'line {i}\n'})
    page = h5.session.read_output(session_id=h5.sid, limit=10)
    assert len(page['records']) == 10 and page['truncated'] is True
    assert page['next_cursor'] == 10 and page['gap'] is False
    rest = h5.session.read_output(session_id=h5.sid, after=page['next_cursor'],
                                  limit=500)
    assert len(rest['records']) == 20 and rest['truncated'] is False
    assert rest['output_cursor'] == 30
    assert 'invalid output bounds' in refuses(h5.session.read_output,
                                               session_id=h5.sid, limit=0)
    assert 'invalid output bounds' in refuses(h5.session.read_output,
                                              session_id=h5.sid, limit=501)
    assert 'output record bound exceeded' in refuses(
        h5.session.observe_output, session_id=h5.sid, generation=1,
        turn_id=r['turn_id'], kind='agent_message',
        data={'delta': 'x' * (ml.RECORD_BOUND)})
    assert 'invalid output delta' in refuses(
        h5.session.observe_output, session_id=h5.sid, generation=1,
        turn_id=r['turn_id'], kind='agent_message',
        data={'delta': 'x', 'envelope': {'secret': 'sk-live'}})
    assert 'unsupported output kind' in refuses(
        h5.session.observe_output, session_id=h5.sid, generation=1,
        turn_id=r['turn_id'], kind='provider_envelope', data={'raw': True})
    # Gap: a corrupt journal line stops reading with an explicit gap.
    journal = h5.root / 'coord/sessions' / (h5.sid + '.jsonl')
    with open(journal, 'ab') as f:
        f.write(b'corrupt-not-json\n')
    gapped = h5.session.read_output(session_id=h5.sid)
    assert gapped['gap'] is True and gapped['truncated'] is True
    assert gapped['output_cursor'] == 30 and len(gapped['records']) == 30
    # Out-of-order cursor tampering is also an explicit gap, never skipped.
    lines = journal.read_bytes().split(b'\n')
    good_line = lines[5]
    rec = json.loads(good_line)
    rec['cursor'] = 99
    lines[5] = json.dumps(rec).encode()
    journal.write_bytes(b'\n'.join(lines))
    tampered = h5.session.read_output(session_id=h5.sid)
    assert tampered['gap'] is True and tampered['records'][-1]['cursor'] == 5
    print('ok bounded output pages, record bound, envelope refusal, explicit gaps', flush=True)

    # 11. Archive limit: finite byte bound, marker, then closed archive.
    h6 = Harness(base)
    r = h6.submit('archive-turn', 'archive turn')
    limited = None
    for i in range(4000):
        limited = h6.session.observe_output(session_id=h6.sid, generation=1,
                                            turn_id=r['turn_id'],
                                            kind='agent_message',
                                            data={'delta': 'y' * 512})
        if limited.get('state') == 'archive_limit':
            break
    assert limited.get('state') == 'archive_limit', 'archive bound never reached'
    assert h6.session.status(session_id=h6.sid)['archive_limited'] is True
    assert 'output archive closed' in refuses(
        h6.session.observe_output, session_id=h6.sid, generation=1,
        turn_id=r['turn_id'], kind='agent_message', data={'delta': 'more'})
    closed = h6.session.read_output(session_id=h6.sid)
    assert closed['gap'] is True and closed['truncated'] is True
    final_page = h6.session.read_output(session_id=h6.sid,
                                        after=limited['cursor'] - 1, limit=500)
    assert final_page['records'][-1]['kind'] == 'archive_limit'
    assert final_page['output_cursor'] == limited['cursor']
    h6.finish(r, 'completed', 0)
    assert h6.session.status(session_id=h6.sid)['state'] == 'terminal'
    print('ok finite archive bound with marker and closed archive', flush=True)

    # 12. Malformed, unsafe and oversized state refuses instead of resetting.
    h7 = Harness(base)
    meta = h7.root / 'coord/sessions' / (h7.sid + '.json')
    doc = json.loads(meta.read_text())
    original = meta.read_bytes()
    meta.write_text('{not json')
    assert 'invalid session state' in refuses(h7.open)
    meta.write_bytes(original)
    doc['role'] = 'worker'
    meta.write_text(json.dumps(doc))
    assert 'invalid session state' in refuses(h7.open)
    doc['role'] = 'lead'
    doc['state'] = 'mystery'
    meta.write_text(json.dumps(doc))
    assert 'invalid session state' in refuses(h7.open)
    meta.write_bytes(original)
    with open(meta, 'ab') as f:
        f.write(b' ' * (ml.STATE_BOUND + 1))
    assert 'unsafe state file' in refuses(h7.open)
    meta.write_bytes(original)
    os.chmod(meta, 0o644)
    assert 'unsafe state file' in refuses(h7.open)
    os.chmod(meta, 0o600)
    assert h7.open().status(session_id=h7.sid)['state'] == 'idle'
    # Symlinked state file refuses.
    meta.unlink()
    os.symlink('/etc/passwd', meta)
    assert 'unsafe' in refuses(h7.open)
    meta.unlink()
    meta.write_bytes(original)
    os.chmod(meta, 0o600)
    # Symlinked journal refuses output observation.
    journal = h7.root / 'coord/sessions' / (h7.sid + '.jsonl')
    journal.unlink()
    os.symlink(str(meta), journal)
    live = h7.open()
    r = live.submit_next_turn(session_id=h7.sid, generation=1,
                              request_id='sym-turn', text='turn input')
    assert 'unsafe' in refuses(
        live.observe_output, session_id=h7.sid, generation=1,
        turn_id=r['turn_id'], kind='agent_message', data={'delta': 'x'})
    journal.unlink()
    journal.touch()
    os.chmod(journal, 0o600)
    live.observe_output(session_id=h7.sid, generation=1, turn_id=r['turn_id'],
                        kind='agent_message', data={'delta': 'recovered\n'})
    assert 'unknown lead session' in refuses(
        ml.LeadSession, h7.root, 'lead-' + 'f' * 24,
        transport=h7.transport, authority=authority_ok, ownership=ownership_ok)
    assert 'invalid session id' in refuses(
        ml.LeadSession, h7.root, '../../etc/passwd',
        transport=h7.transport, authority=authority_ok, ownership=ownership_ok)
    print('ok malformed, oversized, symlinked and loose-permission state refuses', flush=True)

    # 13. Request-history exhaustion refuses new IDs without evicting old ones.
    h8 = Harness(base, max_requests=2)
    first = h8.submit('req-1', 'first bounded request')
    h8.finish(first, 'completed', 0)
    second = h8.submit('req-2', 'second bounded request')
    h8.finish(second, 'completed', 0)
    assert 'request history exhausted' in refuses(h8.submit, 'req-3', 'third request')
    assert len(h8.transport.calls) == 2
    kept = h8.session.submit_next_turn(session_id=h8.sid, generation=3,
                                       request_id='req-1',
                                       text='first bounded request')
    assert kept['state'] == 'accepted' and kept['turn_id'] == first['turn_id']
    assert len(h8.transport.calls) == 2, 'exhausted history evicted or replayed an ID'
    assert h8.session.status(session_id=h8.sid)['requests_recorded'] == 2
    print('ok request-history exhaustion refuses without eviction or replay', flush=True)

    # 14. Rejected transport returns the session to idle without a provider turn.
    h9 = Harness(base)
    h9.transport.mode = 'rejected'
    rejected = h9.submit('rejected-one', 'rejected input')
    assert rejected['state'] == 'rejected'
    view = h9.session.status(session_id=h9.sid)
    assert view['state'] == 'idle' and view['turn'] is None
    assert view['history'][-1]['status'] == 'rejected'
    replayed = h9.session.submit_next_turn(session_id=h9.sid, generation=1,
                                           request_id='rejected-one',
                                           text='rejected input')
    assert replayed['state'] == 'rejected' and len(h9.transport.calls) == 1
    h9.transport.mode = 'invalid'
    invalid = h9.submit('invalid-one', 'invalid reply shape')
    assert invalid['state'] == 'uncertain'
    assert h9.session.status(session_id=h9.sid)['state'] == 'outcome_unknown'
    assert len(h9.transport.calls) == 2
    print('ok rejected and invalid transport outcomes recorded exactly once', flush=True)


def correction_regressions(base):
    h = Harness(base)
    r = h.submit('record')
    h.session.observe_output(session_id=h.sid, generation=1, turn_id=r['turn_id'],
                             kind='agent_message', data={'delta': 'text'})
    journal = h.session.journal_path
    original = journal.read_bytes()
    for corrupt in (b'', b'[]\n', b'null\n', b'1\n', b'"text"\n',
                    b'{}\n', b'\xff\n', original[:-1],
                    original + original):
        journal.write_bytes(corrupt)
        out = h.session.read_output(session_id=h.sid)
        assert out['gap'] and out['truncated'], corrupt
        before = journal.read_bytes()
        refuses(h.session.observe_output, session_id=h.sid, generation=1,
                turn_id=r['turn_id'], kind='agent_message', data={'delta': 'later'})
        assert journal.read_bytes() == before
    journal.write_bytes(original)
    assert len(h.transport.calls) == 1
    h = Harness(base)
    meta = h.session.meta_path
    original = meta.read_bytes()
    doc = json.loads(original)
    doc['session_id'] = 'lead-' + 'f' * 24
    meta.write_text(json.dumps(doc))
    refuses(h.open)
    assert not h.transport.calls
    meta.write_bytes(original)
    for kind in ('hardlink', 'symlink', 'fifo', 'loose'):
        target = base / ('target-' + kind)
        target.write_bytes(b'preserve me')
        os.chmod(target, 0o600)
        tmp = meta.parent / ('.' + meta.name + '.tmp')
        if kind == 'hardlink':
            os.link(target, tmp)
        elif kind == 'symlink':
            tmp.symlink_to(target)
        elif kind == 'fifo':
            os.mkfifo(tmp, 0o600)
        else:
            tmp.write_bytes(b'stale')
            os.chmod(tmp, 0o666)
        # A fresh exclusive private temporary name leaves stale paths untouched.
        result = h.submit('temp-' + kind)
        assert target.read_bytes() == b'preserve me'
        tmp.unlink()
        h.finish(result)
    for mutation in ('generation', 'request-generation', 'result-turn'):
        h2 = Harness(base)
        r2 = h2.submit('relationship')
        doc = json.loads(h2.session.meta_path.read_bytes())
        if mutation == 'generation':
            doc['generation'] += 1
        elif mutation == 'request-generation':
            doc['requests']['relationship']['generation'] += 1
        else:
            doc['requests']['relationship']['result']['turn_id'] = 'turn-' + 'f' * 16
        h2.session.meta_path.write_text(json.dumps(doc))
        refuses(h2.open)
        assert len(h2.transport.calls) == 1
    for operation in ('replace', 'fsync'):
        h2 = Harness(base)
        previous = getattr(ml.os, operation)
        def fail(*args):
            raise OSError('controlled persistence failure')
        setattr(ml.os, operation, fail)
        try:
            refuses(h2.submit, 'durable-failure')
        finally:
            setattr(ml.os, operation, previous)
        assert not h2.transport.calls
        assert h2.open().status(session_id=h2.sid)['state'] == 'idle'
        assert not list(h2.session.meta_path.parent.glob('.*.tmp'))
    h2 = Harness(base)
    fsync = ml.os.fsync
    sync_calls = []
    def fail_directory_sync(fd):
        sync_calls.append(fd)
        if len(sync_calls) == 2:
            raise OSError('controlled crash boundary after replacement')
        return fsync(fd)
    ml.os.fsync = fail_directory_sync
    try:
        refuses(h2.submit, 'replaced-intent')
    finally:
        ml.os.fsync = fsync
    assert not h2.transport.calls
    reopened = h2.open()
    assert reopened.status(session_id=h2.sid)['state'] == 'pending'
    replay = reopened.submit_next_turn(session_id=h2.sid, generation=1,
                                      request_id='replaced-intent', text='next turn input')
    assert replay['state'] == 'uncertain' and not h2.transport.calls
    for kind in ('fifo', 'hardlink', 'symlink', 'loose'):
        h2 = Harness(base)
        meta2 = h2.session.meta_path
        data2 = meta2.read_bytes()
        meta2.unlink()
        target = base / ('unsafe-state-' + kind)
        target.write_bytes(data2)
        os.chmod(target, 0o600)
        if kind == 'fifo':
            os.mkfifo(meta2, 0o600)
        elif kind == 'hardlink':
            os.link(target, meta2)
        elif kind == 'symlink':
            meta2.symlink_to(target)
        else:
            meta2.write_bytes(data2)
            os.chmod(meta2, 0o644)
        refuses(h2.submit, 'unsafe-state')
        assert not h2.transport.calls and target.read_bytes() == data2
    refuses(h.submit, 'unicode', '\ud800')
    print('ok correction regressions: journal integrity, identity, private temps, Unicode')


def medium_review_regressions(base):
    # Delete every persisted key, submitting directly (no Harness.status guard).
    for phase in ('idle', 'running', 'terminal'):
        h = Harness(base)
        if phase != 'idle':
            r = h.submit('required')
            if phase == 'terminal':
                h.finish(r, 'failed', 19)
        original = h.session.meta_path.read_bytes()
        doc = json.loads(original)
        calls = len(h.transport.calls)
        variants = []
        for key in doc:
            bad = json.loads(original)
            del bad[key]
            variants.append(bad)
        nested = [('requests', 'required')] if phase != 'idle' else []
        if phase == 'running':
            nested.append(('turn',))
        if phase == 'terminal':
            nested.extend([('last_turn',), ('history', 0)])
        if phase != 'idle':
            nested.append(('requests', 'required', 'result'))
        for path in nested:
            node = doc
            for part in path:
                node = node[part]
            for key in node:
                bad = json.loads(original)
                parent = bad
                for part in path:
                    parent = parent[part]
                del parent[key]
                variants.append(bad)
        for bad in variants:
            h.session.meta_path.write_text(json.dumps(bad))
            refuses(h.session.status, session_id=h.sid)
            refuses(h.session.submit_next_turn, session_id=h.sid,
                    generation=doc['generation'], request_id='direct', text='x')
            refuses(h.open)
            assert len(h.transport.calls) == calls
        h.session.meta_path.write_bytes(original)
        with h.session._guard():
            del h.session._state['last_turn']
            refuses(h.session._save)
        assert h.session.meta_path.read_bytes() == original
    print('ok every required state/nested key refuses directly; save validates candidate', flush=True)

    # Observations may arrive while send_turn is outside the lock.
    for observation in ('none', 'started', 'terminal', 'started-terminal'):
        for reply in ('accepted', 'uncertain', 'rejected'):
            h = Harness(base)
            def send(facts):
                h.transport.calls.append(dict(facts))
                args = {k: facts[k] for k in ('session_id', 'generation', 'turn_id')}
                if observation in ('started', 'started-terminal'):
                    h.session.observe_turn_started(**args)
                if observation in ('terminal', 'started-terminal'):
                    h.session.observe_terminal(**args, status='failed', exit_code=23)
                return {'status': reply}
            h.transport.send_turn = send
            r = h.submit('ordering')
            expected = 'uncertain' if reply == 'rejected' and observation != 'none' else reply
            assert r['state'] == expected, (observation, reply, r)
            reopened = h.open()
            view = reopened.status(session_id=h.sid)
            if 'terminal' in observation:
                assert view['state'] == 'terminal' and view['last_turn']['exit_code'] == 23
                assert view['turns_failed'] == 1 and view['generation'] == 2
            elif observation == 'started':
                assert view['state'] == 'running' and view['turn']['delivery'] == 'accepted'
            assert reopened.submit_next_turn(session_id=h.sid, generation=1,
                    request_id='ordering', text='next turn input') == r
            assert len(h.transport.calls) == 1
            if view['turn']:
                refuses(reopened.submit_next_turn, session_id=h.sid, generation=1,
                        request_id='blocked', text='x')
                # A later proven start must not turn uncertainty into a replay.
                reopened.observe_turn_started(session_id=h.sid, generation=1,
                                               turn_id=r['turn_id'])
                reopened.observe_terminal(session_id=h.sid, generation=1,
                    turn_id=r['turn_id'], status='failed', exit_code=-9)
                assert h.open().status(session_id=h.sid)['last_turn']['exit_code'] == -9
                assert reopened.submit_next_turn(session_id=h.sid, generation=2,
                        request_id='ordering', text='next turn input') == r
                assert len(h.transport.calls) == 1
    print('ok reply/start/terminal orderings preserve facts, uncertainty, reopen and idempotence', flush=True)

    for operation in ('output', 'terminal', 'owner'):
        h = Harness(base)
        r = h.submit('append-save')
        original_meta = h.session.meta_path.read_bytes()
        replace = ml.os.replace
        def fail_replace(*args):
            raise OSError('injected between journal fsync and state replacement')
        ml.os.replace = fail_replace
        try:
            if operation == 'output':
                refuses(h.session.observe_output, session_id=h.sid, generation=1,
                    turn_id=r['turn_id'], kind='agent_message', data={'delta': 'preserve'})
            elif operation == 'terminal':
                refuses(h.finish, r, 'failed', 37)
            else:
                refuses(h.session.observe_owner, session_id=h.sid, generation=1, owner='owner')
        finally:
            ml.os.replace = replace
        assert h.session.meta_path.read_bytes() == original_meta
        journal_bytes = h.session.journal_path.read_bytes()
        assert journal_bytes
        reopened = h.open()
        view = reopened.status(session_id=h.sid)
        assert not view['archive_limited'] and view['journal_status'] == 'journal_disagreement'
        assert reopened.read_output(session_id=h.sid)['disagreement']
        refuses(reopened.observe_output, session_id=h.sid, generation=1,
                turn_id=r['turn_id'], kind='agent_message', data={'delta': 'no repair'})
        assert 'terminal saved' in refuses(reopened.observe_terminal,
            session_id=h.sid, generation=1, turn_id=r['turn_id'], status='failed', exit_code=37)
        reopened = h.open()
        view = reopened.status(session_id=h.sid)
        assert view['state'] == 'terminal' and view['last_turn']['exit_code'] == 37
        assert view['turns_failed'] == 1 and not view['archive_limited']
        assert view['journal_error'] == view['journal_status'] == 'journal_disagreement'
        assert reopened.read_output(session_id=h.sid)['gap']
        assert h.session.journal_path.read_bytes() == journal_bytes
        replay = reopened.submit_next_turn(session_id=h.sid, generation=2,
                                           request_id='append-save', text='next turn input')
        assert replay == r and len(h.transport.calls) == 1
    print('ok output/terminal/owner append-save crash windows preserve bytes and terminal failure', flush=True)

    # Craft an alignment leaving one byte beyond marker headroom after a valid
    # record. The following tiny record fits, but must instead close the archive.
    for close_with in ('output', 'lifecycle'):
        h = Harness(base)
        r = h.submit('alignment')
        observe = lambda text: h.session.observe_output(session_id=h.sid,
            generation=1, turn_id=r['turn_id'], kind='agent_message', data={'delta': text})
        with h.session._guard():
            marker_len = len(h.session._archive_marker())
        archive_bound = ml.ARCHIVE_BOUND
        try:
            # Small real bound keeps this a fast alignment test; reader and
            # writer use the same bound. Existing suite also fills the real 1 MiB.
            ml.ARCHIVE_BOUND = 4096
            sample = {'cursor': 1, 'kind': 'agent_message', 'data': {'delta': ''},
                      'generation': 1, 'turn_id': r['turn_id'], 'timestamp': ml._now()}
            overhead = len((json.dumps(sample) + '\n').encode())
            delta = ml.ARCHIVE_BOUND - ml.MARKER_HEADROOM - 1 - overhead
            observe('x' * delta)
            assert h.session.journal_path.stat().st_size == ml.ARCHIVE_BOUND - ml.MARKER_HEADROOM - 1
            if close_with == 'output':
                result = observe('y' * (ml.MARKER_HEADROOM - marker_len))
                assert result['state'] == 'archive_limit'
            else:
                h.session.observe_owner(session_id=h.sid, generation=1, owner='owner')
            page = h.open().read_output(session_id=h.sid, after=1)
            assert page['records'][-1]['kind'] == 'archive_limit' and not page['disagreement']
            assert page['output_cursor'] == 2
            assert h.session.journal_path.stat().st_size <= ml.ARCHIVE_BOUND
        finally:
            ml.ARCHIVE_BOUND = archive_bound
    print('ok crafted near-boundary output/lifecycle markers remain complete within reader bound', flush=True)

    h = Harness(base)
    r = h.submit('bad-facts')
    original_meta = h.session.meta_path.read_bytes()
    for bad in (10 ** 5000, -(10 ** 5000), 2 ** 31, -(2 ** 31) - 1,
                True, [], {}, 1.5, '\ud800'):
        refuses(h.finish, r, 'failed', bad)
        for key in ('event', 'status', 'exit_code', 'detail'):
            refuses(h.session.observe_output, session_id=h.sid, generation=1,
                    turn_id=r['turn_id'], kind='lifecycle', data={key: bad})
        assert h.session.meta_path.read_bytes() == original_meta
        assert h.session.journal_path.read_bytes() == b''
    for key in ('delta',):
        refuses(h.session.observe_output, session_id=h.sid, generation=1,
                turn_id=r['turn_id'], kind='agent_message', data={key: '\ud800'})
    for code in (ml.INT_MIN, ml.INT_MAX):
        h2 = Harness(base)
        r2 = h2.submit('real-code')
        h2.finish(r2, 'failed', code)
        assert h2.open().status(session_id=h2.sid)['last_turn']['exit_code'] == code
    for operation in ('write', 'fsync'):
        h2 = Harness(base)
        r2 = h2.submit('io-failure')
        previous = getattr(ml.os, operation)
        def fail(*args):
            raise OSError('controlled journal I/O failure')
        setattr(ml.os, operation, fail)
        try:
            refuses(h2.session.observe_output, session_id=h2.sid, generation=1,
                    turn_id=r2['turn_id'], kind='agent_message', data={'delta': 'x'})
        finally:
            setattr(ml.os, operation, previous)
        assert len(h2.transport.calls) == 1
    # Failed lifecycle persistence must preserve terminal facts and refuse.
    h2 = Harness(base)
    r2 = h2.submit('terminal-write')
    append = ml._append_owned
    def fail_append(*args):
        raise ml.Refusal('output journal write failed')
    ml._append_owned = fail_append
    try:
        assert 'terminal saved' in refuses(h2.finish, r2, 'failed', 44)
    finally:
        ml._append_owned = append
    view = h2.open().status(session_id=h2.sid)
    assert view['last_turn']['exit_code'] == 44 and not view['archive_limited']
    assert view['journal_status'] == view['journal_error'] == 'journal_write_failed'
    for operation in ('mkdir', 'chmod'):
        previous = getattr(ml.Path if operation == 'mkdir' else ml.os, operation)
        parent = ml.Path if operation == 'mkdir' else ml.os
        def fail(*args, **kwargs):
            raise OSError('controlled directory failure')
        setattr(parent, operation, fail)
        try:
            refuses(h.open)
        finally:
            setattr(parent, operation, previous)
    print('ok bounded external facts, Unicode/types, directory/journal I/O and honest persistence failure', flush=True)

    # Exercise replacement-time destination checks directly, without _load.
    for kind in ('fifo', 'hardlink', 'symlink', 'loose'):
        h = Harness(base)
        meta = h.session.meta_path
        data = meta.read_bytes()
        meta.unlink()
        target = h.root / 'controlled-target'
        target.write_bytes(data)
        os.chmod(target, 0o600)
        if kind == 'fifo':
            os.mkfifo(meta, 0o600)
        elif kind == 'hardlink':
            os.link(target, meta)
        elif kind == 'symlink':
            meta.symlink_to(target)
        else:
            meta.write_bytes(data)
            os.chmod(meta, 0o644)
        refuses(ml._atomic_write, meta, b'forbidden replacement')
        assert target.read_bytes() == data and not h.transport.calls
        refuses(h.session.submit_next_turn, session_id=h.sid, generation=1,
                request_id='direct-unsafe', text='x')
        assert not h.transport.calls
    # FIFO lock check is isolated with a hard timeout so a regression cannot
    # hang this test process. No real provider, account or personal-file access.
    h = Harness(base)
    h.session.lock_path.unlink()
    os.mkfifo(h.session.lock_path, 0o600)
    import subprocess
    probe = '''import importlib.util, pathlib, sys
s = importlib.util.spec_from_file_location('ml', sys.argv[1])
m = importlib.util.module_from_spec(s); s.loader.exec_module(m)
try:
    m._acquire_lock(pathlib.Path(sys.argv[2]))
except m.Refusal:
    sys.exit(0)
sys.exit(1)
'''
    result = subprocess.run([sys.executable, '-B', '-c', probe,
                             str(SOURCE / 'tools/managed-lead.py'), str(h.session.lock_path)],
                            timeout=5, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    print('ok direct unsafe destination checks and bounded nonblocking FIFO lock refusal', flush=True)


def main():
    base = Path(tempfile.mkdtemp(prefix='unio-managed-lead-'))
    os.chmod(base, 0o700)
    try:
        run_suite(base)
        correction_regressions(base)
        medium_review_regressions(base)
    finally:
        shutil.rmtree(base, ignore_errors=True)
    print('all managed lead-session core checks passed')


if __name__ == '__main__':
    main()
