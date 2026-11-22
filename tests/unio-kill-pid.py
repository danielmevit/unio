#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Malformed public cancellation identity never reaches a signal builtin.

An isolated BASH_ENV signal spy makes this safe even if the guard regresses.
The actual installed public command runs; no provider or real signal is used.
"""
import os
import subprocess
import tempfile
from pathlib import Path

source = Path(__file__).resolve().parent.parent
with tempfile.TemporaryDirectory(prefix='kill-pid-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env, check=True, capture_output=True)
    root = base / 'project with spaces'
    repo = root / 'repo'
    repo.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', '-b', 'main'], cwd=repo, env=env, check=True)
    subprocess.run(['git', 'commit', '-qm', 'base', '--allow-empty'], cwd=repo, env=env, check=True)
    at = str(base / 'bin' / 'unio')
    subprocess.run([at, 'init', 'mock'], cwd=repo, env=env, check=True, capture_output=True)
    spy, calls = base / 'signal-spy.sh', base / 'signals'
    spy.write_text('kill() { printf "%s\\n" "$*" >> "$UNIO_TEST_SIGNALS"; return 1; }\n')
    env.update(BASH_ENV=str(spy), UNIO_TEST_SIGNALS=str(calls))
    pidfile = root / 'coord' / 'reports' / 'bad.pid'
    payload = '$(touch evaluated-marker)'
    values = ['-1', '-123', '0', '1', '00123', '+123', 'abc', '123 456',
              '123\n456', '9999999999999999999999999', payload, '`touch evaluated-marker`']
    for value in values:
        body = value + '\n'
        pidfile.write_text(body)
        r = subprocess.run([at, 'kill', 'bad'], cwd=repo, env=env, capture_output=True, text=True, timeout=10)
        assert r.returncode == 1 and 'invalid background pid' in r.stderr, (value, r.returncode, r.stderr)
        assert pidfile.read_text() == body, 'invalid identity evidence was changed'
        assert not calls.exists(), 'malformed PID reached a signal probe'
        assert not (repo / 'evaluated-marker').exists(), 'PID text was evaluated'
        print('  ok rejected malformed PID safely: ' + repr(value))
    # The read-only waiter faces the same bogus evidence: it must refuse
    # without signalling, evaluating or mutating anything (here no ownership
    # record exists, so nothing can be bound at all).
    for value in values:
        body = value + '\n'
        pidfile.write_text(body)
        r = subprocess.run([at, 'wait', 'bad', '--timeout', '5'], cwd=repo, env=env,
                           capture_output=True, text=True, timeout=30)
        assert r.returncode == 2 and 'nothing is bound' in r.stderr, (value, r.returncode, r.stderr)
        assert pidfile.read_text() == body, 'wait mutated identity evidence'
        assert not calls.exists(), 'wait reached a signal probe'
        assert not (repo / 'evaluated-marker').exists(), 'wait evaluated PID text'
        print('  ok wait refused bogus identity safely: ' + repr(value))
    print('kill PID safety: %d cases passed; zero signal calls and provider calls' % len(values))
