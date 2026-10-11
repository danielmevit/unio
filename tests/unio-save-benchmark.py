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
import importlib.util
import os
import shlex
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
    if [ -n "${FAKE_HANG_INIT:-}" ]; then printf entered > "$root/init-entered"; sleep 30; fi
    mkdir -p "$root/coord/tasks" "$root/coord/.locks" "$root/wt"
    printf '%s' "$HOME" > "$root/home-observed"
    printf '%s' "${GIT_DIR:-}" > "$root/git-dir-observed"
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
        printf '{"schema_version":1,"save_id":"%s","worker":"%s","task":"%s"}' "$id" "${1:-}" "${2:-}" > "$root/coord/saves/$id/manifest.json"
        if [ -n "${FAKE_BAD_MANIFEST:-}" ]; then printf '{}' > "$root/coord/saves/$id/manifest.json"; fi
        echo "saved $id: manual save" ;;
      inspect)
        echo '{"last_good": {"save_id": "fake"}, "latest_attempt": {"status": "complete"}, "live": "saved"}' ;;
      usage)
        if [ -n "${FAKE_UNKNOWN_USAGE:-}" ]; then echo '{"status":"unknown"}'; exit 2; fi
        echo "usage: unio save ..." >&2; exit 2 ;;
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
    e = dict(os.environ)
    if env:
        # Select the fake engine behavior in its own file. The production
        # probe deliberately strips inherited project/shell overrides.
        variant = engine.with_name('variant-' + str(time.monotonic_ns()))
        exports = ''.join('export %s=%s\n' % (key, shlex.quote(value)) for key, value in env.items()
                          if key.startswith('FAKE_'))
        variant.write_text(FAKE_ENGINE.replace('set -u\n', 'set -u\n' + exports))
        variant.chmod(0o755)
        args = tuple(str(variant) if value == str(engine) else value for value in args)
        e.update({key: value for key, value in env.items() if not key.startswith('FAKE_')})
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
    check('HOME is unchanged in child commands',
          (child / 'project' / 'home-observed').read_text() == os.environ.get('HOME', ''))
    check('staged deletion and unstaged changes are counted',
          doc['workload']['removed'] == 1 and doc['workload']['staged'] == 2
          and doc['workload']['unstaged'] == 1)
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
    check('failed save attempts are not counted as saves', doc['save_count'] == 0
          and doc['save_attempt_count'] == 3)

    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'invalid-manifest',
              '--saves', '1', env={'FAKE_BAD_MANIFEST': '1', 'GIT_DIR': '/nonexistent-host-repo',
                                  'UNIO_CONF_DIR': '/nonexistent-host-config'})
    doc = json.loads(r.stdout)
    check('malformed published manifest cannot confirm a save', r.returncode == 0
          and doc['save_count'] == 0 and not doc['measurements']['save_create'][0]['confirmed_by_manifest'])
    check('inherited Git project overrides are stripped',
          (scratch / 'invalid-manifest/project/git-dir-observed').read_text() == '')

    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'unknown-usage',
              '--saves', '1', env={'FAKE_UNKNOWN_USAGE': '1'})
    usage = json.loads(r.stdout)['measurements']['save_usage']
    check('supported Unknown usage is distinct from an unsupported command',
          usage['exit_code'] == 2 and usage['supported'] is True
          and usage['observation']['status'] == 'unknown')

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

    # Allow real Git fixture setup to finish before testing the fake hung
    # engine. A 0.2s global step bound can stop Git first on WSL/9p.
    started = time.monotonic()
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'hung-init',
              '--step-timeout', '3', env={'FAKE_HANG_INIT': '1'})
    elapsed = time.monotonic() - started
    doc = json.loads(r.stdout)
    check('a timed-out init is a fixture failure, never treated as success',
          r.returncode == 1 and doc['measurements'] is None
          and (scratch / 'hung-init/project/init-entered').read_text() == 'entered'
          and elapsed < 30
          and any('engine init failed' in f for f in doc['failures']))

    # ---- explicit cleanup removes exactly the new workspace -------------
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'run5', '--cleanup')
    doc = json.loads(r.stdout)
    check('cleanup removes only the new benchmark workspace',
          r.returncode == 0 and doc['cleanup'] == {'requested': True, 'performed': True}
          and not (scratch / 'run5').exists() and (scratch / 'run1').exists()
          and (scratch / 'sentinel.txt').exists() and taken.exists())

    for bad_timeout in ('nan', 'inf'):
        r = probe('--engine', str(engine), '--scratch', str(scratch), '--total-timeout', bad_timeout)
        check('nonfinite timeout refused: ' + bad_timeout, r.returncode == 2)

    spec = importlib.util.spec_from_file_location('save_benchmark', tool)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    started = time.monotonic()
    closed = module.run_bounded([sys.executable, '-c',
        'import os,time; os.close(1); os.close(2); time.sleep(30)'], base, os.environ, 0.2)
    check('a process closing its output is still bounded by its deadline',
          closed.timed_out and closed.exit_code is None and time.monotonic()-started < 2)
    flood = module.run_bounded([sys.executable, '-c', 'print("x" * 1000000)'], base, os.environ, 1, cap=1024)
    check('output flood is capped and stopped', flood.output_truncated and len(flood.stdout) == 1024)
    marker = base / 'late-descendant'
    module.run_bounded([sys.executable, '-c',
        'import os,time,pathlib; child=os.fork(); time.sleep(0.6 if child==0 else 30); '
        'pathlib.Path(%r).write_text("escaped")' % str(marker)], base, os.environ, 0.15)
    time.sleep(0.7)
    check('timed-out process descendants cannot keep working', not marker.exists())

    started = time.monotonic()
    r = probe('--engine', str(engine), '--scratch', str(scratch), '--workspace', 'total-deadline',
              '--total-timeout', '0.01')
    check('whole-probe deadline bounds fixture Git and engine commands',
          r.returncode == 1 and time.monotonic()-started < 2
          and any('total timeout' in f for f in json.loads(r.stdout)['failures']))

print('%d checks passed' % passed[0])
