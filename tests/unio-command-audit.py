#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only
"""Installed, offline static audit fixtures: configured commands never run."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]
SCRATCH = REPO / '../../tmp/unio-next/command-audit-sol-low-20261013'


class CommandAudit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        cls.tmp = tempfile.TemporaryDirectory(prefix='fixtures-', dir=SCRATCH)
        cls.root = Path(cls.tmp.name).resolve()
        cls.bin = cls.root / 'bin with spaces'
        cls.conf = cls.root / 'configuration'
        cls.outside = cls.root / 'outside'
        cls.outside.mkdir()
        cls.env = dict(os.environ, UNIO_BIN_DIR=str(cls.bin), UNIO_CONF_DIR=str(cls.conf),
                       UNIO_COMPLETION_DIR=str(cls.root / 'completion'), TMPDIR=str(cls.root),
                       UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0')
        subprocess.run(['bash', str(REPO / 'unio-install.sh')], env=cls.env, cwd=cls.outside,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=60)
        cls.unio = cls.bin / 'unio'
        # Explicit offline Bash mocks. Any accidental CLI invocation records
        # evidence; it cannot reach a real provider, auth store or network.
        cls.calls = cls.root / 'provider-called'
        cls.env['AUDIT_CALLS'] = str(cls.calls)
        for name in ('codex', 'claude', 'opencode', 'grok', 'agy', 'vibe', 'copilot', 'wrapper'):
            p = cls.bin / name
            p.write_text('#!/usr/bin/env bash\nprintf "called\\n" >> "$AUDIT_CALLS"\nexit 91\n')
            p.chmod(0o755)
        cls.env['PATH'] = str(cls.bin) + os.pathsep + os.environ['PATH']
        cls.defaults = (cls.conf / 'agents.conf').read_bytes()
        cls.project = cls.root / 'project with spaces'
        (cls.project / 'coord').mkdir(parents=True)
        (cls.project / 'wt' / 'worker').mkdir(parents=True)
        (cls.project / 'coord' / 'STOP').write_text('frozen STOP\n')
        (cls.project / 'coord' / 'base').write_text('unchanged\n')
        (cls.project / 'coord' / 'work-policy.json').write_text('{"sentinel":"frozen"}\n')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def setUp(self):
        cfg = self.conf / 'agents.conf'
        if cfg.is_symlink() or not cfg.is_file():
            if cfg.exists() or cfg.is_symlink(): cfg.unlink()
        cfg.write_bytes(self.defaults)
        override = self.project / 'coord' / 'agents.conf'
        if override.exists() or override.is_symlink(): override.unlink()
        self.assertFalse(self.calls.exists(), 'configured command was executed')

    def run_audit(self, *args, cwd=None, expected=0):
        p = subprocess.run([str(self.unio), 'doctor', *args], env=self.env,
                           cwd=cwd or self.outside, capture_output=True, timeout=10)
        self.assertEqual(p.returncode, expected, (p.stdout, p.stderr))
        self.assertFalse(self.calls.exists(), 'configured command was executed')
        return p

    def audit(self, text):
        (self.conf / 'agents.conf').write_text(text)
        return json.loads(self.run_audit('--commands', '--json').stdout)

    def test_defaults_installed_smoke(self):
        p = self.run_audit('--commands', '--json')
        d = json.loads(p.stdout)
        self.assertEqual(d['schema_version'], 1)
        self.assertEqual(d['source'], 'local_static')
        for k in ('authentication', 'capacity', 'effective_model', 'effective_effort'):
            self.assertEqual(d[k], 'Unknown')
        rows = {a['alias']: a for a in d['agents']}
        for name, transport in [('claude','stdin'),('codex','stdin'),('opencode','file'),('grok','file'),('antigravity','file_pointer')]:
            self.assertEqual(rows[name]['transport'], transport)
        human = self.run_audit('--commands').stdout.decode()
        self.assertIn('not readiness or compatibility proof', human)
        for row in d['agents']:
            self.assertIn(row['alias']+': tool='+row['tool'], human)
            for issue in row['issues']: self.assertIn(issue['code'], human)

    def test_requested_selectors_and_paths(self):
        d = self.audit('sol="/arbitrary path/codex" exec -m gpt-6.1-sol -c \'model_reasoning_effort="low"\' - < "$TASKFILE"\n'
                       'go=opencode run --auto --model=opencode-go/glm-5.3 --variant high --file "${TASKFILE}"\n'
                       'balance=copilot --model auto-balance\n')
        a,b,c = d['agents']
        self.assertEqual((a['tool'],a['requested_model'],a['requested_effort'],a['transport']), ('codex','gpt-6.1-sol','low','stdin'))
        self.assertEqual((b['requested_model'],b['requested_effort'],b['transport']), ('opencode-go/glm-5.3','high','file'))
        self.assertEqual(c['requested_model'], 'auto-balance')
        self.assertIn('auto_balance', {i['code'] for i in c['issues']})
        self.assertNotIn('/arbitrary path', json.dumps(d))

    def test_legacy_and_missing_transport(self):
        d = self.audit('legacy=codex exec "$(cat "$TASKFILE")"\nold=opencode run --dangerously-skip-permissions --file "$TASKFILE"\nmissing=codex exec -m gpt-6.1-sol\n')
        codes = [{i['code'] for i in a['issues']} for a in d['agents']]
        self.assertIn('whole_taskfile_argv', codes[0])
        self.assertIn('command_unknown', codes[0])
        self.assertIn('legacy_opencode_permission', codes[1])
        self.assertIn('transport_unknown', codes[2])

    def test_poison_and_wrappers_unknown(self):
        sentinel = self.root / 'poison executed'
        forms = [f'codex exec "$(touch \'{sentinel}\')"', f'codex exec `touch "{sentinel}"`',
                 f'API_TOKEN=PRIVATE codex exec -', 'env KEY=PRIVATE codex exec -',
                 'wrapper --model gpt-6.1-sol', '/private/wrapper codex exec -',
                 'codex exec - | wrapper', 'codex exec - && wrapper',
                 'bash -c "codex exec -"', '$(codex) exec -', 'codex exec > /private/output']
        d = self.audit(''.join(f'alias{i}={form}\n' for i,form in enumerate(forms)))
        for row in d['agents']:
            self.assertEqual(row['tool'], 'Unknown')
            self.assertEqual(row['requested_model'], 'Unknown')
        self.assertFalse(sentinel.exists())
        self.assertNotIn('PRIVATE', json.dumps(d))
        self.assertNotIn('/private/', json.dumps(d))

    def test_secrets_and_unsafe_selectors_not_reflected(self):
        secrets = ['sk-secret-value', 'account@example.invalid', 'api_token=PRIVATE', '\u001b[31mBAD', 'abc123TOKEN']
        for secret in secrets:
            text = f'sol=codex exec --model "{secret}" --api-key "{secret}" - < "$TASKFILE"\n'
            (self.conf / 'agents.conf').write_text(text)
            p = self.run_audit('--commands', '--json', expected=2 if '\u001b' in secret else 0)
            self.assertNotIn(secret.encode(), p.stdout + p.stderr)
            if p.returncode == 0: self.assertEqual(json.loads(p.stdout)['agents'][0]['requested_model'], 'Unknown')

    def test_ambiguous_effort_and_model(self):
        forms = ['codex exec --effort high', 'codex exec -c model_reasoning_effort=high -c model_reasoning_effort=low',
                 'opencode run --variant PRIVATE', 'claude -p --effort high --thinking',
                 'codex exec -m gpt-6.1-sol -m gpt-6.1-sol', 'codex exec -m gpt-6.1-sol -c profile=PRIVATE']
        d = self.audit(''.join(f'alias{i}={form}\n' for i,form in enumerate(forms)))
        for row in d['agents'][:4]:
            self.assertEqual(row['requested_effort'], 'Unknown')
            self.assertIn('effort_ambiguous', {i['code'] for i in row['issues']})
        for row in d['agents'][4:]: self.assertEqual(row['requested_model'], 'Unknown')

    def test_strict_arguments(self):
        for args in [('--json',),('--commands','--commands'),('--commands','--json','extra'),
                     ('--commands','--json','--json'),('--commands','extra'),('extra',),('--help',)]:
            self.run_audit(*args, expected=2)

    def test_malformed_bounded(self):
        forms = ['missing_equals', 'same=codex exec\nsame=claude -p\n', 'sol=codex "unterminated',
                 'sol=\n', 'unsafe alias=codex exec\n', 'token=codex exec\n',
                 'sol='+('x'*4097), '#'+('x'*65536), '\n'*513,
                 ''.join(f'a{i}=wrapper\n' for i in range(129)), 'sol=codex exec\x00bad']
        for form in forms:
            (self.conf / 'agents.conf').write_text(form)
            p = self.run_audit('--commands','--json', expected=2)
            self.assertEqual(p.stdout,b'')
            self.assertIn(b'over-bound input', p.stderr)
        (self.conf / 'agents.conf').write_bytes(b'\xff')
        self.run_audit('--commands',expected=2)

    def test_nonregular_missing_and_symlink(self):
        cfg = self.conf / 'agents.conf'
        cfg.unlink()
        self.run_audit('--commands',expected=2)
        cfg.symlink_to(self.root / 'absent')
        self.run_audit('--commands',expected=2)
        cfg.unlink(); os.mkfifo(cfg)
        self.run_audit('--commands',expected=2)
        cfg.unlink(); cfg.symlink_to(self.project / 'coord' / 'base')
        self.run_audit('--commands',expected=2)

    def test_override_stop_and_state_preservation(self):
        override = self.project / 'coord' / 'agents.conf'
        override.write_text('projectalias=claude -p --effort high < "$TASKFILE"\n')
        (self.conf / 'off').mkdir(exist_ok=True)
        (self.conf / 'off' / 'projectalias').write_text('PRIVATE BENCH\n')
        def snapshot():
            return {str(p.relative_to(self.root)): (p.stat().st_mode,hashlib.sha256(p.read_bytes()).hexdigest())
                    for base in (self.project,self.conf) for p in base.rglob('*') if p.is_file()}
        before = snapshot()
        d = json.loads(self.run_audit('--commands','--json',cwd=self.project / 'wt' / 'worker').stdout)
        self.assertEqual([a['alias'] for a in d['agents']], ['projectalias'])
        self.run_audit('--commands',cwd=self.project)
        self.assertEqual(before,snapshot())
        override.unlink()
        d = json.loads(self.run_audit('--commands','--json',cwd=self.project).stdout)
        self.assertIn('codex', [a['alias'] for a in d['agents']])
        override.symlink_to(self.root / 'missing')
        self.run_audit('--commands',cwd=self.project,expected=2)

    def test_existing_agents_json_unchanged(self):
        before = subprocess.run([str(self.unio),'agents','--json'],env=self.env,cwd=self.outside,capture_output=True,check=True).stdout
        self.run_audit('--commands','--json')
        after = subprocess.run([str(self.unio),'agents','--json'],env=self.env,cwd=self.outside,capture_output=True,check=True).stdout
        self.assertEqual(before,after)

    def test_other_installer_payloads_byte_identical(self):
        base = subprocess.run(['git','show','425a9e36845b7e37917f922a91ad2773f7eee730:unio-install.sh'],cwd=REPO,capture_output=True,check=True).stdout
        current = (REPO / 'unio-install.sh').read_bytes()
        def blocks(data):
            import re
            return {m.group(1): m.group(2) for m in re.finditer(rb"<<'([A-Z_0-9]+)'\n(.*?)\n\1(?:\n|$)",data,re.S)}
        old,new = blocks(base),blocks(current)
        self.assertEqual(old.keys(),new.keys())
        for name in old:
            if name != b'UNIO_BIN_EOF': self.assertEqual(old[name],new[name],name)
        # Embedded CLI's other adapters remain exactly unchanged too.
        old,new = blocks(old[b'UNIO_BIN_EOF']),blocks(new[b'UNIO_BIN_EOF'])
        for name in old:
            if name not in (b'QUALITY_PY', b'HELP'): self.assertEqual(old[name],new[name],name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
