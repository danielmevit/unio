#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed native managed Source smoke checks; deterministic, zero AI calls."""
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import tempfile
import time

SOURCE = Path(__file__).resolve().parents[1]
FAKE = r'''#!/usr/bin/env python3
import json, os, select, signal, sys, time
from pathlib import Path
assert sys.argv[1:] == ['app-server', '--listen', 'stdio://']
receipt = Path(os.environ['FAKE_RECEIPT'])
with receipt.open('a') as f: f.write(json.dumps({'launch': os.getpid()})+'\n')
effort = 'low'
started = False
def emit(v): print(json.dumps(v), flush=True)
for line in sys.stdin:
    msg = json.loads(line)
    with receipt.open('a') as f: f.write(json.dumps(msg)+'\n')
    method = msg.get('method')
    if method == 'initialized': continue
    if method == 'initialize': result = {}
    elif method == 'account/read': result = {'account':{'type':os.environ.get('FAKE_AUTH','chatgpt')}}
    elif method == 'model/list': result = {'data':[{'id':os.environ.get('FAKE_MODEL','test-sol'),'model':os.environ.get('FAKE_MODEL','test-sol'),'supportedReasoningEfforts':[{'reasoningEffort':v} for v in ['low','high','xhigh','ultra']]}]}
    elif method == 'thread/start': result = {'thread':{'id':'private-thread','reasoningEffort':effort}}
    elif method == 'turn/start':
        assert not started
        started = True
        assert msg['params']['effort'] == 'low'
        assert 'NATIVE-TASK-SENTINEL' in msg['params']['input'][0]['text']
        Path('task-output.txt').write_text('useful edit\n')
        result = {'turn':{'id':'one-turn'}}
        emit({'id':msg['id'],'result':result})
        emit({'method':'item/agentMessage/delta','params':{'threadId':'private-thread','delta':'worker streamed useful output\n'}})
        mode = os.environ.get('FAKE_MODE','hold')
        if mode == 'exit': sys.exit(7)
        if mode == 'failed':
            emit({'method':'turn/completed','params':{'threadId':'private-thread','turn':{'id':'one-turn','status':'failed'}}})
        if mode == 'success':
            emit({'method':'turn/completed','params':{'threadId':'private-thread','turn':{'id':'one-turn','status':'completed'}}})
        continue
    elif method == 'thread/settings/update':
        assert set(msg['params']) == {'threadId','effort'}
        assert msg['params']['threadId'] == 'private-thread'
        if os.environ.get('FAKE_REJECT'):
            emit({'id':msg['id'],'error':{'code':-32601,'message':'private provider error'}}); continue
        if os.environ.get('FAKE_DELAY_UPDATE'): time.sleep(10)
        effort = msg['params']['effort']
        emit({'method':'item/agentMessage/delta','params':{'threadId':'private-thread','delta':'interleaved output\n'}})
        emit({'method':'thread/settings/updated','params':{'threadId':'foreign-thread','threadSettings':{'effort':'xhigh'}}})
        if not os.environ.get('FAKE_READ_ONLY'):
            emit({'method':'thread/settings/updated','params':{'threadId':'private-thread','threadSettings':{'effort':effort}}})
        result = {}
    elif method == 'thread/read': result = {'thread':{'reasoningEffort':effort}}
    else: raise AssertionError(method)
    emit({'id':msg['id'],'result':result})
'''

class Harness:
    def __init__(self, directory, documented=False, startup=()):
        self.worker = 'codexmanaged' if documented else 'mock'
        self.base = Path(directory)
        self.root = self.base / 'project with spaces'
        self.repo = self.root / 'repo'
        self.repo.mkdir(parents=True)
        self.receipt = self.base / 'rpc.jsonl'
        fake = self.base / 'fake-bin'
        fake.mkdir()
        (fake / 'codex').write_text(FAKE)
        (fake / 'codex').chmod(0o755)
        self.env = dict(os.environ, UNIO_BIN_DIR=str(self.base/'bin'), UNIO_CONF_DIR=str(self.base/'conf'),
            UNIO_COMPLETION_DIR=str(self.base/'completion'), UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0',
            UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='180', FAKE_RECEIPT=str(self.receipt),
            GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock', GIT_AUTHOR_EMAIL='mock@example.invalid',
            GIT_COMMITTER_EMAIL='mock@example.invalid', PATH=str(fake)+os.pathsep+os.environ['PATH'])
        # A suite launched inside managed Source must not inherit its admission.
        for key in list(self.env):
            if key.startswith('UNIO_CODEX_'):
                self.env.pop(key)
        for key in ('OPENAI_API_KEY', 'CODEX_API_KEY'):
            self.env.pop(key, None)
        subprocess.run(['bash',str(SOURCE/'unio-install.sh')],env=self.env,check=True,capture_output=True)
        self.unio = str(self.base/'bin/unio')
        self.helper = self.base/'conf/lib/codex-worker.py'
        assert self.helper.read_bytes() == (SOURCE/'tools/codex-worker.py').read_bytes()
        # Test configuration only: same real native account route, mocked provider.
        (self.base/'conf/agents.conf').write_text('mock=python3 -I -S -B "$UNIO_CONF_DIR/lib/codex-worker.py" run --model test-sol --effort low\nlegacy=true\ncodex=true\n')
        if documented:
            guide=(self.base/'conf/lib/WORKER-EFFORT.md').read_text()
            entry=next(line for line in guide.splitlines() if line.startswith('codexmanaged='))
            with (self.base/'conf/agents.conf').open('a') as config:
                config.write(entry+'\n')
            self.env['FAKE_MODEL']='gpt-6.1-sol'
        if startup:
            config = self.base/'conf/agents.conf'
            text = config.read_text()
            text = text.replace('--effort low', '--effort low ' + ' '.join(startup))
            config.write_text(text)
        for args in [('init','-q','-b','main'),('config','user.name','mock'),('config','user.email','mock@example.invalid')]:
            subprocess.run(['git',*args],cwd=self.repo,env=self.env,check=True,capture_output=True)
        (self.repo/'seed').write_text('seed')
        for args in [('add','seed'),('commit','-qm','seed')]:
            subprocess.run(['git',*args],cwd=self.repo,env=self.env,check=True,capture_output=True)
        self.call('init',self.worker,'legacy')
        self.call('account',self.worker,'codex')
        self.call('account','legacy','codex')
        self.call('tier','medium')
        self.call('lead','codex')
        self.manifest = self.root/('coord/.locks/codex-worker-'+self.worker+'.json')
        self.process = None
        self.task = 0

    def call(self,*args,code=0):
        result = subprocess.run([self.unio,*args],cwd=self.repo,env=self.env,capture_output=True,text=True,timeout=35)
        assert result.returncode == code, (args,result.returncode,result.stdout[-2500:],result.stderr[-2500:])
        return result

    def start(self,mode='hold',extra=None,timeout='180'):
        self.task += 1
        name = 'TASK-'+str(self.task)
        (self.root/'coord/tasks'/ (name+'.md')).write_text('# Task\nNATIVE-TASK-SENTINEL\n## Allowed scope\n- task-output.txt\n## Validate\n$ test -f task-output.txt\n')
        # Task contents and route settings are frozen before native owner consent.
        # Each start needs a fresh one-use grant, including failed provider starts.
        self.call('lead-budget','grant',self.worker,self.worker,name,'run')
        self.process = subprocess.Popen([self.unio,'run',self.worker,name],cwd=self.repo,
            env=dict(self.env,FAKE_MODE=mode,UNIO_TIMEOUT=timeout,**(extra or {})),stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        if mode == 'hold':
            deadline=time.monotonic()+12
            while not self.manifest.exists() and time.monotonic()<deadline and self.process.poll() is None:
                time.sleep(.05)
            assert self.manifest.exists(), self.process.communicate(timeout=5)
            self.effort()  # Socket reserved before startup; wait for actual ready RPC.
        return name

    def finish(self,code=None):
        out,err=self.process.communicate(timeout=20)
        if code is not None:
            assert self.process.returncode == code,(self.process.returncode,out[-3000:],err[-3000:])
        assert not self.manifest.exists(), 'owned manifest left behind'
        slots=list((self.root/'coord/.locks/work-policy-slots').rglob('wpslot-*.json'))
        assert not slots, slots
        return out,err

    def effort(self,level=None,code=0):
        args=['worker-effort',self.worker]+([level] if level else [])+['--json']
        return json.loads(self.call(*args,code=code).stdout)

    def messages(self):
        return [json.loads(line) for line in self.receipt.read_text().splitlines()]

    def terminate(self):
        self.process.send_signal(signal.SIGTERM)
        self.finish(143)


def repeated_cancellation(h):
    # Deliver the second forwarded signal at the cleanup-entry window instead
    # of depending on native timeout/supervisor scheduling to hit that window.
    check = r'''
import json, os, runpy, signal, socket, sys
from pathlib import Path
from types import SimpleNamespace
backend = runpy.run_path(sys.argv[1])
server = backend['Server'](SimpleNamespace(effort='low'))
server.directory = Path(sys.argv[2]) / 'duplicate-cancel'
server.directory.mkdir(mode=0o700)
server.listener = socket.socket(socket.AF_UNIX)
directory_fd = os.open(server.directory, os.O_RDONLY | os.O_DIRECTORY)
try:
    server.listener.bind(f'/proc/self/fd/{directory_fd}/control.sock')
finally:
    os.close(directory_fd)
server.manifest = server.directory / 'manifest.json'
server.manifest.write_text('{}')
server.manifest.chmod(0o600)
server.manifest_inode = backend['read_private'](server.manifest)[1]
signal.signal(signal.SIGTERM, server.stop)
signal.signal(signal.SIGINT, server.stop)
original = signal.signal
def before_ignore(number, handler):
    if number == signal.SIGTERM and handler == signal.SIG_IGN:
        os.kill(os.getpid(), signal.SIGTERM)
        os.kill(os.getpid(), signal.SIGINT)
    return original(number, handler)
signal.signal = before_ignore
try:
    os.kill(os.getpid(), signal.SIGTERM)
except backend['Cancelled']:
    pass
finally:
    server.close()
assert server.stop_code == 143
assert not server.manifest.exists()
assert not server.directory.exists()
sys.exit(server.stop_code)
'''
    result = subprocess.run(['python3', '-I', '-S', '-B', '-c', check, str(h.helper), str(h.base)],
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 143, (result.returncode, result.stdout, result.stderr)
    assert not (h.base / 'duplicate-cancel').exists()
    print('ok repeated TERM/INT at cleanup entry preserves first exit143 and removes owned channel', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='unio-documented-') as directory:
        h=Harness(directory, documented=True)
        try:
            repeated_cancellation(h)
            name=h.start()
            doc=json.loads(h.manifest.read_text())
            assert doc['worker']=='codexmanaged' and doc['task']==name
            assert Path(doc['slot']).parent.name=='codex'
            messages=h.messages()
            assert len([m for m in messages if 'launch' in m])==1
            turn=next(m for m in messages if m.get('method')=='turn/start')
            thread=next(m for m in messages if m.get('method')=='thread/start')
            assert thread['params']['model']=='gpt-6.1-sol' and turn['params']['effort']=='low'
            assert 'sandbox' not in thread['params'] and 'approvalPolicy' not in thread['params']
            # The real shared group retains its lead reservation: a second worker refuses.
            (h.root/'coord/tasks/OTHER.md').write_text('NATIVE-TASK-SENTINEL')
            h.call('lead-budget','grant','legacy','legacy','OTHER','run')
            denied=h.call('run','legacy','OTHER',code=2)
            assert 'budget refused' in denied.stderr
            grants=json.loads((h.root/'coord/lead-budget.json').read_text())['grants']
            assert grants[-1]['state']=='ready', 'capacity refusal consumed owner consent'
            assert len([m for m in h.messages() if 'launch' in m])==1
            h.terminate()
            print('ok installed documented config/account/init/run reaches managed backend in shared codex group with lead reservation',flush=True)
        finally:
            if h.process is not None and h.process.poll() is None:
                h.process.terminate();h.process.communicate(timeout=25)
    with tempfile.TemporaryDirectory(prefix='unio-codex-') as directory:
        h=Harness(directory)
        try:
            denied=subprocess.run(['python3','-I','-S','-B',str(h.helper),'run','--model','test-sol','--effort','low'],env=h.env,capture_output=True)
            assert denied.returncode == 2 and not h.receipt.exists()
            print('ok unmanaged start rejected without provider',flush=True)
            for option, value in [('--sandbox','invalid'), ('--approval-policy','on-failure'),
                                  ('--approval-policy','{"granular":{}}')]:
                denied=subprocess.run(['python3','-I','-S','-B',str(h.helper),'run',
                    '--model','test-sol','--effort','low',option,value],env=h.env,capture_output=True)
                assert denied.returncode == 2 and not h.receipt.exists()
            print('ok invalid startup choices refuse before provider invocation',flush=True)
            custom_tmp=h.base/('caller TMPDIR '+ 'x'*90);custom_tmp.mkdir()
            name=h.start(extra={'TMPDIR':str(custom_tmp)})
            doc=json.loads(h.manifest.read_text()); provider=h.messages()[0]['launch']
            assert doc['worker']=='mock' and doc['task']==name
            assert Path(doc['socket']).parent.parent==custom_tmp and len(doc['socket'].encode())>108
            assert Path(doc['slot']).parent.name=='codex'
            alternate=h.root/'coord/tasks/OTHER.md';alternate.write_text('NATIVE-TASK-SENTINEL')
            h.call('lead-budget','grant','legacy','legacy','OTHER','run')
            denied=h.call('run','legacy','OTHER',code=2)
            assert 'budget refused' in denied.stderr
            grants=json.loads((h.root/'coord/lead-budget.json').read_text())['grants']
            assert grants[-1]['state']=='ready', 'capacity refusal consumed owner consent'
            assert len([m for m in h.messages() if 'launch' in m])==1
            thread=next(m for m in h.messages() if m.get('method')=='thread/start')
            assert 'sandbox' not in thread['params'] and 'approvalPolicy' not in thread['params']
            result=h.effort()
            assert result['supported']==['low','high','xhigh'] and result['effective']=='Unknown'
            result=h.effort('high')
            assert result['state']=='acknowledged' and result['configured']=='high' and result['pending_next_turn']
            assert result['effective']=='Unknown'
            assert len([m for m in h.messages() if m.get('method')=='turn/start'])==1
            assert len([m for m in h.messages() if 'launch' in m])==1
            assert h.effort('medium',code=2)['state']=='rejected'
            log=(h.root/'coord/reports'/ (name+'.log')).read_text()
            assert 'worker streamed useful output' in log and 'interleaved output' in log
            assert (h.root/'wt/mock/task-output.txt').read_text()=='useful edit\n'
            h.terminate()
            assert not Path('/proc',str(provider)).exists()
            assert not Path(doc['socket']).exists()
            print('ok native slot/task, task edit, streaming, empty response + notification/readback, one turn, cancellation cleanup',flush=True)
            name=h.start('success'); h.finish(0)
            assert json.loads(h.call('result','mock',name).stdout)['process']['exit_code']==0
            for mode,code in [('failed',1),('exit',7)]:
                name=h.start(mode);h.finish(code)
                assert json.loads(h.call('result','mock',name).stdout)['process']['exit_code']==code
            print('ok native success and real failed provider exits preserved',flush=True)
            h.start(timeout='2'); h.finish(124)
            print('ok native timeout cleanup preserves 124',flush=True)
            before=len(h.messages())
            h.manifest.write_text('{}');h.manifest.chmod(0o600)
            h.start('blocked');h.process.communicate(timeout=20)
            assert h.process.returncode==2 and len(h.messages())==before
            assert h.manifest.read_text()=='{}'
            h.manifest.unlink()
            name=h.start('blocked',extra={'FAKE_AUTH':'apiKey'});h.finish(2)
            recent=h.messages()[before:]
            assert len([m for m in recent if 'launch' in m])==1
            assert not any(m.get('method')=='turn/start' for m in recent)
            before=len(h.messages())
            h.start('blocked',extra={'OPENAI_API_KEY':'test-only-forbidden'});h.finish(2)
            assert len(h.messages())==before
            (h.root/'coord/STOP').touch()
            h.start('blocked');h.finish(1)
            assert len(h.messages())==before
            print('ok stale startup, API authentication, key environment and STOP refuse before task invocation',flush=True)
        finally:
            if h.process is not None and h.process.poll() is None:
                h.process.terminate()
                h.process.communicate(timeout=25)

    for sandbox, approval in [('read-only','untrusted'), ('workspace-write','on-request'),
                              ('danger-full-access','never'), ('workspace-write',None), (None,'never')]:
        options = (['--sandbox',sandbox] if sandbox else []) + (['--approval-policy',approval] if approval else [])
        with tempfile.TemporaryDirectory(prefix='unio-startup-') as directory:
            h=Harness(directory,startup=options)
            try:
                h.start()
                h.effort('high')
                messages=h.messages()
                threads=[m for m in messages if m.get('method')=='thread/start']
                assert len(threads)==1
                params=threads[0]['params']
                for key,value in [('sandbox',sandbox),('approvalPolicy',approval)]:
                    if value is None:
                        assert key not in params
                    else:
                        assert params[key]==value
                    assert not any(key in m.get('params',{}) for m in messages if m not in threads)
                assert len([m for m in messages if m.get('method')=='turn/start'])==1
                h.terminate()
                print('ok explicit startup choices confined to one thread/start:',sandbox,approval,flush=True)
            finally:
                if h.process is not None and h.process.poll() is None:
                    h.process.terminate();h.process.communicate(timeout=25)

if __name__=='__main__': main()
