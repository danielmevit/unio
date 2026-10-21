#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline canonical result/handoff observation, using installed real Git fixtures."""
import fcntl
import importlib.util
import json
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('findings_fixture',Path(__file__).with_name('unio-review-findings.py'))
f=importlib.util.module_from_spec(spec);spec.loader.exec_module(f)

class Coherence(unittest.TestCase):
    setUpClass=classmethod(f.ReviewFindings.setUpClass.__func__)
    setUp=f.ReviewFindings.setUp
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
        self.assertEqual(p['expected_reviewers'],['revone','revtwo'])
        self.assertTrue(p['extraction_complete']);self.assertTrue(d['ready_for_human_review'])
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
        self.assertTrue(self.result()['ready_for_human_review'])
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

if __name__=='__main__':unittest.main(verbosity=2)
