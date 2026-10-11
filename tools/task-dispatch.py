#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Explicit owner-granted dispatch over the existing execution service.

Prepare, approve and start each delegate to one ExecutionService call. A fresh
start first rebuilds the checked task plan inside the service lock; replays
return existing evidence. No scheduler, retry, automatic approval, review,
acceptance or merge. Launcher acceptance is not task success.
"""

import argparse
import contextlib
import hashlib
import importlib.util
import io
import json
import os
import re
import signal
import sys
import time
from pathlib import Path

SCHEMA_VERSION = 1
MAX_GRANT_BYTES = 16 * 1024
MAX_PATH_CHARS = 4096
MAX_REASONS = 16
MAX_REASON_CHARS = 160
GRANT_FIELDS = ('schema_version', 'project', 'engine', 'config_dir', 'template_path',
                'worker', 'reviewer', 'worker_lab', 'reviewer_lab')
HEX32 = re.compile(r'[0-9a-f]{32}')
HEX64 = re.compile(r'[0-9a-f]{64}')
LABEL = re.compile(r'[a-z][a-z0-9_-]{0,63}')
# Codes whose effect on durable state cannot be ruled out.
UNKNOWN_CODES = frozenset(('outcome_unknown', 'storage_unavailable'))
EXIT_OK, EXIT_REFUSED, EXIT_UNKNOWN = 0, 1, 3


def fail(message, code=2):
    sys.stderr.write('unio dispatch: ' + message + '\n')
    raise SystemExit(code)


def load_module(name, path):
    if not path.is_file():
        fail('helper missing from installed library: ' + str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_planner():
    return load_module('task_plan', Path(__file__).resolve().parent / 'task-plan.py')


def load_service():
    here = Path(__file__).resolve().parent
    installed = here / 'browser/execution_service.py'
    source = here.parent / 'bridge/execution_service.py'
    return load_module('execution_service', installed if installed.is_file() else source)


def physical_path(grant, key, directory):
    value = grant[key]
    if (not isinstance(value, str) or not value or len(value) > MAX_PATH_CHARS
            or any(ord(char) < 32 or ord(char) == 127 for char in value)
            or not os.path.isabs(value) or os.path.normpath(value) != value
            or os.path.realpath(value) != value):
        fail('grant ' + key + ' must be an absolute physical path')
    if directory and not os.path.isdir(value):
        fail('grant ' + key + ' must be an existing directory')
    if not directory and not os.path.isfile(value):
        fail('grant ' + key + ' must be an existing regular file')
    return value


def read_grant(path, planner):
    try:
        raw, _ = planner.read_regular(Path(path), MAX_GRANT_BYTES)
    except FileNotFoundError:
        fail('grant file does not exist')
    except ValueError as error:
        if str(error) == 'input_file_exceeds_bound':
            fail('grant file exceeds 16 KiB limit')
        fail('grant file must be regular and bounded')
    except OSError:
        fail('grant file must not be a symlink or have symlink components; it must be readable')
    grant = planner.parse_strict_json(raw)
    if grant is None:
        fail('grant is not a strict UTF-8 JSON object')
    if set(grant) != set(GRANT_FIELDS):
        fail('grant must contain exactly ' + ', '.join(GRANT_FIELDS))
    if type(grant['schema_version']) is not int or grant['schema_version'] != 1:
        fail('grant schema_version must be integer 1')
    for key in ('project', 'config_dir'):
        physical_path(grant, key, True)
    for key in ('engine', 'template_path'):
        physical_path(grant, key, False)
    if not os.access(grant['engine'], os.X_OK):
        fail('grant engine must be executable')
    for key in ('worker', 'reviewer'):
        if not isinstance(grant[key], str) or LABEL.fullmatch(grant[key]) is None:
            fail('grant ' + key + ' must be a lowercase worker label')
    for key in ('worker_lab', 'reviewer_lab'):
        value = grant[key]
        if (not isinstance(value, str) or not value.strip() or len(value) > 100
                or any(ord(char) < 32 or ord(char) == 127 for char in value)):
            fail('grant ' + key + ' must be a printable label of at most 100 characters')
    if grant['worker_lab'] == grant['reviewer_lab']:
        fail('grant worker_lab and reviewer_lab must differ')
    root = Path(grant['project'])
    for required in ('coord', 'wt'):
        if (root / required).is_symlink() or not (root / required).is_dir():
            fail('granted project requires physical coord/ and wt/ directories')
    return grant


def read_inventory(planner, path, expected):
    """Bounded no-follow read, exact hash, then the planner's schema-1 checks."""
    try:
        raw, info = planner.read_regular(Path(path), planner.MAX_INVENTORY_BYTES)
    except (OSError, ValueError):
        return None, 'inventory_unreadable'
    if hashlib.sha256(raw).hexdigest() != expected:
        return None, 'inventory_hash_mismatch'
    diagnostics = io.StringIO()
    try:
        with contextlib.redirect_stderr(diagnostics):
            inventory, _ = planner.validate_inventory(raw)
    except SystemExit:
        return None, 'inventory_invalid'
    return (inventory, raw, max(0.0, time.time() - info.st_mtime)), None


def bounded_reasons(reasons):
    result = []
    for reason in list(reasons)[:MAX_REASONS]:
        text = str(reason).encode('ascii', 'backslashreplace').decode('ascii')
        result.append(text[:MAX_REASON_CHARS])
    return result


class Preflight:
    """Fresh-start check; the service calls it once inside its coordination lock."""

    def __init__(self, service_module, planner, grant, runner, inventory_path, inventory_sha256, timeout):
        self.error = service_module.ExecutionError
        self.planner, self.grant, self.runner = planner, grant, runner
        self.inventory_path, self.inventory_sha256 = inventory_path, inventory_sha256
        self.timeout = timeout
        self.state = 'not_run'
        self.reason = None
        self.plan = None

    def __call__(self, binding):
        self.state = 'running'
        try:
            code, reason = self.check(binding)
        except Exception:  # noqa: BLE001 - every unexpected planner failure refuses
            code, reason = 'not_ready', 'plan_unavailable'
        except SystemExit:
            code, reason = 'not_ready', 'plan_unavailable'
        if reason is not None:
            self.state, self.reason = 'refused', reason
            raise self.error(code)
        self.state = 'passed'

    def check(self, binding):
        planner = self.planner
        planner.OBSERVATION_DEADLINE = time.monotonic() + self.timeout
        loaded, reason = read_inventory(planner, self.inventory_path, self.inventory_sha256)
        if reason:
            return 'conflict', reason
        inventory, raw, age = loaded
        job_id, preview = binding['job_id'], binding['preview']
        task_id = preview['task_id']
        rows = [row for row in inventory['tasks']
                if row['id'] == task_id or row.get('job_id') == job_id]
        if not rows:
            return 'conflict', 'inventory_row_missing'
        if len(rows) != 1:
            return 'conflict', 'inventory_row_ambiguous'
        row = rows[0]
        if (row['id'] != task_id or row.get('job_id') != job_id
                or row['worker'] != self.grant['worker'] or preview['worker'] != self.grant['worker']
                or row['task_sha256'] != preview['task_sha256']):
            return 'conflict', 'inventory_binding_mismatch'
        if inventory['base_revision'] != binding['base_revision']:
            return 'conflict', 'inventory_base_mismatch'
        report = planner.build_plan(Path(self.grant['project']), inventory, raw, age,
                                    self.timeout, runner=self.runner)
        selected = [task for task in report['tasks']
                    if task['id'] == task_id or task['job_id'] == job_id]
        if (len(selected) != 1 or selected[0]['id'] != task_id or selected[0]['job_id'] != job_id
                or selected[0]['worker'] != self.grant['worker']
                or report['inventory_hash'] != self.inventory_sha256
                or report['base_revision'] != binding['base_revision']):
            return 'conflict', 'plan_binding_mismatch'
        task = selected[0]
        self.plan = dict(status=task['status'], reasons=bounded_reasons(task['reasons']),
                         stop=bool(report['stop']), head_matches_base=(
                             report['head_revision'] == binding['base_revision']))
        if task['status'] != 'ready' or report['head_revision'] != binding['base_revision']:
            return 'not_ready', 'plan_' + task['status']
        return None, None


def summarize(view):
    job, preview = view['job'], view['preview']
    return dict(
        job=dict(id=job['id'], state=job['state'], worker=job['worker'],
                 draft_sha256=job['draft_sha256']),
        task=dict(id=preview['task_id'], sha256=preview['task_sha256']),
        preview_sha256=preview['preview_hash'],
        execution=dict(state=view['execution']['state'],
                       launcher_exit=view['execution']['launcher_exit']),
        warnings=bounded_reasons(view['warnings']))


def view_outcome(operation, view):
    warnings = view['warnings']
    if 'outcome_unknown' in warnings:
        return 'unknown'
    if operation == 'prepare':
        return 'prepared'
    if operation == 'approve':
        return 'approved' if view['job']['state'] == 'approved' else 'unknown'
    execution = view['execution']['state']
    if execution == 'launch_accepted':
        return 'launch_accepted'
    if execution == 'launch_failed':
        return 'launch_failed'
    return 'unknown'


def error_outcome(operation, code, preflight):
    if code in UNKNOWN_CODES:
        return 'unknown'
    if operation == 'start' and preflight is not None and preflight.state == 'passed':
        # After a passed preflight the service may already have reserved or launched.
        return 'launch_failed' if code == 'native_unavailable' else 'unknown'
    return 'refused'


def render_text(report):
    lines = ['Dispatch ' + report['operation'] + ': ' + report['outcome']]
    if report['error']:
        lines.append('Error: ' + report['error'] + (' (' + report['reason'] + ')' if report['reason'] else ''))
    if report['job']:
        job = report['job']
        lines.append('Job: {} (state {}, worker {})'.format(job['id'], job['state'], job['worker']))
        lines.append('Draft sha256: ' + job['draft_sha256'])
        lines.append('Task: {} sha256 {}'.format(report['task']['id'], report['task']['sha256']))
        lines.append('Preview sha256: ' + report['preview_sha256'])
        execution = report['execution']
        exit_text = '' if execution['launcher_exit'] is None else ' (launcher exit {})'.format(
            execution['launcher_exit'])
        lines.append('Execution: ' + execution['state'] + exit_text)
    if report['replay'] is not None:
        lines.append('Replay: ' + ('yes, existing evidence; no new launch' if report['replay'] else 'no'))
    if report['plan']:
        plan = report['plan']
        lines.append('Plan: ' + plan['status'] + (' (' + ', '.join(plan['reasons']) + ')'
                                                    if plan['reasons'] else ''))
    if report['warnings']:
        lines.append('Warnings: ' + ', '.join(report['warnings']))
    if report['operation'] == 'prepare' and report['outcome'] == 'prepared':
        lines.append('Inspect coord/ui-execution/bindings/' + report['job']['id']
                     + '.md before an explicit approve.')
    lines.append('Launcher acceptance is not task success, review or integration.')
    return '\n'.join(lines)


def build_parser():
    parser = argparse.ArgumentParser(
        prog='unio dispatch', allow_abbrev=False,
        description='Explicit owner-granted dispatch: prepare, approve, or start one job '
                    'through the existing execution service. No scheduler or retries.')
    parser.add_argument('--grant', metavar='PATH', required=True,
                        help='physical schema-1 owner grant JSON (at most 16 KiB)')
    parser.add_argument('--project', metavar='PATH',
                        help='optional project root; must equal the granted project')
    parser.add_argument('--json', action='store_true',
                        help='write exactly one schema-1 JSON object')
    operations = parser.add_subparsers(dest='operation', metavar='OPERATION', required=True)
    prepare = operations.add_parser('prepare', allow_abbrev=False,
                                    help='bind a saved draft to a job (no provider call)')
    prepare.add_argument('--draft-id', required=True, metavar='ID')
    prepare.add_argument('--draft-sha256', required=True, metavar='HASH')
    prepare.add_argument('--request-key', required=True, metavar='KEY')
    approve = operations.add_parser('approve', allow_abbrev=False,
                                    help='record explicit owner approval (no provider call)')
    approve.add_argument('--job-id', required=True, metavar='ID')
    approve.add_argument('--draft-sha256', required=True, metavar='HASH')
    approve.add_argument('--preview-sha256', required=True, metavar='HASH')
    approve.add_argument('--approval-key', required=True, metavar='KEY')
    start = operations.add_parser('start', allow_abbrev=False,
                                  help='one explicit native launch after a fresh ready plan')
    start.add_argument('--job-id', required=True, metavar='ID')
    start.add_argument('--approval-key', required=True, metavar='KEY')
    start.add_argument('--reservation-key', required=True, metavar='KEY')
    start.add_argument('--inventory', required=True, metavar='PATH',
                       help='schema-1 task inventory naming ui-JOB_ID with its job_id')
    start.add_argument('--inventory-sha256', required=True, metavar='HASH')
    start.add_argument('--timeout', type=int, default=10, metavar='SECONDS',
                       help='plan observation deadline, 1..60 seconds (default 10)')
    return parser


def validate_arguments(args):
    for name in ('draft_id', 'job_id', 'request_key', 'approval_key', 'reservation_key'):
        value = getattr(args, name, None)
        if value is not None and HEX32.fullmatch(value) is None:
            fail('--' + name.replace('_', '-') + ' must be 32 lowercase hex characters')
    for name in ('draft_sha256', 'preview_sha256', 'inventory_sha256'):
        value = getattr(args, name, None)
        if value is not None and HEX64.fullmatch(value) is None:
            fail('--' + name.replace('_', '-') + ' must be a 64-character lowercase SHA-256')
    if args.operation == 'start':
        if not 1 <= args.timeout <= 60:
            fail('--timeout must be 1..60 seconds')
        if not args.inventory:
            fail('--inventory PATH is required')


def main(argv=None):
    native = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    if native[:1] in (['-h'], ['--help']):
        parser.print_help()
        return 0
    if not native:
        fail('arguments missing; pass --help for usage')
    if native[0].startswith('-'):
        fail('installed runner path missing')
    runner = native.pop(0)
    args = parser.parse_args(native)
    validate_arguments(args)

    planner = load_planner()
    grant = read_grant(args.grant, planner)
    if os.path.realpath(os.path.abspath(runner)) != grant['engine']:
        fail('grant engine does not match the invoked Unio executable')
    if args.project is not None and os.path.realpath(os.path.abspath(args.project)) != grant['project']:
        fail('--project does not match the granted project')
    configured = os.environ.get('UNIO_CONF_DIR')
    if configured is not None and os.path.realpath(os.path.abspath(configured)) != grant['config_dir']:
        fail('UNIO_CONF_DIR does not match the granted config_dir')
    # The planner's fleet observation must read the same configuration as the launch.
    os.environ['UNIO_CONF_DIR'] = grant['config_dir']
    if args.operation == 'start':
        _, reason = read_inventory(planner, args.inventory, args.inventory_sha256)
        if reason:
            fail('start refused before the service: ' + reason, EXIT_REFUSED)

    module = load_service()
    report = dict(schema_version=SCHEMA_VERSION, operation=args.operation, outcome='refused',
                  error=None, reason=None, replay=None, job=None, task=None, preview_sha256=None,
                  execution=None, warnings=[], plan=None)
    preflight = None
    try:
        service = module.ExecutionService(
            grant['project'], grant['engine'], grant['worker'], grant['reviewer'],
            grant['config_dir'], grant['template_path'], grant['worker_lab'], grant['reviewer_lab'])
    except module.ExecutionError as error:
        report.update(error=error.code, reason='service_unavailable')
    else:
        try:
            if args.operation == 'prepare':
                view = service.prepare(args.draft_id, args.draft_sha256, args.request_key)
            elif args.operation == 'approve':
                view = service.approve(args.job_id, args.draft_sha256, args.approval_key,
                                       args.preview_sha256)
            else:
                preflight = Preflight(module, planner, grant, grant['engine'], args.inventory,
                                      args.inventory_sha256, args.timeout)
                view = service.start(args.job_id, args.approval_key, args.reservation_key,
                                     preflight=preflight)
            report.update(summarize(view))
            report['outcome'] = view_outcome(args.operation, view)
        except module.ExecutionError as error:
            report.update(error=error.code,
                          outcome=error_outcome(args.operation, error.code, preflight))
            if preflight is not None and preflight.state == 'refused':
                report['reason'] = preflight.reason
        finally:
            service.close()
    if preflight is not None:
        report['replay'] = preflight.state == 'not_run' and report['error'] is None
        report['plan'] = preflight.plan
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + '\n')
    else:
        sys.stdout.write(render_text(report) + '\n')
    if report['outcome'] in ('prepared', 'approved', 'launch_accepted'):
        return EXIT_OK
    return EXIT_UNKNOWN if report['outcome'] == 'unknown' else EXIT_REFUSED


if __name__ == '__main__':
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write('unio dispatch: interrupted; any started outcome stays unknown\n')
        raise SystemExit(130)
