#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed local observation and bounded failure fixtures; zero provider calls."""
import copy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SOURCE = Path(__file__).resolve().parents[1]
HELPER = SOURCE/'tools/fleet-status.py'
NOW = datetime.now(timezone.utc)
STAMP = NOW.isoformat()
COMMANDS = ('policy --json', 'agents --json', 'capacity show --json',
            'capacity show --provider codex --json', 'readiness show --json')


def documents():
    window = dict(source='manual', status='fresh', observed_at=STAMP, age_seconds=1,
                  window_minutes=300, reset_at=(NOW+timedelta(hours=1)).isoformat(),
                  last_reading_remaining_percent=42.0, usable_remaining_percent=42.0)
    return {
        COMMANDS[0]: dict(schema_version=1, mode='yolo', tier='low', lead_agent='codex',
            lead_group='codex', workflow_enforcement='native_workflows',
            workflow_limit_per_group=1, accounts={'alias':'codex'}, active_with_lead={'codex':1}),
        COMMANDS[1]: dict(schema_version=1, agents=[dict(name=name, binary={'present':present},
            bench={'off':off}, command='secret-sentinel') for name,present,off in
            [('codex',True,False),('alias',True,False),('idle',True,False),
             ('off',True,True),('missing',False,False),('uncertain',None,False)]]),
        COMMANDS[2]: dict(schema_version=1,state='ok',groups={'codex':{'status':'recorded','windows':{'five-hour':window}}}),
        COMMANDS[3]: dict(schema_version=1,provider='codex',state='ok',groups={'codex':dict(
            source='codex',state='ok',reason=None,observed_at=STAMP,age_seconds=1,freshness='fresh',
            buckets={'codex:normal':dict(status='ok',reason=None,windows={'primary':dict(
                window,status='stale',usable_remaining_percent=None),'secondary':None})},last_good=None)}),
        COMMANDS[4]: dict(schema_version=1,state='ok',agents={'codex':dict(status='fresh',
            authentication='signed_in',source='native',observed_at=STAMP,age_seconds=1,
            latest_observation={'email':'private@example.invalid','token':'secret-sentinel'})})}


FAKE = '''#!/usr/bin/env python3
import json,os,sys,time
from pathlib import Path
root=Path(__file__).parent
data=json.loads((root/'input.json').read_text());key=' '.join(sys.argv[1:])
with (root/'argv.jsonl').open('a') as out:out.write(json.dumps({'argv':sys.argv[1:],'cwd':os.getcwd()})+'\\n')
if key not in data['documents']:raise SystemExit(98)
mode=data.get('fail',{}).get(key)
if mode=='timeout':time.sleep(10)
if mode=='closed':
 (root/'child.pid').write_text(str(os.getpid()));os.close(1);os.close(2);time.sleep(10)
if mode=='flood':os.write(1,b'x'*262145)
if mode=='stderr_flood':os.write(2,b'private-secret'*30000)
if mode=='descendant':
 pid=os.fork()
 if pid==0:
  (root/'child.pid').write_text(str(os.getpid()));time.sleep(10);os._exit(0)
 for _ in range(100):
  if (root/'child.pid').exists():break
  time.sleep(.001)
value=data['documents'][key]
os.write(1,(value if isinstance(value,str) else json.dumps(value)).encode())
if mode=='warning':os.write(2,b'private-secret warning\\n')
if mode=='nonzero':raise SystemExit(7)
'''


def alive(pid):
    try:
        text=(Path('/proc')/str(pid)/'stat').read_text()
        return text[text.rindex(')')+2:].split()[0]!='Z'
    except FileNotFoundError:
        return False


class FailureFixtures(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory(prefix='fleet failures ');self.addCleanup(temp.cleanup)
        self.root=Path(temp.name);self.project=self.root/'project with spaces'
        (self.project/'coord').mkdir(parents=True);(self.project/'wt').mkdir()
        self.runner=self.root/'native runner';self.runner.write_text(FAKE);self.runner.chmod(0o755)
        self.data={'documents':documents()};self.input=self.root/'input.json'

    def command(self,*args):
        self.input.write_text(json.dumps(self.data))
        return [sys.executable,'-B',str(HELPER),str(self.runner),'--project',str(self.project),*args]

    def invoke(self,*args):
        result=subprocess.run(self.command(*args),capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        for secret in ('private-secret','secret-sentinel','private@example.invalid'):
            self.assertNotIn(secret,result.stdout+result.stderr)
        return json.loads(result.stdout) if '--json' in args else result.stdout

    def test_groups_lead_blocks_privacy_and_fixed_argv(self):
        view=self.invoke('--json');groups=view['groups'];self.assertEqual(groups['codex']['occupied'],1)
        for name in ('codex','alias'):
            self.assertEqual(groups['codex']['agents'][name]['reasons'],['group_full'])
        self.assertEqual(groups['idle']['agents']['idle']['admission_state'],'clear')
        self.assertEqual(groups['off']['agents']['off']['reasons'],['agent_off'])
        self.assertEqual(groups['missing']['agents']['missing']['reasons'],['binary_missing'])
        self.assertEqual(groups['uncertain']['agents']['uncertain']['admission_state'],'unknown')
        for group in groups.values():
            for agent in group['agents'].values():self.assertEqual(agent['dispatch_readiness'],'unknown')
        self.assertEqual(groups['codex']['agents']['codex']['cached_auth']['authentication'],'signed_in')
        calls=[json.loads(line) for line in (self.root/'argv.jsonl').read_text().splitlines()]
        self.assertEqual([' '.join(c['argv']) for c in calls],list(COMMANDS))
        self.assertTrue(all(c['cwd']==str(self.project) for c in calls))

    def test_stop(self):
        (self.project/'coord/STOP').touch()
        view=self.invoke('--json');self.assertTrue(view['stop'])
        self.assertIn('project_STOP',view['groups']['idle']['agents']['idle']['reasons'])

    def test_real_schemas_and_stale_text(self):
        view=self.invoke('--json')['groups']['codex']
        self.assertEqual(view['manual_allowance']['windows']['five-hour']['usable_remaining_percent'],42)
        self.assertIsNone(view['cached_allowance']['buckets']['codex:normal']['windows']['primary']['usable_remaining_percent'])
        self.assertIn('stale, last reading 42% (not current)',self.invoke())

    def test_past_reset_never_refills(self):
        window=self.data['documents'][COMMANDS[2]]['groups']['codex']['windows']['five-hour']
        window['reset_at']=(NOW-timedelta(seconds=1)).isoformat()
        view=self.invoke('--json')['groups']['codex']['manual_allowance']['windows']['five-hour']
        self.assertEqual(view['status'],'expired');self.assertIsNone(view['usable_remaining_percent'])

    def test_historical_and_unknown_cached_windows(self):
        entry=self.data['documents'][COMMANDS[3]]['groups']['codex']
        bucket=copy.deepcopy(entry['buckets']);bucket['codex:normal']['windows']['primary']['status']='historical'
        entry['last_good']=dict(historical=True,observed_at=STAMP,age_seconds=1,buckets=bucket)
        entry['buckets']['codex:normal']['windows']['primary']={'status':'unknown','usable_remaining_percent':None}
        view=self.invoke('--json')['groups']['codex']['cached_allowance']
        self.assertIsNone(view['last_good']['buckets']['codex:normal']['windows']['primary']['usable_remaining_percent'])
        self.assertIn('historical, never current',self.invoke())

    def test_independent_failure_keeps_agents_and_auth(self):
        self.data['documents'][COMMANDS[0]]='bad json'
        view=self.invoke('--json');self.assertEqual(view['sources']['policy'],'malformed')
        self.assertEqual(view['groups']['idle']['agents']['idle']['admission_state'],'unknown')
        self.assertEqual(view['groups']['codex']['agents']['codex']['cached_auth']['authentication'],'signed_in')

    def test_strict_json_and_typed_schemas(self):
        for value in ['{"schema_version":1,"schema_version":1}', '{"n":NaN}', '{"n":1e999}',
                      '[]','{}','['*1100+']'*1100, dict(documents()[COMMANDS[0]],schema_version=True),
                      dict(documents()[COMMANDS[0]],workflow_limit_per_group=True),
                      dict(documents()[COMMANDS[0]],active_with_lead={'codex':True})]:
            with self.subTest(value=str(value)[:60]):
                self.data['documents'][COMMANDS[0]]=value
                self.assertEqual(self.invoke('--json')['sources']['policy'],'malformed')

    def test_wrong_reading_types_never_available(self):
        for key in ('observed_at','age_seconds','usable_remaining_percent'):
            with self.subTest(field=key):
                self.data={'documents':documents()}
                self.data['documents'][COMMANDS[2]]['groups']['codex']['windows']['five-hour'][key]='private-secret'
                self.assertEqual(self.invoke('--json')['sources']['capacity_manual'],'malformed')

    def test_warning_nonzero_and_combined_output_cap(self):
        for mode,expected in [('warning','ok'),('nonzero','error'),('flood','overflow'),('stderr_flood','overflow')]:
            with self.subTest(mode=mode):
                self.data['fail']={COMMANDS[0]:mode}
                self.assertEqual(self.invoke('--json')['sources']['policy'],expected)

    def test_whole_deadline_and_later_healthy_input(self):
        self.data['fail']={COMMANDS[0]:'timeout'};start=time.monotonic()
        view=self.invoke('--json','--timeout','1');self.assertLess(time.monotonic()-start,2)
        self.assertEqual(view['sources']['policy'],'timeout');self.assertEqual(view['sources']['agents'],'ok')
        self.data['fail']={key:'timeout' for key in COMMANDS};start=time.monotonic()
        self.invoke('--json','--timeout','1');self.assertLess(time.monotonic()-start,2)

    def test_closed_pipes_and_descendants(self):
        for mode in ('closed','descendant'):
            with self.subTest(mode=mode):
                marker=self.root/'child.pid';marker.unlink(missing_ok=True)
                self.data['fail']={COMMANDS[0]:mode};start=time.monotonic()
                view=self.invoke('--json','--timeout','1');self.assertLess(time.monotonic()-start,2)
                self.assertEqual(view['sources']['policy'],'timeout' if mode=='closed' else 'ok')
                self.assertFalse(alive(int(marker.read_text())))

    def test_interrupt_cleans_owned_child(self):
        self.data['fail']={COMMANDS[0]:'closed'}
        child=subprocess.Popen(self.command('--json'),stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        try:
            marker=self.root/'child.pid';deadline=time.monotonic()+3
            while not marker.exists() and time.monotonic()<deadline:time.sleep(.01)
            self.assertTrue(marker.exists());child.send_signal(signal.SIGTERM)
            child.communicate(timeout=3);self.assertEqual(child.returncode,130)
            self.assertFalse(alive(int(marker.read_text())))
        finally:
            if child.poll() is None:child.kill();child.wait()


class InstalledFleet(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='fleet installed ');cls.base=Path(cls.temp.name)
        cls.conf=cls.base/'configuration with spaces';cls.bin=cls.base/'bin with spaces'
        cls.env=dict(os.environ,UNIO_BIN_DIR=str(cls.bin),UNIO_CONF_DIR=str(cls.conf),
            UNIO_COMPLETION_DIR=str(cls.base/'completion'),PYTHONDONTWRITEBYTECODE='1')
        result=subprocess.run(['bash',str(SOURCE/'unio-install.sh')],env=cls.env,cwd=cls.base,
                              capture_output=True,text=True,timeout=60)
        if result.returncode:raise AssertionError(result.stderr)
        cls.engine=cls.bin/'unio';cls.marker=cls.base/'agent-called'
        cls.fake=cls.bin/'never-agent';cls.fake.write_text('#!/bin/sh\ntouch '+shlex.quote(str(cls.marker))+'\nexit 99\n')
        cls.fake.chmod(0o755)
        (cls.conf/'agents.conf').write_text(''.join(name+'='+shlex.quote(str(cls.fake))+'\n' for name in ('codex','alias','idle','claude'))
            +'missing=unio-test-binary-does-not-exist\n')

    @classmethod
    def tearDownClass(cls):
        try:assert not cls.marker.exists(),'Configured agent executed!'
        finally:cls.temp.cleanup()

    def setUp(self):
        self.project=Path(tempfile.mkdtemp(prefix='project ',dir=self.base))
        (self.project/'coord').mkdir();(self.project/'wt').mkdir();(self.project/'repo').mkdir()

    def invoke(self,*args,cwd=None,code=0):
        result=subprocess.run([str(self.engine),'fleet',*args],env=self.env,cwd=cwd or self.project/'repo',
                              capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,code,result.stderr);self.assertFalse(self.marker.exists())
        return result

    def stamp(self):
        return {str(p.relative_to(self.project)):p.stat().st_mtime_ns for p in self.project.rglob('*')}

    def write_policy(self):
        (self.project/'coord/work-policy.json').write_text(json.dumps(dict(schema_version=1,mode='yolo',
            tier='low',lead_agent='codex',accounts={'alias':'codex'},updated_at=STAMP)))

    def test_installed_payload_help_completion_and_strict_arguments(self):
        self.assertEqual((self.conf/'lib/fleet-status.py').read_bytes(),HELPER.read_bytes())
        result=self.invoke('--help',cwd=self.base);self.assertIn('unio fleet',result.stdout)
        completion=(self.base/'completion/unio').read_text();self.assertIn('fleet)',completion)
        self.assertIn('--timeout',completion)
        # Workspace scratch itself is beneath the real project. Use / as a
        # read-only neutral cwd; keep every generated fixture under TMPDIR.
        self.invoke('--json',cwd=Path('/'),code=2)
        self.invoke('--project',str(self.project),'--unknown',code=2)
        for value in ('0','61','nan'):self.invoke('--timeout',value,code=2)
        self.assertFalse((self.project/'coord/capacity').exists())

    def test_local_queries_leave_missing_state_missing_and_preserve_mtimes(self):
        self.write_policy();before=self.stamp()
        view=json.loads(self.invoke('--json').stdout)
        self.assertEqual(view['groups']['codex']['occupied'],1)
        self.assertEqual(view['groups']['codex']['agents']['alias']['reasons'],['group_full'])
        self.assertEqual(view['groups']['idle']['agents']['idle']['admission_state'],'clear')
        self.assertEqual(view['sources']['capacity_manual'],'missing')
        self.assertEqual(view['sources']['readiness'],'missing')
        self.assertEqual(self.stamp(),before)
        explicit=json.loads(self.invoke('--project='+str(self.project),'--json',cwd=self.base).stdout)
        self.assertEqual(explicit['project'],str(self.project.resolve()))
        (self.project/'coord/STOP').touch();view=json.loads(self.invoke('--json').stdout)
        self.assertIn('project_STOP',view['groups']['idle']['agents']['idle']['reasons'])

    def test_recorded_manual_auth_and_corrupt_data_are_read_only(self):
        capacity=self.project/'coord/capacity';capacity.mkdir(mode=0o700)
        reading=dict(source='manual',window_minutes=300,remaining_percent=25.0,observed_at=STAMP,
                     reset_at=(NOW+timedelta(hours=1)).isoformat())
        state=capacity/'readings.json';state.write_text(json.dumps({'schema_version':1,'groups':{'codex':{'five-hour':reading}}}));state.chmod(0o600)
        readiness=self.project/'coord/readiness';readiness.mkdir(mode=0o700)
        good=dict(source='native',observed_at=STAMP,loggedIn=True)
        auth=readiness/'observations.json';auth.write_text(json.dumps(dict(schema_version=1,agents={'claude':{'latest':good,'last_good':good}})));auth.chmod(0o600)
        bucket={'codex':dict(status='ok',reason=None,windows={'primary':dict(status='valid',
            window_minutes=300,used_percent=25.0,remaining_percent=75.0,
            reset_at=(NOW+timedelta(hours=1)).isoformat()),'secondary':None})}
        providers=capacity/'providers.json';providers.write_text(json.dumps(dict(schema_version=1,
            providers={'codex':{'codex':dict(source='codex',attempted_at=STAMP,state='ok',reason=None,
            account_kind='chatgpt',observed_at=STAMP,buckets=bucket,last_good=None)}})));providers.chmod(0o600)
        before=self.stamp();view=json.loads(self.invoke('--json').stdout)
        self.assertEqual(view['groups']['codex']['manual_allowance']['windows']['five-hour']['usable_remaining_percent'],25)
        self.assertEqual(view['groups']['claude']['agents']['claude']['cached_auth']['authentication'],'signed_in')
        self.assertEqual(view['groups']['codex']['cached_allowance']['buckets']['codex']['windows']['primary']['usable_remaining_percent'],75)
        self.assertEqual(self.stamp(),before)
        state.write_text('broken');before=self.stamp();view=json.loads(self.invoke('--json').stdout)
        self.assertEqual(view['sources']['capacity_manual'],'error')
        self.assertIsNone(view['groups']['codex']['manual_allowance'])
        self.assertEqual(self.stamp(),before)


if __name__=='__main__':
    unittest.main()
