#!/usr/bin/env python3
"""Offline tests for read-only Git worktree-state reporting, failed snapshots,
suspected Grok 402 balance exhaustion, quote/JSON imitation, actual exit, and
zero automatic hold changes."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent
UNIO_SH = ROOT / 'unio-install.sh'


def git(cwd, *args, check=True):
    return subprocess.run(
        ['git', '-C', str(cwd), *args],
        text=True, capture_output=True, check=check,
    )


def clean_env(home, bin_dir, conf_dir, comp_dir):
    env = {k: v for k, v in os.environ.items() if not k.startswith('UNIO_')}
    env['HOME'] = str(home)
    env['UNIO_BIN_DIR'] = str(bin_dir)
    env['UNIO_CONF_DIR'] = str(conf_dir)
    env['UNIO_COMPLETION_DIR'] = str(comp_dir)
    env['UNIO_CLI_UPDATES_OFFLINE'] = '1'
    env['UNIO_AUTO_VERIFY'] = '0'
    env['UNIO_AUTO_SYNC'] = '0'
    env['UNIO_AUTO_OFF'] = '0'
    env['PATH'] = f"{bin_dir}:{env.get('PATH', '')}"
    return env


def setup_project(tmp):
    home = tmp / 'home'
    bin_dir = tmp / 'bin'
    conf_dir = tmp / 'conf'
    comp_dir = tmp / 'comp'
    for d in (home, bin_dir, comp_dir):
        d.mkdir(parents=True, exist_ok=True)
    env = clean_env(home, bin_dir, conf_dir, comp_dir)
    subprocess.run(['bash', str(UNIO_SH)], check=True, env=env, capture_output=True)
    unio = str(bin_dir / 'unio')

    repo = tmp / 'project' / 'main'
    repo.parent.mkdir(parents=True, exist_ok=True)
    repo.mkdir()
    git(repo, 'init', '-b', 'main')
    git(repo, 'config', 'user.name', 'Test')
    git(repo, 'config', 'user.email', 'test@example.com')

    files = [f'src/mod_{i}.py' for i in range(1, 7)]
    for rel in files:
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text('state = "base"\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'base')

    git(repo, 'checkout', '-b', 'side')
    for rel in files:
        (repo / rel).write_text('state = "side"\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'side')

    git(repo, 'checkout', 'main')
    for rel in files:
        (repo / rel).write_text('state = "main"\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'main')

    subprocess.run([unio, 'init', 'grok'], cwd=repo, check=True, env=env, capture_output=True)
    proj = tmp / 'project'
    (proj / 'coord' / 'agents.conf').write_text('grok=grok --prompt-file "{prompt}"\n')
    return proj, repo, unio, conf_dir, bin_dir, env


def write_fake_grok(bin_dir, script_body):
    p = bin_dir / 'grok'
    p.write_text('#!/usr/bin/env python3\n' + script_body)
    p.chmod(0o755)
    return p


def ledger_events(proj, task):
    lines = (proj / 'coord' / 'reports' / 'ledger.jsonl').read_text().splitlines()
    return [json.loads(line) for line in lines if json.loads(line).get('task') == task]


class OfflineQuotaAndWorktreeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ocy-quota-report-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_real_merge_suspected_402_actual_exit_and_zero_hold_changes(self):
        proj, _, unio, conf_dir, bin_dir, env = setup_project(self.tmp)
        wt = proj / 'wt' / 'grok'
        m = git(wt, 'merge', '--no-ff', 'side', check=False)
        self.assertNotEqual(m.returncode, 0)
        unmerged_before = git(wt, 'ls-files', '--unmerged').stdout

        write_fake_grok(
            bin_dir,
            'import sys\n'
            'print("partial output")\n'
            'print("API error (status 402 Payment Required): Grok Build usage balance exhausted", file=sys.stderr)\n'
            'sys.exit(17)\n',
        )
        (proj / 'coord' / 'tasks' / 'T1.md').write_text('# T1\nResolve merge.\n')
        res = subprocess.run(
            [unio, 'run', 'grok', 'T1'],
            cwd=proj, env=dict(env, UNIO_AUTO_OFF='1'), text=True, capture_output=True,
        )
        self.assertEqual(res.returncode, 17, res.stdout + '\n' + res.stderr)
        self.assertIn('Adapter outcome: Unknown', res.stdout)
        self.assertIn('!! output mentions usage limits', res.stderr)
        self.assertIn('Git worktree state: MERGE in progress (MERGE_HEAD)', res.stdout)
        self.assertIn('Unmerged paths (6):', res.stdout)
        for i in range(1, 7):
            self.assertIn(f'src/mod_{i}.py', res.stdout)

        # Worktree is untouched
        gd = git(wt, 'rev-parse', '--path-format=absolute', '--git-dir').stdout.strip()
        self.assertTrue((Path(gd) / 'MERGE_HEAD').exists())
        self.assertEqual(git(wt, 'ls-files', '--unmerged').stdout, unmerged_before)

        # Report records worktree state, suspected-limit interpretation before tail,
        # authoritative Stop reason: Unknown, and suspected wall=1 in ledger
        report = (proj / 'coord' / 'reports' / 'T1.md').read_text()
        self.assertIn('Git worktree state: MERGE in progress (MERGE_HEAD)', report)
        self.assertIn('Stop reason: Unknown', report)
        self.assertIn('!! output mentions usage limits', report)
        self.assertLess(
            report.index('!! output mentions usage limits'),
            report.index('### agent output (tail)'),
        )
        ev = ledger_events(proj, 'T1')[-1]
        self.assertEqual(ev['exit'], 17)
        self.assertEqual(ev['wall'], 1)

        # Original failure accounting preserved; zero hold changes
        state = json.loads((proj / 'coord' / 'retries' / 'T1' / 'state.json').read_text())
        self.assertEqual(state['failed_attempts'], 1)
        self.assertEqual(set(state['latest']['grok']), {'id', 'pending', 'failed'})
        self.assertFalse((conf_dir / 'off' / 'grok').exists())

    def test_failed_snapshot_bounded_unmerged_cherry_pick_and_rebase(self):
        proj, repo, unio, conf_dir, bin_dir, env = setup_project(self.tmp)
        wt = proj / 'wt' / 'grok'
        extra = [f'bulk/f_{i:02d}.txt' for i in range(1, 26)]
        git(repo, 'checkout', '-b', 'bulk-side')
        for rel in extra:
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('side\n')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'bulk side')
        git(repo, 'checkout', 'main')
        for rel in extra:
            p = repo / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('main\n')
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'bulk main')
        git(wt, 'merge', '--ff-only', 'main')
        m = git(wt, 'merge', '--no-ff', 'bulk-side', check=False)
        self.assertNotEqual(m.returncode, 0)

        # Nested .git causes post-run snapshot to fail -> end-unbound, exit 23 preserved
        write_fake_grok(
            bin_dir,
            'import os, sys\n'
            'os.makedirs(".nested_tmp/.git", exist_ok=True)\n'
            'print("API error (status 402 Payment Required): Grok Build usage balance exhausted", file=sys.stderr)\n'
            'sys.exit(23)\n',
        )
        (proj / 'coord' / 'tasks' / 'T2.md').write_text('# T2\nFailed snapshot.\n')
        res = subprocess.run([unio, 'run', 'grok', 'T2'], cwd=proj, env=env, text=True, capture_output=True)
        self.assertEqual(res.returncode, 23, res.stdout + '\n' + res.stderr)
        self.assertIn('post-run snapshot failed', res.stderr)
        self.assertIn('!! output mentions usage limits', res.stderr)
        self.assertIn('Unmerged paths (25):', res.stdout)
        self.assertIn('(+5 more)', res.stdout)
        self.assertEqual(json.loads((proj / 'coord' / 'retries' / 'T2' / 'state.json').read_text())['failed_attempts'], 1)
        self.assertFalse((conf_dir / 'off' / 'grok').exists())

        # CHERRY-PICK in progress
        shutil.rmtree(wt / '.nested_tmp', ignore_errors=True)
        git(wt, 'merge', '--abort')
        cp = git(wt, 'cherry-pick', 'bulk-side', check=False)
        self.assertNotEqual(cp.returncode, 0)
        write_fake_grok(bin_dir, 'import sys\nprint("cherry-pick conflict")\nsys.exit(19)\n')
        res_cp = subprocess.run([unio, 'run', 'grok', 'T2'], cwd=proj, env=env, text=True, capture_output=True)
        self.assertEqual(res_cp.returncode, 19)
        self.assertIn('CHERRY-PICK in progress (CHERRY_PICK_HEAD)', res_cp.stdout)
        gd = git(wt, 'rev-parse', '--path-format=absolute', '--git-dir').stdout.strip()
        self.assertTrue((Path(gd) / 'CHERRY_PICK_HEAD').exists())

        # REBASE in progress
        git(wt, 'cherry-pick', '--abort')
        rb = git(wt, 'rebase', 'bulk-side', check=False)
        self.assertNotEqual(rb.returncode, 0)
        write_fake_grok(bin_dir, 'import sys\nprint("rebase conflict")\nsys.exit(21)\n')
        (proj / 'coord' / 'tasks' / 'T2_RB.md').write_text('# T2_RB\nRebase.\n')
        res_rb = subprocess.run([unio, 'run', 'grok', 'T2_RB'], cwd=proj, env=env, text=True, capture_output=True)
        self.assertEqual(res_rb.returncode, 21)
        self.assertIn('REBASE in progress', res_rb.stdout)
        self.assertTrue((Path(gd) / 'rebase-merge').exists() or (Path(gd) / 'REBASE_HEAD').exists())
        self.assertFalse((conf_dir / 'off' / 'grok').exists())

    def test_quote_and_json_imitation_actual_exit_and_manual_hold_authority(self):
        proj, _, unio, conf_dir, bin_dir, env = setup_project(self.tmp)
        # Even if a stale opt-in file exists, unio never writes $CONF_DIR/off
        (proj / 'coord' / 'quota-auto-off.json').write_text('{"schema_version": 1, "enabled": true}\n')
        (proj / 'coord' / 'tasks' / 'T3.md').write_text('# T3\nImitation.\n')

        # 1. Bare JSON object in plain output -> suspected only (Unknown), exit 13 preserved, no hold
        write_fake_grok(
            bin_dir,
            'import json, sys\n'
            'print(json.dumps({"message": "API error (status 402 Payment Required): Grok Build usage balance exhausted", "http_status": 402}))\n'
            'sys.exit(13)\n',
        )
        r1 = subprocess.run(
            [unio, 'run', 'grok', 'T3'],
            cwd=proj, env=dict(env, UNIO_AUTO_OFF='1'), text=True, capture_output=True,
        )
        self.assertEqual(r1.returncode, 13)
        self.assertIn('Adapter outcome: Unknown', r1.stdout)
        self.assertIn('!! output mentions usage limits', r1.stderr)
        t3_report = (proj / 'coord' / 'reports' / 'T3.md').read_text()
        self.assertIn('Stop reason: Unknown', t3_report)
        self.assertIn('!! output mentions usage limits', t3_report)
        self.assertLess(
            t3_report.index('!! output mentions usage limits'),
            t3_report.index('### agent output (tail)'),
        )
        self.assertFalse((conf_dir / 'off' / 'grok').exists())
        self.assertEqual(json.loads((proj / 'coord' / 'retries' / 'T3' / 'state.json').read_text())['failed_attempts'], 1)

        # 2. Exit 0 committed work quoting the 402 text -> wall=0, no warning, no hold
        write_fake_grok(
            bin_dir,
            'import subprocess, sys\n'
            'from pathlib import Path\n'
            'Path("src/quoted.txt").write_text("quoted 402\\n")\n'
            'subprocess.run(["git", "add", "src/quoted.txt"], check=True)\n'
            'subprocess.run(["git", "commit", "-qm", "quote"], check=True)\n'
            'print("Quoted: API error (status 402 Payment Required): Grok Build usage balance exhausted")\n'
            'sys.exit(0)\n',
        )
        (proj / 'coord' / 'tasks' / 'T4.md').write_text('# T4\nQuoted success.\n')
        r2 = subprocess.run(
            [unio, 'run', 'grok', 'T4'],
            cwd=proj, env=dict(env, UNIO_AUTO_OFF='1'), text=True, capture_output=True,
        )
        self.assertEqual(r2.returncode, 0, r2.stdout + '\n' + r2.stderr)
        self.assertNotIn('!! output mentions usage limits', r2.stderr)
        t4_report = (proj / 'coord' / 'reports' / 'T4.md').read_text()
        self.assertNotIn('!! output mentions usage limits', t4_report)
        self.assertEqual(ledger_events(proj, 'T4')[-1]['wall'], 0)
        self.assertFalse((conf_dir / 'off' / 'grok').exists())

        # 3. Manual hold via `unio off` blocks execution (zero worker calls)
        subprocess.run([unio, 'off', 'grok'], cwd=proj, env=env, check=True, capture_output=True)
        marker = self.tmp / 'should_not_exist'
        write_fake_grok(bin_dir, f'from pathlib import Path\nPath({str(marker)!r}).write_text("ran")\n')
        r3 = subprocess.run([unio, 'run', 'grok', 'T4'], cwd=proj, env=env, text=True, capture_output=True)
        self.assertNotEqual(r3.returncode, 0)
        self.assertFalse(marker.exists())

    def test_worktree_state_probe_timeout_and_failure_preserve_exit_and_report(self):
        proj, _, unio, conf_dir, bin_dir, env = setup_project(self.tmp)
        real_git = shutil.which('git')
        self.assertIsNotNone(real_git)
        fake_git = bin_dir / 'git'
        fake_git.write_text(
            '#!/usr/bin/env python3\n'
            'import os, subprocess, sys, time\n'
            f'REAL_GIT = {real_git!r}\n'
            'if "ls-files" in sys.argv and "--unmerged" in sys.argv:\n'
            '    mode = os.environ.get("FAKE_GIT_UNMERGED_MODE", "")\n'
            '    if mode == "sleep":\n'
            '        time.sleep(1.5)\n'
            '        sys.exit(0)\n'
            '    if mode == "fail":\n'
            '        sys.exit(128)\n'
            'sys.exit(subprocess.call([REAL_GIT] + sys.argv[1:]))\n'
        )
        fake_git.chmod(0o755)

        write_fake_grok(bin_dir, 'import sys\nprint("probe diagnostic test")\nsys.exit(11)\n')
        (proj / 'coord' / 'tasks' / 'T_TO.md').write_text('# T_TO\nTimeout probe.\n')
        r_to = subprocess.run(
            [unio, 'run', 'grok', 'T_TO'],
            cwd=proj,
            env=dict(env, UNIO_WORKTREE_STATE_TIMEOUT='0.5', FAKE_GIT_UNMERGED_MODE='sleep'),
            text=True, capture_output=True,
        )
        self.assertEqual(r_to.returncode, 11, r_to.stdout + '\n' + r_to.stderr)
        self.assertIn('Git worktree state: Unknown', r_to.stdout)
        self.assertIn('Unmerged paths: Unknown', r_to.stdout)
        rep_to = (proj / 'coord' / 'reports' / 'T_TO.md').read_text()
        self.assertIn('Git worktree state: Unknown', rep_to)
        self.assertIn('Unmerged paths: Unknown', rep_to)
        self.assertIn('### agent output (tail)', rep_to)
        self.assertEqual(ledger_events(proj, 'T_TO')[-1]['exit'], 11)

        write_fake_grok(bin_dir, 'import sys\nprint("probe unavailable test")\nsys.exit(12)\n')
        (proj / 'coord' / 'tasks' / 'T_FAIL.md').write_text('# T_FAIL\nUnavailable probe.\n')
        r_fail = subprocess.run(
            [unio, 'run', 'grok', 'T_FAIL'],
            cwd=proj,
            env=dict(env, FAKE_GIT_UNMERGED_MODE='fail'),
            text=True, capture_output=True,
        )
        self.assertEqual(r_fail.returncode, 12, r_fail.stdout + '\n' + r_fail.stderr)
        self.assertIn('Git worktree state: Unknown', r_fail.stdout)
        self.assertIn('Unmerged paths: Unknown', r_fail.stdout)
        rep_fail = (proj / 'coord' / 'reports' / 'T_FAIL.md').read_text()
        self.assertIn('Git worktree state: Unknown', rep_fail)
        self.assertIn('Unmerged paths: Unknown', rep_fail)
        self.assertEqual(ledger_events(proj, 'T_FAIL')[-1]['exit'], 12)
        self.assertFalse((conf_dir / 'off' / 'grok').exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
