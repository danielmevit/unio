#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Provider invocation markers prove the loop brake refuses before spending quota."""
import concurrent.futures
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

source = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='loop-brake-') as directory:
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
    git('add','canary.txt'); git('commit','-qm','seed')
    subprocess.run([at,'init','mock','mock-2','mock-3'],cwd=repo,env=env,check=True,capture_output=True)
    mark = root/'calls'; info = root/'mock-process.json'
    mock = root/'mock.py'
    mock.write_text('''import os,json,subprocess,time
from pathlib import Path
p=Path(__file__).parent
with (p/'calls').open('a') as f: f.write('called\\n')
mode=os.environ.get('BRAKE_MOCK_MODE','fail')
if mode=='hold':
 raw=Path('/proc/self/stat').read_text(); fields=raw[raw.rfind(')')+2:].split()
 (p/'mock-process.json').write_text(json.dumps({'pid':os.getpid(),'pgid':os.getpgrp(),'sid':os.getsid(0),'start':int(fields[19])}))
 while True: time.sleep(.1)
if mode=='work':
 with Path('canary.txt').open('a') as f: f.write('ready\\n')
 subprocess.run(['git','add','canary.txt'],check=True)
 subprocess.run(['git','commit','-qm','mock'],check=True)
raise SystemExit(7 if mode=='fail' else 0)
''')
    (base/'conf/agents.conf').write_text('mock=python3 '+shlex.quote(str(mock))+'\n')
    count = 0
    def check(label, condition=True):
        global count
        assert condition,label
        count += 1
        print('  brake: '+label,flush=True)
    def calls(): return len(mark.read_text().splitlines()) if mark.exists() else 0
    def call(*args, code=0, mode='fail'):
        p = subprocess.run([at,*args],cwd=repo,env=dict(env,BRAKE_MOCK_MODE=mode),capture_output=True,text=True,timeout=45)
        assert p.returncode==code,(args,p.returncode,code,p.stdout,p.stderr)
        return p
    def task(name, checks='$ true'):
        (root/'coord/tasks'/f'{name}.md').write_text(f'# {name}\n## Allowed scope\n- canary.txt\n## Validate\n{checks}\n')
    def state(name): return json.loads((root/'coord/retries'/name/'state.json').read_text())
    def refuse(name, worker='mock'):
        n=calls(); p=call('run',worker,name,code=2)
        assert 'loop brake:' in p.stderr and calls()==n
        return p

    def identity(pid):
        try:
            raw=Path(f'/proc/{pid}/stat').read_text(); fields=raw[raw.rfind(')')+2:].split()
            return dict(pid=pid, start=int(fields[19]), sid=int(fields[3]), state=fields[0])
        except (OSError, ValueError, IndexError): return None
    def live(record):
        now=identity(record['pid'])
        return now is not None and now['start']==record['start'] and now['sid']==record['sid'] and now['state'] not in ('Z','X','x')
    def signal_exact(record, sig):
        if not live(record): return
        try:
            fd=os.pidfd_open(record['pid'])
            try:
                if live(record): signal.pidfd_send_signal(fd,sig)
            finally: os.close(fd)
        except ProcessLookupError: pass

    def kill_fixture(shell, provider=None):
        owned=[]; frontier=[shell['pid']] if live(shell) else []
        while frontier:
            pid=frontier.pop()
            try: children=Path(f'/proc/{pid}/task/{pid}/children').read_text().split()
            except OSError: children=[]
            for child in children:
                row=identity(int(child))
                if row: owned.append(row); frontier.append(row['pid'])
        if provider is not None:
            leader=identity(provider['pid'])
            if leader is None or (leader['start']==provider['start'] and leader['sid']==provider['sid']):
                for entry in Path('/proc').iterdir():
                    row=identity(int(entry.name)) if entry.name.isdigit() else None
                    if row and row['sid']==provider['sid']: owned.append(row)
        for row in reversed(owned): signal_exact(row,signal.SIGKILL)
        signal_exact(shell,signal.SIGKILL)

    # A refused run must never publish over, remove, or reap an active run's
    # controls, including when two workers share a task and retry history.
    def ownership_collision(owner_mode):
        name='collision-'+owner_mode
        saved_mode=env.get('UNIO_BG')
        env['UNIO_BG']=owner_mode
        task(name)
        info.unlink(missing_ok=True)
        with (base/(name+'.stdout')).open('w') as output, (base/(name+'.stderr')).open('w') as errors:
            proc=subprocess.Popen([at,'run','mock',name],cwd=repo,
                                  env=dict(env,BRAKE_MOCK_MODE='hold',UNIO_TIMEOUT='120',UNIO_BG=owner_mode),
                                  stdout=output,stderr=errors,start_new_session=True)
            shell=identity(proc.pid); provider=None
            try:
                deadline=time.monotonic()+40
                while not info.exists() and time.monotonic()<deadline and proc.poll() is None: time.sleep(.05)
                assert info.exists(), 'collision provider failed to start'
                provider=json.loads(info.read_text())
                own=root/'coord/reports/.owners/mock'/f'{name}.own'
                if not own.exists(): own=root/'coord/reports'/f'{name}.own'  # baseline proof
                original=own.read_bytes(); n=calls()
                public={suffix:(root/'coord/reports'/f'{name}{suffix}').read_bytes() for suffix in ('.own','.pid')} if owner_mode=='1' else {}
                call('run','mock-2',name,code=2)
                check('account-refused same-task run preserves active ownership',own.exists() and own.read_bytes()==original and live(provider) and calls()==n)
                check('account refusal preserves public selection',all((root/'coord/reports'/f'{name}{suffix}').read_bytes()==raw for suffix,raw in public.items()))
                call('tier','medium')
                retry_path=root/'coord/retries'/name/'state.json'
                retry_state=state(name); retry_state['failed_attempts']=2
                retry_path.write_text(json.dumps(retry_state))
                refuse(name,'mock-2')
                check('retry-refused same-task run preserves active ownership',own.read_bytes()==original and live(provider))
                check('retry refusal preserves public selection',all((root/'coord/reports'/f'{name}{suffix}').read_bytes()==raw for suffix,raw in public.items()))
                task('parallel-other-'+owner_mode); call('run','mock-2','parallel-other-'+owner_mode,code=7)
                check('independent admitted task cannot reap active provider',own.read_bytes()==original and live(provider))
                call('allow-retry',name); call('run','mock-2',name,code=7)
                check('admitted same-task run cleans only its own provider',own.read_bytes()==original and live(provider))
                if owner_mode=='1':
                    # With two admitted background runs on one task, completion
                    # of the first must leave the second's selection untouched.
                    call('allow-retry',name); info.unlink()
                    with (base/'second.stdout').open('w') as out2, (base/'second.stderr').open('w') as err2:
                        second=subprocess.Popen([at,'run','mock-2',name],cwd=repo,
                                                env=dict(env,BRAKE_MOCK_MODE='hold',UNIO_TIMEOUT='120'),
                                                stdout=out2,stderr=err2,start_new_session=True)
                        second_shell=identity(second.pid); second_provider=None
                        try:
                            deadline=time.monotonic()+40
                            while not info.exists() and time.monotonic()<deadline and second.poll() is None: time.sleep(.05)
                            assert info.exists(), 'second collision provider failed to start'
                            second_provider=json.loads(info.read_text())
                            selected={suffix:(root/'coord/reports'/f'{name}{suffix}').read_bytes() for suffix in ('.own','.pid')}
                            signal_exact(shell,signal.SIGTERM); proc.wait(timeout=35)
                            check('first completion cannot remove or signal second background owner',
                                  live(second_provider) and all((root/'coord/reports'/f'{name}{suffix}').read_bytes()==raw for suffix,raw in selected.items()))
                            call('kill',name); second.wait(timeout=35)
                            check('public kill cancels only the selected background owner',second.returncode==143 and not live(second_provider))
                        finally:
                            if second.poll() is None: kill_fixture(second_shell,second_provider)
                            second.wait(timeout=5)
                else:
                    signal_exact(shell,signal.SIGTERM); proc.wait(timeout=35)
                check('active owner completes its own cancellation',proc.returncode==143 and not live(provider) and not own.exists())
            finally:
                signal_exact(shell,signal.SIGTERM)
                try: proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    kill_fixture(shell,provider); proc.wait(timeout=5)
                if provider is not None: signal_exact(provider,signal.SIGKILL)
            call('tier','low')
            if saved_mode is None: env.pop('UNIO_BG',None)
            else: env['UNIO_BG']=saved_mode

    ownership_collision('0')
    ownership_collision('1')

    task('process')
    call('run','mock','process',code=7); check('first real process exit preserved',state('process')['failed_attempts']==1)
    call('verify','mock','process',code=1)
    check('process plus failed verification counts once',state('process')['failed_attempts']==1)
    call('run','mock-2','process',code=7)
    check('failure history spans workers',state('process')['failed_attempts']==2)
    before=(root/'coord/reports/process.log').read_bytes()
    refuse('process')
    check('third attempt spends no quota or overwrites native log',before==(root/'coord/reports/process.log').read_bytes())
    call('allow-retry','process.md'); call('allow-retry','process')
    check('owner grants do not accumulate',state('process')['retry_granted'] is True)
    call('run','mock','process',code=7); refuse('process')
    check('one grant permits one attempt and preserves failures',state('process')['failed_attempts']==3 and not state('process')['retry_granted'])
    task('unrelated'); call('run','mock','unrelated',code=7)
    check('different task has its own counter',state('unrelated')['failed_attempts']==1)
    n=calls(); call('allow-retry','unrelated',code=2)
    check('grant before a block is refused without a provider',calls()==n)

    task('validation','$ false')
    call('run','mock','validation',mode='noop'); call('verify','mock','validation',code=1)
    call('verify','mock','validation',code=1)
    check('repeated verification counts one attempt',state('validation')['failed_attempts']==1)
    call('run','mock','validation',mode='noop'); call('verify','mock','validation',code=1); refuse('validation')
    check('two validation failures after exit zero block a third call',state('validation')['failed_attempts']==2)
    task('incomplete','')
    for _ in range(2):
        call('run','mock','incomplete',mode='work'); call('verify','mock','incomplete',code=2)
    refuse('incomplete'); check('incomplete verification brakes repeated unfinished work')
    call('allow-retry','process'); call('run','mock','process',mode='work'); call('verify','mock','process')
    refuse('process')
    check('successful granted attempt does not erase failed history',state('process')['failed_attempts']==3)

    for name, damage in [('malformed','json'),('symlink','link'),('bad-lock','fifo')]:
        task(name); d=root/'coord/retries'/name; d.mkdir()
        if damage=='json': (d/'state.json').write_text('{broken')
        if damage=='link': (d/'state.json').symlink_to(base/'private')
        if damage=='fifo': os.mkfifo(d/'lock')
        n=calls(); call('run','mock',name,code=2)
        check(name+' state refused before provider invocation',calls()==n)

    task('concurrent')
    call('run','mock','concurrent',code=7); call('run','mock-2','concurrent',code=7)
    call('allow-retry','concurrent'); n=calls()
    def compete(worker):
        p=subprocess.run([at,'run',worker,'concurrent'],cwd=repo,env=env,capture_output=True,timeout=45)
        assert p.returncode in (2,7),(worker,p.returncode,p.stdout,p.stderr)
        return p.returncode
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        codes=list(pool.map(compete,['mock','mock-2']))
    check('concurrent workers share a single retry grant',sorted(codes)==[2,7] and calls()==n+1)

    def interrupt(worker, name, during=None):
        if info.exists(): info.unlink()
        started=time.monotonic()
        proc=subprocess.Popen([at,'run',worker,name],cwd=repo,
                              env=dict(env,BRAKE_MOCK_MODE='hold',UNIO_TIMEOUT='120'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        shell=identity(proc.pid); provider=None
        output=errors=b''
        try:
            # Native startup includes a baseline save with its own 30s budget.
            # Allow preparation time without changing any interruption assertion.
            deadline=started+60
            while not info.exists() and time.monotonic()<deadline and proc.poll() is None: time.sleep(.05)
            assert info.exists(),f'mock did not start after {time.monotonic()-started:.3f}s; runner exit={proc.poll()}'
            print(f'  brake startup: {worker}/{name} ready in {time.monotonic()-started:.3f}s',flush=True)
            provider=json.loads(info.read_text())
            assert provider['sid']!=os.getsid(0)
            if during: during()
            kill_fixture(shell,provider)
            output,errors=proc.communicate(timeout=5)
        finally:
            if proc.poll() is None:
                kill_fixture(shell,provider); output,errors=proc.communicate(timeout=5)
            elif sys.exc_info()[0] is not None:
                output,errors=proc.communicate(timeout=5)
            if provider is not None: kill_fixture(shell,provider)
            if sys.exc_info()[0] is not None:
                print(f'  brake startup failure: {worker}/{name}; runner exit={proc.returncode}',file=sys.stderr,flush=True)
                for label,data in [('runner stdout',output),('runner stderr',errors)]:
                    print(label+':\n'+data.decode(errors='replace'),file=sys.stderr,flush=True)
                log=root/'coord/reports'/f'{name}.log'
                if log.exists():
                    print('native mock log:\n'+log.read_text(errors='replace'),file=sys.stderr,flush=True)
    task('interrupted')
    for _ in range(2): interrupt('mock','interrupted')
    refuse('interrupted')
    check('two interrupted starts block another invocation',state('interrupted')['failed_attempts']==2)
    check('interruption counter never invents a worker exit',json.loads(call('result','mock','interrupted').stdout)['process']['exit_code'] is None)
    task('reassigned')
    interrupt('mock','reassigned'); interrupt('mock-2','reassigned'); refuse('reassigned','mock-3')
    check('interrupted failures remain shared after task reassignment',state('reassigned')['failed_attempts']==2)
    check('reassignment never invents either worker exit',all(json.loads(call('result',w,'reassigned').stdout)['process']['exit_code'] is None for w in ('mock','mock-2')))
    task('active')
    # The 'active' scenario overlaps two workflows. Temporarily grant medium capacity
    # (cap2) so the second run returns expected failure (7) instead of refusal (2).
    call('tier', 'medium')
    def while_active():
        call('run','mock-2','active',code=7)
        check('held active worker is not counted as interrupted',state('active')['failed_attempts']==1 and state('active')['latest']['mock']['pending'])
    interrupt('mock','active',while_active)
    call('tier', 'low')
    refuse('active','mock-3')
    check('released interrupted worker then contributes to shared brake',state('active')['failed_attempts']==2)
    print(f'loop-brake regressions: {count} passed')
