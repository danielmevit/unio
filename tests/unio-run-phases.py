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

def assert_shared_stream_safety(module):
    """Check flags inside the write, where restoring them later cannot hide harm."""
    real_os = os
    for kind in ('file', 'pipe'):
        for event in ('write', 'close', 'error', 'replacement'):
            with contextlib.ExitStack() as stack:
                if kind == 'file':
                    stream = stack.enter_context(tempfile.TemporaryFile(mode='w+'))
                else:
                    reader, writer = os.pipe()
                    stack.callback(os.close, reader)
                    stream = stack.enter_context(os.fdopen(writer, 'w'))
                original = stream.fileno()
                peer = os.dup(original)
                stack.callback(os.close, peer)
                replacement = stack.enter_context(tempfile.TemporaryFile(mode='w+'))
                observed = []
                isolated = types.SimpleNamespace(**vars(os))

                def write(fd, data):
                    observed.append(real_os.get_blocking(peer))
                    assert observed[-1] is True, (kind, event, 'peer became nonblocking during write')
                    if event == 'close':
                        stream.close()
                    elif event == 'replacement':
                        real_os.dup2(replacement.fileno(), original)
                    elif event == 'error':
                        raise BrokenPipeError
                    return real_os.write(fd, data)

                isolated.write = write
                with patch.object(module, 'os', isolated), contextlib.redirect_stderr(stream):
                    module.emit_run_phase('provider launched')
                # The emitter deliberately swallows errors, including assertions.
                assert observed == [True], (kind, event, observed)
                assert real_os.get_blocking(peer) is True, (kind, event, 'peer flags left changed')
                if event != 'error':
                    if kind == 'file':
                        real_os.lseek(peer, 0, os.SEEK_SET)
                        actual = real_os.read(peer, 1024)
                    else:
                        actual = real_os.read(reader, 1024)
                    assert actual == b'unio: phase provider launched\n', (kind, event, actual)
                if event == 'replacement':
                    assert replacement.tell() == 0


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
        assert refused.returncode != 0, refused
        assert 'STOP is active (unio resume to clear)' in refused.stderr, refused.stderr
        assert calls.read_bytes() == before_calls
        assert 'unio: phase ' not in refused.stderr, refused.stderr
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

    assert_shared_stream_safety(module)
    # Keep regular-file offset/append semantics, including bytes beyond the
    # current offset. Reopening the file at offset zero would corrupt this.
    for append in (False, True):
        path = base / 'position-log'
        path.write_bytes(b'prefix:TAIL')
        with path.open('a+' if append else 'r+') as stream, contextlib.redirect_stderr(stream):
            stream.seek(7)
            module.emit_run_phase('provider launched')
            expected = (b'prefix:TAIL' if append else b'prefix:') + b'unio: phase provider launched\n'
            assert stream.tell() == len(expected), (append, stream.tell())
            assert path.read_bytes() == expected

    # A child timeout bounds a regression that accidentally blocks. The hook
    # fills an initially empty pipe immediately before the emitter's write,
    # covering the readiness-check/writer race as well as an already full pipe.
    import ast
    emitter = next(n for n in ast.parse(body).body if isinstance(n, ast.FunctionDef) and n.name == 'emit_run_phase')
    source = ast.get_source_segment(body, emitter)
    full_pipe = r"""
import os, sys, stat, types
from unittest.mock import patch
SOURCE
reader, writer = os.pipe()
peer = os.dup(writer)
filler = os.open('/proc/self/fd/%s' % writer, os.O_WRONLY | os.O_NONBLOCK)
real_write = os.write
observed = []
def fill():
    try:
        while True:
            real_write(filler, b'x' * 4096)
    except BlockingIOError:
        pass
def write(fd, data):
    fill()
    observed.append(os.get_blocking(peer))
    return real_write(fd, data)
stream = os.fdopen(writer, 'w')
for initially_full in (False, True):
    if initially_full:
        fill()
    with patch.object(sys, 'stderr', stream), patch.object(os, 'write', write):
        emit_run_phase('provider launched')
    assert observed[-1] is True and os.get_blocking(peer) is True, observed
assert observed == [True, True], observed
""".replace('SOURCE', source)
    full = subprocess.run(['python3', '-B', '-c', full_pipe], capture_output=True, text=True, timeout=5)
    assert full.returncode == 0, full.stdout + full.stderr
    print('PASS shared peer flags during/after writes, close, error, replacement; full-pipe race; regular-file offsets/append')
