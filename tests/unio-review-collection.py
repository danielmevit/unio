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
if action in ('material','material_changes'):common.write_text('changed common material')
if action=='break_child':
    c=max((root/'project/coord/reports').glob('evidence.review-set.*/collection.json'),key=lambda p:p.stat().st_mtime_ns)
    a=next(a for a in json.loads(c.read_text())['attempts'] if a['reviewer']==name)
    (c.parent.parent/a['raw_directory']/'attempt.json').mkdir()
print('PRIVATE_COLLECTION_PROSE')
print('PRIVATE_COLLECTION_ERROR',file=sys.stderr)
print('VERDICT: '+('REQUEST-CHANGES' if action in ('changes','material_changes') else 'APPROVE'))
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
        self.assertIn('invoked=1/2 refused=1 invalid=0 dispatch_exit=2',stdout)
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
        granted=self.collect()
        self.assertIn('invoked=2/2 refused=0 invalid=0 dispatch_exit=0',granted.stdout)
        observed=self.summary(expect='revone,revtwo')
        self.assertEqual(observed['counts']['unknown'],2)
        self.assertEqual(observed['counts']['approved'],2)
        for path,raw in refused_bytes.items():self.assertEqual(path.read_bytes(),raw)
        self.assertTrue(all(r['process_exit_code']==0 and r['state']=='approved'
                            for r in self.attempts()))
        history=json.loads((self.coord/'lead-budget.json').read_text())['grants']
        self.assertEqual([g['state'] for g in history],['used','used'])
        before=self.calls();replay=self.collect(code=2)
        self.assertEqual(self.calls(),before)
        self.assertIn('invoked=0/2 refused=2 invalid=0 dispatch_exit=2',replay.stdout)
        self.assertTrue(all(r['process_exit_code'] is None for r in self.attempts()))
        # Historical approvals remain honest/current despite this dispatch refusal.
        self.assertEqual(self.summary(expect='revone,revtwo')['counts']['approved'],2)
        # A single-review path uses the same owner task binding.
        self.unio('lead-budget','grant','revone','revone','evidence','review')
        self.unio('review','mock','evidence','revone')
        before=self.calls();self.unio('review','mock','evidence','revone',code=2)
        self.assertEqual(self.calls(),before)

    def test_mixed_process_verdict_timeout_and_child_failure(self):
        # Prior approvals cannot conceal an invoked process failure or verdict.
        self.collect()
        self.controls(revone='approve',revtwo='fail')
        failed=self.collect(code=2)
        self.assertIn('invoked=2/2 refused=0 invalid=0 dispatch_exit=2',failed.stdout)
        self.assertIn(('failed',7),{(r['state'],r['process_exit_code']) for r in self.attempts()})
        self.controls(revone='changes',revtwo='approve')
        changes=self.collect(code=1)
        self.assertIn('invoked=2/2 refused=0 invalid=0 dispatch_exit=1',changes.stdout)
        self.controls(revone='changes',revtwo='fail');self.collect(code=1)
        self.assertEqual({(r['state'],r['process_exit_code']) for r in self.attempts()},
                         {('changes_requested',0),('failed',7)})
        self.controls(revone='unknown',revtwo='timeout')
        env=dict(self.env,UNIO_REVIEW_TIMEOUT='1');self.collect(code=1,env=env)
        self.assertEqual({(r['state'],r['process_exit_code']) for r in self.attempts()},
                         {('unknown',0),('failed',124)})
        self.controls(revone='break_child',revtwo='approve');broken=self.collect(code=1)
        self.assertIn('invalid=1 dispatch_exit=2',broken.stdout)
        self.assertEqual(self.manifest()['state'],'unknown')
        self.assertIn('child_failed',self.manifest()['reasons'])
        self.assertIsNone(self.manifest()['attempts'][0]['receipt_id'])

    def fault_engine(self,old,new):
        # Faults are confined to a disposable installed script, never the source
        # installer, shared installed fixture or production environment switches.
        source=Path(self.__class__.engine).read_text()
        self.assertEqual(source.count(old),1)
        target=self.root/'fault-unio'
        target.write_text(source.replace(old,new));target.chmod(0o700)
        self.engine=str(target)

    def assert_slots_empty(self):
        self.assertFalse(json.loads(self.unio('policy','--json').stdout)['active_native_workflows'])

    def test_current_changes_survive_fully_refused_replay(self):
        self.controls(revone='changes');self.collect(code=1)
        originals={p:p.read_bytes() for p in self.receipts()}
        before=self.calls();self.unio('lead','revone');self.unio('lead','revtwo')
        # Both aliases share the reserved account, so every attempt is refused.
        self.unio('account','revone','beta')
        result=self.collect(code=1)
        self.assertIn('invoked=0/2 refused=2 invalid=0 dispatch_exit=2',result.stdout)
        self.assertEqual(self.calls(),before)
        for path,data in originals.items():self.assertEqual(path.read_bytes(),data)
        self.assert_slots_empty()

    def test_partial_admission_actual_changes(self):
        self.unio('account','revone','shared');self.unio('account','revtwo','shared')
        # Hold whichever reviewer wins admission, then emit a real change request.
        provider=self.root/'provider.py'
        provider.write_text(PROVIDER.replace("('changes','material_changes')", "('changes','material_changes','hold')"))
        self.controls(revone='hold',revtwo='hold');p=self.start()
        self.until(lambda:len(list(self.root.glob('*.started')))==1 and
            any('budget-refused' in f.read_text() for f in (self.coord/'reports').glob('rset-*.md')))
        (self.root/'release').touch();stdout,stderr=p.communicate(timeout=25)
        self.assertEqual(p.returncode,1,(stdout,stderr))
        self.assertIn('invoked=1/2 refused=1 invalid=0 dispatch_exit=2',stdout)
        self.assertEqual(len(self.calls().splitlines()),1)
        self.assertIn(('changes_requested',0),{(r['state'],r['process_exit_code']) for r in self.attempts()})
        self.assert_slots_empty()

    def test_invalid_child_without_current_change_request(self):
        self.controls(revone='break_child');result=self.collect(code=2)
        self.assertIn('invoked=1/2 refused=0 invalid=1 dispatch_exit=2',result.stdout)
        self.assertEqual(len(self.calls().splitlines()),2)
        self.assertIsNone(self.manifest()['attempts'][0]['receipt_id'])
        self.assert_slots_empty()

    def test_missing_child_without_current_change_request(self):
        self.fault_engine('rs_child_result() {', 'rs_child_result() {\n  return 0')
        result=self.collect(code=2)
        self.assertIn('invoked=0/2 refused=0 invalid=2 dispatch_exit=2',result.stdout)
        self.assertEqual(len(self.calls().splitlines()),2)
        self.assertTrue(all(a['receipt_id'] is None for a in self.manifest()['attempts']))
        self.assert_slots_empty()

    def test_process_failure_without_prior_history(self):
        self.controls(revone='fail');result=self.collect(code=2)
        self.assertIn('invoked=2/2 refused=0 invalid=0 dispatch_exit=2',result.stdout)
        records=self.attempts()
        self.assertIn(('failed',7),{(r['state'],r['process_exit_code']) for r in records})
        self.assertFalse(any(r['state']=='changes_requested' for r in records))
        self.assertEqual(len(self.calls().splitlines()),2)
        self.assert_slots_empty()

    def test_mismatched_child_without_current_change_request(self):
        self.fault_engine('rs_child_result() {',
            'rs_child_result() {\n  set -- "$1" wrongreviewer "${@:3}"')
        result=self.collect(code=2)
        self.assertIn('invoked=0/2 refused=0 invalid=2 dispatch_exit=2',result.stdout)
        self.assertEqual(len(self.calls().splitlines()),2)
        self.assertTrue(all(a['receipt_id'] is None for a in self.manifest()['attempts']))
        self.assert_slots_empty()

    def test_finalizer_failure_keeps_unknown_counters(self):
        self.fault_engine('quality() {', 'quality() {\n  [ "$1" != review-set-finalize ] || return 2')
        result=self.collect(code=2)
        self.assertIn('state=unknown invoked=unknown/2 refused=unknown invalid=unknown dispatch_exit=2',result.stdout)
        self.assertEqual(len(self.calls().splitlines()),2)
        self.assert_slots_empty()
        self.controls(revone='changes')
        self.unio('review','mock','evidence','revone',code=1)
        before=len(self.calls().splitlines());result=self.collect(code=1)
        self.assertIn('invoked=unknown/2 refused=unknown invalid=unknown dispatch_exit=2',result.stdout)
        self.assertEqual(len(self.calls().splitlines())-before,2)
        self.assert_slots_empty()

    def test_malformed_finalizer_output_keeps_unknown_counters(self):
        line='if out=$(quality review-set-finalize "$root" "$worker" "$task" "$cdir" "$state_arg" "$specs"); then'
        # Actual providers and receipts run normally; corrupt only the installed
        # helper's returned text at the CLI trust boundary, after finalization.
        cases=('ffffffffffffffffffffffffffffffff completed 2 1 0 2 0 0',
               '$cid running 2 1 0 2 0 0', '$cid completed 2 1 0 -1 0 0',
               '$cid completed 2 1 0 999999999999999999999999 0 0',
               '$cid completed 2 1 0 1 0 0', '$cid completed 3 1 0 2 0 0',
               '$cid completed 2 1 0 2 0 0 extra', '$cid unknown 0 1 0 2 0 0',
               '$cid completed 2 0 0 2 0 0', '$cid completed 2 1 0 2 0 0\nextra',
               '$cid completed 2 1 0 2 0', '$cid completed 2 yes 0 2 0 0',
               # Internally impossible: completed with invalid, change request
               # without a verified invocation or alongside invalid evidence.
               '$cid completed 2 0 2 0 0 2', '$cid unknown 0 0 1 0 2 0',
               '$cid completed 2 0 1 0 0 2', '$cid unknown 1 0 2 0 0 2')
        for output in cases:
            with self.subTest(output=output):
                self.fault_engine(line,line+'\n    out="'+output+'"')
                before=len(self.calls().splitlines());result=self.collect(code=2)
                self.assertIn('state=unknown invoked=unknown/2 refused=unknown invalid=unknown dispatch_exit=2',result.stdout)
                self.assertEqual(len(self.calls().splitlines())-before,2)
                self.assert_slots_empty()

    def test_admitted_stop_before_invocation_preserves_approvals(self):
        self.collect();before=self.calls()
        originals={p:p.read_bytes() for p in self.receipts()}
        marker='  # Recheck STOP immediately before this reviewer\'s provider starts.'
        self.fault_engine(marker, '''  # Disposable fixture barrier: both genuine admissions hold their slots.
  touch "$root/coord/admitted-$reviewer"
  for ((n=0; n<500; n++)); do
    [ -e "$root/coord/admitted-revone" ] && [ -e "$root/coord/admitted-revtwo" ] && break
    sleep .01
  done
  touch "$root/coord/STOP"
'''+marker)
        result=self.collect(code=2)
        self.assertIn('invoked=0/2 refused=2 invalid=0 dispatch_exit=2',result.stdout)
        self.assertEqual(self.calls(),before)
        records=self.attempts();self.assertEqual(len(records),2)
        for record in records:
            self.assertIsNone(record['process_exit_code'])
            self.assertIn('stop_active',record['reasons'])
        for attempt in self.manifest()['attempts']:
            data=json.loads((self.coord/'reports'/attempt['raw_directory']/'attempt.json').read_text())
            self.assertTrue(data['admitted']);self.assertFalse(data['invoked'])
        self.assertEqual(self.summary(code=2,expect='revone,revtwo')['counts']['approved'],2)
        for path,data in originals.items():self.assertEqual(path.read_bytes(),data)
        self.assert_slots_empty()
        # Admitted STOP rows stay conservative unknowns for this revision: a
        # later all-approving batch on the clean engine cannot erase them.
        stopped={p:p.read_bytes() for p in self.receipts()}
        self.engine=self.__class__.engine;self.unio('resume')
        result=self.collect(code=2)
        self.assertIn('invoked=2/2 refused=0 invalid=0 dispatch_exit=0',result.stdout)
        self.assertEqual(len(self.calls().splitlines())-len(before.splitlines()),2)
        self.assertTrue(all(r['state']=='approved' for r in self.attempts()))
        for path,data in stopped.items():self.assertEqual(path.read_bytes(),data)
        self.assert_slots_empty()

    def test_material_mutation_with_changes_is_not_a_dispatch_change_request(self):
        self.controls(revone='material_changes')
        result=self.collect(code=2)
        self.assertIn('dispatch_exit=2',result.stdout)
        mutated=next(r for r in self.attempts() if r['reviewer']=='revone')
        self.assertEqual(mutated['state'],'unknown');self.assertIn('material_changed',mutated['reasons'])
        self.assertIn('material_changed',self.manifest()['reasons'])
        self.assert_slots_empty()

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
