#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Regression tests for lead-session effort-first display (V8 / V8A).

Validates:
- Concrete requested LOW/XHIGH is primary; adaptive/AUTO policy is secondary.
- Active LOW/XHIGH matches the durable decision for the exact current turn.
- A queued opposite next-turn effort stays next-only and never overwrites active turn.
- Pre-first-turn displays 'not started' and never advertises AUTO as effort.
- Idle and waiting states display 'no active turn' and truthful last requested/attempt.
- Provider rejection does not claim effort was used (disclosed as rejected attempt).
- Uncertain turns retain attempted effort with delivery uncertain and effective Unknown.
- Historical views on stale sessions are clearly labelled.
- Read-only status and effort show make zero provider/RPC calls.
- Backwards compatibility of existing JSON fields alongside structured display.
"""
import json
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
        return payload, code

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
        log_path = self.root / 'coord' / 'lead-effort' / 'fake-rpc.jsonl'
        if not log_path.is_file():
            return []
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
        path.write_text(json.dumps(doc) + '\n', encoding='utf-8')


def test_suite():
    with tempfile.TemporaryDirectory(prefix='unio-lead-effort-disp-') as base:
        # 1. Pre-first-turn: 'not started', zero provider calls, no AUTO effort headline
        ws = Workspace(base)
        start_msg = ws.start_human()
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
        assert len(ws.rpc_log()) == 0
        print('ok pre-first-turn displays not started with zero provider calls', flush=True)

        # 2. Active LOW turn
        ws.set_behavior(behavior='hold')
        held_low, held_code = ws.run_exit('r1', 'routine coordination turn\n',
                                          '--kind', 'coordination')
        assert held_code == 6
        assert held_low['turn_completed'] is False

        st_low = ws.status()
        assert st_low['state'] == 'running'
        disp_low = st_low['effort_display']
        assert disp_low['current_request']['active'] is True
        assert disp_low['active_effort'] == 'low'
        assert disp_low['current_request']['effort'] == 'low'
        assert disp_low['current_request']['kind'] == 'coordination'

        st_low_h = ws.status_human()
        assert 'effort low (policy adaptive)' in st_low_h
        eff_low_h = ws.effort_human('show')
        assert 'requested effort: low' in eff_low_h
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
        assert high_code == 6
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
        assert rej_code == 2
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
        assert unc_code == 3
        assert unc['status'] == 'uncertain'

        st_unc = ws.status()
        assert st_unc['state'] == 'outcome_unknown'
        disp_unc = st_unc['effort_display']
        assert disp_unc['current_request']['active'] is True
        assert disp_unc['effective'] == 'Unknown'
        st_unc_h = ws.status_human()
        assert 'state outcome_unknown' in st_unc_h
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


def main():
    test_suite()
    print('all lead effort display presentation checks passed')


if __name__ == '__main__':
    main()
