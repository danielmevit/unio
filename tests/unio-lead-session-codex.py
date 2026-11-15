#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Owned lead-session transport suite: executable fake app-server, no providers.

Every check drives the SAME production owned branch of
tools/lead-session.py (`--transport owned`) end to end through its real
`main()` against an executable fake Codex app-server speaking JSON-RPC
over stdio. The fake is generated per workspace as a real process with
durable thread/turn state, a request log and a behavior sidecar, so
process lifecycle, exact thread resume, notification routing and
zero-call guarantees are asserted from outside the CLI. The old
in-process fake-only seam is NOT selected anywhere here. No real Codex
binary, account or model call is ever touched.
"""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
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

MODEL = 'gpt-5.4-codex'
REFUSALS = (cli.Refusal, ml.Refusal, pe.Refusal, bx.Refusal, cx.Refusal)

FAKE_TEMPLATE = '''#!/usr/bin/env python3
"""Generated fake Codex app-server for offline owned lead-session tests."""
import json
import os
import sys
from pathlib import Path

STATE_PATH = Path(__STATE__)
LOG_PATH = Path(__LOG__)
BEHAVIOR_PATH = Path(__BEHAVIOR__)
MODEL = __MODEL__


def log(event, **facts):
    rec = dict(event=event, pid=os.getpid())
    rec.update(facts)
    line = (json.dumps(rec) + chr(10)).encode()
    fd = os.open(LOG_PATH, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(fd, 'ab') as stream:
        stream.write(line)
        stream.flush()


def load_state():
    if STATE_PATH.exists():
        return json.loads(STATE_PATH.read_text())
    return {'threads': {}, 'turns': 0}


def save_state(doc):
    tmp = STATE_PATH.with_name(STATE_PATH.name + '.tmp')
    tmp.write_text(json.dumps(doc))
    os.replace(tmp, STATE_PATH)


def behavior():
    if BEHAVIOR_PATH.exists():
        try:
            doc = json.loads(BEHAVIOR_PATH.read_text())
        except ValueError:
            return 'ok'
        if isinstance(doc, dict) and isinstance(doc.get('behavior'), str):
            return doc['behavior']
    return 'ok'


def main():
    log('spawn')
    doc = load_state()
    out = sys.stdout

    def send(msg):
        out.write(json.dumps(msg) + chr(10))
        out.flush()

    def notify(method, params):
        send({'method': method, 'params': params})

    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if not isinstance(req, dict):
            continue
        method = req.get('method')
        rid = req.get('id')
        params = req.get('params') or {}
        log('request', method=method, id=rid)
        if method == 'initialize':
            send({'id': rid, 'result': {}})
        elif method == 'account/read':
            send({'id': rid, 'result': {'account': {'type': 'chatgpt',
                                                    'id': 'fake-account'}}})
        elif method == 'model/list':
            if not params.get('cursor'):
                send({'id': rid, 'result': {'data': [], 'nextCursor': 'page2'}})
            else:
                efforts = ('medium', 'high', 'xhigh') if behavior() == 'narrow' \\
                    else ('low', 'medium', 'high', 'xhigh')
                send({'id': rid, 'result': {'data': [{
                    'id': MODEL,
                    'supportedReasoningEfforts': [
                        {'reasoningEffort': e} for e in efforts]}],
                    'nextCursor': None}})
        elif method == 'thread/start':
            tid = 'fake-thread-%d' % (len(doc['threads']) + 1)
            doc['threads'][tid] = {'turns': []}
            save_state(doc)
            send({'id': rid, 'result': {'thread': {'id': tid,
                                                   'reasoningEffort': None}}})
        elif method == 'thread/resume':
            tid = params.get('threadId')
            if tid not in doc['threads']:
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'unknown thread'}})
            else:
                send({'id': rid, 'result': {'thread': {'id': tid}}})
        elif method == 'thread/read':
            tid = params.get('threadId')
            thread = doc['threads'].get(tid)
            if thread is None:
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'unknown thread'}})
            else:
                if behavior() == 'release-held':
                    for turn in thread['turns']:
                        if turn['status'] == 'inProgress':
                            turn['status'] = 'completed'
                    save_state(doc)
                send({'id': rid, 'result': {'thread': {
                    'id': tid,
                    'turns': [dict(turn) for turn in thread['turns']]}}})
        elif method == 'turn/start':
            tid = params.get('threadId')
            thread = doc['threads'].get(tid)
            if thread is None:
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'unknown thread'}})
                continue
            mode = behavior()
            if mode == 'reject-turn':
                send({'id': rid, 'error': {'code': -32000,
                                           'message': 'fake typed rejection'}})
                continue
            if mode == 'bad-ack':
                send({'id': rid, 'result': {'turn': {}}})
                continue
            if mode == 'wrong-thread-ack':
                send({'id': rid, 'result': {'threadId': 'other-thread',
                                             'turn': {'id': 'foreign-turn'}}})
                continue
            if mode == 'crash':
                log('crash')
                out.flush()
                os.close(1)
                os._exit(9)
            if mode == 'foreign-event':
                notify('item/agentMessage/delta',
                       {'threadId': 'other-thread', 'turnId': 'other-turn',
                        'itemId': 'x', 'delta': 'foreign output'})
            doc['turns'] += 1
            uid = 'fake-turn-%d' % doc['turns']
            thread['turns'].append({'id': uid, 'status': 'inProgress'})
            save_state(doc)
            send({'id': rid, 'result': {'turn': {'id': uid,
                                                'status': 'inProgress'}}})
            if mode == 'hold':
                continue
            notify('turn/started', {'threadId': tid,
                                    'turn': {'id': uid,
                                             'status': 'inProgress'}})
            notify('item/agentMessage/delta',
                   {'threadId': tid, 'turnId': uid, 'itemId': 'item-1',
                    'delta': 'fake owned turn output'})
            final = 'failed' if mode == 'fail-turn' else 'completed'
            for turn in thread['turns']:
                if turn['id'] == uid:
                    turn['status'] = final
            save_state(doc)
            notify('turn/completed', {'threadId': tid,
                                      'turn': {'id': uid, 'status': final}})
        elif rid is not None:
            send({'id': rid, 'error': {'code': -32601,
                                        'message': 'unsupported method'}})


main()
'''


def refuses(argv):
    try:
        cli.main(argv)
    except REFUSALS as exc:
        return str(exc)
    raise AssertionError('expected Refusal for %r' % (argv,))


def call(argv):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        code = cli.main(argv)
    assert code == 0, argv
    text = buffer.getvalue()
    if '--json' in argv:
        start = text.index('{')
        return json.loads(text[start:]), text
    return None, text


class Workspace:
    counter = 0

    def __init__(self, base):
        Workspace.counter += 1
        self.root = Path(base) / ('lead-owned-' + str(Workspace.counter))
        self.root.mkdir(mode=0o700)
        self.inputs = 0
        self.binary = self.root / 'fake-codex-app-server.py'
        self.state_path = self.root / 'fake-state.json'
        self.log_path = self.root / 'fake-log.jsonl'
        self.behavior_path = self.root / 'fake-behavior.json'
        script = (FAKE_TEMPLATE
                  .replace('__STATE__', json.dumps(str(self.state_path)))
                  .replace('__LOG__', json.dumps(str(self.log_path)))
                  .replace('__BEHAVIOR__', json.dumps(str(self.behavior_path)))
                  .replace('__MODEL__', json.dumps(MODEL)))
        self.binary.write_text(script, encoding='utf-8')
        os.chmod(self.binary, 0o700)

    def input(self, text):
        self.inputs += 1
        path = self.root / ('input-%d.txt' % self.inputs)
        path.write_text(text, encoding='utf-8')
        return str(path)

    def set_behavior(self, behavior):
        fd = os.open(self.behavior_path,
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'behavior': behavior}, stream)

    def start(self, *extra):
        goal = self.input('owner goal: deliver the owned transport\n')
        payload = call(['--project', str(self.root), 'start', '--goal', goal,
                        '--model', MODEL, '--transport', 'owned',
                        '--codex-binary', str(self.binary), '--json']
                       + list(extra))[0]
        self._sid = payload['session_id']
        return payload

    def run(self, request_id, text, *extra):
        path = self.input(text)
        return call(['--project', str(self.root), 'run', '--file', path,
                     '--request-id', request_id, '--turn-wait', '5',
                     '--json'] + list(extra))[0]

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

    def log_records(self):
        if not self.log_path.exists():
            return []
        records = []
        for line in self.log_path.read_text().splitlines():
            records.append(json.loads(line))
        return records

    def spawns(self):
        return [rec for rec in self.log_records() if rec['event'] == 'spawn']

    def requests(self, method):
        return [rec for rec in self.log_records()
                if rec['event'] == 'request' and rec['method'] == method]

    def turn_starts(self):
        return self.requests('turn/start')


def run_suite(base):
    # 0. Surface: the CLI module owns no process layer (the connection
    #    module does); the generated fake is a real executable; the
    #    installer embeds the new module byte-identically (helper parity).
    assert not any(hasattr(cli, name) for name in
                   ('subprocess', 'socket', 'Popen', 'system', 'fork'))
    assert hasattr(cx, 'subprocess') and hasattr(cx, 'OwnedCodexConnection')
    embed = _load('embed_managed_lead', 'tools/embed-managed-lead.py')
    block = embed.embedded_block()
    assert 'lead-session-codex.py' in block
    installer = (SOURCE / 'unio-install.sh').read_text()
    assert block in installer
    ws = Workspace(base)
    assert ws.binary.exists() and os.access(ws.binary, os.X_OK)
    print('ok surface: executable fake, owned connection module, embed parity',
          flush=True)

    # 1. Start: one owned process initializes, verifies the account,
    #    queries the paged model catalog and starts ONE new thread;
    #    zero turn starts; the exact thread id is persisted.
    ws = Workspace(base)
    view = ws.start()
    sid = view['session_id']
    assert view['transport'] == 'owned'
    assert view['state'] == 'idle' and view['generation'] == 1
    assert view['thread_id'].startswith('fake-thread-')
    assert view['baseline_effort'] == 'xhigh'
    assert view['effort']['supported_efforts'] == ['low', 'medium', 'high',
                                                   'xhigh']
    assert view['effective'] == 'Unknown'
    assert len(ws.spawns()) == 1
    assert len(ws.requests('initialize')) == 1
    assert len(ws.requests('account/read')) == 1
    assert len(ws.requests('model/list')) == 2  # two catalog pages
    assert len(ws.requests('thread/start')) == 1
    assert ws.requests('thread/start')[0]['id'] == 5  # after init/account/pages
    assert ws.turn_starts() == []
    assert (ws.root / 'coord' / 'lead-effort' / 'owner.json').exists()
    print('ok owned start: init, account, paged model list, one new thread',
          flush=True)

    # 2. Exact same-thread resume and LOW -> XHIGH -> LOW across one
    #    owned process per command.
    thread = view['thread_id']
    first = ws.run('r1', 'check worker status\n')
    assert first['status'] == 'accepted' and first['effort'] == 'low'
    assert first['kind'] == 'coordination' and first['source'] == 'auto'
    assert first['turn_completed'] is True and first['thread_id'] == thread
    second = ws.run('r2', 'plan the next phase\n', '--kind', 'planning')
    assert second['effort'] == 'xhigh' and second['kind'] == 'planning'
    third = ws.run('r3', 'summarize coordination\n')
    assert third['effort'] == 'low' and third['kind'] == 'coordination'
    starts = ws.turn_starts()
    assert len(starts) == 3
    assert all(rec['id'] == 4 for rec in starts)  # per-command rpc counter
    resumes = ws.requests('thread/resume')
    assert len(resumes) == 3
    assert all(rec['id'] == 3 for rec in resumes)
    assert len(ws.requests('thread/read')) == 0  # nothing to reconcile
    assert ws.status()['turns_completed'] == 3
    state = json.loads((ws.root / 'coord' / 'lead-effort'
                        / (sid + '.json')).read_text())
    assert state['thread_id'] == thread
    assert state['transport'] == 'owned'
    assert len(state['provider_turns']) == 3
    print('ok exact same-thread resume with LOW -> XHIGH -> LOW', flush=True)

    # 3. Zero provider calls while waiting and on every read-only
    #    command; one review wakeup per worker terminal event.
    before_spawns = len(ws.spawns())
    before_starts = len(ws.turn_starts())
    ws.worker('register', 'w1')
    ws.worker('wait')
    ws.worker('terminal', 'w1')
    assert ws.status()['waiting'] is True
    assert ws.status()['workers']['w1']['state'] == 'terminal'
    ws.effort('show')
    ws.output()
    assert len(ws.spawns()) == before_spawns  # zero owned processes
    review = ws.run('r4', 'review the worker outcome\n')
    assert review['kind'] == 'review' and review['effort'] == 'xhigh'
    routine = ws.run('r5', 'back to routine coordination\n')
    assert routine['kind'] == 'coordination' and routine['effort'] == 'low'
    assert 'worker terminal event already recorded' in refuses(
        ['--project', str(ws.root), 'worker', 'terminal', 'w1', '--json'])
    assert len(ws.turn_starts()) == before_starts + 2
    print('ok zero calls while waiting and reading; one wakeup per terminal',
          flush=True)

    # 4. Active-turn pending change: a held turn stays running with zero
    #    sends; the pending effort applies only after the provider's own
    #    thread state proves the turn ended (thread/read reconciliation).
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('hold')
    held = ws.run('r1', 'long substantive planning turn\n', '--kind',
                  'planning')
    assert held['turn_completed'] is False
    assert ws.status()['state'] == 'running'
    before_spawns = len(ws.spawns())
    pending = ws.effort('request', 'xhigh', '--reason', 'owner next phase')
    assert pending['pending_next_turn']['effort'] == 'xhigh'
    assert len(ws.spawns()) == before_spawns  # effort control: zero calls
    blocked = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('too soon\n'), '--request-id', 'r2',
                       '--turn-wait', '5', '--json'])
    assert 'not open for a next turn' in blocked  # provider truth: inProgress
    ws.set_behavior('release-held')
    applied = ws.run('r2', 'next phase with the requested effort\n')
    assert applied['effort'] == 'xhigh' and applied['source'] == 'pending'
    assert applied['turn_completed'] is True
    assert len(ws.requests('thread/read')) == 2  # blocked probe + reconcile
    back = ws.run('r3', 'routine coordination again\n')
    assert back['effort'] == 'low' and back['source'] == 'auto'
    print('ok pending change during an active turn applies only after it '
          'ends', flush=True)

    # 5. STOP, owner holds and reservation contention refuse BEFORE any
    #    owned process is spawned.
    ws = Workspace(base)
    ws.start()
    before_spawns = len(ws.spawns())
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('second goal\n'), '--model', MODEL,
                       '--transport', 'owned', '--codex-binary',
                       str(ws.binary), '--json'])
    assert 'already has an active managed lead session' in message
    assert len(ws.spawns()) == before_spawns
    ws.worker('register', 'w9')
    stopped = ws.stop()
    assert stopped['stopped'] is True
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('blocked\n'), '--request-id', 'r1',
                       '--turn-wait', '5', '--json'])
    assert 'stopped' in message
    assert len(ws.spawns()) == before_spawns
    assert ws.status()['workers']['w9']['state'] == 'registered'
    owner_path = ws.root / 'coord' / 'lead-effort' / 'owner.json'
    owner_path.write_text(json.dumps({'session_id': 'lead-' + '0' * 24})
                          + '\n')
    os.chmod(owner_path, 0o600)
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('foreign\n'), '--request-id', 'r1',
                       '--turn-wait', '5', '--json'])
    assert 'unknown lead session control state' in message
    assert len(ws.spawns()) == before_spawns
    print('ok STOP, owner holds and contention refuse before the child',
          flush=True)

    # 6. Wrong model and unsupported efforts refuse honestly; no fallback.
    ws = Workspace(base)
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('goal\n'), '--model', 'gpt-nonexistent',
                       '--transport', 'owned', '--codex-binary',
                       str(ws.binary), '--json'])
    assert 'owned model not advertised' in message
    assert not (ws.root / 'coord' / 'lead-effort'
                / 'owner.json').exists()
    ws = Workspace(base)
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('goal\n'), '--model', MODEL,
                       '--transport', 'owned', '--codex-binary',
                       str(ws.binary), '--json', '--ceiling', 'high'])
    assert 'first adaptive interface' in message
    assert len(ws.spawns()) == 0  # pure policy refusal before the child
    ws = Workspace(base)
    ws.set_behavior('narrow')
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('goal\n'), '--model', MODEL,
                       '--transport', 'owned', '--codex-binary',
                       str(ws.binary), '--json'])
    assert 'unsupported coordination effort' in message
    assert not (ws.root / 'coord' / 'lead-effort'
                / 'owner.json').exists()
    ws = Workspace(base)
    ws.start()
    before_spawns = len(ws.spawns())
    assert 'unsupported manual effort: ultra' in refuses(
        ['--project', str(ws.root), 'effort', 'manual', 'ultra', '--json'])
    assert 'unsupported requested effort: max' in refuses(
        ['--project', str(ws.root), 'effort', 'request', 'max', '--json'])
    assert len(ws.spawns()) == before_spawns
    print('ok wrong model and unsupported efforts refuse without fallback',
          flush=True)

    # 7. Foreign events never enter the turn; the real output does.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('foreign-event')
    turn = ws.run('r1', 'coordination with a foreign event\n')
    assert turn['status'] == 'accepted' and turn['turn_completed'] is True
    page = ws.output()
    deltas = [rec['data']['delta'] for rec in page['records']
              if rec['kind'] == 'agent_message']
    assert deltas == ['fake owned turn output']
    assert all('foreign' not in json.dumps(rec) for rec in page['records'])
    print('ok foreign-thread events are ignored; output stays exact', flush=True)

    # 8. Malformed acknowledgement: uncertain, no replay, no resend, no
    #    new thread; a new turn refuses at the core with zero turn starts.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('bad-ack')
    uncertain = ws.run('r1', 'turn with a malformed acknowledgement\n')
    assert uncertain['status'] == 'uncertain'
    assert ws.status()['state'] == 'outcome_unknown'
    before_starts = len(ws.turn_starts())
    replay = ws.run('r1', 'turn with a malformed acknowledgement\n')
    assert replay['status'] == 'uncertain'
    assert len(ws.turn_starts()) == before_starts  # no resend
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('a fresh turn\n'), '--request-id', 'r2',
                       '--turn-wait', '5', '--json'])
    assert 'not open for a next turn' in message
    assert len(ws.turn_starts()) == before_starts
    print('ok malformed ack stays uncertain with no replay or resend', flush=True)

    # 9. Typed provider rejection is preserved; the session continues.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('reject-turn')
    rejected = ws.run('r1', 'turn the provider rejects\n')
    assert rejected['status'] == 'rejected'
    assert ws.status()['state'] == 'idle'
    ws.set_behavior('ok')
    accepted = ws.run('r2', 'a later turn after rejection\n')
    assert accepted['status'] == 'accepted'
    assert ws.status()['last_turn']['status'] == 'completed'
    print('ok typed rejection preserved; session continues correctly', flush=True)

    # 10. Owned process crash mid-send: untyped failure stays uncertain;
    #     replay returns the recorded result; new turns refuse with zero
    #     turn starts.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('crash')
    crashed = ws.run('r1', 'turn that crashes the owned process\n')
    assert crashed['status'] == 'uncertain'
    assert ws.status()['state'] == 'outcome_unknown'
    before_starts = len(ws.turn_starts())
    replay = ws.run('r1', 'turn that crashes the owned process\n')
    assert replay['status'] == 'uncertain'
    assert len(ws.turn_starts()) == before_starts
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('a fresh turn\n'), '--request-id', 'r2',
                       '--turn-wait', '5', '--json'])
    assert 'not open for a next turn' in message
    assert len(ws.turn_starts()) == before_starts
    print('ok owned process crash stays uncertain with no replay', flush=True)

    # 11. Idempotent replay after success: zero new turn starts.
    ws = Workspace(base)
    ws.start()
    first = ws.run('r1', 'successful turn\n')
    assert first['status'] == 'accepted'
    before_starts = len(ws.turn_starts())
    replay = ws.run('r1', 'successful turn\n')
    assert replay['status'] == 'accepted'
    assert replay['turn_id'] == first['turn_id']
    assert len(ws.turn_starts()) == before_starts
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('different content\n'), '--request-id', 'r1',
                       '--turn-wait', '5', '--json'])
    assert 'changed content for request id' in message
    print('ok idempotent replay sends zero new turn starts', flush=True)

    # 12. Original failures are retained; the session stays usable.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('fail-turn')
    failed = ws.run('r1', 'turn that fails\n')
    assert failed['status'] == 'accepted'
    assert failed['turn_completed'] is False
    view = ws.status()
    assert view['state'] == 'terminal'
    assert view['last_turn']['status'] == 'failed'
    assert view['turns_failed'] == 1
    ws.set_behavior('ok')
    next_turn = ws.run('r2', 'turn after the failure\n')
    assert next_turn['status'] == 'accepted'
    assert next_turn['turn_completed'] is True
    print('ok original failures retained; session stays usable', flush=True)

    # 13. Output journal, decision records and owned-process cleanup.
    ws = Workspace(base)
    ws.start()
    ws.run('r1', 'first coordination turn\n')
    ws.run('r2', 'planning turn\n', '--kind', 'planning')
    page = ws.output()
    assert page['records'] and page['gap'] is False
    kinds = [rec['kind'] for rec in page['records']]
    assert 'agent_message' in kinds and 'lifecycle' in kinds
    view = ws.status()
    assert [d['effort'] for d in view['decisions']] == ['low', 'xhigh']
    assert view['provider_turns_recorded'] == 2
    for rec in ws.spawns():
        try:
            os.kill(rec['pid'], 0)
        except ProcessLookupError:
            continue
        raise AssertionError('owned process %d survived its command'
                             % rec['pid'])
    print('ok output journal, decisions and owned-process cleanup', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='lead-owned-') as base:
        run_suite(base)
    print('all owned lead-session transport checks passed')


if __name__ == '__main__':
    main()
