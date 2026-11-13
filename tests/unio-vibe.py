#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline real-schema-shaped CLI fixtures; no Vibe inference or network."""
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "tools/vibe-worker.py"
spec = importlib.util.spec_from_file_location("vibe_worker", SCRIPT)
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
FAKE = r'''
import json,os,pathlib,sys,time
if sys.argv[1:]==['--version']:
 print('vibe '+os.environ.get('FAKE_VERSION','2.26.1'));raise SystemExit()
a=sys.argv[1:]
pathlib.Path(os.environ['MARKER']).open('a').write('call\n')
assert '-p' not in a and '--auto-approve' not in a
get=lambda k:a[a.index(k)+1]
assert get('--agent')=='auto-approve' and '--trust' in a
assert get('--output')=='streaming'
label=os.environ['VIBE_ACTIVE_MODEL'];model=json.loads(os.environ['VIBE_MODELS'])[label]
wire='zai-glm-5-3' if label=='glm-5-3' else 'mistral-medium-3-5'
assert model['name']==wire and model['alias']==label and model['provider']=='mistral'
assert model['thinking']==os.environ.get('EXPECT_THINKING','high') and model['thinking_levels']==[model['thinking']]
assert model['input_price']>0 and model['output_price']>0
assert json.loads(os.environ['VIBE_ALLOWED_MODELS'])==[wire]
assert json.loads(os.environ['VIBE_COMPACTION_MODEL'])==model
assert json.loads(os.environ['VIBE_UTILITY_MODELS'])=={'title':'active','smart_approve':'active'}
for key in ['VIBE_SESSION_LOGGING__GENERATE_TITLES','VIBE_ENABLE_UPDATE_CHECKS','VIBE_ENABLE_AUTO_UPDATE','VIBE_EXPERIMENTS__ENABLE','VIBE_ENABLE_SUBAGENTS','VIBE_ENABLE_CONNECTORS']:
 assert os.environ[key]=='false'
assert json.loads(os.environ['VIBE_MCP_SERVERS'])==[]
assert os.environ['VIBE_API_RETRY_MAX_ELAPSED_TIME']=='0'
assert 'VIBE_INVENTED_OVERRIDE' not in os.environ
assert get('--max-tokens')==os.environ.get('EXPECT_TOKENS','2000000')
assert float(get('--max-price'))==float(os.environ.get('EXPECT_PRICE','5'))
assert [a[i+1] for i,v in enumerate(a) if v=='--enabled-tools']==['bash','read_file','write_file','edit','grep']
content=pathlib.Path(get('--prompt-file')).read_text()
assert len(content)==int(os.environ['EXPECT_PROMPT_LENGTH'])
assert content not in ' '.join(a)
mode=os.environ.get('FAKE_MODE','ok');code=int(os.environ.get('FAKE_EXIT','0'))
if mode=='missing':raise SystemExit(code)
if mode=='noexport':
 for text in ['abcd','abcdefgh']:
  print(json.dumps({'type':'message','role':'assistant','content':[{'type':'text','text':text}]}))
 raise SystemExit(code)
x={'schema_version':1,'vibe_version':'2.26.1','outcome':'finished' if code==0 else 'token_limit','stop_reason':None if code==0 else 'interrupted','exit_code':code,'usage':{'input_tokens':198950,'output_tokens':2336,'cached_input_tokens':0,'total_tokens':201286},'cost_usd':.2888084,'config':{'secret':'NEVER-IN-RECEIPT'},'error':{'message':'NEVER-IN-RECEIPT'}}
if os.environ.get('FAKE_OUTCOME'):x['outcome']=os.environ['FAKE_OUTCOME']
if os.environ.get('FAKE_ERROR') is not None:x['error']=json.loads(os.environ['FAKE_ERROR'])
if x['outcome'] in ('usage_error','config_error'):
 x['usage']=None;x['cost_usd']=None;x['stop_reason']=None
if mode=='nan':x['cost_usd']=float('nan')
if mode=='bool':x['usage']['input_tokens']=True
if mode=='legacy':x['usage']={'prompt_tokens':1,'completion_tokens':2,'total_tokens':3}
if mode=='none':x['usage']=None;x['cost_usd']=None
if mode=='unsafe_reason':x['stop_reason']='NEVER-IN-RECEIPT'
text=json.dumps(x)
if mode=='duplicate':text=text.replace('"schema_version": 1','"schema_version": 1, "schema_version": 1')
if os.environ.get('FAKE_STREAM'):
 e=[{'type':'message','role':'user','content':[{'type':'text','text':'SECRET-PROMPT'}],'generationStatus':'completed'},
    {'type':'reasoning','text':'SECRET-REASONING','summary':[],'generationStatus':'completed'},
    {'type':'message','role':'assistant','content':[{'type':'text','text':'SECRET-ANSWER'}],'generationStatus':'completed'},
    {'type':'effect','title':'bash','detail':{'kind':'shell','toolName':'bash','input':{'command':'SECRET-CMD'}},'state':{'status':'completed','outputText':'SECRET-OUT'}},
    {'type':'effect','title':'read','detail':{'kind':'file_read','toolName':'read_file','input':{'filePath':'/SECRET-PATH'}},'state':{'status':'completed'}},
    {'type':'effect','title':'edit','detail':{'kind':'file_edit','toolName':'edit','input':{'filePath':'/SECRET-PATH','oldString':'SECRET-OLD'}},'state':{'status':'completed'}},
    {'type':'effect','title':'write','detail':{'kind':'file_write','toolName':'write_file','input':{'filePath':'/SECRET-PATH','note':'héllo'}},'state':{'status':'completed'}},
    {'type':'effect','title':'search','detail':{'kind':'file_search','toolName':'grep','input':{'pattern':'SECRET-PATTERN'}},'state':{'status':'completed'}},
    {'type':'effect','title':'todo','detail':{'kind':'todo','toolName':'todo_write','input':{}},'state':{'status':'completed'}},
    {'type':'effect','title':'skill','detail':{'kind':'skill','toolName':'skill','input':{'name':'SECRET-SKILL'}},'state':{'status':'completed'}},
    {'type':'effect','title':'web','detail':{'kind':'web_search','toolName':'web_search','input':{'query':'SECRET-QUERY'}},'state':{'status':'failed','error':{'message':'SECRET-ERROR'}}},
    {'type':'notice','level':'error','message':'SECRET-NOTICE','detail':{'kind':'agent_changed','agentName':'SECRET-AGENT'}}]
 b=sys.stdout.buffer
 for v in e[:3]:b.write((json.dumps(v)+'\n').encode())
 b.write((json.dumps(e[3])+'\n'+json.dumps(e[4])+'\n').encode())
 blob=json.dumps(e[5]).encode();b.write(blob[:15]);b.flush();time.sleep(.05);b.write(blob[15:]+b'\n')
 raw=json.dumps(e[6],ensure_ascii=False).encode();cut=raw.index('é'.encode())+1
 b.write(raw[:cut]);b.flush();time.sleep(.05);b.write(raw[cut:]+b'\n')
 b.write(('\n'.join(json.dumps(v) for v in e[7:])+'\n').encode())
 b.write(b'this is not json\n')
 b.write(b'["not","an","object"]\n')
 b.write(b'{"type":"mystery","payload":"SECRET-UNKNOWN"}\n')
 b.write(b'{"pad":"'+b'A'*300000+b'"}\n')
 b.write(b'['*50000+b']'*50000+b'\n')
 b.flush()
 if os.environ.get('FAKE_HOSTILE'):
  for h in [{'type':'effect','detail':{'kind':[]},'state':{'status':'running'}},
            {'type':'effect','detail':{'kind':{}},'state':{'status':'running'}},
            {'type':'effect','detail':{'kind':'shell'},'state':{'status':[]}},
            {'type':'effect','detail':{'kind':'shell'},'state':{'status':{}}},
            {'type':[]},
            {'type':'message','role':[]},
            {'type':'message','role':'assistant','content':[{'type':'text','text':'POST-HOSTILE'}],'generationStatus':'completed'}]:
   b.write((json.dumps(h)+'\n').encode())
  b.flush()
 wait=os.environ.get('FAKE_STREAM_WAIT')
 if wait:
  for _ in range(400):
   if pathlib.Path(wait).exists():break
   time.sleep(.05)
pathlib.Path(get('--output-dir'),'export.json').write_text(text)
print('NEVER-IN-RECEIPT')
print('NEVER-IN-RECEIPT',file=sys.stderr)
raise SystemExit(code)
'''


class VibeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vibe-offline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prompt = self.root / "large task with spaces.md"
        self.prompt.write_text("a" * 150000)
        self.receipts = self.root / "private receipts"
        self.receipts.mkdir(mode=0o700)
        cli = self.root / "vibe"
        cli.write_text("#!" + sys.executable + "\n" + FAKE)
        cli.chmod(0o700)
        self.marker = self.root / "calls"
        self.env = dict(os.environ, PATH=str(self.root)+os.pathsep+os.environ['PATH'],
                        MARKER=str(self.marker), EXPECT_PROMPT_LENGTH="150000",
                        VIBE_ACTIVE_MODEL="wrong", VIBE_INVENTED_OVERRIDE="wrong")

    def invoke(self, *args, **env):
        return subprocess.run([sys.executable,"-B",str(SCRIPT),"--model","glm-5-3",
                               "--prompt-file",str(self.prompt),"--receipt-dir",str(self.receipts),*args],
                              env=dict(self.env,**env),capture_output=True,text=True,timeout=30)

    def receipt(self):
        paths=list(self.receipts.glob('vibe-run-*/receipt.json'))
        self.assertEqual(len(paths),1)
        return json.loads(paths[0].read_text())

    def test_exact_pins_actual_usage_private_transport_and_one_call(self):
        p=self.invoke()
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(r['export']['usage']['input_tokens'],198950)
        self.assertEqual(r['export']['estimated_cost_usd'],.2888084)
        self.assertEqual(r['native_limits']['max_tokens'],2000000)
        self.assertEqual(r['budget_group'],'mistral')
        self.assertEqual(r['effective_model'],'unknown')
        self.assertEqual(self.marker.read_text(),'call\n')
        self.assertNotIn('NEVER-IN-RECEIPT',json.dumps(r)+p.stdout+p.stderr)

    def test_second_model_and_substantial_budget(self):
        p=self.invoke('--model','mistral-medium-3-5','--max-tokens','4000000','--max-price','10',
                      EXPECT_TOKENS='4000000',EXPECT_PRICE='10')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.receipt()['configured_wire_model'],'mistral-medium-3-5')

    def test_native_limit_exit_three_is_not_provider_exhaustion(self):
        p=self.invoke(FAKE_EXIT='3')
        self.assertEqual(p.returncode,3,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],3)
        self.assertEqual(r['export']['outcome'],'token_limit')
        self.assertEqual(r['remaining_allowance'],'unknown')
        self.assertEqual(self.marker.read_text(),'call\n')

    def test_missing_or_malformed_export_cannot_report_success(self):
        for mode in ['missing','nan','bool','legacy','duplicate','unsafe_reason']:
            with self.subTest(mode=mode):
                p=self.invoke(FAKE_MODE=mode)
                self.assertEqual(p.returncode,2,p.stderr)
                latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda p:p.stat().st_mtime_ns)[-1].read_text())
                self.assertEqual(latest['export_state'],'invalid_or_missing')
                self.assertNotIn('NEVER-IN-RECEIPT',json.dumps(latest))

    def test_missing_usage_remains_unknown_not_zero(self):
        p=self.invoke(FAKE_MODE='none')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertIsNone(self.receipt()['export']['usage'])
        self.assertIsNone(self.receipt()['export']['estimated_cost_usd'])

    def test_no_export_repeated_context_estimates_and_generic_three(self):
        p=self.invoke(FAKE_MODE='noexport', FAKE_EXIT='3')
        self.assertEqual(p.returncode,3,p.stderr)
        r=self.receipt(); b=r['budget_telemetry']
        # Prompt 150000 bytes, then 4 and 8 bytes of responses: second
        # request includes the first response, rather than counting input once.
        self.assertEqual(b['tokens']['used'],37500+37501+1+2)
        self.assertEqual(b['tokens']['provenance'],'estimated')
        self.assertEqual(b['turns']['used'],2)
        self.assertGreater(b['usd']['used'],0)
        self.assertEqual(b['usd']['provenance'],'estimated')
        self.assertEqual(r['process_exit'],3)
        self.assertEqual(r['stop_reason'],'unknown')
        self.assertNotIn('turn_limit',json.dumps(r))

    def test_usage_none_stream_fallback_and_reported_precedence(self):
        p=self.invoke(FAKE_MODE='none',FAKE_STREAM='1')
        self.assertEqual(p.returncode,0,p.stderr)
        b=self.receipt()['budget_telemetry']
        self.assertEqual(b['tokens']['provenance'],'estimated')
        self.assertGreater(b['tokens']['used'],0)
        self.assertGreater(b['usd']['used'],0)

    def test_current_twelve_million_bound_thinking_and_legacy_environment_api(self):
        p=self.invoke('--max-tokens','12000000','--max-turns','180','--thinking','medium',
                      EXPECT_TOKENS='12000000',EXPECT_THINKING='medium')
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(self.receipt()['requested_thinking'],'medium')
        # 2.26.1 behavior is preserved: every level travels through the
        # tested process-local overlay mechanism.
        p=self.invoke('--thinking','low',EXPECT_THINKING='low')
        self.assertEqual(p.returncode,0,p.stderr)
        latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
        self.assertEqual(latest['requested_thinking'],'low')
        self.assertEqual(latest['configured_wire_effort'],'low')
        env,_,_=worker.model_environment('glm-5-3',{'VIBE_HOME':'owned'})
        self.assertEqual(env['VIBE_HOME'],'owned')

    def test_invalid_bounds_unknown_model_and_unsupported_version_pre_call(self):
        for args in [('--max-price','nan'),('--max-price','inf'),('--max-tokens','0'),
                     ('--max-turns','0'),('--time-limit','nan'),('--model','wrong')]:
            with self.subTest(args=args):self.assertNotEqual(self.invoke(*args).returncode,0)
        self.assertNotEqual(self.invoke(FAKE_VERSION='2.0.0').returncode,0)
        self.assertFalse(self.marker.exists())
        self.assertFalse(list(self.receipts.iterdir()))

    def test_new_receipts_never_overwrite_and_taskfile_fallback(self):
        first=self.invoke();self.assertEqual(first.returncode,0,first.stderr)
        path=next(self.receipts.glob('vibe-run-*/receipt.json'));before=path.read_bytes()
        p=self.invoke('--prompt-file','',TASKFILE=str(self.prompt))
        self.assertEqual(p.returncode,0,p.stderr)
        self.assertEqual(path.read_bytes(),before)
        self.assertEqual(len(list(self.receipts.glob('vibe-run-*'))),2)

    def test_unsafe_task_files_are_refused_before_provider(self):
        self.prompt.unlink();os.mkfifo(self.prompt)
        self.assertNotEqual(self.invoke().returncode,0)
        self.prompt.unlink();self.prompt.symlink_to(__file__)
        self.assertNotEqual(self.invoke().returncode,0)
        self.assertFalse(self.marker.exists())

    def test_owned_deadline_output_bound_and_unrelated_process_survives(self):
        other=subprocess.Popen([sys.executable,'-c','import time;time.sleep(10)'])
        self.addCleanup(lambda:other.poll() is None and other.kill())
        with self.assertRaises(worker.Refusal):
            worker.owned_call([sys.executable,'-c','import time;time.sleep(10)'],dict(os.environ),.1)
        with self.assertRaises(worker.Refusal):
            worker.owned_call([sys.executable,'-c','print("x"*10000)'],dict(os.environ),2,output_limit=20)
        self.assertIsNone(other.poll())
        other.terminate();other.wait(timeout=3)

    def test_streaming_progress_labels_counts_and_privacy(self):
        p=self.invoke(FAKE_STREAM='1')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        prog=r['progress']
        self.assertEqual(prog['events'],10)
        self.assertEqual(prog['malformed_records'],4)
        self.assertEqual(prog['unlabeled_records'],4)
        self.assertEqual(prog['heartbeats'],0)
        self.assertEqual(prog['last_label'],'tool failure observed')
        self.assertIsInstance(prog['last_observed_at'],str)
        lines=[l for l in p.stdout.splitlines() if l.startswith('Vibe ')]
        self.assertEqual(len(lines),10)
        for label in ['assistant reasoning observed','assistant response observed',
                      'running shell command','reading file','editing file','writing file',
                      'searching files','updating task list','tool call observed',
                      'tool failure observed']:
            self.assertIn('Vibe progress: '+label,p.stdout)
        final=json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(final['progress_events'],10)
        self.assertEqual(final['progress_last_label'],'tool failure observed')
        self.assertNotIn('SECRET',p.stdout+p.stderr+json.dumps(r))
        raw=next(self.receipts.glob('vibe-run-*/native-stdout.log')).read_text()
        for secret in ['SECRET-PROMPT','SECRET-REASONING','SECRET-ANSWER','SECRET-CMD',
                       'SECRET-PATH','SECRET-ERROR']:
            self.assertIn(secret,raw)

    def test_public_progress_arrives_before_child_exit(self):
        sentinel=self.root/'child may exit'
        command=[sys.executable,'-B',str(SCRIPT),'--model','glm-5-3','--prompt-file',str(self.prompt),
                 '--receipt-dir',str(self.receipts)]
        proc=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                              env=dict(self.env,FAKE_STREAM='1',FAKE_STREAM_WAIT=str(sentinel)))
        try:
            seen=[]
            for line in proc.stdout:
                seen.append(line)
                if 'Vibe progress: assistant response observed' in line:
                    break
            self.assertTrue(any(l.startswith('Vibe progress: ') for l in seen))
            self.assertIsNone(proc.poll())
            sentinel.write_text('go\n')
            for line in proc.stdout:
                seen.append(line)
            proc.wait(timeout=30)
        finally:
            if proc.poll() is None:
                proc.kill()
        self.assertEqual(proc.returncode,0)
        text=''.join(seen)
        self.assertIn('Vibe progress: running shell command',text)
        self.assertIn('"progress_events": 10',text)

    def test_heartbeat_is_liveness_only_and_distinct_from_events(self):
        out=io.StringIO()
        progress=worker.Progress(stream=out)
        original=worker.HEARTBEAT_SECONDS
        worker.HEARTBEAT_SECONDS=.2
        try:
            code,_=worker.owned_call([sys.executable,'-c','import time;time.sleep(1)'],
                                     dict(os.environ),5,progress=progress)
        finally:
            worker.HEARTBEAT_SECONDS=original
        self.assertEqual(code,0)
        self.assertGreaterEqual(progress.heartbeats,2)
        self.assertEqual(progress.events,0)
        lines=out.getvalue().splitlines()
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(line.startswith('Vibe heartbeat: '),line)
        self.assertNotIn('Vibe progress:',out.getvalue())

    def test_progress_parser_handles_split_records_and_hostile_streams(self):
        out=io.StringIO()
        progress=worker.Progress(stream=out)
        record='{"type":"message","role":"assistant","content":[{"type":"text","text":"héllo"}]}'.encode()
        cut=record.index('é'.encode())+1
        progress.feed(record[:cut]);progress.feed(record[cut:]+b'\n')
        self.assertEqual(progress.events,1)
        progress.feed(b'{"type":"effect","detail":{"kind":"shell"},"state":{"status":"completed"}}\n')
        self.assertEqual(progress.last_label,'running shell command')
        progress.feed(b'{"type":"effect","detail":{"kind":"shell"},"state":{"status":"failed"}}\n')
        self.assertEqual(progress.last_label,'tool failure observed')
        progress.feed(b'{"type":"effect","detail":null,"state":{"status":"completed"}}\n')
        progress.feed(b'{"type":"message","role":"user"}\n')
        progress.feed(b'not json\n')
        progress.feed(b'['*60000+b']'*60000+b'\n')
        progress.feed(b'{"pad":"'+b'A'*300000+b'"}\n')
        self.assertEqual(progress.malformed,3)
        self.assertEqual(progress.unlabeled,2)
        for hostile in [
            b'{"type":"effect","detail":{"kind":[]},"state":{"status":"running"}}\n',
            b'{"type":"effect","detail":{"kind":{}},"state":{"status":"running"}}\n',
            b'{"type":"effect","detail":{"kind":"shell"},"state":{"status":[]}}\n',
            b'{"type":"effect","detail":{"kind":"shell"},"state":{"status":{}}}\n',
            b'{"type":"effect","detail":{"kind":123},"state":{"status":"completed"}}\n',
            b'{"type":"effect","detail":{"kind":"shell"},"state":{"status":123}}\n',
            b'{"type":[]}\n',
            b'{"type":"message","role":[]}\n',
        ]:
            progress.feed(hostile)
        self.assertEqual(progress.unlabeled,10)
        self.assertEqual(progress.events,3)
        progress.feed(b'{"type":"message","role":"assistant","content":[{"type":"text","text":"ok"}]}\n')
        self.assertEqual(progress.events,4)
        self.assertEqual(progress.last_label,'assistant response observed')
        self.assertLessEqual(len(progress.buffer),worker.PROGRESS_RECORD_BYTES+65536)
        for line in out.getvalue().splitlines():
            self.assertTrue(line.startswith('Vibe progress: '),line)
        self.assertNotIn('héllo',out.getvalue())

    def test_progress_public_lines_are_bounded(self):
        out=io.StringIO()
        progress=worker.Progress(stream=out)
        line=b'{"type":"reasoning","text":"x"}\n'
        for _ in range(worker.PROGRESS_LINES+500):
            progress.feed(line)
        self.assertEqual(progress.events,worker.PROGRESS_LINES+500)
        self.assertEqual(len(out.getvalue().splitlines()),worker.PROGRESS_LINES)

    def test_streaming_noise_does_not_break_failure_export_validation(self):
        p=self.invoke(FAKE_STREAM='1',FAKE_EXIT='3')
        self.assertEqual(p.returncode,3,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],3)
        self.assertEqual(r['export_state'],'valid')
        self.assertEqual(r['export']['outcome'],'token_limit')
        self.assertEqual(r['progress']['events'],10)
        self.assertNotIn('SECRET',json.dumps(r)+p.stdout+p.stderr)

    def test_hostile_valid_json_through_fake_cli_cannot_terminate_task(self):
        p=self.invoke(FAKE_STREAM='1',FAKE_HOSTILE='1')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],0)
        self.assertEqual(r['export_state'],'valid')
        prog=r['progress']
        self.assertEqual(prog['events'],11)
        self.assertEqual(prog['malformed_records'],4)
        self.assertEqual(prog['unlabeled_records'],10)
        self.assertEqual(prog['last_label'],'assistant response observed')
        self.assertIn('Vibe progress: assistant response observed',p.stdout)
        final=json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(final['progress_events'],11)
        self.assertEqual(final['progress_last_label'],'assistant response observed')
        self.assertEqual(final['adapter_exit'],0)
        self.assertEqual(final['process_exit'],0)
        self.assertEqual(final['export_state'],'valid')

    def test_hostile_valid_json_through_fake_cli_preserves_native_limit_exit(self):
        p=self.invoke(FAKE_STREAM='1',FAKE_HOSTILE='1',FAKE_EXIT='3')
        self.assertEqual(p.returncode,3,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],3)
        self.assertEqual(r['export_state'],'valid')
        self.assertEqual(r['export']['outcome'],'token_limit')
        self.assertEqual(r['progress']['events'],11)
        self.assertEqual(r['progress']['last_label'],'assistant response observed')

    def test_heartbeat_survives_child_closing_stdout_early_while_remaining_alive(self):
        out=io.StringIO()
        progress=worker.Progress(stream=out)
        original=worker.HEARTBEAT_SECONDS
        worker.HEARTBEAT_SECONDS=.2
        try:
            cmd='import os,time; os.close(1); time.sleep(.8)'
            code,_=worker.owned_call([sys.executable,'-c',cmd],dict(os.environ),5,progress=progress)
        finally:
            worker.HEARTBEAT_SECONDS=original
        self.assertEqual(code,0)
        self.assertGreaterEqual(progress.heartbeats,2)
        self.assertEqual(progress.events,0)
        lines=out.getvalue().splitlines()
        self.assertTrue(lines)
        for line in lines:
            self.assertTrue(line.startswith('Vibe heartbeat: '),line)
        self.assertNotIn('Vibe progress:',out.getvalue())

    def test_deadline_supervision_survives_child_closing_stdout_early(self):
        cmd='import os,time; os.close(1); time.sleep(10)'
        with self.assertRaises(worker.Refusal):
            worker.owned_call([sys.executable,'-c',cmd],dict(os.environ),.2)


FAKE31 = r'''
import json,os,pathlib,sys,time
if sys.argv[1:]==['--version']:
 print('vibe '+os.environ.get('FAKE_VERSION','3.1.1'));raise SystemExit()
a=sys.argv[1:]
pathlib.Path(os.environ['MARKER']).open('a').write('call\n')
get=lambda k:a[a.index(k)+1] if k in a else None
# 3.1.1 selection is the documented explicit --model ALIAS; no VIBE_* overlay.
assert get('--model')==os.environ['EXPECT_MODEL']
assert 'VIBE_ACTIVE_MODEL' not in os.environ and 'VIBE_MODELS' not in os.environ
assert 'VIBE_ALLOWED_MODELS' not in os.environ and 'VIBE_COMPACTION_MODEL' not in os.environ
assert os.environ['VIBE_ENABLE_UPDATE_CHECKS']=='false' and os.environ['VIBE_ENABLE_AUTO_UPDATE']=='false'
assert 'VIBE_INVENTED_OVERRIDE' not in os.environ
assert get('--output')=='json' and get('--agent')=='auto-approve' and '--trust' in a
assert '-p' not in a and '--auto-approve' not in a
for flag,key,conv in [('--max-price','EXPECT_PRICE',float),('--max-tokens','EXPECT_TOKENS',int),
                      ('--time-limit','EXPECT_TIME',float),('--max-turns','EXPECT_TURNS',int)]:
 if os.environ.get(key,'')=='':
  assert get(flag) is None,(flag,'must be omitted')
 else:
  assert conv(get(flag))==conv(os.environ[key]),(flag,get(flag))
assert [a[i+1] for i,v in enumerate(a) if v=='--enabled-tools']==['bash','read_file','write_file','edit','grep']
content=pathlib.Path(get('--prompt-file')).read_text()
assert len(content)==int(os.environ['EXPECT_PROMPT_LENGTH'])
assert content not in ' '.join(a)
mode=os.environ.get('FAKE_MODE','ok');code=int(os.environ.get('FAKE_EXIT','0'))
if mode=='missing':raise SystemExit(code)
if mode=='sleep':time.sleep(float(os.environ.get('FAKE_SLEEP','5')));raise SystemExit(code)
msgs=[{'role':'user','content':[{'type':'text','text':'SECRET-PROMPT'}]},
      {'role':'assistant','content':[{'type':'text','text':'SECRET-ACK'}]},
      {'role':'assistant','content':[{'type':'text','text':'SECRET-VERDICT accepted'}]}]
if mode=='nomessages':msgs=[{'role':'user','content':[{'type':'text','text':'x'}]}]
if mode=='notlist':msgs={'messages':[]}
# Real captured 3.1.1 shapes: assistant content as plain strings, and a
# history ending in a tool-call-only assistant entry.
if mode=='strings':
 msgs=[{'role':'user','content':[{'type':'text','text':'SECRET-PROMPT'}]},
       {'role':'assistant','content':'SECRET-ACK'},
       {'role':'assistant','content':'SECRET-VERDICT accepted'}]
if mode=='toolonly':
 msgs=[{'role':'user','content':[{'type':'text','text':'SECRET-PROMPT'}]},
       {'role':'assistant','content':[{'type':'text','text':'SECRET-ACK'}]},
       {'role':'assistant','content':[],'tool_calls':[{'id':'t1','type':'function','function':{'name':'read_file','arguments':'{}'}}]}]
sys.stdout.write(json.dumps(msgs))
if mode=='garbage':sys.stdout.write(' this is not json')
if mode=='trailing':sys.stdout.write('\nNEVER-IN-RECEIPT\n')
alias=os.environ['EXPECT_MODEL'];wire=os.environ['EXPECT_WIRE']
config=json.loads(os.environ.get('FAKE_CONFIG',
    '{"active_model":"%s","routed_model_config":{"name":"%s","provider":"mistral","alias":"%s","thinking":"%s"}}'
    %(alias,wire,alias,os.environ.get('EXPECT_THINKING','high'))))
x={'schema_version':1,'vibe_version':'3.1.1','outcome':os.environ.get('FAKE_OUTCOME','finished' if code==0 else 'turn_limit'),
   'stop_reason':None if code==0 else 'limit','exit_code':code,'session_id':'sess',
   'usage':{'input_tokens':1543219,'output_tokens':26307,'cached_input_tokens':1273088,'total_tokens':1569526},
   'cost_usd':0.0,'steps':33,'config':config,'error':{'message':'NEVER-IN-RECEIPT'},
   'limits':{'max_turns':None if get('--max-turns') is None else int(get('--max-turns')),
             'max_price':None if get('--max-price') is None else float(get('--max-price')),
             'max_tokens':None if get('--max-tokens') is None else int(get('--max-tokens')),
             'time_limit_s':None if get('--time-limit') is None else float(get('--time-limit'))}}
if os.environ.get('FAKE_ERROR') is not None:x['error']=json.loads(os.environ['FAKE_ERROR'])
if x['outcome'] in ('usage_error','config_error'):
 x['stop_reason']=None;x['usage']=None;x['cost_usd']=None
if mode=='badlimits':x['limits']={'max_turns':'many'}
if mode=='badsteps':x['steps']=-1
out=pathlib.Path(get('--output-dir'))
(out/'export.json').write_text(json.dumps(x))
# The native CLI records the session's actually selected client model under
# the output directory; FAKE_SESSION_META='' omits it, a JSON string replaces it.
if os.environ.get('FAKE_SESSION_META','default')!='':
 pathlib.Path(out,'session').mkdir(exist_ok=True)
 pathlib.Path(out,'session','meta.json').write_text(os.environ.get('FAKE_SESSION_META') or json.dumps({'active_model':alias,'model_name':wire}))
print('NEVER-IN-RECEIPT',file=sys.stderr)
raise SystemExit(code)
'''


class Vibe31Tests(unittest.TestCase):
    """Vibe 3.1.1: explicit --model alias, --output json message list, omittable caps."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="vibe31-offline-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prompt = self.root / "task.md"
        self.prompt.write_text("b" * 4096)
        self.receipts = self.root / "receipts"
        self.receipts.mkdir(mode=0o700)
        cli = self.root / "vibe"
        cli.write_text("#!" + sys.executable + "\n" + FAKE31)
        cli.chmod(0o700)
        self.marker = self.root / "calls"
        self.env = dict(os.environ, PATH=str(self.root)+os.pathsep+os.environ['PATH'],
                        MARKER=str(self.marker), EXPECT_PROMPT_LENGTH="4096",
                        EXPECT_MODEL="mistral-large-4-0-3", EXPECT_WIRE="mistral-large-4-0",
                        EXPECT_PRICE="5.0", EXPECT_TOKENS="2000000", EXPECT_TIME="5400", EXPECT_TURNS="120",
                        VIBE_ACTIVE_MODEL="wrong", VIBE_INVENTED_OVERRIDE="wrong")

    def invoke(self, *args, **env):
        return subprocess.run([sys.executable,"-B",str(SCRIPT),"--model","mistral-large-4-0-3",
                               "--prompt-file",str(self.prompt),"--receipt-dir",str(self.receipts),*args],
                              env=dict(self.env,**env),capture_output=True,text=True,timeout=30)

    def receipt(self):
        paths=list(self.receipts.glob('vibe-run-*/receipt.json'))
        self.assertEqual(len(paths),1)
        return json.loads(paths[0].read_text())

    def test_311_explicit_model_json_verified_selection_final_response_and_unpriced_usd(self):
        p=self.invoke()
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(r['cli_version'],'3.1.1')
        self.assertEqual(r['output_mode'],'json')
        self.assertEqual(r['requested_model'],'mistral-large-4-0-3')
        self.assertEqual(r['configured_wire_model'],'mistral-large-4-0')
        self.assertEqual(r['configured_wire_effort'],'unknown')
        self.assertEqual(r['effective_model'],'unknown')
        self.assertEqual(r['remaining_allowance'],'unknown')
        sel=r['session_selection']
        self.assertEqual(sel['state'],'verified')
        self.assertEqual(sel['session_alias'],'mistral-large-4-0-3')
        self.assertEqual(sel['session_wire'],'mistral-large-4-0')
        self.assertEqual(sel['session_thinking'],'high')
        fr=r['final_response']
        self.assertEqual(fr['state'],'present')
        self.assertEqual(fr['message_count'],3)
        self.assertEqual(fr['assistant_messages'],2)
        self.assertEqual(fr['final_index'],2)  # the LAST assistant reply, not an earlier ack
        self.assertEqual(len(fr['final_sha256']),64)
        self.assertGreater(fr['final_text_bytes'],0)
        self.assertEqual(r['export']['usage']['total_tokens'],1569526)
        self.assertEqual(r['export']['usage']['cached_input_tokens'],1273088)
        self.assertEqual(r['export']['limits']['max_turns'],120)
        self.assertEqual(r['omitted_caps'],[])
        b=r['budget_telemetry']
        self.assertEqual(b['tokens'],{'used':1569526,'cap':2000000,'provenance':'reported'})
        self.assertEqual(b['turns'],{'used':2,'cap':120,'provenance':'estimated'})
        # Unpriced Mistral4: USD stays unknown, never 0/free, even with a native cost field.
        self.assertEqual(b['usd']['used'],None)
        self.assertEqual(b['usd']['provenance'],'unknown')
        self.assertTrue(any('unknown, not zero' in n for n in b['notes']))
        self.assertEqual(self.marker.read_text(),'call\n')
        self.assertNotIn('NEVER-IN-RECEIPT',json.dumps(r)+p.stdout+p.stderr)
        self.assertNotIn('SECRET',json.dumps(r)+p.stdout+p.stderr)
        raw=next(self.receipts.glob('vibe-run-*/native-stdout.log')).read_text()
        self.assertIn('SECRET-VERDICT accepted',raw)  # raw/private evidence preserved
        final=json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(final['cli_version'],'3.1.1')
        self.assertEqual(final['selection'],'verified')
        self.assertEqual(final['final_response'],'present')
        self.assertEqual(final['adapter_exit'],0)

    def test_311_owner_can_omit_caps_and_native_defaults_are_recorded(self):
        p=self.invoke('--max-turns','none','--time-limit','none',
                      EXPECT_TURNS='',EXPECT_TIME='')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(sorted(r['omitted_caps']),['max_turns','time_limit'])
        self.assertIsNone(r['native_limits']['max_turns'])
        self.assertIsNone(r['native_limits']['time_limit'])
        self.assertEqual(r['export']['limits']['max_turns'],None)
        self.assertIsNone(r['export']['limits']['time_limit_s'])
        # Omission is not an unlimited claim: supervisor bound remains, recorded separately.
        self.assertEqual(r['supervisor_seconds'],7220)
        b=r['budget_telemetry']
        self.assertIsNone(b['turns']['cap'])
        self.assertEqual(b['tokens']['cap'],2000000)

    def test_311_native_limit_exit_three_and_stop_reason(self):
        p=self.invoke(FAKE_EXIT='3')
        self.assertEqual(p.returncode,3,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],3)
        self.assertEqual(r['adapter_exit'],3)
        self.assertEqual(r['export']['outcome'],'turn_limit')
        self.assertEqual(r['stop_reason'],'turn_cap')
        self.assertEqual(r['session_selection']['state'],'verified')

    def test_311_exit_zero_without_export_is_incomplete(self):
        p=self.invoke(FAKE_MODE='missing',FAKE_EXIT='0')
        self.assertEqual(p.returncode,2,p.stderr)
        r=self.receipt()
        self.assertEqual(r['export_state'],'invalid_or_missing')
        self.assertEqual(r['session_selection']['state'],'unknown')
        final=json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(final['adapter_exit'],2)
        self.assertEqual(final['export_state'],'invalid_or_missing')

    def test_311_malformed_export_limits_or_steps_refused(self):
        for mode in ('badlimits','badsteps'):
            with self.subTest(mode=mode):
                p=self.invoke(FAKE_MODE=mode)
                self.assertEqual(p.returncode,2,p.stderr)
                latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
                self.assertEqual(latest['export_state'],'invalid_or_missing')

    def test_311_selection_mismatch_and_missing_metadata_never_verified(self):
        p=self.invoke(FAKE_CONFIG='{"active_model":"glm-5-3","routed_model_config":{"name":"zai-glm-5-3","alias":"glm-5-3","thinking":"low"}}',
                      FAKE_SESSION_META='')
        self.assertEqual(p.returncode,0,p.stderr)
        sel=self.receipt()['session_selection']
        self.assertEqual(sel['state'],'mismatch')
        self.assertEqual(sel['session_alias'],'glm-5-3')
        self.assertIn('!= requested',sel['detail'])
        p=self.invoke(FAKE_CONFIG='{}',FAKE_SESSION_META='')
        self.assertEqual(p.returncode,0,p.stderr)
        latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
        self.assertEqual(latest['session_selection']['state'],'unknown')
        self.assertNotIn('NEVER-IN-RECEIPT',json.dumps(latest))

    def test_311_selected_identity_comes_from_session_meta_before_routed_default(self):
        # Real captured 3.1.1 GLM session shape (sanitized to model IDs): the
        # session selected glm-5-3 / wire zai-glm-5-3 while the export's
        # routed_model_config describes the account's DEFAULT Mistral Large 4
        # route. The default must never be read as this session's selection.
        config=json.dumps({'active_model':'glm-5-3','routed_default_model':'mistral-large-4-0-3',
                           'routed_model_config':{'name':'mistral-large-4-0','provider':'mistral',
                                                  'alias':'mistral-large-4-0-3','thinking':'high'},
                           'models':{'glm-5-3':{'name':'zai-glm-5-3','alias':'glm-5-3',
                                               'provider':'mistral','thinking':'high'}}})
        p=self.invoke('--model','glm-5-3',EXPECT_MODEL='glm-5-3',EXPECT_WIRE='zai-glm-5-3',
                      FAKE_CONFIG=config,
                      FAKE_SESSION_META='{"active_model":"glm-5-3","model_name":"zai-glm-5-3"}')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt(); sel=r['session_selection']
        self.assertEqual(sel['state'],'verified')
        self.assertEqual(sel['session_alias'],'glm-5-3')
        self.assertEqual(sel['session_wire'],'zai-glm-5-3')
        # The contradicting default observation is preserved separately.
        self.assertEqual(sel['routed_default_alias'],'mistral-large-4-0-3')
        self.assertEqual(sel['routed_default_wire'],'mistral-large-4-0')
        self.assertIn('not this session\'s selection',sel['detail'])
        # Manifest identity stays client-side only.
        self.assertEqual(r['effective_model'],'unknown')
        self.assertEqual(r['effective_effort'],'unknown')
        # Session metadata alone identifies the session even when the export
        # config carries only a default thinking declaration; the default's
        # effort is preserved separately and never proves the session level.
        p=self.invoke(FAKE_CONFIG='{"routed_model_config":{"thinking":"high"}}',
                      FAKE_SESSION_META='{"active_model":"mistral-large-4-0-3","model_name":"mistral-large-4-0"}')
        self.assertEqual(p.returncode,0,p.stderr)
        latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
        sel=latest['session_selection']
        self.assertEqual(sel['state'],'verified')
        self.assertEqual(sel['session_alias'],'mistral-large-4-0-3')
        self.assertEqual(sel['session_wire'],'mistral-large-4-0')
        self.assertIsNone(sel['session_thinking'])
        self.assertEqual(sel['routed_default_thinking'],'high')

    def test_311_partial_or_default_only_metadata_never_verifies(self):
        # A catalog/default thinking declaration with no actual selected
        # alias/wire identity can never become a verified selection, and it
        # is not proof that the requested level took effect.
        for config in ('{"routed_model_config":{"thinking":"high"}}',
                       '{"routed_model_config":{"name":"zai-glm-5-3","alias":"glm-5-3","thinking":"high"}}'):
            with self.subTest(config=config):
                p=self.invoke(FAKE_CONFIG=config,FAKE_SESSION_META='')
                self.assertEqual(p.returncode,0,p.stderr)
                latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
                sel=latest['session_selection']
                self.assertEqual(sel['state'],'unknown')
                self.assertIsNone(sel['session_alias'])
                self.assertIsNone(sel['session_wire'])
                self.assertIsNone(sel['session_thinking'])

    def test_311_string_final_text_and_textless_trailing_entry(self):
        # The real 3.1.1 message list uses assistant.content strings; an
        # earlier acknowledgment is never selected as the final delivery.
        p=self.invoke(FAKE_MODE='strings')
        self.assertEqual(p.returncode,0,p.stderr)
        fr=self.receipt()['final_response']
        self.assertEqual(fr['state'],'present')
        self.assertEqual(fr['message_count'],3)
        self.assertEqual(fr['final_index'],2)
        self.assertEqual(fr['final_content_form'],'string')
        self.assertGreater(fr['final_text_bytes'],0)
        self.assertEqual(len(fr['final_sha256']),64)
        raw=next(self.receipts.glob('vibe-run-*/native-stdout.log')).read_text()
        self.assertIn('SECRET-VERDICT accepted',raw)
        # History ending in a tool-call-only assistant entry: recorded with
        # provenance, but never as a completed text delivery.
        p=self.invoke(FAKE_MODE='toolonly')
        self.assertEqual(p.returncode,0,p.stderr)
        latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
        fr=latest['final_response']
        self.assertEqual(fr['state'],'final_without_text')
        self.assertEqual(fr['final_index'],2)
        self.assertEqual(fr['final_text_bytes'],0)
        self.assertEqual(len(fr['final_sha256']),64)
        final=json.loads(p.stdout.strip().splitlines()[-1])
        self.assertEqual(final['final_response'],'final_without_text')

    def test_311_unsupported_thinking_levels_refuse_before_provider(self):
        # 3.1.1 has no real thinking control (no overlay mechanism, no native
        # flag); a low/medium request would silently execute the account's
        # existing level, so it is refused before the provider with
        # actionable documentation, not silently accepted.
        for level in ('low','medium'):
            with self.subTest(level=level):
                p=self.invoke('--thinking',level)
                self.assertEqual(p.returncode,2,p.stderr)
                self.assertIn('thinking control',p.stderr)
                self.assertIn('2.26.1',p.stderr)
                self.assertFalse(self.marker.exists())
                self.assertFalse(list(self.receipts.iterdir()))
        # 'high' (the observed catalog level of the validated aliases) still
        # runs, recorded with the effective effort unknown, never as verified
        # server-side control.
        p=self.invoke('--thinking','high')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(r['requested_thinking'],'high')
        self.assertEqual(r['configured_wire_effort'],'unknown')
        self.assertEqual(r['effective_effort'],'unknown')

    def test_311_thinking_mismatch_is_explicit(self):
        # A requested level that the selected model's own declaration
        # contradicts is an explicit mismatch, never a silent substitution.
        p=self.invoke(FAKE_CONFIG='{"active_model":"mistral-large-4-0-3","routed_model_config":{"name":"mistral-large-4-0","alias":"mistral-large-4-0-3","thinking":"low"}}',
                      FAKE_SESSION_META='')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(r['requested_thinking'],'high')
        self.assertEqual(r['session_selection']['state'],'mismatch')
        self.assertIn('thinking low != requested high',r['session_selection']['detail'])

    def test_311_garbage_or_assistantless_message_list_keeps_export_verdict(self):
        for mode,state in (('garbage','invalid'),('notlist','invalid'),('trailing','invalid'),
                           ('nomessages','no_final_assistant')):
            with self.subTest(mode=mode):
                p=self.invoke(FAKE_MODE=mode)
                self.assertEqual(p.returncode,0,p.stderr)
                latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
                self.assertEqual(latest['export_state'],'valid')
                self.assertEqual(latest['final_response']['state'],state)
                self.assertEqual(latest['session_selection']['state'],'verified')
                self.assertNotIn('SECRET',json.dumps(latest)+p.stdout)

    def test_311_native_deadline_and_limit_stops_are_preserved(self):
        p=self.invoke(FAKE_EXIT='3',FAKE_OUTCOME='deadline')
        self.assertEqual(p.returncode,3,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],3)
        self.assertEqual(r['export']['outcome'],'deadline')
        self.assertEqual(r['stop_reason'],'time_cap')
        self.assertEqual(r['remaining_allowance'],'unknown')
        p=self.invoke(FAKE_EXIT='3',FAKE_OUTCOME='price_limit')
        self.assertEqual(p.returncode,3,p.stderr)
        latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
        self.assertEqual(latest['stop_reason'],'price_cap')
        # The adapter's own supervisor deadline stays separate (owned group kill):
        with self.assertRaises(worker.Refusal):
            worker.owned_call([sys.executable,'-c','import time;time.sleep(5)'],dict(os.environ),.2)

    def test_model_and_none_caps_are_version_gated_before_provider(self):
        # mistral-medium-3-5 is not a validated 3.1.1 alias: refuse, no call, no receipt.
        p=self.invoke('--model','mistral-medium-3-5')
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertIn('unsupported_model_for_cli_version',p.stderr)
        self.assertFalse(self.marker.exists())
        self.assertFalse(list(self.receipts.iterdir()))
        # ...and the Mistral4 alias is not a validated 2.26.1 pin.
        p=self.invoke('--model','mistral-large-4-0-3',FAKE_VERSION='2.26.1')
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertIn('unsupported_model_for_cli_version',p.stderr)
        self.assertFalse(self.marker.exists())
        # 'none' caps are unsupported on 2.26.1: refused before provider.
        p=self.invoke('--max-turns','none',FAKE_VERSION='2.26.1',EXPECT_TURNS='')
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertIn('none',p.stderr)
        self.assertFalse(self.marker.exists())
        self.assertFalse(list(self.receipts.iterdir()))
        # Unknown versions still refuse before provider.
        p=self.invoke(FAKE_VERSION='3.2.0')
        self.assertEqual(p.returncode,2,p.stderr)
        self.assertIn('unsupported_cli',p.stderr)
        self.assertFalse(self.marker.exists())

    def test_311_contract_parity_for_new_alias_and_none(self):
        def contract(*args):
            cp=subprocess.run([sys.executable,"-B",str(SCRIPT),"--contract-validate",
                               "--model","mistral-large-4-0-3","--receipt-dir","/private",*args],
                              capture_output=True,text=True,timeout=10)
            return json.loads(cp.stdout)
        self.assertEqual(contract()['state'],'valid')
        self.assertEqual(contract('--max-turns','none','--max-price','none','--max-tokens','none','--time-limit','none')['state'],'valid')
        # The offline preflight cannot know the CLI version, so it accepts the
        # union of thinking choices exactly as it accepts the union of cap
        # choices; the run narrows per detected version before the provider.
        self.assertEqual(contract('--thinking','low')['state'],'valid')
        self.assertEqual(contract('--thinking','medium')['state'],'valid')
        self.assertEqual(contract('--turns','none')['state'],'invalid')
        self.assertEqual(contract('--max-turns','181')['state'],'invalid')
        self.assertEqual(contract('--max-tokens','0')['state'],'invalid')
        self.assertEqual(contract('--max-price','nan')['state'],'invalid')
        self.assertEqual(contract('--max-tokens','1.5')['state'],'invalid')
        self.assertEqual(contract('--max-turns','0x10')['state'],'invalid')
        self.assertEqual(contract('--thinking','extrahigh')['state'],'invalid')

    def test_311_glm_alias_supported_with_wire_verification(self):
        p=self.invoke('--model','glm-5-3',EXPECT_MODEL='glm-5-3',EXPECT_WIRE='zai-glm-5-3')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(r['configured_wire_model'],'zai-glm-5-3')
        self.assertEqual(r['session_selection']['state'],'verified')
        self.assertEqual(r['session_selection']['session_wire'],'zai-glm-5-3')
        self.assertNotIn('setup_reason',r)
        self.assertNotIn('setup_reason',r.get('export') or {})
        self.assertNotIn('Vibe setup:',p.stdout)

    def test_311_usage_error_unavailable_alias_keeps_exit_one_and_unknown_usage(self):
        # Sanitized original 2026-11-13 export shape: usage_error / Unknown
        # model for the pinned mistral-large-4-0-3 alias. Available-list and
        # credential-looking tail must never enter the receipt or public line.
        original=('Unknown model: mistral-large-4-0-3. Available: glm-5-3, '
                  'mistral-medium-3.5, zai-glm-5-3-flash '
                  'sk-live-SECRET Bearer eyJhbGciOi https://evil.example/path '
                  '/home/user/.config/vibe session-abc')
        p=self.invoke(FAKE_EXIT='1',FAKE_OUTCOME='usage_error',
                      FAKE_ERROR=json.dumps({'message':original,'code':None}))
        self.assertEqual(p.returncode,1,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],1)
        self.assertEqual(r['adapter_exit'],1)
        self.assertEqual(r['export_state'],'valid')
        self.assertEqual(r['export']['outcome'],'usage_error')
        self.assertIsNone(r['export']['usage'])
        self.assertEqual(r['remaining_allowance'],'unknown')
        self.assertEqual(r['effective_model'],'unknown')
        self.assertEqual(r['stop_reason'],'setup')
        reason=r['setup_reason']
        self.assertEqual(reason,r['export']['setup_reason'])
        self.assertEqual(reason['state'],'recognized')
        self.assertEqual(reason['category'],'unavailable_model')
        self.assertEqual(reason['alias'],'mistral-large-4-0-3')
        self.assertIsNone(reason['argument'])
        self.assertEqual(reason['summary'],
                         'Requested model alias is unavailable on this CLI catalog')
        public=p.stdout
        self.assertIn('Vibe setup: Requested model alias mistral-large-4-0-3 is unavailable on this CLI catalog',public)
        final=json.loads(public.strip().splitlines()[-1])
        self.assertEqual(final['setup_reason'],'unavailable_model')
        self.assertEqual(final['adapter_exit'],1)
        leaked=json.dumps(r)+public+p.stderr
        for secret in ('sk-live-SECRET','Bearer eyJ','https://evil.example',
                       '/home/user/.config/vibe','session-abc','NEVER-IN-RECEIPT',
                       'mistral-medium-3.5','Available:'):
            self.assertNotIn(secret,leaked)
        # Cap/quota outcomes stay separate: a native limit is not a setup reason.
        p=self.invoke(FAKE_EXIT='3',FAKE_OUTCOME='token_limit')
        self.assertEqual(p.returncode,3,p.stderr)
        latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
        self.assertEqual(latest['stop_reason'],'token_cap')
        self.assertNotIn('setup_reason',latest)
        self.assertNotIn('Vibe setup:',p.stdout)

    def test_311_unknown_malformed_and_invalid_native_argument_setup_reasons(self):
        p=self.invoke(FAKE_EXIT='1',FAKE_OUTCOME='usage_error')
        self.assertEqual(p.returncode,1,p.stderr)
        r=self.receipt()
        self.assertEqual(r['setup_reason']['state'],'unknown')
        self.assertEqual(r['setup_reason']['category'],'unknown')
        self.assertIsNone(r['setup_reason']['alias'])
        self.assertNotIn('NEVER-IN-RECEIPT',json.dumps(r)+p.stdout+p.stderr)
        self.assertIn('Vibe setup: Unknown setup failure',p.stdout)
        p=self.invoke(FAKE_EXIT='1',FAKE_OUTCOME='config_error',
                      FAKE_ERROR=json.dumps({'message':"error: argument --max-turns: invalid int value: 'nope'"}))
        self.assertEqual(p.returncode,1,p.stderr)
        latest=json.loads(sorted(self.receipts.glob('vibe-run-*/receipt.json'),key=lambda q:q.stat().st_mtime_ns)[-1].read_text())
        reason=latest['setup_reason']
        self.assertEqual(reason['category'],'invalid_native_argument')
        self.assertEqual(reason['argument'],'max-turns')
        self.assertIn('Vibe setup: Native CLI rejected launch argument --max-turns',p.stdout)
        self.assertNotIn('nope',json.dumps(latest)+p.stdout+p.stderr)


class SetupReasonTests(unittest.TestCase):
    """Direct classifier coverage; no CLI and no provider."""

    ORIGINAL=('Unknown model: mistral-large-4-0-3. Available: glm-5-3, '
              'mistral-medium-3.5, zai-glm-5-3-flash')

    def test_original_unavailable_alias_is_recognized_without_available_list(self):
        reason=worker.setup_reason('usage_error',{'message':self.ORIGINAL,'code':None})
        self.assertEqual(reason['category'],'unavailable_model')
        self.assertEqual(reason['alias'],'mistral-large-4-0-3')
        dumped=json.dumps(reason)
        self.assertNotIn('Available:',dumped)
        self.assertNotIn('mistral-medium-3.5',dumped)
        self.assertNotIn(self.ORIGINAL,dumped)

    def test_credential_looking_payloads_are_redacted(self):
        payload=('Unknown model: mistral-large-4-0-3. Available: glm-5-3 '
                 'sk-live-SECRET api_key=SECRET token=SECRET '
                 'https://accounts.example/oauth /etc/passwd sess-XYZ')
        reason=worker.setup_reason('usage_error',{'message':payload})
        self.assertEqual(reason['alias'],'mistral-large-4-0-3')
        dumped=json.dumps(reason)
        for secret in ('sk-live-SECRET','api_key=SECRET','token=SECRET',
                       'https://accounts.example','/etc/passwd','sess-XYZ','Available:'):
            self.assertNotIn(secret,dumped)

    def test_invalid_malformed_unknown_and_non_setup_outcomes_stay_unknown_or_absent(self):
        self.assertIsNone(worker.setup_reason('finished',{'message':self.ORIGINAL}))
        self.assertIsNone(worker.setup_reason('token_limit',{'message':self.ORIGINAL}))
        self.assertEqual(worker.setup_reason('usage_error',None)['state'],'unknown')
        self.assertEqual(worker.setup_reason('usage_error','boom')['state'],'unknown')
        self.assertEqual(worker.setup_reason('usage_error',{'message':['x']})['state'],'unknown')
        self.assertEqual(worker.setup_reason('usage_error',{'message':''})['state'],'unknown')
        self.assertEqual(worker.setup_reason('usage_error',{'message':'A'*513})['state'],'unknown')
        self.assertEqual(worker.setup_reason('usage_error',{'message':'quota exceeded'})['state'],'unknown')
        self.assertEqual(worker.setup_reason('usage_error',
            {'message':'Unknown model: not-a-pinned-alias'})['state'],'unknown')
        self.assertIsNone(worker.setup_reason('usage_error',
            {'message':'Unknown model: not-a-pinned-alias'})['alias'])
        unrecognized=worker.setup_reason('config_error',{'message':'unrecognized arguments: --invented'})
        self.assertEqual(unrecognized['category'],'invalid_native_argument')
        self.assertIsNone(unrecognized['argument'])
        self.assertNotIn('--invented',json.dumps(unrecognized))
        flagged=worker.setup_reason('config_error',
            {'message':"Invalid value for '--time-limit': -1"})
        self.assertEqual(flagged['argument'],'time-limit')
        unlisted=worker.setup_reason('config_error',
            {'message':"Invalid value for '--evil-flag': SECRET"})
        self.assertEqual(unlisted['category'],'invalid_native_argument')
        self.assertIsNone(unlisted['argument'])
        self.assertNotIn('SECRET',json.dumps(unlisted))
        self.assertNotIn('evil-flag',json.dumps(unlisted))

    def test_2261_thinking_overlay_unchanged_and_usage_error_classifies(self):
        # Existing 2.26.1 thinking overlay path is a separate fixture class;
        # this only asserts the shared classifier does not depend on CLI version.
        reason=worker.setup_reason('usage_error',{'message':self.ORIGINAL})
        self.assertEqual(reason['alias'],'mistral-large-4-0-3')
        self.assertEqual(worker.THINKING_LEVELS,('low','medium','high'))
        env,_,_=worker.model_environment('glm-5-3','medium',cli_version='2.26.1')
        overlay=json.loads(env['VIBE_MODELS'])['glm-5-3']
        self.assertEqual(overlay['thinking'],'medium')


class Vibe2261SetupReasonTests(unittest.TestCase):
    """2.26.1 mock path: thinking overlay stays, setup reason is additive."""

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='vibe2261-setup-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.prompt=self.root/'task.md'
        self.prompt.write_text('c'*4096)
        self.receipts=self.root/'receipts'
        self.receipts.mkdir(mode=0o700)
        cli=self.root/'vibe'
        cli.write_text('#!'+sys.executable+'\n'+FAKE)
        cli.chmod(0o700)
        self.marker=self.root/'calls'
        self.env=dict(os.environ,PATH=str(self.root)+os.pathsep+os.environ['PATH'],
                      MARKER=str(self.marker),EXPECT_PROMPT_LENGTH='4096',
                      VIBE_ACTIVE_MODEL='wrong',VIBE_INVENTED_OVERRIDE='wrong')

    def invoke(self,*args,**env):
        return subprocess.run([sys.executable,'-B',str(SCRIPT),'--model','glm-5-3',
                               '--prompt-file',str(self.prompt),'--receipt-dir',str(self.receipts),*args],
                              env=dict(self.env,**env),capture_output=True,text=True,timeout=30)

    def receipt(self):
        paths=list(self.receipts.glob('vibe-run-*/receipt.json'))
        self.assertEqual(len(paths),1)
        return json.loads(paths[0].read_text())

    def test_2261_medium_thinking_success_has_no_setup_reason(self):
        p=self.invoke('--thinking','medium',EXPECT_THINKING='medium')
        self.assertEqual(p.returncode,0,p.stderr)
        r=self.receipt()
        self.assertEqual(r['requested_thinking'],'medium')
        self.assertEqual(r['configured_wire_effort'],'medium')
        self.assertNotIn('setup_reason',r)
        self.assertNotIn('NEVER-IN-RECEIPT',json.dumps(r)+p.stdout+p.stderr)

    def test_2261_usage_error_unavailable_glm_alias(self):
        p=self.invoke(FAKE_EXIT='1',FAKE_OUTCOME='usage_error',
                      FAKE_ERROR=json.dumps({'message':'Unknown model: glm-5-3. Available: other'}))
        self.assertEqual(p.returncode,1,p.stderr)
        r=self.receipt()
        self.assertEqual(r['process_exit'],1)
        self.assertEqual(r['export']['outcome'],'usage_error')
        self.assertIsNone(r['export']['usage'])
        self.assertEqual(r['setup_reason']['alias'],'glm-5-3')
        self.assertNotIn('Available:',json.dumps(r)+p.stdout)
        self.assertNotIn('NEVER-IN-RECEIPT',json.dumps(r)+p.stdout+p.stderr)


if __name__=='__main__':
    unittest.main()
