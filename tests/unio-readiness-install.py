#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit).
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Installed CLI integration: fake native metadata only, no real account."""
import json
import os
import subprocess
import tempfile
from pathlib import Path

source = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='readiness-install-') as directory:
    root = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(root/'bin'), UNIO_CONF_DIR=str(root/'conf'),
               UNIO_COMPLETION_DIR=str(root/'completion'))
    subprocess.run(['bash', str(source/'unio-install.sh')], env=env, capture_output=True, check=True)
    project = root/'workspace with spaces'; (project/'coord').mkdir(parents=True); (project/'wt').mkdir()
    repo = project/'repo'; repo.mkdir()
    (project/'coord/STOP').write_text('owner pause\n')
    for name in ('bridge/readiness.py', 'tools/agent-readiness.py'):
        assert (source/name).read_bytes() == (root/'conf/lib/readiness'/name).read_bytes()
    calls = root/'calls'; fake = root/'bin/claude'
    fake.write_text('#!/usr/bin/env python3\nimport json,sys\nfrom pathlib import Path\n'
        + 'root=Path(__file__).parent.parent\n'
        + 'with (root/"calls").open("a") as log: log.write(json.dumps(sys.argv[1:])+"\\n")\n'
        + 'if sys.argv[1:]==["--version"]: print("2.1.296 (Claude Code)")\n'
        + 'elif sys.argv[1:]==["auth","status","--json"]: print(json.dumps({"loggedIn":True,"authMethod":"claude.ai","email":"private@example.invalid","token":"secret-sentinel"}))\n'
        + 'else: raise SystemExit(99)\n')
    fake.chmod(0o755); env['PATH'] = str(root/'bin') + os.pathsep + env['PATH']

    def unio(*args, cwd=repo):
        return subprocess.run([str(root/'bin/unio'), 'readiness', *args], cwd=cwd, env=env,
                              capture_output=True, text=True, timeout=20)

    help_result = unio('--help', cwd=root)
    assert help_result.returncode == 0 and 'unio readiness' in help_result.stdout and not calls.exists()
    missing = unio('show', '--json')
    assert missing.returncode == 0 and json.loads(missing.stdout)['state'] == 'missing'
    assert not (project/'coord/readiness').exists() and not calls.exists()
    refreshed = unio('--project', str(project), 'refresh', 'claude')
    assert refreshed.returncode == 0, refreshed.stderr
    view = json.loads(refreshed.stdout)['agents']['claude']
    assert view['authentication'] == 'signed_in' and view['capacity'] == 'unknown'
    assert view['dispatch_readiness'] == 'unknown'
    assert [json.loads(line) for line in calls.read_text().splitlines()] == [['--version'], ['auth', 'status', '--json']]
    actual_calls = calls.read_bytes()
    local = unio('show', '--agent', 'claude', '--json')
    assert local.returncode == 0 and calls.read_bytes() == actual_calls
    for output in (refreshed.stdout, local.stdout, (project/'coord/readiness/observations.json').read_text()):
        assert 'private@example.invalid' not in output and 'secret-sentinel' not in output
    denied = unio('refresh', 'other')
    assert denied.returncode == 2 and calls.read_bytes() == actual_calls
    assert (project/'coord/STOP').read_text() == 'owner pause\n'
    print('Installed readiness: payload, help, local-only show, fixed refresh argv, privacy and STOP independence PASS')
