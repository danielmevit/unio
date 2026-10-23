# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Explicit, at-most-once native execution over the frozen draft/job stores.

The coordination lock serializes service writers across threads and processes.
Native Unio retains its own worker lock. Neither a receipt nor reading a result
is authority to launch, retry, release ownership or spend on a review.
"""
from contextlib import contextmanager
from datetime import datetime
import copy
import fcntl
import functools
import hashlib
import inspect
import json
import os
from pathlib import Path
import re
import selectors
import signal
import sqlite3
import stat
import subprocess
import threading
import time
import unicodedata
import uuid

try:
    from job_store import JobStore
    from plan_store import PlanStore
except ImportError:
    import importlib.util

    def _load(name):
        spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module

    JobStore = _load('job_store').JobStore
    PlanStore = _load('plan_store').PlanStore

JSON_LIMIT = 128 * 1024
OUTPUT_LIMIT = 1024 * 1024
CONFIG_LIMIT = 8 * 1024 * 1024
CONFIG_FILES = 128
DEADLINES = dict(result=15, run=30, verify=900, review=1200, kill=30)
LOCK_TIMEOUT = 10
HEX32 = re.compile(r'[0-9a-f]{32}')
HEX64 = re.compile(r'[0-9a-f]{64}')
GIT_ID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')
LABEL = re.compile(r'[a-z][a-z0-9_-]{0,63}')
# Native engine identities are wider than public HTTP/draft input labels.
NATIVE_REVIEWER = re.compile(r'[a-zA-Z0-9_][a-zA-Z0-9_-]{0,127}')
ERRORS = dict(invalid_request=400, job_not_found=404, conflict=409, draft_stale=409,
              binding_stale=409, worker_unavailable=409, stopped=409, not_ready=409,
              outcome_unknown=409, storage_unavailable=503, native_unavailable=503)
REASONS = frozenset(('missing_scope', 'missing_validate', 'scope_violation', 'check_failed',
                     'empty_work', 'task_tampered', 'candidate_changed_during_validation',
                     'delivery_failed', 'invalid_report_artifact',
                     'budget_refused', 'reviewer_process_failed', 'unknown_verdict', 'candidate_changed_during_review'))
WARNINGS = frozenset(('native_result_unavailable', 'native_result_invalid', 'binding_stale',
                      'draft_stale', 'outcome_unknown', 'ownership_unknown', 'stopped'))
REVISION_FIELDS = {'base_commit', 'candidate_commit', 'task_sha256', 'worktree_sha256'}


class ExecutionError(Exception):
    """Fixed public error; never exposes an internal exception or host path."""
    def __init__(self, code, status=None):
        if code not in ERRORS or (status is not None and status != ERRORS[code]):
            raise ValueError('unsupported execution error')
        self.code, self.status = code, ERRORS[code]
        super().__init__(code)


class _NativeFailure(Exception):
    def __init__(self, started, exit_code=None):
        self.started, self.exit_code = started, exit_code


def _public(method):
    signature = inspect.signature(method)
    @functools.wraps(method)
    def wrapped(self, *args, **kwargs):
        try:
            signature.bind(self, *args, **kwargs)
        except TypeError as error:
            raise ExecutionError('invalid_request') from error
        try:
            return method(self, *args, **kwargs)
        except ExecutionError:
            raise
        except (OSError, sqlite3.Error, ValueError, TypeError, KeyError, UnicodeError, RecursionError, OverflowError) as error:
            raise ExecutionError('storage_unavailable') from error
    return wrapped


def _json_bytes(value):
    return _canonical(value) + b'\n'


def _canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(',', ':')).encode()


def _stored(value):
    """Durable companion bytes; unescaped UTF-8 keeps valid Unicode text within bounds.

    Values that cannot be UTF-8 (lone surrogates from a JSON-escaped draft) keep
    the escaped form. Both decode to the identical value, so canonical hashes
    (always computed with _canonical) never depend on the stored encoding.
    """
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode() + b'\n'
    except UnicodeEncodeError:
        return _json_bytes(value)


def _hash(raw):
    return hashlib.sha256(raw).hexdigest()


def _pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


def _decode(raw):
    return json.loads(raw, object_pairs_hook=_pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('invalid number')))


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def _path_control(value):
    return any(unicodedata.category(char) in ('Cc', 'Zl', 'Zp') for char in value)


def _input(pattern, value):
    if not _matches(pattern, value):
        raise ExecutionError('invalid_request')


def _real_path(value, directory=False):
    path = Path(value).absolute()
    if path.resolve() != path:
        raise ValueError('symlink path')
    info = path.lstat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError('unsupported path')
    return path


def _read(path, limit=JSON_LIMIT):
    _real_path(path)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, 'rb') as source:
        if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
            raise ValueError('unsupported file')
        data = source.read(limit + 1)
    if len(data) > limit:
        raise ValueError('oversized file')
    return data


def _revision(value):
    if not isinstance(value, dict) or set(value) != REVISION_FIELDS:
        raise ValueError('invalid revision')
    for key in REVISION_FIELDS:
        if not _matches(GIT_ID if key.endswith('_commit') else HEX64, value[key]):
            raise ValueError('invalid revision value')
    return dict(value)


def _admission_only(row, projection):
    """Validate additive native evidence, never trust an isolated exclusion flag."""
    proof = row.get('admission_evidence')
    if proof is None:
        return False
    if not isinstance(proof, dict) or set(proof) != {'receipt', 'context'}:
        raise ValueError('invalid review admission evidence')
    receipt, context = proof['receipt'], proof['context']
    receipt_fields = {'schema_version', 'material_protocol', 'id', 'worker', 'task', 'reviewer',
        'recorded_at', 'policy_group', 'requested_model', 'effective_model', 'requested_effort',
        'effective_effort', 'state', 'process_exit_code', 'material_complete', 'reasons',
        'before', 'after', 'material_sha256', 'stdout', 'stderr'}
    empty = {'bytes': 0, 'sha256': 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855'}
    if (not isinstance(receipt, dict) or set(receipt) != receipt_fields
            or any(receipt.get(k) != 'unknown' for k in
                   ('requested_model', 'effective_model', 'requested_effort', 'effective_effort'))
            or not isinstance(receipt.get('recorded_at'), str) or len(receipt['recorded_at']) > 64
            or datetime.fromisoformat(receipt['recorded_at']).tzinfo is None
            or not isinstance(context, dict)
            or set(context) != {'schema_version', 'reviewer', 'config_sha256', 'command_sha256'}
            or type(context.get('schema_version')) is not int or context['schema_version'] != 2
            or context.get('reviewer') != row.get('reviewer')
            or not _matches(HEX64, context.get('config_sha256'))
            or not _matches(HEX64, context.get('command_sha256'))
            or type(receipt.get('schema_version')) is not int or receipt['schema_version'] != 2
            or type(receipt.get('material_protocol')) is not int or receipt['material_protocol'] != 2
            or receipt.get('worker') != projection['worker'] or receipt.get('task') != projection['task']
            or receipt.get('before') != projection['current_revision']
            or receipt.get('after') != projection['current_revision']
            or receipt.get('material_sha256') != projection['material_protocols']['2']
            or not _matches(HEX64, receipt.get('material_sha256'))
            or any(receipt.get(key) != row.get(field) for key, field in
                   (('id', 'receipt_id'), ('reviewer', 'reviewer'), ('policy_group', 'policy_group')))
            or receipt.get('state') != 'unknown' or row.get('state') != 'unknown'
            or receipt.get('process_exit_code') is not None or row.get('process_exit_code') is not None
            or receipt.get('material_complete') is not False
            or receipt.get('reasons') != ['budget_refused'] or row.get('reasons') != ['budget_refused']
            or receipt.get('stdout') != empty or receipt.get('stderr') != empty
            or any(type(receipt[k]['bytes']) is not int for k in ('stdout', 'stderr'))
            or row.get('protocol') != 2 or row.get('config_current') is not True
            or row.get('findings_state') != 'not_extracted' or row.get('findings_count') is not None
            or row.get('block_line') is not None):
        raise ValueError('invalid review admission binding')
    return True


def _current_review(projection, worker, task, current):
    """Check the canonical observation, never a worker's isolated ready flag."""
    if (not isinstance(projection, dict) or type(projection.get('schema_version')) is not int
            or projection['schema_version'] != 1 or projection.get('view') != 'findings'
            or projection.get('worker') != worker or projection.get('task') != task
            or projection.get('ai_lab_independence') != 'unknown'
            or projection.get('human_acceptance') is not False):
        raise ValueError('invalid current review identity')
    revision = projection.get('current_revision')
    if revision is not None:
        revision = _revision(revision)
    if revision != current:
        raise ValueError('stale current review')
    for key in ('incomplete', 'verdict_incomplete', 'extraction_complete',
                'machine_review_ready', 'verdict_disagreement'):
        if type(projection.get(key)) is not bool:
            raise ValueError('invalid current review flags')
    if (projection.get('decision') not in ('no_structured_findings', 'findings_attention',
                                         'not_run', 'unstructured_legacy', 'incomplete')
            or projection.get('verdict_decision') not in ('all_recorded_approved',
                'changes_requested', 'not_run', 'incomplete')):
        raise ValueError('invalid current review decision')
    lists = {}
    for key in ('expected_reviewers', 'missing_reviewers', 'distinct_reviewers', 'policy_groups', 'reasons'):
        value = projection.get(key)
        if (not isinstance(value, list) or len(value) > 256
                or any(not isinstance(x, str) or len(x) > 160 for x in value)
                or len(set(value)) != len(value)):
            raise ValueError('invalid current review list')
        lists[key] = value
    for key in ('expected_reviewers', 'missing_reviewers', 'distinct_reviewers'):
        if any(not _matches(NATIVE_REVIEWER, x) for x in lists[key]):
            raise ValueError('invalid current reviewer')
    counts = projection.get('counts')
    keys = {'approved', 'changes_requested', 'unknown', 'failed', 'stale', 'unresolved', 'recorded', 'current'}
    if (not isinstance(counts, dict) or set(counts) != keys
            or any(type(v) is not int or not 0 <= v <= 256 for v in counts.values())):
        raise ValueError('invalid current review counts')
    protocols = projection.get('material_protocols')
    if (not isinstance(protocols, dict) or set(protocols) != {'1', '2'}
            or any(value is not None and not _matches(HEX64, value) for value in protocols.values())
            or (projection.get('material_sha256') is not None
                and not _matches(HEX64, projection['material_sha256']))):
        raise ValueError('invalid current review material')
    evidence = projection.get('evidence')
    findings = projection.get('findings')
    if (not isinstance(evidence, list) or len(evidence) > 256 or counts['recorded'] != len(evidence)
            or not isinstance(findings, list) or len(findings) > 4096):
        raise ValueError('invalid current review evidence')
    active = []; ids = set()
    for row in evidence:
        if (not isinstance(row, dict) or type(row.get('current')) is not bool
                or type(row.get('stale')) is not bool
                or row.get('state') not in ('approved', 'changes_requested', 'unknown', 'failed')
                or not isinstance(row.get('reasons'), list)
                or any(not isinstance(reason, str) or len(reason) > 160 for reason in row['reasons'])
                or not _matches(re.compile(re.escape(task) + r'\.review\.[A-Za-z0-9]{8}'), row.get('raw_directory'))
                or row.get('findings_state') not in ('not_extracted', 'empty', 'findings',
                    'unstructured_legacy', 'missing_block', 'invalid_block', 'multiple_blocks',
                    'oversized_block', 'overflow')
                or (row.get('protocol') is not None and (type(row['protocol']) is not int
                    or row['protocol'] not in (1, 2)))
                or (row.get('findings_count') is not None and (type(row['findings_count']) is not int
                    or not 0 <= row['findings_count'] <= 4096))
                or (row.get('block_line') is not None and (type(row['block_line']) is not int
                    or not 1 <= row['block_line'] <= 16 * 1024 * 1024))):
            raise ValueError('invalid current review row')
        if row['current']:
            receipt = row.get('receipt_id')
            if (row['stale'] or not _matches(HEX32, receipt) or receipt in ids
                    or not _matches(NATIVE_REVIEWER, row.get('reviewer'))
                    or (row.get('process_exit_code') is not None
                        and (type(row['process_exit_code']) is not int
                             or not 0 <= row['process_exit_code'] <= 2147483647))):
                raise ValueError('invalid bound current review')
            ids.add(receipt); active.append(row)
    if (counts['current'] != len(active) or counts['stale'] != sum(r['stale'] for r in evidence)
            or any(counts[state] != sum(r['state'] == state for r in active)
                   for state in ('approved', 'changes_requested', 'unknown', 'failed'))
            or sorted({r['reviewer'] for r in active if r['process_exit_code'] is not None}) != sorted(lists['distinct_reviewers'])
            or sorted(set(lists['expected_reviewers']) - set(lists['distinct_reviewers'])) != sorted(lists['missing_reviewers'])):
        raise ValueError('inconsistent current review counts')
    verdicts = [row for row in active if not _admission_only(row, projection)]
    ready = bool(current is not None and verdicts and not findings and not lists['reasons']
        and not lists['missing_reviewers'] and not counts['unresolved']
        and not projection['incomplete'] and not projection['verdict_incomplete']
        and projection['extraction_complete'] and not projection['verdict_disagreement']
        and projection['decision'] == 'no_structured_findings'
        and projection['verdict_decision'] == 'all_recorded_approved'
        and _matches(HEX64, projection.get('material_sha256'))
        and isinstance(projection.get('material_protocols'), dict)
        and projection['material_protocols'].get('2') == projection['material_sha256']
        and all(r['state'] == 'approved' and r['process_exit_code'] == 0
                and r.get('config_current') is True and r.get('protocol') == 2
                and r.get('findings_state') == 'empty' and r.get('findings_count') == 0
                and type(r.get('block_line')) is int and r['block_line'] > 0
                and not r['reasons'] for r in verdicts))
    if projection['machine_review_ready'] != ready:
        raise ValueError('inconsistent current review readiness')
    return ready


def _native_document(document, worker, task):
    """Validate known fields before whitelisting; private producer extras vanish."""
    if (not isinstance(document, dict) or type(document.get('schema_version')) is not int
            or document['schema_version'] != 1 or document.get('worker') != worker
            or document.get('task') != task):
        raise ValueError('invalid native identity')
    updated = document.get('updated_at')
    if (not isinstance(updated, str) or len(updated) > 64
            or datetime.fromisoformat(updated).tzinfo is None):
        raise ValueError('invalid native date')
    if 'current_revision' not in document:
        raise ValueError('missing current revision')
    current = document['current_revision']
    if current is not None:
        current = _revision(current)
    if any(type(document.get(key)) is not bool for key in ('stale', 'ready_for_human_review')):
        raise ValueError('invalid native readiness')
    result = dict(worker=worker, task=task, updated_at=updated, current_revision=current)
    fields = dict(process=('state', 'exit_code', 'revision'),
                  validation=('state', 'scope', 'checks_run', 'checks_failed', 'reasons', 'revision'),
                  review=('state', 'reviewer', 'process_exit_code', 'material_complete', 'reasons', 'revision'))
    states = dict(process=('not_run', 'running', 'succeeded', 'failed'),
                  validation=('not_run', 'passed', 'failed', 'incomplete'),
                  review=('not_run', 'approved', 'changes_requested', 'unknown', 'failed'))
    for name, keys in fields.items():
        section = document.get(name)
        if not isinstance(section, dict) or any(key not in section for key in keys):
            raise ValueError('missing evidence')
        section = {key: section[key] for key in keys}
        if section['state'] not in states[name]:
            raise ValueError('invalid evidence state')
        if section['revision'] is not None:
            section['revision'] = _revision(section['revision'])
        elif section['state'] != 'not_run':
            raise ValueError('missing evidence revision')
        if name in ('process', 'review'):
            code = section['exit_code' if name == 'process' else 'process_exit_code']
            if code is not None and (type(code) is not int or not 0 <= code <= 2147483647):
                raise ValueError('invalid native exit')
        if name in ('validation', 'review'):
            reasons = section['reasons']
            if (not isinstance(reasons, list) or len(reasons) > 30
                    or any(not isinstance(reason, str) or reason not in REASONS for reason in reasons)):
                raise ValueError('invalid native reasons')
        result[name] = section
    p, v, r = (result[key] for key in ('process', 'validation', 'review'))
    if ((p['state'] == 'succeeded' and p['exit_code'] != 0)
            or (p['state'] in ('not_run', 'running') and p['exit_code'] is not None)
            or (p['state'] == 'failed' and p['exit_code'] == 0)):
        raise ValueError('inconsistent worker exit')
    if (v['scope'] not in ('OK', 'VIOLATION', 'UNCHECKED')
            or any(type(v[key]) is not int or not 0 <= v[key] <= 1000000
                   for key in ('checks_run', 'checks_failed'))
            or v['checks_failed'] > v['checks_run']):
        raise ValueError('invalid native checks')
    if v['state'] == 'passed' and (v['scope'] != 'OK' or v['checks_run'] < 1
                                   or v['checks_failed'] != 0 or v['reasons']):
        raise ValueError('inconsistent validation')
    if (type(r['material_complete']) is not bool
            or (r['reviewer'] is not None and not _matches(NATIVE_REVIEWER, r['reviewer']))):
        raise ValueError('invalid reviewer')
    if r['state'] in ('approved', 'changes_requested') and (
            r['process_exit_code'] != 0 or not r['material_complete'] or not r['reviewer'] or r['reasons']):
        raise ValueError('inconsistent review decision')
    if r['state'] == 'failed' and r['process_exit_code'] in (None, 0):
        raise ValueError('inconsistent review failure')
    stale = document['stale'] or current is None or any(
        section['revision'] != current for section in (p, v, r) if section['state'] != 'not_run')
    # An explicitly failed post-run snapshot must never become ready after filtering.
    if 'post_run_snapshot' in document['process']:
        if document['process']['post_run_snapshot'] != 'failed':
            raise ValueError('invalid snapshot failure')
        stale = True
    review_ready = r['state'] == 'approved' and r['revision'] == current
    if 'review_current' in document:
        review_ready = _current_review(document['review_current'], worker, task, current)
        dispatch = document.get('dispatch_revision')
        if dispatch is None:
            # Manual verification and legacy results can have no Source binding.
            # Validate their projection above, but never promote them to ready.
            review_ready = False
        else:
            dispatch = _revision(dispatch)
            review_ready = review_ready and current is not None and dispatch['task_sha256'] == current['task_sha256']
        delivery = document.get('delivery')
        if delivery is not None:
            if not isinstance(delivery, dict) or delivery.get('state') not in (None, 'Unknown', 'complete'):
                review_ready = False
    ready = (not stale and p['state'] == 'succeeded' and v['state'] == 'passed'
             and review_ready and all(s['revision'] == current for s in (p, v)))
    if document['ready_for_human_review'] and not ready:
        raise ValueError('inconsistent native readiness')
    result.update(stale=stale, ready_for_human_review=ready and document['ready_for_human_review'])
    return result


class ExecutionService:
    @_public
    def __init__(self, workspace, engine, worker, reviewer, config_dir,
                 template_path, worker_company, reviewer_company):
        self._closed = False
        self._thread_lock = threading.RLock()
        self._fd = None
        for value in (worker, reviewer):
            _input(LABEL, value)
        for value in (worker_company, reviewer_company):
            if not isinstance(value, str) or not value.strip() or len(value) > 100 or any(
                    ord(char) < 32 or ord(char) == 127 for char in value):
                raise ExecutionError('invalid_request')
        if worker_company == reviewer_company:
            raise ExecutionError('invalid_request')
        try:
            self._workspace = _real_path(workspace, True)
            self._repo = _real_path(self._workspace / 'repo', True)
            self._coord = _real_path(self._workspace / 'coord', True)
            _real_path(self._workspace / 'wt', True)
            self._wt = _real_path(self._workspace / 'wt' / worker, True)
            self._engine = _real_path(engine)
            if not os.access(self._engine, os.X_OK):
                raise ValueError('engine not executable')
            self._config = _real_path(config_dir, True)
            self._template_path = _real_path(template_path)
        except (ValueError, OSError, TypeError) as error:
            raise ExecutionError('invalid_request') from error
        self._worker, self._reviewer = worker, reviewer
        self._worker_company, self._reviewer_company = worker_company, reviewer_company
        try:
            self._template()  # Startup validates compilation, but never demands a clean worker.
            self._fingerprints()
        except (OSError, ValueError, TypeError, RecursionError) as error:
            raise ExecutionError('invalid_request') from error
        directory = self._coord / 'ui-execution'
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _real_path(directory, True)
        self._directory = directory
        self._fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            with self._locked():
                for name in ('bindings', 'states', 'actions'):
                    try:
                        os.mkdir(name, mode=0o700, dir_fd=self._fd)
                    except FileExistsError:
                        pass
                    _real_path(directory / name, True)
                with JobStore(self._workspace) as store:
                    store.jobs()  # Fail closed on corrupt queue records at startup.
                self._owner()  # Existing unknown ownership is retained, never repaired.
        except BaseException:
            os.close(self._fd)
            self._fd = None
            raise

    def close(self):
        with self._thread_lock:
            self._closed = True
            if self._fd is not None:
                os.close(self._fd)
                self._fd = None

    @contextmanager
    def _locked(self):
        with self._thread_lock:
            if self._closed or self._fd is None:
                raise ExecutionError('storage_unavailable')
            descriptor = os.open('lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 0o600, dir_fd=self._fd)
            try:
                if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                    raise ValueError('unsupported lock')
                deadline = time.monotonic() + LOCK_TIMEOUT
                while True:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise ExecutionError('worker_unavailable')
                        time.sleep(0.02)
                # Refuse directory replacement; held descriptors are not a new authority.
                if os.stat(self._directory, follow_symlinks=False).st_ino != os.fstat(self._fd).st_ino:
                    raise ValueError('replaced execution directory')
                _real_path(self._directory, True)
                yield
            finally:
                os.close(descriptor)

    def _write(self, path, record, exclusive=False):
        raw = _json_bytes(record)
        if len(raw) > JSON_LIMIT:
            raise ValueError('oversized durable record')
        self._publish(path, raw, exclusive)

    def _publish(self, path, raw, exclusive):
        _real_path(path.parent, True)
        if os.path.lexists(path):
            _real_path(path)
            if exclusive:
                if _read(path, max(JSON_LIMIT, len(raw))) == raw:
                    return
                raise ExecutionError('conflict')
        temporary = path.parent / ('.' + uuid.uuid4().hex + '.tmp')
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            if exclusive:
                try:
                    os.link(temporary, path, follow_symlinks=False)
                except FileExistsError:
                    if _read(path, max(JSON_LIMIT, len(raw))) != raw:
                        raise ExecutionError('conflict') from None
            else:
                os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)

    def _owner_path(self):
        return self._directory / (self._worker + '.json')

    def _owner(self):
        path = self._owner_path()
        if not os.path.lexists(path):
            return None
        record = _decode(_read(path))
        if (not isinstance(record, dict) or set(record) != {
                'schema_version', 'worker', 'phase', 'job_id', 'request_key'}
                or type(record['schema_version']) is not int or record['schema_version'] != 1
                or record['worker'] != self._worker or record['phase'] not in ('preparing', 'owned', 'released')
                or not _matches(HEX32, record['request_key'])
                or (record['phase'] != 'preparing' and not _matches(HEX32, record['job_id']))
                or (record['phase'] == 'preparing' and record['job_id'] is not None)):
            raise ValueError('corrupt ownership')
        if record['phase'] in ('owned', 'released'):
            try:
                binding, state = self._records(record['job_id'])
            except ExecutionError as error:
                raise ValueError('ownership has no service binding') from error
            if binding['request_key'] != record['request_key']:
                raise ValueError('ownership mismatch')
            with JobStore(self._workspace) as store:
                job = store.get(record['job_id'])
            if job is None or job['worker'] != self._worker:
                raise ValueError('ownership has no queue binding')
            if any(job[key] != binding[key] for key in ('request_key', 'draft_id', 'draft_sha256')):
                raise ValueError('ownership queue inputs changed')
            if record['phase'] == 'released' and job['state'] != 'cancelled' and state['acceptance']['state'] != 'accepted':
                raise ValueError('ownership released without explicit completion')
            if record['phase'] == 'released' and job['state'] != 'cancelled' and (
                    self._unresolved(state) or not any(self._action(key)['method'] == 'accept'
                    and self._action(key)['phase'] == 'done'
                    and self._action(key)['revision'] == state['acceptance']['revision'] for key in state['actions'])):
                raise ValueError('ownership released without a durable acceptance outcome')
        return record

    def _own(self, job):
        owner = self._owner()
        if (owner is None or owner['phase'] != 'owned' or owner['job_id'] != job['id']
                or owner['request_key'] != job['request_key']):
            raise ExecutionError('outcome_unknown')

    def _release(self, job):
        owner = self._owner()
        if owner and owner['phase'] == 'released' and owner['job_id'] == job['id']:
            return
        self._own(job)
        self._write(self._owner_path(), dict(schema_version=1, worker=self._worker,
                    phase='released', job_id=job['id'], request_key=job['request_key']))

    def _template(self):
        raw = _read(self._template_path)
        template = _decode(raw)
        self._validate_template(template)
        return template, _hash(raw)

    @staticmethod
    def _validate_template(template):
        if (not isinstance(template, dict) or set(template) != {'schema_version', 'instructions', 'scope', 'validate'}
                or type(template['schema_version']) is not int or template['schema_version'] != 1):
            raise ExecutionError('invalid_request')
        instructions, scope, validate = (template[key] for key in ('instructions', 'scope', 'validate'))
        if (not isinstance(instructions, str) or not 1 <= len(instructions) <= 12000
                or re.search(r'^## (?:Allowed scope|Validate)(?:\r)?$', instructions, re.MULTILINE)):
            raise ExecutionError('invalid_request')
        instructions.encode('utf-8')
        if not isinstance(scope, list) or not 1 <= len(scope) <= 100:
            raise ExecutionError('invalid_request')
        for path in scope:
            if (not isinstance(path, str) or not path or path.startswith('/') or '\\' in path
                    or any(part in ('', '.', '..') for part in path.split('/'))
                    or _path_control(path)
                    or path != path.strip()):
                raise ExecutionError('invalid_request')
            path.encode('utf-8')
        if len(set(scope)) != len(scope) or not isinstance(validate, list) or not 1 <= len(validate) <= 30:
            raise ExecutionError('invalid_request')
        if any(not isinstance(command, str) or not command.strip() or len(command) > 2000
               or any(char in '\x00\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029' for char in command) for command in validate):
            raise ExecutionError('invalid_request')
        for command in validate:
            command.encode('utf-8')

    def _config_hash(self):
        rows, total = [], 0
        def walk(directory):
            nonlocal total
            _real_path(directory, True)
            for path in sorted(directory.iterdir()):
                mode = path.lstat().st_mode
                if stat.S_ISDIR(mode):
                    rows.append([str(path.relative_to(self._config)), 'directory'])
                    if len(rows) > 1024:
                        raise ValueError('too many configuration entries')
                    walk(path)
                elif stat.S_ISREG(mode):
                    raw = _read(path, CONFIG_LIMIT - total)
                    total += len(raw)
                    rows.append([str(path.relative_to(self._config)), 'file', stat.S_IMODE(mode), _hash(raw)])
                    if sum(row[1] == 'file' for row in rows) > CONFIG_FILES:
                        raise ValueError('too many configuration files')
                else:
                    raise ValueError('unsupported configuration input')
        walk(self._config)
        # Native Unio prefers the project-local override over config_dir/agents.conf.
        override = self._coord / 'agents.conf'
        if os.path.lexists(override):
            raw = _read(override, CONFIG_LIMIT - total)
            if sum(row[1] == 'file' for row in rows) >= CONFIG_FILES:
                raise ValueError('too many configuration files')
            rows.append(['@coord/agents.conf', 'file', _hash(raw)])
        return _hash(_json_bytes(rows))

    def _fingerprints(self):
        return dict(engine=_hash(_read(self._engine, CONFIG_LIMIT)), config=self._config_hash(),
                    template=self._template()[1])

    def _call(self, argv, timeout):
        """Drain bounded pipes while the process runs, including inherited pipes."""
        environment = os.environ.copy()
        environment.update(UNIO_CONF_DIR=str(self._config), UNIO_AUTO_OFF='0',
                           UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0')
        try:
            process = subprocess.Popen(argv, cwd=self._repo, env=environment,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, start_new_session=True, close_fds=True)
        except OSError as error:
            raise _NativeFailure(False) from error
        stdout, size = bytearray(), 0
        deadline = time.monotonic() + timeout
        try:
            with selectors.DefaultSelector() as selector:
                for pipe in (process.stdout, process.stderr):
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ)
                while selector.get_map():
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise _NativeFailure(True, process.poll())
                    for key, _ in selector.select(min(remaining, 0.1)):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        size += len(chunk)
                        if size > OUTPUT_LIMIT:
                            raise _NativeFailure(True, process.poll())
                        if key.fileobj is process.stdout:
                            stdout.extend(chunk)
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise _NativeFailure(True, process.poll())
                try:
                    code = process.wait(timeout=remaining)
                except subprocess.TimeoutExpired as error:
                    raise _NativeFailure(True) from error
                return code, bytes(stdout)
        except (OSError, _NativeFailure) as error:
            self._terminate_session(process.pid)
            try:
                process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
            if isinstance(error, _NativeFailure):
                raise
            raise _NativeFailure(True, process.poll()) from error
        finally:
            process.stdout.close()
            process.stderr.close()

    @staticmethod
    def _terminate_session(session_id):
        # Native timeout commands create additional process groups. Signal only
        # groups in the session we created, never names or unrelated workers.
        groups = {session_id}
        if Path('/proc').is_dir():
            for entry in Path('/proc').iterdir():
                if not entry.name.isdigit():
                    continue
                try:
                    identity = int(entry.name)
                    if os.getsid(identity) == session_id:
                        groups.add(os.getpgid(identity))
                except (ProcessLookupError, PermissionError):
                    pass
        for group in groups:
            try:
                os.killpg(group, signal.SIGKILL)
            except ProcessLookupError:
                pass

    def _git(self, directory, *arguments):
        try:
            code, raw = self._call(['git', '-C', str(directory), '-c', 'core.fsmonitor=false',
                                    '-c', 'core.untrackedCache=false', *arguments], 15)
        except _NativeFailure as error:
            raise ExecutionError('worker_unavailable') from error
        if code != 0:
            raise ExecutionError('worker_unavailable')
        return raw

    def _base(self):
        path = self._coord / 'base'
        base = _read(path, 4096).decode().strip() if os.path.lexists(path) else 'main'
        if (not base or base.startswith('-') or '..' in base or any(
                char.isspace() or ord(char) < 32 for char in base)):
            raise ExecutionError('worker_unavailable')
        revision = self._git(self._repo, 'rev-parse', '--verify', '--end-of-options', base + '^{commit}').decode().strip()
        if not _matches(GIT_ID, revision):
            raise ExecutionError('worker_unavailable')
        return base, revision

    def _worker_revision(self, clean=False):
        _real_path(self._wt, True)
        # Batch only facts within this observation. No evidence is cached or
        # shared with another _check/_native call. rev-parse emits the common
        # directory, peeled commit, then full symbolic HEAD in that order.
        try:
            raw = self._git(self._wt, 'rev-parse', '--path-format=absolute',
                            '--git-common-dir', 'HEAD^{commit}', '--symbolic-full-name', 'HEAD')
            common, revision, branch, end = raw.decode().split('\n')
            repo_common, repo_end = self._git(
                self._repo, 'rev-parse', '--path-format=absolute', '--git-common-dir').decode().split('\n')
            if (end or repo_end or branch != 'refs/heads/agent/' + self._worker
                    or not _matches(GIT_ID, revision)
                    or any(not Path(path).is_absolute() or any(ord(c) < 32 for c in path)
                           for path in (common, repo_common))
                    or Path(common).resolve() != Path(repo_common).resolve()):
                raise ExecutionError('worker_unavailable')
        except (ValueError, OSError) as error:
            raise ExecutionError('worker_unavailable') from error

        # -v supplies hidden-edit flags; --stage supplies unmerged stages in
        # the same NUL-delimited read. Parse the fixed header only: filenames
        # may contain tabs/newlines and must never become shell input.
        raw = self._git(self._wt, 'ls-files', '--stage', '-v', '-z')
        seen = set()
        for row in raw.split(b'\0')[:-1]:
            header, separator, path = row.partition(b'\t')
            if (not separator or not path or path in seen
                    or re.fullmatch(rb'[HMRCK?] (?:100644|100755|120000|160000) '
                                    rb'(?:[0-9a-f]{40}|[0-9a-f]{64}) 0', header) is None):
                raise ExecutionError('worker_unavailable')
            seen.add(path)
        if raw and not raw.endswith(b'\0'):
            raise ExecutionError('worker_unavailable')
        try:
            # Git distinguishes a bare key (true) from an explicit empty value
            # (false); an untyped read emits the same newline for both.
            code, raw = self._call(['git', '-C', str(self._wt), 'config', '--type=bool',
                                    '--get-all', 'core.sparseCheckout'], 15)
        except _NativeFailure as error:
            raise ExecutionError('worker_unavailable') from error
        if not ((code == 1 and raw == b'') or (code == 0 and raw == b'false\n')):
            raise ExecutionError('worker_unavailable')
        if clean:
            base, base_revision = self._base()
            if revision != base_revision:
                raise ExecutionError('worker_unavailable')
            if self._git(self._wt, 'status', '--porcelain=v1', '--untracked-files=all', '-z'):
                raise ExecutionError('worker_unavailable')
        return revision

    def _stop_check(self):
        path = self._coord / 'STOP'
        if os.path.lexists(path):
            _real_path(path)
            raise ExecutionError('stopped')

    def _worker_free(self):
        path = self._coord / '.locks' / (self._worker + '.lock')
        if not os.path.lexists(path):
            return
        _real_path(path)
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError('invalid native lock')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ExecutionError('worker_unavailable') from error
        finally:
            os.close(descriptor)

    @contextmanager
    def _accept_guard(self):
        """Keep native writers out while evidence and acceptance are compared."""
        directory = self._coord / '.locks'
        try:
            directory.mkdir(mode=0o700)
        except FileExistsError:
            pass
        _real_path(directory, True)
        path = directory / (self._worker + '.lock')
        descriptor = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            if not stat.S_ISREG(os.fstat(descriptor).st_mode):
                raise ValueError('unsupported native lock')
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise ExecutionError('worker_unavailable') from error
            yield
        finally:
            os.close(descriptor)

    def _draft(self, draft_id, expected_hash):
        try:
            with PlanStore(self._workspace) as plans:
                draft = plans.get(draft_id)
        except (FileNotFoundError, ValueError) as error:
            raise ExecutionError('draft_stale') from error
        if draft['content_sha256'] != expected_hash:
            raise ExecutionError('draft_stale')
        return draft

    def _compile(self, request, task_id, template):
        # ensure_ascii escapes every newline/control/unicode line separator in the request.
        return ('# ' + task_id + '\n\nSaved request (one literal JSON string):\n'
                + json.dumps(request, ensure_ascii=True) + '\n\n' + template['instructions']
                + '\n\n## Allowed scope\n' + ''.join('- ' + path + '\n' for path in template['scope'])
                + '\n## Validate\n' + ''.join('$ ' + command + '\n' for command in template['validate'])).encode()

    def _records(self, job_id):
        path = self._directory / 'bindings' / (job_id + '.json')
        if not os.path.lexists(path):
            raise ExecutionError('job_not_found')
        binding = _decode(_read(path))
        fields = {'schema_version', 'job_id', 'request_key', 'draft_id', 'draft_sha256', 'base',
                  'base_revision', 'worker_revision', 'preview', 'fingerprints', 'startup'}
        if (not isinstance(binding, dict) or set(binding) != fields
                or type(binding['schema_version']) is not int or binding['schema_version'] != 1
                or binding['job_id'] != job_id
                or any(not _matches(HEX32, binding[key]) for key in ('job_id', 'request_key', 'draft_id'))
                or not _matches(HEX64, binding['draft_sha256'])
                or any(not _matches(GIT_ID, binding[key]) for key in ('base_revision', 'worker_revision'))
                or binding['worker_revision'] != binding['base_revision']
                or not isinstance(binding['base'], str) or not 1 <= len(binding['base']) <= 4096):
            raise ValueError('corrupt binding')
        preview = binding['preview']
        if not isinstance(preview, dict) or set(preview) != {'task_id', 'task_sha256',
                'preview_hash', 'worker', 'reviewer', 'worker_company', 'reviewer_company'}:
            raise ValueError('corrupt stored preview')
        if not _matches(LABEL, preview['worker']):
            raise ValueError('corrupt bound worker')
        if preview['worker'] != self._worker:
            raise ExecutionError('job_not_found')
        # Keep each JSON document bounded even at the template/request maxima.
        # These immutable companions are part of the complete binding, checked
        # against its preview/task hashes on every read.
        for name in ('request', 'scope', 'validate'):
            preview[name] = _decode(_read(self._directory / 'bindings' / (job_id + '.' + name + '.json')))
        binding['task'] = _read(self._directory / 'bindings' / (job_id + '.md'), OUTPUT_LIMIT).decode()
        if (not isinstance(preview, dict) or set(preview) != {'request', 'task_id', 'task_sha256',
                'preview_hash', 'scope', 'validate', 'worker', 'reviewer', 'worker_company', 'reviewer_company'}
                or preview['worker'] != self._worker or preview['task_id'] != 'ui-' + job_id
                or not _matches(LABEL, preview['reviewer'])
                or not _matches(HEX64, preview['task_sha256']) or not _matches(HEX64, preview['preview_hash'])
                or _hash(binding['task'].encode()) != preview['task_sha256']):
            raise ValueError('corrupt preview')
        public = {key: value for key, value in preview.items() if key != 'preview_hash'}
        if _hash(_canonical(public)) != preview['preview_hash']:
            raise ValueError('corrupt preview hash')
        # Reconstruct with the bound sections, ensuring stored compilation is exact.
        task = binding['task']
        if (task.count('\n## Allowed scope\n') != 1 or task.count('\n## Validate\n') != 1
                or not isinstance(preview['request'], str) or not 1 <= len(preview['request']) <= 4000
                or not isinstance(preview['scope'], list) or not isinstance(preview['validate'], list)
                or not all(isinstance(value, str) for value in preview['scope'] + preview['validate'])
                or not isinstance(preview['worker_company'], str) or not isinstance(preview['reviewer_company'], str)
                or preview['worker_company'] == preview['reviewer_company']):
            raise ValueError('corrupt bound task')
        prefix = ('# ' + preview['task_id'] + '\n\nSaved request (one literal JSON string):\n'
                  + json.dumps(preview['request'], ensure_ascii=True) + '\n\n')
        suffix = ('\n\n## Allowed scope\n' + ''.join('- ' + path + '\n' for path in preview['scope'])
                  + '\n## Validate\n' + ''.join('$ ' + command + '\n' for command in preview['validate']))
        if not task.startswith(prefix) or not task.endswith(suffix):
            raise ValueError('task disagrees with public preview')
        instructions = task[len(prefix):-len(suffix)]
        try:
            self._validate_template(dict(schema_version=1, instructions=instructions,
                                         scope=preview['scope'], validate=preview['validate']))
        except ExecutionError as error:
            raise ValueError('corrupt compiled template') from error
        for label in ('worker_company', 'reviewer_company'):
            if not 1 <= len(preview[label]) <= 100 or any(ord(char) < 32 or ord(char) == 127 for char in preview[label]):
                raise ValueError('corrupt company label')
        fingerprints = binding['fingerprints']
        if (not isinstance(fingerprints, dict) or set(fingerprints) != {'engine', 'config', 'template'}
                or any(not _matches(HEX64, value) for value in fingerprints.values())
                or not isinstance(binding['startup'], dict)
                or set(binding['startup']) != {'engine', 'config', 'template'}
                or any(not isinstance(value, str) for value in binding['startup'].values())):
            raise ValueError('corrupt fingerprints')
        state = _decode(_read(self._directory / 'states' / (job_id + '.json')))
        if (not isinstance(state, dict) or set(state) != {'schema_version', 'job_id', 'execution',
                'acceptance', 'run_action', 'review_action', 'actions'}
                or type(state['schema_version']) is not int or state['schema_version'] != 1
                or state['job_id'] != job_id or not isinstance(state['actions'], list)
                or len(state['actions']) > 1000
                or len(set(state['actions'])) != len(state['actions'])
                or any(not _matches(HEX32, key) for key in state['actions'])):
            raise ValueError('corrupt execution state')
        execution = state['execution']
        if (not isinstance(execution, dict) or set(execution) != {'state', 'launcher_exit'}
                or execution['state'] not in ('not_started', 'launch_accepted', 'launch_failed', 'completion_unknown')
                or (execution['launcher_exit'] is not None and type(execution['launcher_exit']) is not int)):
            raise ValueError('corrupt launch state')
        acceptance = state['acceptance']
        if (not isinstance(acceptance, dict) or set(acceptance) != {'state', 'revision'}
                or acceptance['state'] not in ('pending', 'accepted')
                or (acceptance['state'] == 'pending') != (acceptance['revision'] is None)):
            raise ValueError('corrupt acceptance')
        if acceptance['revision'] is not None:
            _revision(acceptance['revision'])
        for key in ('run_action', 'review_action'):
            if state[key] is not None and (not _matches(HEX32, state[key]) or state[key] not in state['actions']):
                raise ValueError('corrupt action pointer')
        for key in state['actions']:
            action = self._action(key)
            if action is None or action['job_id'] != job_id or action['binding_sha256'] != _hash(_json_bytes(binding)):
                raise ValueError('corrupt action binding')
        # Publication may have stopped between an action intent and its state
        # pointer. Such an orphan must block another key, especially a review.
        for path in (self._directory / 'actions').iterdir():
            if not _matches(HEX32, path.stem) or path.suffix != '.json':
                if path.name.startswith('.'):
                    continue
                raise ValueError('unsupported action record')
            action = self._action(path.stem)
            if action['job_id'] == job_id and path.stem not in state['actions']:
                raise ValueError('unresolved orphan action')
        return binding, state

    def _state_write(self, state):
        self._write(self._directory / 'states' / (state['job_id'] + '.json'), state)

    def _load_job(self, store, job_id):
        _input(HEX32, job_id)
        binding, state = self._records(job_id)
        job = store.get(job_id)
        if job is None:
            raise ValueError('binding has no job')
        if any(job[key] != binding[key] for key in ('draft_id', 'draft_sha256', 'request_key')) or job['worker'] != self._worker:
            raise ValueError('queue binding mismatch')
        return job, binding, state

    def _check(self, job, binding, task=False, clean=False, check_stop=True):
        if check_stop:
            self._stop_check()
        self._draft(job['draft_id'], job['draft_sha256'])
        startup = dict(engine=str(self._engine), config=str(self._config), template=str(self._template_path))
        preview = binding['preview']
        if (startup != binding['startup'] or self._reviewer != preview['reviewer']
                or self._worker_company != preview['worker_company']
                or self._reviewer_company != preview['reviewer_company']):
            raise ExecutionError('binding_stale')
        try:
            if self._fingerprints() != binding['fingerprints']:
                raise ExecutionError('binding_stale')
            base, revision = self._base()
            if base != binding['base'] or revision != binding['base_revision']:
                raise ExecutionError('binding_stale')
            worker_revision = self._worker_revision(clean=clean)
            if job['reservation_key'] is None and job['state'] != 'cancelled' and worker_revision != binding['worker_revision']:
                raise ExecutionError('binding_stale')
            task_path = self._task_path(binding)
            if task or os.path.lexists(task_path):
                if _read(task_path, OUTPUT_LIMIT) != binding['task'].encode():
                    raise ExecutionError('binding_stale')
        except ExecutionError as error:
            if error.code == 'invalid_request':
                raise ExecutionError('binding_stale') from error
            raise
        except (ValueError, OSError) as error:
            raise ExecutionError('binding_stale') from error

    def _task_path(self, binding):
        return self._coord / 'tasks' / (binding['preview']['task_id'] + '.md')

    def _action(self, key):
        path = self._directory / 'actions' / (key + '.json')
        if not os.path.lexists(path):
            return None
        action = _decode(_read(path))
        if (not isinstance(action, dict) or set(action) != {'schema_version', 'key', 'job_id', 'method',
                'inputs', 'revision', 'binding_sha256', 'phase', 'exit_code', 'error'}
                or type(action['schema_version']) is not int or action['schema_version'] != 1
                or action['key'] != key or not _matches(HEX32, action['job_id'])
                or action['method'] not in ('approve', 'start', 'verify', 'review', 'accept', 'stop')
                or not isinstance(action['inputs'], dict)
                or not _matches(HEX64, action['binding_sha256'])
                or action['phase'] not in ('intent', 'done', 'unknown', 'failed')
                or (action['exit_code'] is not None and type(action['exit_code']) is not int)
                or (action['error'] is not None and action['error'] not in ERRORS)):
            raise ValueError('corrupt action')
        if action['revision'] is not None:
            _revision(action['revision'])
        return action

    def _replay(self, key, method, job_id, inputs):
        action = self._action(key)
        if action is not None and (action['method'] != method or action['job_id'] != job_id or action['inputs'] != inputs):
            raise ExecutionError('conflict')
        return action

    def _intent(self, key, method, binding, state, inputs, revision=None):
        action = dict(schema_version=1, key=key, job_id=binding['job_id'], method=method,
                      inputs=inputs, revision=revision, binding_sha256=_hash(_json_bytes(binding)),
                      phase='intent', exit_code=None, error=None)
        self._write(self._directory / 'actions' / (key + '.json'), action, True)
        state['actions'].append(key)
        if method == 'start':
            state['run_action'] = key
        elif method == 'review':
            state['review_action'] = key
        self._state_write(state)
        return action

    def _finish(self, action, phase='done', exit_code=None, error=None):
        action.update(phase=phase, exit_code=exit_code, error=error)
        self._write(self._directory / 'actions' / (action['key'] + '.json'), action)

    def _unknown(self, store, job, state, action, code=None):
        self._finish(action, 'unknown', code, 'outcome_unknown')
        if job['state'] == 'reserved':
            store.mark_unknown(job['id'], job['reservation_key'])
        state['execution'] = dict(state='completion_unknown', launcher_exit=state['execution']['launcher_exit'])
        self._state_write(state)

    def _unresolved(self, state):
        return any(self._action(key)['phase'] in ('intent', 'unknown') for key in state['actions'])

    def _native(self, binding):
        task = binding['preview']['task_id']
        try:
            code, raw = self._call([str(self._engine), 'result', self._worker, task], DEADLINES['result'])
        except _NativeFailure:
            return None, 'native_result_unavailable'
        if code != 0:
            return None, 'native_result_unavailable'
        try:
            document = _decode(raw)
            native = _native_document(document, self._worker, task)
            revision = native['current_revision']
            if revision is not None and (revision['task_sha256'] != binding['preview']['task_sha256']
                    or revision['base_commit'] != binding['base_revision']
                    or revision['candidate_commit'] != self._worker_revision()):
                native.update(stale=True, ready_for_human_review=False)
            if native['review']['state'] == 'approved' and native['review']['reviewer'] != binding['preview']['reviewer']:
                native.update(stale=True, ready_for_human_review=False)
            if ('review_current' in document and native['ready_for_human_review']
                    and binding['preview']['reviewer'] not in document['review_current']['distinct_reviewers']):
                native.update(stale=True, ready_for_human_review=False)
            return native, None
        except (ValueError, TypeError, KeyError, UnicodeError, ExecutionError, RecursionError, OverflowError):
            return None, 'native_result_invalid'

    def _view(self, store, job, binding, state, native=None, native_warning=None, observe=True):
        warnings = []
        try:
            self._check(job, binding, task=state['run_action'] is not None, check_stop=False)
        except ExecutionError as error:
            if error.code in ('binding_stale', 'draft_stale', 'stopped'):
                warnings.append(error.code)
            else:
                warnings.append('binding_stale')
        if os.path.lexists(self._coord / 'STOP'):
            _real_path(self._coord / 'STOP')
            warnings.append('stopped')
        owner = self._owner()
        if owner is None or owner['phase'] == 'preparing' or (
                owner['phase'] == 'owned' and owner['job_id'] != job['id']
                and state['acceptance']['state'] != 'accepted' and job['state'] != 'cancelled'):
            warnings.append('ownership_unknown')
        execution = dict(state['execution'])
        if state['run_action'] is not None:
            launch = self._action(state['run_action'])
            if launch['exit_code'] is not None:
                execution['launcher_exit'] = launch['exit_code']
        if self._unresolved(state) or (job['state'] in ('reserved', 'completion_unknown') and state['run_action'] is None):
            execution['state'] = 'completion_unknown'
            warnings.append('outcome_unknown')
        if observe and state['run_action'] is not None and 'binding_stale' not in warnings and 'draft_stale' not in warnings:
            native, native_warning = self._native(binding)
        if native_warning:
            warnings.append(native_warning)
        if native is not None and any(message in warnings for message in (
                'binding_stale', 'draft_stale', 'ownership_unknown', 'outcome_unknown')):
            native = copy.deepcopy(native)
            native.update(stale=True, ready_for_human_review=False)
        acceptance = copy.deepcopy(state['acceptance'])
        if acceptance['state'] == 'accepted' and (native is None or not native['ready_for_human_review']
                                                  or acceptance['revision'] != native['current_revision']):
            acceptance['state'] = 'stale'
        return dict(schema_version=1, job=job, preview=copy.deepcopy(binding['preview']),
                    execution=execution, native_result=native, acceptance=acceptance,
                    warnings=list(dict.fromkeys(warnings))[:8])

    def _publication(self, job_id, request_key, draft, template, base, base_revision,
                     worker_revision, fingerprints):
        """Build and bound-check every document prepare() publishes for job_id."""
        if not _matches(HEX32, job_id):
            raise ValueError('invalid queue identity')
        task_id = 'ui-' + job_id
        task = self._compile(draft['request'], task_id, template)
        preview = dict(request=draft['request'], task_id=task_id, task_sha256=_hash(task),
                       scope=template['scope'], validate=template['validate'], worker=self._worker,
                       reviewer=self._reviewer, worker_company=self._worker_company,
                       reviewer_company=self._reviewer_company)
        preview['preview_hash'] = _hash(_canonical(preview))
        binding = dict(schema_version=1, job_id=job_id, request_key=request_key, draft_id=draft['id'],
                       draft_sha256=draft['content_sha256'], base=base, base_revision=base_revision,
                       worker_revision=worker_revision, preview=preview, task=task.decode(),
                       fingerprints=fingerprints, startup=dict(engine=str(self._engine),
                       config=str(self._config), template=str(self._template_path)))
        state = dict(schema_version=1, job_id=job_id,
                     execution=dict(state='not_started', launcher_exit=None),
                     acceptance=dict(state='pending', revision=None), run_action=None,
                     review_action=None, actions=[])
        physical = copy.deepcopy(binding)
        physical.pop('task')
        bindings = self._directory / 'bindings'
        documents = [(bindings / (job_id + '.md'), task)]
        for name in ('request', 'scope', 'validate'):
            documents.append((bindings / (job_id + '.' + name + '.json'), _stored(physical['preview'].pop(name))))
        documents.append((bindings / (job_id + '.json'), _json_bytes(physical)))
        # Metadata written by this and later transitions: state and every ownership phase.
        metadata = [_json_bytes(state)] + [
            _json_bytes(dict(schema_version=1, worker=self._worker, phase=phase,
                             job_id=None if phase == 'preparing' else job_id, request_key=request_key))
            for phase in ('preparing', 'owned', 'released')]
        if len(task) > OUTPUT_LIMIT or any(len(raw) > JSON_LIMIT
                                           for raw in [raw for _, raw in documents[1:]] + metadata):
            raise ExecutionError('invalid_request')
        _json_bytes(binding)  # The canonical action-binding hash input must also serialize.
        return binding, state, documents

    @_public
    def prepare(self, draft_id, expected_hash, request_key):
        _input(HEX32, draft_id)
        _input(HEX64, expected_hash)
        _input(HEX32, request_key)
        with self._locked(), JobStore(self._workspace) as store:
            draft = self._draft(draft_id, expected_hash)
            existing = next((job for job in store.jobs() if job['request_key'] == request_key), None)
            if existing:
                if existing['draft_id'] != draft_id or existing['draft_sha256'] != expected_hash or existing['worker'] != self._worker:
                    raise ExecutionError('conflict')
                job, binding, state = self._load_job(store, existing['id'])
                self._check(job, binding, task=state['run_action'] is not None)
                return self._view(store, job, binding, state)
            self._stop_check()
            owner = self._owner()
            if owner and owner['phase'] != 'released':
                raise ExecutionError('outcome_unknown' if owner['phase'] == 'preparing' else 'worker_unavailable')
            if owner is None and any(job['worker'] == self._worker for job in store.jobs()):
                raise ExecutionError('outcome_unknown')
            # A missing ownership record never grants authority over an orphan binding/queue claim.
            if any(job['worker'] == self._worker and job['state'] != 'cancelled'
                   and (owner is None or job['id'] != owner['job_id']) for job in store.jobs()):
                for job in store.jobs():
                    if job['worker'] == self._worker and job['state'] != 'cancelled':
                        try:
                            _, old_state = self._records(job['id'])
                        except ExecutionError as error:
                            raise ExecutionError('outcome_unknown') from error
                        if old_state['acceptance']['state'] != 'accepted':
                            raise ExecutionError('outcome_unknown')
            self._worker_free()
            worker_revision = self._worker_revision(clean=True)
            base, base_revision = self._base()
            template, _ = self._template()
            fingerprints = self._fingerprints()
            # Preflight every document at its exact size before any ownership or
            # queue publication: queue IDs are always 32 hex characters, so a
            # placeholder ID yields byte-identical lengths. A deterministic bound
            # refusal therefore leaves ownership, queue rows and evidence unchanged.
            self._publication('0' * 32, request_key, draft, template, base, base_revision,
                              worker_revision, fingerprints)
            self._write(self._owner_path(), dict(schema_version=1, worker=self._worker,
                        phase='preparing', job_id=None, request_key=request_key))
            job = store.enqueue(draft_id, expected_hash, self._worker, request_key)
            # Any failure from here is genuine uncertainty and stays outcome_unknown.
            binding, state, documents = self._publication(job['id'], request_key, draft, template, base,
                                                          base_revision, worker_revision, fingerprints)
            for path, raw in documents:
                self._publish(path, raw, True)
            self._state_write(state)
            self._write(self._owner_path(), dict(schema_version=1, worker=self._worker,
                        phase='owned', job_id=job['id'], request_key=request_key))
            return self._view(store, job, binding, state, observe=False)

    @_public
    def approve(self, job_id, expected_hash, approval_key, preview_hash):
        _input(HEX64, expected_hash)
        _input(HEX32, approval_key)
        _input(HEX64, preview_hash)
        with self._locked(), JobStore(self._workspace) as store:
            job, binding, state = self._load_job(store, job_id)
            inputs = dict(expected_hash=expected_hash, preview_hash=preview_hash)
            action = self._replay(approval_key, 'approve', job_id, inputs)
            self._check(job, binding)
            if expected_hash != job['draft_sha256'] or preview_hash != binding['preview']['preview_hash']:
                raise ExecutionError('conflict')
            if action:
                if action['phase'] != 'done':
                    raise ExecutionError(action['error'] or 'outcome_unknown')
                return self._view(store, job, binding, state, observe=False)
            self._own(job)
            if job['state'] not in ('awaiting_owner_approval', 'approved'):
                raise ExecutionError('conflict')
            if job['approval_key'] is not None and job['approval_key'] != approval_key:
                raise ExecutionError('conflict')
            action = self._intent(approval_key, 'approve', binding, state, inputs)
            try:
                job = store.approve(job_id, expected_hash, self._worker, approval_key)
            except ValueError as error:
                self._finish(action, 'failed', error='conflict')
                raise ExecutionError('conflict') from error
            self._finish(action)
            return self._view(store, job, binding, state, observe=False)

    @_public
    def start(self, job_id, approval_key, reservation_key, *, preflight=None):
        _input(HEX32, approval_key)
        _input(HEX32, reservation_key)
        if preflight is not None and not callable(preflight):
            raise ExecutionError('invalid_request')
        with self._locked(), JobStore(self._workspace) as store:
            job, binding, state = self._load_job(store, job_id)
            inputs = dict(approval_key=approval_key)
            action = self._replay(reservation_key, 'start', job_id, inputs)
            if action:
                if action['phase'] == 'intent' and job['state'] == 'reserved':
                    self._unknown(store, job, state, action)
                    job = store.get(job_id)
                return self._view(store, job, binding, state)
            if job['state'] != 'approved' or state['run_action'] is not None or job['approval_key'] != approval_key:
                raise ExecutionError('conflict')
            self._own(job)
            self._check(job, binding, clean=True)
            self._worker_free()
            # Check any existing task before reservation; publication itself remains exclusive.
            path = self._task_path(binding)
            _real_path(path.parent, True)
            if os.path.lexists(path) and _read(path, OUTPUT_LIMIT) != binding['task'].encode():
                raise ExecutionError('binding_stale')
            if preflight is not None:
                # Fresh starts only, under the coordination lock: a refusal leaves
                # the approval intact with no reservation, action or native task.
                preflight(copy.deepcopy(binding))
            try:
                reservation = store.reserve(job_id, approval_key, reservation_key)
            except ValueError as error:
                raise ExecutionError('conflict') from error
            job = reservation['job']
            if not reservation['newly_reserved']:
                raise ExecutionError('outcome_unknown')
            action = self._intent(reservation_key, 'start', binding, state, inputs)
            try:
                self._publish(path, binding['task'].encode(), True)
                self._check(job, binding, task=True, clean=True)
                code, _ = self._call([str(self._engine), 'run', '-b', self._worker,
                                      binding['preview']['task_id']], DEADLINES['run'])
            except _NativeFailure as error:
                self._unknown(store, job, state, action, error.exit_code)
                state['execution']['launcher_exit'] = error.exit_code
                if not error.started:
                    state['execution']['state'] = 'launch_failed'
                    self._finish(action, 'failed', error.exit_code, 'native_unavailable')
                self._state_write(state)
                raise ExecutionError('outcome_unknown' if error.started else 'native_unavailable') from error
            except (ExecutionError, OSError, ValueError) as error:
                self._unknown(store, job, state, action)
                raise ExecutionError('outcome_unknown') from error
            state['execution'] = dict(state='launch_accepted' if code == 0 else 'completion_unknown', launcher_exit=code)
            if code != 0:
                self._unknown(store, job, state, action, code)
            else:
                try:
                    # Keep intent unresolved until the launch receipt itself is
                    # durable. A crash between publications stays conservative.
                    self._state_write(state)
                    self._finish(action, exit_code=code)
                except (OSError, ValueError, sqlite3.Error) as error:
                    self._unknown(store, job, state, action, code)
                    raise ExecutionError('outcome_unknown') from error
            return self._view(store, store.get(job_id), binding, state)

    def _perform(self, method, job_id, action_key):
        _input(HEX32, action_key)
        with self._locked(), JobStore(self._workspace) as store:
            job, binding, state = self._load_job(store, job_id)
            action = self._replay(action_key, method, job_id, {})
            if action:
                if action['phase'] == 'intent':
                    self._unknown(store, job, state, action)
                    job = store.get(job_id)
                return self._view(store, job, binding, state)
            self._own(job)
            if state['run_action'] is None or job['state'] not in ('reserved', 'completion_unknown'):
                raise ExecutionError('not_ready')
            if method != 'stop':
                self._check(job, binding, task=True)
                if self._unresolved(state) or job['state'] == 'completion_unknown':
                    raise ExecutionError('outcome_unknown')
            else:
                # Kill addresses only this immutable task; STOP/draft edits must not block it.
                try:
                    if _hash(_read(self._engine, CONFIG_LIMIT)) != binding['fingerprints']['engine'] or str(self._engine) != binding['startup']['engine']:
                        raise ExecutionError('binding_stale')
                except (ValueError, OSError) as error:
                    raise ExecutionError('binding_stale') from error
            if method == 'review' and state['review_action'] is not None:
                raise ExecutionError('conflict')
            native, warning = self._native(binding)
            revision = native['current_revision'] if native else None
            if method != 'stop':
                self._worker_free()
                if (native is None or native['stale'] or native['process']['state'] != 'succeeded'
                        or native['process']['exit_code'] != 0 or native['process']['revision'] != revision):
                    raise ExecutionError('not_ready')
                if method == 'review' and (native['validation']['state'] != 'passed'
                                           or native['validation']['revision'] != revision):
                    raise ExecutionError('not_ready')
                # Recheck after the observational subprocess, immediately before Validate/review.
                self._check(job, binding, task=True)
            action = self._intent(action_key, method, binding, state, {}, revision)
            operation = 'kill' if method == 'stop' else method
            argv = [str(self._engine), operation]
            if method != 'stop':
                argv.append(self._worker)
            argv.append(binding['preview']['task_id'])
            if method == 'review':
                argv.append(self._reviewer)
            try:
                code, _ = self._call(argv, DEADLINES[operation])
            except _NativeFailure as error:
                self._unknown(store, job, state, action, error.exit_code)
                raise ExecutionError('outcome_unknown') from error
            try:
                self._finish(action, exit_code=code)
            except (OSError, ValueError, sqlite3.Error) as error:
                self._unknown(store, job, state, action, code)
                raise ExecutionError('outcome_unknown') from error
            native, warning = self._native(binding)
            if method == 'stop' and (code != 0 or native is None or native['process']['state'] not in ('succeeded', 'failed')):
                self._unknown(store, job, state, action, code)
            # Failed checks/reviews retain their real exit; they never buy a new paid review.
            return self._view(store, store.get(job_id), binding, state, native, warning, observe=False)

    @_public
    def verify(self, job_id, action_key):
        return self._perform('verify', job_id, action_key)

    @_public
    def review(self, job_id, action_key):
        return self._perform('review', job_id, action_key)

    @_public
    def stop(self, job_id, action_key):
        return self._perform('stop', job_id, action_key)

    @_public
    def accept(self, job_id, revision_hash, action_key):
        _input(HEX32, job_id)
        _input(GIT_ID, revision_hash)
        _input(HEX32, action_key)
        with self._locked(), JobStore(self._workspace) as store, self._accept_guard():
            job, binding, state = self._load_job(store, job_id)
            inputs = dict(revision_hash=revision_hash)
            action = self._replay(action_key, 'accept', job_id, inputs)
            self._check(job, binding, task=True)
            if self._unresolved(state) or job['state'] == 'completion_unknown':
                raise ExecutionError('outcome_unknown')
            native, warning = self._native(binding)
            if (native is None or not native['ready_for_human_review'] or native['stale']
                    or native['current_revision']['candidate_commit'] != revision_hash):
                raise ExecutionError('not_ready')
            if action:
                if action['phase'] != 'done' or action['revision'] != native['current_revision']:
                    raise ExecutionError('conflict')
                self._release(job)
                return self._view(store, job, binding, state, native, warning, observe=False)
            self._own(job)
            self._check(job, binding, task=True)
            latest, latest_warning = self._native(binding)
            if (latest is None or not latest['ready_for_human_review']
                    or latest['current_revision'] != native['current_revision']):
                raise ExecutionError('not_ready')
            native, warning = latest, latest_warning
            action = self._intent(action_key, 'accept', binding, state, inputs, native['current_revision'])
            state['acceptance'] = dict(state='accepted', revision=native['current_revision'])
            self._state_write(state)
            self._finish(action)
            self._release(job)
            return self._view(store, job, binding, state, native, warning, observe=False)

    @_public
    def cancel(self, job_id):
        with self._locked(), JobStore(self._workspace) as store:
            job, binding, state = self._load_job(store, job_id)
            if job['state'] == 'cancelled':
                owner = self._owner()
                if owner and owner['phase'] == 'owned' and owner['job_id'] == job_id:
                    self._release(job)
                return self._view(store, job, binding, state, observe=False)
            if job['state'] not in ('awaiting_owner_approval', 'approved') or state['run_action'] is not None:
                raise ExecutionError('conflict')
            self._own(job)
            job = store.cancel(job_id)
            self._release(job)
            return self._view(store, job, binding, state, observe=False)

    @_public
    def get(self, job_id):
        with self._locked(), JobStore(self._workspace) as store:
            job, binding, state = self._load_job(store, job_id)
            return self._view(store, job, binding, state)

    @_public
    def jobs(self):
        with self._locked(), JobStore(self._workspace) as store:
            result = []
            for job in store.jobs():
                if job['worker'] != self._worker or not os.path.lexists(self._directory / 'bindings' / (job['id'] + '.json')):
                    continue
                job, binding, state = self._load_job(store, job['id'])
                result.append(self._view(store, job, binding, state))
            return result
