#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline canonical parser contracts and native refusal before admission."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('contract', ROOT/'tools/adapter-contract.py')
c = importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)


def command(route, args, base=ROOT/'tools'):
    return shlex.join(['python3', '-I', '-S', '-B', str(base/(route+'-worker.py')), *args])


class Parsers(unittest.TestCase):
    def test_current_vibe_bound_thinking_quotes_and_repeated_args(self):
        args=['--model','glm-5-3','--receipt-dir',"/private ; $ literal ' quote",
              '--max-tokens','17000000','--max-tokens','12000000',
              '--max-turns','180','--time-limit','7200','--max-price','10','--thinking','medium']
        self.assertEqual(c.check(command('vibe',args))['state'],'valid')
        args += ['--max-tokens','17000000']
        result=c.check(command('vibe',args))
        self.assertEqual(result['state'],'invalid')
        self.assertIn('--max-tokens',result['detail'])
        self.assertIn('16000000',result['detail'])

    def test_all_numeric_bounds_types_choices_and_required_flags(self):
        basics={'vibe':['--model','glm-5-3','--receipt-dir','/private'],
                'copilot':['--receipt-dir','/private'],
                'antigravity':['--receipt-dir','/private'],
                'perplexity':['--model','glm53']}
        cases={'vibe':[('--max-tokens','16000001'),('--max-tokens','0'),('--max-tokens','1.2'),
                       ('--max-price','nan'),('--max-price','inf'),('--max-price','10.01'),
                       ('--max-turns','181'),('--time-limit','7201'),('--thinking','wrong')],
               'copilot':[('--time-limit','nan'),('--time-limit','7201'),('--max-ai-credits','29'),
                          ('--max-ai-credits','301'),('--max-ai-credits','1.2')],
               'antigravity':[('--time-limit','inf'),('--time-limit','0'),('--time-limit','7201'),
                              ('--selector','wrong')],
               'perplexity':[('--timeout','nan'),('--timeout','0'),('--max-output','0'),
                             ('--max-output','999999999999'),('--source','wrong')]}
        for route,args in basics.items():
            self.assertEqual(c.check(command(route,args))['state'],'valid',route)
            for pair in cases[route]:
                with self.subTest(route=route,pair=pair):
                    self.assertEqual(c.check(command(route,args+list(pair)))['state'],'invalid')
            for suffix in (['--unknown','SECRET'],['--time-limit'] if route!='perplexity' else ['--timeout'], ['--help']):
                self.assertEqual(c.check(command(route,args+suffix))['state'],'invalid')
            self.assertEqual(c.check(command(route,[]))['state'],'invalid')
        for suffix in (['--check'],['--child'],['--receipt-dir','/x','--proposal-dir','/y']):
            self.assertEqual(c.check(command('perplexity',basics['perplexity']+suffix))['state'],'invalid')

    def test_safe_diagnostics_and_no_provider_in_metadata(self):
        for route,args in [('vibe',['--model','SECRET']),('copilot',['--time-limit','SECRET']),
                           ('antigravity',['--selector','SECRET']),('perplexity',['--timeout','SECRET'])]:
            result=c.check(command(route,args))
            self.assertEqual(result['state'],'invalid')
            self.assertNotIn('SECRET',json.dumps(result))
            cp=subprocess.run([sys.executable,'-B',str(ROOT/'tools'/(route+'-worker.py')),
                               '--contract-validate',*args],capture_output=True,text=True,timeout=10)
            self.assertEqual(cp.returncode,0,cp.stderr)
            self.assertEqual(json.loads(cp.stdout)['state'],'invalid')
            self.assertNotIn('SECRET',cp.stdout+cp.stderr)

    def test_no_evaluation_imports_or_mandatory_custom_contract(self):
        for text in ['echo custom', 'env '+command('vibe',[]),
                     'bash -c '+shlex.quote(command('vibe',[])),
                     command('vibe',[])+' | cat', 'python3 /tmp/vibe-worker.py --model wrong',
                     'python3 -c '+shlex.quote("raise RuntimeError('must never execute')")]:
            self.assertEqual(c.check(text)['state'],'unvalidated')
        self.assertEqual(c.check(command('vibe',[])+" --receipt-dir 'unfinished")['state'],'invalid')
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'vibe-worker.py'
            p.write_text("raise RuntimeError('untrusted source must never be imported')")
            self.assertEqual(c.check(shlex.join(['python3',str(p)]))['state'],'unvalidated')
            shutil.copyfile(ROOT/'tools/vibe-worker.py',p)
            cp=subprocess.run([sys.executable,str(p),'--help'],capture_output=True,text=True,timeout=10)
            self.assertEqual(cp.returncode,0,cp.stderr)


VIBE = '''#!/usr/bin/env python3
import json,os,pathlib,sys
with open(os.environ['MARKER'],'a') as f:f.write('metadata\\n' if '--version' in sys.argv else 'provider\\n')
if '--version' in sys.argv:
 print('vibe 2.26.1');raise SystemExit(0)
a=sys.argv[1:]
assert a[a.index('--max-tokens')+1]=='12000000'
p=pathlib.Path(a[a.index('--output-dir')+1])/'export.json'
p.write_text(json.dumps(dict(schema_version=1,vibe_version='2.26.1',outcome='turn_limit',exit_code=3,stop_reason='limit',usage=None,cost_usd=None)))
raise SystemExit(3)
'''


class Native(unittest.TestCase):
    def test_preflight_before_cli_slot_retry_and_background_and_custom_compatibility(self):
        with tempfile.TemporaryDirectory(prefix='route-contract-',dir='/dev/shm') as tmp:
            b=Path(tmp)
            env={k:v for k,v in os.environ.items() if not k.startswith(('UNIO_','PYTHON')) and k!='BASH_ENV'}
            env.update(UNIO_BIN_DIR=str(b/'bin'),UNIO_CONF_DIR=str(b/'conf'),
                       UNIO_COMPLETION_DIR=str(b/'completion'),UNIO_AUTO_VERIFY='0',UNIO_AUTO_SYNC='0',
                       UNIO_TIMEOUT='20',GIT_AUTHOR_NAME='offline',GIT_COMMITTER_NAME='offline',
                       GIT_AUTHOR_EMAIL='offline@example.invalid',GIT_COMMITTER_EMAIL='offline@example.invalid',
                       MARKER=str(b/'marker'))
            def run(argv,cwd=None,codes=(0,)):
                cp=subprocess.run(argv,cwd=cwd,env=env,capture_output=True,text=True,timeout=90)
                self.assertIn(cp.returncode,codes,cp.stdout+cp.stderr)
                return cp
            run(['bash',str(ROOT/'unio-install.sh')])
            adapters=b/'conf/lib/adapters'
            for name in ('adapter-contract.py','adapter-budget.py','adapter-outcome.py'):
                self.assertEqual((adapters/name).read_bytes(),(ROOT/'tools'/name).read_bytes())
            mock=b/'mock';mock.mkdir()
            (mock/'vibe').write_text(VIBE);(mock/'vibe').chmod(0o700)
            env['PATH']=str(mock)+':'+env['PATH']
            repo=b/'project/repo';repo.mkdir(parents=True)
            run(['git','init','-qb','main'],repo)
            (repo/'file').write_text('base\n');run(['git','add','.'],repo);run(['git','commit','-qm','base'],repo)
            def unio(*args,codes=(0,)):return run([str(b/'bin/unio'),*args],repo,codes)
            receipts=b/"private receipts ' quoted";receipts.mkdir(mode=0o700)
            conf=b/'conf/agents.conf'
            valid=['--model','glm-5-3','--receipt-dir',str(receipts),'--max-tokens','12000000',
                   '--max-turns','180','--thinking','medium']
            conf.write_text('vibe='+command('vibe',valid,adapters)+'\ncustom=echo custom; exit 7\n')
            unio('init','vibe','custom');unio('tier','low');unio('lead','none')
            root=repo.parent
            def task(name):
                (root/'coord/tasks'/(name+'.md')).write_text('# Task\n\nNo edits.\n\n## Allowed scope\n- file\n\n## Validate\n$ true\n')
            for i,args in enumerate([['--max-tokens','16000001'],['--max-price','nan'],
                                     ['--thinking','SECRET'],['--max-turns'],['--unknown','SECRET']]):
                name='BAD'+str(i);task(name)
                conf.write_text('vibe='+command('vibe',valid+args,adapters)+'\n')
                for background in (False,True):
                    cp=unio('run',*(['-b'] if background else []),'vibe',name,codes=(2,))
                    self.assertIn('Route contract: invalid',cp.stdout+cp.stderr)
                    self.assertNotIn('SECRET',cp.stdout+cp.stderr)
                    self.assertNotIn('started in background',cp.stdout+cp.stderr)
                    self.assertFalse((b/'marker').exists())
                    self.assertFalse((root/'coord/retries'/name).exists())
                    self.assertFalse((root/'coord/reports'/(name+'.policy.json')).exists())
                    self.assertFalse((root/'coord/reports/.outcomes').exists())
            # Same canonical route through an override with no lib/, and a
            # copied standalone engine. Invalid bounds must still precede all
            # metadata/provider/admission markers; custom commands still run.
            thin=b/'thin';thin.mkdir()
            thin_conf=thin/'agents.conf'
            copied=b/'copied-engine';shutil.copyfile(b/'bin/unio',copied)
            copied.chmod(0o700)
            env['UNIO_CONF_DIR']=str(thin)
            for engine in (b/'bin/unio',copied):
                thin_conf.write_text('vibe='+command('vibe',valid+['--max-tokens','16000001'],adapters)+'\n')
                task('THINBAD')
                cp=run([str(engine),'run','-b','vibe','THINBAD'],repo,codes=(2,))
                self.assertIn('Route contract: invalid',cp.stdout+cp.stderr)
                self.assertIn('16000000',cp.stdout+cp.stderr)
                self.assertFalse((b/'marker').exists())
                thin_conf.write_text('custom=echo custom; exit 7\n')
                task('THINCUSTOM')
                cp=run([str(engine),'run','custom','THINCUSTOM'],repo,codes=(7,))
                self.assertIn('Route contract: unvalidated',cp.stdout+cp.stderr)
            self.assertFalse((thin/'lib').exists())
            env['UNIO_CONF_DIR']=str(b/'conf')
            task('VALID');conf.write_text('vibe='+command('vibe',valid,adapters)+'\n')
            cp=unio('run','vibe','VALID',codes=(3,))
            self.assertIn('Route contract: valid',cp.stdout)
            self.assertIn('Stop reason: Configured turn cap',cp.stdout)
            self.assertEqual((b/'marker').read_text(),'metadata\nprovider\n')
            self.assertIn('exit=3',(root/'coord/reports/VALID.md').read_text())
            task('CUSTOM');conf.write_text('custom=echo custom; exit 7\n')
            cp=unio('run','custom','CUSTOM',codes=(7,))
            self.assertIn('Route contract: unvalidated',cp.stdout)
            self.assertIn('Stop reason: Unknown',cp.stdout)
            self.assertIn('Run budget: Unknown',cp.stdout)


if __name__=='__main__':
    unittest.main(verbosity=2)
