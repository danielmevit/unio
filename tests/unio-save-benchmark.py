#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Focused fake-fixture checks for tools/save-benchmark.py.

Uses a stub engine (no real Unio installation) to verify the probe's
argument and scratch safety, fixture isolation, honest measurement
recording, subprocess/output bounds and exact-workspace cleanup. No
provider, network or real project is involved.
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

source = Path(__file__).resolve().parent.parent
tool = source / 'tools' / 'save-benchmark.py'
passed = [0]

FAKE_ENGINE = r'''#!/usr/bin/env bash
set -u
cmd="${1:-}"; [ $# -gt 0 ] && shift
root="$(dirname "$PWD")"
case "$cmd" in
  version) echo "Unio 0.5.9-fake ($0)"; echo "Your AIs, in sync." ;;
  init)
    mkdir -p "$root/coord/tasks" "$root/coord/.locks" "$root/wt"
    for w in "$@"; do
      ( git clone -q "$root/repo" "$root/wt/$w" && printf '%s' "$w" > "$root/wt/$w/.unio-worker" ) &
    done
    wait
    echo "workers initialized" ;;
  stop) mkdir -p "$root/coord"; touch "$root/coord/STOP"; echo "STOP set" ;;
  save)
    sub="${1:-}"; shift || true
    case "$sub" in
      create)
        if [ -n "${FAKE_HANG_CREATE:-}" ]; then sleep 30; fi
        if [ -n "${FAKE_FAIL_CREATE:-}" ]; then echo "unio: fake refusal" >&2; exit 1; fi
        id="$(printf '%032x' $((RANDOM * 100000 + RANDOM)))"
        mkdir -p "$root/coord/saves/$id"
        printf '{"worker": "%s", "task": "%s"}' "${1:-}" "${2:-}" > "$root/coord/saves/$id/manifest.json"
        echo "saved $id: manual save" ;;
      inspect)
        echo '{"last_good": {"save_id": "fake"}, "latest_attempt": {"status": "complete"}, "live": "saved"}' ;;
      usage) echo "usage: unio save ..." >&2; exit 2 ;;
      *) echo "fake save subcommand" >&2; exit 2 ;;
    esac ;;
  watch) echo '{"observed_at": "2026-01-01T00:00:00Z", "stopped": true}' ;;
  *) echo "fake engine: unknown command" >&2; exit 2 ;;
esac
'''


def check(label, condition=True):
    if not condition:
        print('FAIL ' + label)
        sys.exit(1)
    passed[0] += 1
    print('  ok %s' % label)


def probe(*args, env=None, timeout=180):
    e = dict(os.environ, **(env or {}))
    return subprocess.run([sys.executable, '-B', str(tool), *args],
                          capture_output=True, text=True, timeout=timeout, env=e)


with tempfile.TemporaryDirectory(prefix='save-benchmark-test-') as directory:
    base = Path(directory)
    scratch = base / 'scratch'
    scratch.mkdir()
    (scratch / 'sentinel.txt').write_text('caller content\n')
    engine = base / 'fake-unio'
    engine.write_text(FAKE_ENGINE)
    os.chmod(engine, 0o755)
    engine_bytes = engine.read_bytes()

    # ---- usage and input safety ---------------------------------------
    r = probe()
    check('missing --engine and --scratch is a usage error', r.returncode == 2)
    r = probe('--engine', str(engine))
    check('missing --scratch is a usage error', r.returncode == 2)
    r = probe('--engine', str(engine), '--scratch', str(base / 'missing'))
    check('nonexistent scratch refused', r.returncode == 2 and 'scratch' in r.stderr)
    r = probe('--engine', str(engine), '--scratch', str(engine))
    check('file as scratch refused', r.returncode == 2)
    linked = base / 'linked-scratch'
    os.symlink(scratch, linked)
    r = probe('--engine', str(engine), '--scratch', str(linked))
    check('symlinked scratch refused', r.returncode == 2)
    r = probe('--engine', str(base / 'missing'), '--scratch', str(scratch))
    check('missing engine refused', r.returncode == 2)
    dead = base / 'dead-unio'
    dead.write_text('#!/bin/sh\n')
    os.chmod(dead, 0o644)
    r = probe('--engine', str(dead), '--scratch', str(scratch))
    check('non-executable engine refused', r.returncode == 2)
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--saves', '4')
    check('more than three saves refused', r.returncode == 2)
    taken = scratch / 'taken'
    taken.mkdir()
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'taken')
    check('existing benchmark workspace refused', r.returncode == 2 and 'refusing to reuse' in r.stderr)

    # ---- full run against the fake engine ------------------------------
    started = time.monotonic()
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'run1')
    check('probe completes against the fake engine', r.returncode == 0)
    check('probe is bounded', time.monotonic() - started < 120)
    child = scratch / 'run1'
    receipt_path = child / 'receipt.json'
    check('private receipt retained in the workspace', receipt_path.is_file()
          and stat.S_IMODE(receipt_path.stat().st_mode) == 0o600)
    doc = json.loads(receipt_path.read_text())
    check('receipt uses schema 1 and prints to stdout',
          doc['schema_version'] == 1 and json.loads(r.stdout)['schema_version'] == 1)
    check('exact engine version recorded',
          doc['engine']['version'] == '0.5.9-fake' and doc['engine']['version_line'].startswith('Unio 0.5.9-fake'))
    check('filesystem type observed', doc['scratch']['filesystem']['stat_f_type'])
    creates = doc['measurements']['save_create']
    check('three save-create calls measured with monotonic durations',
          len(creates) == 3 and all(c['duration_seconds'] >= 0 for c in creates))
    check('saves confirmed by published manifests, not exit alone',
          all(c['exit_code'] == 0 and c['save_id'] and c['confirmed_by_manifest'] is True for c in creates))
    check('worker inspect recorded as valid JSON',
          doc['measurements']['save_inspect_worker']['exit_code'] == 0
          and doc['measurements']['save_inspect_worker']['json_valid'] is True)
    usage = doc['measurements']['save_usage']
    check('save usage recorded honestly as unsupported',
          usage['exit_code'] == 2 and usage['supported'] is False and usage['detail'])
    check('watch --once --json recorded',
          doc['measurements']['watch_once_json']['exit_code'] == 0
          and doc['measurements']['watch_once_json']['json_valid'] is True)
    check('no provider call recorded', doc['fixture']['provider_calls_recorded'] == 0)
    check('workload counts reported',
          doc['workload']['tracked_paths'] > 0 and doc['workload']['worktree_files'] > 0
          and doc['workload']['worktree_bytes'] > 0 and doc['workload']['untracked'] > 0)
    check('fixture stays inside the private workspace',
          (child / 'project' / 'coord' / 'STOP').exists()
          and (child / 'project' / 'wt' / 'bench-a' / '.unio-worker').exists())
    check('caller scratch content untouched', (scratch / 'sentinel.txt').read_text() == 'caller content\n')
    check('engine never modified', engine.read_bytes() == engine_bytes)
    check('no cleanup without the explicit option',
          doc['cleanup'] == {'requested': False, 'performed': False} and child.exists())

    # ---- fewer saves ----------------------------------------------------
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'run2', '--saves', '1')
    doc = json.loads(r.stdout)
    check('--saves 1 measures exactly one save create',
          r.returncode == 0 and len(doc['measurements']['save_create']) == 1 and doc['save_count'] == 1)

    # ---- honest refusal recording ---------------------------------------
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'run3',
              env={'FAKE_FAIL_CREATE': '1'})
    doc = json.loads(r.stdout)
    creates = doc['measurements']['save_create']
    check('refused saves recorded honestly without a claimed save',
          r.returncode == 0 and all(c['exit_code'] == 1 and c['save_id'] is None
                                     and c['confirmed_by_manifest'] is False for c in creates))

    # ---- bounded hung subprocess ----------------------------------------
    started = time.monotonic()
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'run4',
              '--saves', '1', '--step-timeout', '3', env={'FAKE_HANG_CREATE': '1'})
    elapsed = time.monotonic() - started
    doc = json.loads(r.stdout)
    hung = doc['measurements']['save_create'][0]
    check('hung save create is killed at the step deadline',
          r.returncode == 0 and hung['timed_out'] is True and hung['exit_code'] is None
          and elapsed < 30 and 'bounded' in doc['failures'][0])

    # ---- explicit cleanup removes exactly the new workspace -------------
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'run5', '--cleanup')
    doc = json.loads(r.stdout)
    check('cleanup removes only the new benchmark workspace',
          r.returncode == 0 and doc['cleanup'] == {'requested': True, 'performed': True}
          and not (scratch / 'run5').exists() and (scratch / 'run1').exists()
          and (scratch / 'sentinel.txt').exists() and taken.exists())

print('%d checks passed' % passed[0])
