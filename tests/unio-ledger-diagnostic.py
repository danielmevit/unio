#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline regression for the Source ledger diagnostic in dispatch_sha.

A selected-function harness runs the actual installed engine text (the
QUALITY_PY block of unio-install.sh) against disposable synthetic
fixtures. It demonstrates the four ledger cases that matter for the
damaged-ledger diagnostic:

* valid history (including run records for other tasks) stays passable;
* invalid JSON syntax midfile fails closed naming the project-relative
  journal and the exact physical row, never the row's contents;
* valid JSON that is not an object record fails closed the same way;
* undecodable bytes fail closed the same way;
* a valid record that proves a Source existed still refuses legacy
  manual verification without bound evidence.

Every case asserts the fixture journal is byte-identical afterwards (no
ledger mutation) and a subprocess guard proves zero provider launches.
No real ledger row content is used: all fixture rows are synthetic. One
end-to-end check replays the exact `quality dispatch-sha` invocation the
bash engine performs (python3 - with the engine text on stdin).
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

SOURCE = Path(__file__).resolve().parent.parent
INSTALLER = (SOURCE / 'unio-install.sh').read_text()
QUALITY = INSTALLER.split("<<'QUALITY_PY'\n", 1)[1].split('\nQUALITY_PY', 1)[0]
DEFINITIONS = QUALITY.split('\ntry:\n    cmd,*a=sys.argv[1:]', 1)[0]

JOURNAL = 'coord/reports/ledger.jsonl'
WORKER = 'mock'
TASK = 'ledger-fixture-task'
OTHER = 'other-fixture-task'
HEX = '0' * 64

checks = 0


def check(label, condition, detail=None):
    global checks
    if not condition:
        raise AssertionError(f'{label}: {detail}')
    checks += 1
    print('  ok ' + label, flush=True)


class NoProviders:
    """Any subprocess use inside the harness is a provider launch."""

    def __getattr__(self, name):
        raise AssertionError('provider launch attempted: ' + name)


def engine():
    ns = {'__name__': 'unio_ledger_diagnostic_fixture'}
    exec(compile(DEFINITIONS, 'QUALITY_PY', 'exec'), ns)
    ns['subprocess'] = NoProviders()
    return ns


def fixture(root, rows):
    """Write a synthetic ledger; rows are bytes or (str|bytes) lines."""
    reports = root / 'coord' / 'reports'
    reports.mkdir(parents=True, exist_ok=True)
    (root / 'coord' / 'results').mkdir(parents=True, exist_ok=True)
    (root / 'wt' / WORKER).mkdir(parents=True, exist_ok=True)
    ledger = reports / 'ledger.jsonl'
    ledger.write_bytes(b'\n'.join(rows) + (b'\n' if rows else b''))
    return ledger


def event(task, kind):
    return json.dumps({'task': task, 'event': kind, 'worker': WORKER,
                       'run_id': 'f' * 32}).encode()


def tree_state(root):
    state = {}
    for path in sorted(root.rglob('*')):
        if path.is_file():
            state[str(path.relative_to(root))] = path.read_bytes()
    return state


def call(ns, root, task=TASK, d=None):
    return ns['dispatch_sha'](str(root), WORKER, task, d)


def expect_refusal(ns, root, ledger, task, needle, row, label, body):
    before = ledger.read_bytes()
    state_before = tree_state(root)
    try:
        call(ns, root, task)
    except ValueError as exc:
        message = str(exc)
        check(label + ' names the journal', JOURNAL in message, message)
        check(label + ' names the exact physical row', f'row {row}' in message, message)
        check(label + ' names the failure class', needle in message, message)
        check(label + ' carries actionable wording',
              'inspect that row' in message and 'never skip, repair or rewrite ledger history' in message,
              message)
        check(label + ' hides the row contents', body not in message, message)
    else:
        raise AssertionError(label + ' accepted a damaged ledger')
    check(label + ' leaves the ledger byte-identical', ledger.read_bytes() == before)
    check(label + ' mutates nothing else', tree_state(root) == state_before)


def main():
    print('ledger diagnostic: selected-function harness against the installed engine')
    ns = engine()
    with tempfile.TemporaryDirectory(prefix='unio-ledger-diagnostic-') as temporary:
        root = Path(temporary)

        # 1. Valid history: object records, run evidence for another task,
        #    and an empty non-object-free journal all stay passable. The
        #    no-provider semantics are intact: absence of Source permits
        #    machine-only checks (empty binding), never a fabricated SHA.
        ledger = fixture(root, [event(OTHER, 'run_start'),
                                 event(OTHER, 'run'),
                                 event(TASK, 'queued')])
        before = ledger.read_bytes()
        check('valid history yields no binding', call(ns, root) is None)
        check('valid history leaves the ledger untouched', ledger.read_bytes() == before)
        ledger.unlink()
        check('absent ledger yields no binding', call(ns, root) is None)

        # 2. Invalid JSON syntax midfile: row 3 of 5 is malformed.
        bad = b'{"event": "run_start"'  # truncated object, synthetic
        sentinel = 'TRUNCATED-SYNTAX-SENTINEL'
        ledger = fixture(root, [event(OTHER, 'run_start'), event(OTHER, 'run'),
                                bad + sentinel.encode(), event(OTHER, 'run'),
                                event(OTHER, 'run_start')])
        expect_refusal(ns, root, ledger, TASK, 'not valid JSON', 3,
                       'invalid syntax midfile', sentinel)

        # 3. Valid JSON that is not an object record: row 2 is an array.
        ledger = fixture(root, [event(OTHER, 'run_start'), b'[1, 2, 3]'])
        expect_refusal(ns, root, ledger, TASK, 'not a JSON object record', 2,
                       'valid JSON non-object', '[1, 2, 3]')

        # 4. Undecodable bytes: row 2 is not valid text at all.
        ledger = fixture(root, [event(OTHER, 'run_start'), b'\x80\x81\x82 not text'])
        expect_refusal(ns, root, ledger, TASK, 'not decodable text', 2,
                       'undecodable bytes', 'not text')

        # 5. Actual Source evidence: a valid run_start record for this
        #    exact task still refuses legacy manual verification without
        #    bound dispatch evidence. The ledger itself is healthy.
        ledger = fixture(root, [event(OTHER, 'run_start'),
                                event(TASK, 'run_start'),
                                event(OTHER, 'run')])
        before = ledger.read_bytes()
        try:
            call(ns, root)
        except ValueError as exc:
            check('recorded Source refuses unbound verification',
                  'dispatch binding unavailable for recorded Source' in str(exc), str(exc))
        else:
            raise AssertionError('recorded Source accepted without bound evidence')
        check('Source refusal leaves the ledger untouched', ledger.read_bytes() == before)

        # 6. Original runs stay intact: a persisted result with a bound
        #    dispatch revision returns its task SHA without reading the
        #    ledger at all.
        rev = {'candidate_commit': HEX, 'base_commit': HEX,
               'task_sha256': 'a' * 64, 'worktree_sha256': HEX}
        d = ns['fresh'](WORKER, TASK)
        d['process'] = dict(state='succeeded', exit_code=0, revision=rev)
        d['dispatch_revision'] = rev
        check('bound original run returns its task SHA',
              call(ns, root, d=d) == 'a' * 64)

        # 7. End-to-end: replay the exact `quality dispatch-sha` entry the
        #    bash engine performs and check the surfaced operator error.
        ledger = fixture(root, [event(OTHER, 'run_start'),
                                b'{"event": "run_start"' + b'ENDTOEND-SYNTAX-SENTINEL',
                                event(OTHER, 'run')])
        before = ledger.read_bytes()
        env = {k: v for k, v in os.environ.items() if not k.startswith('UNIO_')}
        env['UNIO_QUALITY_CONF'] = str(root / 'conf')
        result = subprocess.run([sys.executable, '-', 'dispatch-sha', str(root), WORKER, TASK],
                               input=QUALITY, capture_output=True, text=True, env=env,
                               timeout=120)
        check('engine entry fails closed', result.returncode == 2, str(result.returncode))
        check('engine error carries the quality prefix and row',
              result.stderr.startswith('unio quality: malformed Source ledger: ')
              and f'{JOURNAL} row 2' in result.stderr, result.stderr)
        check('engine error hides the row contents',
              'ENDTOEND-SYNTAX-SENTINEL' not in result.stderr, result.stderr)
        check('engine run leaves the ledger byte-identical', ledger.read_bytes() == before)

    print(f'unio-ledger-diagnostic: {checks} checks passed')


if __name__ == '__main__':
    main()
