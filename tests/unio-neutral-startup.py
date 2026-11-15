#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Test neutral fresh-start lead instructions, tier terminology, and custom role preservation."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
INSTALLER = ROOT / 'unio-install.sh'
passed = [0]


def check(label, condition=True):
    if not condition:
        print('FAIL ' + label, file=sys.stderr)
        sys.exit(1)
    passed[0] += 1
    print('  ok %s' % label)


def run(cmd, env, cwd=None):
    return subprocess.run(cmd, env=env, cwd=cwd, capture_output=True, text=True)


def test_neutral_fresh_install_and_tiers():
    """Verify fresh install produces neutral MASTER, correct tier table, and retains legal credit."""
    with tempfile.TemporaryDirectory(prefix='neutral-fresh-') as tmp:
        base = Path(tmp)
        bin_dir = base / 'bin'
        conf_dir = base / 'conf'
        comp_dir = base / 'comp'
        scratch_dir = base / 'tmp'
        scratch_dir.mkdir(parents=True, exist_ok=True)

        env = dict(
            os.environ,
            UNIO_BIN_DIR=str(bin_dir),
            UNIO_CONF_DIR=str(conf_dir),
            UNIO_COMPLETION_DIR=str(comp_dir),
            TMPDIR=str(scratch_dir),
            UNIO_TEST_SCRATCH=str(scratch_dir),
            UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_SYNC='0',
            UNIO_AUTO_OFF='0',
            GIT_AUTHOR_NAME='test',
            GIT_COMMITTER_NAME='test',
            GIT_AUTHOR_EMAIL='test@example.invalid',
            GIT_COMMITTER_EMAIL='test@example.invalid',
        )

        res = run(['bash', str(INSTALLER)], env=env)
        check('fresh install succeeds', res.returncode == 0)

        master_tpl = conf_dir / 'templates' / 'MASTER.md'
        check('MASTER template installed', master_tpl.is_file())
        master_content = master_tpl.read_text(encoding='utf-8')

        # Neutral human-owner wording: no maintainer personal instructions
        check('MASTER does not contain maintainer personal name Daniel',
              'Daniel' not in master_content)
        check('MASTER uses neutral human owner wording',
              'human owner' in master_content or 'owner' in master_content)

        # Supported tooling vs unsupported guidance
        check('MASTER references unio score and unio experience',
              'unio score' in master_content and 'unio experience' in master_content)
        check('MASTER does not contain unsupported myapp guidance',
              'myapp' not in master_content)

        # CodeGraph only when indexed
        check('MASTER specifies CodeGraph only when indexed',
              'CodeGraph only when indexed' in master_content
              or ('CodeGraph' in master_content and '.codegraph/' in master_content))

        # Required markers and startup dashboard rules preserved
        check('MASTER preserves dashboard startup marker',
              '<!-- UNIO-DASHBOARD-STARTUP -->' in master_content)
        check('MASTER preserves work policy marker',
              '<!-- UNIO-WORK-POLICY -->' in master_content)
        check('MASTER does not assume owner approval already granted',
              'do not assume owner approval is already granted' in master_content
              or 'authorization' in master_content)

        # Work-modes tier table check
        work_modes_tpl = conf_dir / 'templates' / 'WORK-MODES.md'
        check('WORK-MODES template installed', work_modes_tpl.is_file())
        modes_content = work_modes_tpl.read_text(encoding='utf-8')
        check('coordination tier table uses medium for 2 workflows',
              '| `medium` | 2, including the lead |' in modes_content)
        check('coordination tier table balanced row corrected',
              '| `balanced` | 2, including the lead |' not in modes_content)
        check('balanced work mode remains intact',
              '| `balanced` | Deliver manageable feature batches' in modes_content)

        # Legal credit retained elsewhere in project files and templates
        protocol_tpl = conf_dir / 'templates' / 'PROTOCOL.md'
        check('PROTOCOL template installed', protocol_tpl.is_file())
        check('legal copyright attribution retained in PROTOCOL.md',
              'Daniel Mitev' in protocol_tpl.read_text(encoding='utf-8'))
        check('legal copyright attribution retained in installer header',
              'Daniel Mitev' in INSTALLER.read_text(encoding='utf-8'))


def test_unsafe_target_refusal():
    """Verify installer refuses symlink or hardlink for MASTER template."""
    with tempfile.TemporaryDirectory(prefix='neutral-unsafe-') as tmp:
        base = Path(tmp)
        bin_dir = base / 'bin'
        conf_dir = base / 'conf'
        comp_dir = base / 'comp'
        scratch_dir = base / 'tmp'
        scratch_dir.mkdir(parents=True, exist_ok=True)
        tpl_dir = conf_dir / 'templates'
        tpl_dir.mkdir(parents=True, exist_ok=True)

        env = dict(
            os.environ,
            UNIO_BIN_DIR=str(bin_dir),
            UNIO_CONF_DIR=str(conf_dir),
            UNIO_COMPLETION_DIR=str(comp_dir),
            TMPDIR=str(scratch_dir),
            UNIO_TEST_SCRATCH=str(scratch_dir),
            UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_SYNC='0',
            UNIO_AUTO_OFF='0',
        )

        # Symlink refusal
        master_target = tpl_dir / 'MASTER.md'
        master_target.symlink_to('/dev/null')
        res_sym = run(['bash', str(INSTALLER)], env=env)
        check('installer refuses symlinked MASTER template',
              res_sym.returncode != 0 and 'refusing unsafe master template file' in res_sym.stderr)

        # Hardlink refusal
        master_target.unlink()
        dummy = tpl_dir / 'dummy.txt'
        dummy.write_text('dummy\n', encoding='utf-8')
        os.link(dummy, master_target)
        res_hard = run(['bash', str(INSTALLER)], env=env)
        check('installer refuses hardlinked MASTER template',
              res_hard.returncode != 0 and 'refusing unsafe master template file' in res_hard.stderr)


def test_repeat_install_preserves_custom_master():
    """Verify repeat install preserves custom template MASTER.md."""
    with tempfile.TemporaryDirectory(prefix='neutral-repeat-') as tmp:
        base = Path(tmp)
        bin_dir = base / 'bin'
        conf_dir = base / 'conf'
        comp_dir = base / 'comp'
        scratch_dir = base / 'tmp'
        scratch_dir.mkdir(parents=True, exist_ok=True)

        env = dict(
            os.environ,
            UNIO_BIN_DIR=str(bin_dir),
            UNIO_CONF_DIR=str(conf_dir),
            UNIO_COMPLETION_DIR=str(comp_dir),
            TMPDIR=str(scratch_dir),
            UNIO_TEST_SCRATCH=str(scratch_dir),
            UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_SYNC='0',
            UNIO_AUTO_OFF='0',
        )

        # Initial install
        res = run(['bash', str(INSTALLER)], env=env)
        check('initial install succeeds', res.returncode == 0)

        master_tpl = conf_dir / 'templates' / 'MASTER.md'
        custom_content = '# Custom Organization Lead Instructions\nExplicit custom rules.\n'
        master_tpl.write_text(custom_content, encoding='utf-8')

        # Repeat install
        res_repeat = run(['bash', str(INSTALLER)], env=env)
        check('repeat install succeeds', res_repeat.returncode == 0)
        check('custom MASTER template preserved on repeat install',
              master_tpl.read_text(encoding='utf-8') == custom_content)


def test_project_init_preserves_custom_roles_and_routers():
    """Verify unio init preserves custom repo MASTER.md and custom router AGENTS.md."""
    with tempfile.TemporaryDirectory(prefix='neutral-init-') as tmp:
        base = Path(tmp)
        bin_dir = base / 'bin'
        conf_dir = base / 'conf'
        comp_dir = base / 'comp'
        scratch_dir = base / 'tmp'
        scratch_dir.mkdir(parents=True, exist_ok=True)
        repo_dir = base / 'my-repo'
        repo_dir.mkdir(parents=True, exist_ok=True)

        env = dict(
            os.environ,
            UNIO_BIN_DIR=str(bin_dir),
            UNIO_CONF_DIR=str(conf_dir),
            UNIO_COMPLETION_DIR=str(comp_dir),
            TMPDIR=str(scratch_dir),
            UNIO_TEST_SCRATCH=str(scratch_dir),
            UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_SYNC='0',
            UNIO_AUTO_OFF='0',
            GIT_AUTHOR_NAME='test',
            GIT_COMMITTER_NAME='test',
            GIT_AUTHOR_EMAIL='test@example.invalid',
            GIT_COMMITTER_EMAIL='test@example.invalid',
        )

        run(['bash', str(INSTALLER)], env=env)
        unio_bin = str(bin_dir / 'unio')

        # Setup git repository
        run(['git', 'init', '-q', '-b', 'main'], env=env, cwd=repo_dir)
        (repo_dir / 'README.md').write_text('# Test Repo\n', encoding='utf-8')
        run(['git', 'add', 'README.md'], env=env, cwd=repo_dir)
        run(['git', 'commit', '-qm', 'initial'], env=env, cwd=repo_dir)

        # Pre-populate custom project MASTER.md and custom AGENTS.md router
        custom_master = '# Custom Project MASTER\nOwner-specific instructions.\n'
        custom_agents = '# Project AGENTS router\nCustom agent definitions.\n'
        (repo_dir / 'MASTER.md').write_text(custom_master, encoding='utf-8')
        (repo_dir / 'AGENTS.md').write_text(custom_agents, encoding='utf-8')

        init_res = run([unio_bin, 'init', 'mock'], env=env, cwd=repo_dir)
        check('unio init exits 0', init_res.returncode == 0)

        # Custom project MASTER.md must retain custom text
        repo_master = (repo_dir / 'MASTER.md').read_text(encoding='utf-8')
        check('custom project MASTER.md content preserved',
              'Owner-specific instructions.' in repo_master)
        check('policy reference appended to custom MASTER.md',
              'UNIO-WORK-POLICY' in repo_master)
        check('review policy pointer appended once to custom MASTER.md',
              repo_master.count('<!-- UNIO-LEAD-REVIEW-POLICY -->') == 1
              and 'templates/LEAD-REVIEW-POLICY.md' in repo_master)
        reinit = run([unio_bin, 'init', 'mock'], env=env, cwd=repo_dir)
        repo_master_again = (repo_dir / 'MASTER.md').read_text(encoding='utf-8')
        check('repeat unio init keeps one review policy pointer',
              reinit.returncode == 0
              and repo_master_again.count('<!-- UNIO-LEAD-REVIEW-POLICY -->') == 1
              and repo_master_again.startswith(custom_master))

        # Custom project router AGENTS.md must NOT be replaced with symlink
        agents_path = repo_dir / 'AGENTS.md'
        check('custom AGENTS.md remains a regular file, not a symlink',
              agents_path.is_file() and not agents_path.is_symlink())
        check('custom AGENTS.md content preserved',
              'Custom agent definitions.' in agents_path.read_text(encoding='utf-8'))

        # Non-existing routers (e.g. CLAUDE.md) should be symlinks to MASTER.md
        claude_path = repo_dir / 'CLAUDE.md'
        check('unspecified router CLAUDE.md links to MASTER.md',
              claude_path.is_symlink() and os.readlink(claude_path) == 'MASTER.md')


PROVIDER_CLIS = ('claude', 'codex', 'agy', 'opencode', 'grok', 'vibe', 'copilot', 'gemini')


def test_review_policy_managed_refresh_preserves_custom_files():
    """Install twice offline: managed review policy refreshes, owner files stay byte-identical."""
    with tempfile.TemporaryDirectory(prefix='neutral-review-policy-') as tmp:
        base = Path(tmp)
        conf_dir = base / 'conf'
        scratch_dir = base / 'tmp'
        scratch_dir.mkdir(parents=True, exist_ok=True)
        stubs = base / 'stubs'
        stubs.mkdir()
        sentinel = base / 'provider-called'
        for name in PROVIDER_CLIS:
            stub = stubs / name
            stub.write_text('#!/bin/sh\necho "$0" >> "%s"\nexit 97\n' % sentinel, encoding='utf-8')
            stub.chmod(0o755)
        env = dict(
            os.environ,
            PATH=str(stubs) + os.pathsep + os.environ.get('PATH', ''),
            UNIO_BIN_DIR=str(base / 'bin'),
            UNIO_CONF_DIR=str(conf_dir),
            UNIO_COMPLETION_DIR=str(base / 'comp'),
            TMPDIR=str(scratch_dir),
            UNIO_TEST_SCRATCH=str(scratch_dir),
            UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_SYNC='0',
            UNIO_AUTO_OFF='0',
        )
        tpl = conf_dir / 'templates'
        canonical_policy = (ROOT / 'docs' / 'ai' / 'LEAD-REVIEW-POLICY.md').read_bytes()
        canonical_card = (ROOT / 'docs' / 'ai' / 'REVIEWER-STARTUP-CARD.md').read_bytes()

        res = run(['bash', str(INSTALLER)], env=env)
        check('review policy: fresh install succeeds', res.returncode == 0)
        check('review policy: installed policy byte-identical to canonical',
              (tpl / 'LEAD-REVIEW-POLICY.md').read_bytes() == canonical_policy)
        check('review policy: installed reviewer card byte-identical to canonical',
              (tpl / 'REVIEWER-STARTUP-CARD.md').read_bytes() == canonical_card)
        fresh_master = (tpl / 'MASTER.md').read_text(encoding='utf-8')
        check('review policy: fresh MASTER reading ritual points to installed policy',
              fresh_master.count('<!-- UNIO-LEAD-REVIEW-POLICY -->') == 1
              and '/templates/LEAD-REVIEW-POLICY.md' in fresh_master)

        custom = {
            tpl / 'MASTER.md': b'# Custom lead card\nKeep my review rules.\n',
            conf_dir / 'OWNER-WORKFLOW.md': b'# Owner workflow\nTwo external reviews for my team.\n',
            conf_dir / 'agents.conf': b'# owner routes\nmine=true < "$TASKFILE"\n',
        }
        for path, data in custom.items():
            path.write_bytes(data)
        (tpl / 'LEAD-REVIEW-POLICY.md').write_bytes(b'stale managed policy\n')

        res_again = run(['bash', str(INSTALLER)], env=env)
        check('review policy: repeat install succeeds', res_again.returncode == 0)
        for path, data in custom.items():
            check('review policy: repeat install keeps custom ' + path.name,
                  path.read_bytes() == data)
        check('review policy: repeat install refreshes managed policy',
              (tpl / 'LEAD-REVIEW-POLICY.md').read_bytes() == canonical_policy)
        check('review policy: installs made no provider CLI call', not sentinel.exists())

        # A symlinked managed policy target is refused rather than followed.
        outside = base / 'outside.md'
        outside.write_bytes(b'outside\n')
        (tpl / 'LEAD-REVIEW-POLICY.md').unlink()
        (tpl / 'LEAD-REVIEW-POLICY.md').symlink_to(outside)
        res_sym = run(['bash', str(INSTALLER)], env=env)
        check('review policy: symlinked managed policy refused, target untouched',
              res_sym.returncode != 0 and 'refusing unsafe role card file' in res_sym.stderr
              and outside.read_bytes() == b'outside\n')


def main():
    test_neutral_fresh_install_and_tiers()
    test_unsafe_target_refusal()
    test_repeat_install_preserves_custom_master()
    test_project_init_preserves_custom_roles_and_routers()
    test_review_policy_managed_refresh_preserves_custom_files()
    print('ok %d neutral startup assertions passed' % passed[0])


if __name__ == '__main__':
    main()
