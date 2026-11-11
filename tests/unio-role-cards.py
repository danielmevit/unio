#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Test compact role startup cards embedding, template installation, init, and transport."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKER_CARD = ROOT / 'docs/ai/WORKER-STARTUP-CARD.md'
REVIEWER_CARD = ROOT / 'docs/ai/REVIEWER-STARTUP-CARD.md'
POINTER_LINE = (
    'Role card: use the matching role from the frozen task, with project coord/docs '
    'and installed templates fallback; task and current owner instructions prevail.\n'
)


class RoleCardsTest(unittest.TestCase):
    def setUp(self):
        self.worker_bytes = WORKER_CARD.read_bytes()
        self.reviewer_bytes = REVIEWER_CARD.read_bytes()

    def test_canonical_cards_properties(self):
        """Ensure canonical cards meet word count, encoding, and control requirements."""
        for card_path, name, min_words, max_words in (
            (WORKER_CARD, 'worker', 250, 700),
            (REVIEWER_CARD, 'reviewer', 250, 700),
        ):
            text = card_path.read_text(encoding='utf-8')
            self.assertTrue(text.endswith('\n'), f'{name} card must end with newline')
            self.assertNotIn('\r', text, f'{name} card must use LF line endings')
            words = text.split()
            self.assertGreaterEqual(len(words), min_words, f'{name} card has fewer than {min_words} words')
            self.assertLessEqual(len(words), max_words, f'{name} card exceeds {max_words} words')

        # Check operative control distinctions in WORKER-STARTUP-CARD.md
        worker_text = WORKER_CARD.read_text(encoding='utf-8')
        self.assertIn('commit coherent scoped checkpoints', worker_text)
        self.assertIn('save the declared report artifacts early', worker_text)
        self.assertIn('do not fabricate a code commit', worker_text)
        self.assertIn('STOP blocks new Unio admissions', worker_text)
        self.assertIn('it does not by itself cancel an already admitted Source', worker_text)
        self.assertIn('Startup and client settings do not prove effective serving identity or effort', worker_text)
        self.assertIn('Unknown without validated serving evidence', worker_text)

        # Check operative control distinctions in REVIEWER-STARTUP-CARD.md
        reviewer_text = REVIEWER_CARD.read_text(encoding='utf-8')
        self.assertIn('Reviewed source stays read-only', reviewer_text)
        self.assertIn('corrections require a separate assignment', reviewer_text)
        self.assertIn('STOP blocks new admissions', reviewer_text)
        self.assertIn('it is not automatic cancellation of an admitted review', reviewer_text)
        self.assertIn('mark effective model/effort Unknown unless observed', reviewer_text)
        self.assertIn('cross-lab acceptance', reviewer_text)
        self.assertIn("Do not count a free model's approval as", reviewer_text)

    def test_installer_contains_exact_canonical_cards(self):
        """The standalone installer must package the exact canonical cards bytes."""
        installer = (ROOT / 'unio-install.sh').read_text(encoding='utf-8')
        self.assertIn('# BEGIN EMBEDDED ROLE CARDS\n', installer)
        self.assertIn('# END EMBEDDED ROLE CARDS\n', installer)
        self.assertIn(self.worker_bytes.decode('utf-8'), installer)
        self.assertIn(self.reviewer_bytes.decode('utf-8'), installer)

    def test_embed_generator_check_catches_drift(self):
        """tools/embed-role-cards.py --check verifies identity and catches drift."""
        # 1. Normal check passes
        cp = subprocess.run(
            ['python3', '-B', str(ROOT / 'tools/embed-role-cards.py'), '--check'],
            cwd=ROOT, capture_output=True, text=True
        )
        self.assertEqual(cp.returncode, 0, cp.stderr)
        self.assertIn('embedded role cards: templates byte-identical', cp.stdout)

        # 2. Tampering detects drift
        installer_path = ROOT / 'unio-install.sh'
        original_installer = installer_path.read_text(encoding='utf-8')
        try:
            tampered = original_installer.replace(
                'Use this compact entry point with the lead-supplied frozen task',
                'TAMPERED ENTRY POINT WITH FROZEN TASK'
            )
            installer_path.write_text(tampered, encoding='utf-8')
            cp_tampered = subprocess.run(
                ['python3', '-B', str(ROOT / 'tools/embed-role-cards.py'), '--check'],
                cwd=ROOT, capture_output=True, text=True
            )
            self.assertNotEqual(cp_tampered.returncode, 0)
            self.assertIn('embedded role cards differ', cp_tampered.stderr)
        finally:
            installer_path.write_text(original_installer, encoding='utf-8')

    def test_installed_templates_and_unio_init(self):
        """unio init copies cards into coord/docs; rerun preserves custom cards."""
        with tempfile.TemporaryDirectory(prefix='role-cards-test-') as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / 'bin'
            conf_dir = tmp_path / 'conf'
            comp_dir = tmp_path / 'completion'
            repo_dir = tmp_path / 'my-repo'
            repo_dir.mkdir()

            env = dict(
                os.environ,
                UNIO_BIN_DIR=str(bin_dir),
                UNIO_CONF_DIR=str(conf_dir),
                UNIO_COMPLETION_DIR=str(comp_dir),
                UNIO_AUTO_VERIFY='0',
                UNIO_AUTO_SYNC='0',
                UNIO_AUTO_OFF='0',
                GIT_AUTHOR_NAME='test',
                GIT_COMMITTER_NAME='test',
                GIT_AUTHOR_EMAIL='test@example.invalid',
                GIT_COMMITTER_EMAIL='test@example.invalid',
            )

            # 1. Run installer
            subprocess.run(['bash', str(ROOT / 'unio-install.sh')], env=env, check=True, capture_output=True)

            # Templates must match exact canonical bytes
            tpl_worker = conf_dir / 'templates/WORKER-STARTUP-CARD.md'
            tpl_reviewer = conf_dir / 'templates/REVIEWER-STARTUP-CARD.md'
            self.assertTrue(tpl_worker.is_file())
            self.assertTrue(tpl_reviewer.is_file())
            self.assertEqual(tpl_worker.read_bytes(), self.worker_bytes)
            self.assertEqual(tpl_reviewer.read_bytes(), self.reviewer_bytes)

            # 2. Setup mock git repo
            subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=repo_dir, env=env, check=True)
            (repo_dir / 'file.txt').write_text('init\n')
            subprocess.run(['git', 'add', 'file.txt'], cwd=repo_dir, env=env, check=True)
            subprocess.run(['git', 'commit', '-qm', 'initial'], cwd=repo_dir, env=env, check=True)

            # 3. unio init
            unio_bin = str(bin_dir / 'unio')
            subprocess.run([unio_bin, 'init'], cwd=repo_dir, env=env, check=True, capture_output=True)

            coord_docs = tmp_path / 'coord/docs'
            proj_worker = coord_docs / 'WORKER-STARTUP-CARD.md'
            proj_reviewer = coord_docs / 'REVIEWER-STARTUP-CARD.md'
            self.assertTrue(proj_worker.is_file())
            self.assertTrue(proj_reviewer.is_file())
            self.assertEqual(proj_worker.read_bytes(), self.worker_bytes)
            self.assertEqual(proj_reviewer.read_bytes(), self.reviewer_bytes)

            # 4. Custom card preservation on rerun init
            custom_content = '# Custom Project Worker Card\nSpecific rules here.\n'
            proj_worker.write_text(custom_content, encoding='utf-8')
            subprocess.run([unio_bin, 'init'], cwd=repo_dir, env=env, check=True, capture_output=True)
            self.assertEqual(proj_worker.read_text(encoding='utf-8'), custom_content)
            self.assertEqual(proj_reviewer.read_bytes(), self.reviewer_bytes)

            # 5. Missing older cards tolerated:
            # If an older project deleted/lacks the cards, doctor and policy and run continue to work
            proj_worker.unlink()
            proj_reviewer.unlink()
            self.assertFalse(proj_worker.exists())
            self.assertFalse(proj_reviewer.exists())

            doc_res = subprocess.run([unio_bin, 'doctor'], cwd=repo_dir, env=env, capture_output=True, text=True)
            self.assertEqual(doc_res.returncode, 0, doc_res.stderr)

            pol_res = subprocess.run([unio_bin, 'policy', '--json'], cwd=repo_dir, env=env, capture_output=True, text=True)
            self.assertEqual(pol_res.returncode, 0, pol_res.stderr)

    def test_installer_safe_destination_checks(self):
        """Installer must refuse unsafe template destination directory or symlink."""
        with tempfile.TemporaryDirectory(prefix='role-cards-unsafe-') as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / 'bin'
            conf_dir = tmp_path / 'conf'
            comp_dir = tmp_path / 'completion'
            tpl_dir = conf_dir / 'templates'
            tpl_dir.mkdir(parents=True)

            env = dict(
                os.environ,
                UNIO_BIN_DIR=str(bin_dir),
                UNIO_CONF_DIR=str(conf_dir),
                UNIO_COMPLETION_DIR=str(comp_dir),
            )

            # Refuse symlink template file
            bad_card = tpl_dir / 'WORKER-STARTUP-CARD.md'
            bad_card.symlink_to('/dev/null')

            cp = subprocess.run(['bash', str(ROOT / 'unio-install.sh')], env=env, capture_output=True, text=True)
            self.assertNotEqual(cp.returncode, 0)
            self.assertIn('refusing unsafe role card file', cp.stderr)

    def test_effective_prompt_pointer_and_transport(self):
        """Policy snapshot transports one compact pointer and preserves original bytes."""
        with tempfile.TemporaryDirectory(prefix='role-cards-prompt-') as tmp:
            tmp_path = Path(tmp)
            bin_dir = tmp_path / 'bin'
            conf_dir = tmp_path / 'conf'
            comp_dir = tmp_path / 'completion'
            repo_dir = tmp_path / 'repo'
            repo_dir.mkdir()

            env = dict(
                os.environ,
                UNIO_BIN_DIR=str(bin_dir),
                UNIO_CONF_DIR=str(conf_dir),
                UNIO_COMPLETION_DIR=str(comp_dir),
                UNIO_AUTO_VERIFY='0',
                UNIO_AUTO_SYNC='0',
                UNIO_AUTO_OFF='0',
                GIT_AUTHOR_NAME='test',
                GIT_COMMITTER_NAME='test',
                GIT_AUTHOR_EMAIL='test@example.invalid',
                GIT_COMMITTER_EMAIL='test@example.invalid',
            )

            subprocess.run(['bash', str(ROOT / 'unio-install.sh')], env=env, check=True, capture_output=True)
            unio_bin = str(bin_dir / 'unio')

            subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=repo_dir, env=env, check=True)
            (repo_dir / 'init.txt').write_text('init\n')
            subprocess.run(['git', 'add', 'init.txt'], cwd=repo_dir, env=env, check=True)
            subprocess.run(['git', 'commit', '-qm', 'init'], cwd=repo_dir, env=env, check=True)
            subprocess.run([unio_bin, 'init'], cwd=repo_dir, env=env, check=True, capture_output=True)

            slot_path = tmp_path / 'coord/.locks/work-policy-slots/test-slot.json'
            slot_path.parent.mkdir(parents=True, exist_ok=True)
            slot_path.write_text('{"pid": 12345}\n')

            # Test run prompt snapshot
            task_file = tmp_path / 'coord/tasks/test-run.md'
            task_content = '# Goal: Implement feature\nExact original content\n'
            task_file.write_text(task_content, encoding='utf-8')

            installer = (ROOT / 'unio-install.sh').read_text(encoding='utf-8')
            policy_py = installer.split("<<'POLICY_PY'\n", 1)[1].split('\nPOLICY_PY\n', 1)[0]

            cp_run = subprocess.run(
                ['python3', '-', str(tmp_path), '_snapshot_sidecar', 'antigravity', str(slot_path), 'antigravity', 'test-run', 'run', str(task_file)],
                input=policy_py, cwd=repo_dir, env=env, capture_output=True, text=True
            )
            self.assertEqual(cp_run.returncode, 0, cp_run.stderr)
            run_prompt_path = Path(cp_run.stdout.strip())
            run_prompt = run_prompt_path.read_text(encoding='utf-8')

            self.assertTrue(run_prompt.startswith('# Unio work-policy header (effective prompt; the original task is unchanged)\n'))
            self.assertEqual(run_prompt.count(POINTER_LINE), 1)
            run_delim = '--- original run material follows ---\n'
            self.assertIn(run_delim, run_prompt)
            _, run_body = run_prompt.split(run_delim, 1)
            self.assertEqual(run_body, task_content)
            self.assertEqual(hashlib.sha256(run_body.encode()).hexdigest(), hashlib.sha256(task_content.encode()).hexdigest())

            # Test review prompt snapshot
            review_task_file = tmp_path / 'coord/tasks/test-rev.md'
            review_content = 'You are an independent code reviewer\nOriginal review instructions\n'
            review_task_file.write_text(review_content, encoding='utf-8')

            cp_rev = subprocess.run(
                ['python3', '-', str(tmp_path), '_snapshot_sidecar', 'codex', str(slot_path), 'codex', 'test-rev', 'review', str(review_task_file)],
                input=policy_py, cwd=repo_dir, env=env, capture_output=True, text=True
            )
            self.assertEqual(cp_rev.returncode, 0, cp_rev.stderr)
            rev_prompt_path = Path(cp_rev.stdout.strip())
            rev_prompt = rev_prompt_path.read_text(encoding='utf-8')

            self.assertTrue(rev_prompt.startswith('# Unio work-policy header (effective prompt; the original task is unchanged)\n'))
            self.assertEqual(rev_prompt.count(POINTER_LINE), 1)
            rev_delim = '--- original review material follows ---\n'
            self.assertIn(rev_delim, rev_prompt)
            _, rev_body = rev_prompt.split(rev_delim, 1)
            self.assertEqual(rev_body, review_content)
            self.assertEqual(hashlib.sha256(rev_body.encode()).hexdigest(), hashlib.sha256(review_content.encode()).hexdigest())


if __name__ == '__main__':
    unittest.main()
