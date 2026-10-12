#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed worker experience and selection advice suite; zero provider calls."""
import copy
import datetime
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]
CLI = SOURCE / 'tools/model-experience.py'
NOW = datetime.datetime.now(datetime.timezone.utc)
STAMP = NOW.isoformat()


def make_revision(seed='1'):
    import hashlib
    h = hashlib.sha256(str(seed).encode('utf-8')).hexdigest()
    c = h[:40]
    b = h[:40]
    t = h
    w = h
    return {
        'candidate_commit': c,
        'base_commit': b,
        'task_sha256': t,
        'worktree_sha256': w,
    }


def make_result(worker='codex', task='TASK-1', rev=None, exit_code=0,
                val_state='passed', updated_at=None, stale=False,
                schema_version=1):
    if rev is None:
        rev = make_revision('a')
    if updated_at is None:
        updated_at = (NOW - datetime.timedelta(minutes=5)).isoformat()
    checks_run = 2 if val_state == 'passed' else 0
    checks_failed = 0
    scope = 'OK' if val_state == 'passed' else 'UNCHECKED'
    state = 'succeeded' if exit_code == 0 else 'failed'
    return {
        'schema_version': schema_version,
        'worker': worker,
        'task': task,
        'updated_at': updated_at,
        'stale': stale,
        'current_revision': rev,
        'revision': rev,
        'process': {
            'state': state,
            'exit_code': exit_code,
            'revision': rev,
        },
        'validation': {
            'state': val_state,
            'scope': scope,
            'checks_run': checks_run,
            'checks_failed': checks_failed,
            'revision': rev,
        },
        'review': {
            'state': 'not_run',
            'reviewer': None,
            'process_exit_code': None,
            'material_complete': False,
            'reasons': [],
            'revision': None,
        },
        'ready_for_human_review': False,
    }


RUNNER_SCRIPT = '''#!/usr/bin/env python3
import json, sys, os
from pathlib import Path

root = Path(__file__).parent
calls_log = root / 'calls.jsonl'
with calls_log.open('a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')

cmd = sys.argv[1] if len(sys.argv) > 1 else ''
if cmd == 'result':
    worker = sys.argv[2]
    task = sys.argv[3]
    db_file = root / 'results.json'
    if not db_file.exists():
        sys.stderr.write("no results db\\n")
        sys.exit(2)
    db = json.loads(db_file.read_text())
    key = worker + '/' + task
    if key not in db:
        sys.stderr.write("result not found\\n")
        sys.exit(2)
    res = db[key]
    sys.stdout.write(json.dumps(res))
    sys.exit(0)
elif cmd == 'policy':
    policy_file = root / 'policy.json'
    if policy_file.exists():
        sys.stdout.write(policy_file.read_text())
        sys.exit(0)
    sys.stdout.write(json.dumps({
        "schema_version": 1, "mode": "yolo", "tier": "low",
        "lead_agent": "codex", "lead_group": "codex",
        "workflow_enforcement": "native_workflows",
        "workflow_limit_per_group": 1,
        "accounts": {"alias": "codex"},
        "active_with_lead": {"codex": 0}
    }))
    sys.exit(0)
elif cmd == 'agents':
    agents_file = root / 'agents.json'
    if agents_file.exists():
        sys.stdout.write(agents_file.read_text())
        sys.exit(0)
    sys.stdout.write(json.dumps({
        "schema_version": 1,
        "agents": [
            {"name": "codex", "binary": {"present": True}, "bench": {"off": False}, "command": "codex"},
            {"name": "grok", "binary": {"present": True}, "bench": {"off": False}, "command": "grok"},
            {"name": "claude", "binary": {"present": True}, "bench": {"off": False}, "command": "claude"},
            {"name": "opencode-zen-free", "binary": {"present": True}, "bench": {"off": False}, "command": "opencode"}
        ]
    }))
    sys.exit(0)
elif cmd == 'capacity':
    cap_file = root / 'capacity.json'
    if cap_file.exists():
        sys.stdout.write(cap_file.read_text())
        sys.exit(0)
    sys.stdout.write(json.dumps({"schema_version": 1, "state": "ok", "groups": {}}))
    sys.exit(0)
elif cmd == 'readiness':
    read_file = root / 'readiness.json'
    if read_file.exists():
        sys.stdout.write(read_file.read_text())
        sys.exit(0)
    sys.stdout.write(json.dumps({"schema_version": 1, "state": "ok", "agents": {}}))
    sys.exit(0)
else:
    sys.stderr.write("unknown mock runner command: " + cmd + "\\n")
    sys.exit(1)
'''


class ExperienceSuite(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory(prefix='unio-experience-test-')
        self.root = Path(self.temp_dir.name)
        self.project = self.root / 'workspace'
        (self.project / 'coord').mkdir(parents=True)
        (self.project / 'wt').mkdir(parents=True)

        self.runner = self.root / 'mock-runner'
        self.runner.write_text(RUNNER_SCRIPT)
        self.runner.chmod(0o755)

        self.results_db = self.root / 'results.json'
        self.results = {}
        self.save_results()

    def tearDown(self):
        self.temp_dir.cleanup()

    def save_results(self):
        self.results_db.write_text(json.dumps(self.results))

    def run_cli(self, *args, cwd=None, project=None):
        if cwd is None:
            cwd = self.project
        cmd = [sys.executable, '-B', str(CLI), str(self.runner)]
        if project is not None:
            cmd.extend(['--project', str(project)])
        cmd.extend(args)
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)

    def test_01_installed_bundle_and_help(self):
        """Journey 1: Real copied standalone install & native project detection."""
        bin_dir = self.root / 'bin'
        conf_dir = self.root / 'conf'
        comp_dir = self.root / 'completion'
        env = dict(os.environ, UNIO_BIN_DIR=str(bin_dir), UNIO_CONF_DIR=str(conf_dir),
                   UNIO_COMPLETION_DIR=str(comp_dir))
        res = subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env,
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        installed_cli = conf_dir / 'lib/model-experience.py'
        self.assertTrue(installed_cli.exists())
        self.assertEqual(CLI.read_bytes(), installed_cli.read_bytes())

        unio_bin = bin_dir / 'unio'
        # Help outside any project
        outside = self.root / 'outside'
        outside.mkdir()
        h_res = subprocess.run([str(unio_bin), 'experience', '--help'], cwd=outside,
                               env=env, capture_output=True, text=True)
        self.assertEqual(h_res.returncode, 0)
        self.assertIn('Local worker experience', h_res.stdout)

        # Bare unio experience outside workspace shows help
        bare_res = subprocess.run([str(unio_bin), 'experience'], cwd=outside,
                                  env=env, capture_output=True, text=True)
        self.assertEqual(bare_res.returncode, 0)
        self.assertIn('Local worker experience', bare_res.stdout)

        # Show without --project inside project finds root
        show_res = subprocess.run([str(unio_bin), 'experience', 'show', '--json'],
                                  cwd=self.project, env=env, capture_output=True, text=True)
        self.assertEqual(show_res.returncode, 0, show_res.stderr)
        data = json.loads(show_res.stdout)
        self.assertEqual(data['command'], 'show')
        self.assertEqual(data['records'], 0)

        # Rejection of surplus / invalid flags with help
        rej1 = subprocess.run([str(unio_bin), 'experience', 'show', '--help', 'surplus'],
                              cwd=outside, env=env, capture_output=True, text=True)
        self.assertEqual(rej1.returncode, 2)
        self.assertIn('surplus argument', rej1.stderr)

        rej2 = subprocess.run([str(unio_bin), 'experience', 'show', '--unknown', '--help'],
                              cwd=outside, env=env, capture_output=True, text=True)
        self.assertEqual(rej2.returncode, 2)
        self.assertIn('unrecognized option', rej2.stderr)

        rej3 = subprocess.run([str(unio_bin), 'experience', 'show', '--project', str(self.project),
                               '--project', str(self.project), '--help'],
                              cwd=outside, env=env, capture_output=True, text=True)
        self.assertEqual(rej3.returncode, 2)
        self.assertIn('duplicate option', rej3.stderr)

    def test_02_record_outcomes_and_replay_conflicts(self):
        """Journey 2: Accepted vs unaccepted/quality/operational separation, replay/conflict."""
        rev = make_revision('1')
        up_time = (NOW - datetime.timedelta(days=2)).isoformat()
        self.results['codex/TASK-1'] = make_result(worker='codex', task='TASK-1', rev=rev,
                                                   exit_code=0, val_state='passed', updated_at=up_time)
        self.save_results()

        # 1. Accepted record
        res = self.run_cli('record', 'codex', 'TASK-1', '--model', 'openai/gpt-4o',
                           '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                           '--outcome', 'accepted', '--corrections', '0',
                           project=self.project)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('stored', res.stdout)

        # Check observed_at is from updated_at, not today's timestamp
        show = self.run_cli('show', '--json', project=self.project)
        self.assertEqual(show.returncode, 0)
        show_data = json.loads(show.stdout)
        self.assertEqual(show_data['records'], 1)
        profile = show_data['profiles'][0]
        self.assertEqual(profile['accepted_tasks'], 1)
        self.assertEqual(profile['newest_observation'], up_time)
        self.assertEqual(profile['model'], 'openai/gpt-4o')

        # 2. Idempotent replay of identical record
        res_replay = self.run_cli('record', 'codex', 'TASK-1', '--model', 'openai/gpt-4o',
                                  '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                                  '--outcome', 'accepted', '--corrections', '0',
                                  project=self.project)
        self.assertEqual(res_replay.returncode, 0)
        self.assertIn('already stored', res_replay.stdout)

        # 3. Conflicting record for same revision fails unchanged
        res_conf = self.run_cli('record', 'codex', 'TASK-1', '--model', 'openai/gpt-4o',
                                '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                                '--outcome', 'quality_issue', '--corrections', '1',
                                project=self.project)
        self.assertEqual(res_conf.returncode, 2)
        self.assertIn('conflicting assessment', res_conf.stderr)

        # 4. Accepted requires Source exit 0 and validation PASS
        self.results['codex/TASK-FAIL'] = make_result(worker='codex', task='TASK-FAIL', rev=rev,
                                                      exit_code=1, val_state='failed', updated_at=up_time)
        self.save_results()
        res_bad_acc = self.run_cli('record', 'codex', 'TASK-FAIL', '--model', 'openai/gpt-4o',
                                   '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                                   '--outcome', 'accepted', project=self.project)
        self.assertEqual(res_bad_acc.returncode, 2)
        self.assertIn('accepted requires Source exit zero', res_bad_acc.stderr)

        # 5. operational_failure requires nonzero exit code
        self.results['codex/TASK-OK'] = make_result(worker='codex', task='TASK-OK', rev=rev,
                                                    exit_code=0, val_state='passed', updated_at=up_time)
        self.save_results()
        res_bad_op = self.run_cli('record', 'codex', 'TASK-OK', '--model', 'openai/gpt-4o',
                                  '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                                  '--outcome', 'operational_failure', project=self.project)
        self.assertEqual(res_bad_op.returncode, 2)
        self.assertIn('operational_failure requires a nonzero Source exit', res_bad_op.stderr)

        # 6. Quality issue with exit 0 is valid
        res_qi = self.run_cli('record', 'codex', 'TASK-OK', '--model', 'openai/gpt-4o',
                              '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                              '--outcome', 'quality_issue', project=self.project)
        self.assertEqual(res_qi.returncode, 0)

        # 7. Unaccepted with exit 0 is valid
        rev2 = make_revision('2')
        self.results['codex/TASK-UNACC'] = make_result(worker='codex', task='TASK-UNACC', rev=rev2,
                                                       exit_code=0, val_state='passed', updated_at=up_time)
        self.save_results()
        res_unacc = self.run_cli('record', 'codex', 'TASK-UNACC', '--model', 'openai/gpt-4o',
                                 '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                                 '--outcome', 'unaccepted', project=self.project)
        self.assertEqual(res_unacc.returncode, 0)

    def test_03_result_schema_and_timestamp_strictness(self):
        """Journey 3: Strict result schema (schema_version bool, future timestamps, stale)."""
        rev = make_revision('3')
        # schema_version: True must fail
        self.results['codex/TASK-BOOL'] = make_result(worker='codex', task='TASK-BOOL', rev=rev,
                                                      schema_version=True)
        self.save_results()
        res = self.run_cli('record', 'codex', 'TASK-BOOL', '--model', 'gpt-4o',
                           '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                           '--outcome', 'accepted', project=self.project)
        self.assertEqual(res.returncode, 2)
        self.assertIn('malformed native result schema', res.stderr)

        # Future timestamp rejected
        future_time = (NOW + datetime.timedelta(days=10)).isoformat()
        self.results['codex/TASK-FUT'] = make_result(worker='codex', task='TASK-FUT', rev=rev,
                                                     updated_at=future_time)
        self.save_results()
        res_fut = self.run_cli('record', 'codex', 'TASK-FUT', '--model', 'gpt-4o',
                               '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                               '--outcome', 'accepted', project=self.project)
        self.assertEqual(res_fut.returncode, 2)
        self.assertIn('implausibly future', res_fut.stderr)

        # Stale result rejected
        self.results['codex/TASK-STALE'] = make_result(worker='codex', task='TASK-STALE', rev=rev,
                                                       stale=True)
        self.save_results()
        res_stale = self.run_cli('record', 'codex', 'TASK-STALE', '--model', 'gpt-4o',
                                 '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                                 '--outcome', 'accepted', project=self.project)
        self.assertEqual(res_stale.returncode, 2)
        self.assertIn('stale for the current revision', res_stale.stderr)

    def test_04_same_task_different_revisions_no_inflation(self):
        """Journey 4: Same task different revisions cannot inflate accepted task counts."""
        rev1 = make_revision('4')
        rev2 = make_revision('5')
        up_time = (NOW - datetime.timedelta(days=1)).isoformat()

        self.results['codex/TASK-MULTI'] = make_result(worker='codex', task='TASK-MULTI', rev=rev1,
                                                       exit_code=0, val_state='passed', updated_at=up_time)
        self.save_results()
        r1 = self.run_cli('record', 'codex', 'TASK-MULTI', '--model', 'gpt-4o',
                          '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                          '--outcome', 'accepted', project=self.project)
        self.assertEqual(r1.returncode, 0)

        # Record revision 2 for same task
        self.results['codex/TASK-MULTI'] = make_result(worker='codex', task='TASK-MULTI', rev=rev2,
                                                       exit_code=0, val_state='passed', updated_at=up_time)
        self.save_results()
        r2 = self.run_cli('record', 'codex', 'TASK-MULTI', '--model', 'gpt-4o',
                          '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                          '--outcome', 'accepted', project=self.project)
        self.assertEqual(r2.returncode, 0)

        show = self.run_cli('show', '--json', project=self.project)
        self.assertEqual(show.returncode, 0)
        p = json.loads(show.stdout)['profiles'][0]
        self.assertEqual(p['attempts'], 2)
        self.assertEqual(p['tasks'], 1)
        self.assertEqual(p['accepted_tasks'], 1)

    def test_05_suggestions_threshold_and_route_roles(self):
        """Journey 5: Old/empty/sparse samples, 90-day threshold, role limits (implementation vs routine)."""
        # 1. Empty sample -> insufficient evidence
        s0 = self.run_cli('suggest', '--task-type', 'feature', '--json', project=self.project)
        self.assertEqual(s0.returncode, 0)
        self.assertEqual(json.loads(s0.stdout)['decision'], 'insufficient_evidence')

        # 2. Record 3 accepted tasks for opencode-zen-free (free route)
        for i in range(1, 4):
            task_id = f'TASK-ZEN-{i}'
            rev = make_revision(f'z{i}')
            up_time = (NOW - datetime.timedelta(days=i)).isoformat()
            self.results[f'opencode-zen-free/{task_id}'] = make_result(
                worker='opencode-zen-free', task=task_id, rev=rev, exit_code=0,
                val_state='passed', updated_at=up_time)
        self.save_results()
        for i in range(1, 4):
            task_id = f'TASK-ZEN-{i}'
            r = self.run_cli('record', 'opencode-zen-free', task_id, '--model', 'glm-4',
                             '--route', 'opencode-zen-free', '--effort', 'none', '--task-type', 'feature',
                             '--outcome', 'accepted', project=self.project)
            self.assertEqual(r.returncode, 0)

        # Free route NOT eligible for implementation advice even with 3 accepted tasks!
        s_impl = self.run_cli('suggest', '--task-type', 'feature', '--work-kind', 'implementation',
                              '--json', project=self.project)
        self.assertEqual(s_impl.returncode, 0)
        self.assertEqual(json.loads(s_impl.stdout)['decision'], 'insufficient_evidence')

        # Free route IS eligible for routine advice!
        s_rout = self.run_cli('suggest', '--task-type', 'feature', '--work-kind', 'routine',
                              '--json', project=self.project)
        self.assertEqual(s_rout.returncode, 0)
        rout_data = json.loads(s_rout.stdout)
        self.assertEqual(rout_data['decision'], 'conditional_suggestions')
        self.assertEqual(len(rout_data['advice']['suggestions']), 1)
        self.assertEqual(rout_data['advice']['suggestions'][0]['route'], 'opencode-zen-free')

        # 3. Old records (> 90 days) do not qualify for threshold
        old_time = (NOW - datetime.timedelta(days=100)).isoformat()
        for i in range(1, 4):
            task_id = f'TASK-OLD-{i}'
            rev = make_revision(f'o{i}')
            self.results[f'grok/{task_id}'] = make_result(
                worker='grok', task=task_id, rev=rev, exit_code=0,
                val_state='passed', updated_at=old_time)
        self.save_results()
        for i in range(1, 4):
            task_id = f'TASK-OLD-{i}'
            r = self.run_cli('record', 'grok', task_id, '--model', 'grok-2',
                             '--route', 'grok', '--effort', 'high', '--task-type', 'old-type',
                             '--outcome', 'accepted', project=self.project)
            self.assertEqual(r.returncode, 0)

        s_old = self.run_cli('suggest', '--task-type', 'old-type', '--json', project=self.project)
        self.assertEqual(s_old.returncode, 0)
        self.assertEqual(json.loads(s_old.stdout)['decision'], 'insufficient_evidence')

    def test_06_admission_observation_honesty(self):
        """Journey 6: Group/lead slots, auth/allowance states, stale auth stays unknown."""
        # Record 3 recent accepted tasks for claude
        for i in range(1, 4):
            task_id = f'TASK-CLAUDE-{i}'
            rev = make_revision(f'c{i}')
            up_time = (NOW - datetime.timedelta(days=i)).isoformat()
            self.results[f'claude/{task_id}'] = make_result(
                worker='claude', task=task_id, rev=rev, exit_code=0,
                val_state='passed', updated_at=up_time)
        self.save_results()
        for i in range(1, 4):
            task_id = f'TASK-CLAUDE-{i}'
            r = self.run_cli('record', 'claude', task_id, '--model', 'claude-3-5-sonnet',
                             '--route', 'claude', '--effort', 'medium', '--task-type', 'adm-test',
                             '--outcome', 'accepted', project=self.project)
            self.assertEqual(r.returncode, 0)

        # Fake readiness: stale signed_in auth must remain unknown!
        readiness_file = self.root / 'readiness.json'
        readiness_file.write_text(json.dumps({
            "schema_version": 1, "state": "ok",
            "agents": {
                "claude": {
                    "status": "stale", "authentication": "signed_in",
                    "observed_at": (NOW - datetime.timedelta(hours=2)).isoformat(),
                    "age_seconds": 7200
                }
            }
        }))
        s1 = self.run_cli('suggest', '--task-type', 'adm-test', '--json', project=self.project)
        self.assertEqual(s1.returncode, 0)
        s1_data = json.loads(s1.stdout)
        claude_adm = s1_data['admission']['agents']['claude']
        self.assertEqual(claude_adm['auth'], 'unknown')
        self.assertIn('authentication_unknown', s1_data['advice']['suggestions'][0]['conditions'])

        # Fresh signed_out auth makes it NOT recommendable
        readiness_file.write_text(json.dumps({
            "schema_version": 1, "state": "ok",
            "agents": {
                "claude": {
                    "status": "fresh", "authentication": "signed_out",
                    "observed_at": NOW.isoformat(), "age_seconds": 1
                }
            }
        }))
        s2 = self.run_cli('suggest', '--task-type', 'adm-test', '--json', project=self.project)
        self.assertEqual(s2.returncode, 0)
        s2_data = json.loads(s2.stdout)
        sug = s2_data['advice']['suggestions'][0]
        self.assertEqual(sug['recommendable'], False)
        self.assertIn('fresh_signed_out', sug['conditions'])

        # STOP active makes admission blocked
        stop_file = self.project / 'coord/STOP'
        stop_file.write_text('owner pause\n')
        s3 = self.run_cli('suggest', '--task-type', 'adm-test', '--json', project=self.project)
        self.assertEqual(s3.returncode, 0)
        s3_data = json.loads(s3.stdout)
        sug3 = s3_data['advice']['suggestions'][0]
        self.assertEqual(sug3['recommendable'], False)
        self.assertEqual(sug3['admission_state'], 'blocked')
        stop_file.unlink()

    def test_07_store_corruption_symlink_and_no_write_reads(self):
        """Journey 7: Corrupt/bounded/symlink/no-write reads; identity recomputation."""
        # 1. Reads on clean project do not create store or locks
        clean_proj = self.root / 'clean'
        (clean_proj / 'coord').mkdir(parents=True)
        (clean_proj / 'wt').mkdir(parents=True)
        r_show = self.run_cli('show', '--json', project=clean_proj)
        self.assertEqual(r_show.returncode, 0)
        self.assertFalse((clean_proj / 'coord/experience').exists())

        # 2. Symlink in coord refuses
        bad_coord = self.root / 'bad-coord'
        bad_coord.mkdir()
        (bad_coord / 'wt').mkdir()
        target_dir = self.root / 'target-coord'
        target_dir.mkdir()
        (bad_coord / 'coord').symlink_to(target_dir)
        r_sym = self.run_cli('show', '--json', project=bad_coord)
        self.assertEqual(r_sym.returncode, 2)
        self.assertIn('unsafe coord directory', r_sym.stderr)

        # 3. Corrupt record in store fails load closed
        exp_dir = self.project / 'coord/experience/records'
        exp_dir.mkdir(parents=True)
        corrupt_rec = exp_dir / ('0' * 32 + '.json')
        corrupt_rec.write_text('{invalid json}')
        r_corrupt = self.run_cli('show', '--json', project=self.project)
        self.assertEqual(r_corrupt.returncode, 2)
        self.assertIn('malformed experience record', r_corrupt.stderr)
        corrupt_rec.unlink()

        # 4. Identity mismatch (tampered task in record file)
        # Create a valid record
        rev = make_revision('9')
        self.results['codex/TASK-TAMPER'] = make_result(worker='codex', task='TASK-TAMPER', rev=rev,
                                                        exit_code=0, val_state='passed')
        self.save_results()
        r_ok = self.run_cli('record', 'codex', 'TASK-TAMPER', '--model', 'gpt-4o',
                            '--route', 'codex', '--effort', 'high', '--task-type', 'feature',
                            '--outcome', 'accepted', project=self.project)
        self.assertEqual(r_ok.returncode, 0)

        # Modify the stored record to change task
        records = list(exp_dir.glob('*.json'))
        self.assertTrue(len(records) >= 1)
        rec_file = records[0]
        data = json.loads(rec_file.read_text())
        data['task'] = 'TASK-MODIFIED'
        rec_file.write_text(json.dumps(data))

        # Show must detect identity mismatch and fail
        r_tamper = self.run_cli('show', '--json', project=self.project)
        self.assertEqual(r_tamper.returncode, 2)
        self.assertIn('experience record identity mismatch', r_tamper.stderr)


if __name__ == '__main__':
    unittest.main()
