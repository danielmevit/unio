#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline installed review histories, corruption and local summary checks."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
PROVIDER='''import json,os,pathlib,sys,time
root=pathlib.Path(sys.argv[1]); name=sys.argv[2]
with (root/'calls').open('a') as out: out.write(name+'\\n')
action=json.loads((root/'control.json').read_text()).get(name,'approve')
if action=='timeout': time.sleep(10)
if action=='drift': (root/'project/wt/mock/hello.txt').write_text('changed during review')
if action=='snapshot_fail': os.mkfifo(root/'project/wt/mock/unsupported')
if action=='material': pathlib.Path(os.environ['UNIO_ORIGINAL_TASKFILE']).write_text('changed common material')
print('PRIVATE_REVIEW_PROSE')
print('PRIVATE_REVIEW_ERROR',file=sys.stderr)
print('VERDICT: '+('REQUEST-CHANGES' if action=='changes' else 'APPROVE'))
raise SystemExit(7 if action=='fail' else 0)
'''

class ReviewReceipts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='review receipts install ')
        cls.addClassCleanup(cls.temp.cleanup)
        cls.install=Path(cls.temp.name)
        cls.env={k:v for k,v in os.environ.items() if not k.startswith(('UNIO_','PYTHON'))}
        cls.env.update(UNIO_BIN_DIR=str(cls.install/'bin'),UNIO_CONF_DIR=str(cls.install/'conf'),
            UNIO_COMPLETION_DIR=str(cls.install/'completion'),UNIO_AUTO_VERIFY='0',
            UNIO_AUTO_OFF='0',UNIO_AUTO_SYNC='0',UNIO_TIMEOUT='30',UNIO_REVIEW_TIMEOUT='15',
            UNIO_VERIFY_TIMEOUT='15',GIT_AUTHOR_NAME='mock',GIT_AUTHOR_EMAIL='mock@test.invalid',
            GIT_COMMITTER_NAME='mock',GIT_COMMITTER_EMAIL='mock@test.invalid',PYTHONDONTWRITEBYTECODE='1')
        copy=cls.install/'copied standalone installer.sh'
        copy.write_bytes((ROOT/'unio-install.sh').read_bytes())
        p=subprocess.run(['bash',str(copy)],cwd=cls.install,env=cls.env,capture_output=True,text=True,timeout=90)
        assert p.returncode==0,p.stderr
        cls.engine=str(cls.install/'bin/unio')

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='review project β ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.repo=self.root/'project/repo';self.repo.mkdir(parents=True)
        self.env=dict(self.__class__.env)
        self.env['UNIO_CONF_DIR']=str(self.root/'conf')
        conf=self.root/'conf';conf.mkdir()
        shutil.copytree(self.install/'conf/templates',conf/'templates')
        provider=self.root/'provider.py';provider.write_text(PROVIDER)
        lines=["mock=bash -c 'printf work > hello.txt; git add hello.txt; git commit -qm work'"]
        for name in ('revone','revtwo'):
            lines.append(name+'='+shlex.join(['python3',str(provider),str(self.root),name]))
        (conf/'agents.conf').write_text('\n'.join(lines)+'\n')
        self.control={};self.controls()
        self.call(['git','init','-q','-b','dev'])
        self.call(['git','commit','--allow-empty','-qm','initial'])
        self.unio('init','mock')
        self.coord=self.root/'project/coord'
        self.task=self.coord/'tasks/evidence.md'
        self.task.write_text('# Task\n## Allowed scope\n- hello.txt\n## Validate\n$ test -s hello.txt\n')
        self.unio('run','mock','evidence');self.unio('verify','mock','evidence')

    def call(self,args,code=0,env=None,cwd=None):
        p=subprocess.run(args,cwd=cwd or self.repo,env=env or self.env,capture_output=True,text=True,timeout=90)
        self.assertEqual(p.returncode,code,(args,p.stdout[-3000:],p.stderr[-2000:]))
        return p

    def unio(self,*args,code=0,env=None,cwd=None):
        return self.call([self.engine,*args],code,env,cwd)

    def controls(self,**changes):
        self.control.update(changes)
        (self.root/'control.json').write_text(json.dumps(self.control))

    def calls(self):
        p=self.root/'calls'
        return p.read_bytes() if p.exists() else b''

    def summary(self,code=0,expect='revone',env=None):
        before=self.calls()
        p=self.unio('reviews','mock','evidence','--expect',expect,'--json',code=code,env=env)
        d=json.loads(p.stdout)
        self.assertEqual(before,self.calls(),'summary made provider call')
        self.assertFalse(d['human_acceptance'])
        self.assertNotIn('PRIVATE_REVIEW',p.stdout)
        return d

    def receipts(self):
        return sorted((self.coord/'reports').glob('evidence.review.*/receipt.json'))

    def test_approvals_expectations_duplicates_and_current_changes(self):
        self.assertEqual(self.summary(code=2)['decision'],'not_run')
        self.unio('review','mock','evidence','revone')
        first=self.receipts()[0];original=first.read_bytes()
        self.assertEqual(self.summary(code=2,expect='revone,revtwo')['missing_reviewers'],['revtwo'])
        self.unio('review','mock','evidence','revtwo')
        d=self.summary(expect='revone,revtwo,revone')
        self.assertEqual(d['decision'],'all_recorded_approved')
        self.assertEqual(d['distinct_reviewers'],['revone','revtwo'])
        self.controls(revone='changes');self.unio('review','mock','evidence','revone',code=1)
        self.controls(revone='approve');self.unio('review','mock','evidence','revone')
        self.controls(revtwo='fail');self.unio('review','mock','evidence','revtwo',code=1)
        d=self.summary(code=1,expect='revone,revtwo,missing')
        self.assertEqual(d['decision'],'changes_requested');self.assertTrue(d['incomplete'])
        self.assertEqual(d['counts']['changes_requested'],1)
        self.assertEqual(d['counts']['failed'],1)
        self.assertEqual(first.read_bytes(),original)
        self.assertEqual(len(self.receipts()),5)

    def test_strict_receipts_and_log_bounds_never_inherit_approval(self):
        self.unio('review','mock','evidence','revone')
        path=self.receipts()[0];original=path.read_bytes();d=json.loads(original)
        cases=[b'\xff',b' '*65537,
            json.dumps(dict(d,unexpected=True)).encode(),
            json.dumps(dict(d,schema_version=True)).encode(),
            json.dumps(dict(d,process_exit_code=True)).encode(),
            json.dumps(dict(d,stdout=dict(sha256=d['stdout']['sha256'],bytes=-1))).encode(),
            original.rstrip()[:-1]+b',"schema_version":1}',
            original.rstrip()[:-1]+b',"unknown":NaN}',
            b'['*1500+b']'*1500]
        for raw in cases:
            with self.subTest(raw_length=len(raw)):
                path.write_bytes(raw)
                self.assertEqual(self.summary(code=2)['decision'],'incomplete')
        path.write_bytes(original)
        stream=path.parent/'stdout.log';saved=stream.read_bytes()
        for kind in ('changed','missing','symlink','fifo','oversized'):
            with self.subTest(stream=kind):
                stream.unlink()
                if kind=='changed':stream.write_bytes(saved+b'tampered')
                if kind=='symlink':stream.symlink_to(self.root/'control.json')
                if kind=='fifo':os.mkfifo(stream)
                if kind=='oversized':
                    with stream.open('wb') as out:out.truncate(16*1024*1024+1)
                self.assertEqual(self.summary(code=2)['decision'],'incomplete')
                if stream.exists() or stream.is_symlink():stream.unlink()
                stream.write_bytes(saved)
        path.unlink();path.symlink_to(self.root/'control.json')
        self.assertEqual(self.summary(code=2)['decision'],'incomplete')

    def test_budget_refusal_and_timeout_keep_actual_evidence(self):
        self.unio('lead','revone')
        self.unio('review','mock','evidence','revone',code=2)
        self.assertEqual(self.calls(),b'')
        d=json.loads(self.receipts()[0].read_text())
        self.assertIsNone(d['process_exit_code']);self.assertFalse(d['material_complete'])
        self.assertEqual(d['reasons'],['budget_refused'])
        self.assertEqual(self.summary(code=2)['decision'],'incomplete')
        self.unio('lead','none');self.controls(revone='timeout')
        self.unio('review','mock','evidence','revone',code=1,env=dict(self.env,UNIO_REVIEW_TIMEOUT='1'))
        codes=[json.loads(p.read_text())['process_exit_code'] for p in self.receipts()]
        self.assertIn(124,codes)

    def test_stale_history_and_mid_review_drift(self):
        self.unio('review','mock','evidence','revone')
        self.task.write_text(self.task.read_text()+'\nNew owner instructions.\n')
        self.assertEqual(self.summary(code=2)['counts']['stale'],1)
        self.unio('verify','mock','evidence')
        self.unio('review','mock','evidence','revone')
        self.assertEqual(self.summary()['counts']['stale'],1)
        self.controls(revone='drift');self.unio('review','mock','evidence','revone',code=2)
        records=[json.loads(p.read_text()) for p in self.receipts()]
        drift=[d for d in records if d['before']!=d['after']]
        self.assertEqual(len(drift),1);self.assertEqual(drift[0]['state'],'approved')
        self.assertEqual(self.summary(code=2)['decision'],'incomplete')

    def test_stop_busy_and_legacy_are_read_only(self):
        self.unio('review','mock','evidence','revone');self.unio('stop')
        def hashes():
            return {str(p.relative_to(self.coord)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.coord.rglob('*') if p.is_file()}
        before=hashes();self.summary();self.assertEqual(hashes(),before)
        with (self.coord/'.locks/mock.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.assertEqual(self.summary(code=2)['decision'],'incomplete')
        legacy=self.coord/'reports/evidence.review.Legacy00';legacy.mkdir()
        (legacy/'stdout.log').write_text('VERDICT: APPROVE\n')
        self.assertEqual(self.summary(code=2)['counts']['unresolved'],1)

    def test_failed_snapshot_keeps_uncertainty_after_worker_recovery(self):
        self.unio('review','mock','evidence','revone')
        self.controls(revone='snapshot_fail')
        self.unio('review','mock','evidence','revone',code=2)
        records=[json.loads(p.read_text()) for p in self.receipts()]
        uncertain=[d for d in records if d['after'] is None]
        self.assertEqual(len(uncertain),1)
        self.assertEqual(uncertain[0]['process_exit_code'],0)
        (self.root/'project/wt/mock/unsupported').unlink()
        self.assertEqual(self.summary(code=2)['decision'],'incomplete')

    def test_material_hash_is_captured_before_reviewer_invocation(self):
        self.controls(revone='material')
        self.unio('review','mock','evidence','revone',code=2)
        d=json.loads(self.receipts()[0].read_text())
        self.assertEqual(d['process_exit_code'],0)
        self.assertEqual(d['state'],'unknown');self.assertFalse(d['material_complete'])
        self.assertIn('material_changed',d['reasons'])
        self.assertEqual(self.summary(code=2)['decision'],'incomplete')

    def test_duplicate_receipt_identity_is_unresolved(self):
        self.unio('review','mock','evidence','revone')
        receipt=self.receipts()[0]
        shutil.copytree(receipt.parent,self.coord/'reports/evidence.review.Copy0000')
        self.assertEqual(self.summary(code=2)['counts']['unresolved'],1)

    def test_installed_help_completion_and_invalid_args(self):
        p=self.unio('reviews','--help',cwd=self.install)
        self.assertIn('--expect',p.stdout)
        completion=(self.install/'completion/unio').read_text()
        self.assertIn('reviews)',completion)
        for args in [[],['mock'],['mock','evidence','--expect',''],
                     ['mock','evidence','--expect','bad alias'],
                     ['mock','evidence','--json','--json'],
                     ['mock','evidence','--expect','revone','--expect','revtwo'],
                     ['mock','evidence','--invalid']]:
            self.unio('reviews',*args,code=2,cwd=self.install)

if __name__=='__main__': unittest.main(verbosity=2)
