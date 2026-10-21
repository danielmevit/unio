#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline canonical result/handoff observation, using installed real Git fixtures."""
import fcntl
import hashlib
import shlex
import importlib.util
import json
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

if __name__=='__main__':unittest.main(verbosity=2)
