#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline tests for bounded read-only task plan observation and recommendations."""

import copy
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SOURCE_ROOT / 'bridge'))
from execution_service import ExecutionService
from plan_store import PlanStore
PLAN_HELPER = SOURCE_ROOT / 'tools/task-plan.py'
FLEET_HELPER = SOURCE_ROOT / 'tools/fleet-status.py'
INSTALLER = SOURCE_ROOT / 'unio-install.sh'

GIT_ENV = dict(
    os.environ,
    GIT_AUTHOR_NAME='Test Author',
    GIT_AUTHOR_EMAIL='test@example.com',
    GIT_COMMITTER_NAME='Test Committer',
    GIT_COMMITTER_EMAIL='test@example.com',
    GIT_OPTIONAL_LOCKS='0'
)


def git_run(repo, *args):
    cmd = ['git', '-C', str(repo), *args]
    res = subprocess.run(cmd, env=GIT_ENV, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{res.stderr}")
    return res.stdout.strip()


def sha256_text(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


class TaskPlanFixtures(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='task_plan_test_')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

        # Setup project workspace
        self.project = self.root / 'test project with spaces'
        self.coord = self.project / 'coord'
        self.wt = self.project / 'wt'
        self.repo = self.project / 'repo'

        self.coord.mkdir(parents=True)
        (self.coord / 'tasks').mkdir(parents=True)
        self.wt.mkdir(parents=True)
        self.repo.mkdir(parents=True)

        # Setup tiny Git history in repo
        git_run(self.repo, 'init', '-q', '-b', 'main')
        (self.repo / 'README.md').write_text('# Test Repo\n')
        git_run(self.repo, 'add', 'README.md')
        git_run(self.repo, 'commit', '-qm', 'initial commit')
        self.commit0 = git_run(self.repo, 'rev-parse', 'HEAD')

        (self.repo / 'file.txt').write_text('content\n')
        git_run(self.repo, 'add', 'file.txt')
        git_run(self.repo, 'commit', '-qm', 'second commit')
        self.commit1 = git_run(self.repo, 'rev-parse', 'HEAD')

        # Mock runner script for fleet collection
        self.runner = self.root / 'mock-runner'
        self.runner_calls = self.root / 'runner-calls.jsonl'
        self.runner_data_file = self.root / 'mock-runner-data.json'
        self.runner_data = self._default_fleet_data()
        self._write_runner_script()

        # Sentinel file to verify configured agents never run
        self.sentinel_marker = self.root / 'agent-executed'
        self.fake_agent = self.root / 'fake-agent'
        self.fake_agent.write_text(f"#!/bin/sh\ntouch {shlex.quote(str(self.sentinel_marker))}\nexit 99\n")
        self.fake_agent.chmod(0o755)

    def _default_fleet_data(self):
        stamp = datetime.now(timezone.utc).isoformat()
        return {
            'policy --json': {
                'schema_version': 1,
                'mode': 'yolo',
                'tier': 'low',
                'lead_agent': 'codex',
                'lead_group': 'codex',
                'workflow_enforcement': 'native_workflows',
                'workflow_limit_per_group': 1,
                'accounts': {'alias': 'codex'},
                'active_with_lead': {'codex': 1}
            },
            'agents --json': {
                'schema_version': 1,
                'agents': [
                    {'name': 'codex', 'binary': {'present': True}, 'bench': {'off': False}, 'command': 'agent'},
                    {'name': 'alias', 'binary': {'present': True}, 'bench': {'off': False}, 'command': 'agent'},
                    {'name': 'grok', 'binary': {'present': True}, 'bench': {'off': False}, 'command': 'agent'},
                    {'name': 'claude', 'binary': {'present': True}, 'bench': {'off': False}, 'command': 'agent'},
                    {'name': 'off_agent', 'binary': {'present': True}, 'bench': {'off': True}, 'command': 'agent'},
                    {'name': 'missing_bin', 'binary': {'present': False}, 'bench': {'off': False}, 'command': 'agent'}
                ]
            },
            'capacity show --json': {
                'schema_version': 1,
                'state': 'ok',
                'groups': {}
            },
            'capacity show --provider codex --json': {
                'schema_version': 1,
                'provider': 'codex',
                'state': 'ok',
                'groups': {}
            },
            'readiness show --json': {
                'schema_version': 1,
                'state': 'ok',
                'agents': {}
            }
        }

    def _write_runner_script(self):
        fake_py = f'''#!/usr/bin/env python3
import json, os, sys
root = Path = sys.modules['os'].path.dirname(__file__)
key = ' '.join(sys.argv[1:])
with open(os.path.join(root, 'runner-calls.jsonl'), 'a') as f:
    f.write(json.dumps({{'argv': sys.argv[1:], 'cwd': os.getcwd()}}) + '\\n')
with open(os.path.join(root, 'mock-runner-data.json')) as f:
    data = json.load(f)
if key in data:
    sys.stdout.write(json.dumps(data[key]))
    sys.exit(0)
sys.exit(1)
'''
        self.runner.write_text(fake_py)
        self.runner.chmod(0o755)

    def invoke_plan(self, inv_path, *extra_args, check_code=0):
        self.runner_data_file.write_text(json.dumps(self.runner_data))
        cmd = [
            sys.executable, '-B', str(PLAN_HELPER), str(self.runner),
            '--inventory', str(inv_path),
            '--project', str(self.project),
            *extra_args
        ]
        res = subprocess.run(cmd, env=GIT_ENV, capture_output=True, text=True, timeout=15)
        self.assertEqual(res.returncode, check_code, f"stderr: {res.stderr}\nstdout: {res.stdout}")
        self.assertFalse(self.sentinel_marker.exists(), "Provider sentinel binary was executed!")
        return res

    def make_task_file(self, task_id, scope_lines):
        scopes = '\n'.join(f"- {s}" for s in scope_lines)
        content = f"# Task {task_id}\n\nDescription of {task_id}.\n\n## Allowed scope\n{scopes}\n\n## Validate\n$ echo validate\n"
        path = self.coord / 'tasks' / f"{task_id}.md"
        path.write_text(content)
        return sha256_text(content)

    def make_inventory(self, tasks=None, accepted=None, base_revision=None):
        data = {
            'schema_version': 1,
            'base_revision': base_revision or self.commit1,
            'tasks': tasks or [],
            'accepted': accepted or []
        }
        inv_file = self.root / f"inv-{time.time_ns()}.json"
        inv_file.write_text(json.dumps(data, indent=2))
        return inv_file

    def test_strict_inventory_validation(self):
        # 1. Non-existent inventory
        res = self.invoke_plan(self.root / 'non-existent.json', check_code=2)
        self.assertIn('does not exist', res.stderr)

        # 2. Exceeds 256KiB
        big_file = self.root / 'big.json'
        big_file.write_bytes(b'{"x": "' + b'a' * (256 * 1024 + 10) + b'"}')
        res = self.invoke_plan(big_file, check_code=2)
        self.assertIn('exceeds 256 KiB', res.stderr)

        # 3. Duplicate JSON keys
        dup_file = self.root / 'dup.json'
        dup_file.write_text('{"schema_version": 1, "schema_version": 1, "base_revision": "abc", "tasks": [], "accepted": []}')
        res = self.invoke_plan(dup_file, check_code=2)
        self.assertIn('not valid strict UTF-8 JSON', res.stderr)

        # 4. Non-finite numbers (NaN)
        nan_file = self.root / 'nan.json'
        nan_file.write_text('{"schema_version": NaN, "base_revision": "abc", "tasks": [], "accepted": []}')
        res = self.invoke_plan(nan_file, check_code=2)
        self.assertIn('not valid strict UTF-8 JSON', res.stderr)

        # 5. Boolean as integer schema_version
        bool_file = self.root / 'bool.json'
        bool_file.write_text(json.dumps({
            'schema_version': True,
            'base_revision': self.commit1,
            'tasks': [],
            'accepted': []
        }))
        res = self.invoke_plan(bool_file, check_code=2)
        self.assertIn('schema_version must be integer 1', res.stderr)

        # 6. Unknown field in root
        unk_file = self.root / 'unk.json'
        unk_file.write_text(json.dumps({
            'schema_version': 1,
            'base_revision': self.commit1,
            'tasks': [],
            'accepted': [],
            'extra': 'bad'
        }))
        res = self.invoke_plan(unk_file, check_code=2)
        self.assertIn('must contain exactly', res.stderr)

        # 7. Duplicate task IDs in inventory
        t_hash = self.make_task_file('TASK-A', ['file.txt'])
        dup_task_file = self.make_inventory(tasks=[
            {'id': 'TASK-A', 'task_sha256': t_hash, 'worker': 'grok', 'depends_on': []},
            {'id': 'TASK-A', 'task_sha256': t_hash, 'worker': 'grok', 'depends_on': []}
        ])
        res = self.invoke_plan(dup_task_file, check_code=2)
        self.assertIn('duplicate task ID', res.stderr)

        # 8. Ambiguous accepted IDs
        dup_acc_file = self.make_inventory(accepted=[
            {'id': 'TASK-A', 'task_sha256': t_hash, 'revision': self.commit0},
            {'id': 'TASK-A', 'task_sha256': t_hash, 'revision': self.commit1}
        ])
        res = self.invoke_plan(dup_acc_file, check_code=2)
        self.assertIn('duplicate or ambiguous accepted task ID', res.stderr)

        # 9. Symlink inventory rejected
        target_file = self.make_inventory()
        symlink_file = self.root / 'symlink-inv.json'
        symlink_file.symlink_to(target_file)
        res = self.invoke_plan(symlink_file, check_code=2)
        self.assertIn('must not be a symlink', res.stderr)

        # 10. Timeout bounds
        valid_inv = self.make_inventory()
        self.invoke_plan(valid_inv, '--timeout', '0', check_code=2)
        self.invoke_plan(valid_inv, '--timeout', '61', check_code=2)

    def test_native_task_hashes_and_scope_parsing(self):
        # 1. Valid task with matching hash and scope
        h1 = self.make_task_file('TASK-1', ['tools/task-plan.py'])
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-1', 'task_sha256': h1, 'worker': 'grok', 'depends_on': []}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['summary']['ready'], 1)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(report['tasks'][0]['scopes'], ['tools/task-plan.py'])

        # 2. Task hash mismatch
        inv_bad_hash = self.make_inventory(tasks=[
            {'id': 'TASK-1', 'task_sha256': '0' * 64, 'worker': 'grok', 'depends_on': []}
        ])
        res = self.invoke_plan(inv_bad_hash, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['summary']['unresolved'], 1)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('task_hash_mismatch', report['tasks'][0]['reasons'])

        # 3. Missing task markdown file
        inv_missing_file = self.make_inventory(tasks=[
            {'id': 'TASK-MISSING', 'task_sha256': '0' * 64, 'worker': 'grok', 'depends_on': []}
        ])
        res = self.invoke_plan(inv_missing_file, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('missing_task_file', report['tasks'][0]['reasons'])

        # 4. Unsupported glob pattern in scope (e.g. *.py, ?, traversal ..)
        for bad_scope in ('tools/*.py', 'tools/?', '../traversal', '/absolute', 'path\\back', 'a//b'):
            h_bad = self.make_task_file('TASK-BAD-SCOPE', [bad_scope])
            inv_bad = self.make_inventory(tasks=[
                {'id': 'TASK-BAD-SCOPE', 'task_sha256': h_bad, 'worker': 'grok', 'depends_on': []}
            ])
            res = self.invoke_plan(inv_bad, '--json')
            report = json.loads(res.stdout)
            self.assertEqual(report['tasks'][0]['status'], 'unresolved', f"Failed for scope: {bad_scope}")
            self.assertIn('unsupported_scope_pattern', report['tasks'][0]['reasons'])

    def test_scope_conflicts_and_conservative_disjointness(self):
        # 1. Exact file conflict
        h_a = self.make_task_file('TASK-A', ['tools/task-plan.py'])
        h_b = self.make_task_file('TASK-B', ['tools/task-plan.py'])
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-A', 'task_sha256': h_a, 'worker': 'grok', 'depends_on': []},
            {'id': 'TASK-B', 'task_sha256': h_b, 'worker': 'claude', 'depends_on': []}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['summary']['ready'], 1)
        self.assertEqual(report['summary']['blocked'], 1)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(report['tasks'][1]['status'], 'blocked')
        self.assertIn('scope_conflict', report['tasks'][1]['reasons'])

        # 2. Parent / child conflict (directory prefix vs file)
        h_c = self.make_task_file('TASK-C', ['tools/'])
        h_d = self.make_task_file('TASK-D', ['tools/task-plan.py'])
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-C', 'task_sha256': h_c, 'worker': 'grok', 'depends_on': []},
            {'id': 'TASK-D', 'task_sha256': h_d, 'worker': 'claude', 'depends_on': []}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(report['tasks'][1]['status'], 'blocked')
        self.assertIn('scope_conflict', report['tasks'][1]['reasons'])

        # 3. Terminal /** conflict
        h_e = self.make_task_file('TASK-E', ['wt/**'])
        h_f = self.make_task_file('TASK-F', ['wt/sub/file.txt'])
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-E', 'task_sha256': h_e, 'worker': 'grok', 'depends_on': []},
            {'id': 'TASK-F', 'task_sha256': h_f, 'worker': 'claude', 'depends_on': []}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(report['tasks'][1]['status'], 'blocked')

        # 4. Whole-root ** conflicts with everything
        h_g = self.make_task_file('TASK-G', ['**'])
        h_h = self.make_task_file('TASK-H', ['other/dir/file.txt'])
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-G', 'task_sha256': h_g, 'worker': 'grok', 'depends_on': []},
            {'id': 'TASK-H', 'task_sha256': h_h, 'worker': 'claude', 'depends_on': []}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(report['tasks'][1]['status'], 'blocked')

        # 5. Conservative disjointness: when one unfinished task has invalid scope, other pending tasks become unresolved
        h_good = self.make_task_file('TASK-GOOD', ['tools/task-plan.py'])
        h_bad = self.make_task_file('TASK-BAD', ['tools/*.py'])
        inv_disjoint = self.make_inventory(tasks=[
            {'id': 'TASK-BAD', 'task_sha256': h_bad, 'worker': 'claude', 'depends_on': []},
            {'id': 'TASK-GOOD', 'task_sha256': h_good, 'worker': 'grok', 'depends_on': []}
        ])
        res = self.invoke_plan(inv_disjoint, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['summary']['ready'], 0)
        self.assertEqual(report['summary']['unresolved'], 2)
        self.assertIn('disjointness_unknown', report['tasks'][1]['reasons'])

    def test_dependencies_git_history_and_cycles(self):
        # 1. Dependency satisfied: revision commit0 is ancestor of commit1 (base HEAD)
        h0 = self.make_task_file('TASK-0', ['docs/TASK-0.md'])
        h1 = self.make_task_file('TASK-1', ['tools/task-plan.py'])
        inv = self.make_inventory(
            tasks=[
                {'id': 'TASK-1', 'task_sha256': h1, 'worker': 'grok', 'depends_on': [
                    {'id': 'TASK-0', 'task_sha256': h0, 'revision': self.commit0}
                ]}
            ],
            accepted=[
                {'id': 'TASK-0', 'task_sha256': h0, 'revision': self.commit0}
            ]
        )
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(len(report['tasks'][0]['dependencies']), 1)
        self.assertEqual(report['tasks'][0]['dependencies'][0]['revision'], self.commit0)

        # 2. Dependency hash mismatch -> blocked with exact mismatch reason
        inv_mismatch_hash = self.make_inventory(
            tasks=[
                {'id': 'TASK-1', 'task_sha256': h1, 'worker': 'grok', 'depends_on': [
                    {'id': 'TASK-0', 'task_sha256': '1' * 64, 'revision': self.commit0}
                ]}
            ],
            accepted=[
                {'id': 'TASK-0', 'task_sha256': h0, 'revision': self.commit0}
            ]
        )
        res = self.invoke_plan(inv_mismatch_hash, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertTrue(any('hash_mismatch' in r for r in report['tasks'][0]['reasons']))

        # 3. Dependency revision mismatch -> blocked with exact mismatch reason
        inv_mismatch_rev = self.make_inventory(
            tasks=[
                {'id': 'TASK-1', 'task_sha256': h1, 'worker': 'grok', 'depends_on': [
                    {'id': 'TASK-0', 'task_sha256': h0, 'revision': '1' * 40}
                ]}
            ],
            accepted=[
                {'id': 'TASK-0', 'task_sha256': h0, 'revision': self.commit0}
            ]
        )
        res = self.invoke_plan(inv_mismatch_rev, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertTrue(any('revision_mismatch' in r for r in report['tasks'][0]['reasons']))

        # 4. Missing acceptance evidence (prerequisite not in accepted) -> unresolved
        inv_missing_acc = self.make_inventory(
            tasks=[
                {'id': 'TASK-1', 'task_sha256': h1, 'worker': 'grok', 'depends_on': [
                    {'id': 'TASK-0', 'task_sha256': h0, 'revision': self.commit0}
                ]}
            ],
            accepted=[]
        )
        res = self.invoke_plan(inv_missing_acc, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertTrue(any('missing_acceptance_evidence' in r for r in report['tasks'][0]['reasons']))

        # 5. Task already integrated at base -> blocked as already_integrated
        inv_already = self.make_inventory(
            tasks=[
                {'id': 'TASK-0', 'task_sha256': h0, 'worker': 'grok', 'depends_on': []}
            ],
            accepted=[
                {'id': 'TASK-0', 'task_sha256': h0, 'revision': self.commit0}
            ]
        )
        res = self.invoke_plan(inv_already, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('already_integrated', report['tasks'][0]['reasons'])

        # 6. Dependency cycle among unsatisfied inventory tasks (A -> B -> A)
        ha = self.make_task_file('TASK-CYC-A', ['dir/a.txt'])
        hb = self.make_task_file('TASK-CYC-B', ['dir/b.txt'])
        inv_cycle = self.make_inventory(
            tasks=[
                {'id': 'TASK-CYC-A', 'task_sha256': ha, 'worker': 'grok', 'depends_on': [
                    {'id': 'TASK-CYC-B', 'task_sha256': hb, 'revision': self.commit0}
                ]},
                {'id': 'TASK-CYC-B', 'task_sha256': hb, 'worker': 'claude', 'depends_on': [
                    {'id': 'TASK-CYC-A', 'task_sha256': ha, 'revision': self.commit0}
                ]}
            ]
        )
        res = self.invoke_plan(inv_cycle, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['summary']['unresolved'], 2)
        self.assertIn('dependency_cycle', report['tasks'][0]['reasons'])
        self.assertIn('dependency_cycle', report['tasks'][1]['reasons'])

    def test_fleet_slots_group_aliases_and_busy_groups(self):
        # 1. Codex group has limit 1, occupied 1 by lead. Task for codex worker is blocked.
        h_codex = self.make_task_file('TASK-CODEX', ['file1.txt'])
        h_grok = self.make_task_file('TASK-GROK', ['file2.txt'])
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-CODEX', 'task_sha256': h_codex, 'worker': 'codex', 'depends_on': []},
            {'id': 'TASK-GROK', 'task_sha256': h_grok, 'worker': 'grok', 'depends_on': []}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('group_full', report['tasks'][0]['reasons'])
        # Grok is on an independent group with limit 1, occupied 0 -> ready!
        self.assertEqual(report['tasks'][1]['status'], 'ready')

        # 2. Group alias: 'alias' maps to 'codex'. Task for alias worker is also blocked by group_full.
        h_alias = self.make_task_file('TASK-ALIAS', ['file3.txt'])
        inv_alias = self.make_inventory(tasks=[
            {'id': 'TASK-ALIAS', 'task_sha256': h_alias, 'worker': 'alias', 'depends_on': []}
        ])
        res = self.invoke_plan(inv_alias, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('group_full', report['tasks'][0]['reasons'])

        # 3. Busy group in fleet: suppose grok group has occupied=1.
        # Inventory contains TASK-GROK with scope ['shared/scope.txt'].
        # Another task TASK-OTHER on claude has scope ['shared/scope.txt'].
        # TASK-GROK's scope is inferred occupied, blocking TASK-OTHER!
        self.runner_data['policy --json']['active_with_lead']['grok'] = 1
        h_g1 = self.make_task_file('TASK-G1', ['shared/scope.txt'])
        h_cl = self.make_task_file('TASK-CL', ['shared/scope.txt'])
        inv_busy = self.make_inventory(tasks=[
            {'id': 'TASK-CL', 'task_sha256': h_cl, 'worker': 'claude', 'depends_on': []},
            {'id': 'TASK-G1', 'task_sha256': h_g1, 'worker': 'grok', 'depends_on': []}
        ])
        res = self.invoke_plan(inv_busy, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('scope_conflict', report['tasks'][0]['reasons'])

        # 4. Busy group with no task in inventory generates a warning
        self.runner_data['policy --json']['active_with_lead']['unknown_busy_grp'] = 1
        res = self.invoke_plan(inv_busy, '--json')
        report = json.loads(res.stdout)
        self.assertTrue(any('unknown_busy_grp' in w for w in report['warnings']))

        # 5. STOP active blocks all rows
        (self.coord / 'STOP').touch()
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertTrue(report['stop'])
        self.assertEqual(report['summary']['ready'], 0)
        self.assertEqual(report['summary']['blocked'], 2)
        (self.coord / 'STOP').unlink()

        # 6. Changed repo HEAD vs inventory base_revision makes all rows unresolved
        inv_changed_head = self.make_inventory(
            tasks=[{'id': 'TASK-GROK', 'task_sha256': h_grok, 'worker': 'grok', 'depends_on': []}],
            base_revision='0' * 40
        )
        res = self.invoke_plan(inv_changed_head, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['summary']['unresolved'], 1)
        self.assertIn('base_revision_mismatch', report['tasks'][0]['reasons'])

    def test_auth_and_allowance_handling(self):
        # 1. Fresh signed_out auth blocks task with auth_signed_out
        h = self.make_task_file('TASK-CLAUDE', ['tools/claude.py'])
        self.runner_data['readiness show --json']['agents']['claude'] = {
            'status': 'fresh',
            'authentication': 'signed_out',
            'source': 'native',
            'observed_at': datetime.now(timezone.utc).isoformat(),
            'age_seconds': 5
        }
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-CLAUDE', 'task_sha256': h, 'worker': 'claude', 'depends_on': []}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('auth_signed_out', report['tasks'][0]['reasons'])

        # 2. Fresh zero allowance blocks task with zero_allowance
        self.runner_data['readiness show --json']['agents']['claude']['authentication'] = 'signed_in'
        self.runner_data['capacity show --json']['groups']['claude'] = {
            'status': 'recorded',
            'windows': {
                '5h': {
                    'source': 'manual',
                    'status': 'fresh',
                    'window_minutes': 300,
                    'usable_remaining_percent': 0.0,
                    'last_reading_remaining_percent': 0.0,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                    'age_seconds': 10,
                    'reset_at': None
                }
            }
        }
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('zero_allowance', report['tasks'][0]['reasons'])

        # 3. Stale allowance does not block
        self.runner_data['capacity show --json']['groups']['claude']['windows']['5h']['status'] = 'stale'
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'ready')

    def test_browser_queue_observation(self):
        # 1. Absent queue creates nothing; task with job_id stays unresolved
        h = self.make_task_file('TASK-Q', ['file.py'])
        job_id = 'a' * 32
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-Q', 'task_sha256': h, 'worker': 'grok', 'depends_on': [], 'job_id': job_id}
        ])
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertFalse((self.coord / 'ui-jobs.sqlite3').exists(), "Absent queue must not be created!")

        # 2. Existing sqlite queue with approved job and valid draft
        db_path = self.coord / 'ui-jobs.sqlite3'
        conn = sqlite3.connect(db_path)
        conn.execute('''CREATE TABLE jobs (
            id TEXT PRIMARY KEY,
            request_key TEXT NOT NULL UNIQUE,
            draft_id TEXT NOT NULL,
            draft_sha256 TEXT NOT NULL,
            worker TEXT NOT NULL,
            created_at TEXT NOT NULL,
            state TEXT NOT NULL,
            approval_key TEXT UNIQUE,
            approved_at TEXT,
            reservation_key TEXT UNIQUE,
            reserved_at TEXT,
            unknown_at TEXT,
            cancelled_at TEXT)''')
        conn.execute('PRAGMA user_version = 2')

        plans_dir = self.coord / 'ui-plans'
        plans_dir.mkdir(parents=True)
        draft_id = 'b' * 32
        stamp = datetime.now(timezone.utc).isoformat()
        draft_data = {
            'schema_version': 1,
            'id': draft_id,
            'created_at': stamp,
            'state': 'draft',
            'request': 'plan draft request'
        }
        draft_bytes = (json.dumps(draft_data, sort_keys=True, separators=(',', ':')) + '\n').encode('utf-8')
        (plans_dir / f"{draft_id}.json").write_bytes(draft_bytes)
        draft_sha256 = hashlib.sha256(draft_bytes).hexdigest()

        conn.execute(
            'INSERT INTO jobs (id, request_key, draft_id, draft_sha256, worker, created_at, state, approval_key, approved_at) '
            'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
            (job_id, 'c' * 32, draft_id, draft_sha256, 'grok', stamp, 'approved', 'd' * 32, stamp)
        )
        conn.commit()
        conn.close()

        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(report['tasks'][0]['job_id'], job_id)

        # 3. Job state 'awaiting_owner_approval' -> blocked
        conn = sqlite3.connect(db_path)
        conn.execute('UPDATE jobs SET state = "awaiting_owner_approval", approval_key = NULL, approved_at = NULL WHERE id = ?', (job_id,))
        conn.commit()
        conn.close()

        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('awaiting_owner_approval', report['tasks'][0]['reasons'])

        # 4. Job state 'cancelled' -> blocked
        conn = sqlite3.connect(db_path)
        conn.execute('UPDATE jobs SET state = "cancelled", cancelled_at = ? WHERE id = ?', (stamp, job_id))
        conn.commit()
        conn.close()

        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('job_cancelled', report['tasks'][0]['reasons'])

        # 5. Sidecar present (-wal) -> unresolved
        (self.coord / 'ui-jobs.sqlite3-wal').touch()
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('unsupported_queue_sidecar', report['tasks'][0]['reasons'])
        (self.coord / 'ui-jobs.sqlite3-wal').unlink()

    def test_coordination_tree_immutability(self):
        h = self.make_task_file('TASK-IMMUTABLE', ['tools/file.py'])
        inv = self.make_inventory(tasks=[
            {'id': 'TASK-IMMUTABLE', 'task_sha256': h, 'worker': 'grok', 'depends_on': []}
        ])

        before_files = {}
        for p in self.coord.rglob('*'):
            before_files[str(p.relative_to(self.coord))] = (p.stat().st_mtime_ns, p.stat().st_size)

        self.invoke_plan(inv, '--json')
        self.invoke_plan(inv)

        after_files = {}
        for p in self.coord.rglob('*'):
            after_files[str(p.relative_to(self.coord))] = (p.stat().st_mtime_ns, p.stat().st_size)

        self.assertEqual(before_files, after_files, "Coordination directory was modified!")

    def test_queue_malformed_evidence_is_unresolved(self):
        h = self.make_task_file('QUEUE', ['src/queue.py'])
        job_id, draft_id = 'a' * 32, 'b' * 32
        inv = self.make_inventory(tasks=[dict(id='QUEUE', task_sha256=h, worker='grok',
                                             depends_on=[], job_id=job_id)])
        import importlib.util
        spec = importlib.util.spec_from_file_location('fixture_job_types', SOURCE_ROOT / 'bridge/job_store.py')
        types = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(types)
        db = self.coord / 'ui-jobs.sqlite3'
        conn = sqlite3.connect(db)
        conn.execute(types.CREATE_JOBS)
        conn.execute('PRAGMA user_version=2')
        plans = self.coord / 'ui-plans'
        plans.mkdir()
        stamp = datetime.now(timezone.utc).isoformat()

        def body(identity):
            return json.dumps(dict(schema_version=1, id=identity, created_at=stamp,
                                   state='draft', request='Offline fixture')).encode()

        raw = body(draft_id)
        (plans / (draft_id + '.json')).write_bytes(raw)
        conn.execute('INSERT INTO jobs VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
            (job_id, 'c' * 32, draft_id, hashlib.sha256(raw).hexdigest(), 'grok', stamp,
             'approved', None, None, None, None, None, None))
        conn.commit()
        report = json.loads(self.invoke_plan(inv, '--json').stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('invalid_queue_evidence', report['tasks'][0]['reasons'])

        # Invalid draft IDs must be rejected before forming a file path.
        outside = '../outside'
        raw = body(outside)
        (self.coord / 'outside.json').write_bytes(raw)
        conn.execute('UPDATE jobs SET draft_id=?,draft_sha256=?,approval_key=?,approved_at=?',
            (outside, hashlib.sha256(raw).hexdigest(), 'd' * 32, stamp))
        conn.commit()
        report = json.loads(self.invoke_plan(inv, '--json').stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        conn.close()

        db.write_bytes(b'not a SQLite database')
        res = self.invoke_plan(inv, '--json')
        self.assertEqual(json.loads(res.stdout)['tasks'][0]['status'], 'unresolved')
        self.assertNotIn('Traceback', res.stderr)

    def test_special_files_parent_links_and_git_deadline(self):
        inv = self.make_inventory()
        fifo = self.root / 'inventory-fifo'
        os.mkfifo(fifo)
        self.invoke_plan(fifo, check_code=2)
        link = self.root / 'inventory-parent-link'
        link.symlink_to(self.root, target_is_directory=True)
        self.invoke_plan(link / inv.name, check_code=2)
        task_hash = self.make_task_file('FIFO', ['src/safe.py'])
        task_path = self.coord / 'tasks/FIFO.md'
        task_path.unlink()
        os.mkfifo(task_path)
        fifo_inv = self.make_inventory(tasks=[dict(id='FIFO', task_sha256=task_hash,
                                                  worker='grok', depends_on=[])])
        self.assertEqual(json.loads(self.invoke_plan(fifo_inv, '--json').stdout)
                         ['tasks'][0]['status'], 'unresolved')

        # A Git process that closes output and leaves a descendant must not
        # escape the shared deadline or survive the observation.
        fake_bin = self.root / 'fake-bin'
        fake_bin.mkdir()
        pid_file = self.root / 'git-child.pid'
        fake_git = fake_bin / 'git'
        fake_git.write_text('#!' + sys.executable + '\nimport os,time\n'
            'pid=os.fork()\nif pid==0:\n'
            f' open({str(pid_file)!r},"w").write(str(os.getpid()))\n'
            ' os.close(1);os.close(2);time.sleep(30);os._exit(0)\n'
            'os.close(1);os.close(2);time.sleep(30)\n')
        fake_git.chmod(0o755)
        env = dict(GIT_ENV, PATH=str(fake_bin) + os.pathsep + os.environ['PATH'])
        started = time.monotonic()
        res = subprocess.run([sys.executable, '-I', '-S', '-B', str(PLAN_HELPER),
            str(self.runner), '--project', str(self.project), '--inventory', str(inv),
            '--timeout', '1', '--json'], env=env, capture_output=True, text=True, timeout=5)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertLess(time.monotonic() - started, 4)
        self.assertTrue(pid_file.is_file())
        proc = Path('/proc') / pid_file.read_text().strip() / 'stat'
        if proc.exists():
            text = proc.read_text()
            self.assertEqual(text[text.rindex(')') + 2:].split()[0], 'Z')

    def test_prepared_material_observation(self):
        # Setup git worktree and base for ExecutionService
        (self.coord / 'base').write_text('main\n')
        wt_worker = self.wt / 'grok'
        git_run(self.repo, 'worktree', 'add', '-q', '-b', 'agent/grok', str(wt_worker))

        engine = self.project / 'mock-engine'
        engine.write_text("#!/bin/sh\nexit 0\n")
        engine.chmod(0o755)

        config_dir = self.project / 'config'
        config_dir.mkdir(parents=True, exist_ok=True)
        (config_dir / 'agents.conf').write_text("grok=agent\nclaude=agent\n")

        template_path = self.project / 'template.json'
        template_path.write_text(json.dumps({
            'schema_version': 1,
            'instructions': 'Implement the literal saved request.',
            'scope': ['file.txt'],
            'validate': ['echo validate']
        }))

        # Create draft via PlanStore and prepare/approve via real ExecutionService
        plans = PlanStore(self.project)
        draft = plans.create("Implement feature X.")
        plans.close()

        service = ExecutionService(
            self.project,
            engine,
            'grok',
            'claude',
            config_dir,
            template_path,
            'Grok Lab',
            'Claude Lab'
        )
        prep_view = service.prepare(draft['id'], draft['content_sha256'], '1' * 32)
        job_id = prep_view['job']['id']
        preview_hash = prep_view['preview']['preview_hash']
        app_view = service.approve(job_id, draft['content_sha256'], '2' * 32, preview_hash)
        service.close()

        task_id = 'ui-' + job_id
        task_sha256 = app_view['preview']['task_sha256']
        inv_tasks = [
            {'id': task_id, 'task_sha256': task_sha256, 'worker': 'grok', 'depends_on': [], 'job_id': job_id}
        ]
        inv = self.make_inventory(tasks=inv_tasks, base_revision=self.commit1)

        # 1. Native task is absent, prepared material plans ready with unchanged coordination bytes
        self.assertFalse((self.coord / 'tasks' / f"{task_id}.md").exists())
        before_coord = {
            str(p.relative_to(self.coord)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in self.coord.rglob('*') if p.is_file()
        }

        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['summary']['ready'], 1)
        self.assertEqual(report['tasks'][0]['status'], 'ready')
        self.assertEqual(report['tasks'][0]['scopes'], ['file.txt'])
        self.assertEqual(report['tasks'][0]['job_id'], job_id)

        after_coord = {
            str(p.relative_to(self.coord)): (p.stat().st_size, p.stat().st_mtime_ns)
            for p in self.coord.rglob('*') if p.is_file()
        }
        self.assertEqual(before_coord, after_coord, "Coordination directory must remain unchanged!")
        self.assertFalse((self.coord / 'tasks' / f"{task_id}.md").exists())
        self.assertFalse(self.sentinel_marker.exists())

        # 2. Altered companion: alter scope.json
        scope_file = self.coord / 'ui-execution' / 'bindings' / f"{job_id}.scope.json"
        orig_scope = scope_file.read_bytes()
        scope_file.write_text('["other.txt"]')
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('altered_companion', report['tasks'][0]['reasons'])
        scope_file.write_bytes(orig_scope)

        # Alter request.json
        req_file = self.coord / 'ui-execution' / 'bindings' / f"{job_id}.request.json"
        orig_req = req_file.read_bytes()
        req_file.write_text('"Tampered request"')
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('altered_companion', report['tasks'][0]['reasons'])
        req_file.write_bytes(orig_req)

        # Alter compiled task markdown .md
        md_file = self.coord / 'ui-execution' / 'bindings' / f"{job_id}.md"
        orig_md = md_file.read_bytes()
        md_file.write_text('# Tampered task markdown\n')
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('altered_companion', report['tasks'][0]['reasons'])
        md_file.write_bytes(orig_md)

        # 3. Wrong identity: wrong worker, wrong task ID, or wrong job ID
        inv_wrong_worker = self.make_inventory(
            tasks=[{'id': task_id, 'task_sha256': task_sha256, 'worker': 'claude', 'depends_on': [], 'job_id': job_id}],
            base_revision=self.commit1
        )
        res = self.invoke_plan(inv_wrong_worker, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('job_worker_mismatch', report['tasks'][0]['reasons'])

        inv_wrong_tid = self.make_inventory(
            tasks=[{'id': 'TASK-DIFF', 'task_sha256': task_sha256, 'worker': 'grok', 'depends_on': [], 'job_id': job_id}],
            base_revision=self.commit1
        )
        res = self.invoke_plan(inv_wrong_tid, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('missing_task_file', report['tasks'][0]['reasons'])

        inv_wrong_job = self.make_inventory(
            tasks=[{'id': 'ui-' + 'f' * 32, 'task_sha256': task_sha256, 'worker': 'grok', 'depends_on': [], 'job_id': 'f' * 32}],
            base_revision=self.commit1
        )
        res = self.invoke_plan(inv_wrong_job, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('missing_prepared_material', report['tasks'][0]['reasons'])

        # 4. Wrong base: binding prepared at an old base must be unresolved
        bind_file = self.coord / 'ui-execution' / 'bindings' / f"{job_id}.json"
        orig_bind = bind_file.read_bytes()
        bind_obj = json.loads(orig_bind)
        spec = importlib.util.spec_from_file_location('prepared_plan_types', PLAN_HELPER)
        planner = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(planner)
        fields = [(key,) for key in (
            'job_id', 'request_key', 'draft_id', 'draft_sha256',
            'base_revision', 'worker_revision')]
        fields += [('preview', key) for key in (
            'reviewer', 'task_sha256', 'preview_hash')]
        fields += [('fingerprints', key) for key in ('engine', 'config', 'template')]
        for field in fields:
            for value in (None, 17, True, [], {}):
                with self.subTest(field=field, invalid_value=value):
                    malformed = copy.deepcopy(bind_obj)
                    target = malformed if len(field) == 1 else malformed[field[0]]
                    target[field[-1]] = value
                    bind_file.write_text(json.dumps(malformed))
                    parsed = planner.parse_prepared_binding(
                        self.coord, job_id, inv_tasks[0], self.commit1)
                    self.assertEqual(parsed[1:3], ('unresolved', 'invalid_prepared_material'))
        # Exercise the public planner too: malformed metadata is a JSON result,
        # not an uncaught exception or an opportunity to publish a native task.
        res = self.invoke_plan(inv, '--json')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('invalid_prepared_material', json.loads(res.stdout)['tasks'][0]['reasons'])
        self.assertFalse((self.coord / 'tasks' / f'{task_id}.md').exists())
        bind_file.write_bytes(orig_bind)
        bind_obj['base_revision'] = self.commit0
        bind_obj['worker_revision'] = self.commit0
        bind_file.write_text(json.dumps(bind_obj))
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('prepared_base_mismatch', report['tasks'][0]['reasons'])
        bind_file.write_bytes(orig_bind)

        # 5. Wrong hash
        inv_wrong_hash = self.make_inventory(
            tasks=[{'id': task_id, 'task_sha256': '0' * 64, 'worker': 'grok', 'depends_on': [], 'job_id': job_id}],
            base_revision=self.commit1
        )
        res = self.invoke_plan(inv_wrong_hash, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('task_hash_mismatch', report['tasks'][0]['reasons'])

        # 6. Native tamper must refuse and never fall back to prepared binding
        native_task = self.coord / 'tasks' / f"{task_id}.md"
        native_task.write_text('# Tampered native markdown\n\n## Allowed scope\n- file.txt\n\n## Validate\n$ echo 1\n')
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('task_hash_mismatch', report['tasks'][0]['reasons'])

        # Native task as symlink
        native_task.unlink()
        native_task.symlink_to(self.repo / 'file.txt')
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'unresolved')
        self.assertIn('task_path_unsafe', report['tasks'][0]['reasons'])
        native_task.unlink()

        # 7. Unapproved job: state awaiting_owner_approval blocks
        db_path = self.coord / 'ui-jobs.sqlite3'
        conn = sqlite3.connect(db_path)
        conn.execute('UPDATE jobs SET state = "awaiting_owner_approval", approval_key = NULL, approved_at = NULL WHERE id = ?', (job_id,))
        conn.commit()
        conn.close()
        res = self.invoke_plan(inv, '--json')
        report = json.loads(res.stdout)
        self.assertEqual(report['tasks'][0]['status'], 'blocked')
        self.assertIn('awaiting_owner_approval', report['tasks'][0]['reasons'])

        # 8. Provider sentinels must remain untouched
        self.assertFalse(self.sentinel_marker.exists())


class InstalledPlanCli(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='installed_plan_')
        cls.base = Path(cls.temp.name)
        cls.conf = cls.base / 'conf with spaces'
        cls.bin = cls.base / 'bin with spaces'
        cls.completion = cls.base / 'completion'

        cls.env = dict(
            os.environ,
            UNIO_BIN_DIR=str(cls.bin),
            UNIO_CONF_DIR=str(cls.conf),
            UNIO_COMPLETION_DIR=str(cls.completion),
            PYTHONDONTWRITEBYTECODE='1',
            GIT_AUTHOR_NAME='Test',
            GIT_AUTHOR_EMAIL='test@example.com',
            GIT_COMMITTER_NAME='Test',
            GIT_COMMITTER_EMAIL='test@example.com'
        )

        standalone = cls.base / 'standalone-installer.sh'
        standalone.write_bytes(INSTALLER.read_bytes())
        res = subprocess.run(
            ['bash', str(standalone)],
            env=cls.env, cwd=cls.base,
            capture_output=True, text=True, timeout=60
        )
        if res.returncode != 0:
            raise RuntimeError(f"Installer failed: {res.stderr}")

        cls.engine = cls.bin / 'unio'

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_embedded_payload_and_cli_help(self):
        # 1. Byte-identical embedded task-plan.py
        installed_helper = self.conf / 'lib/task-plan.py'
        self.assertTrue(installed_helper.is_file())
        self.assertEqual(installed_helper.read_bytes(), PLAN_HELPER.read_bytes())

        # 2. --help outside project works and exits 0
        res = subprocess.run([str(self.engine), 'plan', '--help'], env=self.env, cwd=self.base, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0)
        self.assertIn('unio plan', res.stdout)
        self.assertIn('--inventory', res.stdout)

        # 3. bash completion file has plan command and options
        comp_file = self.completion / 'unio'
        self.assertTrue(comp_file.is_file())
        comp_text = comp_file.read_text()
        self.assertIn('plan)', comp_text)
        self.assertIn('--inventory', comp_text)

    def test_installed_command_keeps_absent_queue_absent(self):
        project = self.base / 'installed project'
        (project / 'coord/tasks').mkdir(parents=True)
        (project / 'wt').mkdir()
        repo = project / 'repo'
        repo.mkdir()
        git_run(repo, 'init', '-q', '-b', 'main')
        (repo / 'file.txt').write_text('fixture\n')
        git_run(repo, 'add', 'file.txt')
        git_run(repo, 'commit', '-qm', 'fixture')
        (project / 'coord/base').write_text('main\n')
        marker = self.base / 'provider-was-called'
        sentinel = self.base / 'provider-sentinel'
        sentinel.write_text('#!/bin/sh\ntouch ' + shlex.quote(str(marker)) + '\n')
        sentinel.chmod(0o755)
        (self.conf / 'agents.conf').write_text('idle=' + shlex.quote(str(sentinel)) + '\n')
        body = '# Test\n\n## Allowed scope\n- src/feature.py\n\n## Validate\n$ touch validate-was-run\n'
        (project / 'coord/tasks/READY.md').write_text(body)
        inventory = self.base / 'installed-inventory.json'
        inventory.write_text(json.dumps(dict(schema_version=1,
            base_revision=git_run(repo, 'rev-parse', 'HEAD'), accepted=[], tasks=[dict(
                id='READY', task_sha256=sha256_text(body), worker='idle-one', depends_on=[])])))
        before = {str(p.relative_to(project / 'coord')): p.read_bytes()
                  for p in (project / 'coord').rglob('*') if p.is_file()}
        res = subprocess.run([str(self.engine), 'plan', '--inventory', str(inventory),
            '--project', str(project), '--json'], cwd=self.base, env=self.env,
            capture_output=True, text=True, timeout=20)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(json.loads(res.stdout)['tasks'][0]['status'], 'ready')
        after = {str(p.relative_to(project / 'coord')): p.read_bytes()
                 for p in (project / 'coord').rglob('*') if p.is_file()}
        self.assertEqual(before, after)
        self.assertFalse(marker.exists())
        self.assertFalse((repo / 'validate-was-run').exists())
        self.assertFalse((project / 'coord/ui-jobs.sqlite3').exists())


if __name__ == '__main__':
    unittest.main()
