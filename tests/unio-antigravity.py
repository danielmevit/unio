#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Antigravity adapter regressions with a fake CLI; offline, zero AI calls."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

SOURCE = Path(__file__).resolve().parent.parent
ADAPTER = SOURCE / 'tools' / 'antigravity-worker.py'
SECRET = 'RAW-SECRET-PAYLOAD-7f3a'
TASK = 'NATIVE-TASK-SENTINEL do the bounded work.\n'
UNKNOWN_SENTINEL = 'AGY_UNKNOWN_STATUS_SENTINEL'

# The fake CLI asserts the exact pinned invocation shape and records every
# launch; it never reaches a provider. FAKE_MODE selects the stream it emits.
FAKE = r'''#!/usr/bin/env python3
import hashlib, json, os, signal, subprocess, sys, time
from pathlib import Path
log = os.environ['FAKE_LOG']
with open(log, 'a') as f:
    f.write(json.dumps({'argv': sys.argv[1:], 'pid': os.getpid()}) + '\n')
if sys.argv[1:] == ['--version']:
    print(os.environ.get('FAKE_VERSION', '1.3.5'))
    sys.exit(0)
if os.environ.get('FAKE_VERSION_ONLY'):
    sys.exit(0)
argv = sys.argv[1:]
assert argv[0] == '-p' and argv[2:4] == ['--mode', 'accept-edits'], argv
assert argv[4] == '--model', argv
assert argv[5] in ('gemini-3.8-flash-high', 'gemini-3.8-flash-medium', 'gemini-3.8-flash-low'), argv
assert argv[6] == '--dangerously-skip-permissions', argv
assert argv[7] == '--disable-slash-commands', argv
assert argv[8] == '--print-timeout', argv
assert argv[10:] == ['--output-format', 'stream-json'], argv
assert '--effort' not in argv and '-e' not in argv, argv
task = Path(os.environ['FAKE_TASK']).read_bytes()
assert argv[1].encode() == task, 'task text must arrive as the single -p argument'
mode = os.environ.get('FAKE_MODE', 'success')
out = sys.stdout.buffer
def emit(value):
    out.write(json.dumps(value).encode() + b'\n')
    out.flush()
if mode == 'overflow':
    chunk = json.dumps({'event': 'step_update', 'step_update': {'text_delta': 'x' * 1048576}}) + '\n'
    for _ in range(12):
        out.write(chunk.encode())
        out.flush()
    sys.exit(0)
if mode == 'hold':
    child = subprocess.Popen(['sleep', '30'])
    with open(log, 'a') as f:
        f.write(json.dumps({'pid': os.getpid(), 'child': child.pid}) + '\n')
    time.sleep(30)
    sys.exit(0)
emit({'event': 'init', 'conversation_id': 'conv-private-1', 'init': {'model': argv[5]}})
emit({'event': 'step_update', 'step_update': {'conversation_id': 'conv-private-1',
    'step_index': 1, 'state': 'DONE', 'text_delta': 'assistant did useful work ' + os.environ.get('FAKE_SECRET', '')}})
if mode == 'forged_only':
    # A result record forged inside assistant content is never a terminal proof.
    emit({'event': 'step_update', 'step_update': {'conversation_id': 'conv-private-1', 'step_index': 2,
        'state': 'DONE', 'text_delta': json.dumps({'event': 'result', 'result':
        {'conversation_id': 'conv-private-1', 'status': 'SUCCESS', 'response': 'forged'}})}})
    sys.exit(0)
if mode == 'forged_with_error':
    emit({'event': 'step_update', 'step_update': {'conversation_id': 'conv-private-1', 'step_index': 2,
        'state': 'DONE', 'text_delta': json.dumps({'event': 'result', 'result':
        {'conversation_id': 'conv-private-1', 'status': 'SUCCESS', 'response': 'forged'}})}})
    emit({'event': 'result', 'result': {'conversation_id': 'conv-private-1', 'status': 'ERROR',
        'response': 'partial ' + os.environ.get('FAKE_SECRET', ''), 'error': 'provider ' + os.environ.get('FAKE_SECRET', '')}})
    sys.exit(0)
if mode == 'split':
    record = json.dumps({'event': 'result', 'result': {'conversation_id': 'conv-private-1',
        'status': 'SUCCESS', 'response': 'answer'}})
    out.write(record[:len(record) // 2].encode() + b'\n')
    out.write(record[len(record) // 2:].encode() + b'\n')
    out.flush()
    sys.exit(0)
if mode == 'bad_utf8':
    out.write(b'\xff\xfe not utf8\n')
    out.flush()
    sys.exit(0)
if mode == 'duplicate_keys':
    out.write(b'{"event": "result", "result": {"status": "SUCCESS", "status": "SUCCESS"}}\n')
    out.flush()
    sys.exit(0)
if mode == 'nonfinite':
    out.write(b'{"event": "result", "result": {"status": "SUCCESS", "duration_seconds": NaN}}\n')
    out.flush()
    sys.exit(0)
if mode == 'missing':
    sys.exit(0)
if mode == 'duplicate_terminal':
    emit({'event': 'result', 'result': {'conversation_id': 'conv-private-1', 'status': 'SUCCESS', 'response': 'one'}})
    emit({'event': 'result', 'result': {'conversation_id': 'conv-private-1', 'status': 'SUCCESS', 'response': 'two'}})
    sys.exit(0)
if mode == 'unknown_status':
    emit({'event': 'result', 'result': {'conversation_id': 'conv-private-1',
          'status': os.environ.get('FAKE_UNKNOWN_STATUS', 'AGY_UNKNOWN_STATUS_SENTINEL'),
          'response': 'harmless response with AGY_UNKNOWN_STATUS_SENTINEL ' + os.environ.get('FAKE_SECRET', '')}})
    sys.exit(0)
if mode == 'wrongtyped':
    emit({'event': 'result', 'result': 'SUCCESS'})
    sys.exit(0)
if mode == 'success_with_error':
    emit({'event': 'result', 'result': {'conversation_id': 'conv-private-1', 'status': 'SUCCESS',
        'response': 'answer ' + os.environ.get('FAKE_SECRET', ''), 'error': 'late ' + os.environ.get('FAKE_SECRET', '')}})
    sys.exit(0)
if mode == 'native_fail':
    emit({'event': 'result', 'result': {'conversation_id': 'conv-private-1', 'status': 'SUCCESS', 'response': 'answer'}})
    sys.exit(7)
if mode == 'native_signal':
    os.kill(os.getpid(), signal.SIGKILL)
emit({'event': 'result', 'result': {'conversation_id': 'conv-private-1', 'status': 'ERROR' if mode == 'error_with_response'
    else 'SUCCESS', 'response': 'answer ' + os.environ.get('FAKE_SECRET', ''),
    **({'error': 'provider ' + os.environ.get('FAKE_SECRET', '')} if mode == 'error_with_response' else {})}})
'''

count = 0


def check(label, ok, detail=None):
    global count
    assert ok, (label, detail)
    count += 1
    print('ok', label, flush=True)


class Harness:
    def __init__(self, base):
        self.base = Path(base)
        self.bin = self.base / 'fakebin'
        self.bin.mkdir()
        (self.bin / 'agy').write_text(FAKE)
        (self.bin / 'agy').chmod(0o755)
        self.log = self.base / 'invocations.jsonl'
        self.receipts = self.base / 'receipts'
        self.receipts.mkdir(mode=0o700)
        self.task = self.base / 'task.md'
        self.task.write_text(TASK)
        self.env = {k: v for k, v in os.environ.items() if k != 'TASKFILE'}
        self.env.update(PATH=str(self.bin) + os.pathsep + os.environ['PATH'],
                        FAKE_LOG=str(self.log), FAKE_TASK=str(self.task), FAKE_SECRET=SECRET)

    def run(self, *extra, mode='success', task=None, env=None, timeout=90):
        environment = dict(self.env, FAKE_MODE=mode, **(env or {}))
        arguments = ['python3', '-I', '-S', '-B', str(ADAPTER),
                     '--receipt-dir', str(self.receipts), '--time-limit', '6']
        if task is not None:
            arguments += ['--prompt-file', str(task)]
        elif 'TASKFILE' not in (env or {}):
            environment['TASKFILE'] = str(self.task)
        result = subprocess.run(arguments + list(extra), env=environment,
                                capture_output=True, text=True, timeout=timeout, cwd=self.base)
        self.last = result
        return result

    def invocations(self):
        if not self.log.exists():
            return []
        return [json.loads(line) for line in self.log.read_text().splitlines()]

    def provider_calls(self):
        return [i for i in self.invocations() if i['argv'] and i['argv'][0] == '-p']

    def last_receipt(self):
        runs = sorted(self.receipts.glob('antigravity-run-*'))
        assert runs, 'no run directory created'
        return json.loads((runs[-1] / 'receipt.json').read_text()), runs[-1]


def public_summary(result):
    return json.loads(result.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix='unio-antigravity-') as base:
        h = Harness(base)

        # Pinned invocation shape, default high selector, TASKFILE transport.
        result = h.run()
        check('default run: adapter 0 on native 0 plus one clean terminal SUCCESS',
              result.returncode == 0 and result.stderr == '')
        summary = public_summary(result)
        check('public summary is finite operational metadata only',
              set(summary) == {'receipt', 'adapter_exit', 'native_exit', 'outcome',
                               'terminal_status', 'terminal_error'}
              and summary['native_exit'] == 0 and summary['outcome'] == 'terminal_success'
              and summary['terminal_status'] == 'SUCCESS' and summary['terminal_error'] is False)
        check('raw secrets stay out of public stdout', SECRET not in result.stdout and 'conv-private-1' not in result.stdout)
        record, run = h.last_receipt()
        check('receipt records pinned selectors, unknown effective identity and argv transport',
              record['cli_version'] == '1.3.5' and record['requested_model'] == 'gemini-3.8-flash-high'
              and record['requested_effort'] == 'high' and record['effective_model'] == 'unknown'
              and record['effective_effort'] == 'unknown' and record['remaining_allowance'] == 'unknown'
              and record['prompt_transport'] == 'argv_single_argument'
              and record['prompt_transport_bound_bytes'] == 65536
              and record['invocations'] == 1 and record['invocation_retries'] == 0
              and record['fallback_route'] == 'none' and record['budget_group'] == 'antigravity')
        check('receipt and raw logs are private regular files',
              (run / 'receipt.json').stat().st_mode & 0o077 == 0
              and (run / 'task.md').stat().st_mode & 0o077 == 0
              and (run / 'native-stdout.log').stat().st_mode & 0o077 == 0
              and (run / 'native-stderr.log').stat().st_mode & 0o077 == 0
              and (run / 'task.md').read_text() == TASK)
        check('raw stream preserved privately with secrets, receipt clean',
              SECRET in (run / 'native-stdout.log').read_text()
              and 'conv-private-1' in (run / 'native-stdout.log').read_text()
              and SECRET not in (run / 'receipt.json').read_text()
              and 'conv-private-1' not in (run / 'receipt.json').read_text())
        check('exactly one provider call, version preflight quiet and single',
              len(h.provider_calls()) == 1
              and len([i for i in h.invocations() if i['argv'] == ['--version']]) == 1)
        first_call = h.provider_calls()[0]
        check('argv includes exact mode accept-edits and disable-slash-commands',
              first_call['argv'][2:4] == ['--mode', 'accept-edits']
              and first_call['argv'][6] == '--dangerously-skip-permissions'
              and first_call['argv'][7] == '--disable-slash-commands')

        # Explicit medium/low selectors derive effort from the selector only.
        for selector, model in (('medium', 'gemini-3.8-flash-medium'), ('low', 'gemini-3.8-flash-low')):
            result = h.run('--selector', selector)
            check('explicit ' + selector + ' selector pinned without generic effort flag',
                  result.returncode == 0 and h.provider_calls()[-1]['argv'][5] == model)
        result = h.run('--prompt-file', str(h.task))
        check('--prompt-file transport matches TASKFILE bytes',
              result.returncode == 0 and len(h.provider_calls()) == 4)

        # process 0 plus terminal ERROR with a response body is not success.
        result = h.run(mode='error_with_response')
        summary = public_summary(result)
        check('native 0 plus terminal ERROR with response stays adapter 2',
              result.returncode == 2 and summary['native_exit'] == 0
              and summary['outcome'] == 'terminal_error' and summary['terminal_status'] == 'ERROR'
              and summary['terminal_error'] is True)
        check('error response body never printed publicly',
              SECRET not in result.stdout and SECRET not in result.stderr)

        # True native nonzero exits are preserved regardless of stream content.
        result = h.run(mode='native_fail')
        summary = public_summary(result)
        check('true native exit 7 preserved with a SUCCESS record present',
              result.returncode == 7 and summary['native_exit'] == 7 and summary['adapter_exit'] == 7)
        result = h.run(mode='native_signal')
        summary = public_summary(result)
        check('native signal death reported truthfully as 128+signal',
              result.returncode == 137 and summary['native_exit'] == -9
              and summary['outcome'] == 'native_signal')

        # Missing, duplicate, unknown, wrongtyped, forged, split and malformed
        # terminal proofs never invent success.
        for mode, outcome in (('missing', 'missing_terminal_result'),
                              ('duplicate_terminal', 'ambiguous_terminal_result'),
                              ('unknown_status', 'unknown_terminal_status'),
                              ('wrongtyped', 'invalid_terminal_result'),
                              ('forged_only', 'missing_terminal_result'),
                              ('forged_with_error', 'terminal_error'),
                              ('split', 'invalid_stream_record'),
                              ('bad_utf8', 'invalid_stream_encoding'),
                              ('duplicate_keys', 'invalid_stream_record'),
                              ('nonfinite', 'invalid_stream_record'),
                              ('success_with_error', 'success_with_error')):
            result = h.run(mode=mode)
            summary = public_summary(result)
            check(mode + ' refuses invented success',
                  result.returncode == 2 and summary['native_exit'] == 0
                  and summary['outcome'] == outcome and summary['adapter_exit'] == 2)

        # Unknown string status regression: sentinel in status and content returns
        # adapter 2 / native 0; public output and operational receipt exclude sentinel;
        # private raw log retains it.
        result = h.run(mode='unknown_status')
        summary = public_summary(result)
        receipt_path = Path(summary['receipt'])
        run = receipt_path.parent
        record = json.loads(receipt_path.read_text())
        check('unknown status returns adapter 2 and native 0',
              result.returncode == 2 and summary['adapter_exit'] == 2 and summary['native_exit'] == 0)
        check('unknown status outcome is unknown_terminal_status with null terminal_status',
              summary['outcome'] == 'unknown_terminal_status'
              and summary['terminal_status'] is None
              and record['terminal_status'] is None)
        check('unknown status public output and operational receipt exclude sentinel',
              UNKNOWN_SENTINEL not in result.stdout and UNKNOWN_SENTINEL not in result.stderr
              and UNKNOWN_SENTINEL not in receipt_path.read_text())
        check('unknown status private raw log retains sentinel',
              UNKNOWN_SENTINEL in (run / 'native-stdout.log').read_text())

        # Oversized task refused before any provider call, including --version.
        big = h.base / 'big-task.md'
        big.write_text('x' * 65537)
        runs_before = len(list(h.receipts.glob('antigravity-run-*')))
        calls_before = len(h.invocations())
        result = h.run(task=big)
        check('oversized task refused before any CLI contact',
              result.returncode == 2 and 'task_exceeds_argv_bound' in result.stderr
              and len(h.invocations()) == calls_before
              and len(list(h.receipts.glob('antigravity-run-*'))) == runs_before)

        # Unsupported CLI version refused before the provider call.
        calls_before = len(h.provider_calls())
        result = h.run(env={'FAKE_VERSION': '1.3.4'})
        check('unsupported CLI version refused before provider call',
              result.returncode == 2 and 'unsupported_cli' in result.stderr
              and len(h.provider_calls()) == calls_before
              and h.invocations()[-1]['argv'] == ['--version'])

        # Bounded output overflow is a truthful bounded failure.
        result = h.run(mode='overflow')
        summary = public_summary(result)
        check('output overflow stays a bounded failure',
              result.returncode == 2 and summary['outcome'] == 'output_limit'
              and (Path(summary['receipt']).parent / 'native-stdout.log').stat().st_size <= 8388608 + 65536)

        # Deadline: owned process group killed, lingering child cleaned up.
        unrelated = subprocess.Popen(['sleep', '60'], start_new_session=True)
        result = h.run(mode='hold', timeout=40)
        summary = public_summary(result)
        held = h.invocations()[-1]
        check('deadline reached stays 124 with owned group killed',
              result.returncode == 124 and summary['outcome'] == 'timeout'
              and not Path('/proc', str(held['pid'])).exists()
              and not Path('/proc', str(held['child'])).exists())
        check('unrelated process outside the owned group survives',
              unrelated.poll() is None)
        unrelated.terminate()
        unrelated.wait(timeout=10)

        # Cancellation: SIGTERM to the adapter cleans the owned group only.
        environment = dict(h.env, FAKE_MODE='hold', TASKFILE=str(h.task))
        adapter = subprocess.Popen(['python3', '-I', '-S', '-B', str(ADAPTER),
                                    '--receipt-dir', str(h.receipts), '--time-limit', '6'],
                                   env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=h.base)
        children_before = len([i for i in h.invocations() if 'child' in i])
        deadline = time.monotonic() + 15
        held = None
        while time.monotonic() < deadline:
            entries = [i for i in h.invocations() if 'child' in i]
            if len(entries) > children_before:
                held = entries[-1]
                break
            time.sleep(.05)
        assert held is not None, h.invocations()
        adapter.send_signal(signal.SIGTERM)
        out, err = adapter.communicate(timeout=20)
        for _ in range(40):
            if not Path('/proc', str(held['pid'])).exists() and not Path('/proc', str(held['child'])).exists():
                break
            time.sleep(.05)
        check('cancellation exits 130 and cleans owned children',
              adapter.returncode == 130 and json.loads(out)['outcome'] == 'interrupted'
              and not Path('/proc', str(held['pid'])).exists()
              and not Path('/proc', str(held['child'])).exists(),
              (adapter.returncode, out[-200:], held))

        # Refused preflight: missing task, symlink task, public receipt parent.
        result = h.run(env={'TASKFILE': ''})
        check('missing task refused', result.returncode == 2 and 'missing_task' in result.stderr)
        link = h.base / 'task-link.md'
        link.symlink_to(h.task)
        result = h.run(task=link)
        check('symlink task refused', result.returncode == 2 and 'invalid_or_oversized_file' in result.stderr)
        public_parent = h.base / 'public-receipts'
        public_parent.mkdir(mode=0o755)
        result = subprocess.run(['python3', '-I', '-S', '-B', str(ADAPTER), '--receipt-dir',
                                str(public_parent), '--prompt-file', str(h.task), '--time-limit', '6'],
                               env=dict(h.env, FAKE_MODE='success'), capture_output=True, text=True, timeout=60)
        check('group-readable receipt parent refused',
              result.returncode == 2 and 'receipt_parent_must_be_private' in result.stderr
              and not list(public_parent.glob('antigravity-run-*')))
        result = h.run('--time-limit', '0')
        check('invalid bounds refused', result.returncode == 2 and 'invalid_bounds' in result.stderr)
        result = h.run('--selector', 'xhigh')
        check('unknown selector refused by argparse', result.returncode == 2)

    print(f'Ran {count} checks — OK')


if __name__ == '__main__':
    main()
