#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Limit phrases are a heuristic on one normalized final window; worker text never benches an agent."""
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import time

source = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='limit-wall-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'),
               UNIO_CONF_DIR=str(base/'conf'), UNIO_COMPLETION_DIR=str(base/'completion'),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
               UNIO_TIMEOUT='20', UNIO_VERIFY_TIMEOUT='10')
    subprocess.run(['bash',str(source/'unio-install.sh')],env=env,check=True,capture_output=True)
    at = str(base/'bin/unio')
    root = base/'project'; repo = root/'repo'; repo.mkdir(parents=True)
    def git(*args):
        return subprocess.run(['git',*args],cwd=repo,env=env,check=True,capture_output=True)
    git('init','-q','-b','main'); (repo/'canary.txt').write_text('pending\n')
    (repo/'quota-notes.txt').write_text('usage limit reached. resets at 17:00.\n')
    git('add','canary.txt','quota-notes.txt'); git('commit','-qm','seed')
    subprocess.run([at,'init','mock'],cwd=repo,env=env,check=True,capture_output=True)
    seed = git('rev-parse','HEAD').stdout.decode().strip()
    mock = root/'mock.py'
    mock.write_text('''import os,subprocess
from pathlib import Path
print(os.environ.get('WALL_MOCK_TEXT',''),end='')
mode=os.environ.get('WALL_MOCK_MODE','fail')
if mode in ('work','workfail'):
    with Path('canary.txt').open('a') as f: f.write('done\\n')
    subprocess.run(['git','add','canary.txt'],check=True)
    subprocess.run(['git','commit','-qm','mock'],check=True)
raise SystemExit(0 if mode in ('work','dry') else 7)
''')
    (base/'conf/agents.conf').write_text('mock=python3 '+shlex.quote(str(mock))+'\n')
    conf_text = (base/'conf/agents.conf').read_text()
    count = 0
    def check(label, condition=True):
        global count
        assert condition,label
        count += 1
        print('  wall: '+label,flush=True)
    def bench(): return (base/'conf/off/mock').exists()
    def avail():
        p = subprocess.run([at,'agents','--json'],cwd=repo,env=env,capture_output=True,text=True,check=True)
        return [a for a in json.loads(p.stdout)['agents'] if a['name']=='mock'][0]
    def clean_state():
        return not bench() and (base/'conf/agents.conf').read_text()==conf_text \
               and avail()['bench']['off'] is False and avail()['capacity']=='unknown'
    def reset():  # drop earlier case commits so empty-work cases stay empty
        work = root/'wt/mock'
        subprocess.run(['git','-C',str(work),'reset','--hard',seed],env=env,check=True,capture_output=True)
        subprocess.run(['git','-C',str(work),'clean','-fdq'],env=env,check=True,capture_output=True)
    def call(*args, code=0, mode='fail', text='', auto_off='0'):
        reset()
        p = subprocess.run([at,*args],cwd=repo,env=dict(env,WALL_MOCK_MODE=mode,WALL_MOCK_TEXT=text,
                            UNIO_AUTO_OFF=auto_off),capture_output=True,text=True)
        assert p.returncode==code,(args,p.returncode,code,p.stdout,p.stderr)
        return p
    def task(name, checks='$ true'):
        (root/'coord/tasks'/f'{name}.md').write_text(f'# {name}\n## Allowed scope\n- canary.txt\n## Validate\n{checks}\n')
    def wall(name):
        events=[json.loads(line) for line in (root/'coord/reports/ledger.jsonl').read_text().splitlines()]
        return [e for e in events if e.get('event')=='run' and e.get('task')==name][-1]['wall']
    def window(name):
        report=(root/'coord/reports'/f'{name}.md').read_text()
        return report.rsplit('### agent output (tail)',1)[1].split('~~~')[1]
    WARNING='!! output mentions usage limits'

    task('superseded')
    p=call('run','mock','superseded',code=7,auto_off='1',text='The preceding quota question is superseded.')
    check('worker prose about quotas never walls or benches',WARNING not in p.stderr and wall('superseded')==0 and clean_state())

    task('capped')
    p=call('run','mock','capped',code=7,auto_off='1',text="Error: You've hit your usage limit. Resets at 3pm.")
    check('provider cap language walls a failed run but never benches it, even with AUTO_OFF=1',
          WARNING in p.stderr and wall('capped')==1 and not bench() and clean_state())

    task('requests')
    p=call('run','mock','requests',code=7,text='HTTP 429 Too Many Requests')
    check('too many requests walls a failed run and preserves its exit',
          WARNING in p.stderr and wall('requests')==1)

    task('succeeds')
    p=call('run','mock','succeeds',code=0,mode='work',auto_off='1',text='rate limit exceeded')
    check('successful committed work never walls or benches whatever it prints',
          WARNING not in p.stderr and wall('succeeds')==0 and clean_state())

    task('empty-capped')
    p=call('run','mock','empty-capped',code=0,mode='dry',auto_off='1',
           text='Error: usage limit reached for this model. resets at 17:00.')
    check('exit-zero empty work is failed for the helper: wall=1, real exit kept, no bench',
          WARNING in p.stderr and wall('empty-capped')==1 and not bench() and clean_state())

    task('failed-committed')
    p=call('run','mock','failed-committed',code=7,mode='workfail',auto_off='1',text='Too many requests')
    check('failed committed work walls but never benches',
          WARNING in p.stderr and wall('failed-committed')==1 and not bench() and clean_state())

    task('ansi-capped')
    p=call('run','mock','ansi-capped',code=7,mode='fail',text='usage \x1b[1mlimit\x1b[0m reached\r')
    raw=(root/'coord/reports/ansi-capped.log').read_bytes()
    shown=window('ansi-capped')
    check('ANSI escapes and carriage returns are normalized for matching and display',
          WARNING in p.stderr and wall('ansi-capped')==1 and b'\x1b[1m' in raw and b'\r' in raw
          and '\x1b' not in shown and '\r' not in shown and 'usage limit reached' in shown)

    task('far-capped')
    p=call('run','mock','far-capped',code=7,mode='fail',
           text='usage limit reached\n'+'\n'.join(f'filler {i}' for i in range(49)))
    check('a phrase 50 lines from the end still walls (60-line window)',
          WARNING in p.stderr and wall('far-capped')==1)

    task('printed-repo')
    p=call('run','mock','printed-repo',code=7,auto_off='1',text=(repo/'quota-notes.txt').read_text())
    check('printed repository file text walls a failed run as suspected only, never benches',
          WARNING in p.stderr and wall('printed-repo')==1 and not bench() and clean_state())

    task('unstructured-ocy')
    p=call('run','mock','unstructured-ocy',code=7,auto_off='1',
           text='API error (status 402 Payment Required): Grok Build usage balance exhausted')
    check('unstructured Grok 402 balance exhaustion stays Unknown/suspected only and never benches',
          'Adapter outcome: Unknown' in p.stdout and WARNING in p.stderr and wall('unstructured-ocy')==1
          and not bench() and clean_state())

    print(f'limit-wall regressions: {count} passed')
