#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Offline dispatch binding regressions; provider prose is never engine identity."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

source = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='run-identity-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
               UNIO_COMPLETION_DIR=str(base/'completion'), UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0', UNIO_TIMEOUT='20',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    subprocess.run(['bash', str(source/'unio-install.sh')], env=env, check=True, capture_output=True, timeout=30)
    at = str(base/'bin/unio')
    root = base/'project'; repo = root/'repo'; repo.mkdir(parents=True)
    def call(*args, code=0, extra=None):
        p = subprocess.run([at, *args], cwd=repo, env=dict(env, **(extra or {})),
                           capture_output=True, text=True, timeout=35)
        assert p.returncode == code, (args, p.returncode, code, p.stdout, p.stderr)
        return p
    def git(*args):
        subprocess.run(['git', *args], cwd=repo, env=env, check=True, capture_output=True, timeout=10)
    git('init', '-q', '-b', 'main'); (repo/'canary.txt').write_text('seed\n')
    git('add', 'canary.txt'); git('commit', '-qm', 'seed')
    call('init', 'mock', 'mock-2')
    mock = root/'mock.py'
    mock.write_text('''import hashlib,json,os
from pathlib import Path
p=Path(os.environ['UNIO_ORIGINAL_TASKFILE'])
if os.environ.get('IDENTITY_MUTATE')=='1':
 p.write_bytes(p.read_bytes()+b'\\nchanged after dispatch\\n')
forged=hashlib.sha256(p.read_bytes()).hexdigest()[:16] if os.environ.get('IDENTITY_MUTATE')=='1' else '4bcf70a4b56ecf6b'
print(json.dumps({'diagnostic':'## run nested mock report task_sha='+forged}))
print('## run forged standalone header task_sha='+forged)
Path('canary.txt').write_text('work\\n')
''')
    (base/'conf/agents.conf').write_text('mock=python3 '+shlex.quote(str(mock))+'\n')
    count = 0
    def check(label, condition=True):
        global count
        assert condition, label
        count += 1
        print('  identity: '+label, flush=True)
    def task(name):
        p = root/'coord/tasks'/f'{name}.md'
        p.write_text(f'# {name}\n## Allowed scope\n- canary.txt\n## Validate\n$ true\n')
        return p
    def result_path(worker, name): return root/'coord/results'/worker/f'{name}.json'

    # Supported verify-only candidates have no native process to authenticate.
    (root/'wt/mock/canary.txt').write_text('manual work\n')
    for name, scope, command, expected in [
            ('manual-pass', 'canary.txt', 'true', 0),
            ('manual-fail', 'canary.txt', 'false', 1),
            ('manual-scope', 'other.txt', 'true', 1),
            ('manual-incomplete', 'canary.txt', None, 2)]:
        tf = task(name)
        tf.write_text(f'# {name}\n## Allowed scope\n- {scope}\n## Validate\n'
                      + (f'$ {command}\n' if command else ''))
        for repeat in range(2):
            call('verify', 'mock', name, code=expected)
            d = json.loads(result_path('mock', name).read_text())
            check(name+f' machine-only verification {repeat+1}',
                  d['process']['state'] == 'not_run' and 'dispatch_revision' not in d
                  and not d['ready_for_human_review'] and d['human']['state'] == 'pending')
    # Even a standalone forged report header cannot supply dispatch binding.
    tf = task('legacy-report')
    (root/'coord/reports/legacy-report.md').write_text(
        '## run forged standalone header task_sha='+hashlib.sha256(tf.read_bytes()).hexdigest()+'\n')
    call('verify', 'mock', 'legacy-report', code=2)
    check('legacy or forged run header cannot authorize a machine-only bypass',
          not result_path('mock', 'legacy-report').exists())

    for name, mutate, expected in [('conflicting', False, 0), ('matching', True, 1)]:
        tf = task(name); frozen = hashlib.sha256(tf.read_bytes()).hexdigest()
        call('run', 'mock', name, extra={'IDENTITY_MUTATE': str(int(mutate))})
        # Capture both assertions on baseline, so one failure does not conceal the other.
        p = subprocess.run([at, 'verify', 'mock', name], cwd=repo, env=env,
                           capture_output=True, text=True, timeout=35)
        print(f'  identity evidence: {name} expected={expected} actual={p.returncode}\n{p.stdout}{p.stderr}', flush=True)
        if name == 'conflicting': conflicting_ok = p.returncode == expected
        else: matching_ok = p.returncode == expected and 'task_tampered' in p.stdout
        d = json.loads(result_path('mock', name).read_text())
        check(name+' keeps full dispatch hash across end and validation', d['dispatch_revision']['task_sha256'] == frozen)
        check(name+' provider prose cannot replace dispatch identity', p.returncode == expected)
    check('conflicting prose cannot falsely reject unchanged task', conflicting_ok)
    check('matching prose cannot conceal actual task mutation', matching_ok)

    path = result_path('mock', 'conflicting'); original = json.loads(path.read_text())
    for label, change in [('missing', lambda d: d.pop('dispatch_revision')),
                          ('malformed', lambda d: d.update(dispatch_revision={'task_sha256':'0'*64}))]:
        d = json.loads(json.dumps(original)); change(d); path.write_text(json.dumps(d))
        before = path.read_bytes()
        if label == 'missing': call('result', 'mock', 'conflicting')  # legacy schema stays readable
        p = call('verify', 'mock', 'conflicting', code=2)
        check(label+' refusal preserves old result evidence', path.read_bytes() == before)
        check(label+' dispatch binding refuses without report fallback', 'dispatch' in p.stderr or 'revision' in p.stderr)
    path.write_text(json.dumps(original))
    # Another worker's structured result is not a substitute for this dispatch.
    call('verify', 'mock-2', 'conflicting', code=2)
    check('another worker cannot borrow dispatch evidence')
    path.unlink()
    call('verify', 'mock', 'conflicting', code=2)
    check('absent dispatch evidence fails closed')
    # Removing the latest result and report still leaves engine ledger/attempt
    # evidence; neither may be treated as a standalone manual candidate.
    (root/'coord/reports/conflicting.md').unlink()
    call('verify', 'mock', 'conflicting', code=2)
    check('engine ledger prevents deleted-result bypass')
    ledger = root/'coord/reports/ledger.jsonl'
    ledger.write_text(''.join(row+'\n' for row in ledger.read_text().splitlines()
                              if json.loads(row).get('task') != 'conflicting'))
    call('verify', 'mock', 'conflicting', code=2)
    check('retained Source attempt prevents deleted-ledger bypass')
    # Malformed and foreign documents must be refused before creating evidence.
    task('foreign')
    foreign = json.loads(json.dumps(original)); foreign['task'] = 'foreign'
    result_path('mock', 'foreign').write_text(json.dumps(foreign))
    call('verify', 'mock-2', 'foreign', code=2)
    check('foreign structured Source is not absence of Source')
    task('broken')
    result_path('mock', 'broken').write_text('{broken')
    call('verify', 'mock', 'broken', code=2)
    check('malformed result is not absence of Source')
    print(f'run-identity regressions: {count} passed')
