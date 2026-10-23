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
from unittest import mock
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
            runner='/mock/engine';raw=json.dumps(d).encode()
            binding=dict(worker='mock',task='evidence',task_sha256=d['current_revision']['task_sha256'],
                startup=dict(engine=runner,config='/mock/config'),fingerprints=dict(engine=hashlib.sha256(b'engine').hexdigest()))
            planner=types.SimpleNamespace(read_regular=lambda *a:(b'engine',None),parse_strict_json=json.loads)
            store=types.SimpleNamespace(project=self.repo)
            item=dict(attempted=True,source='unknown',launcher='started')
            with mock.patch.object(scheduler,'spawn',return_value=None),mock.patch.object(scheduler,'collect',return_value=(0,raw)):
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
            ):
                forged=copy.deepcopy(d);mutate(forged)
                with self.assertRaises(ValueError):execution._native_document(forged,'mock','evidence')

        self.controls(revone='changes');self.unio('review','mock','evidence','revone',code=1)
        d=self.result();self.assertFalse(d['ready_for_human_review'])
        self.assertFalse(execution._native_document(d,'mock','evidence')['ready_for_human_review'])

if __name__=='__main__':unittest.main(verbosity=2)
