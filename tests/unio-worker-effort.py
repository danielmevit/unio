#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed live effort client with native mocked run; zero actual AI calls."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile

spec=importlib.util.spec_from_file_location('smoke',Path(__file__).with_name('unio-codex-worker.py'))
smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)

def main():
    with tempfile.TemporaryDirectory(prefix='unio-effort-') as directory:
        h=smoke.Harness(directory)
        socket_fd=None
        try:
            result=json.loads(h.call('worker-effort','legacy','--json',code=2).stdout)
            assert result['state']=='unsupported' and not h.receipt.exists()
            for effort in ('max','ultra'):
                h.call('worker-effort','mock',effort,'--json',code=2)
            print('ok legacy/forbidden efforts refuse without launch',flush=True)
            h.start(extra={'FAKE_READ_ONLY':'1'})
            original=h.manifest.read_bytes()
            doc=json.loads(original)
            socket_path=Path(doc['socket'])
            socket_fd=os.open(socket_path.parent, os.O_RDONLY | os.O_DIRECTORY)
            socket_address=f'/proc/self/fd/{socket_fd}/{socket_path.name}'
            def raw(request):
                with socket.socket(socket.AF_UNIX) as conn:
                    conn.settimeout(20);conn.connect(socket_address);conn.sendall(request)
                    data=conn.recv(16384)
                    return json.loads(data)
            before=len(h.messages())
            for request in [b'{bad}\n', b'['*2000+b']'*2000+b'\n',json.dumps({'nonce':doc['nonce'],'model':'forbidden'}).encode()+b'\n',
                            json.dumps({'nonce':doc['nonce'],'threadId':'foreign','effort':'high'}).encode()+b'\n',
                            json.dumps({'nonce':'wrong','effort':'high'}).encode()+b'\n',b'x'*16385+b'\n']:
                assert raw(request)['state']=='rejected'
            assert len(h.messages())==before,'invalid control emitted provider RPC'
            result=h.effort('high')
            assert result['configured']=='high' and result['state']=='acknowledged' and result['pending_next_turn']
            print('ok malformed, overbound, forbidden settings, nonce validation; empty response + readback only',flush=True)
            # Two independent clients are serialized by the single backend event loop.
            import subprocess
            clients=[subprocess.Popen([h.unio,'worker-effort','mock',v,'--json'],cwd=h.repo,env=h.env,
                     stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True) for v in ('low','xhigh')]
            for p in clients:
                out,err=p.communicate(timeout=25)
                assert p.returncode==0,(out,err)
                assert json.loads(out)['state']=='acknowledged'
            updates=[m for m in h.messages() if m.get('method')=='thread/settings/update']
            assert len(updates)==3 and updates[0]['params']['effort']=='high'
            assert sorted(m['params']['effort'] for m in updates[1:])==['low','xhigh']
            assert len([m for m in h.messages() if m.get('method')=='turn/start'])==1
            print('ok serialized concurrent requests preserve single turn and native slot',flush=True)
            before=len(h.messages())
            # Replacing the inode, even with identical JSON, is not the owned endpoint.
            replacement=h.manifest.with_suffix('.replacement')
            replacement.write_bytes(original);replacement.chmod(0o600)
            saved=h.manifest.with_suffix('.saved');h.manifest.rename(saved);replacement.rename(h.manifest)
            assert h.effort('high',code=2)['state']=='rejected'
            assert len(h.messages())==before
            h.manifest.unlink();saved.rename(h.manifest)
            socket_path=Path(doc['socket']);socket_saved=socket_path.with_suffix('.saved')
            socket_path.rename(socket_saved)
            with socket.socket(socket.AF_UNIX) as replacement_socket:
                replacement_socket.bind(socket_address);socket_path.chmod(0o600);replacement_socket.listen(1)
                assert h.effort('high',code=2)['state']=='stale-or-invalid'
            socket_path.unlink();socket_saved.rename(socket_path)
            os.close(socket_fd);socket_fd=None
            for mutate in [lambda d:d.update(pid_stamp='stale'), lambda d:d.update(worker='other'),
                           lambda d:d.update(slot_inode=[0,0]), lambda d:d.update(holder_stamp='stale')]:
                changed=json.loads(original);mutate(changed);h.manifest.write_text(json.dumps(changed))
                assert h.effort('high',code=2)['state']=='stale-or-invalid'
            slot=Path(doc['slot']); parked=slot.with_suffix('.parked')
            slot_data=slot.read_bytes()
            slot.rename(parked);slot.write_bytes(slot_data);slot.chmod(0o600)
            assert h.effort('high',code=2)['state']=='stale-or-invalid'
            slot.unlink();parked.rename(slot)
            h.manifest.write_bytes(b'{' + b'x'*16384)
            assert h.effort(code=2)['state']=='stale-or-invalid'
            h.manifest.write_bytes(original)
            h.manifest.chmod(0o644)
            assert h.effort(code=2)['state']=='stale-or-invalid'
            h.manifest.chmod(0o600)
            h.manifest.unlink();h.manifest.symlink_to(saved)
            assert h.effort(code=2)['state']=='stale-or-invalid'
            h.manifest.unlink()
            # Restore ownership inode for cleanup.
            saved.write_bytes(original);saved.chmod(0o600);saved.rename(h.manifest)
            # This newly created manifest is deliberately replaced: backend must not unlink it.
            h.process.terminate();h.process.communicate(timeout=20)
            assert h.process.returncode==143
            assert h.manifest.exists()
            h.manifest.unlink()
            assert len(h.messages())==before
            assert not Path(doc['socket']).exists()
            print('ok stale/replaced/malformed/file-type/private-mode channels refuse with no provider effects',flush=True)
            h.start(extra={'FAKE_REJECT':'1'})
            result=h.effort('high',code=2)
            assert result['state']=='rejected' and not result['pending_next_turn']
            assert 'private provider error' not in json.dumps(result)
            h.terminate()
            print('ok provider RPC rejection preserved without raw payload or pending acknowledgement',flush=True)
            h.start(extra={'FAKE_DELAY_UPDATE':'1'})
            before=len([m for m in h.messages() if m.get('method')=='thread/settings/update'])
            pending=subprocess.Popen([h.unio,'worker-effort','mock','high','--json'],cwd=h.repo,env=h.env,
                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            import time
            deadline=time.monotonic()+5
            while len([m for m in h.messages() if m.get('method')=='thread/settings/update'])==before and time.monotonic()<deadline:
                time.sleep(.05)
            assert len([m for m in h.messages() if m.get('method')=='thread/settings/update'])==before+1
            h.terminate()
            out,err=pending.communicate(timeout=20)
            assert pending.returncode==2,(out,err)
            print('ok cancellation during active effort RPC reaps backend/provider and preserves 143',flush=True)
        finally:
            if socket_fd is not None:
                os.close(socket_fd)
            if h.process is not None and h.process.poll() is None:
                h.process.terminate()
                h.process.communicate(timeout=25)

if __name__=='__main__':main()
