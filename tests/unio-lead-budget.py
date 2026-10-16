#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed mock-only consent regression; never invokes a real provider."""
import json
import os
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

source = Path(__file__).resolve().parent.parent
count = 0

def check(name, ok, detail=''):
    global count
    assert ok, name + ': ' + str(detail)
    count += 1
    print('ok', name, flush=True)

with tempfile.TemporaryDirectory(prefix='lead-budget-') as tmp:
    base = Path(tmp)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
               UNIO_COMPLETION_DIR=str(base/'completion'), UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0', UNIO_TIMEOUT='20',
               GIT_AUTHOR_NAME='mock', GIT_AUTHOR_EMAIL='mock@example.invalid',
               GIT_COMMITTER_NAME='mock', GIT_COMMITTER_EMAIL='mock@example.invalid')
    subprocess.run(['bash', str(source/'unio-install.sh')], env=env, check=True, capture_output=True)
    runner = base/'bin/unio'
    root = base/'project'; repo = root/'repo'; repo.mkdir(parents=True)
    def cli(*args):
        return subprocess.run([str(runner), *args], cwd=repo, env=env,
                              capture_output=True, text=True, timeout=60)
    for args in [('init', '-q', '-b', 'main'), ('add', '.'), ('commit', '--allow-empty', '-qm', 'seed')]:
        subprocess.run(['git', *args], cwd=repo, env=env, check=True, capture_output=True)
    calls = base/'calls'
    mock = base/'mock.sh'
    mock.write_text('echo called >> "'+str(calls)+'"\nsleep 0.2\nexit 7\n')
    (base/'conf/agents.conf').write_text('mock=bash "'+str(mock)+'"\nalias=bash "'+str(mock)+'"\nother=bash "'+str(mock)+'"\n')
    result = cli('init', 'mock', 'alias', 'other')
    check('installed init', result.returncode == 0, result.stderr)
    for name in ('task', 'other-task'):
        (root/'coord/tasks'/f'{name}.md').write_text('Owner task '+name+'\n')
    store = root/'coord/lead-budget.json'
    def records(): return json.loads(store.read_text())
    def grant(kind='run', worker='mock', task='task', agent='mock'):
        r = cli('lead-budget', 'grant', agent, worker, task, kind)
        check('owner grant '+kind, r.returncode == 0, r.stderr)
        return records()['grants'][-1]['id']
    def run(worker='mock', task='task'):
        return cli('run', worker, task)
    def ncall(): return len(calls.read_text().splitlines()) if calls.exists() else 0
    def refused(label, action):
        before = ncall(); r = action()
        check(label, r.returncode != 0 and ncall() == before and 'budget' in r.stderr, r.stdout+r.stderr)
        return r
    cli('account', 'alias', 'mock'); cli('lead', 'mock')
    for tier in ('medium', 'high'):
        cli('tier', tier)
        r = refused(tier+' shared lead denied', run)
        check('actionable refusal', 'lead-budget grant' in r.stderr, r.stderr)
    grant(); cli('tier', 'low')
    refused('low still capped with grant', run)
    check('capacity refusal does not consume', records()['grants'][-1]['state'] == 'ready')
    cli('tier', 'medium')
    before = ncall(); r = run()
    check('grant admits provider with original failed exit', r.returncode == 7 and ncall() == before+1, r.stdout+r.stderr)
    check('failed provider leaves used history', records()['grants'][-1]['state'] == 'used')
    refused('replay denied', run)
    refused('same group alias cannot bypass', lambda: run('alias'))
    before = ncall(); r = run('other')
    check('different actual group unaffected', r.returncode == 7 and ncall() == before+1, r.stdout+r.stderr)
    grant(); refused('other worker denied', lambda: run('alias'))
    refused('other task denied', lambda: run(task='other-task'))
    task = root/'coord/tasks/task.md'; original = task.read_text(); task.write_text(original+'changed\n')
    refused('changed task hash denied', run); task.write_text(original)
    conf = base/'conf/agents.conf'; original_conf = conf.read_text(); conf.write_text(original_conf+'# changed route config\n')
    refused('changed route denied', run); conf.write_text(original_conf)
    cli('lead','none'); cli('account','mock','newgroup'); cli('lead','mock')
    refused('changed actual group denied',run)
    cli('lead','none'); cli('account','mock','mock'); cli('lead','mock')
    cli('lead', 'none'); cli('lead', 'alias')
    refused('changed lead denied', run); cli('lead', 'none'); cli('lead', 'mock')
    # Installed helper entry points exercise the same broker used by reviewers.
    text = runner.read_text(); helper = text.split("<<'POLICY_PY'\n",1)[1].split('\nPOLICY_PY\n',1)[0]
    helper_file = base/'policy.py'; helper_file.write_text(helper)
    penv = dict(env, UNIO_POLICY_CONF=str(base/'conf'))
    def policy(*args):
        return subprocess.run(['python3','-B', str(helper_file),str(root),*args], env=penv,
                              capture_output=True,text=True,timeout=10)
    def probe(kind='review', owner='task', worker='mock'):
        return policy('_admit_hold','mock',worker,'attempt',kind,str(task),str(base/'missing-fifo'),owner)
    refused('run grant does not permit review', probe)
    # Revoke ready run grant, then permit exactly one review. Missing FIFO is a
    # deliberate post-consumption startup failure, with no fake Source success.
    ready = records()['grants'][-1]['id']; cli('lead-budget','revoke',ready)
    gid = grant('review')
    r = probe()
    check('review consumed before uncertain startup', records()['grants'][-1]['state']=='used', r.stderr)
    refused('review replay denied', probe)
    gid = grant(); cli('lead-budget','revoke',gid)
    refused('revoked grant denied', run)
    gid = grant(); data=records(); data['grants'][-1]['issued']=1; data['grants'][-1]['expires']=901
    store.write_text(json.dumps(data)); refused('expired grant denied',run)
    clean=store.read_bytes()
    for raw in (b'{', b'{}', b'x'*65537):
        store.write_bytes(raw); refused('malformed or oversized state denied',run)
        check('evidence unchanged',store.read_bytes()==raw)
    store.write_bytes(clean)
    typed=records(); typed['grants'][-1]['expires']='later'
    store.write_text(json.dumps(typed)); refused('malformed typed record denied',run)
    store.write_bytes(clean); store.chmod(0o644)
    refused('nonprivate state denied',run); store.chmod(0o600)
    target=base/'sentinel'; target.write_bytes(clean); target.chmod(0o600)
    store.unlink(); store.symlink_to(target)
    refused('symlink state denied',run); check('symlink preserved',store.is_symlink())
    store.unlink(); os.link(target,store)
    refused('hardlink state denied',run); check('hardlink preserved',store.stat().st_nlink==2)
    store.unlink(); store.write_bytes(clean); store.chmod(0o600)
    gid=grant('review'); cli('tier','high')
    before=ncall()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _: probe(), range(2)))
    check('concurrent broker consumes exactly once',
          sum('shared lead budget requires' in r.stderr for r in results)==1
          and sum('shared lead budget requires' not in r.stderr for r in results)==1,
          [r.stderr for r in results])
    check('concurrent grant used once with no provider',records()['grants'][-1]['state']=='used' and ncall()==before)
    (root/'coord/tasks/background.md').write_text('Background owner task\n')
    refused('native background run cannot bypass',lambda: cli('run','-b','mock','background'))
    check('store private',store.stat().st_mode & 0o777 == 0o600)
    # Legacy slot path refuses shared operation even with a grant.
    grant(); refused('legacy slot creation cannot bypass',lambda: policy('_slot_create','mock','mock','mock','task','run'))
print('lead-budget:',count,'checks passed')
