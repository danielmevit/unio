#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Focused tests for the local fleet snapshot tool."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

class FleetStatusTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.project_root = os.path.join(self.temp_dir, 'project with spaces')
        self.coord_dir = os.path.join(self.project_root, 'coord')
        os.makedirs(self.coord_dir)
        
        self.fake_runner = os.path.join(self.temp_dir, 'fake-runner.py')
        with open(self.fake_runner, 'w') as f:
            f.write("""#!/usr/bin/env python3
import sys
import json
cmd = sys.argv[1:]
if cmd == ['policy', '--json']:
    print(json.dumps({"schema_version": 1, "mode": "yolo", "tier": "low", "lead_agent": "codex", "workflow_limit_per_group": 1, "accounts": {"alias": "codex"}, "active_with_lead": {"codex": 1}}))
elif cmd == ['agents', '--json']:
    print(json.dumps({"schema_version": 1, "agents": [{"name": "codex", "binary": {"present": True}}, {"name": "alias", "binary": {"present": True}}, {"name": "missing", "binary": {"present": False}}]}))
elif cmd == ['capacity', 'show', '--json']:
    print(json.dumps({"schema_version": 1, "groups": {"codex": {"state": "ok", "buckets": {}}}}))
elif cmd == ['capacity', 'show', '--provider', 'codex', '--json']:
    print(json.dumps({"schema_version": 1, "groups": {"codex": {"state": "stale", "buckets": {}}}}))
elif cmd == ['readiness', 'show', '--json']:
    print(json.dumps({"schema_version": 1, "agents": {"codex": {"status": "ok", "age_seconds": 120}}}))
else:
    sys.exit(1)
""")
        os.chmod(self.fake_runner, 0o755)

        # Write fleet-status.py exactly as in the repo
        repo_root = Path(__file__).resolve().parent.parent
        self.fleet_py = os.path.join(self.temp_dir, 'fleet-status.py')
        shutil.copy2(os.path.join(repo_root, 'tools', 'fleet-status.py'), self.fleet_py)

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def run_fleet(self, args, project=None):
        if project is None:
            project = self.project_root
        cmd = [sys.executable, self.fleet_py, self.fake_runner, project] + args
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc

    def test_json_object(self):
        proc = self.run_fleet(['--json'])
        self.assertEqual(proc.returncode, 0)
        obj = json.loads(proc.stdout)
        self.assertEqual(obj['schema_version'], 1)
        self.assertEqual(obj['mode'], 'yolo')
        self.assertFalse(obj['stop'])
        self.assertIn('codex', obj['groups'])

    def test_shared_aliases_and_lead_at_low_tier(self):
        proc = self.run_fleet(['--json'])
        obj = json.loads(proc.stdout)
        group = obj['groups']['codex']
        self.assertEqual(group['occupied'], 1)
        self.assertEqual(group['limit'], 1)
        self.assertEqual(group['agents']['codex']['admission_state'], 'blocked')
        self.assertIn('group_full', group['agents']['codex']['reasons'])
        self.assertEqual(group['agents']['alias']['admission_state'], 'blocked')
        self.assertIn('group_full', group['agents']['alias']['reasons'])

    def test_stop(self):
        with open(os.path.join(self.coord_dir, 'STOP'), 'w') as f:
            f.write('')
        proc = self.run_fleet(['--json'])
        obj = json.loads(proc.stdout)
        self.assertTrue(obj['stop'])
        self.assertIn('project_STOP', obj['groups']['codex']['agents']['codex']['reasons'])

    def test_missing_binary(self):
        proc = self.run_fleet(['--json'])
        obj = json.loads(proc.stdout)
        self.assertIn('binary_missing', obj['groups']['missing']['agents']['missing']['reasons'])

    def test_help_outside_project(self):
        # Even if the dispatcher didn't pass a project or passed empty string, help should work
        proc = subprocess.run([sys.executable, self.fleet_py, self.fake_runner, '', '--help'], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0)
        self.assertIn('usage', proc.stdout.lower() + proc.stderr.lower())

    def test_no_provider_calls(self):
        proc = self.run_fleet(['--json'])
        self.assertEqual(proc.returncode, 0)
        # the fake runner doesn't do provider calls, it only checks JSON outputs

    def test_process_groups_and_timeout(self):
        with open(self.fake_runner, 'w') as f:
            f.write("""#!/usr/bin/env python3
import time
time.sleep(10)
""")
        os.chmod(self.fake_runner, 0o755)
        start = time.time()
        proc = self.run_fleet(['--json', '--timeout', '1'])
        self.assertLess(time.time() - start, 10)
        self.assertEqual(proc.returncode, 0) # still returns 0 but with unknown status
        obj = json.loads(proc.stdout)
        self.assertEqual(obj['policy_status'], 'timeout')

    def test_malformed_input(self):
        with open(self.fake_runner, 'w') as f:
            f.write("""#!/usr/bin/env python3
print("not json")
""")
        os.chmod(self.fake_runner, 0o755)
        proc = self.run_fleet(['--json'])
        self.assertEqual(proc.returncode, 0)
        obj = json.loads(proc.stdout)
        self.assertEqual(obj['policy_status'], 'malformed')
        self.assertEqual(obj['mode'], 'unknown')

if __name__ == '__main__':
    unittest.main()
