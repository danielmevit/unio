#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Deeply nested save JSON is refused as invalid evidence, never a traceback."""
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import types

SOURCE = Path(__file__).resolve().parents[1]
passed = 0
# The exact pre-existing reproduction: 400001 bytes of unclosed nesting.
OPEN = b'[' * 400001
BALANCED = b'[' * 200000 + b']' * 200000
OBJECTS = b'{"a":' * 100000 + b'1' + b'}' * 100000


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


with tempfile.TemporaryDirectory(prefix='save-json-depth-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base/'bin'), UNIO_CONF_DIR=str(base/'conf'),
               UNIO_COMPLETION_DIR=str(base/'completion'), UNIO_AUTO_VERIFY='0',
               UNIO_AUTO_SYNC='0', UNIO_SAVE_CAPTURE_TIMEOUT='300',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    env.pop('UNIO_SAVE_TEST_FAULT', None)
    subprocess.run(['bash', str(SOURCE/'unio-install.sh')], env=env,
                   check=True, capture_output=True, timeout=120)
    engine = base/'bin/unio'
    calls = base/'provider-calls'
    (base/'conf/agents.conf').write_text("mock=bash -c 'echo invoked >> \"%s\"; exit 99'\n" % calls)
    root = base/'project'; repo = root/'repo'; repo.mkdir(parents=True)

    def git(where, *args):
        return subprocess.check_output(['git', '-C', str(where), *args], env=env, stderr=subprocess.PIPE)

    def unio(*args):
        return subprocess.run([str(engine), *args], cwd=repo, env=env,
                              capture_output=True, text=True, timeout=180)

    def clean(result):
        return 'Traceback' not in result.stderr and 'RecursionError' not in result.stderr

    body = engine.read_text().split("<<'SAVES_PY'\n", 1)[1].split('\nSAVES_PY\n', 1)[0]
    module = types.ModuleType('installed_save_json_depth')
    exec(compile(body.rsplit('sys.exit(main(sys.argv[1:]))', 1)[0], str(engine), 'exec'), module.__dict__)

    def refusal(raw, limit=None):
        try:
            module.strict_json(raw, limit or module.MAX_MANIFEST, 'manifest')
        except module.Refuse as refused:
            return refused.code, refused.message
        except RecursionError:
            return 'RecursionError', None
        return None

    check('400001-byte unclosed nesting is refused as invalid save evidence',
          refusal(OPEN) == ('invalid_save', 'manifest is nested too deeply'))
    check('balanced deep arrays are refused the same way',
          refusal(BALANCED) == ('invalid_save', 'manifest is nested too deeply'))
    check('deep objects are refused the same way',
          refusal(OBJECTS) == ('invalid_save', 'manifest is nested too deeply'))
    moderate = b'{"worker":"w","x":' + b'[' * 900 + b']' * 900 + b'}'
    check('moderate nesting still parses exactly as before',
          module.strict_json(moderate, module.MAX_MANIFEST, 'manifest') == json.loads(moderate))
    check('size bound still applies before parsing',
          refusal(OPEN, 4096) == ('invalid_save', 'manifest exceeds its size bound'))
    check('ordinary malformed JSON keeps its refusal',
          refusal(b'{"a":') == ('invalid_save', 'manifest is not valid JSON'))
    check('duplicate keys keep their refusal',
          refusal(b'{"a":1,"a":2}') == ('invalid_save', 'manifest has a duplicate key: a'))
    check('non-finite numbers keep their refusal',
          refusal(b'{"a":NaN}') == ('invalid_save', 'manifest has a non-finite number'))

    (repo/'file.txt').write_bytes(b'base\n')
    git(repo, 'init', '-q', '-b', 'main'); git(repo, 'add', '.'); git(repo, 'commit', '-qm', 'base')
    check('real Git workers initialize', unio('init', 'mock-source', 'mock-dest').returncode == 0)
    unio('stop')
    (root/'coord/tasks/T.md').write_text('# T\nOffline only\n')
    wt = root/'wt/mock-source'
    (wt/'file.txt').write_bytes(b'working bytes\n')

    # A deeply nested frozen task record is unreadable metadata: save create
    # falls back to the native coord/base exactly as for any malformed record.
    results = root/'coord/results/mock-source'
    results.mkdir(parents=True, exist_ok=True)
    (results/'T.json').write_bytes(OPEN)
    created = unio('save', 'create', 'mock-source', 'T')
    match = re.search(r'^saved ([0-9a-f]{32}):', created.stdout, re.M)
    check('deep frozen task record falls back without a traceback',
          created.returncode == 0 and match is not None and clean(created))
    (results/'T.json').unlink()
    sid = match[1]; store = root/'coord/saves'

    # A newer save directory whose manifest is deeply nested must be skipped
    # as corrupt evidence; the supported original remains the last good save.
    planted = store/('f' * 32)
    shutil.copytree(store/sid, planted)
    (planted/'manifest.json').write_bytes(OPEN)
    inspected = unio('save', 'inspect', '--worker', 'mock-source', '--json')
    check('worker inspection completes without a traceback', inspected.returncode == 0 and clean(inspected))
    report = json.loads(inspected.stdout)
    check('deep manifest is skipped and the supported save stays selected',
          report['last_good'] is not None and report['last_good']['save_id'] == sid)
    check('deep manifest is counted as corrupt evidence', report['corrupt_evidence'] >= 1)
    found = module.last_good(str(store), 'mock-source', True)
    check('lookup helper skips the deep candidate', found is not None and found['id'] == sid)
    usage = unio('save', 'usage', '--json')
    # Corrupt evidence makes usage Unknown (exit 2) by design, not a crash.
    observed = json.loads(usage.stdout) if usage.stdout.strip() else {}
    check('store usage reports the deep manifest as corrupt evidence without a traceback',
          usage.returncode == 2 and clean(usage) and observed.get('status') == 'unknown'
          and observed.get('corrupt_evidence', 0) >= 1)
    by_id = unio('save', 'inspect', planted.name, '--json')
    refused = json.loads(by_id.stdout) if by_id.stdout.strip() else {}
    check('inspecting the deep save is an ordinary JSON refusal',
          by_id.returncode == 1 and clean(by_id) and refused.get('valid') is False
          and refused.get('reason') == 'invalid_save' and refused.get('message') == 'manifest is nested too deeply')
    plain = unio('save', 'inspect', planted.name)
    check('plain inspection explains the refusal without a traceback',
          plain.returncode == 1 and clean(plain) and 'is not usable (invalid_save): manifest is nested too deeply' in plain.stderr)
    check('deep manifest bytes are preserved, not cleaned up',
          (planted/'manifest.json').read_bytes() == OPEN)
    check('no provider was invoked', not calls.exists())

print('save JSON depth: %d checks passed' % passed)
