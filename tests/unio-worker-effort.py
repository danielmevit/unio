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
import subprocess
from types import SimpleNamespace
from unittest.mock import patch
from copy import deepcopy

spec=importlib.util.spec_from_file_location('smoke',Path(__file__).with_name('unio-codex-worker.py'))
smoke=importlib.util.module_from_spec(spec);spec.loader.exec_module(smoke)

def audit_validator_checks(base):
    """Reach the helper's native-evidence validator without a provider or delay."""
    spec = importlib.util.spec_from_file_location('effort_worker', smoke.SOURCE / 'tools/codex-worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    project = base / 'audit-project'
    project.mkdir()
    conf = base / 'audit-conf'
    conf.mkdir()
    (conf / 'agents.conf').write_text('legacy=codex exec -c model_reasoning_effort=medium\n')
    args = SimpleNamespace(worker='legacy-17', project=str(project))
    row = dict(alias='legacy', tool='codex', requested_model='gpt-6.1-sol',
               requested_effort='medium', transport='stdin', authentication='Unknown',
               capacity='Unknown', effective_model='Unknown', effective_effort='Unknown', issues=[])
    audit = dict(schema_version=1, source='local_static', authentication='Unknown',
                 capacity='Unknown', effective_model='Unknown', effective_effort='Unknown', agents=[row])
    def invoke(payload, status=0, timeout=False):
        def fake_run(argv, **kwargs):
            assert argv == ['offline-audit-fixture', 'doctor', '--commands', '--json']
            assert kwargs['cwd'] == str(project) and kwargs['timeout'] == 15
            assert kwargs['stderr'] == subprocess.DEVNULL
            if timeout:
                raise subprocess.TimeoutExpired(argv, kwargs['timeout'])
            kwargs['stdout'].write(payload)
            return SimpleNamespace(returncode=status)
        with patch.dict(os.environ, {'UNIO_CONF_DIR': str(conf), 'UNIO_EFFORT_CLI': 'offline-audit-fixture'}), \
                patch.object(worker.subprocess, 'run', side_effect=fake_run) as run:
            result = worker.effort_info_audit(args)
            assert run.call_count == 1
            return result
    valid = json.dumps(audit).encode()
    accepted = invoke(valid)
    assert accepted['requested_effort'] == 'medium' and accepted['reason'] is None
    assert accepted['alias'] == 'legacy' and accepted['scope'] == 'future_launch'
    invalid = [b'{bad', b'[' * 2000 + b']' * 2000, b' ' * 131073]
    for change in ('extra', 'bool_schema', 'invalid_row', 'duplicate_alias'):
        doc = deepcopy(audit)
        if change == 'extra': doc['extra'] = True
        elif change == 'bool_schema': doc['schema_version'] = True
        elif change == 'invalid_row': doc['agents'][0]['requested_effort'] = True
        else: doc['agents'].append(deepcopy(row))
        invalid.append(json.dumps(doc).encode())
    for payload, status, timeout in [(v, 0, False) for v in invalid] + [(valid, 7, False), (valid, 0, True)]:
        result = invoke(payload, status, timeout)
        assert result['reason'] == 'invalid_agents_conf', result
        assert all(result[k] == 'Unknown' for k in ('tool', 'requested_model', 'requested_effort'))
    with patch.dict(os.environ, {'UNIO_CONF_DIR': str(conf), 'UNIO_EFFORT_CLI': ''}), \
            patch.object(worker.subprocess, 'run', side_effect=AssertionError('no CLI evidence')):
        result = worker.effort_info_audit(args)
        assert result['reason'] == 'static_evidence_unavailable'
        assert result['requested_effort'] == 'Unknown'
    print('ok direct native audit validator: status, bounds, JSON/schema/rows, duplicate, absent CLI and mocked timeout', flush=True)


def isolated_native_home_checks(h):
    # HOME is overridden only in child environments, never in this process.
    home = h.base / 'isolated-home'
    conf = home / '.config/unio'
    conf.mkdir(parents=True)
    (conf / 'agents.conf').write_text('legacy=codex exec -c model_reasoning_effort=medium - < "$TASKFILE"\n')
    script = ("import importlib.util,json; from types import SimpleNamespace; "
              "s=importlib.util.spec_from_file_location('worker'," + repr(str(h.helper)) + "); "
              "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
              "print(json.dumps(m.effort_info_audit(SimpleNamespace(worker='legacy',project=" + repr(str(h.root)) + "))))")
    def query(value):
        env = dict(h.env, HOME=str(home), UNIO_EFFORT_CLI=h.unio)
        if value is None: env.pop('UNIO_CONF_DIR', None)
        else: env['UNIO_CONF_DIR'] = value
        p = subprocess.run(['python3', '-B', '-c', script], cwd=h.repo, env=env,
                           capture_output=True, text=True, timeout=20)
        assert p.returncode == 0, p.stderr
        return json.loads(p.stdout)
    unset = query(None)
    assert unset == query('')
    assert unset['requested_effort'] == 'medium' and unset['reason'] is None, unset
    project_conf = h.root / 'coord/agents.conf'
    assert not project_conf.exists()
    try:
        project_conf.write_text('legacy=codex exec -c model_reasoning_effort=low - < "$TASKFILE"\n')
        assert query('')['requested_effort'] == 'low'
        project_conf.write_text('legacy=codex exec "unterminated\n')
        malformed = query('')
        assert malformed['requested_effort'] == 'Unknown'
        assert malformed['reason'] == 'invalid_agents_conf', malformed
    finally:
        project_conf.unlink()
    print('ok isolated native homes: empty/unset default, project precedence and malformed agents.conf Unknown', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='unio-effort-') as directory:
        h=smoke.Harness(directory)
        audit_validator_checks(h.base)
        isolated_native_home_checks(h)
        socket_fd=None
        try:
            result=json.loads(h.call('worker-effort','legacy','--json',code=2).stdout)
            assert result['state']=='unsupported' and not h.receipt.exists()
            for effort in ('max','ultra'):
                h.call('worker-effort','mock',effort,'--json',code=2)
            print('ok legacy/forbidden efforts refuse without launch',flush=True)
            for option in ('--sandbox','--approval-policy','--model','--permissions','--service-tier'):
                h.call('worker-effort','mock','high',option,'never','--json',code=2)
            assert not h.receipt.exists()
            conf_path = h.base / 'conf/agents.conf'
            conf_backup = conf_path.read_text()
            # 1. Literal legacy medium startup config with unavailable live channel:
            conf_path.write_text('legacy=codex exec -c model_reasoning_effort="medium" - < "$TASKFILE"\n')
            r_med = json.loads(h.call('worker-effort','legacy','--json',code=2).stdout)
            assert r_med['state'] == 'unsupported'
            assert r_med['live_control'] == 'unsupported'
            assert r_med['channel'] == 'none'
            assert r_med['effective'] == 'Unknown'
            assert r_med['worker'] == 'legacy'
            assert r_med['current_configuration']['provenance'] == 'static_agents_conf'
            assert r_med['current_configuration']['scope'] == 'future_launch'
            assert r_med['current_configuration']['requested_effort'] == 'medium'
            assert r_med['current_configuration']['tool'] == 'codex'
            assert r_med['current_configuration']['reason'] is None
            # Argparse, rather than argv[0], determines the worker at every option order.
            for argv in [('--json', 'legacy'), ('legacy-17', '--json'), ('--json', 'legacy-17')]:
                reordered = json.loads(h.call('worker-effort', *argv, code=2).stdout)
                assert reordered['current_configuration'] == r_med['current_configuration']
                assert reordered['worker'] == next(v for v in argv if v != '--json')
            assert json.loads(h.call('worker-effort', '--json', 'absent-17', code=2).stdout)['current_configuration']['reason'] == 'missing_alias'
            h.call('worker-effort', '--json', code=2)  # missing positional remains argparse failure
            # Internal evidence cannot be injected by callers, even when shaped like a handoff.
            sentinel = 'sk-secret-audit-override-998877'
            for payload in ['{bad', '[' * 2000, 'x' * 20000,
                            json.dumps({'found': True, 'alias': 'legacy', 'tool': sentinel,
                                        'requested_effort': 'high', 'requested_model': sentinel}),
                            json.dumps({'found': [], 'requested_effort': {'secret': sentinel}}),
                            json.dumps({'found': True, 'unsupported': sentinel}),
                            json.dumps({'found': True, 'alias': 'legacy', 'tool': 'codex',
                                        'requested_model': 'gpt-6.1-sol', 'requested_effort': 'high',
                                        'issues': [], 'reason': None})]:
                refused = h.call('worker-effort', '--json', 'legacy', '--audit-json', payload, code=2)
                assert not refused.stdout
                assert '--audit-json is not accepted from callers' in refused.stderr
                assert sentinel not in refused.stderr and payload not in refused.stderr
            assert not h.receipt.exists()
            # Human presentation check:
            human = h.call('worker-effort','legacy',code=2).stdout
            assert 'worker=legacy state=unsupported live_control=unsupported channel=none effective=Unknown' in human
            assert 'current_configuration: effort=medium' in human
            assert 'provenance=static_agents_conf' in human
            assert 'scope=future_launch' in human
            assert 'model reasoning effort, distinct from coordination tier and review pace' in human

            # 2. Config changed after a frozen request (correct current/future label):
            conf_path.write_text('legacy=codex exec -c model_reasoning_effort=low - < "$TASKFILE"\n')
            r_changed = json.loads(h.call('worker-effort','legacy','--json',code=2).stdout)
            assert r_changed['current_configuration']['requested_effort'] == 'low'
            assert r_changed['current_configuration']['scope'] == 'future_launch'
            assert r_changed['current_configuration']['provenance'] == 'static_agents_conf'

            # 3. Missing alias / missing config:
            r_noalias = json.loads(h.call('worker-effort','unconfigured','--json',code=2).stdout)
            assert r_noalias['state'] == 'unsupported'
            assert r_noalias['current_configuration']['requested_effort'] == 'Unknown'
            assert r_noalias['current_configuration']['reason'] == 'missing_alias'
            # Missing config file:
            saved_conf = conf_path.with_suffix('.bak')
            conf_path.rename(saved_conf)
            r_noconf = json.loads(h.call('worker-effort','legacy','--json',code=2).stdout)
            assert r_noconf['state'] == 'unsupported'
            assert r_noconf['current_configuration']['requested_effort'] == 'Unknown'
            assert r_noconf['current_configuration']['reason'] == 'missing_agents_conf'
            saved_conf.rename(conf_path)

            # 4. Conflicting selectors:
            conf_path.write_text('legacy=codex exec -c model_reasoning_effort=high -c model_reasoning_effort=low - < "$TASKFILE"\n')
            r_conflict = json.loads(h.call('worker-effort','legacy','--json',code=2).stdout)
            assert r_conflict['state'] == 'unsupported'
            assert r_conflict['current_configuration']['requested_effort'] == 'Unknown'
            assert r_conflict['current_configuration']['reason'] == 'effort_ambiguous'

            # 5. Malicious shell/wrapper/secret values with zero execution and no secret reflection:
            secret = "sk-priv-token-99887766"
            conf_path.write_text(f'legacy=codex exec --model "{secret}" --api-key "{secret}" $(echo inject) - < "$TASKFILE"\n')
            r_sec = h.call('worker-effort','legacy','--json',code=2)
            assert secret not in r_sec.stdout and secret not in r_sec.stderr
            sec_doc = json.loads(r_sec.stdout)
            assert sec_doc['state'] == 'unsupported'
            assert sec_doc['current_configuration']['requested_effort'] == 'Unknown'
            assert sec_doc['current_configuration']['reason'] == 'command_unknown'
            r_sec_h = h.call('worker-effort','legacy',code=2)
            assert secret not in r_sec_h.stdout and secret not in r_sec_h.stderr

            # 6. Auto Balance Unknown:
            conf_path.write_text('cop=copilot -m auto-balance < "$TASKFILE"\n')
            r_auto = json.loads(h.call('worker-effort','cop','--json',code=2).stdout)
            assert r_auto['state'] == 'unsupported'
            assert r_auto['current_configuration']['requested_effort'] == 'Unknown'
            assert r_auto['current_configuration']['reason'] == 'auto_balance'

            # 7. STOP / query behavior:
            (h.root / 'coord/STOP').write_text('frozen STOP\n')
            r_stop = json.loads(h.call('worker-effort','cop','--json',code=2).stdout)
            assert r_stop['state'] == 'unsupported'
            assert json.loads(h.call('worker-effort','--json','cop',code=2).stdout) == r_stop
            assert (h.root / 'coord/STOP').read_text() == 'frozen STOP\n'
            (h.root / 'coord/STOP').unlink()

            # 8. Unsupported set unchanged/nonzero (cannot edit config):
            conf_path.write_text('legacy=codex exec -c model_reasoning_effort=medium - < "$TASKFILE"\n')
            r_set = json.loads(h.call('worker-effort','legacy','high','--json',code=2).stdout)
            assert json.loads(h.call('worker-effort','--json','legacy','high',code=2).stdout) == r_set
            assert r_set['state'] == 'unsupported'
            assert r_set['live_control'] == 'unsupported'
            assert 'model_reasoning_effort=medium' in conf_path.read_text()

            # Restore original agents.conf:
            conf_path.write_text(conf_backup)
            print('ok read-only effort clarity, provenance, fallback, bounds and safety verified',flush=True)
            h.start(extra={'FAKE_READ_ONLY':'1'})
            native = json.loads(h.call('worker-effort', '--json', 'mock').stdout)
            conventional = json.loads(h.call('worker-effort', 'mock', '--json').stdout)
            assert native == conventional and 'current_configuration' not in native
            assert native['effective'] == 'Unknown'
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
            for key in ('sandbox','approvalPolicy','approval_policy','permissions','serviceTier'):
                request=json.dumps({'nonce':doc['nonce'],'effort':'high',key:'never'}).encode()+b'\n'
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
            assert all(set(m['params'])=={'threadId','effort'} for m in updates)
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
