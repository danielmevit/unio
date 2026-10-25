#!/usr/bin/env python3
"""Offline installed phase ordering plus isolated broken-diagnostic regression."""
import contextlib
import io
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import tempfile
import types
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='unio-run-phases-') as temporary:
    base = Path(temporary)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='30',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    for key in ('UNIO_SAVE_TEST_FAULT', 'UNIO_SAVE_CAPTURE_TIMEOUT', 'BASH_ENV'):
        env.pop(key, None)
    subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env, check=True, capture_output=True)
    at = str(base / 'bin' / 'unio')
    repo = base / 'project' / 'repo'
    repo.mkdir(parents=True)

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, env=env, check=True, capture_output=True)

    def unio(*args, extra=None):
        return subprocess.run([at, *args], cwd=repo, env=dict(env, **(extra or {})),
                              text=True, capture_output=True, timeout=60)

    def good(result):
        assert result.returncode == 0, result.stdout + result.stderr

    git('init', '-q', '-b', 'main')
    (repo / 'tracked').write_text('base\n')
    git('add', 'tracked')
    git('commit', '-qm', 'base')
    good(unio('init', 'mock-order', 'mock-failure', 'mock-refused'))
    coord = repo.parent / 'coord'
    for worker in ('mock-order', 'mock-failure', 'mock-refused'):
        (coord / 'tasks' / (worker + '.md')).write_text('# Offline phase fixture\n')
    calls = base / 'calls'
    provider = base / 'provider.py'
    provider.write_text('from pathlib import Path\n'
                        + 'with Path(' + repr(str(calls)) + ").open('a') as out: out.write('called\\n')\n"
                        + "print('provider-only')\nraise SystemExit(23)\n")
    (base / 'conf' / 'agents.conf').write_text('mock=python3 -B ' + shlex.quote(str(provider)) + '\n')
    good(unio('resume'))
    # A Unix socket handshake blocks the real baseline Git helper until the
    # parent has inspected diagnostics. No elapsed delay establishes success.
    listener = socket.socket(socket.AF_UNIX)
    endpoint = '\0unio-run-phases-' + str(os.getpid())
    listener.bind(endpoint)
    listener.listen(1)
    listener.settimeout(25)
    shim_dir = base / 'shim'
    shim_dir.mkdir()
    shim = shim_dir / 'git'
    real_git = shutil.which('git')
    shim.write_text('#!/usr/bin/env python3\nimport os,socket,sys\nfrom pathlib import Path\n'
                    + "if '--show-object-format' in sys.argv and b'_supervise' in Path('/proc/%s/cmdline' % os.getppid()).read_bytes() and not os.path.exists(" + repr(str(base / 'claimed')) + '):\n'
                    + ' open(' + repr(str(base / 'claimed')) + ", 'w').close()\n"
                    + ' s=socket.socket(socket.AF_UNIX); s.connect(' + repr(endpoint) + "); s.sendall(b'baseline'); assert s.recv(1)==b'G'; s.close()\n"
                    + 'os.execv(' + repr(real_git) + ", ['git', *sys.argv[1:]])\n")
    shim.chmod(0o755)
    err = base / 'stderr'
    active = None
    try:
        with err.open('w') as stderr:
            active = subprocess.Popen([at, 'run', 'mock-order', 'mock-order'], cwd=repo,
                                      env=dict(env, PATH=str(shim_dir) + os.pathsep + env['PATH']),
                                      stdout=subprocess.DEVNULL, stderr=stderr)
            connection, _ = listener.accept()
            with connection:
                connection.settimeout(5)
                assert connection.recv(8) == b'baseline'
                before = err.read_text()
                assert 'unio: phase checkpoint attempt started checkpoint=baseline budget=30s' in before, before
                assert 'provider launch' not in before and not calls.exists()
                connection.sendall(b'G')
            assert active.wait(timeout=30) == 23
        phases = err.read_text()
        ordered = ['checkpoint attempt started checkpoint=baseline', 'checkpoint attempt ended checkpoint=baseline',
                   'provider launch starting', 'provider launched', 'provider command completed exit=23',
                   'owned cleanup started', 'owned cleanup clear', 'supervisor finalization started',
                   'checkpoint attempt started checkpoint=final-failure',
                   'checkpoint attempt ended checkpoint=final-failure', 'supervisor finalization ended exit=23']
        positions = [phases.index('unio: phase ' + label) for label in ordered]
        assert positions == sorted(positions)
        assert (coord / 'reports' / 'mock-order.log').read_text() == 'provider-only\n'
        failed = unio('run', 'mock-failure', 'mock-failure', extra={'UNIO_SAVE_TEST_FAULT': 'capture-launch'})
        assert failed.returncode == 23, failed.stderr
        assert 'save could not start' in failed.stderr
        assert 'checkpoint attempt ended checkpoint=final-failure' in failed.stderr
        good(unio('stop'))
        before_calls = calls.read_bytes()
        refused = unio('run', 'mock-refused', 'mock-refused')
        assert refused.returncode != 0 and calls.read_bytes() == before_calls
        assert 'unio: phase provider' not in refused.stderr
        print('PASS installed baseline IPC visibility, completion/final ordering, log isolation, save failure and refused admission')
    finally:
        listener.close()
        if active is not None and active.poll() is None:
            active.terminate()
            active.wait(timeout=40)
        unio('stop')

    # Load the installed supervisor, then isolate storage/ownership dependencies.
    # A real local command still executes while every phase write fails.
    body = Path(at).read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY\n', 1)[0]
    module = types.ModuleType('phase_contract')
    exec(compile(body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], 'phase_contract', 'exec'), module.__dict__)
    launched = []

    def spawn(root, worker, task, timeout, command, fd):
        launched.append(True)
        return subprocess.Popen(['python3', '-B', '-c', 'raise SystemExit(19)'], stdout=fd, stderr=fd)

    # Patch the supervisor's OS reference, never subprocess's shared os module.
    isolated_os = types.SimpleNamespace(**vars(os))
    isolated_os.close = lambda fd: None if fd == 9 else os.close(fd)
    def broken_write(fd, data):
        raise BrokenPipeError
    isolated_os.write = broken_write
    with tempfile.TemporaryFile(mode='w+') as diagnostic, \
         patch.object(module, 'inherited_run', return_value='run'), \
         patch.object(module, 'capture_child'), \
         patch.object(module, 'spawn_owned_provider', side_effect=spawn), \
         patch.object(module, 'finish_owned', return_value='clear'), \
         patch.object(module.signal, 'signal'), \
         patch.object(module, 'os', isolated_os), \
         contextlib.redirect_stderr(diagnostic):
        assert module.supervise_run(str(repo.parent), 'mock-order', 'mock-order', '30', 'unused') == 19
    assert launched == [True]
    # A replacement stream with no descriptor is equally harmless.
    with contextlib.redirect_stderr(io.StringIO()):
        module.emit_run_phase('provider launched')
    # Also verify that descriptor writes really were attempted and failed.
    with tempfile.TemporaryFile(mode='w+') as stream, contextlib.redirect_stderr(stream), \
         patch.object(module.os, 'write', side_effect=BrokenPipeError) as write:
        module.emit_run_phase('provider launched')
        assert write.call_count == 1
    print('PASS broken/replaced diagnostic streams preserve actual command exit')
