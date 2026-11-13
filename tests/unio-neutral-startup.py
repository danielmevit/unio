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


def main():
    test_neutral_fresh_install_and_tiers()
    test_unsafe_target_refusal()
    test_repeat_install_preserves_custom_master()
    test_project_init_preserves_custom_roles_and_routers()
    print('ok %d neutral startup assertions passed' % passed[0])


if __name__ == '__main__':
    main()
