#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed structured review findings. Tiny real Git, offline providers only."""
import fcntl
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import unittest

# Share only the existing installed real-Git fixture, not its test cases.
spec=importlib.util.spec_from_file_location('receipt_fixture',Path(__file__).with_name('unio-review-receipts.py'))
fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)

F1=dict(severity='high',path='hello.txt',line=2,summary='A concrete issue caf\u00e9',
        detail='Why it matters and the evidence')
F2=dict(severity='low',path=None,line=None,summary='General note',detail='Second distinct claim')
# Same claim with decomposed text and padding: identical after NFC + trim.
F1_NFD=dict(F1,summary='  A concrete issue cafe\u0301  ',
            detail='  Why it matters and the evidence  ')

def block(*findings):
    return json.dumps(dict(schema_version=1,findings=list(findings)))

BLOCKS={
    'empty':block(),
    'findings':block(F1,F2),
    'same':block(F1),
    'samenc':block(F1_NFD),
    'changes':block(F1),
    'fail':block(F1),
    'noverdict':block(F1),
    'twoblocks':[block(F1),block(F2)],
    'badjson':'{not json',
    'dupkeys':'{"schema_version":1,"schema_version":1,"findings":[]}',
    'nonfinite':'{"schema_version":1,"findings":[{"severity":"high","path":null,"line":null,"summary":"x","detail":NaN}]}',
    'unknownkey':'{"schema_version":1,"findings":[],"extra":1}',
    'badsev':block(dict(severity='blocker',path=None,line=None,summary='s',detail='d')),
    'booline':block(dict(severity='high',path=None,line=True,summary='s',detail='d')),
    'zeroline':block(dict(severity='high',path=None,line=0,summary='s',detail='d')),
    'bigline':block(dict(severity='high',path=None,line=1000001,summary='s',detail='d')),
    'abspath':block(dict(severity='high',path='/etc/passwd',line=None,summary='s',detail='d')),
    'traverse':block(dict(severity='high',path='../outside.txt',line=None,summary='s',detail='d')),
    'longpath':block(dict(severity='high',path='x'*513,line=None,summary='s',detail='d')),
    'bigsummary':block(dict(severity='high',path=None,line=None,summary='x'*1001,detail='d')),
    'bigdetail':block(dict(severity='high',path=None,line=None,summary='s',detail='x'*4001)),
    'ctrl':block(dict(severity='high',path=None,line=None,summary='bad\x1b[31m escape',detail='d')),
    'many':block(*[dict(F1,summary='finding %d'%i) for i in range(33)]),
    'bigblock':'x'*200000,
    'deepnest':'['*1500+']'*1500,
}

PROVIDER='''import hashlib,json,os,pathlib,sys
BLOCKS=json.loads(r"""%s""")
root=pathlib.Path(sys.argv[1]);name=sys.argv[2]
action=json.loads((root/'control.json').read_text()).get(name,'empty')
common=pathlib.Path(os.environ['UNIO_ORIGINAL_TASKFILE'])
with (root/'calls').open('a') as out:out.write(name+'\\\\n')
(root/(name+'.material')).write_text(json.dumps(dict(sha256=hashlib.sha256(common.read_bytes()).hexdigest())))
print('PRIVATE_FINDINGS_PROSE')
if action=='nonutf8':
    print('```unio-findings-v1')
    sys.stdout.buffer.write(b'\\xff\\xfe not utf8\\n')
    print('```')
else:
    content=BLOCKS.get(action)
    if content is not None:
        for text in (content if isinstance(content,list) else [content]):
            print('```unio-findings-v1')
            print(text)
            print('```')
if action!='noverdict':
    print('VERDICT: '+('REQUEST-CHANGES' if action=='changes' else 'APPROVE'))
raise SystemExit(7 if action=='fail' else 0)
''' % json.dumps(BLOCKS)

class ReviewFindings(unittest.TestCase):
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
        lines=["mock=bash -c 'printf work > hello.txt; git add hello.txt; git commit -qm work'"]
        for name in ('revone','revtwo','revthree','revfour'):
            lines.append(name+'='+shlex.join(['python3',str(self.root/'provider.py'),str(self.root),name]))
        (self.root/'conf/agents.conf').write_text('\n'.join(lines)+'\n')

    def findings(self,code=0,expect='revone,revtwo'):
        before=self.calls()
        arguments=['reviews','mock','evidence']
        if expect is not None: arguments+=['--expect',expect]
        p=self.unio(*arguments,'--findings','--json',code=code)
        self.assertEqual(before,self.calls(),'findings view made provider call')
        d=json.loads(p.stdout)
        self.assertFalse(d['human_acceptance'])
        self.assertEqual(d['ai_lab_independence'],'unknown')
        self.assertNotIn('PRIVATE_FINDINGS',p.stdout)
        return d

    def test_current_findings_sources_and_schema_two_receipts(self):
        self.controls(revone='findings',revtwo='empty')
        self.unio('review','mock','evidence','revone')
        self.unio('review','mock','evidence','revtwo')
        paths=self.receipts()
        records=[json.loads(p.read_text()) for p in paths]
        self.assertTrue(all(r['schema_version']==2 and r['material_protocol']==2 for r in records))
        folders={r['id']:p.parent.name for p,r in zip(paths,records)}
        seen={n:json.loads((self.root/(n+'.material')).read_text())['sha256']
              for n in ('revone','revtwo')}
        for r in records:
            self.assertEqual(r['material_sha256'],seen[r['reviewer']])
        d=self.findings(code=1)
        self.assertEqual(d['decision'],'findings_attention')
        self.assertFalse(d['incomplete'])
        self.assertEqual([f['severity'] for f in d['findings']],['high','low'])
        self.assertEqual(d['findings'][0]['path'],'hello.txt')
        self.assertEqual(d['findings'][0]['line'],2)
        receipt=next(r for r in records if r['reviewer']=='revone')
        source=d['findings'][0]['sources'][0]
        self.assertEqual(source['receipt_id'],receipt['id'])
        self.assertEqual(source['reviewer'],'revone')
        self.assertEqual(source['policy_group'],receipt['policy_group'])
        self.assertEqual(source['raw_directory'],folders[receipt['id']])
        self.assertEqual(source['stdout_sha256'],receipt['stdout']['sha256'])
        self.assertEqual(source['block_line'],1)
        self.assertEqual(source['finding_index'],0)
        self.assertEqual(d['findings'][1]['summary'],'General note')
        self.assertEqual(d['material_sha256'],d['material_protocols']['2'])
        # A later empty approval does not hide the still-current findings.
        self.controls(revone='empty',revtwo='empty')
        self.unio('review','mock','evidence','revone')
        self.assertEqual(self.findings(code=1)['decision'],'findings_attention')

    def test_empty_structured_findings_exit_zero(self):
        self.controls(revone='empty',revtwo='empty')
        self.unio('review','mock','evidence','revone')
        self.unio('review','mock','evidence','revtwo')
        d=self.findings(code=0)
        self.assertEqual(d['decision'],'no_structured_findings')
        self.assertFalse(d['incomplete'])
        self.assertEqual(d['findings'],[])
        self.assertEqual(sorted(e['findings_state'] for e in d['evidence']),['empty','empty'])
        p=self.unio('reviews','mock','evidence','--expect','revone,revtwo','--findings',code=0)
        self.assertIn('no_structured_findings',p.stdout)
        self.assertIn('Human acceptance: false',p.stdout)

    def test_duplicate_grouping_distinct_claims_and_disagreement(self):
        self.controls(revone='same',revtwo='changes',revthree='samenc',revfour='findings')
        for name in ('revone','revtwo','revthree','revfour'):
            self.unio('review','mock','evidence',name)
        d=self.findings(code=1,expect='revone,revtwo,revthree,revfour')
        self.assertTrue(d['verdict_disagreement'])
        self.assertEqual(len(d['findings']),2)
        merged=d['findings'][0]
        self.assertEqual(merged['summary'],'A concrete issue caf\u00e9')
        self.assertEqual(sorted(s['reviewer'] for s in merged['sources']),
                         ['revfour','revone','revthree','revtwo'])
        self.assertEqual(len({s['receipt_id'] for s in merged['sources']}),4)
        self.assertEqual(d['findings'][1]['summary'],'General note')
        self.assertEqual([s['reviewer'] for s in d['findings'][1]['sources']],['revfour'])
        # Recorded disagreement stays visible even beside later approvals.
        self.controls(revone='empty')
        self.unio('review','mock','evidence','revone')
        later=self.findings(code=1,expect='revone,revtwo,revthree,revfour')
        self.assertTrue(later['verdict_disagreement'])
        self.assertTrue(later['incomplete'] is False or later['incomplete'] is True)

    def test_legacy_receipts_and_mixed_protocol_currentness(self):
        self.controls(revone='empty')
        self.unio('review','mock','evidence','revone')
        real=self.receipts()[0];real_bytes=real.read_bytes()
        base=json.loads(real_bytes)
        d=self.findings(code=0,expect='revone')
        h1=d['material_protocols']['1'];h2=d['material_protocols']['2']
        self.assertNotEqual(h1,h2)
        self.assertEqual(d['material_sha256'],h2)
        def write_receipt(name,material_hash,schema_version,material_protocol=None,
                          stdout=b'VERDICT: APPROVE\n'):
            target=self.coord/'reports'/'evidence.review.'+name
            shutil.copytree(real.parent,target)
            (target/'stdout.log').write_bytes(stdout)
            (target/'stderr.log').write_bytes(b'')
            receipt=dict(base,id=hashlib.sha256(name.encode()).hexdigest()[:32],
                         schema_version=schema_version,material_sha256=material_hash,
                         stdout=dict(sha256=hashlib.sha256(stdout).hexdigest(),bytes=len(stdout)),
                         stderr=dict(sha256=hashlib.sha256(b'').hexdigest(),bytes=0))
            if schema_version==2: receipt['material_protocol']=material_protocol
            else: receipt.pop('material_protocol')
            (target/'receipt.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
            return target
        # A lookalike block in legacy evidence is never inferred as structured.
        lookalike=b'```unio-findings-v1\n'+block(F1).encode()+b'\n```\nVERDICT: APPROVE\n'
        legacy=write_receipt('Legacy01',h1,1,stdout=lookalike)
        legacy_bytes=(legacy/'receipt.json').read_bytes()
        summary=self.summary(expect='revone')
        self.assertEqual(summary['decision'],'all_recorded_approved')
        self.assertEqual(summary['counts']['current'],2)
        self.assertEqual(summary['material_sha256'],h2)
        # Legacy bytes never bind a protocol-2 hash.
        write_receipt('Legacy02',h2,1)
        summary=self.summary(expect='revone')
        self.assertEqual(summary['decision'],'all_recorded_approved')
        self.assertEqual(summary['counts']['current'],2)
        self.assertEqual(summary['counts']['stale'],1)
        # Unknown schema/protocol combinations stay invalid, never promoted.
        write_receipt('Legacy03',h2,2,material_protocol=3)
        summary=self.summary(code=2,expect='revone')
        self.assertEqual(summary['decision'],'incomplete')
        self.assertEqual(summary['counts']['unresolved'],1)
        d=self.findings(code=2,expect='revone')
        legacy_row=next(e for e in d['evidence'] if e['raw_directory'].endswith('Legacy01'))
        self.assertTrue(legacy_row['current'])
        self.assertEqual(legacy_row['findings_state'],'unstructured_legacy')
        self.assertEqual(legacy_row['protocol'],1)
        self.assertEqual(d['findings'],[])  # the lookalike block was not extracted
        self.assertIn('unstructured_legacy',d['reasons'])
        self.assertEqual((legacy/'receipt.json').read_bytes(),legacy_bytes)
        self.assertEqual(real.read_bytes(),real_bytes)

    def test_protocol2_size_refusal_keeps_legacy_receipt_current(self):
        self.task.write_text('# Task\n## Allowed scope\n- hello.txt\n- big.txt\n'
                              '## Validate\n$ test -s hello.txt\n')
        worker=self.root/'project/wt/mock'
        size=298000
        while size<300000:
            (worker/'big.txt').write_text('x'*size)
            self.call(['git','add','big.txt'],cwd=worker)
            self.call(['git','commit','-qm','big'],cwd=worker)
            self.unio('verify','mock','evidence')
            d=self.findings(code=2,expect=None)
            if d['material_protocols']['1'] is None:
                self.fail('material overshot the protocol-1 limit')
            if d['material_protocols']['2'] is None: break
            size+=200
        else: self.fail('no protocol-2 size window found')
        h1=d['material_protocols']['1']
        self.assertIsNone(d['material_protocols']['2'])
        # New review calls cannot run at this size; the refusal is explicit.
        self.unio('review','mock','evidence','revone',code=2)
        rev=d['current_revision']
        stdout=b'VERDICT: APPROVE\n'
        receipt=dict(schema_version=1,id=hashlib.sha256(b'legacybig').hexdigest()[:32],
                     worker='mock',task='evidence',reviewer='revone',
                     recorded_at='2026-10-13T00:00:00+00:00',policy_group=None,
                     requested_model='unknown',effective_model='unknown',
                     requested_effort='unknown',effective_effort='unknown',
                     state='approved',process_exit_code=0,material_complete=True,
                     reasons=[],before=rev,after=rev,material_sha256=h1,
                     stdout=dict(sha256=hashlib.sha256(stdout).hexdigest(),bytes=len(stdout)),
                     stderr=dict(sha256=hashlib.sha256(b'').hexdigest(),bytes=0))
        target=self.coord/'reports/evidence.review.Legacy01'
        target.mkdir()
        (target/'stdout.log').write_bytes(stdout)
        (target/'stderr.log').write_bytes(b'')
        (target/'receipt.json').write_text(json.dumps(receipt,sort_keys=True)+'\n')
        summary=self.summary(expect='revone')
        self.assertEqual(summary['decision'],'all_recorded_approved')
        self.assertEqual(summary['counts']['current'],1)
        self.assertEqual(summary['material_sha256'],h1)
        d=self.findings(code=2,expect='revone')
        self.assertEqual(d['decision'],'unstructured_legacy')
        self.assertEqual(d['material_protocols'],{'1':h1,'2':None})

    def test_invalid_blocks_and_bounds_never_promote_findings(self):
        actions={'noblk':'missing_block','twoblocks':'multiple_blocks',
                 'badjson':'invalid_block','dupkeys':'invalid_block',
                 'nonfinite':'invalid_block','unknownkey':'invalid_block',
                 'badsev':'invalid_block','booline':'invalid_block',
                 'zeroline':'invalid_block','bigline':'invalid_block',
                 'abspath':'invalid_block','traverse':'invalid_block',
                 'longpath':'invalid_block','bigsummary':'invalid_block',
                 'bigdetail':'invalid_block','ctrl':'invalid_block',
                 'many':'invalid_block','bigblock':'oversized_block',
                 'deepnest':'invalid_block','nonutf8':'invalid_block'}
        for action in actions:
            with self.subTest(action=action):
                self.controls(revone=action)
                self.unio('review','mock','evidence','revone')
        self.controls(revone='fail',revtwo='noverdict')
        self.unio('review','mock','evidence','revone',code=1)
        self.unio('review','mock','evidence','revtwo',code=2)
        d=self.findings(code=2)
        observed={e['findings_state'] for e in d['evidence']}
        self.assertEqual(d['findings'],[])
        self.assertTrue(d['incomplete'])
        self.assertEqual(observed,{'missing_block','multiple_blocks','invalid_block',
                                   'oversized_block','not_extracted'})
        # Failed and unknown-verdict evidence keeps its actual state, unpromoted.
        failed=next(e for e in d['evidence'] if e['state']=='failed')
        unknown=next(e for e in d['evidence'] if e['state']=='unknown')
        self.assertEqual(failed['findings_state'],'not_extracted')
        self.assertEqual(unknown['findings_state'],'not_extracted')

    def test_stale_tampered_unbound_and_missing_evidence_stay_visible(self):
        self.controls(revone='findings')
        self.unio('review','mock','evidence','revone')
        self.assertEqual(self.findings(code=1,expect='revone')['findings'][0]['summary'],
                         'A concrete issue caf\u00e9')
        # Replaced stdout cannot pass: the digest binds the parsed bytes.
        stream=self.receipts()[0].parent/'stdout.log'
        saved=stream.read_bytes()
        stream.write_bytes(b'```unio-findings-v1\n'+block(F2).encode()+b'\n```\nVERDICT: APPROVE\n')
        d=self.findings(code=2,expect='revone')
        self.assertEqual(d['counts']['unresolved'],1)
        self.assertEqual(d['findings'],[])
        stream.write_bytes(saved)
        self.assertEqual(self.findings(code=1,expect='revone')['counts']['current'],1)
        # Unbound historical folder stays unresolved.
        legacy=self.coord/'reports/evidence.review.Legacy00';legacy.mkdir()
        (legacy/'stdout.log').write_text('VERDICT: APPROVE\n')
        d=self.findings(code=2,expect='revone')
        self.assertEqual(d['counts']['unresolved'],1)
        # Stale evidence keeps its findings out of the actionable view.
        self.task.write_text(self.task.read_text()+'\nNew owner instructions.\n')
        d=self.findings(code=2,expect='revone')
        self.assertEqual(d['counts']['stale'],1)
        self.assertEqual(d['findings'],[])
        self.assertEqual(d['counts']['unresolved'],1)

    def test_findings_and_incompleteness_coexist_at_exit_one(self):
        self.controls(revone='findings')
        self.unio('review','mock','evidence','revone')
        d=self.findings(code=1,expect='revone,revtwo')
        self.assertEqual(d['decision'],'findings_attention')
        self.assertTrue(d['incomplete'])
        self.assertEqual(d['missing_reviewers'],['revtwo'])
        self.assertEqual(d['findings'][0]['summary'],'A concrete issue caf\u00e9')
        self.assertEqual(d['counts']['current'],1)

    def test_lock_and_revision_drift_make_findings_unavailable(self):
        self.controls(revone='findings')
        self.unio('review','mock','evidence','revone')
        with (self.coord/'.locks/mock.lock').open('rb') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
            d=self.findings(code=2,expect='revone')
        self.assertEqual(d['decision'],'incomplete')
        self.assertIn('worker_busy',d['reasons'])
        self.assertEqual(d['findings'],[])
        self.assertTrue(all(not e['current'] for e in d['evidence']))
        worker=self.root/'project/wt/mock'
        (worker/'hello.txt').write_text('updated candidate')
        self.call(['git','add','hello.txt'],cwd=worker)
        self.call(['git','commit','-qm','updated candidate'],cwd=worker)
        d=self.findings(code=2,expect='revone')
        self.assertIn('revision_changed',d['reasons'])
        self.assertEqual(d['findings'],[])
        self.assertEqual(d['counts']['current'],0)

    def test_stop_and_read_only_browsing(self):
        self.controls(revone='findings',revtwo='empty')
        self.unio('review','mock','evidence','revone')
        self.unio('review','mock','evidence','revtwo')
        self.unio('stop')
        def hashes():
            return {str(p.relative_to(self.coord)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in self.coord.rglob('*') if p.is_file()}
        before=hashes();calls=self.calls()
        self.findings(code=1)
        self.assertEqual(hashes(),before)
        self.assertEqual(self.calls(),calls)
        self.unio('resume')

    def test_review_set_binds_whole_protocol_two_material(self):
        self.unio('account','revone','alpha');self.unio('account','revtwo','beta')
        self.controls(revone='same',revtwo='same')
        self.unio('review-set','mock','evidence','revone','revtwo')
        manifest=json.loads(max((self.coord/'reports').glob('evidence.review-set.*/collection.json'),
                                key=lambda p:p.stat().st_mtime_ns).read_text())
        records=[json.loads((self.coord/'reports'/a['raw_directory']/'receipt.json').read_text())
                 for a in manifest['attempts'] if a['receipt_id'] is not None]
        self.assertEqual(len(records),2)
        seen={n:json.loads((self.root/(n+'.material')).read_text())['sha256']
              for n in ('revone','revtwo')}
        for r in records:
            self.assertEqual(r['schema_version'],2)
            self.assertEqual(r['material_protocol'],2)
            self.assertEqual(r['material_sha256'],manifest['material_sha256'])
            self.assertEqual(r['material_sha256'],seen[r['reviewer']])
        d=self.findings(code=1)
        self.assertEqual(len(d['findings']),1)
        self.assertEqual(sorted(s['reviewer'] for s in d['findings'][0]['sources']),
                         ['revone','revtwo'])
        self.assertEqual(len({s['raw_directory'] for s in d['findings'][0]['sources']}),2)
        self.assertEqual(d['material_sha256'],manifest['material_sha256'])

    def test_help_completion_and_invalid_arguments(self):
        p=self.unio('reviews','--help',cwd=self.install)
        self.assertIn('--findings',p.stdout)
        completion=(self.install/'completion/unio').read_text()
        self.assertIn('--findings',completion)
        for args in [['mock','evidence','--findings','--findings'],
                     ['mock','evidence','--findings','--json','--json'],
                     ['mock','evidence','--findings','--expect'],
                     ['mock','evidence','--findings','--invalid']]:
            self.unio('reviews',*args,code=2,cwd=self.install)
        self.assertEqual(self.findings(code=2,expect=None)['decision'],'not_run')

if __name__=='__main__':unittest.main(verbosity=2)
