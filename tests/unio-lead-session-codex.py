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
import fcntl
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

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
REFUSALS = (cli.Refusal, ml.Refusal, pe.Refusal, bx.Refusal, cx.Refusal, lp.Refusal)

FAKE_TEMPLATE = '''#!/usr/bin/env python3
"""Generated fake Codex app-server for offline owned lead-session tests."""
import json
import os
import select
import sys
import time
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


def sidecar(key, default):
    if BEHAVIOR_PATH.exists():
        try:
            doc = json.loads(BEHAVIOR_PATH.read_text())
        except ValueError:
            return default
        if isinstance(doc, dict) and isinstance(doc.get(key), str):
            return doc[key]
    return default


def behavior():
    return sidecar('behavior', 'ok')


def interrupt_behavior():
    # ok: ack {} then a real terminal 'interrupted' event; silent: ack {}
    # only (acknowledgement is not terminal proof); reject: typed error.
    return sidecar('interrupt', 'ok')


def read_behavior():
    # 'abandoned-interrupted': the provider's own thread state reports a
    # turn whose app-server was killed as interrupted. Default: a killed
    # turn stays inProgress forever (nothing keeps computing it).
    return sidecar('read', 'stale')


def main():
    log('spawn')
    doc = load_state()
    out = sys.stdout

    def send(msg):
        out.write(json.dumps(msg) + chr(10))
        out.flush()

    def notify(method, params):
        send({'method': method, 'params': params})

    # A turn computes ONLY while this process lives: 'slow-turn' finishes
    # after a delay inside this process; 'hold' never finishes here. When
    # this process is killed its in-flight turn stays inProgress in the
    # durable state; no later process ever completes it on its own.
    running = {}
    # Native lazy materialization (observed with codex-cli 0.169.0 by a
    # zero-inference control): thread/start creates a thread known ONLY to
    # this process; nothing durable exists until its first accepted
    # turn/start. thread/resume of an unmaterialized thread refuses with
    # -32600 "no rollout found" -- even in the creating process -- while
    # thread/read in the creating process still answers.
    unmaterialized = {}

    def materialize(tid):
        if tid in unmaterialized:
            doc['threads'][tid] = unmaterialized.pop(tid)
            save_state(doc)
            log('materialize', threadId=tid)
        return doc['threads'].get(tid)

    def no_rollout(rid, tid):
        send({'id': rid, 'error': {
            'code': -32600,
            'message': 'no rollout found for thread id %s' % tid}})

    def set_status(tid, uid, status):
        for turn in doc['threads'][tid]['turns']:
            if turn['id'] == uid:
                turn['status'] = status
        save_state(doc)

    def finish(tid, uid, final):
        running.pop(uid, None)
        set_status(tid, uid, final)
        notify('turn/completed', {'threadId': tid,
                                  'turn': {'id': uid, 'status': final}})

    pending_lines = []
    raw = b''
    stdin_fd = sys.stdin.fileno()
    while True:
        if not pending_lines:
            due = [at for at, _ in running.values() if at is not None]
            timeout = max(0.0, min(due) - time.monotonic()) if due else None
            ready, _, _ = select.select([stdin_fd], [], [], timeout)
            if not ready:
                now = time.monotonic()
                for uid, (at, tid) in list(running.items()):
                    if at is not None and at <= now:
                        finish(tid, uid, 'completed')
                continue
            chunk = os.read(stdin_fd, 65536)
            if not chunk:
                return
            raw += chunk
            while bytes([10]) in raw:
                one, raw = raw.split(bytes([10]), 1)
                pending_lines.append(one.decode())
            continue
        line = pending_lines.pop(0)
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
            if behavior() == 'reject-init':
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'fake initialize rejection'}})
            else:
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
            if behavior() == 'reject-thread-start':
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'fake thread/start rejection'}})
                continue
            # Unique ids across processes; the counter is not a thread.
            doc['created'] = doc.get('created', 0) + 1
            save_state(doc)
            tid = 'fake-thread-%d' % doc['created']
            unmaterialized[tid] = {'turns': []}
            log('thread-created', threadId=tid)
            send({'id': rid, 'result': {'thread': {
                'id': tid, 'reasoningEffort': None, 'ephemeral': False,
                'path': '/fake/sessions/rollout-%s.jsonl' % tid}}})
        elif method == 'thread/resume':
            tid = params.get('threadId')
            if tid not in doc['threads']:
                no_rollout(rid, tid)
            else:
                send({'id': rid, 'result': {'thread': {'id': tid}}})
        elif method == 'thread/read':
            tid = params.get('threadId')
            thread = doc['threads'].get(tid) or unmaterialized.get(tid)
            if thread is None:
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'unknown thread'}})
            else:
                if read_behavior() == 'abandoned-interrupted':
                    for turn in thread['turns']:
                        if (turn['status'] == 'inProgress'
                                and turn['id'] not in running):
                            turn['status'] = 'interrupted'
                    save_state(doc)
                send({'id': rid, 'result': {'thread': {
                    'id': tid,
                    'turns': [dict(turn) for turn in thread['turns']]}}})
        elif method == 'turn/start':
            tid = params.get('threadId')
            thread = doc['threads'].get(tid) or unmaterialized.get(tid)
            if thread is None:
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'unknown thread'}})
                continue
            mode = behavior()
            if mode in ('reject-turn', 'slow-reject'):
                if mode == 'slow-reject':
                    log('slow-reject')
                    time.sleep(2.0)
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
            if mode == 'slow-ack':
                # Delay the turn/start reply so a real overlapping CLI run
                # process is mid-RPC (past its decision, before persist).
                log('slow-ack')
                time.sleep(2.0)
            if mode == 'crash':
                log('crash')
                out.flush()
                sys.stderr.write('fake owned crash diagnostic' + chr(10))
                sys.stderr.flush()
                os.close(1)
                os._exit(9)
            if mode == 'die-waiting':
                # Acknowledge the turn, then die without any terminal
                # notification: the run's wait loop must stop promptly.
                thread = materialize(tid)
                doc['turns'] += 1
                uid = 'fake-turn-%d' % doc['turns']
                thread['turns'].append({'id': uid, 'status': 'inProgress'})
                save_state(doc)
                send({'id': rid, 'result': {'turn': {'id': uid,
                                                    'status': 'inProgress'}}})
                log('die-waiting')
                out.flush()
                sys.stderr.write('fake owned wait death diagnostic' + chr(10))
                sys.stderr.flush()
                os.close(1)
                os._exit(9)
            if mode == 'foreign-event':
                notify('item/agentMessage/delta',
                       {'threadId': 'other-thread', 'turnId': 'other-turn',
                        'itemId': 'x', 'delta': 'foreign output'})
            thread = materialize(tid)
            doc['turns'] += 1
            uid = 'fake-turn-%d' % doc['turns']
            thread['turns'].append({'id': uid, 'status': 'inProgress'})
            save_state(doc)
            send({'id': rid, 'result': {'turn': {'id': uid,
                                                'status': 'inProgress'}}})
            notify('turn/started', {'threadId': tid,
                                    'turn': {'id': uid,
                                             'status': 'inProgress'}})
            notify('item/agentMessage/delta',
                   {'threadId': tid, 'turnId': uid, 'itemId': 'item-1',
                    'delta': 'fake owned turn output'})
            if mode == 'hold':
                running[uid] = (None, tid)
                continue
            if mode == 'slow-turn':
                running[uid] = (time.monotonic() + 1.5, tid)
                continue
            final = 'failed' if mode == 'fail-turn' else 'completed'
            for turn in thread['turns']:
                if turn['id'] == uid:
                    turn['status'] = final
            save_state(doc)
            notify('turn/completed', {'threadId': tid,
                                      'turn': {'id': uid, 'status': final}})
        elif method == 'turn/interrupt':
            tid = params.get('threadId')
            uid = params.get('turnId')
            log('interrupt', threadId=tid, turnId=uid)
            thread = doc['threads'].get(tid)
            known = thread is not None and any(
                turn['id'] == uid for turn in thread['turns'])
            mode = interrupt_behavior()
            if not known or not isinstance(uid, str):
                send({'id': rid, 'error': {'code': -32602,
                                            'message': 'unknown turn'}})
            elif mode == 'reject':
                send({'id': rid, 'error': {'code': -32000,
                                            'message': 'fake interrupt rejection'}})
            else:
                send({'id': rid, 'result': {}})
                status = [turn['status'] for turn in thread['turns']
                          if turn['id'] == uid][0]
                if mode == 'ok' and status == 'inProgress':
                    finish(tid, uid, 'interrupted')
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
        self.root = Path(base) / ('lead-owned-' + str(Workspace.counter))
        self.root.mkdir(mode=0o700)
        coord = self.root / 'coord'
        coord.mkdir(mode=0o700, exist_ok=True)
        (coord / 'work-policy.json').write_text(json.dumps({
            'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
            'lead_agent': 'codex', 'accounts': {'codex': 'codex-shared'},
        }) + '\n', encoding='utf-8')
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

    def set_stop(self, active=True):
        stop_file = self.root / 'coord' / 'STOP'
        if active:
            stop_file.write_text('STOP\n')
        elif stop_file.exists():
            stop_file.unlink()

    def set_off(self, agent='codex', duration=None):
        off_dir = self.root / 'coord' / 'off'
        off_dir.mkdir(mode=0o700, exist_ok=True)
        marker = off_dir / agent
        if duration is None:
            marker.write_text('')
        else:
            marker.write_text(str(int(time.time() + duration)) + '\n')

    def clear_off(self, agent='codex'):
        marker = self.root / 'coord' / 'off' / agent
        if marker.exists():
            marker.unlink()

    def set_policy(self, doc):
        (self.root / 'coord' / 'work-policy.json').write_text(
            json.dumps(doc) + '\n', encoding='utf-8')

    @contextlib.contextmanager
    def occupy_slot(self, group='codex-shared', name='slot-1'):
        slot_dir = self.root / 'coord' / '.locks' / 'work-policy-slots' / group
        slot_dir.mkdir(parents=True, exist_ok=True)
        slot_path = slot_dir / ('wpslot-%s.json' % name)
        slot_path.write_text(json.dumps({
            'schema_version': 1, 'group': group, 'agent': 'worker-1',
            'worker': 'w1', 'task': 't1', 'kind': 'run',
            'created_at': '2026-11-15T10:00:00Z',
        }) + '\n', encoding='utf-8')
        fd = os.open(slot_path, os.O_RDWR)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield slot_path
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(fd)
            if slot_path.exists():
                slot_path.unlink()

    @contextlib.contextmanager
    def occupy_lease(self):
        locks_dir = self.root / 'coord' / '.locks'
        locks_dir.mkdir(parents=True, exist_ok=True)
        lease_path = locks_dir / 'lead-session.lock'
        fd = os.open(lease_path, os.O_CREAT | os.O_RDWR, 0o600)
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield lease_path
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
            os.close(fd)

    def input(self, text):
        self.inputs += 1
        path = self.root / ('input-%d.txt' % self.inputs)
        path.write_text(text, encoding='utf-8')
        return str(path)

    def set_behavior(self, behavior, interrupt='ok', read='stale'):
        fd = os.open(self.behavior_path,
                     os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as stream:
            json.dump({'behavior': behavior, 'interrupt': interrupt,
                       'read': read}, stream)

    def recover(self, *extra):
        payload, _, code = invoke(['--project', str(self.root), 'recover',
                                   '--drain', '2', '--json'] + list(extra))
        return payload, code

    def fake_turns(self):
        doc = json.loads(self.state_path.read_text())
        return [turn for thread in doc['threads'].values()
                for turn in thread['turns']]

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

    def run_exit(self, request_id, text, *extra):
        """Run one turn; return (payload, exit code) without asserting 0."""
        path = self.input(text)
        payload, _, code = invoke(['--project', str(self.root), 'run',
                                   '--file', path, '--request-id', request_id,
                                   '--turn-wait', '5',
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

    # 4. Controller deadline on a long turn: the run keeps its owned
    #    process until the deadline, then requests turn/interrupt for the
    #    EXACT proven thread/turn. A bare {} acknowledgement is not
    #    terminal proof: the turn stays active/Unknown (exit 6), the killed
    #    fake process does NOT keep computing (durable inProgress stays),
    #    a pending effort waits, and explicit `recover --interrupt` on the
    #    SAME thread resolves it with zero turn starts or resends.
    ws = Workspace(base)
    view = ws.start()
    thread = view['thread_id']
    ws.set_behavior('hold', interrupt='silent')
    started = time.monotonic()
    held, held_code = ws.run_exit('r1', 'long substantive planning turn\n',
                                  '--kind', 'planning', '--turn-wait', '1',
                                  '--interrupt-drain', '1')
    assert time.monotonic() - started >= 1.0  # process kept for the wait
    assert held_code == 6
    assert held['status'] == 'accepted' and held['turn_completed'] is False
    assert held['delivery'] == 'unknown' and held['turn_status'] is None
    assert held['wait'] == {'seconds': 1, 'outcome': 'deadline'}
    interrupt = held['interrupt']
    assert interrupt['acknowledged'] is True and interrupt['error'] is None
    assert interrupt['terminal_observed'] is False
    assert interrupt['provider_status'] == 'inProgress'
    assert interrupt['thread_id'] == thread
    assert 'recover' in held['note'] and 'Unknown' in held['note']
    sent = ws.requests('turn/interrupt')
    assert len(sent) == 1
    interrupts = [rec for rec in ws.log_records() if rec['event'] == 'interrupt']
    assert interrupts[0]['threadId'] == thread
    assert interrupts[0]['turnId'] == interrupt['provider_turn_id']
    assert ws.status()['state'] == 'running'
    time.sleep(0.3)
    assert [t['status'] for t in ws.fake_turns()] == ['inProgress']
    before_spawns = len(ws.spawns())
    pending = ws.effort('request', 'xhigh', '--reason', 'owner next phase')
    assert pending['pending_next_turn']['effort'] == 'xhigh'
    assert len(ws.spawns()) == before_spawns  # effort control: zero calls
    blocked = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('too soon\n'), '--request-id', 'r2',
                       '--turn-wait', '5', '--json'])
    assert 'not open for a next turn' in blocked  # provider truth: inProgress
    # Replay of the accepted request never waits, interrupts or resends.
    before_interrupts = len(ws.requests('turn/interrupt'))
    replay, replay_code = ws.run_exit('r1', 'long substantive planning turn\n')
    assert replay['status'] == 'accepted' and replay_code == 6
    assert replay['wait']['outcome'] == 'replay_not_waited'
    assert len(ws.requests('turn/interrupt')) == before_interrupts
    # recover without --interrupt: provider still reports inProgress.
    rec, rec_code = ws.recover()
    assert rec_code == 6 and rec['outcome'] == 'still_in_progress'
    assert rec['provider_status_before'] == 'inProgress'
    assert rec['interrupt'] is None and rec['turn_starts'] == 0
    # recover --interrupt with an acknowledgement but no terminal event.
    rec, rec_code = ws.recover('--interrupt')
    assert rec_code == 6 and rec['outcome'] == 'interrupt_unconfirmed'
    assert rec['interrupt']['acknowledged'] is True
    assert rec['interrupt']['terminal_observed'] is False
    # recover --interrupt with a typed interrupt rejection.
    ws.set_behavior('ok', interrupt='reject')
    rec, rec_code = ws.recover('--interrupt')
    assert rec_code == 6 and rec['outcome'] == 'interrupt_unconfirmed'
    assert rec['interrupt']['error'].startswith('rejected:')
    assert 'fake interrupt rejection' in rec['interrupt']['error']
    assert ws.status()['state'] == 'running'
    # recover --interrupt with a real terminal interrupted event.
    ws.set_behavior('ok', interrupt='ok')
    rec, rec_code = ws.recover('--interrupt')
    assert rec_code == 0 and rec['outcome'] == 'reconciled'
    assert rec['turn_status'] == 'interrupted'
    assert rec['interrupt']['terminal_observed'] is True
    view = ws.status()
    assert view['state'] == 'terminal'
    assert view['last_turn']['status'] == 'interrupted'
    assert view['thread_id'] == thread  # same thread, no context reset
    assert len(ws.turn_starts()) == 1  # recover never started a turn
    assert 'no active turn to recover' in refuses(
        ['--project', str(ws.root), 'recover', '--json'])
    applied = ws.run('r2', 'next phase with the requested effort\n')
    assert applied['effort'] == 'xhigh' and applied['source'] == 'pending'
    assert applied['turn_completed'] is True
    back = ws.run('r3', 'routine coordination again\n')
    assert back['effort'] == 'low' and back['source'] == 'auto'
    print('ok deadline interrupt keeps Unknown without a terminal; explicit '
          'same-thread recover', flush=True)

    # 4z. Owner replacement is fail-closed (V10 item 5), checked before any
    #     new owned process: a stopped owner with a PROVEN unresolved turn
    #     must be recovered on the same thread first; unreadable or unknown
    #     owner state is refused, never reset or replaced.
    ws = Workspace(base)
    old_view = ws.start()
    old_sid = old_view['session_id']
    owner_path = ws.root / 'coord' / 'lead-effort' / 'owner.json'
    ws.set_behavior('hold', interrupt='silent')
    held, held_code = ws.run_exit('r1', 'long turn then stop\n',
                                  '--turn-wait', '1', '--interrupt-drain', '1')
    assert held_code == 6 and held['delivery'] == 'unknown', held
    ws.stop()
    owner_bytes = owner_path.read_bytes()
    before_spawns = len(ws.spawns())
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('replacement goal\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary', str(ws.binary),
                   '--json'])
    assert 'proven unresolved active turn' in msg, msg
    assert ('recover --session %s --interrupt' % old_sid) in msg, msg
    assert len(ws.spawns()) == before_spawns  # refused before any process
    assert owner_path.read_bytes() == owner_bytes
    # Same-thread recovery works on the stopped owner, then start proceeds.
    ws.set_behavior('ok', interrupt='ok')
    rec, rec_code = ws.recover('--interrupt')
    assert rec_code == 0 and rec['outcome'] == 'reconciled', rec
    assert rec['thread_id'] == old_view['thread_id']
    new_view = ws.start()
    assert new_view['session_id'] != old_sid
    hist, _, hist_code = invoke(['--project', str(ws.root), 'status',
                                 '--session', old_sid, '--json'])
    assert hist_code == 0 and hist['historical'] is True
    assert hist['last_turn']['status'] == 'interrupted'
    # Unreadable current-owner state: refused, zero spawns, nothing reset.
    ws.stop()
    state_file = ws.root / 'coord' / 'lead-effort' / (new_view['session_id']
                                                      + '.json')
    assert state_file.is_file()
    fd = os.open(state_file, os.O_WRONLY | os.O_TRUNC)
    os.write(fd, b'{not json')
    os.close(fd)
    owner_bytes = owner_path.read_bytes()
    before_spawns = len(ws.spawns())
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('replace corrupt owner\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary', str(ws.binary),
                   '--json'])
    assert 'unreadable or unknown control state' in msg, msg
    assert len(ws.spawns()) == before_spawns
    assert owner_path.read_bytes() == owner_bytes
    # Unknown owner (record points to a session with no state): refused.
    owner_path.write_text(json.dumps({'session_id': 'lead-' + '1' * 24})
                          + '\n')
    os.chmod(owner_path, 0o600)
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('replace unknown owner\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary', str(ws.binary),
                   '--json'])
    assert 'unreadable or unknown control state' in msg, msg
    assert len(ws.spawns()) == before_spawns
    print('ok owner replacement refuses proven unresolved turns and '
          'unreadable/unknown owners before any process', flush=True)

    # 4b. Deadline interrupt WITH a terminal event inside the run itself:
    #     interrupted (exit 5), session usable; a typed interrupt rejection
    #     keeps Unknown (exit 6).
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('hold', interrupt='ok')
    done, done_code = ws.run_exit('r1', 'turn interrupted at deadline\n',
                                  '--turn-wait', '1')
    assert done_code == 5 and done['delivery'] == 'interrupted'
    assert done['interrupt']['acknowledged'] is True
    assert done['interrupt']['terminal_observed'] is True
    assert done['interrupt']['drain_outcome'] == 'terminal'
    assert ws.status()['last_turn']['status'] == 'interrupted'
    ws.set_behavior('hold', interrupt='reject')
    bad, bad_code = ws.run_exit('r2', 'interrupt rejected at deadline\n',
                                '--turn-wait', '1', '--interrupt-drain', '1')
    assert bad_code == 6 and bad['delivery'] == 'unknown'
    assert bad['interrupt']['acknowledged'] is False
    assert 'fake interrupt rejection' in bad['interrupt']['error']
    assert bad['interrupt']['provider_status'] == 'inProgress'
    assert ws.status()['state'] == 'running'
    # The provider's own thread state may later report the abandoned turn
    # as terminal: recover records it with no interrupt and no turn start.
    ws.set_behavior('ok', read='abandoned-interrupted')
    before_interrupts = len(ws.requests('turn/interrupt'))
    rec, rec_code = ws.recover()
    assert rec_code == 0 and rec['outcome'] == 'reconciled'
    assert rec['turn_status'] == 'interrupted'
    assert len(ws.requests('turn/interrupt')) == before_interrupts
    assert len(ws.turn_starts()) == 2
    print('ok deadline interrupt with terminal, rejection and provider-read '
          'recovery', flush=True)

    # 4c. A long turn completes inside the wait because the process is
    #     kept alive (no premature kill); --turn-wait 0 refuses before any
    #     owned process or intent exists.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('slow-turn')
    started = time.monotonic()
    slow, slow_code = ws.run_exit('r1', 'slow but healthy turn\n')
    assert time.monotonic() - started >= 1.4
    assert slow_code == 0 and slow['delivery'] == 'completed'
    assert slow['wait']['outcome'] == 'terminal' and slow['interrupt'] is None
    assert ws.requests('turn/interrupt') == []
    before_spawns = len(ws.spawns())
    before_requests = ws.status()['requests_recorded']
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('async please\n'), '--request-id', 'r2',
                       '--turn-wait', '0', '--json'])
    assert '--turn-wait 0 is refused before launch' in message
    assert len(ws.spawns()) == before_spawns
    assert ws.status()['requests_recorded'] == before_requests
    print('ok long turn kept alive to completion; zero wait refused before '
          'launch', flush=True)

    # 4d. recover refuses an unacknowledged turn (no proven provider id).
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('bad-ack')
    ws.run_exit('r1', 'unacknowledged turn\n')
    before_spawns = len(ws.spawns())
    assert 'no proven provider turn id' in refuses(
        ['--project', str(ws.root), 'recover', '--interrupt', '--json'])
    assert len(ws.spawns()) == before_spawns
    print('ok recover refuses an unproven turn before any process', flush=True)

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

    # 5a. Project STOP before start and after start / before run.
    ws = Workspace(base)
    ws.set_stop(True)
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('stop goal\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary',
                   str(ws.binary), '--json'])
    assert 'project STOP is active' in msg
    assert len(ws.spawns()) == 0
    ws.set_stop(False)
    ws.start()
    assert len(ws.spawns()) == 1
    ws.set_stop(True)
    msg = refuses(['--project', str(ws.root), 'run', '--file',
                   ws.input('blocked by project stop\n'), '--request-id', 'r-stop',
                   '--turn-wait', '5', '--json'])
    assert 'project STOP is active' in msg
    assert len(ws.spawns()) == 1  # zero new spawns
    assert ws.turn_starts() == []

    # 5b. Read-only status and pending controls are zero-provider and allowed in STOP.
    before_spawns = len(ws.spawns())
    status_view = ws.status()
    assert status_view['session_id'] == ws._sid
    assert 'records' in ws.output()
    assert ws.effort('show')['mode'] == 'auto'
    pending_req = ws.effort('request', 'xhigh', '--reason', 'stop plan')
    assert pending_req['pending_next_turn']['effort'] == 'xhigh'
    w_reg = ws.worker('register', 'w-stop')
    assert w_reg['worker'] == 'w-stop'
    w_wait = ws.worker('wait')
    assert w_wait['waiting'] is True
    assert len(ws.spawns()) == before_spawns  # zero provider calls in STOP
    ws.set_stop(False)
    unstopped_run = ws.run('r1', 'after stop cleared\n')
    assert unstopped_run['status'] == 'accepted'

    # 5c. Real off holds (project-level and installed) with duration expiry.
    ws = Workspace(base)
    ws.set_off('codex')
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('off goal\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary',
                   str(ws.binary), '--json'])
    assert 'off: hold is active' in msg
    assert len(ws.spawns()) == 0
    # Expired off hold passes admission
    ws.set_off('codex', duration=-10)
    ws.start()
    assert len(ws.spawns()) == 1
    # Off hold set before run refuses before child
    ws.set_off('codex')
    msg = refuses(['--project', str(ws.root), 'run', '--file',
                   ws.input('off turn\n'), '--request-id', 'r-off',
                   '--turn-wait', '5', '--json'])
    assert 'off: hold is active' in msg
    assert len(ws.spawns()) == 1
    ws.clear_off('codex')
    off_run = ws.run('r1', 'resumed after off cleared\n')
    assert off_run['status'] == 'accepted'

    # 5d. Absent and mismatched lead registration.
    ws = Workspace(base)
    ws.set_policy({'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
                   'lead_agent': None, 'accounts': {}})
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('no lead\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary',
                   str(ws.binary), '--json'])
    assert 'no lead registered' in msg
    assert len(ws.spawns()) == 0
    ws.set_policy({'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
                   'lead_agent': 'opencode', 'accounts': {}})
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('wrong lead\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary',
                   str(ws.binary), '--json'])
    assert 'registered lead mismatch' in msg
    assert len(ws.spawns()) == 0

    # 5e. Shared-account group full / contention.
    ws = Workspace(base)
    with ws.occupy_slot('codex-shared', 'contending-w1'):
        msg = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('busy slot\n'), '--model', MODEL,
                       '--transport', 'owned', '--codex-binary',
                       str(ws.binary), '--json'])
        assert 'at capacity' in msg
        assert len(ws.spawns()) == 0
    ws.start()
    with ws.occupy_slot('codex-shared', 'contending-w2'):
        msg = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('busy turn\n'), '--request-id', 'r-busy',
                       '--turn-wait', '5', '--json'])
        assert 'at capacity' in msg
        assert len(ws.spawns()) == 1
    slot_cleared = ws.run('r1', 'turn after slot clear\n')
    assert slot_cleared['status'] == 'accepted'

    # 5f. Mapped aliases and arbitrary budget label refusal.
    ws = Workspace(base)
    ws.set_policy({'schema_version': 1, 'mode': 'yolo', 'tier': 'low',
                   'lead_agent': 'codex', 'accounts': {'codex': 'antigravity'}})
    msg = refuses(['--project', str(ws.root), 'start', '--goal',
                   ws.input('arbitrary budget\n'), '--model', MODEL,
                   '--transport', 'owned', '--codex-binary',
                   str(ws.binary), '--budget-label', 'made-up-group', '--json'])
    assert 'budget label mismatch' in msg
    assert len(ws.spawns()) == 0
    # Unrelated group busy does not block antigravity
    with ws.occupy_slot('unrelated', 'w-unrelated'):
        alias_start = ws.start()
        assert alias_start['budget_label'] == 'antigravity'
    with ws.occupy_slot('antigravity', 'w-antigravity'):
        msg = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('anti busy\n'), '--request-id', 'r-anti',
                       '--turn-wait', '5', '--json'])
        assert 'at capacity' in msg
        assert len(ws.spawns()) == 1
    anti_ok = ws.run('r1', 'anti clear turn\n')
    assert anti_ok['status'] == 'accepted'

    # 5g. Concurrent starts and setter guard against active owned invocations.
    ws = Workspace(base)
    with ws.occupy_lease():
        msg = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('concurrent start\n'), '--model', MODEL,
                       '--transport', 'owned', '--codex-binary',
                       str(ws.binary), '--json'])
        assert 'active owned lead session already running' in msg
        assert len(ws.spawns()) == 0
    ws.start()
    with ws.occupy_lease():
        msg = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('concurrent run\n'), '--request-id', 'r-conc',
                       '--turn-wait', '5', '--json'])
        assert 'active owned lead session already running' in msg
        assert len(ws.spawns()) == 1
        # Setter guard also refuses while lease is held
        guard_refused = False
        try:
            with lp.lead_session_guard(ws.root):
                pass
        except lp.Refusal as exc:
            assert 'active owned lead session is running' in str(exc)
            guard_refused = True
        assert guard_refused is True

    # 5h. Correct real lead counted once under low tier.
    ws = Workspace(base)
    low_start = ws.start()
    assert low_start['baseline_effort'] == 'xhigh'
    low_run = ws.run('r1', 'low tier lead turn\n')
    assert low_run['status'] == 'accepted'
    assert low_run['turn_completed'] is True
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
    #    new thread; a new turn refuses at the core with zero turn starts;
    #    uncertain work exits nonzero.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('bad-ack')
    uncertain, uncertain_code = ws.run_exit(
        'r1', 'turn with a malformed acknowledgement\n')
    assert uncertain['status'] == 'uncertain'
    assert uncertain['delivery'] == 'uncertain'
    assert uncertain_code == 3
    assert ws.status()['state'] == 'outcome_unknown'
    before_starts = len(ws.turn_starts())
    replay, replay_code = ws.run_exit(
        'r1', 'turn with a malformed acknowledgement\n')
    assert replay['status'] == 'uncertain'
    assert replay_code == 3
    assert len(ws.turn_starts()) == before_starts  # no resend
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('a fresh turn\n'), '--request-id', 'r2',
                       '--turn-wait', '5', '--json'])
    assert 'not open for a next turn' in message
    assert len(ws.turn_starts()) == before_starts
    print('ok malformed ack stays uncertain with no replay or resend', flush=True)

    # 9. Typed provider rejection is preserved; the session continues;
    #    rejected work exits nonzero with an explicit delivery state.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('reject-turn')
    rejected, rejected_code = ws.run_exit('r1', 'turn the provider rejects\n')
    assert rejected['status'] == 'rejected'
    assert rejected['delivery'] == 'rejected'
    assert rejected_code == 2
    assert ws.status()['state'] == 'idle'
    ws.set_behavior('ok')
    accepted = ws.run('r2', 'a later turn after rejection\n')
    assert accepted['status'] == 'accepted'
    assert ws.status()['last_turn']['status'] == 'completed'
    print('ok typed rejection preserved; session continues correctly', flush=True)

    # 9b. A provably rejected turn restores ONLY its own consumption: the
    #     review wakeup and pending XHIGH survive; the attempted decision
    #     stays as evidence with its rejected outcome.
    ws = Workspace(base)
    ws.start()
    ws.worker('register', 'w1')
    ws.worker('terminal', 'w1')
    ws.effort('request', 'xhigh', '--reason', 'owner review')
    ws.set_behavior('reject-turn')
    rejected, rejected_code = ws.run_exit('r1', 'review rejected\n')
    assert rejected_code == 2 and rejected['delivery'] == 'rejected'
    assert rejected['kind'] == 'review' and rejected['effort'] == 'xhigh'
    assert rejected['source'] == 'pending'
    assert rejected['restored']['wakeup'] == 'w1'
    assert rejected['restored']['pending'] == {'effort': 'xhigh',
                                               'reason': 'owner review'}
    state = json.loads((ws.root / 'coord' / 'lead-effort'
                        / (ws.sid + '.json')).read_text())
    assert state['policy']['pending'] == {'effort': 'xhigh',
                                          'reason': 'owner review'}
    assert [w['worker'] for w in state['policy']['wakeups']] == ['w1']
    assert state['policy']['wakeups_consumed'] == 0
    view = ws.status()
    assert [(d['turn_id'], d['outcome']) for d in view['decisions']] == [
        (rejected['turn_id'], 'rejected')]
    ws.set_behavior('ok')
    review = ws.run('r2', 'review again after rejection\n')
    assert review['kind'] == 'review' and review['effort'] == 'xhigh'
    assert review['source'] == 'pending' and review['restored'] is None
    routine = ws.run('r3', 'routine coordination\n')
    assert routine['kind'] == 'coordination' and routine['effort'] == 'low'
    print('ok rejected turn restores its own wakeup and pending effort',
          flush=True)

    # 9c. Newer concurrent controls written during a slow rejected turn
    #     are kept (not overwritten by the restored consumption).
    ws = Workspace(base)
    ws.start()
    ws.worker('register', 'w-pre')
    ws.worker('terminal', 'w-pre')
    ws.effort('request', 'xhigh', '--reason', 'before')
    ws.set_behavior('slow-reject')
    run_argv = [sys.executable, str(SOURCE / 'tools' / 'lead-session.py'),
                '--project', str(ws.root), 'run', '--file',
                ws.input('slow rejection\n'), '--request-id', 'r1',
                '--turn-wait', '5', '--json']
    proc = subprocess.Popen(run_argv, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while not ws.turn_starts():
        assert time.monotonic() < deadline, 'fake never received turn/start'
        time.sleep(0.05)
    ws.effort('request', 'low', '--reason', 'newer')
    ws.worker('register', 'w-during')
    ws.worker('terminal', 'w-during')
    stdout, stderr = proc.communicate(timeout=60)
    assert proc.returncode == 2, (stdout, stderr)
    payload = json.loads(stdout[stdout.index('{'):])
    assert payload['delivery'] == 'rejected' and payload['restored']
    state = json.loads((ws.root / 'coord' / 'lead-effort'
                        / (ws.sid + '.json')).read_text())
    assert state['policy']['pending'] == {'effort': 'low', 'reason': 'newer'}
    assert [w['worker'] for w in state['policy']['wakeups']] == [
        'w-pre', 'w-during']
    assert state['policy']['wakeups_consumed'] == 0
    print('ok newer concurrent controls survive a restored rejection',
          flush=True)

    # 9d. Local mapping-bound exhaustion is known non-delivery: rejected
    #     (never uncertain), zero turn starts, consumption restored, the
    #     session is not poisoned and the limit is explained.
    ws = Workspace(base)
    ws.start('--max-mappings', '1')
    first = ws.run('r1', 'only mapped turn\n')
    assert first['delivery'] == 'completed'
    ws.effort('request', 'xhigh', '--reason', 'next')
    before_starts = len(ws.turn_starts())
    full, full_code = ws.run_exit('r2', 'beyond the mapping bound\n')
    assert full_code == 2 and full['status'] == 'rejected'
    assert full['delivery'] == 'rejected'
    assert 'mapping bound reached' in full['note']
    assert 'start a new one' in full['note']
    assert full['restored']['pending']['effort'] == 'xhigh'
    assert len(ws.turn_starts()) == before_starts
    view = ws.status()
    assert view['state'] != 'outcome_unknown'
    assert view['effort']['pending_next_turn']['effort'] == 'xhigh'
    replay = ws.run('r1', 'only mapped turn\n')
    assert replay['status'] == 'accepted'
    again, again_code = ws.run_exit('r3', 'still beyond the bound\n')
    assert again_code == 2 and again['status'] == 'rejected'
    print('ok mapping exhaustion is a controlled non-delivery, not uncertain',
          flush=True)

    # 10. Owned process crash mid-send: untyped failure stays uncertain;
    #     replay returns the recorded result; new turns refuse with zero
    #     turn starts. The native exit is reported explicitly with a
    #     bounded private stderr tail (no discarded diagnostics).
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('crash')
    crashed, crashed_code = ws.run_exit(
        'r1', 'turn that crashes the owned process\n')
    assert crashed['status'] == 'uncertain'
    assert crashed['delivery'] == 'uncertain'
    assert crashed_code == 3
    assert crashed['provider_exited'] is True
    assert 'fake owned crash diagnostic' in crashed['stderr_tail']
    assert ws.status()['state'] == 'outcome_unknown'
    before_starts = len(ws.turn_starts())
    replay, replay_code = ws.run_exit(
        'r1', 'turn that crashes the owned process\n')
    assert replay['status'] == 'uncertain'
    assert replay_code == 3
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

    # 12. Original failures are retained; the session stays usable; a
    #     failed turn exits nonzero with its actual terminal status.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('fail-turn')
    failed, failed_code = ws.run_exit('r1', 'turn that fails\n')
    assert failed['status'] == 'accepted'
    assert failed['turn_completed'] is False
    assert failed['turn_status'] == 'failed'
    assert failed['delivery'] == 'failed'
    assert failed_code == 4
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

    # 14. Real overlapping CLI processes: control commands issued while a
    #     delayed turn/start RPC is in flight (after the turn decision,
    #     before the run's persistence) survive — pending effort, worker
    #     terminal wakeup and STOP are never overwritten by the stale
    #     pre-turn snapshot, and the run's own wakeup consumption is
    #     merged on top instead of clobbering the concurrent queue.
    ws = Workspace(base)
    ws.start()
    ws.worker('register', 'w-pre')
    ws.worker('terminal', 'w-pre')  # one review wakeup pending at run load
    ws.set_behavior('slow-ack')
    run_argv = [sys.executable, str(SOURCE / 'tools' / 'lead-session.py'),
                '--project', str(ws.root), 'run', '--file',
                ws.input('slow acknowledgement turn\n'),
                '--request-id', 'r1', '--turn-wait', '5', '--json']
    proc = subprocess.Popen(run_argv, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while not ws.turn_starts():
        assert time.monotonic() < deadline, 'fake never received turn/start'
        time.sleep(0.05)
    # The run process is now mid-RPC, past its turn decision (which
    # consumed the w-pre wakeup as a review turn): concurrent control
    # commands must survive its persistence.
    ws.effort('request', 'xhigh', '--reason', 'during the active turn')
    ws.worker('register', 'w-during')
    ws.worker('terminal', 'w-during')
    ws.stop()
    stdout, stderr = proc.communicate(timeout=60)
    assert stderr == '', stderr
    assert proc.returncode == 0  # slow-ack completes the turn
    payload = json.loads(stdout[stdout.index('{'):])
    assert payload['delivery'] == 'completed'
    assert payload['kind'] == 'review' and payload['effort'] == 'xhigh'
    state = json.loads((ws.root / 'coord' / 'lead-effort'
                        / (ws.sid + '.json')).read_text())
    assert state['policy']['pending'] == {
        'effort': 'xhigh', 'reason': 'during the active turn'}
    assert state['stopped'] is True
    assert state['workers']['w-pre']['state'] == 'terminal'
    assert state['workers']['w-during']['state'] == 'terminal'
    assert [w['worker'] for w in state['policy']['wakeups']] == ['w-during']
    assert state['policy']['wakeups_consumed'] == 1
    assert state['policy']['decisions'][0]['kind'] == 'review'
    message = refuses(['--project', str(ws.root), 'run', '--file',
                       ws.input('blocked by stop\n'), '--request-id', 'r2',
                       '--turn-wait', '5', '--json'])
    assert 'stopped' in message
    # The surviving pending request applies exactly once, next turn.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('slow-ack')
    run_argv = [sys.executable, str(SOURCE / 'tools' / 'lead-session.py'),
                '--project', str(ws.root), 'run', '--file',
                ws.input('slow acknowledgement turn\n'),
                '--request-id', 'r1', '--turn-wait', '5', '--json']
    proc = subprocess.Popen(run_argv, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, text=True)
    deadline = time.monotonic() + 10
    while not ws.turn_starts():
        assert time.monotonic() < deadline, 'fake never received turn/start'
        time.sleep(0.05)
    ws.effort('request', 'xhigh', '--reason', 'during the active turn')
    stdout, stderr = proc.communicate(timeout=60)
    assert stderr == '', stderr
    assert proc.returncode == 0
    payload = json.loads(stdout[stdout.index('{'):])
    assert payload['effort'] == 'low'  # this turn's decision already made
    ws.set_behavior('ok')
    applied = ws.run('r2', 'next turn with the requested effort\n')
    assert applied['effort'] == 'xhigh' and applied['source'] == 'pending'
    assert applied['delivery'] == 'completed'
    back = ws.run('r3', 'routine coordination again\n')
    assert back['effort'] == 'low' and back['source'] == 'auto'
    print('ok concurrent controls survive a real overlapping run process',
          flush=True)

    # 15. A typed RPC rejection on initialize is a controlled refusal
    #     preserving method, code and reason — never a raw traceback.
    ws = Workspace(base)
    ws.set_behavior('reject-init')
    message = refuses(['--project', str(ws.root), 'start', '--goal',
                       ws.input('goal\n'), '--model', MODEL,
                       '--transport', 'owned', '--codex-binary',
                       str(ws.binary), '--json'])
    assert 'owned app-server rejected initialize' in message
    assert 'code -32000' in message
    assert 'fake initialize rejection' in message
    assert len(ws.spawns()) == 1
    assert not (ws.root / 'coord' / 'lead-effort'
                / 'owner.json').exists()
    print('ok non-turn RPC rejection is controlled with method, code, '
          'reason', flush=True)

    # 16. Child death during the turn wait: the wait stops promptly (no
    #     busy loop until the deadline), the outcome stays pending with
    #     the native exit and bounded stderr tail reported, and no
    #     terminal is ever inferred.
    ws = Workspace(base)
    ws.start()
    ws.set_behavior('die-waiting')
    started = time.monotonic()
    died, died_code = ws.run_exit('r1', 'turn whose process dies waiting\n')
    elapsed = time.monotonic() - started
    assert died['status'] == 'accepted'
    assert died['delivery'] == 'unknown' and died['turn_status'] is None
    assert died['wait']['outcome'] == 'provider_exited'
    assert died['interrupt'] is None
    assert died['provider_exited'] is True
    assert 'fake owned wait death diagnostic' in died['stderr_tail']
    assert died_code == 6
    assert elapsed < 4.0, elapsed  # prompt stop, not the 5s deadline spin
    assert ws.status()['state'] == 'running'  # no inferred terminal
    print('ok child death in the wait loop stops promptly without '
          'inferring success', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='lead-owned-') as base:
        run_suite(base)
    print('all owned lead-session transport checks passed')


if __name__ == '__main__':
    main()
