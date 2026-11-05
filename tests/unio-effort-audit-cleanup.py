#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""The read-only effort audit leaves no descendant process behind.

Real processes, a fake offline audit CLI and no provider or model call.
"""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]
passed = 0

FAKE = r'''#!/usr/bin/env bash
# Leave one direct and one nested background descendant in our process group.
sleep 300 & echo $! >> "$FAKE_DIR/pids"
bash -c 'sleep 300 & echo $! >> "$FAKE_DIR/pids"; wait' & echo $! >> "$FAKE_DIR/pids"
case "$(cat "$FAKE_DIR/mode")" in
  hang) sleep 300 ;;
  ok) cat "$FAKE_DIR/audit.json" ;;
  flood) while :; do printf '%04096d' 0; done ;;
esac
'''


def check(label, condition):
    global passed
    assert condition, label
    passed += 1
    print('PASS ' + label, flush=True)


def alive(pid):
    try:
        state = Path('/proc/%d/stat' % pid).read_text().rsplit(') ', 1)[1].split()[0]
    except (FileNotFoundError, ProcessLookupError):
        return False
    return state != 'Z'


def survivors(pids):
    # SIGKILL delivery is asynchronous: allow a loaded host a moment to finish
    # exiting, but a process that ignores the group kill would remain here.
    deadline = time.monotonic() + 5
    while any(alive(pid) for pid in pids) and time.monotonic() < deadline:
        time.sleep(.05)
    return [pid for pid in pids if alive(pid)]


spec = importlib.util.spec_from_file_location('effort_worker', SOURCE/'tools/codex-worker.py')
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)

with tempfile.TemporaryDirectory(prefix='effort audit cleanup ') as directory:
    base = Path(directory)
    project = base/'project'; project.mkdir()
    conf = base/'conf'; conf.mkdir()
    (conf/'agents.conf').write_text('legacy=codex exec -c model_reasoning_effort=medium\n')
    fake_dir = base/'fake'; fake_dir.mkdir()
    cli = base/'fake audit cli'; cli.write_text(FAKE); cli.chmod(0o700)
    row = dict(alias='legacy', tool='codex', requested_model='gpt-6.1-sol', requested_effort='medium',
               transport='stdin', authentication='Unknown', capacity='Unknown', effective_model='Unknown',
               effective_effort='Unknown', issues=[])
    (fake_dir/'audit.json').write_text(json.dumps(dict(
        schema_version=1, source='local_static', authentication='Unknown', capacity='Unknown',
        effective_model='Unknown', effective_effort='Unknown', agents=[row])))
    args = SimpleNamespace(worker='legacy-1', project=str(project))
    environment = {'UNIO_CONF_DIR': str(conf), 'UNIO_EFFORT_CLI': str(cli), 'FAKE_DIR': str(fake_dir)}

    def audit(mode):
        (fake_dir/'mode').write_text(mode)
        pids = fake_dir/'pids'
        if pids.exists(): pids.unlink()
        started = time.monotonic()
        with patch.dict(os.environ, environment), patch.object(worker, 'AUDIT_SECONDS', 2):
            result = worker.effort_info_audit(args)
        elapsed = time.monotonic() - started
        recorded = [int(x) for x in pids.read_text().split()] if pids.exists() else []
        return result, elapsed, recorded

    result, elapsed, pids = audit('hang')
    check('a hung audit is reported as invalid evidence', result['reason'] == 'invalid_agents_conf'
          and all(result[k] == 'Unknown' for k in ('tool', 'requested_model', 'requested_effort')))
    check('a hung audit stops at its bound', elapsed < 10)
    check('a hung audit started its descendants', len(pids) == 3)
    check('no descendant of a hung audit survives', not survivors(pids))

    result, elapsed, pids = audit('ok')
    check('a completed audit is still accepted', result['requested_effort'] == 'medium'
          and result['reason'] is None and result['tool'] == 'codex')
    check('no lingering descendant of a completed audit survives',
          len(pids) == 3 and not survivors(pids))

    result, elapsed, pids = audit('flood')
    check('oversized audit output is refused', result['reason'] == 'invalid_agents_conf')
    check('oversized output stops before the time bound', elapsed < 2)
    check('no descendant of a flooding audit survives', not survivors(pids))

print('effort audit cleanup: %d checks passed' % passed)
