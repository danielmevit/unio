#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Installed, mock-only selftest regression; honors the caller's TMPDIR."""
import os
from pathlib import Path
import re
import subprocess
import tempfile

SOURCE = Path(__file__).resolve().parent.parent


def check(label, condition, detail=''):
    assert condition, label + ': ' + detail
    print('ok ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='unio selftest ',
                                 dir=os.environ.get('TMPDIR', str(SOURCE))) as tmp:
    base = Path(tmp)
    home = base / 'isolated home'
    home.mkdir()
    # Sentinel proves even the fixture's global Git config stays untouched.
    global_config = home / '.gitconfig'
    sentinel = b'[user]\n\tname = fixture\n\temail = fixture@example.invalid\n'
    global_config.write_bytes(sentinel)
    env = dict(os.environ, HOME=str(home),
               UNIO_BIN_DIR=str(base / 'installed bin'),
               UNIO_CONF_DIR=str(base / 'installed conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               TMPDIR=str(base), GIT_CONFIG_GLOBAL=str(global_config),
               GIT_CONFIG_NOSYSTEM='1', UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0', UNIO_TIMEOUT='30',
               GIT_AUTHOR_NAME='fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
               GIT_COMMITTER_NAME='fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
    for key in ('BASH_ENV', 'UNIO_SAVE_TEST_FAULT', 'UNIO_TEST_FAULT_DIR'):
        env.pop(key, None)
    subprocess.run(['bash', str(SOURCE / 'unio-install.sh')], env=env,
                   check=True, capture_output=True, timeout=120)
    runner = base / 'installed bin/unio'
    conf = base / 'installed conf'
    helper = conf / 'lib/remote-guard.py'
    canonical = (SOURCE / 'tools/remote-guard.py').read_bytes()
    check('installed helper is canonical', helper.read_bytes() == canonical)
    # Removing the external file no longer removes the implementation: the
    # byte-identical engine core must still run all behavioral assertions.
    helper.rename(helper.with_suffix('.saved'))
    # Snapshot all installed payload/config bytes; selftest may only write its
    # own sandbox, never alter the invoking profile.
    before = {p.relative_to(conf): p.read_bytes() for p in conf.rglob('*') if p.is_file()}
    result = subprocess.run([str(runner), 'selftest'], cwd=base, env=env,
                            capture_output=True, text=True, timeout=300)
    print(result.stdout, end='', flush=True)
    check('selftest without external helper exits zero', result.returncode == 0, result.stdout + result.stderr)
    check('all 40 built-in assertions pass',
          'selftest: 40 ok, 0 failed' in result.stdout and
          len(re.findall(r'^  ok    ', result.stdout, re.M)) == 40 and
          '  FAIL  ' not in result.stdout, result.stdout)
    match = re.search(r'^== unio selftest — sandbox: (.+) ==$', result.stdout, re.M)
    check('sandbox honors TMPDIR with spaces', bool(match) and Path(match[1]).parent == base)
    check('successful sandbox removed', bool(match) and not Path(match[1]).exists())
    after = {p.relative_to(conf): p.read_bytes() for p in conf.rglob('*') if p.is_file()}
    check('installed profile untouched', before == after)
    check('global Git config untouched', global_config.read_bytes() == sentinel)
