#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Regression tests for lead-session effort-first display.

Contract: docs/development/contracts/0531-EFFORT-PRESENTATION-V8.md, with the
bounded V10 truth corrections (0531-FINAL-REVIEW-CORRECTIONS-V10.md).

Validates:
- Concrete requested LOW/XHIGH is primary; adaptive/AUTO policy is secondary.
- Active LOW/XHIGH matches the durable decision for the exact current turn.
- A queued opposite next-turn effort stays next-only and never overwrites active turn.
- Pre-first-turn displays 'not started' and never advertises AUTO as effort.
- Idle and waiting states display 'no active turn' and truthful last requested/attempt.
- Provider rejection does not claim effort was used (disclosed as rejected attempt).
- Uncertain turns retain attempted effort with delivery uncertain and effective Unknown.
- Historical views on stale sessions are clearly labelled.
- Read-only status and effort show make zero provider/RPC calls (counted in
  the exact <session>.rpclog.jsonl the fake transport writes).
- An outcome_unknown attempt is marked delivery uncertain, never shown as an
  ordinary confirmed active turn.
- `waiting` clears once every registered worker is terminal and a review turn
  completes; a real concurrent wait on a non-terminal worker stays visible.

Fixture note: the product refuses group/other-accessible state files
(fail-closed). Every fixture file the product reads as owned state is
therefore written 0600 explicitly, independent of the caller's umask. The
original Google native verification failed line `held_code == 6` because a
umask-022 environment produced a 0644 behavior sidecar (the run then exited 3,
uncertain); a umask-0077 shell passed. See test_umask_independent_fixture.
- Backwards compatibility of existing JSON fields alongside structured display.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
CLI = ROOT / 'tools' / 'lead-session.py'
MODEL = 'fake-lead-model'
THREAD = 'thread-fake-00000000'


def invoke(argv):
    proc = subprocess.run([sys.executable, '-B', str(CLI)] + list(argv),
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True)
    return proc.stdout, proc.stderr, proc.returncode


def call(argv):
    out, err, code = invoke(argv)
    if code != 0:
        raise AssertionError('command failed (%d): %s\n%s' % (code, argv, err))
    if '--json' in argv:
        return json.loads(out), out
    return None, out


class Workspace:
    counter = 0

    def __init__(self, base):
        Workspace.counter += 1
        self.root = Path(base) / ('effort-display-' + str(Workspace.counter))
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
        goal = self.input('owner goal: deliver effort presentation\n')
        payload = call(['--project', str(self.root), 'start',
                        '--goal', goal, '--model', MODEL,
                        '--transport', 'fake', '--json'] + list(extra))[0]
        self._sid = payload['session_id']
        return payload

    def start_human(self, *extra):
        goal = self.input('owner goal: deliver effort presentation\n')
        _, out = call(['--project', str(self.root), 'start',
                       '--goal', goal, '--model', MODEL,
                       '--transport', 'fake'] + list(extra))
        return out.strip()

    def run(self, request_id, text, *extra):
        path = self.input(text)
        return call(['--project', str(self.root), 'run', '--file', path,
                     '--request-id', request_id, '--json'] + list(extra))[0]

    def run_exit(self, request_id, text, *extra):
        path = self.input(text)
        out, err, code = invoke(['--project', str(self.root), 'run',
                                '--file', path, '--request-id', request_id,
                                '--json'] + list(extra))
        payload = json.loads(out) if out.strip() else None
        self.last_run = (code, out, err)
        return payload, code

    def expect_run(self, code, expected):
        """Actionable assertion: report the actual rc, stdout and stderr."""
        actual, out, err = self.last_run
        assert actual == expected, (
            'run exit %r, expected %r\nstdout:\n%s\nstderr:\n%s'
            % (actual, expected, out, err))

    def effort(self, *args):
        return call(['--project', str(self.root), 'effort']
                    + list(args) + ['--json'])[0]

    def effort_human(self, *args):
        _, out = call(['--project', str(self.root), 'effort'] + list(args))
        return out.strip()

    def status(self, *extra):
        return call(['--project', str(self.root), 'status', '--json'] + list(extra))[0]

    def status_human(self, *extra):
        _, out = call(['--project', str(self.root), 'status'] + list(extra))
        return out.strip()

    def worker(self, *args):
        return call(['--project', str(self.root), 'worker']
                    + list(args) + ['--json'])[0]

    def stop(self):
        return call(['--project', str(self.root), 'stop', '--json'])[0]

    def rpc_log(self):
        # The exact log FakeLeadRPC writes: coord/lead-effort/<sid>.rpclog.jsonl
        log_path = (self.root / 'coord' / 'lead-effort'
                    / (self.sid + '.rpclog.jsonl'))
        assert log_path.is_file(), 'fake rpc log missing: %s' % log_path
        records = []
        for line in log_path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records

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
        path.parent.mkdir(mode=0o700, exist_ok=True)
        # Owned state: always 0600, whatever the caller's umask is.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(json.dumps(doc) + '\n')
        os.chmod(path, 0o600)


def test_suite():
    with tempfile.TemporaryDirectory(prefix='unio-lead-effort-disp-') as base:
        # 1. Pre-first-turn: 'not started', zero provider calls, no AUTO effort headline
        ws = Workspace(base)
        start_msg = ws.start_human()
        # start queries supported efforts once: real fixture traffic.
        start_log = ws.rpc_log()
        assert [rec['method'] for rec in start_log] == ['model/list'], start_log
        rpc_before = len(start_log)
        assert 'effort not started' in start_msg
        assert 'policy adaptive' in start_msg
        assert 'effort auto' not in start_msg.lower()

        # Status human
        st_human = ws.status_human()
        assert 'effort not started' in st_human
        assert 'policy adaptive' in st_human
        assert 'effort mode auto' not in st_human

        # Effort show human
        eff_human = ws.effort_human('show')
        assert eff_human.startswith('requested effort: not started')
        assert 'policy adaptive' in eff_human
        assert 'effort mode auto' not in eff_human

        # Status JSON structured view
        st_json = ws.status()
        assert st_json['effort']['mode'] == 'auto'  # legacy machine field preserved
        assert st_json['effective'] == 'Unknown'
        disp = st_json['effort_display']
        assert disp['active_status'] == 'not started'
        assert disp['active_effort'] is None
        assert disp['current_request']['active'] is False
        assert disp['current_request']['effort'] is None
        assert disp['policy_mode'] == 'adaptive'
        assert disp['last_attempt'] is None
        assert disp['effective'] == 'Unknown'

        # Read-only status & effort show made zero provider calls
        assert len(ws.rpc_log()) == rpc_before, ws.rpc_log()
        print('ok pre-first-turn displays not started with zero provider calls', flush=True)

        # 2. Active LOW turn
        ws.set_behavior(behavior='hold')
        held_low, held_code = ws.run_exit('r1', 'routine coordination turn\n',
                                          '--kind', 'coordination')
        ws.expect_run(held_code, 6)
        assert held_low['turn_completed'] is False

        st_low = ws.status()
        assert st_low['state'] == 'running'
        disp_low = st_low['effort_display']
        assert disp_low['current_request']['active'] is True
        assert disp_low['active_effort'] == 'low'
        assert disp_low['current_request']['effort'] == 'low'
        assert disp_low['current_request']['kind'] == 'coordination'
        # Acknowledged running turn: confirmed accepted, not uncertain.
        assert disp_low['current_request']['delivery'] == 'accepted'

        st_low_h = ws.status_human()
        assert 'effort low (policy adaptive)' in st_low_h
        assert 'uncertain' not in st_low_h
        eff_low_h = ws.effort_human('show')
        assert 'requested effort: low' in eff_low_h
        assert 'uncertain' not in eff_low_h
        assert 'kind coordination' in eff_low_h

        # 3. Queued opposite next-turn effort (XHIGH) stays next-only
        req_msg = ws.effort_human('request', 'xhigh', '--reason', 'substantive next phase')
        assert 'requested next-turn effort: xhigh' in req_msg
        assert 'applied after active turn ends' in req_msg

        # Status during the active turn: active effort is STILL LOW, next is XHIGH
        st_queued = ws.status()
        disp_q = st_queued['effort_display']
        assert disp_q['active_effort'] == 'low'  # NOT overwritten!
        assert disp_q['pending_next_turn']['effort'] == 'xhigh'

        st_q_h = ws.status_human()
        assert 'effort low (policy adaptive, pending next: xhigh)' in st_q_h

        eff_q_h = ws.effort_human('show')
        assert 'requested effort: low' in eff_q_h
        assert 'pending next: xhigh' in eff_q_h

        # Release hold on r1
        ws.set_behavior(behavior='ok', release_held=True)
        r1_done = ws.run('r1', 'routine coordination turn\n')
        assert r1_done['turn_completed'] is True
        assert r1_done['effort'] == 'low'
        print('ok active LOW turn and opposite pending next XHIGH are distinct', flush=True)

        # 4. Consumed queued next-turn effort (XHIGH active)
        ws.set_behavior(behavior='hold')
        held_high, high_code = ws.run_exit('r2', 'substantive turn using queued request\n')
        ws.expect_run(high_code, 6)
        st_high = ws.status()
        assert st_high['state'] == 'running'
        disp_high = st_high['effort_display']
        assert disp_high['active_effort'] == 'xhigh'
        assert disp_high['current_request']['effort'] == 'xhigh'
        assert disp_high['pending_next_turn'] is None  # consumed

        st_high_h = ws.status_human()
        assert 'effort xhigh (policy adaptive)' in st_high_h
        eff_high_h = ws.effort_human('show')
        assert 'requested effort: xhigh' in eff_high_h

        # Release hold on r2
        ws.set_behavior(behavior='ok', release_held=True)
        r2_done = ws.run('r2', 'substantive turn using queued request\n')
        assert r2_done['turn_completed'] is True
        assert r2_done['effort'] == 'xhigh'
        print('ok active XHIGH turn derived from exact turn decision', flush=True)

        # 5. Idle and waiting display 'no active turn' and last requested effort
        st_idle = ws.status()
        assert st_idle['state'] in ('idle', 'terminal')
        assert st_idle['turn'] is None
        disp_idle = st_idle['effort_display']
        assert disp_idle['current_request']['active'] is False
        assert disp_idle['active_effort'] is None
        assert disp_idle['last_attempt']['effort'] == 'xhigh'
        assert disp_idle['last_attempt']['status'] == 'completed'

        st_idle_h = ws.status_human()
        assert 'effort no active turn' in st_idle_h
        assert 'last requested: xhigh (completed)' in st_idle_h

        eff_idle_h = ws.effort_human('show')
        assert 'requested effort: no active turn' in eff_idle_h
        assert 'last requested: xhigh (completed)' in eff_idle_h

        # Worker wait
        ws.worker('register', 'w1')
        ws.worker('wait')
        st_wait = ws.status()
        assert st_wait['waiting'] is True
        st_wait_h = ws.status_human()
        assert 'waiting True' in st_wait_h
        assert 'effort no active turn' in st_wait_h
        print('ok idle and waiting show no active turn with last attempt', flush=True)

        # 6. Manual vs adaptive secondary policy
        ws.worker('terminal', 'w1')
        man_msg = ws.effort_human('manual', 'low', '--reason', 'owner override to low')
        assert 'requested effort override: low' in man_msg
        assert 'policy manual; auto suspended' in man_msg

        st_man_h = ws.status_human()
        assert 'policy manual (low)' in st_man_h
        eff_man_h = ws.effort_human('show')
        assert 'policy manual (low)' in eff_man_h

        resume_msg = ws.effort_human('auto', '--reason', 'resume adaptive')
        assert 'effort policy: adaptive' in resume_msg
        assert 'effort auto' not in resume_msg.lower()
        st_res_h = ws.status_human()
        assert 'policy adaptive' in st_res_h
        print('ok manual vs adaptive secondary policy with no AUTO effort headline', flush=True)

        # 7. Rejected attempt: disclosed as rejected, effort not claimed as used
        ws.set_behavior(behavior='reject')
        rej, rej_code = ws.run_exit('r3', 'turn rejected by provider\n')
        ws.expect_run(rej_code, 2)
        assert rej['delivery'] == 'rejected'

        st_rej = ws.status()
        assert st_rej['state'] in ('idle', 'terminal')
        disp_rej = st_rej['effort_display']
        assert disp_rej['current_request']['active'] is False
        assert disp_rej['last_attempt']['effort'] == rej['effort']
        assert disp_rej['last_attempt']['status'] == 'rejected'

        st_rej_h = ws.status_human()
        assert ('last attempt: %s (rejected, not delivered)' % rej['effort']) in st_rej_h
        eff_rej_h = ws.effort_human('show')
        assert ('last attempt: %s (rejected, not delivered)' % rej['effort']) in eff_rej_h
        print('ok provider rejection disclosed truthfully as undelivered attempt', flush=True)

        # 8. Uncertain attempt: preserved evidence, delivery uncertain, effective Unknown
        ws.set_behavior(behavior='raise')
        unc, unc_code = ws.run_exit('r4', 'turn that crashes in flight\n')
        ws.expect_run(unc_code, 3)
        assert unc['status'] == 'uncertain'

        st_unc = ws.status()
        assert st_unc['state'] == 'outcome_unknown'
        disp_unc = st_unc['effort_display']
        assert disp_unc['current_request']['active'] is True
        assert disp_unc['effective'] == 'Unknown'
        # The attempted effort is kept but never shown as an ordinary
        # confirmed active turn.
        assert disp_unc['current_request']['state'] == 'outcome_unknown'
        assert disp_unc['current_request']['delivery'] == 'uncertain'
        assert disp_unc['current_request']['effort'] == unc['effort']
        st_unc_h = ws.status_human()
        assert 'state outcome_unknown' in st_unc_h
        assert 'delivery uncertain, effective Unknown' in st_unc_h
        eff_unc_h = ws.effort_human('show')
        assert eff_unc_h.startswith('requested effort: %s (active turn '
                                    % unc['effort']), eff_unc_h
        assert 'delivery uncertain, effective Unknown' in eff_unc_h, eff_unc_h
        print('ok uncertain attempt preserves evidence with effective Unknown', flush=True)

        # 9. Historical labelling on stale session
        old_sid = ws.sid
        ws.stop()
        new_payload = ws.start()
        new_sid = new_payload['session_id']
        assert new_sid != old_sid

        st_hist_h = ws.status_human('--session', old_sid)
        assert '(historical: not the current workspace owner)' in st_hist_h

        eff_hist_h = ws.effort_human('show', '--session', old_sid)
        assert '(historical: not the current workspace owner)' in eff_hist_h

        st_current_h = ws.status_human()
        assert '(historical' not in st_current_h
        print('ok historical sessions labelled truthfully', flush=True)

        # 10. Existing JSON compatibility verification
        view = ws.status()
        assert 'effort' in view and isinstance(view['effort'], dict)
        assert view['effort']['mode'] == 'auto'
        assert 'ceiling' in view['effort']
        assert 'decisions' in view and isinstance(view['decisions'], list)
        assert 'current_request' in view and isinstance(view['current_request'], dict)
        assert 'effort_display' in view and isinstance(view['effort_display'], dict)
        assert view['effective'] == 'Unknown'
        print('ok backwards-compatible JSON fields and structured display verified', flush=True)


def test_waiting_truth():
    """`waiting` is truthful: a real wait on a non-terminal worker stays,
    and it clears once every worker is terminal and the review completed."""
    with tempfile.TemporaryDirectory(prefix='unio-lead-effort-wait-') as base:
        ws = Workspace(base)
        ws.start()
        ws.worker('register', 'w1')
        ws.worker('register', 'w2')
        ws.worker('wait')
        assert ws.status()['waiting'] is True
        # No turn yet: 'not started' stays the effort truth while waiting.
        assert ws.status()['effort_display']['active_status'] == 'not started'
        ws.worker('terminal', 'w1')
        # One review wakeup queued; w2 still running: still waiting.
        first = ws.run('rw1', 'review w1 outcome\n')
        assert first['turn_completed'] is True and first['kind'] == 'review'
        view = ws.status()
        assert view['waiting'] is True, view['workers']
        assert view['effort_display']['active_status'] == 'waiting'
        assert 'waiting True' in ws.status_human()
        ws.worker('terminal', 'w2')
        # Terminal but its review wakeup is unconsumed: still waiting.
        assert ws.status()['waiting'] is True
        second = ws.run('rw2', 'review w2 outcome\n')
        assert second['turn_completed'] is True and second['kind'] == 'review'
        view = ws.status()
        assert view['waiting'] is False, view
        assert view['effort_display']['active_status'] == 'idle'
        assert view['effort_display']['current_request']['state'] == 'idle'
        human = ws.status_human()
        assert 'waiting False' in human and 'effort no active turn' in human
        assert 'requested effort: no active turn' in ws.effort_human('show')
        # A new real wait is shown again (concurrent waits are preserved).
        ws.worker('register', 'w3')
        ws.worker('wait')
        assert ws.status()['waiting'] is True
        print('ok waiting clears after all workers terminal and review '
              'completes; real waits stay visible', flush=True)


def test_umask_independent_fixture():
    """Regression for the original Google native-verify failure at
    `held_code == 6`: under umask 022 the old fixture wrote a 0644 behavior
    sidecar, the product correctly refused it as unsafe owned state and the
    run exited 3 (uncertain). The fixture now writes 0600 explicitly."""
    old = os.umask(0o022)
    try:
        with tempfile.TemporaryDirectory(prefix='unio-lead-effort-umask-') as base:
            ws = Workspace(base)
            ws.start()
            ws.set_behavior(behavior='hold')
            sidecar = (ws.root / 'coord' / 'lead-effort'
                       / (ws.sid + '.fake.json'))
            assert (sidecar.stat().st_mode & 0o777) == 0o600
            _, code = ws.run_exit('ru1', 'held turn under umask 022\n')
            ws.expect_run(code, 6)
            # Fail-closed product behavior stays: a group/other-readable
            # owned sidecar is refused, so a new turn is never delivered.
            ws2 = Workspace(base)
            ws2.start()
            bad = (ws2.root / 'coord' / 'lead-effort'
                   / (ws2.sid + '.fake.json'))
            bad.write_text('{"behavior": "hold"}\n', encoding='utf-8')
            os.chmod(bad, 0o644)
            _, code = ws2.run_exit('ru2', 'unsafe sidecar\n')
            ws2.expect_run(code, 3)
    finally:
        os.umask(old)
    print('ok fixture is umask-independent; unsafe sidecar still fails closed',
          flush=True)


def main():
    test_suite()
    test_waiting_truth()
    test_umask_independent_fixture()
    print('all lead effort display presentation checks passed')


if __name__ == '__main__':
    main()
