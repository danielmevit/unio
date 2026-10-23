#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Declared metadata and mock-only native outcome contracts. No provider calls."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = Path(os.environ.get('TMPDIR',str(ROOT/'tmp')))
FIXTURES.mkdir(parents=True,exist_ok=True)
spec = importlib.util.spec_from_file_location('outcomes', ROOT/'tools/task-outcomes.py')
outcomes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(outcomes)


class Metadata(unittest.TestCase):
    def test_report_channel_refuses_symlink_ancestors(self):
        with tempfile.TemporaryDirectory(dir=FIXTURES) as tmp:
            root=Path(tmp); (root/'outside/sub').mkdir(parents=True)
            (root/'linked').symlink_to(root/'outside',target_is_directory=True)
            prior=os.environ.get('UNIO_TASK_REPORT')
            os.environ['UNIO_TASK_REPORT']=str(root/'linked/sub/incoming.txt')
            try:
                with self.assertRaises(OSError): outcomes.publish_report('native report')
            finally:
                if prior is None: os.environ.pop('UNIO_TASK_REPORT')
                else: os.environ['UNIO_TASK_REPORT']=prior
            self.assertFalse((root/'outside/sub/incoming.txt').exists())

    def test_modes_and_legacy(self):
        self.assertIsNone(outcomes.parse('# task\nimplementation prose\n'))
        for mode in outcomes.MODES:
            self.assertEqual(outcomes.parse('## Outcome\n'+mode+'\n## Validate\n$ true\n'), mode)

    def test_legacy_outcome_headings(self):
        for heading in ('## Outcomes', '## Outcome notes', '## Outcome implementation',
                        '### Outcome', '##Outcome', '## outcome', ' ## Outcome'):
            with self.subTest(heading=heading):
                self.assertIsNone(outcomes.parse(heading+'\nreport-only\n'))

    def test_malformed(self):
        for text in ('## Outcome\n', '## Outcome\nunknown', '## Outcome\n implementation',
                     '## Outcome\nimplementation\nreport-only',
                     '## Outcome\nimplementation\n## Outcome\nimplementation'):
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
        cls.tmp = tempfile.TemporaryDirectory(prefix='unio-outcomes-', dir=FIXTURES)
        cls.base = Path(cls.tmp.name)
        cls.env = {k:v for k,v in os.environ.items() if not k.startswith(('UNIO_', 'GIT_', 'PYTHON')) and k!='BASH_ENV'}
        cls.env.update(UNIO_BIN_DIR=str(cls.base/'bin'), UNIO_CONF_DIR=str(cls.base/'conf'),
                       UNIO_COMPLETION_DIR=str(cls.base/'completion'), UNIO_AUTO_VERIFY='0',
                       UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0', UNIO_TIMEOUT='30',
                       GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
                       GIT_AUTHOR_NAME='fixture', GIT_COMMITTER_NAME='fixture',
                       GIT_AUTHOR_EMAIL='fixture@example.invalid', GIT_COMMITTER_EMAIL='fixture@example.invalid', PYTHONDONTWRITEBYTECODE='1')
        subprocess.run(['bash',str(ROOT/'unio-install.sh')],env=cls.env,capture_output=True,check=True,timeout=100)
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
            bg=self.call('run','-b',route,name,code=2)
            self.assertIn('blocked_no_repo_access',bg.stderr)
            self.assertNotIn('started in background',bg.stdout)
            for path in ('results/'+route+'/'+name+'.json','retries/'+name,'reports/'+name+'.log'):
                self.assertFalse((self.root/'coord'/path).exists(),path)
        self.conf.write_text('mock=touch provider-called\n')
        for index,text in enumerate(('unknown','implementation\nreport-only','')):
            name='malformed-'+str(index)
            tf=self.task(name)
            tf.write_text('## Outcome\n'+text+'\n')
            self.call('run','mock',name,code=2)
            self.assertFalse((self.wt/'provider-called').exists())

    def test_legacy_headings_reach_native_provider(self):
        for index,heading in enumerate(('## Outcomes', '## Outcome notes')):
            name='legacy-heading-'+str(index)
            marker=self.base/('legacy-provider-'+str(index))
            self.configure('touch '+shlex.quote(str(marker)))
            tf=self.task(name,mode=None)
            tf.write_text(tf.read_text()+'\n'+heading+'\nordinary legacy notes\n')
            cp=self.call('run','mock',name)
            self.assertTrue(marker.exists())
            self.assertNotIn('task outcome:',cp.stdout+cp.stderr)
            self.assertNotIn('outcome',self.data(name))

    def test_adapter_wrapped_guards(self):
        tf=self.task('wrapped','implementation')
        for route,args in [('copilot',['--receipt-dir','/missing-private']),('perplexity',['--model','glm53'])]:
            cp=self.raw(['python3',ROOT/'tools'/(route+'-worker.py'),'--prompt-file',tf,*args],code=2)
            self.assertIn('blocked_no_repo_access',cp.stdout+cp.stderr)

    def configure(self,source='printf "native diagnostic\\n"'):
        cmd = ('grep -q "COMPLETE SOURCE REPORT" "$TASKFILE" && '
               'printf "%s\\n" \'```unio-findings-v1\' \'{"schema_version": 1, "findings": []}\' \'```\' \'VERDICT: APPROVE\'')
        self.conf.write_text('mock=bash -c '+shlex.quote(source)+'\n'+
                            'rev=bash -c '+shlex.quote(cmd)+'\n')

    def data(self,name):
        return json.loads(self.call('result','mock',name).stdout)

    def artifact(self,name):
        o=self.data(name)['outcome']
        return self.root/'coord/results/mock'/(name+'.outcomes')/o['run_id']/'report.txt'

    def test_report_success_prior_commits_review_handoff_and_freshness(self):
        self.configure()
        (self.wt/'earlier.txt').write_bytes(b'earlier binary feature\0\xff')
        self.raw(['git','add','earlier.txt'],cwd=self.wt)
        self.raw(['git','commit','-qm','earlier feature'],cwd=self.wt)
        head=self.raw(['git','rev-parse','HEAD'],cwd=self.wt).stdout
        name='report-success'
        self.task(name,scope='- diagnostic-only')
        self.call('run','mock',name)
        self.assertEqual(head,self.raw(['git','rev-parse','HEAD'],cwd=self.wt).stdout)
        self.call('verify','mock',name)
        self.call('review','mock',name,'rev')
        reviewer=self.conf.read_text().splitlines()[1].replace('rev=','revother=',1)
        with self.conf.open('a') as f: f.write(reviewer+'\n')
        self.call('review-set','mock',name,'rev','revother')
        self.assertTrue(self.data(name)['ready_for_human_review'])
        artifact=self.artifact(name)
        original=artifact.read_bytes()
        self.assertEqual(original,b'native diagnostic\n')
        packet=Path(self.call('handoff','mock',name).stdout.strip())
        report=(packet/'report.md').read_text()
        self.assertIn('native diagnostic',report)
        self.assertIn(self.data(name)['outcome']['run_id'],report)
        self.assertEqual(set(self.data(name)['revision']),{'candidate_commit','base_commit','task_sha256','worktree_sha256'})
        artifact.chmod(0o600)
        artifact.write_text('tampered\n')
        self.assertFalse(self.data(name)['ready_for_human_review'])
        self.assertEqual(self.data(name)['outcome_current']['state'],'invalid')
        self.call('review','mock',name,'rev',code=2)
        self.call('review-set','mock',name,'rev','revother',code=2)
        self.call('handoff','mock',name,code=2)
        self.call('verify','mock',name,code=1)
        artifact.write_bytes(original)
        self.call('verify','mock',name)
        self.call('review','mock',name,'rev')
        artifact.unlink()
        self.assertFalse(self.data(name)['ready_for_human_review'])
        self.call('verify','mock',name,code=1)

    def test_private_command_hash_only_provenance(self):
        name='private-command'
        canary='mock-api-key=harmless-private-canary'
        self.configure('printf "private command report" # '+canary)
        command=self.conf.read_text().splitlines()[0].split('=',1)[1]
        material=self.base/'private-review-material'
        reviewer='cp "$TASKFILE" '+shlex.quote(str(material))+'; printf "VERDICT: APPROVE\\n"'
        with self.conf.open('a') as f:
            f.write('privacyrev=bash -c '+shlex.quote(reviewer)+'\n')
        self.task(name)
        self.call('run','mock',name)
        self.call('verify','mock',name)
        result=self.call('result','mock',name)
        self.assertNotIn(canary,result.stdout+result.stderr)
        o=json.loads(result.stdout)['outcome']
        self.assertNotIn('command',o)
        self.assertEqual(o['command_sha256'],hashlib.sha256(command.encode()).hexdigest())
        binding=self.artifact(name).with_name('binding.json').read_text()
        self.assertNotIn(canary,binding)
        self.call('review','mock',name,'privacyrev')
        self.assertNotIn(canary,material.read_text())
        self.assertIn(o['command_sha256'],material.read_text())
        packet=Path(self.call('handoff','mock',name).stdout.strip())
        for path in packet.rglob('*'):
            if path.is_file(): self.assertNotIn(canary.encode(),path.read_bytes())
        receipt=self.root/'coord/results/mock'/(name+'.json')
        original=receipt.read_bytes()
        doc=json.loads(original)
        doc['outcome']['command_sha256']='0'*64
        receipt.write_text(json.dumps(doc))
        self.call('verify','mock',name,code=1)
        receipt.write_bytes(original)
        self.call('verify','mock',name)
        # Pre-release records with raw commands fail closed without echoing them.
        doc=json.loads(original)
        doc['outcome']['command']=command
        receipt.write_text(json.dumps(doc))
        try:
            for args in [('result','mock',name),('review','mock',name,'privacyrev'),
                         ('handoff','mock',name)]:
                cp=self.call(*args,code=2)
                self.assertNotIn(canary,cp.stdout+cp.stderr)
        finally:
            receipt.write_bytes(original)

    def test_reports_fail_closed_and_legacy_empty_stays_failed(self):
        cases=[('no-artifact','true',0),('empty-artifact','printf "  "',0),
               ('failed-source','echo diagnostic; exit 7',7),
               ('changed-code','echo diagnostic; echo new > forbidden.txt',0),
               ('invalid-utf8',"printf '\\377'",0),
               ('oversize',shlex.join(['python3','-c','print("x"*262145)']),0)]
        for name,source,rc in cases:
            with self.subTest(name=name):
                self.configure(source)
                self.task(name)
                self.call('run','mock',name,code=rc)
                self.call('verify','mock',name,code=1)
                self.assertFalse(self.data(name)['ready_for_human_review'])
                self.assertEqual(self.data(name)['process']['exit_code'],rc)
                if (self.wt/'forbidden.txt').exists(): (self.wt/'forbidden.txt').unlink()
        self.configure('true')
        self.task('legacy-empty',mode=None)
        # Separate clean-base worker proves the existing empty-work gate.
        self.conf.write_text('copilot=true\n')
        self.call('run','copilot','legacy-empty')
        self.call('verify','copilot','legacy-empty',code=1)

    def test_missing_checks_scope_task_stale_and_binding_tamper(self):
        self.configure()
        for name,validate,scope in [('missing-validate','','- *'),('missing-scope','$ true','')]:
            self.task(name,validate=validate,scope=scope)
            self.call('run','mock',name)
            self.call('verify','mock',name,code=2)
        name='stale-binding'
        tf=self.task(name)
        self.call('run','mock',name)
        self.call('verify','mock',name)
        artifact=self.artifact(name)
        binding=artifact.with_name('binding.json')
        old=binding.read_bytes()
        binding.chmod(0o600)
        doc=json.loads(old); doc['task']='another-task'
        binding.write_text(json.dumps(doc))
        self.call('verify','mock',name,code=1)
        binding.write_bytes(old)
        prompt=artifact.with_name('prompt.md'); saved=prompt.read_bytes()
        prompt.chmod(0o600); prompt.write_text('stale prompt')
        self.call('verify','mock',name,code=1)
        prompt.write_bytes(saved)
        tf.write_text(tf.read_text()+'\nchanged task\n')
        self.call('verify','mock',name,code=1)
        self.assertTrue(self.data(name)['stale'])

    def test_engine_channel_contains_answer_not_stdout_pointer(self):
        name='answer-channel'
        self.configure('printf "complete actual answer" > "$UNIO_TASK_REPORT"; printf "receipt: /private/pointer"')
        self.task(name)
        self.call('run','mock',name)
        self.call('verify','mock',name)
        self.assertEqual(self.artifact(name).read_text(),'complete actual answer')


    def test_canonical_channel_cannot_accept_pointer_and_old_run_cannot_rebind(self):
        # Exercise engine capture directly with frozen definitions, without a
        # provider. The public tests above cover the native lifecycle; this
        # models a canonical adapter that returned a pointer but lost its answer.
        engine=(ROOT/'unio-install.sh').read_text().split(" <<'QUALITY_PY'\n",1)[1].split('\nQUALITY_PY\n',1)[0]
        definitions=engine.rsplit('\ntry:\n    cmd,*a=sys.argv[1:]',1)[0]
        ns={'__name__':'offline_quality_fixture'}
        exec(compile(definitions,'QUALITY_PY','exec'),ns)
        name='channel-missing'
        tf=self.task(name)
        rev=ns['snapshot'](str(self.root),'mock',name)
        root=str(self.root)
        o=ns['outcome_start'](root,'mock',name,rev,'canonical proposal',str(tf),'channel')
        d=dict(outcome=o,dispatch_revision=rev,process=dict(state='succeeded',exit_code=0,revision=rev))
        (self.root/'coord/reports'/(name+'.log')).write_text('receipt: /private/pointer')
        ns['outcome_finish'](root,'mock',name,d)
        self.assertIsNotNone(o['error'])
        with self.assertRaises(ValueError): ns['report_evidence'](root,'mock',name,d,rev)
        previous=None
        for _ in range(2):
            o=ns['outcome_start'](root,'mock',name,rev,'canonical proposal',str(tf),'channel')
            directory=Path(ns['outcome_directory'](root,'mock',name,o['run_id']))
            (directory/'incoming.txt').write_text('identical actual report')
            d=dict(outcome=o,dispatch_revision=rev,process=dict(state='succeeded',exit_code=0,revision=rev))
            ns['outcome_finish'](root,'mock',name,d)
            ns['report_evidence'](root,'mock',name,d,rev)
            if previous:
                binding=directory/'binding.json'; binding.chmod(0o600); binding.write_bytes(previous)
                with self.assertRaises(ValueError): ns['report_evidence'](root,'mock',name,d,rev)
            previous=(directory/'binding.json').read_bytes()


    def test_standalone_thin_report_mode_and_material_bounds(self):
        saved_at,saved_conf=self.at,self.env['UNIO_CONF_DIR']
        thin=self.base/'thin outcomes conf'
        thin.mkdir()
        shutil.copytree(self.base/'conf/templates',thin/'templates')
        engine=self.base/'copied standalone engine'/'unio'
        engine.parent.mkdir()
        shutil.copyfile(self.at,engine); engine.chmod(0o700)
        self.at=engine
        self.env['UNIO_CONF_DIR']=str(thin)
        try:
            thin_rev = 'printf "%s\\n" \'```unio-findings-v1\' \'{"schema_version": 1, "findings": []}\' \'```\' \'VERDICT: APPROVE\''
            (thin/'agents.conf').write_text('mock=printf "thin native report"\nrev=' + thin_rev + '\n')
            name='standalone-thin'
            self.task(name)
            self.call('run','mock',name)
            self.call('verify','mock',name)
            self.call('review','mock',name,'rev')
            self.assertTrue(self.data(name)['ready_for_human_review'])
            self.assertFalse((thin/'lib').exists())
        finally:
            self.at=saved_at
            self.env['UNIO_CONF_DIR']=saved_conf
        self.configure(shlex.join(['python3','-c','import sys; sys.stdout.write("x"*262144)']))
        name='material-bound'
        tf=self.task(name)
        tf.write_text(tf.read_text()+'\n## Additional context\n'+'a'*50000+'\n')
        self.call('run','mock',name)
        self.call('verify','mock',name)
        cp=self.call('review','mock',name,'rev',code=2)
        self.assertIn('exceeds 300000 bytes',cp.stdout+cp.stderr)



if __name__=='__main__':
    unittest.main()
