#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Read-only activity observations and streams, using local mock commands only."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import select
import shlex
import signal
import subprocess
import tempfile

source = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='watch-') as directory:
    base=Path(directory); root=base/'project'; repo=root/'repo'; repo.mkdir(parents=True)
    env=dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
             UNIO_COMPLETION_DIR=str(base/'completion'), UNIO_AUTO_VERIFY='0',
             UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='15',
             GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
             GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    subprocess.run(['bash',str(source/'unio-install.sh')],env=env,check=True,capture_output=True)
    at=str(base/'bin/unio')
    def call(*args, code=0):
        p=subprocess.run([at,*args],cwd=repo,env=env,capture_output=True,text=True,timeout=30)
        assert p.returncode==code,(args,p.returncode,p.stdout,p.stderr)
        return p
    def git(*args): return subprocess.run(['git',*args],cwd=repo,env=env,check=True,capture_output=True)
    git('init','-q','-b','main');(repo/'canary.txt').write_text('pending\n')
    git('add','canary.txt');git('commit','-qm','seed');call('init','mock')
    marker=root/'calls';mock=root/'mock.py'
    mock.write_text('''from pathlib import Path
import subprocess,os
p=Path(__file__).parent
with (p/'calls').open('a') as f:f.write('called\\n')
if os.environ.get('FAIL_MOCK'):raise SystemExit(7)
with Path('canary.txt').open('a') as f:f.write('ready\\n')
subprocess.run(['git','add','canary.txt'],check=True)
subprocess.run(['git','commit','-qm','mock'],check=True)
''')
    (base/'conf/agents.conf').write_text('mock=python3 '+shlex.quote(str(mock))+' PRIVATE_COMMAND\nreviewer=printf "VERDICT: APPROVE\\n"\n')
    task=root/'coord/tasks/activity.md';task.write_text('# Activity\n## Allowed scope\n- canary.txt\n## Validate\n$ true\n')
    checks=0
    def check(label, condition=True):
        global checks
        assert condition,label;checks+=1;print('  watch: '+label,flush=True)
    def snapshot():
        p=subprocess.run([at,'watch','--once','--json'],cwd=repo,env=env,capture_output=True,text=True,timeout=10)
        assert p.returncode==0,(p.stdout,p.stderr)
        return json.loads(p.stdout)
    def files():
        return {str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (root/'coord').rglob('*') if p.is_file()}
    before=files();s=snapshot()
    check('empty project snapshot creates no coordination files',files()==before and s['results']==[])
    check('local diagnostics keep auth and capacity unknown',all(a['authentication']==a['capacity']=='unknown' for a in s['agents']))
    check('commands, secrets and raw task text absent', 'PRIVATE_COMMAND' not in json.dumps(s) and not marker.exists())
    call('run','mock','activity');call('verify','mock','activity');call('review','mock','activity','reviewer')
    before=files();s=snapshot();r=s['results'][0]
    check('recorded process, validation and review shown separately',r['process']['state']=='succeeded' and r['validation']['state']=='passed' and r['review']['state']=='approved')
    check('monitor never claims current readiness', 'ready_for_human_review' not in json.dumps(s) and 'recorded' in s['evidence'])
    check('watching completed evidence is read only',files()==before and len(marker.read_text().splitlines())==1)
    check('repeated Unio snapshots agree',snapshot()['results']==s['results'])
    human=call('watch','--once').stdout
    check('human view explains recorded evidence', 'validation passed' in human and 'review approved' in human and 'Authentication/capacity unknown' in human)
    call('off','mock','5h');call('stop');s=snapshot();a=s['agents'][0]
    check('STOP and operator retry are visible without a quota probe',s['stopped'] and a['bench']['off'] and a['bench']['operator_retry_at'] and a['capacity']=='unknown')
    call('resume');call('on','mock')
    task2=root/'coord/tasks/failed.md';task2.write_text(task.read_text())
    env['FAIL_MOCK']='1'
    call('run','mock','failed',code=7);call('run','mock','failed',code=7);del env['FAIL_MOCK']
    s=snapshot();brake=next(x for x in s['retries'] if x['task']=='failed')
    check('failure history and blocked task visible',brake['failed_attempts']==2 and brake['blocked'])
    call('allow-retry','failed');s=snapshot();brake=next(x for x in s['retries'] if x['task']=='failed')
    check('single owner grant visible',brake['retry_granted'] and not brake['blocked'])
    result=root/'coord/results/mock/activity.json';d=json.loads(result.read_text())
    d['process']['state']='running';d['process']['exit_code']=None;d['updated_at']='2026-01-01T00:00:00+00:00';result.write_text(json.dumps(d))
    before=files();s=snapshot();r=next(x for x in s['results'] if x['task']=='activity')
    check('unheld recorded running state has unknown completion',r['activity']=='completion_unknown' and r['process']['state']=='running' and r['process']['exit_code'] is None)
    check('interrupted observation does not rewrite native evidence',files()==before)
    lock=root/'coord/.locks/mock.lock'
    with lock.open('rb') as held:
        fcntl.flock(held,fcntl.LOCK_EX | fcntl.LOCK_NB)
        r=next(x for x in snapshot()['results'] if x['task']=='activity')
        check('held lock is an observation separate from recorded process',r['worker_lock']=='held' and r['activity']=='running_recorded')
    ledger=root/'coord/reports/ledger.jsonl'
    with ledger.open('a') as f:
        f.write('{broken}\n'+json.dumps({'event':'merge','ts':'now','worker':'mock','subject':'PRIVATE_COMMAND'})+'\n'+ '{"event":')
    s=snapshot()
    check('malformed and partial ledger lines do not invent events',any(w['source']=='ledger' for w in s['warnings']) and s['recent_events'][-1]['event']=='merge' and 'PRIVATE_COMMAND' not in json.dumps(s))
    ledger.write_text(json.dumps({'event':'run','task':'rotated','exit':7,'wall':1})+'\n')
    check('replaced ledger is followed',snapshot()['recent_events'][0]['task']=='rotated')
    check('limit signal remains a runner pattern, not known capacity',snapshot()['recent_events'][0]['limit_signal']=='runner_log_pattern' and all(a['capacity']=='unknown' for a in snapshot()['agents']))
    retry=root/'coord/retries/failed/state.json';broken=json.loads(retry.read_text());broken['latest']['mock']['id']='invalid';retry.write_text(json.dumps(broken))
    s=snapshot();check('corrupt retry attempt is warned about without a usable grant',any(w['source']=='retry' for w in s['warnings']) and all(x['task']!='failed' for x in s['retries']))
    result.write_text('{broken');s=snapshot()
    check('corrupt result is warned about without a verdict',any(w['source']=='result' for w in s['warnings']) and all(x['task']!='activity' for x in s['results']))
    stream=subprocess.Popen([at,'watch','--json','--interval','.1'],cwd=repo,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
    try:
        assert select.select([stream.stdout],[],[],5)[0];first=json.loads(stream.stdout.readline())
        check('live stream starts with a full snapshot',first['schema_version']==1)
        check('unchanged state does not flood the stream',not select.select([stream.stdout],[],[],.3)[0])
        call('stop');assert select.select([stream.stdout],[],[],5)[0]
        check('live stream emits state changes',json.loads(stream.stdout.readline())['stopped'])
        stream.send_signal(signal.SIGINT);stdout,stderr=stream.communicate(timeout=5)
        check('Ctrl-C exits cleanly',stream.returncode==0 and not stderr)
    finally:
        if stream.poll() is None:os.killpg(stream.pid,signal.SIGTERM);stream.communicate(timeout=5)
    before=len(marker.read_text().splitlines());ledger.unlink();private=base/'private';private.write_text('PRIVATE_COMMAND')
    ledger.symlink_to(private);p=call('watch','--once','--json',code=2)
    check('symlink ledger refused without reading target', 'PRIVATE_COMMAND' not in p.stdout+p.stderr)
    ledger.unlink();os.mkfifo(ledger);call('watch','--once',code=2);ledger.unlink()
    check('FIFO ledger is refused without blocking')
    call('watch','--once','--interval','nan',code=2);call('watch','--unknown',code=2)
    check('invalid monitor arguments spend no quota',len(marker.read_text().splitlines())==before)
    print(f'watch regressions: {checks} passed')
