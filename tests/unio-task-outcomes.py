#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Declared metadata and mock-only native outcome contracts. No provider calls."""
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('outcomes', ROOT/'tools/task-outcomes.py')
outcomes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(outcomes)


class Metadata(unittest.TestCase):
    def test_modes_and_legacy(self):
        self.assertIsNone(outcomes.parse('# task\nimplementation prose\n'))
        for mode in outcomes.MODES:
            self.assertEqual(outcomes.parse('## Outcome\n'+mode+'\n## Validate\n$ true\n'), mode)

    def test_malformed(self):
        for text in ('## Outcome\n', '## Outcome\nunknown', '## Outcome\n implementation',
                     '## Outcome\nimplementation\nreport-only',
                     '## Outcome\nimplementation\n## Outcome\nimplementation',
                     '## Outcome implementation\n', '### Outcome\nreport-only',
                     '## outcome\nreport-only', ' ## Outcome\nreport-only'):
            with self.subTest(text=text), self.assertRaises(outcomes.OutcomeError):
                outcomes.parse(text)

    def test_fences(self):
        for fence in ('```', '~~~~'):
            text = fence+'markdown\n## Outcome\nunknown\n```\n'+fence+'\n'
            # The backtick fence closes at the first matching line; the tilde
            # fence ignores a shorter/different delimiter inside the example.
            if fence == '```':
                text = '```markdown\n## Outcome\nunknown\n```\n'
            self.assertIsNone(outcomes.parse(text))
            self.assertEqual(outcomes.parse(text+'## Outcome\nreport-only\n'), 'report-only')


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='unio-outcomes-', dir=os.environ.get('TMPDIR'))
        cls.base = Path(cls.tmp.name)
        cls.env = {k:v for k,v in os.environ.items() if not k.startswith(('UNIO_', 'GIT_', 'PYTHON')) and k!='BASH_ENV'}
        cls.env.update(UNIO_BIN_DIR=str(cls.base/'bin'), UNIO_CONF_DIR=str(cls.base/'conf'),
                       UNIO_COMPLETION_DIR=str(cls.base/'completion'), UNIO_AUTO_VERIFY='0',
                       UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0', UNIO_TIMEOUT='30',
                       GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                       GIT_AUTHOR_NAME='fixture', GIT_COMMITTER_NAME='fixture',
                       GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        subprocess.run(['bash',str(ROOT/'unio-install.sh')],env=cls.env,capture_output=True,check=True)
        cls.at = cls.base/'bin/unio'
        cls.root = cls.base/'project'
        cls.repo = cls.root/'repo'
        cls.repo.mkdir(parents=True)
        cls.raw(['git','init','-q','-b','main'])
        cls.raw(['git','commit','--allow-empty','-qm','initial'])
        cls.raw([cls.at,'init','mock','copilot','perplexity'])
        cls.wt = cls.root/'wt/mock'
        cls.conf = cls.base/'conf/agents.conf'
        cls.conf.write_text('mock=printf "native diagnostic\\n"\n')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def raw(cls, argv, cwd=None, code=0):
        cp = subprocess.run(list(map(str,argv)),cwd=cwd or cls.repo,env=cls.env,
                            capture_output=True,text=True,timeout=100)
        if cp.returncode != code:
            raise AssertionError((argv,cp.returncode,code,cp.stdout,cp.stderr))
        return cp

    def call(self,*args,code=0):
        return self.raw([self.at,*args],code=code)

    def task(self,name,mode='report-only',validate='$ true',scope='- *'):
        tf=self.root/'coord/tasks'/ (name+'.md')
        tf.write_text('# task\n'+('## Outcome\n'+mode+'\n' if mode else '')+
                      '## Allowed scope\n'+scope+'\n## Validate\n'+validate+'\n')
        return tf

    def test_blocked_before_admission_and_no_source(self):
        for route,args in [('copilot',['--receipt-dir','/missing-private']),('perplexity',['--model','glm53'])]:
            name='blocked-'+route
            self.task(name,'implementation')
            command=shlex.join(['python3','-I','-S','-B',str(self.base/'conf/lib/adapters'/(route+'-worker.py')),*args])
            self.conf.write_text(route+'='+command+'\n')
            cp=self.call('run',route,name,code=2)
            self.assertIn('blocked_no_repo_access',cp.stderr)
            for path in ('results/'+route+'/'+name+'.json','retries/'+name,'reports/'+name+'.log'):
                self.assertFalse((self.root/'coord'/path).exists(),path)
        self.conf.write_text('mock=touch provider-called\n')
        for index,text in enumerate(('unknown','implementation\nreport-only','')):
            name='malformed-'+str(index)
            tf=self.task(name)
            tf.write_text('## Outcome\n'+text+'\n')
            self.call('run','mock',name,code=2)
            self.assertFalse((self.wt/'provider-called').exists())

    def test_adapter_wrapped_guards(self):
        tf=self.task('wrapped','implementation')
        for route,args in [('copilot',['--receipt-dir','/missing-private']),('perplexity',['--model','glm53'])]:
            cp=self.raw(['python3',ROOT/'tools'/(route+'-worker.py'),'--prompt-file',tf,*args],code=2)
            self.assertIn('blocked_no_repo_access',cp.stdout+cp.stderr)


if __name__=='__main__':
    unittest.main()
