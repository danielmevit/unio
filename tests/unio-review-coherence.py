#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline canonical result/handoff observation, using installed real Git fixtures."""
import fcntl
import hashlib
import shlex
import importlib.util
import json
import os
import types
import copy
import shutil
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('findings_fixture',Path(__file__).with_name('unio-review-findings.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

class Coherence(unittest.TestCase):
    setUpClass=classmethod(f.ReviewFindings.setUpClass.__func__)
    def setUp(self):
        f.fixture.ReviewReceipts.setUp(self)
        (self.root/'provider.py').write_text(f.PROVIDER)
    call=f.ReviewFindings.call
    unio=f.ReviewFindings.unio
    controls=f.ReviewFindings.controls
    calls=f.ReviewFindings.calls
    receipts=f.ReviewFindings.receipts
    def result(self):
        calls=self.calls()
        stored=self.coord/'results/mock/evidence.json'
        before=stored.read_bytes()
        d=json.loads(self.unio('result','mock','evidence').stdout)
        self.assertEqual(before,stored.read_bytes())
        self.assertEqual(calls,self.calls())
        self.assertEqual(d['human'],{'state':'pending'})
        self.assertEqual(d['integration'],{'state':'not_attempted'})
        self.assertEqual(d['review_current']['ai_lab_independence'],'unknown')
        return d

    def unavailable_review_env(self):
        # Deterministic unavailable/expensive-work sentinel: do not depend on
        # wall-clock speed. Every forbidden attempt is persisted before refusal.
        hooks=self.root/'observation-hooks';hooks.mkdir()
        attempted=self.root/'review-material-attempts'
        (hooks/'sitecustomize.py').write_text("""import pathlib,sys
marker=pathlib.Path(%r)
def trace(frame,event,arg):
    if event=='call' and (frame.f_code.co_name=='material_body'
            or (frame.f_code.co_name=='review_config_data'
                and frame.f_back.f_code.co_name in ('reviews','observe_material'))
            or (frame.f_code.co_name=='snapshot' and frame.f_back.f_code.co_name=='reviews')):
        with marker.open('a') as stream:stream.write(frame.f_code.co_name+'\\n')
        raise OSError('controlled unavailable review material')
    return trace
if len(sys.argv)>1 and sys.argv[1]=='result':sys.settrace(trace)
""" % str(attempted))
        return dict(self.env,PYTHONPATH=str(hooks)),attempted

    def test_unreviewed_observation_skips_unusable_review_material(self):
        env,attempted=self.unavailable_review_env()
        stored=self.coord/'results/mock/evidence.json'
        original=stored.read_bytes();before=self.result();calls=self.calls()
        reports=self.coord/'reports'
        for kind in ('no_folders','unbound','malformed_receipt','malformed_collection'):
            if kind=='unbound':
                orphan=reports/'evidence.review.Orphan01';orphan.mkdir()
                (orphan/'stdout.log').write_bytes(b'raw history\x00\xff')
            elif kind=='malformed_receipt':
                bad=reports/'evidence.review.Broken01';bad.mkdir()
                (bad/'receipt.json').write_bytes(b'{')
            elif kind=='malformed_collection':
                bad=reports/'evidence.review-set.Broken01';bad.mkdir()
                (bad/'collection.json').write_bytes(b'{')
            raw={p:p.read_bytes() for p in reports.rglob('*') if p.is_file()}
            with self.subTest(kind=kind):
                d=json.loads(self.unio('result','mock','evidence',env=env).stdout)
                self.assertFalse(attempted.exists(),attempted.read_text() if attempted.exists() else '')
                self.assertFalse(d['ready_for_human_review'])
                self.assertFalse(d['review_current']['machine_review_ready'])
                self.assertEqual(d['review_current']['current_revision'],d['current_revision'])
                for key in ('process','validation','delivery','human','integration','dispatch_revision'):
                    self.assertEqual(d.get(key),before.get(key),key)
                self.assertEqual(stored.read_bytes(),original)
                self.assertEqual({p:p.read_bytes() for p in raw},raw)
                self.assertEqual(self.calls(),calls)
                if kind!='no_folders':
                    self.assertTrue(any('unbound_legacy_evidence' in row['reasons']
                                        for row in d['review_current']['evidence']))
                if kind in ('malformed_receipt','malformed_collection'):
                    self.assertEqual(d['review_current']['counts']['unresolved'],1)
                if kind=='malformed_collection':
                    self.assertIn('invalid_collection_evidence',d['review_current']['reasons'])

        with (self.coord/'.locks/mock.lock').open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            d=json.loads(self.unio('result','mock','evidence',env=env).stdout)
            self.assertIn('worker_busy',d['review_current']['reasons'])
            self.assertFalse(d['ready_for_human_review'])
            self.assertFalse(attempted.exists())

    def test_reviewed_material_is_fresh_on_every_observation(self):
        self.controls(revone='empty');self.unio('review','mock','evidence','revone')
        self.assertTrue(self.result()['ready_for_human_review'])
        env,attempted=self.unavailable_review_env()
        for observation in range(2):
            with self.subTest(observation=observation):
                if attempted.exists():attempted.unlink()
                d=json.loads(self.unio('result','mock','evidence',env=env).stdout)
                self.assertTrue(attempted.exists())
                self.assertIn('current_evidence_unavailable',d['review_current']['reasons'])
                self.assertFalse(d['ready_for_human_review'])
                self.assertEqual(d['review_current']['counts']['current'],0)
                self.assertEqual(d['process']['exit_code'],0)
        self.assertTrue(self.result()['ready_for_human_review'])

    def test_unreviewed_source_and_delivery_outcomes_with_unavailable_material(self):
        env,attempted=self.unavailable_review_env()
        conf=self.root/'conf/agents.conf';saved=conf.read_text()
        for name,exit_code,writes,state in (('complete',0,True,'complete'),
                ('incomplete',0,False,'incomplete'),('failed',7,True,'incomplete')):
            task='unreviewed-'+name
            (self.coord/'tasks'/(task+'.md')).write_text(
                '# Task\n## Allowed scope\n- hello.txt\n## Required artifacts\nreport.txt\n## Validate\n$ true\n')
            command=('printf artifact > "$UNIO_DELIVERY_DIR/report.txt"; ' if writes else '')
            command+='exit '+str(exit_code)
            conf.write_text('mock='+shlex.join(['bash','-c',command])+'\n'+
                            '\n'.join(saved.splitlines()[1:])+'\n')
            self.unio('run','mock',task,code=exit_code)
            before=json.loads(self.unio('result','mock',task).stdout)
            calls=self.calls();stored=self.coord/'results/mock'/(task+'.json');raw=stored.read_bytes()
            with self.subTest(outcome=name):
                d=json.loads(self.unio('result','mock',task,env=env).stdout)
                self.assertFalse(attempted.exists())
                self.assertEqual(d['process']['exit_code'],exit_code)
                self.assertEqual(d['process']['state'],'failed' if exit_code else 'succeeded')
                self.assertEqual(d['delivery']['state'],state)
                for key in ('process','validation','delivery','delivery_current','dispatch_revision','human','integration'):
                    self.assertEqual(d.get(key),before.get(key),key)
                self.assertFalse(d['ready_for_human_review'])
                self.assertFalse(d['review_current']['machine_review_ready'])
                self.assertEqual(d['human'],{'state':'pending'})
                self.assertEqual(d['current_revision'],d['review_current']['current_revision'])
                self.assertEqual(stored.read_bytes(),raw);self.assertEqual(self.calls(),calls)
        conf.write_text(saved)

    def test_collection_result_handoff_and_missing_format(self):
        self.controls(revone='empty',revtwo='empty')
        self.unio('review-set','mock','evidence','revone','revtwo')
        d=self.result();p=d['review_current']
        self.assertEqual(p['verdict_decision'],'all_recorded_approved')
        self.assertEqual(p['counts']['current'],2)
        summary=json.loads(self.unio('reviews','mock','evidence','--json').stdout)
        self.assertEqual(summary['decision'],p['verdict_decision'])
        self.assertEqual(summary['extraction_complete'],p['extraction_complete'])
        self.assertEqual(summary['machine_review_ready'],p['machine_review_ready'])
        self.assertEqual(summary['entries'],p['evidence'])
        self.assertEqual(p['expected_reviewers'],['revone','revtwo'])
        self.assertTrue(p['extraction_complete']);self.assertTrue(d['ready_for_human_review'],d)
        self.assertEqual(d['review']['state'],'not_run')
        packet=Path(self.unio('handoff','mock','evidence').stdout.strip())
        self.assertEqual(json.loads((packet/'result.json').read_text())['review_current'],p)
        self.assertIn('Current recorded review: all_recorded_approved',(packet/'HANDOFF.md').read_text())
        self.controls(revone='missing')
        self.unio('review','mock','evidence','revone')
        d=self.result();self.assertEqual(d['review_current']['verdict_decision'],'all_recorded_approved')
        self.assertFalse(d['review_current']['extraction_complete'])
        self.assertFalse(d['ready_for_human_review'])

    def test_preserve_changes_failure_and_corrupt_evidence(self):
        self.controls(revone='changes');self.unio('review','mock','evidence','revone',code=1)
        raw={p:p.read_bytes() for p in self.receipts()}
        self.controls(revone='empty',revtwo='empty')
        self.unio('review-set','mock','evidence','revone','revtwo',code=1)
        d=self.result();self.assertEqual(d['review_current']['verdict_decision'],'changes_requested')
        self.assertFalse(d['ready_for_human_review'])
        for p,b in raw.items():self.assertEqual(p.read_bytes(),b)
        self.controls(revtwo='fail');self.unio('review','mock','evidence','revtwo',code=1)
        self.assertEqual(self.result()['review_current']['counts']['failed'],1)
        self.receipts()[-1].write_text('{')
        self.assertGreater(self.result()['review_current']['counts']['unresolved'],0)

    def test_busy_and_drift_fail_closed(self):
        self.controls(revone='empty');self.unio('review','mock','evidence','revone')
        d=self.result();self.assertTrue(d['ready_for_human_review'],d)
        with (self.coord/'.locks/mock.lock').open('r') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            d=self.result();self.assertFalse(d['ready_for_human_review'])
            self.assertIn('worker_busy',d['review_current']['reasons'])
        wt=self.root/'project/wt/mock'
        for path in (wt/'hello.txt',self.task,self.root/'conf/agents.conf'):
            original=path.read_bytes();path.write_bytes(original+b'\n')
            d=self.result();self.assertFalse(d['ready_for_human_review'])
            self.assertEqual(d['review_current']['counts']['current'],0)
            path.write_bytes(original)
        (wt/'hello.txt').write_bytes(b'x'*300001)
        self.call(['git','add','hello.txt'],cwd=wt);self.call(['git','commit','-qm','oversized'],cwd=wt)
        self.assertFalse(self.result()['ready_for_human_review'])

    def test_legacy_and_report_only_provenance(self):
        self.controls(revone='empty');self.unio('review','mock','evidence','revone')
        receipt=self.receipts()[0]
        base=json.loads(receipt.read_text())
        body=f.ReviewFindings.legacy_body(self,base['before'])
        legacy=dict(base,schema_version=1,material_sha256=hashlib.sha256(body+
            b'\nEnd with exactly one standalone line: VERDICT: APPROVE or VERDICT: REQUEST-CHANGES\n').hexdigest())
        del legacy['material_protocol']
        # A synthetic legacy receipt deliberately lacks the new context sidecar.
        f.ReviewFindings.synthetic(self,legacy,'Legacy01',b'VERDICT: APPROVE\n')
        d=self.result();self.assertEqual(d['review_current']['counts']['current'],2)
        self.assertFalse(d['review_current']['extraction_complete'])
        self.assertFalse(d['ready_for_human_review'])
        conf=self.root/'conf/agents.conf'
        lines=conf.read_text().splitlines()
        lines[0]='mock='+shlex.join(['bash','-c','printf "offline report\\n"'])
        conf.write_text('\n'.join(lines)+'\n')
        self.task.write_text('# Task\n## Outcome\nreport-only\n## Allowed scope\n- report.txt\n## Validate\n$ true\n')
        self.unio('run','mock','evidence');self.unio('verify','mock','evidence')
        self.unio('review-set','mock','evidence','revone','revtwo')
        d=self.result();self.assertEqual(d['outcome_current']['state'],'current')
        self.assertTrue(d['ready_for_human_review'],d)
        packet=Path(self.unio('handoff','mock','evidence').stdout.strip())
        self.assertIn('offline report',(packet/'report.md').read_text())
        report=self.coord/'results/mock/evidence.outcomes'/d['outcome']['run_id']/'report.txt'
        report.chmod(0o600);report.write_text('tampered')
        d=self.result();self.assertFalse(d['ready_for_human_review'])
        self.assertEqual(d['outcome_current']['state'],'invalid')

    def test_base_drift_and_collection_contract_corruption(self):
        self.controls(revone='empty',revtwo='empty')
        self.unio('review-set','mock','evidence','revone','revtwo')
        self.call(['git','commit','--allow-empty','-qm','advance base'])
        d=self.result();self.assertEqual(d['review_current']['counts']['stale'],2)
        self.assertFalse(d['ready_for_human_review'])
        self.call(['git','reset','--hard','HEAD~1'])
        task=self.task.read_bytes()
        race=json.loads(self.unio('reviews','mock','evidence','--expect','revone,revtwo','--json',
            code=2,env=f.ReviewFindings.hook_env(self,'collection')).stdout)
        self.assertIn('revision_changed',race['reasons'])
        self.assertEqual(race['counts']['current'],0)
        self.task.write_bytes(task)
        manifest=next((self.coord/'reports').glob('evidence.review-set.*/collection.json'))
        manifest.write_text('{')
        d=self.result();self.assertIn('invalid_collection_evidence',d['review_current']['reasons'])
        self.assertFalse(d['ready_for_human_review'])
        summary=json.loads(self.unio('reviews','mock','evidence','--expect','revone,revtwo','--json',code=2).stdout)
        self.assertIn('invalid_collection_evidence',summary['reasons'])

class IntegrationCorrections(Coherence):
    def execution_module(self):
        spec=importlib.util.spec_from_file_location('config_execution',Path(__file__).resolve().parents[1]/'bridge/execution_service.py')
        execution=importlib.util.module_from_spec(spec);spec.loader.exec_module(execution)
        return execution

    def test_native_reviewer_grammar_installed_results(self):
        execution=self.execution_module()
        aliases=('Opus','2nd','_x','R'+'x'*127)
        conf=self.root/'conf/agents.conf'
        with conf.open('a') as stream:
            for alias in aliases:
                stream.write(alias+'='+shlex.join(['python3',str(self.root/'provider.py'),str(self.root),alias])+'\n')
        self.controls(**dict.fromkeys(aliases,'empty'))
        self.unio('review','mock','evidence',aliases[0])
        d=self.result()
        self.assertEqual(d['review']['reviewer'],'Opus')
        self.assertTrue(execution._native_document(d,'mock','evidence')['ready_for_human_review'])
        self.unio('review-set','mock','evidence',*aliases)
        d=self.result();self.assertTrue(d['ready_for_human_review'])
        self.assertEqual(set(d['review_current']['distinct_reviewers']),set(aliases))
        self.assertTrue(execution._native_document(d,'mock','evidence')['ready_for_human_review'])
        for bad in ('../Opus','-x','x/y','x'*129):
            for location in ('legacy','list','row'):
                forged=copy.deepcopy(d)
                if location=='legacy': forged['review']['reviewer']=bad
                elif location=='list': forged['review_current']['distinct_reviewers']=[bad]
                else: forged['review_current']['evidence'][0]['reviewer']=bad
                with self.subTest(bad=bad,location=location),self.assertRaises(ValueError):
                    execution._native_document(forged,'mock','evidence')

    def test_invalid_configuration_keeps_installed_source_observable(self):
        execution=self.execution_module()
        self.controls(revone='empty');self.unio('review','mock','evidence','revone')
        conf=self.root/'conf/agents.conf';saved=conf.read_bytes()
        hooks=self.root/'unstable-config-hooks';hooks.mkdir()
        (hooks/'sitecustomize.py').write_text("""import os,sys,types
original=os.stat
count=0
def unstable(path,*args,**kwargs):
    global count
    st=original(path,*args,**kwargs)
    if sys._getframe(1).f_code.co_name=='review_config_data':
        count+=1
        if count%2==0:
            values={k:getattr(st,k) for k in dir(st) if k.startswith('st_')}
            values['st_ino']+=1
            return types.SimpleNamespace(**values)
    return st
os.stat=unstable
""")
        try:
            for kind in ('utf8','missing','oversized','unstable'):
                conf.write_bytes(saved)
                env=self.env
                if kind=='utf8': conf.write_bytes(b'\xff')
                elif kind=='missing': conf.unlink()
                elif kind=='oversized': conf.write_bytes(b'#'+b'x'*1048576)
                else: env=dict(self.env,PYTHONPATH=str(hooks))
                with self.subTest(kind=kind):
                    d=json.loads(self.unio('result','mock','evidence',env=env).stdout)
                    self.assertEqual(d['process']['state'],'succeeded')
                    self.assertEqual(d['process']['exit_code'],0)
                    self.assertEqual(d['review_current']['current_revision'],d['current_revision'])
                    self.assertFalse(d['ready_for_human_review'])
                    self.assertIn('current_evidence_unavailable',d['review_current']['reasons'])
                    self.assertFalse(any(r['current'] for r in d['review_current']['evidence']))
                    self.assertFalse(execution._native_document(d,'mock','evidence')['ready_for_human_review'])
                    for mutate in (
                        lambda x:x['review_current'].update(current_revision=None),
                        lambda x:x['review_current']['current_revision'].update(task_sha256='0'*64),
                        lambda x:x.update(ready_for_human_review=True),
                        lambda x:x['review_current'].update(machine_review_ready=True),
                    ):
                        forged=copy.deepcopy(d);mutate(forged)
                        with self.assertRaises(ValueError):execution._native_document(forged,'mock','evidence')
        finally: conf.write_bytes(saved)
        self.assertTrue(self.result()['ready_for_human_review'])

    def test_unbound_history_is_visible_without_veto(self):
        orphan=self.coord/'reports/evidence.review.Orphan01';orphan.mkdir()
        (orphan/'stdout.log').write_text('interrupted historical stream')
        self.controls(revone='empty');self.unio('review','mock','evidence','revone')
        d=self.result();self.assertTrue(d['ready_for_human_review'])
        self.assertEqual(d['review_current']['counts']['unresolved'],0)
        self.assertTrue(any('unbound_legacy_evidence' in r['reasons'] for r in d['review_current']['evidence']))
        self.assertEqual((orphan/'stdout.log').read_text(),'interrupted historical stream')

    def test_effective_project_config(self):
        global_config=self.root/'conf/agents.conf'
        project=self.coord/'agents.conf';project.write_bytes(global_config.read_bytes())
        self.controls(revone='empty');self.unio('review','mock','evidence','revone')
        self.assertTrue(self.result()['ready_for_human_review'])
        original=project.read_bytes()
        global_config.write_bytes(global_config.read_bytes()+b'\n# inactive configuration\n')
        self.assertTrue(self.result()['ready_for_human_review'])
        project.write_text(project.read_text().replace('revone=','revone=printf changed; '))
        self.assertFalse(self.result()['ready_for_human_review'])
        project.write_bytes(original)
        self.assertTrue(self.result()['ready_for_human_review'])

    def test_context_command_binding_and_legacy_override_unknown(self):
        project=self.coord/'agents.conf';project.write_bytes((self.root/'conf/agents.conf').read_bytes())
        self.controls(revone='empty');self.unio('review','mock','evidence','revone')
        context=next((self.coord/'reports').glob('evidence.review.*/context.json'))
        original=json.loads(context.read_text())
        altered=dict(original,command_sha256='0'*64);context.write_text(json.dumps(altered))
        self.assertFalse(self.result()['ready_for_human_review'])
        context.write_text(json.dumps(dict(schema_version=1,config_sha256=original['config_sha256'])))
        d=self.result();self.assertFalse(d['ready_for_human_review'])
        self.assertIsNone(d['review_current']['evidence'][0]['config_current'])
        context.write_text(json.dumps(original));self.assertTrue(self.result()['ready_for_human_review'])

    def test_supported_config_links(self):
        path=self.root/'conf/agents.conf';target=path.with_name('original.conf');path.rename(target)
        self.controls(revone='empty',revtwo='empty')
        for kind in ('symlink','hardlink'):
            with self.subTest(kind=kind):
                if path.is_symlink() or path.exists():path.unlink()
                if kind=='symlink':path.symlink_to(target.name)
                else:os.link(target,path)
                self.unio('review','mock','evidence','revone')
                self.unio('review-set','mock','evidence','revone','revtwo')
                self.assertTrue(self.result()['ready_for_human_review'])
                path.unlink()

    def test_empty_conf_override_uses_default(self):
        home=self.root/'home';config=home/'.config/unio'
        shutil.copytree(self.root/'conf',config)
        env=dict(self.env,HOME=str(home),UNIO_CONF_DIR='')
        self.controls(revone='empty')
        self.unio('review','mock','evidence','revone',env=env)
        d=json.loads(self.unio('result','mock','evidence',env=env).stdout)
        self.assertTrue(d['ready_for_human_review'])

    def test_context_failure_cleans_only_owned_preparation(self):
        path=self.root/'conf/agents.conf'
        path.write_bytes(path.read_bytes()+b'#'+b'x'*1048576)
        orphan=self.coord/'reports/evidence.review.Orphan01';orphan.mkdir()
        (orphan/'stdout.log').write_text('preserved')
        before=self.calls();scratch=set(Path(os.environ['TMPDIR']).iterdir())
        for args in (('review','mock','evidence','revone'),('review-set','mock','evidence','revone','revtwo')):
            self.unio(*args,code=2)
            self.assertEqual(list((self.coord/'reports').glob('evidence.review.*')),[orphan])
            self.assertEqual(self.calls(),before)
            self.assertEqual(set(Path(os.environ['TMPDIR']).iterdir()),scratch)
        self.assertEqual((orphan/'stdout.log').read_text(),'preserved')

    def test_later_context_failure_removes_earlier_preparation(self):
        orphan=self.coord/'reports/evidence.review.Orphan01';orphan.mkdir()
        (orphan/'stdout.log').write_text('old evidence')
        hooks=self.root/'context-hooks';hooks.mkdir()
        (hooks/'sitecustomize.py').write_text("""import pathlib,sys
counter=pathlib.Path(%r)
def trace(frame,event,arg):
    if event=='call' and frame.f_code.co_name=='review_context':
        count=int(counter.read_text())+1 if counter.exists() else 1
        counter.write_text(str(count))
        if count==2:raise ValueError('injected later context read failure')
    return trace
if len(sys.argv)>1 and sys.argv[1]=='review-context':sys.settrace(trace)
""" % str(self.root/'context-count'))
        before=self.calls();scratch=set(Path(os.environ['TMPDIR']).iterdir())
        self.unio('review-set','mock','evidence','revone','revtwo',code=2,
                  env=dict(self.env,PYTHONPATH=str(hooks)))
        self.assertEqual((self.root/'context-count').read_text(),'2')
        self.assertEqual(self.calls(),before)
        self.assertEqual(list((self.coord/'reports').glob('evidence.review.*')),[orphan])
        self.assertEqual(set(Path(os.environ['TMPDIR']).iterdir()),scratch)
        self.assertEqual((orphan/'stdout.log').read_text(),'old evidence')

    def test_manual_no_source_projection_is_readable_but_never_ready(self):
        spec=importlib.util.spec_from_file_location('manual_execution',Path(__file__).resolve().parents[1]/'bridge/execution_service.py')
        execution=importlib.util.module_from_spec(spec);spec.loader.exec_module(execution)
        task='manual-no-source'
        (self.coord/'tasks'/(task+'.md')).write_text('# Manual check\n## Allowed scope\n- hello.txt\n## Validate\n$ test -s hello.txt\n')
        self.unio('verify','mock',task)
        d=json.loads(self.unio('result','mock',task).stdout)
        self.assertEqual(d['process']['state'],'not_run')
        self.assertNotIn('dispatch_revision',d)
        self.assertFalse(d['ready_for_human_review'])
        for projection in (True,False):
            observed=copy.deepcopy(d)
            if not projection:observed.pop('review_current')
            self.assertFalse(execution._native_document(observed,'mock',task)['ready_for_human_review'])
            observed['ready_for_human_review']=True
            with self.assertRaises(ValueError):execution._native_document(observed,'mock',task)
        forged=copy.deepcopy(d);forged['review_current']['counts']['current']=True
        with self.assertRaises(ValueError):execution._native_document(forged,'mock',task)

    def test_real_projection_parser_and_scheduler(self):
        spec=importlib.util.spec_from_file_location('integration_execution',Path(__file__).resolve().parents[1]/'bridge/execution_service.py')
        execution=importlib.util.module_from_spec(spec);spec.loader.exec_module(execution)
        spec=importlib.util.spec_from_file_location('integration_scheduler',Path(__file__).resolve().parents[1]/'tools/continuous-delegation.py')
        scheduler=importlib.util.module_from_spec(spec);spec.loader.exec_module(scheduler)
        self.controls(revone='empty',revtwo='empty')
        self.unio('review-set','mock','evidence','revone','revtwo')
        for reverify in (False,True):
            if reverify:self.unio('verify','mock','evidence')
            d=self.result();self.assertTrue(d['ready_for_human_review'])
            self.assertEqual(d['review']['state'],'not_run')
            self.assertTrue(execution._native_document(d,'mock','evidence')['ready_for_human_review'])
            runner=self.engine;raw=json.dumps(d).encode()
            client=types.SimpleNamespace(_engine=runner,_worker='mock',
                _call=lambda *a:(0,raw),_worker_revision=lambda:d['current_revision']['candidate_commit'])
            service_binding=dict(preview=dict(task_id='evidence',task_sha256=d['current_revision']['task_sha256'],reviewer='revone'),
                                 base_revision=d['current_revision']['base_commit'])
            self.assertTrue(execution.ExecutionService._native(client,service_binding)[0]['ready_for_human_review'])
            service_binding['preview']['reviewer']='absent'
            self.assertFalse(execution.ExecutionService._native(client,service_binding)[0]['ready_for_human_review'])
            binding=dict(worker='mock',task='evidence',task_sha256=d['current_revision']['task_sha256'],
                startup=dict(engine=runner,config=str(self.root/'conf')),fingerprints=dict(engine=hashlib.sha256(Path(runner).read_bytes()).hexdigest()))
            planner=types.SimpleNamespace(read_regular=lambda path,limit:(Path(path).read_bytes(),None),parse_strict_json=json.loads)
            store=types.SimpleNamespace(project=self.repo.parent)
            item=dict(attempted=True,source='unknown',launcher='started')
            dispatch=types.SimpleNamespace(load_service=lambda:execution)
            self.assertEqual(scheduler.observe_source(planner,dispatch,store,dict(bindings={'job':binding},base=d['current_revision']['base_commit']),dict(jobs={'job':item}),'job',runner,5),('succeeded',0))
            for mutate in (
                lambda x:x.update(review_current={'machine_review_ready':True}),
                lambda x:x['review_current'].update(evidence=[]),
                lambda x:x['review_current'].update(missing_reviewers=['revtwo']),
                lambda x:x['review_current']['current_revision'].update(task_sha256='0'*64),
                lambda x:x['review_current']['evidence'][0].update(config_current=False),
                lambda x:x['review_current']['evidence'][0].update(state='changes_requested'),
                lambda x:x.update(dispatch_revision=None),
                lambda x:x['review_current']['evidence'][0].update(findings_count=False),
                lambda x:x['review_current']['evidence'][0].pop('raw_directory'),
                lambda x:x['review_current'].update(material_protocols={}),
            ):
                forged=copy.deepcopy(d);mutate(forged)
                with self.assertRaises(ValueError):execution._native_document(forged,'mock','evidence')

        self.controls(revone='changes');self.unio('review','mock','evidence','revone',code=1)
        d=self.result();self.assertFalse(d['ready_for_human_review'])
        self.assertFalse(execution._native_document(d,'mock','evidence')['ready_for_human_review'])

if __name__=='__main__':unittest.main(verbosity=2)
