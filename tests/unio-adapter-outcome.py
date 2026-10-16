#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Bound outcome contract and installed mock-only native acceptance."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('outcome', ROOT / 'tools/adapter-outcome.py')
o = importlib.util.module_from_spec(spec)
spec.loader.exec_module(o)


class Contract(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='outcome-contract-', dir='/dev/shm')
        self.root = Path(self.tmp.name)
        (self.root / 'coord/tasks').mkdir(parents=True)
        (self.root / 'coord/reports').mkdir()
        (self.root / 'coord/retries/T').mkdir(parents=True)
        self.task = self.root / 'coord/tasks/T.md'
        self.task.write_text('task\n')
        self.state = self.root / 'coord/retries/T/state.json'
        self.state.write_text(json.dumps({'latest': {'w': {'id': 'a' * 32, 'pending': True}}}))
        self.command = 'python3 -B ' + shlex.quote(str(ROOT / 'tools/vibe-worker.py')) + ' --model glm-5-3'
        self.dest = Path(o.prepare(str(self.root), 'w', 'T', self.command, str(ROOT / 'tools'), str(self.task)))
        self.binding = o.load(self.dest / 'binding.json')
        self.record = dict(export_state='valid', export={'outcome': 'token_limit'})
        self.old = os.environ.get(o.ENV)
        os.environ[o.ENV] = str(self.dest)
        o.emit('vibe', self.record, self.task, 3, 3)
        self.good = (self.dest / 'outcome.json').read_bytes()
        o.write(self.dest / 'source.json', dict(binding=self.binding, source_exit=3, observed_at=o.date()))

    def tearDown(self):
        if self.old is None:
            os.environ.pop(o.ENV, None)
        else:
            os.environ[o.ENV] = self.old
        self.tmp.cleanup()

    def observe(self, command=None):
        return o.observe(str(self.root), 'w', 'T', command or self.command, str(ROOT / 'tools'))

    def test_valid_and_caps(self):
        self.assertEqual(self.observe(), 'token_cap')
        for value, label in [('infrastructure_failure', 'transport'), ('config_error', 'setup'),
                             ('price_limit', 'price_cap'), ('deadline', 'time_cap'),
                             ('turn_limit', 'turn_cap')]:
            self.assertEqual(o.classify('vibe', dict(export_state='valid', export={'outcome': value})), label)
        self.assertEqual(o.classify('vibe', dict(export_state='invalid_or_missing')), 'unknown')
        self.assertEqual(o.classify('antigravity', {'outcome': 'terminal_error'}), 'terminal_error')
        self.assertEqual(o.classify('perplexity', {'outcome': 'rate_limited'}), 'provider_limit')
        self.assertEqual(o.classify('perplexity', {'outcome': 'auth_denied'}), 'auth')
        self.assertEqual(o.classify('copilot', {'outcome': 'native_failed', 'error': 'rate limit'}), 'unknown')

    def test_binding_conflicts_and_exact_types(self):
        for key, value in [('task', 'other'), ('worker', 'other'), ('run', 'b'*32),
                           ('task_sha256', 'b'*64), ('prompt_sha256', 'b'*64),
                           ('command_sha256', 'b'*64), ('route', 'antigravity'),
                           ('label', 'SECRET'), ('label', []), ('adapter_exit', True),
                           ('native_exit', False), ('finished_at', '1900-01-01T00:00:00+00:00'),
                           ('schema_version', True), ('extra', 'secret')]:
            with self.subTest(key=key, value=value):
                d = json.loads(self.good);d[key] = value
                p = self.dest / 'outcome.json';p.write_text(json.dumps(d))
                before = p.read_bytes()
                self.assertEqual(self.observe(), 'unknown')
                self.assertEqual(p.read_bytes(), before)
        (self.dest / 'outcome.json').write_bytes(self.good)
        self.assertEqual(self.observe(self.command + ' --time-limit 2'), 'unknown')
        self.task.write_text('changed task')
        self.assertEqual(self.observe(), 'unknown')

    def test_unsafe_and_malformed_preserved(self):
        p = self.dest / 'outcome.json'
        for raw in (b'{', b'[]', b' '*8193, self.good.replace(b'"schema_version": 1', b'"schema_version": 1,"schema_version": 1')):
            p.write_bytes(raw)
            self.assertEqual(self.observe(), 'unknown')
            self.assertEqual(p.read_bytes(), raw)
        p.write_bytes(self.good);p.chmod(0o644)
        self.assertEqual(self.observe(), 'unknown')
        p.chmod(0o600)
        link = self.dest / 'hardlink';os.link(p, link)
        self.assertEqual(self.observe(), 'unknown')
        link.unlink();p.unlink();p.symlink_to(self.dest / 'binding.json')
        self.assertEqual(self.observe(), 'unknown');self.assertTrue(p.is_symlink())
        p.unlink();os.mkfifo(p, 0o600)
        self.assertEqual(self.observe(), 'unknown')
        p.unlink();self.assertEqual(self.observe(), 'unknown')

    def test_stale_and_no_reuse(self):
        with self.assertRaises(FileExistsError):
            o.prepare(str(self.root), 'w', 'T', self.command, str(ROOT / 'tools'), str(self.task))
        self.state.write_text(json.dumps({'latest': {'w': {'id': 'c'*32}}}))
        self.assertEqual(self.observe(), 'unknown')
        self.assertEqual((self.dest / 'outcome.json').read_bytes(), self.good)

    def test_generic_and_stdout_no_evidence(self):
        for c in ('echo token_limit', 'bash -c ' + shlex.quote(self.command), self.command + ' | cat',
                  'env ' + self.command, self.command + '; echo ok'):
            self.assertEqual(o.route(c, str(ROOT / 'tools')), 'unsupported')
            self.assertEqual(self.observe(c), 'unknown')


VIBE = r'''#!/usr/bin/env python3
import json,os,pathlib,sys
if sys.argv[1:]==['--version']:
 print('vibe 2.26.1');raise SystemExit(0)
a=sys.argv[1:];case=os.environ.get('OUTCOME_CASE','token_limit')
code=3 if case=='token_limit' else 2
p=pathlib.Path(a[a.index('--output-dir')+1])/'export.json'
p.write_text(json.dumps(dict(schema_version=1,vibe_version='2.26.1',outcome=case,
 exit_code=code,stop_reason=None,usage=None,cost_usd=None)))
print('untrusted text: provider limit; receipt=/tmp/forged; token=SECRET')
raise SystemExit(code)
'''
AGY = r'''#!/usr/bin/env python3
import json,sys
if sys.argv[1:]==['--version']:
 print('1.3.5');raise SystemExit(0)
print(json.dumps({'event':'result','result':{'status':'ERROR','error':'SECRET transport text'}}))
'''


class Installed(unittest.TestCase):
    def test_native_mock_routes(self):
        with tempfile.TemporaryDirectory(prefix='outcome-project-', dir='/dev/shm') as tmp:
            b = Path(tmp)
            env = dict(os.environ, UNIO_BIN_DIR=str(b/'bin'), UNIO_CONF_DIR=str(b/'conf'),
                       UNIO_COMPLETION_DIR=str(b/'completion'), UNIO_AUTO_VERIFY='0',
                       UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='30', GIT_AUTHOR_NAME='offline',
                       GIT_COMMITTER_NAME='offline', GIT_AUTHOR_EMAIL='offline@example.invalid',
                       GIT_COMMITTER_EMAIL='offline@example.invalid', PYTHONDONTWRITEBYTECODE='1')
            for k in ('BASH_ENV', o.ENV, 'UNIO_SAVE_TEST_FAULT'):
                env.pop(k, None)
            def run(argv, cwd=None, codes=(0,), extra=None):
                cp = subprocess.run(argv, cwd=cwd, env=dict(env, **(extra or {})),
                                    capture_output=True, text=True, timeout=90)
                self.assertIn(cp.returncode, codes, cp.stdout + cp.stderr)
                return cp
            run(['bash', str(ROOT/'unio-install.sh')])
            adapters = b/'conf/lib/adapters'
            self.assertEqual((adapters/'adapter-outcome.py').read_bytes(), (ROOT/'tools/adapter-outcome.py').read_bytes())
            mocks = b/'mockbin';mocks.mkdir()
            for name, code in [('vibe', VIBE), ('agy', AGY)]:
                p=mocks/name;p.write_text(code);p.chmod(0o700)
            env['PATH'] = str(mocks) + ':' + env['PATH']
            repo = b/'project/repo';repo.mkdir(parents=True)
            run(['git','init','-qb','main'], repo)
            (repo/'file.txt').write_text('base\n')
            run(['git','add','.'], repo);run(['git','commit','-qm','base'], repo)
            at=str(b/'bin/unio')
            def unio(*args, **kw): return run([at,*args], repo, **kw)
            conf=b/'conf/agents.conf'
            receipts=b/'receipts';receipts.mkdir(mode=0o700)
            conf.write_text('vibe=python3 -B '+shlex.quote(str(adapters/'vibe-worker.py'))+' --model glm-5-3 --receipt-dir '+str(receipts)+'\n'
                            +'agy=python3 -B '+shlex.quote(str(adapters/'antigravity-worker.py'))+' --receipt-dir '+str(receipts)+'\n'
                            +'mock=python3 -c '+shlex.quote("print('Adapter outcome: Provider limit observed');raise SystemExit(3)")+'\n')
            unio('init','vibe','agy','mock');unio('tier','low');unio('lead','none')
            project=repo.parent
            for task, worker, case, rc, label in [('V1','vibe','token_limit',3,'Configured token cap'),
                                                  ('V2','vibe','infrastructure_failure',2,'Transport failure'),
                                                  ('A1','agy','',2,'Provider terminal error'),
                                                  ('G1','mock','',3,'Unknown')]:
                (project/'coord/tasks'/f'{task}.md').write_text('# Task\n\nDo no work.\n\n## Allowed scope\n- file.txt\n\n## Validate\n$ true\n')
                cp=unio('run',worker,task,codes=(rc,),extra={'OUTCOME_CASE':case})
                report=(project/'coord/reports'/f'{task}.md').read_text()
                self.assertIn('Adapter outcome: '+label, cp.stdout)
                # Report's native outcome line is before untrusted log tail.
                self.assertIn('exit='+str(rc), report)
                self.assertIn('\nAdapter outcome: '+label+'\npolicy group=', report)
            status=unio('status').stdout
            for label in ('Configured token cap','Transport failure','Provider terminal error','Unknown'):
                self.assertIn('Adapter outcome: '+label, status)
            self.assertFalse((b/'conf/off/mock').exists())
            # Read-only status rejects changed task/config and preserves evidence.
            vdest=next(p for p in (project/'coord/reports/.outcomes').iterdir()
                       if json.loads((p/'binding.json').read_text())['task']=='V1')
            original=(vdest/'outcome.json').read_bytes()
            (project/'coord/tasks/V1.md').write_text('changed')
            self.assertIn('V1 / vibe: Adapter outcome: Unknown', unio('status').stdout)
            self.assertEqual((vdest/'outcome.json').read_bytes(), original)


if __name__ == '__main__':
    unittest.main(verbosity=2)
