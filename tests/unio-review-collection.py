#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed concurrent reviewer acceptance. Tiny real Git, offline providers only."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import time
import unittest

# Share only the existing installed real-Git fixture, not its test cases.
spec=importlib.util.spec_from_file_location('receipt_fixture',Path(__file__).with_name('unio-review-receipts.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

PROVIDER='''import hashlib,json,os,pathlib,subprocess,sys,time
root=pathlib.Path(sys.argv[1]);name=sys.argv[2];other='revtwo' if name=='revone' else 'revone'
action=json.loads((root/'control.json').read_text()).get(name,'approve')
common=pathlib.Path(os.environ['UNIO_ORIGINAL_TASKFILE'])
record=dict(pid=os.getpid(),sha256=hashlib.sha256(common.read_bytes()).hexdigest(),
            effective=pathlib.Path(os.environ['TASKFILE']).read_text())
if action=='hold':
    child=subprocess.Popen([sys.executable,'-c','import time;time.sleep(120)'])
    record['child_pid']=child.pid
(root/(name+'.started')).write_text(json.dumps(record))
with (root/'calls').open('a') as out:out.write(name+'\\n')
if action=='barrier':
    deadline=time.monotonic()+15
    while not (root/(other+'.started')).exists():
        if time.monotonic()>deadline:raise SystemExit('overlap barrier timed out')
        time.sleep(.03)
    (root/(name+'.overlap')).write_text('yes')
if action=='hold':
    deadline=time.monotonic()+60
    while not (root/'release').exists():
        if time.monotonic()>deadline:raise SystemExit('release event missing')
        time.sleep(.03)
    child.terminate();child.wait()
if action=='timeout':time.sleep(20)
if action=='drift':(root/'project/wt/mock/hello.txt').write_text('changed during review')
if action=='snapshot_fail':os.mkfifo(root/'project/wt/mock/unsupported')
if action=='material':common.write_text('changed common material')
if action=='break_child':
    c=max((root/'project/coord/reports').glob('evidence.review-set.*/collection.json'),key=lambda p:p.stat().st_mtime_ns)
    a=next(a for a in json.loads(c.read_text())['attempts'] if a['reviewer']==name)
    (c.parent.parent/a['raw_directory']/'attempt.json').mkdir()
print('PRIVATE_COLLECTION_PROSE')
print('PRIVATE_COLLECTION_ERROR',file=sys.stderr)
print('VERDICT: '+('REQUEST-CHANGES' if action=='changes' else 'APPROVE'))
if action=='unknown':print('VERDICT: APPROVE')
raise SystemExit(7 if action=='fail' else 0)
'''

class ReviewCollection(unittest.TestCase):
    setUpClass=classmethod(fixture.ReviewReceipts.setUpClass.__func__)
    call=fixture.ReviewReceipts.call
    unio=fixture.ReviewReceipts.unio
    controls=fixture.ReviewReceipts.controls
    calls=fixture.ReviewReceipts.calls
    receipts=fixture.ReviewReceipts.receipts
    summary=fixture.ReviewReceipts.summary

    def setUp(self):
        fixture.ReviewReceipts.setUp(self)
        (self.root/'provider.py').write_text(PROVIDER)
        self.unio('account','revone','alpha');self.unio('account','revtwo','beta')

    def collect(self,code=0,env=None):
        return self.unio('review-set','mock','evidence','revone','revtwo',code=code,env=env)

    def manifest(self):
        files=list((self.coord/'reports').glob('evidence.review-set.*/collection.json'))
        return json.loads(max(files,key=lambda p:p.stat().st_mtime_ns).read_text())

    def attempts(self):
        return [json.loads((self.coord/'reports'/a['raw_directory']/'receipt.json').read_text())
                for a in self.manifest()['attempts'] if a['receipt_id'] is not None]

    def start(self):
        p=subprocess.Popen([self.engine,'review-set','mock','evidence','revone','revtwo'],
            cwd=self.repo,env=self.env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        def cleanup():
            if p.poll() is None:
                p.terminate()
                try:p.communicate(timeout=20)
                except subprocess.TimeoutExpired:p.kill();p.communicate()
        self.addCleanup(cleanup)
        return p

    def until(self,predicate):
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            if predicate():return
            time.sleep(.05)
        self.fail('expected local event did not arrive')

    def test_parallel_frozen_input_receipt_bindings_and_history(self):
        self.controls(revone='changes');self.unio('review','mock','evidence','revone',code=1)
        old_result=self.unio('result','mock','evidence').stdout
        old_receipt=self.receipts()[0];old_bytes=old_receipt.read_bytes()
        for p in self.root.glob('*.started'):p.unlink()
        self.controls(revone='barrier',revtwo='barrier')
        p=self.collect(code=1) # older same-revision request must survive new approvals
        self.assertNotIn('PRIVATE_COLLECTION',p.stdout)
        self.assertEqual(json.loads(self.unio('result','mock','evidence').stdout)['review'],json.loads(old_result)['review'])
        self.assertEqual(old_receipt.read_bytes(),old_bytes)
        manifest=self.manifest();records=self.attempts()
        self.assertEqual(manifest['state'],'completed')
        self.assertEqual(manifest['before'],manifest['after'])
        self.assertEqual(len(records),2)
        self.assertEqual(len({r['id'] for r in records}),2)
        for i,(alias,group) in enumerate((('revone','alpha'),('revtwo','beta'))):
            self.assertEqual((self.root/(alias+'.overlap')).read_text(),'yes')
            seen=json.loads((self.root/(alias+'.started')).read_text())
            self.assertIn('budget_group: '+group+' ',seen['effective'])
            self.assertEqual(seen['sha256'],manifest['material_sha256'])
            attempt=manifest['attempts'][i];receipt=records[i]
            self.assertEqual(attempt['policy_task'],'rset-'+manifest['id']+'-'+str(i+1))
            self.assertEqual(attempt['receipt_id'],receipt['id'])
            self.assertEqual(receipt['material_sha256'],manifest['material_sha256'])
            self.assertEqual(receipt['before'],receipt['after'])
            self.assertEqual(receipt['reviewer'],alias)
            self.assertEqual(receipt['policy_group'],group)
            self.assertEqual((receipt['state'],receipt['process_exit_code']),('approved',0))
        self.assertEqual(self.summary(code=1,expect='revone,revtwo')['counts']['changes_requested'],1)

    def test_arguments_stop_and_material_preflight_make_no_calls(self):
        # Existing native task IDs may contain dots; only reviewer aliases use
        # the stricter configured-alias shape. Reuse the real verify boundary.
        (self.coord/'tasks/evidence.v2.md').write_bytes(self.task.read_bytes())
        self.unio('verify','mock','evidence.v2')
        self.unio('review-set','mock','evidence.v2','revone','revtwo')
        previous_calls=self.calls()
        self.unio('review-set','--help',cwd=self.root)
        for args in ((),('mock','evidence','revone'),('mock','evidence','revone','revone'),
                     ('mock','evidence','bad,alias','revtwo'),('mock','evidence','--json','revtwo'),
                     ('mock','evidence','revone','revtwo','--help'),
                     ('mock','evidence','revone','revtwo',*['x'+str(i) for i in range(7)])):
            self.unio('review-set',*args,code=2,cwd=self.root)
        completion=(self.install/'completion/unio').read_text()
        self.assertIn('reviews review-set race',completion)
        self.unio('stop');self.collect(code=2);self.unio('resume')
        self.unio('review-set','mock','evidence','revone','missing',code=2)
        self.unio('review-set','mock','evidence','revone','mock',code=2)
        self.unio('off','revtwo');self.collect(code=2);self.unio('on','revtwo')
        wt=self.root/'project/wt/mock'
        (wt/'hello.txt').write_text('dirty');self.collect(code=2)
        for data in (b'\0binary',b'x'*300001):
            (wt/'hello.txt').write_bytes(data)
            self.call(['git','add','hello.txt'],cwd=wt);self.call(['git','commit','-qm','material'],cwd=wt)
            self.unio('verify','mock','evidence');self.collect(code=2)
        self.assertEqual(self.calls(),previous_calls)
        self.assertFalse(list((self.coord/'reports').glob('evidence.review*')))

    def test_shared_budget_partial_admission_and_lead_reservation(self):
        self.unio('account','revone','shared');self.unio('account','revtwo','shared')
        self.controls(revone='hold',revtwo='hold');p=self.start()
        self.until(lambda:len(list(self.root.glob('*.started')))==1 and
            any('budget-refused' in f.read_text() for f in (self.coord/'reports').glob('rset-*.md')))
        self.assertEqual(len(self.calls().splitlines()),1)
        (self.root/'release').touch();stdout,stderr=p.communicate(timeout=25)
        self.assertEqual(p.returncode,2,(stdout,stderr))
        records=self.attempts()
        self.assertEqual(len(records),2)
        self.assertEqual(sorted(r['process_exit_code'] for r in records if r['process_exit_code'] is not None),[0])
        refused=next(r for r in records if r['process_exit_code'] is None)
        self.assertFalse(refused['material_complete']);self.assertEqual(refused['state'],'unknown')
        before=self.calls();self.unio('lead','revone');self.collect(code=2)
        self.assertEqual(self.calls(),before)
        self.assertTrue(all(r['process_exit_code'] is None for r in self.attempts()))
        self.assertFalse(json.loads(self.unio('policy','--json').stdout)['active_native_workflows'])

    def test_shared_lead_requires_exact_owner_review_consent(self):
        self.unio('tier','high')
        self.unio('account','revone','shared');self.unio('account','revtwo','shared')
        self.unio('lead','revone')
        before=self.calls();self.collect(code=2)
        self.assertEqual(self.calls(),before)
        self.assertTrue(all(r['process_exit_code'] is None for r in self.attempts()))
        for reviewer in ('revone','revtwo'):
            self.unio('lead-budget','grant',reviewer,reviewer,'evidence','review')
        # Earlier proven pre-provider refusals stay visible without vetoing
        # a completed current collection. They never supply expected reviewers.
        refused_bytes={p:p.read_bytes() for p in self.receipts()}
        self.collect()
        observed=self.summary(expect='revone,revtwo')
        self.assertEqual(observed['counts']['unknown'],2)
        self.assertEqual(observed['counts']['approved'],2)
        for path,raw in refused_bytes.items():self.assertEqual(path.read_bytes(),raw)
        self.assertTrue(all(r['process_exit_code']==0 and r['state']=='approved'
                            for r in self.attempts()))
        history=json.loads((self.coord/'lead-budget.json').read_text())['grants']
        self.assertEqual([g['state'] for g in history],['used','used'])
        before=self.calls();self.collect(code=2)
        self.assertEqual(self.calls(),before)
        # A single-review path uses the same owner task binding.
        self.unio('lead-budget','grant','revone','revone','evidence','review')
        self.unio('review','mock','evidence','revone')
        before=self.calls();self.unio('review','mock','evidence','revone',code=2)
        self.assertEqual(self.calls(),before)

    def test_mixed_process_verdict_timeout_and_child_failure(self):
        self.controls(revone='changes',revtwo='fail');self.collect(code=1)
        self.assertEqual({(r['state'],r['process_exit_code']) for r in self.attempts()},
                         {('changes_requested',0),('failed',7)})
        self.controls(revone='unknown',revtwo='timeout')
        env=dict(self.env,UNIO_REVIEW_TIMEOUT='1');self.collect(code=1,env=env)
        self.assertEqual({(r['state'],r['process_exit_code']) for r in self.attempts()},
                         {('unknown',0),('failed',124)})
        self.controls(revone='break_child',revtwo='approve');self.collect(code=1)
        self.assertEqual(self.manifest()['state'],'unknown')
        self.assertIn('child_failed',self.manifest()['reasons'])
        self.assertIsNone(self.manifest()['attempts'][0]['receipt_id'])

    def test_drift_material_mutation_and_failed_observation(self):
        wt=self.root/'project/wt/mock'
        self.controls(revone='drift');self.collect(code=2)
        self.assertTrue(all(r['state']=='approved' and r['process_exit_code']==0 for r in self.attempts()))
        self.assertNotEqual(self.manifest()['before'],self.manifest()['after'])
        self.call(['git','restore','hello.txt'],cwd=wt)
        self.controls(revone='material');self.collect(code=2)
        mutated=next(r for r in self.attempts() if r['reviewer']=='revone')
        other=next(r for r in self.attempts() if r['reviewer']=='revtwo')
        self.assertEqual(mutated['process_exit_code'],0)
        self.assertFalse(mutated['material_complete']);self.assertIn('material_changed',mutated['reasons'])
        self.assertEqual(other['state'],'approved')
        self.controls(revone='snapshot_fail');self.collect(code=2)
        self.assertEqual(self.manifest()['state'],'unknown');self.assertIsNone(self.manifest()['after'])
        self.assertTrue(all(r['after'] is None and r['process_exit_code']==0 for r in self.attempts()))
        (wt/'unsupported').unlink();self.summary(code=2,expect='revone,revtwo')

    def test_parent_term_reaps_owned_provider_trees_and_slots(self):
        self.controls(revone='hold',revtwo='hold');p=self.start()
        self.until(lambda:len(list(self.root.glob('*.started')))==2)
        with (self.coord/'.locks/mock.lock').open('a') as lock:
            with self.assertRaises(BlockingIOError):fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        seen=[json.loads(f.read_text()) for f in self.root.glob('*.started')]
        p.send_signal(signal.SIGTERM);stdout,stderr=p.communicate(timeout=25)
        self.assertEqual(p.returncode,143,(stdout,stderr))
        self.assertEqual(self.manifest()['state'],'interrupted')
        self.assertTrue(all(a['receipt_id'] is None for a in self.manifest()['attempts']))
        self.assertFalse(json.loads(self.unio('policy','--json').stdout)['active_native_workflows'])
        for record in seen:
            for pid in (record['pid'],record['child_pid']):
                path=Path('/proc')/str(pid)/'stat'
                self.assertTrue(not path.exists() or path.read_text().rsplit(') ',1)[1].startswith('Z '),str(pid))
        with (self.coord/'.locks/mock.lock').open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)

if __name__=='__main__':unittest.main(verbosity=2)
