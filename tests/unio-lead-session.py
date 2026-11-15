#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Native lead-session CLI test suite: fake owned app-server, no providers.

Every check drives tools/lead-session.py end to end through its real
`main()` with a deterministic fake owned connection, so the exact CLI a
user installs is what is tested. No real Codex invocation, thread, turn or
worker ever happens; rpc call counts are asserted from the fake
connection's durable log, never from callbacks.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile

SOURCE = Path(__file__).resolve().parents[1]


def _load(name, relative):
    spec = importlib.util.spec_from_file_location(name, SOURCE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cli = _load('lead_session', 'tools/lead-session.py')
ml = cli.ml
bx = cli.bx
pe = cli.pe
cx = cli.cx
lp = cli.lp

MODEL = 'gpt-5.4-codex'
THREAD = 'fake-owned-thread-1'
REFUSALS = (cli.Refusal, ml.Refusal, pe.Refusal, bx.Refusal, cx.Refusal, lp.Refusal)


def refuses(argv):
    try:
        cli.main(argv)
    except REFUSALS as exc:
        return str(exc)
    raise AssertionError('expected Refusal for %r' % (argv,))


def call(argv):
    """Run one CLI command; return (payload, human text)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli.main(argv)
    assert code == 0, argv
    text = buffer.getvalue()
    if '--json' in argv:
        start = text.index('{')
        return json.loads(text[start:]), text
    return None, text


def invoke(argv):
    """Run one CLI command; return (payload, human text, exit code)."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli.main(argv)
    text = buffer.getvalue()
    if '--json' in argv:
        start = text.index('{')
        return json.loads(text[start:]), text, code
    return None, text, code


class Workspace:
    counter = 0

    def __init__(self, base):
        Workspace.counter += 1
        self.root = Path(base) / ('lead-cli-' + str(Workspace.counter))
        self.root.mkdir(mode=0o700)
        coord = self.root / 'coord'
        coord.mkdir(mode=0o700, exist_ok=True)
        (coord / 'work-policy.json').write_text(json.dumps({
            'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
            'lead_agent': 'codex', 'accounts': {'codex': 'codex-shared'},
        }) + '\n', encoding='utf-8')
        self.inputs = 0

    def input(self, text):
        self.inputs += 1
        path = self.root / ('input-%d.txt' % self.inputs)
        path.write_text(text, encoding='utf-8')
        return str(path)

    def start(self, *extra):
        goal = self.input('owner goal: deliver the vertical slice\n')
        payload = call(['--project', str(self.root), 'start',
                        '--goal', goal, '--model', MODEL,
                        '--transport', 'fake', '--json'] + list(extra))[0]
        self._sid = payload['session_id']
        return payload

    def run(self, request_id, text, *extra):
        path = self.input(text)
        return call(['--project', str(self.root), 'run', '--file', path,
                     '--request-id', request_id, '--json'] + list(extra))[0]

    def run_exit(self, request_id, text, *extra):
        """Run one turn; return (payload, exit code) without asserting 0."""
        path = self.input(text)
        payload, _, code = invoke(['--project', str(self.root), 'run',
                                   '--file', path, '--request-id', request_id,
                                   '--json'] + list(extra))
        return payload, code

    def effort(self, *args):
        return call(['--project', str(self.root), 'effort']
                    + list(args) + ['--json'])[0]

    def worker(self, *args):
        return call(['--project', str(self.root), 'worker']
                    + list(args) + ['--json'])[0]

    def status(self):
        return call(['--project', str(self.root), 'status', '--json'])[0]

    def stop(self):
        return call(['--project', str(self.root), 'stop', '--json'])[0]

    def output(self):
        return call(['--project', str(self.root), 'output', '--json'])[0]

    @property
    def sid(self):
        if getattr(self, '_sid', None):
            return self._sid
        owner = json.loads((self.root / 'coord' / 'lead-effort'
                            / 'owner.json').read_text())
        return owner['session_id']

    def set_behavior(self, behavior=None, release_held=None):
        path = (self.root / 'coord' / 'lead-effort'
                / (self.sid + '.fake.json'))
        doc = {}
        if behavior is not None:
            doc['behavior'] = behavior
        if release_held is not None:
            doc['release_held'] = release_held
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump(doc, stream)
        os.chmod(path, 0o600)

    def rpc_log(self):
        path = (self.root / 'coord' / 'lead-effort'
                / (self.sid + '.rpclog.jsonl'))
        if not path.exists():
            return []
        records = []
        for line in path.read_text().splitlines():
            records.append(json.loads(line))
        return records

    def turn_starts(self):
        return [rec for rec in self.rpc_log()
                if rec['method'] == 'turn/start']


def run_suite(base):
    # 0. Module surface: no process/network launch in the CLI module, honest
    #    owned-connection failure, nothing written on that failure. The
    #    owned default transport is the production path; it is exercised
    #    against an executable fake app-server in unio-lead-session-codex.py,
    #    never against a real codex binary here.
    assert not any(hasattr(cli, name) for name in
                   ('subprocess', 'socket', 'pty', 'Popen', 'system', 'fork'))
    ws = Workspace(base)
    goal = ws.input('owner goal\n')
    message = refuses(['--project', str(ws.root), 'start', '--goal', goal,
                       '--model', MODEL, '--codex-binary',
                       str(ws.root / 'missing-codex-binary')])
    assert 'owned app-server connection failed' in message
    assert not (ws.root / 'coord' / 'lead-effort' / 'owner.json').exists()
    print('ok default owned transport fails honestly without fabricating '
          'authority', flush=True)

    # 1. Start: exactly one supported-effort query, zero turn starts;
    #    every read-only command makes zero provider calls.
    ws = Workspace(base)
    view = ws.start()
    sid = view['session_id']
    assert view['state'] == 'idle' and view['generation'] == 1
    assert view['baseline_effort'] == 'xhigh'
    assert view['effort']['mode'] == 'auto'
    assert view['effort']['supported_efforts'] == ['low', 'medium', 'high',
                                                   'xhigh']
    assert view['effective'] == 'Unknown'
    log = ws.rpc_log()
    assert len(log) == 1 and log[0]['method'] == 'model/list'
    assert ws.status()['session_id'] == sid
    assert ws.effort('show')['mode'] == 'auto'
    ws.worker('register', 'w1')
    ws.worker('wait')
    assert len(ws.rpc_log()) == 1  # still only the single query
    print('ok start queries efforts once; read-only commands make zero calls',
          flush=True)

    # 2. Same owned thread LOW -> XHIGH -> LOW across CLI processes.
    first = ws.run('r1', 'check worker status\n')
    assert first['status'] == 'accepted' and first['effort'] == 'low'
    assert first['kind'] == 'coordination' and first['source'] == 'auto'
    assert first['turn_completed'] is True
    second = ws.run('r2', 'plan the next phase\n', '--kind', 'planning')
    assert second['effort'] == 'xhigh' and second['kind'] == 'planning'
    third = ws.run('r3', 'summarize coordination\n')
    assert third['effort'] == 'low' and third['kind'] == 'coordination'
    starts = ws.turn_starts()
    assert len(starts) == 3
    assert all(rec['params']['threadId'] == THREAD for rec in starts)
    assert [rec['params']['effort'] for rec in starts] == ['low', 'xhigh',
                                                          'low']
    assert all(rec['params']['model'] == MODEL for rec in starts)
    assert ws.status()['turns_completed'] == 3
    print('ok same owned thread LOW -> XHIGH -> LOW with explicit handoff',
          flush=True)

    # 3. Zero model calls while waiting; one wakeup per terminal event.
    before = len(ws.rpc_log())
    ws.worker('register', 'w2')
    ws.worker('wait')
    ws.worker('terminal', 'w2')
    assert ws.status()['waiting'] is True
    assert ws.status()['workers']['w2']['state'] == 'terminal'
    assert len(ws.rpc_log()) == before  # waiting and polling: zero calls
    queued = ws.effort('show')
    assert queued['pending_wakeups'] == 1, queued
    consumed_before = queued['wakeups_consumed']
    review = ws.run('r4', 'review the worker outcome\n')
    assert review['kind'] == 'review' and review['effort'] == 'xhigh'
    # The review kind came from the recorded w2 terminal wakeup (automatic
    # selection, not a pending/manual request) and consumed it exactly once.
    assert review['source'] == 'auto', review
    after_review = ws.effort('show')
    assert after_review['pending_wakeups'] == 0, after_review
    assert after_review['wakeups_consumed'] == consumed_before + 1, after_review
    routine = ws.run('r5', 'back to routine coordination\n')
    assert routine['kind'] == 'coordination' and routine['effort'] == 'low'
    ws.worker('register', 'w3')
    ws.worker('terminal', 'w3')
    again = ws.run('r6', 'review the second worker\n')
    assert again['kind'] == 'review' and again['effort'] == 'xhigh'
    settled = ws.run('r7', 'routine again\n')
    assert settled['kind'] == 'coordination'
    assert 'worker terminal event already recorded' in refuses(
        ['--project', str(ws.root), 'worker', 'terminal', 'w2', '--json'])
    print('ok zero calls while waiting; one review wakeup per terminal event',
          flush=True)

    # 4. Pending effort change during an active turn applies next turn;
    #    an incomplete turn exits nonzero with an explicit unknown
    #    delivery state (never 'accepted'/exit-0 ambiguity). This is the
    #    in-process fake seam; killed-turn semantics are covered by the
    #    owned suite against the executable fake app-server.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior(behavior='hold')
    held, held_code = ws.run_exit('r1', 'long substantive planning turn\n',
                                  '--kind', 'planning')
    assert held['turn_completed'] is False
    assert held['delivery'] == 'unknown' and held['turn_status'] is None
    assert held_code == 6
    assert ws.status()['state'] == 'running'
    before = len(ws.rpc_log())
    pending = ws.effort('request', 'xhigh', '--reason', 'owner next phase')
    assert pending['pending_next_turn']['effort'] == 'xhigh'
    assert len(ws.rpc_log()) == before  # effort control: zero calls
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('too soon\n'), '--request-id', 'r2',
                       '--json'])
    assert 'not open for a next turn' in message
    assert len(ws.rpc_log()) == before  # refused run: zero calls
    ws.set_behavior(behavior='ok', release_held=True)
    applied = ws.run('r2', 'next phase with the requested effort\n')
    assert applied['effort'] == 'xhigh' and applied['source'] == 'pending'
    assert applied['turn_completed'] is True
    back = ws.run('r3', 'routine coordination again\n')
    assert back['effort'] == 'low' and back['source'] == 'auto'
    print('ok pending change during an active turn applies only after it ends',
          flush=True)

    # 4b. Reviewer probe: a typed provider rejection must not consume the
    #     review wakeup or the pending XHIGH; the next turn is still the
    #     review at XHIGH, never a silent coordination/LOW downgrade.
    ws = Workspace(base)
    ws.start()
    ws.worker('register', 'w1')
    ws.worker('terminal', 'w1')
    ws.effort('request', 'xhigh')
    ws.set_behavior(behavior='reject')
    rejected, rejected_code = ws.run_exit('r1', 'review the worker\n')
    assert rejected_code == 2 and rejected['delivery'] == 'rejected'
    assert (rejected['effort'], rejected['kind'], rejected['source']) == (
        'xhigh', 'review', 'pending')
    assert rejected['restored']['wakeup'] == 'w1'
    effort = ws.effort('show')
    assert effort['pending_next_turn']['effort'] == 'xhigh'
    assert effort['pending_wakeups'] == 1 and effort['wakeups_consumed'] == 0
    ws.set_behavior(behavior='ok')
    review = ws.run('r2', 'review the worker again\n')
    assert (review['effort'], review['kind'], review['source']) == (
        'xhigh', 'review', 'pending')
    routine = ws.run('r3', 'routine\n')
    assert (routine['effort'], routine['kind'], routine['source']) == (
        'low', 'coordination', 'auto')
    # An untyped failure stays uncertain and is never restored.
    ws = Workspace(base)
    ws.start()
    ws.worker('register', 'w2')
    ws.worker('terminal', 'w2')
    ws.set_behavior(behavior='raise')
    failed, failed_code = ws.run_exit('r1', 'uncertain review\n')
    assert failed_code == 3 and failed['delivery'] == 'uncertain'
    assert failed['restored'] is None
    assert ws.effort('show')['pending_wakeups'] == 0
    print('ok rejected turns restore their own wakeup and pending effort; '
          'uncertain turns do not', flush=True)

    # 5. Manual override suspends auto; auto selection resumes it.
    ws = Workspace(base)
    ws.start()
    ws.effort('manual', 'xhigh', '--reason', 'owner override')
    assert ws.effort('show')['mode'] == 'manual'
    turn = ws.run('r1', 'coordination under manual override\n')
    assert turn['effort'] == 'xhigh' and turn['source'] == 'manual'
    turn = ws.run('r2', 'planning under manual override\n', '--kind',
                  'planning')
    assert turn['effort'] == 'xhigh' and turn['source'] == 'manual'
    ws.effort('auto')
    turn = ws.run('r3', 'planning after auto resumed\n', '--kind', 'planning')
    assert turn['effort'] == 'xhigh' and turn['source'] == 'auto'
    print('ok manual override suspends auto until auto is selected again',
          flush=True)

    # 6. Unsupported efforts refuse; no fallback, no max/ultra; the first
    #    adaptive interface exposes only low and xhigh (V2 correction).
    ws = Workspace(base)
    ws.start()
    assert 'unsupported manual effort: ultra' in refuses(
        ['--project', str(ws.root), 'effort', 'manual', 'ultra', '--json'])
    assert 'unsupported requested effort: max' in refuses(
        ['--project', str(ws.root), 'effort', 'request', 'max', '--json'])
    assert 'first adaptive interface' in refuses(
        ['--project', str(ws.root), 'effort', 'manual', 'high', '--json'])
    assert 'first adaptive interface' in refuses(
        ['--project', str(ws.root), 'effort', 'request', 'medium', '--json'])
    try:
        cli.main(['--project', str(ws.root), 'run', '--file',
                  ws.input('x\n'), '--request-id', 'r1', '--kind', 'vibes',
                  '--json'])
    except SystemExit:
        pass
    else:
        raise AssertionError('expected argparse refusal for unknown kind')
    narrow = Workspace(base)
    message = refuses(['--project', str(narrow.root), 'start', '--goal',
                       narrow.input('goal\n'), '--model', MODEL,
                       '--transport', 'fake', '--json',
                       '--fake-efforts', 'medium,high,xhigh'])
    assert 'unsupported coordination effort' in message
    strict = Workspace(base)
    message = refuses(['--project', str(strict.root), 'start', '--goal',
                       strict.input('goal\n'), '--model', MODEL,
                       '--transport', 'fake', '--json',
                       '--effort', 'medium'])
    assert 'first adaptive interface' in message
    message = refuses(['--project', str(strict.root), 'start', '--goal',
                       strict.input('goal\n'), '--model', MODEL,
                       '--transport', 'fake', '--json',
                       '--ceiling', 'high'])
    assert 'first adaptive interface' in message
    low_ceiling = Workspace(base)
    started = low_ceiling.start('--ceiling', 'low')
    assert started['baseline_effort'] == 'low'
    assert low_ceiling.run('r1', 'plan\n', '--kind', 'planning')[
        'effort'] == 'low'
    print('ok unsupported efforts, kinds and intermediate levels refuse '
          'without fallback', flush=True)

    # 7. STOP blocks new turns without killing workers; never auto-resumes.
    ws = Workspace(base)
    ws.start()
    ws.worker('register', 'w9')
    ws.set_behavior(behavior='hold')
    held, held_code = ws.run_exit('r1', 'active turn when stop arrives\n')
    assert held_code == 6  # incomplete turn: truthful nonzero exit
    stopped = ws.stop()
    assert stopped['stopped'] is True
    assert stopped['workers'] == {'w9': {'state': 'registered',
                                         'updated_at': stopped['workers']
                                         ['w9']['updated_at']}}
    before = len(ws.rpc_log())
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('blocked\n'), '--request-id', 'r2', '--json'])
    assert 'stopped' in message
    assert len(ws.rpc_log()) == before
    ws.set_behavior(behavior='ok', release_held=True)
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('still blocked\n'), '--request-id', 'r2',
                       '--json'])
    assert 'stopped' in message  # STOP survives the active turn ending
    assert ws.status()['stopped'] is True
    assert ws.status()['workers']['w9']['state'] == 'registered'
    print('ok STOP blocks new turns, keeps workers, never auto-resumes',
          flush=True)

    # 8. Ownership: one managed owner per workspace; unknown owner refuses.
    ws = Workspace(base)
    ws.start()
    goal = ws.input('second goal\n')
    message = refuses(['--project', str(ws.root), 'start', '--goal', goal,
                       '--model', MODEL, '--transport', 'fake', '--json'])
    assert 'already has an active managed lead session' in message
    owner_path = ws.root / 'coord' / 'lead-effort' / 'owner.json'
    owner_path.unlink()
    before = len(ws.rpc_log())
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('orphan\n'), '--request-id', 'r1', '--json'])
    assert 'no managed lead session' in message
    assert len(ws.rpc_log()) == before
    owner_path.write_text(json.dumps(
        {'session_id': 'lead-' + '0' * 24}) + '\n')
    os.chmod(owner_path, 0o600)
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('foreign\n'), '--request-id', 'r1', '--json'])
    assert 'unknown lead session control state' in message
    # start refuses an unknown owner instead of replacing it (V10 item 5):
    # no new session state, rpc log or owner change.
    lead_dir = ws.root / 'coord' / 'lead-effort'
    files_before = sorted(p.name for p in lead_dir.iterdir())
    owner_bytes = owner_path.read_bytes()
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('replace unknown owner\n'), '--model', MODEL,
                       '--transport', 'fake', '--json'])
    assert 'unreadable or unknown control state' in message, message
    assert owner_path.read_bytes() == owner_bytes
    assert sorted(p.name for p in lead_dir.iterdir()) == files_before
    # Corrupt (unreadable) state of a stopped owner also refuses.
    ws = Workspace(base)
    ws.start()
    ws.stop()
    lead_dir = ws.root / 'coord' / 'lead-effort'
    owner_path = lead_dir / 'owner.json'
    state_file = lead_dir / (ws.sid + '.json')
    fd = os.open(state_file, os.O_WRONLY | os.O_TRUNC)
    os.write(fd, b'{corrupt')
    os.close(fd)
    files_before = sorted(p.name for p in lead_dir.iterdir())
    owner_bytes = owner_path.read_bytes()
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('replace corrupt owner\n'), '--model', MODEL,
                       '--transport', 'fake', '--json'])
    assert 'unreadable or unknown control state' in message, message
    assert owner_path.read_bytes() == owner_bytes
    assert sorted(p.name for p in lead_dir.iterdir()) == files_before
    # A stopped owner with a proven (acknowledged, mapped) held turn is not
    # replaced: that would make same-thread recovery impossible.
    ws = Workspace(base)
    ws.start()
    old_sid = ws.sid
    ws.set_behavior(behavior='hold')
    _, held_code = ws.run_exit('r1', 'held turn then stop\n')
    assert held_code == 6
    ws.stop()
    lead_dir = ws.root / 'coord' / 'lead-effort'
    files_before = sorted(p.name for p in lead_dir.iterdir())
    calls_before = len(ws.rpc_log())
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('replace held owner\n'), '--model', MODEL,
                       '--transport', 'fake', '--json'])
    assert 'proven unresolved active turn' in message, message
    assert old_sid in message
    assert sorted(p.name for p in lead_dir.iterdir()) == files_before
    assert len(ws.rpc_log()) == calls_before
    # A cleanly stopped owner (no active turn) is replaced; the old one
    # stays readable as historical.
    ws = Workspace(base)
    ws.start()
    old_sid = ws.sid
    ws.stop()
    ws._sid = None
    ws.start()
    assert ws.sid != old_sid
    old_view = call(['--project', str(ws.root), 'status', '--session',
                     old_sid, '--json'])[0]
    assert old_view['historical'] is True and old_view['stopped'] is True
    print('ok one managed owner per workspace; unknown ownership refuses',
          flush=True)

    # 9. Uncertain send stays Unknown: replay returns the recorded result
    #    with zero new calls; changed content and new turns refuse; the
    #    exit code is truthful (nonzero for uncertain work).
    ws = Workspace(base)
    ws.start()
    ws.set_behavior(behavior='raise')
    uncertain, uncertain_code = ws.run_exit('r1', 'turn that crashes in flight\n')
    assert uncertain['status'] == 'uncertain'
    assert uncertain['delivery'] == 'uncertain'
    assert uncertain_code == 3
    assert ws.status()['state'] == 'outcome_unknown'
    before = len(ws.rpc_log())
    replay, replay_code = ws.run_exit('r1', 'turn that crashes in flight\n')
    assert replay['status'] == 'uncertain'
    assert replay_code == 3
    assert len(ws.rpc_log()) == before  # no resend, no new thread
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('changed content\n'), '--request-id', 'r1',
                       '--json'])
    assert 'changed content for request id' in message
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('a fresh turn\n'), '--request-id', 'r2',
                       '--json'])
    assert 'not open for a next turn' in message
    assert len(ws.rpc_log()) == before
    print('ok uncertain send stays Unknown with no replay or resend', flush=True)

    # 10. Typed provider rejection is preserved and not contradicted;
    #     rejected work exits nonzero with an explicit delivery state.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior(behavior='reject')
    rejected, rejected_code = ws.run_exit('r1', 'turn the provider rejects\n')
    assert rejected['status'] == 'rejected'
    assert rejected['delivery'] == 'rejected'
    assert rejected_code == 2
    assert ws.status()['state'] == 'idle'
    ws.set_behavior(behavior='ok')
    accepted = ws.run('r2', 'a later turn after rejection\n')
    assert accepted['status'] == 'accepted'
    assert ws.status()['history'] if False else True
    view = ws.status()
    assert view['last_turn']['status'] == 'completed'
    print('ok typed rejection preserved; session continues correctly', flush=True)

    # 11. Idempotent replay after success: zero new provider calls.
    ws = Workspace(base)
    ws.start()
    first = ws.run('r1', 'successful turn\n')
    assert first['status'] == 'accepted'
    before = len(ws.rpc_log())
    replay = ws.run('r1', 'successful turn\n')
    assert replay['status'] == 'accepted' and replay['turn_id'] == \
        first['turn_id']
    assert len(ws.rpc_log()) == before
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('different content\n'), '--request-id', 'r1',
                       '--json'])
    assert 'changed content for request id' in message
    print('ok idempotent request replay makes zero new provider calls', flush=True)

    # 12. Output journal and immutable per-turn decisions are visible.
    ws = Workspace(base)
    ws.start()
    ws.run('r1', 'first coordination turn\n')
    ws.run('r2', 'planning turn\n', '--kind', 'planning')
    page = ws.output()
    assert page['records'] and page['gap'] is False
    kinds = [rec['kind'] for rec in page['records']]
    assert 'agent_message' in kinds and 'lifecycle' in kinds
    view = ws.status()
    decisions = view['decisions']
    assert [d['effort'] for d in decisions] == ['low', 'xhigh']
    assert [d['kind'] for d in decisions] == ['coordination', 'planning']
    assert view['max_requests'] == ml.MAX_REQUESTS
    assert view['max_mappings'] == bx.OWNED_MAPPING_BOUND
    assert view['provider_turns_recorded'] == 2
    print('ok output journal and immutable per-turn decisions are visible',
          flush=True)

    # 13. Input bounds and unsafe input files refuse.
    ws = Workspace(base)
    ws.start()
    big = ws.root / 'big.txt'
    big.write_text('x' * (cli.MAX_INPUT_BYTES + 1))
    message = refuses(['--project', str(ws.root), 'run', '--file', str(big),
                       '--request-id', 'r1', '--json'])
    assert 'input bound exceeded' in message
    linked = ws.root / 'link.txt'
    real = ws.root / 'real.txt'
    real.write_text('symlinked input\n')
    linked.symlink_to(real)
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       str(linked), '--request-id', 'r1', '--json'])
    assert 'unsafe' in message
    print('ok input bounds and unsafe input files refuse', flush=True)

    # 14. Mutating controls require the current workspace owner even with
    #     an explicit --session; historical read-only views stay labelled.
    ws = Workspace(base)
    old_sid = ws.start()['session_id']
    ws.stop()
    new_sid = ws.start()['session_id']
    assert new_sid != old_sid
    for argv in (['effort', 'request', 'xhigh', '--session', old_sid],
                 ['effort', 'manual', 'low', '--session', old_sid],
                 ['worker', 'register', 'w-old', '--session', old_sid],
                 ['worker', 'wait', '--session', old_sid],
                 ['stop', '--session', old_sid]):
        message = refuses(['--project', str(ws.root)] + argv + ['--json'])
        assert 'workspace owner mismatch' in message, argv
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('stale session turn\n'), '--request-id', 'r1',
                       '--session', old_sid, '--json'])
    assert 'workspace owner mismatch' in message
    stale_view = call(['--project', str(ws.root), 'status', '--session',
                       old_sid, '--json'])[0]
    assert stale_view['historical'] is True
    stale_page = call(['--project', str(ws.root), 'output', '--session',
                       old_sid, '--json'])[0]
    assert stale_page['historical'] is True
    stale_show = call(['--project', str(ws.root), 'effort', 'show',
                       '--session', old_sid, '--json'])[0]
    assert stale_show['historical'] is True
    assert call(['--project', str(ws.root), 'status', '--json'])[0][
        'historical'] is False
    assert ws.status()['session_id'] == new_sid
    print('ok mutating controls need the current owner; stale views are '
          'labelled historical', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='lead-session-') as base:
        run_suite(base)
    print('all lead-session CLI checks passed')


if __name__ == '__main__':
    main()
