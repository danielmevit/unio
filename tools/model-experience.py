#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Local worker experience and selection advice: bounded, strict, honest.

`record` stores one explicit operator assessment of one native task revision.
It reads only the existing runner's fixed `result WORKER TASK` command — never
a shell, never a configured agent — and refuses running, not-run, stale,
mismatched or unsupported evidence. `show` groups the stored evidence by
profile. `suggest` combines that evidence with the bounded fleet observation
into conditional selection advice. All profile metadata is operator-reported;
effective model and effort remain unknown, human acceptance is never granted
or synthesized, and no provider call is ever made.
"""

import argparse
import datetime
import fcntl
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import signal
import stat
import sys
import tempfile
import time
from pathlib import Path

SCHEMA_VERSION = 1
RECORD_DEADLINE_SECONDS = 30
MAX_RECORD_BYTES = 65536
MAX_STORE_RECORDS = 512
MAX_EXAMPLES = 8
RECENT_DAYS = 90
MIN_RECENT_ACCEPTED = 3
SUGGEST_TIMEOUT_DEFAULT = 10

LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
RECORD_NAME = re.compile(r'[0-9a-f]{32}\.json')
HEX32 = re.compile(r'[0-9a-f]{32}')
GIT_ID = re.compile(r'(?:[0-9a-f]{40}|[0-9a-f]{64})')
TIME = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d{1,6})?(?:Z|[+-]\d\d:\d\d)')
CORRECTIONS = re.compile(r'(?:0|[1-9][0-9]{0,3}|10000)')
TIMEOUT = re.compile(r'(?:[1-9]|[1-5][0-9]|60)')

EFFORTS = ('unknown', 'none', 'low', 'medium', 'high', 'xhigh', 'thinking')
ROUTES = ('codex', 'claude', 'grok', 'antigravity', 'mistral-vibe', 'opencode-go',
          'opencode-zen-free', 'perplexity-web', 'copilot-auto', 'unknown')
OUTCOMES = ('accepted', 'quality_issue', 'operational_failure', 'unaccepted')
WORK_KINDS = ('implementation', 'routine')
IMPLEMENTATION_ROUTES = ('codex', 'claude', 'grok', 'antigravity',
                         'mistral-vibe', 'opencode-go')
ROUTINE_ROUTES = IMPLEMENTATION_ROUTES + ('opencode-zen-free',
                                          'perplexity-web', 'copilot-auto')

REVISION_KEYS = {'candidate_commit', 'base_commit', 'task_sha256', 'worktree_sha256'}
PROCESS_KEYS = {'state', 'exit_code'}
VALIDATION_KEYS = {'state', 'scope', 'checks_run', 'checks_failed'}
PROFILE_KEYS = {'model', 'route', 'effort', 'task_type'}
PROVENANCE = {'source': 'operator_report', 'effective_model': 'unknown',
              'effective_effort': 'unknown', 'human_acceptance': False,
              'independent_review': False}
RECORD_KEYS = {'schema_version', 'id', 'worker', 'task', 'recorded_at',
               'observed_at', 'revision', 'process', 'validation', 'profile',
               'outcome', 'corrections', 'provenance'}

LIMITATIONS = (
    'operator-reported metadata only; effective model and effort remain unknown',
    'conditional advice; no autonomous winner, reservation or dispatch',
    'local admission observation only; provider readiness stays unknown',
    'no provider call was made; human acceptance is never granted here',
)

HELP = '''usage: unio experience <command> [options]

Local worker experience and selection advice. Record one final operator
assessment per native task revision, show the stored evidence, or get
conditional selection advice for one task type. Standard library only;
no provider call, no agent execution, no human acceptance.

commands:
  record WORKER TASK --model MODEL --route ROUTE --effort EFFORT
        --task-type TYPE --outcome OUTCOME [--corrections N]
        record one final operator assessment of one native task revision
  show [--task-type TYPE] [--json]
        show stored evidence grouped by profile
  suggest --task-type TYPE [--work-kind implementation|routine]
        [--json] [--timeout SECONDS]
        conditional selection advice from local evidence and observation

common options:
  --project PATH   explicit physical project root (coord/ and wt/)
  --help           show help for a command (works outside a workspace)

Routes: codex, claude, grok, antigravity, mistral-vibe, opencode-go,
opencode-zen-free, perplexity-web, copilot-auto, unknown.
Efforts: unknown, none, low, medium, high, xhigh, thinking.
Outcomes: accepted, quality_issue, operational_failure, unaccepted.
Model, route, effort and outcome are operator-reported declarations; the
effective model and effort remain unknown. An accepted record reports the
operator's acceptance only; it never grants human acceptance, merge, review
or publication. Advice is conditional; there is no autonomous winner,
reservation or dispatch.
'''


def fail(message):
    sys.stderr.write('unio experience: ' + message + '\n')
    raise SystemExit(2)


def is_label(value):
    return isinstance(value, str) and LABEL.fullmatch(value) is not None


def ident_ok(value):
    # Native worker/task ID rules: no path separators, traversal, control
    # characters, whitespace or leading dash.
    return (isinstance(value, str) and value not in ('', '.', '..')
            and '..' not in value and not value.startswith('-')
            and not any(c.isspace() or ord(c) < 32 or c in '/\\' for c in value))


def timestamp(value):
    if not isinstance(value, str) or TIME.fullmatch(value) is None:
        return None
    try:
        return datetime.datetime.fromisoformat(
            value.replace('Z', '+00:00')).astimezone(datetime.timezone.utc)
    except (ValueError, OverflowError):
        return None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _reject_constant(name):
    raise ValueError('non-finite JSON constant ' + name)


def _finite(value):
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(_finite(item) for item in value.values())
    if isinstance(value, list):
        return all(_finite(item) for item in value)
    return True


def parse_strict(data):
    """One strict UTF-8 JSON object; duplicates, non-finite numbers, non-object
    roots and undecodable text all fail instead of becoming stored state."""
    try:
        obj = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
        if not isinstance(obj, dict) or not _finite(obj):
            return None
    except (ValueError, UnicodeError, RecursionError):
        return None
    return obj


def open_regular(path, limit):
    """Open every component without following links; refuse FIFOs before reads."""
    parts = Path(os.path.abspath(path)).parts
    directory = os.open(parts[0], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            os.close(directory)
            directory = child
        descriptor = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW,
                             dir_fd=directory)
        try:
            info = os.fstat(descriptor)
            if info.st_size > limit:
                raise ValueError('input_file_exceeds_bound')
            if not stat.S_ISREG(info.st_mode):
                raise ValueError('unsupported input file')
            return descriptor, info
        except BaseException:
            os.close(descriptor)
            raise
    finally:
        os.close(directory)


def read_regular(path, limit):
    descriptor, before = open_regular(path, limit)
    with os.fdopen(descriptor, 'rb') as source:
        raw = source.read(limit + 1)
        after = os.fstat(source.fileno())
    if (len(raw) > limit or (before.st_size, before.st_mtime_ns, before.st_ctime_ns)
            != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
        raise ValueError('input changed or exceeded bound')
    return raw


def load_fleet_status():
    """The installed sibling observer is the only code this helper loads."""
    sibling = Path(__file__).resolve().parent / 'fleet-status.py'
    if not sibling.is_file():
        fail('fleet-status helper missing from installed library: ' + str(sibling))
    spec = importlib.util.spec_from_file_location('fleet_status', sibling)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def valid_revision(value):
    return (isinstance(value, dict) and set(value) == REVISION_KEYS
            and all(isinstance(item, str) and GIT_ID.fullmatch(item) is not None
                    for item in value.values()))


def valid_record(d):
    """Exact schema-1 record view; any deviation is corruption, not data."""
    if not isinstance(d, dict) or set(d) != RECORD_KEYS:
        return None
    if type(d['schema_version']) is not int or d['schema_version'] != 1:
        return None
    if not isinstance(d['id'], str) or len(d['id']) != 32 or GIT_ID.fullmatch(d['id']) is None:
        return None
    if not ident_ok(d['worker']) or not ident_ok(d['task']):
        return None
    if timestamp(d['recorded_at']) is None or timestamp(d['observed_at']) is None:
        return None
    if not valid_revision(d['revision']):
        return None
    process = d['process']
    if not isinstance(process, dict) or set(process) != PROCESS_KEYS:
        return None
    if process['state'] not in ('succeeded', 'failed'):
        return None
    if type(process['exit_code']) is not int or process['exit_code'] < 0:
        return None
    if (process['state'] == 'succeeded') != (process['exit_code'] == 0):
        return None
    validation = d['validation']
    if not isinstance(validation, dict) or set(validation) != VALIDATION_KEYS:
        return None
    if validation['state'] not in ('not_run', 'passed', 'failed', 'incomplete'):
        return None
    if validation['scope'] not in ('OK', 'VIOLATION', 'UNCHECKED'):
        return None
    for key in ('checks_run', 'checks_failed'):
        if type(validation[key]) is not int or validation[key] < 0:
            return None
    if validation['checks_failed'] > validation['checks_run']:
        return None
    if validation['state'] == 'passed' and (validation['scope'] != 'OK'
            or validation['checks_run'] < 1 or validation['checks_failed'] != 0):
        return None
    profile = d['profile']
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        return None
    if not is_label(profile['model']) or not is_label(profile['task_type']):
        return None
    if profile['route'] not in ROUTES or profile['effort'] not in EFFORTS:
        return None
    if d['outcome'] not in OUTCOMES:
        return None
    corrections = d['corrections']
    if corrections is not None and (type(corrections) is not int
                                   or not 0 <= corrections <= 10000):
        return None
    if d['provenance'] != PROVENANCE:
        return None
    if d['outcome'] == 'accepted' and not (process['state'] == 'succeeded'
                                           and validation['state'] == 'passed'):
        return None
    if d['outcome'] == 'operational_failure' and process['state'] != 'failed':
        return None
    return d


def record_identity(worker, task, revision):
    canonical = json.dumps(revision, ensure_ascii=True, sort_keys=True,
                           separators=(',', ':'))
    digest = hashlib.sha256(
        (worker + '\0' + task + '\0' + canonical).encode('utf-8')).hexdigest()
    return digest[:32]


def store_dirs(root):
    base = os.path.join(root, 'coord', 'experience')
    return base, os.path.join(base, 'records')


def check_store_dir(path, label):
    try:
        info = os.lstat(path)
    except OSError:
        fail('cannot inspect experience store path: ' + label)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        fail('unsafe experience store path: ' + label)


def ensure_store_dir(path, label):
    if os.path.lexists(path):
        check_store_dir(path, label)
        return
    try:
        os.makedirs(path, mode=0o700)
    except OSError:
        fail('cannot create experience store directory: ' + label)


def load_records(root):
    """Read the immutable store. Missing storage is an empty sample; anything
    unsafe, unknown, oversized or malformed is corruption and fails closed."""
    base, records_dir = store_dirs(root)
    if not os.path.lexists(base):
        return []
    check_store_dir(base, 'coord/experience')
    if not os.path.lexists(records_dir):
        return []
    check_store_dir(records_dir, 'coord/experience/records')
    names = []
    try:
        with os.scandir(records_dir) as entries:
            for entry in entries:
                if entry.name.startswith('.'):
                    continue  # transient writer scratch; never a published record
                if RECORD_NAME.fullmatch(entry.name) is None:
                    fail('unknown entry in experience store: '
                         + entry.name.encode('unicode_escape').decode('ascii'))
                info = entry.stat(follow_symlinks=False)
                if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
                    fail('unsafe experience record path: ' + entry.name)
                if info.st_nlink != 1:
                    fail('hardlinked experience record refused: ' + entry.name)
                if info.st_size > MAX_RECORD_BYTES:
                    fail('oversized experience record: ' + entry.name)
                names.append(entry.name)
    except OSError:
        fail('cannot read experience store')
    if len(names) > MAX_STORE_RECORDS:
        fail('experience store exceeds its record bound')
    records = []
    for name in sorted(names):
        try:
            raw = read_regular(os.path.join(records_dir, name), MAX_RECORD_BYTES)
        except (OSError, ValueError):
            fail('cannot read experience record: ' + name)
        obj = parse_strict(raw)
        if obj is None:
            fail('malformed experience record: ' + name)
        record = valid_record(obj)
        if record is None:
            fail('invalid experience record schema: ' + name)
        if record['id'] != name[:-len('.json')]:
            fail('experience record identity mismatch: ' + name)
        records.append(record)
    return records


def sweep_temps(records_dir):
    # The caller holds the store lock, so scratch left here is from a killed
    # writer. Links are never followed or removed; reads refuse real records.
    try:
        names = os.listdir(records_dir)
    except OSError:
        return
    for name in names:
        if not name.startswith('.record-'):
            continue
        stale = os.path.join(records_dir, name)
        try:
            if os.path.islink(stale):
                continue
            if os.path.isdir(stale):
                shutil.rmtree(stale)
            else:
                os.unlink(stale)
        except OSError:
            pass


def same_assessment(old, new):
    for key in ('worker', 'task', 'revision', 'process', 'validation',
                'profile', 'outcome', 'corrections', 'provenance'):
        if old[key] != new[key]:
            return False
    return True


def write_record(root, record):
    """Transactional, lock-serialized store write. An identical replay is
    idempotent; a conflicting assessment for the same revision is refused
    with the existing record unchanged."""
    base, records_dir = store_dirs(root)
    ensure_store_dir(base, 'coord/experience')
    ensure_store_dir(records_dir, 'coord/experience/records')
    lock_path = os.path.join(base, 'lock')
    try:
        lock_fd = os.open(lock_path, os.O_RDWR | os.O_CREAT
                          | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        fail('cannot open experience store lock')
    try:
        info = os.fstat(lock_fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            fail('unsafe experience store lock')
        fcntl.flock(lock_fd, fcntl.LOCK_EX)
    except OSError:
        os.close(lock_fd)
        fail('cannot lock experience store')
    temp = None
    try:
        sweep_temps(records_dir)
        existing = load_records(root)
        known = {item['id']: item for item in existing}
        if record['id'] in known:
            previous = known[record['id']]
            if same_assessment(previous, record):
                return previous, False
            fail('conflicting assessment for this task revision; '
                 'the existing record is unchanged')
        if len(existing) >= MAX_STORE_RECORDS:
            fail('experience store is full; no new record can be added')
        target = os.path.join(records_dir, record['id'] + '.json')
        fd_temp, temp = tempfile.mkstemp(prefix='.record-', dir=records_dir)
        with os.fdopen(fd_temp, 'w') as out:
            json.dump(record, out, ensure_ascii=True, sort_keys=True, indent=2)
            out.write('\n')
            out.flush()
            os.fsync(out.fileno())
        try:
            os.link(temp, target, follow_symlinks=False)
        except FileExistsError:
            # A concurrent writer without the lock; compare honestly.
            try:
                prior = valid_record(parse_strict(
                    read_regular(target, MAX_RECORD_BYTES)))
            except (OSError, ValueError):
                fail('cannot read concurrent experience record')
            if prior is None or not same_assessment(prior, record):
                fail('conflicting assessment for this task revision; '
                     'the existing record is unchanged')
            return prior, False
        directory_fd = os.open(records_dir, os.O_RDONLY
                               | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return record, True
    finally:
        if temp is not None and os.path.lexists(temp):
            try:
                os.unlink(temp)
            except OSError:
                pass
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(lock_fd)


def valid_result(obj, worker, task):
    """Strict native result view for exactly these identifiers and their
    current revision. Running, not-run, stale, failed-snapshot, mismatched
    or malformed evidence is refused, never recorded."""
    if not isinstance(obj, dict) or obj.get('schema_version') != 1:
        fail('malformed native result schema')
    if obj.get('worker') != worker or obj.get('task') != task:
        fail('native result identity mismatch')
    revision = obj.get('revision')
    current = obj.get('current_revision')
    if not valid_revision(revision) or current is None or current != revision:
        fail('native result has no current revision binding')
    if obj.get('stale') is not False:
        fail('native result is stale for the current revision')
    process = obj.get('process')
    if not isinstance(process, dict):
        fail('malformed native process evidence')
    if process.get('state') not in ('succeeded', 'failed'):
        fail('native process is running or not run; no final assessment can be recorded')
    if 'post_run_snapshot' in process:
        fail('native post-run snapshot failed; evidence is stale')
    code = process.get('exit_code')
    if type(code) is not int or code < 0:
        fail('malformed native process exit')
    if (process['state'] == 'succeeded') != (code == 0):
        fail('inconsistent native process exit')
    if process.get('revision') != revision:
        fail('native process evidence is bound to another revision')
    validation = obj.get('validation')
    if not isinstance(validation, dict):
        fail('malformed native validation evidence')
    state = validation.get('state')
    if state not in ('not_run', 'passed', 'failed', 'incomplete'):
        fail('malformed native validation state')
    if validation.get('scope') not in ('OK', 'VIOLATION', 'UNCHECKED'):
        fail('malformed native validation scope')
    ran, failed = validation.get('checks_run'), validation.get('checks_failed')
    if (type(ran) is not int or type(failed) is not int
            or ran < 0 or failed < 0 or failed > ran):
        fail('malformed native validation counts')
    if state == 'passed' and (validation['scope'] != 'OK' or ran < 1 or failed != 0):
        fail('inconsistent native validation pass')
    bound = validation.get('revision')
    if state == 'not_run':
        if bound is not None:
            fail('inconsistent native validation binding')
    elif bound != revision:
        fail('native validation evidence is bound to another revision')
    process_facts = {'state': process['state'], 'exit_code': code}
    validation_facts = {'state': state, 'scope': validation['scope'],
                       'checks_run': ran, 'checks_failed': failed}
    return process_facts, validation_facts, revision


def build_profiles(records, now):
    """Group by account alias (the native worker prefix), requested model,
    route, requested effort and exact task type. A task contributes at most
    once to a profile's accepted-task counts."""
    groups = {}
    for record in records:
        profile = record['profile']
        key = (record['worker'].split('-')[0], profile['model'], profile['route'],
               profile['effort'], profile['task_type'])
        groups.setdefault(key, []).append(record)
    cutoff = now - datetime.timedelta(days=RECENT_DAYS)
    profiles = []
    for key in sorted(groups):
        rows = groups[key]
        observed = [timestamp(item['observed_at']) for item in rows]
        accepted = {item['task'] for item in rows if item['outcome'] == 'accepted'}
        recent = {item['task'] for item in rows if item['outcome'] == 'accepted'
                  and timestamp(item['observed_at']) >= cutoff}
        known = [item['corrections'] for item in rows
                 if item['corrections'] is not None]
        examples = sorted((item for item in rows if item['outcome'] == 'accepted'),
                         key=lambda item: (timestamp(item['observed_at']), item['task']),
                         reverse=True)
        profiles.append({
            'account_alias': key[0], 'model': key[1], 'route': key[2],
            'effort': key[3], 'task_type': key[4],
            'attempts': len(rows),
            'tasks': len({item['task'] for item in rows}),
            'accepted_tasks': len(accepted),
            'recent_accepted_tasks': len(recent),
            'quality_issues': sum(1 for item in rows if item['outcome'] == 'quality_issue'),
            'operational_failures': sum(1 for item in rows
                                         if item['outcome'] == 'operational_failure'),
            'unaccepted_attempts': sum(1 for item in rows if item['outcome'] == 'unaccepted'),
            'corrections': {'known_total': sum(known) if known else None,
                            'known_records': len(known),
                            'unknown_records': len(rows) - len(known)},
            'newest_observation': max(rows, key=lambda item: timestamp(
                item['observed_at']))['observed_at'],
            'sample_age_seconds': round((now - min(observed)).total_seconds(), 3),
            'accepted_examples': [{'task': item['task'],
                                   'observed_at': item['observed_at']}
                                  for item in examples[:MAX_EXAMPLES]],
        })
    return profiles


def _fresh_windows(group):
    windows = []
    manual = group.get('manual_allowance')
    if manual and manual.get('status') == 'recorded':
        windows.extend(manual.get('windows', {}).values())
    cached = group.get('cached_allowance')
    if cached and cached.get('state') == 'ok' and cached.get('freshness') == 'fresh':
        for bucket in cached.get('buckets', {}).values():
            for window in bucket.get('windows', {}).values():
                if window:
                    windows.append(window)
    return [window for window in windows if window.get('status') == 'fresh']


def agent_admission(report, agent):
    """Bounded local admission view for one agent: STOP/off/binary facts,
    shared-group slots including the lead, cached sign-in and fresh cached
    allowance. Stale, missing or expired capacity stays unknown."""
    for group_name, group in report['groups'].items():
        if agent in group['agents']:
            row = group['agents'][agent]
            auth_view = row.get('cached_auth')
            fresh_signed_out = bool(auth_view and auth_view.get('status') == 'fresh'
                                    and auth_view.get('authentication') == 'signed_out')
            fresh = _fresh_windows(group)
            exhausted = any(window.get('usable_remaining_percent') == 0
                            for window in fresh)
            available = any(window.get('usable_remaining_percent') is not None
                            and window.get('usable_remaining_percent') > 0
                            for window in fresh)
            return {'group': group_name,
                    'admission_state': row['admission_state'],
                    'reasons': row['reasons'],
                    'auth': auth_view.get('authentication') if auth_view else 'unknown',
                    'allowance': ('exhausted' if exhausted
                                   else 'available' if available else 'unknown'),
                    'fresh_signed_out': fresh_signed_out,
                    'fresh_exhausted': exhausted}
    return {'group': None, 'admission_state': 'unknown',
            'reasons': ['agent_not_observed'], 'auth': 'unknown',
            'allowance': 'unknown', 'fresh_signed_out': False,
            'fresh_exhausted': False}


def cmd_record(runner, root, args):
    for label, value in (('worker', args.worker), ('task', args.task)):
        if not ident_ok(value):
            fail('invalid ' + label + ' ID: '
                 + value.encode('unicode_escape').decode('ascii'))
    if not is_label(args.model):
        fail('--model must be a bounded ASCII token')
    if not is_label(args.task_type):
        fail('--task-type must be a bounded ASCII token')
    if args.route not in ROUTES:
        fail('--route must be one of: ' + ', '.join(ROUTES))
    if args.effort not in EFFORTS:
        fail('--effort must be one of: ' + ', '.join(EFFORTS))
    if args.outcome not in OUTCOMES:
        fail('--outcome must be one of: ' + ', '.join(OUTCOMES))
    corrections = None
    if args.corrections is not None:
        if CORRECTIONS.fullmatch(args.corrections) is None:
            fail('--corrections must be an integer 0..10000')
        corrections = int(args.corrections)
    fleet = load_fleet_status()
    observed_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
    obj, reason = fleet.observe(runner, str(root), ['result', args.worker, args.task],
                                time.monotonic() + RECORD_DEADLINE_SECONDS)
    if obj is None:
        fail('native result unavailable (' + reason + '); nothing was recorded')
    process_facts, validation_facts, revision = valid_result(obj, args.worker, args.task)
    if args.outcome == 'accepted':
        if process_facts['state'] != 'succeeded' or validation_facts['state'] != 'passed':
            fail('accepted requires Source exit zero and current native validation PASS')
    elif args.outcome == 'operational_failure':
        if process_facts['state'] != 'failed':
            fail('operational_failure requires a nonzero Source exit')
    record = {
        'schema_version': SCHEMA_VERSION,
        'id': record_identity(args.worker, args.task, revision),
        'worker': args.worker, 'task': args.task,
        'recorded_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'observed_at': observed_at,
        'revision': revision,
        'process': process_facts,
        'validation': validation_facts,
        'profile': {'model': args.model, 'route': args.route,
                    'effort': args.effort, 'task_type': args.task_type},
        'outcome': args.outcome,
        'corrections': corrections,
        'provenance': dict(PROVENANCE),
    }
    if valid_record(record) is None:
        fail('internal record validation failed; nothing was written')
    stored, created = write_record(root, record)
    print('Experience record {} {}.'.format(
        stored['id'], 'stored' if created else 'already stored; identical replay is idempotent'))
    print('  worker/task: {}/{} (revision {})'.format(
        stored['worker'], stored['task'], stored['revision']['candidate_commit'][:12]))
    print('  profile: model {}, route {}, effort {}, task-type {}'.format(
        stored['profile']['model'], stored['profile']['route'],
        stored['profile']['effort'], stored['profile']['task_type']))
    outcome_text = stored['outcome']
    if outcome_text == 'accepted':
        outcome_text += ' (reported acceptance; not human acceptance, merge or review)'
    print('  outcome: ' + outcome_text)
    print('  corrections: {}'.format(
        stored['corrections'] if stored['corrections'] is not None else 'unknown'))
    print('Operator-reported metadata; effective model/effort unknown. '
          'No provider call was made.')
    return 0


def cmd_show(root, args):
    task_type = args.task_type
    if task_type is not None and not is_label(task_type):
        fail('--task-type must be a bounded ASCII token')
    records = load_records(root)
    if task_type is not None:
        records = [item for item in records
                   if item['profile']['task_type'] == task_type]
    now = datetime.datetime.now(datetime.timezone.utc)
    profiles = build_profiles(records, now)
    report = {
        'schema_version': SCHEMA_VERSION,
        'command': 'show',
        'project': root,
        'checked_at': now.isoformat(),
        'task_type': task_type,
        'records': len(records),
        'profiles': profiles,
        'human_acceptance': False,
        'provider_calls': False,
    }
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=True,
                                    allow_nan=False) + '\n')
    else:
        sys.stdout.write(render_show(report) + '\n')
    return 0


def cmd_suggest(runner, root, args):
    if not is_label(args.task_type):
        fail('--task-type must be a bounded ASCII token')
    if TIMEOUT.fullmatch(args.timeout) is None:
        fail('--timeout must be 1..60 seconds')
    timeout = int(args.timeout)
    records = load_records(root)
    selected = [item for item in records
                if item['profile']['task_type'] == args.task_type]
    now = datetime.datetime.now(datetime.timezone.utc)
    profiles = build_profiles(selected, now)
    fleet = load_fleet_status()
    try:
        stop = os.path.exists(os.path.join(root, 'coord', 'STOP'))
    except OSError:
        stop = False
    observed, statuses = fleet.collect(runner, str(root), timeout)
    report = fleet.build_report(str(root), timeout, stop, observed, statuses)
    admission = {}
    for profile in profiles:
        agent = profile['account_alias']
        if agent not in admission:
            admission[agent] = agent_admission(report, agent)
    eligible_routes = (ROUTINE_ROUTES if args.work_kind == 'routine'
                       else IMPLEMENTATION_ROUTES)
    candidates = [profile for profile in profiles
                  if profile['route'] in eligible_routes
                  and profile['recent_accepted_tasks'] >= MIN_RECENT_ACCEPTED]
    candidates.sort(key=lambda profile: (
        -profile['recent_accepted_tasks'],
        profile['quality_issues'],
        (0, profile['corrections']['known_total'])
        if profile['corrections']['known_total'] is not None else (1, 0),
        (profile['account_alias'], profile['model'], profile['route'],
         profile['effort'])))
    suggestions = []
    for profile in candidates:
        agent = admission[profile['account_alias']]
        recommendable = (agent['admission_state'] == 'clear'
                         and not agent['fresh_signed_out']
                         and not agent['fresh_exhausted'])
        conditions = ['provider_readiness_unknown', 'human_acceptance_false']
        if agent['admission_state'] != 'clear':
            conditions.append('local_admission_' + agent['admission_state'])
        if agent['fresh_signed_out']:
            conditions.append('fresh_signed_out')
        if agent['fresh_exhausted']:
            conditions.append('fresh_exhausted_allowance')
        if agent['auth'] == 'unknown':
            conditions.append('authentication_unknown')
        if agent['allowance'] == 'unknown':
            conditions.append('allowance_unknown')
        suggestions.append({
            'account_alias': profile['account_alias'],
            'model': profile['model'], 'route': profile['route'],
            'effort': profile['effort'], 'task_type': profile['task_type'],
            'recent_accepted_tasks': profile['recent_accepted_tasks'],
            'quality_issues': profile['quality_issues'],
            'corrections': profile['corrections'],
            'admission_state': agent['admission_state'],
            'admission_reasons': agent['reasons'],
            'auth': agent['auth'], 'allowance': agent['allowance'],
            'recommendable': recommendable, 'conditions': conditions})
    decision = 'conditional_suggestions' if suggestions else 'insufficient_evidence'
    report_out = {
        'schema_version': SCHEMA_VERSION,
        'command': 'suggest',
        'project': root,
        'checked_at': now.isoformat(),
        'task_type': args.task_type,
        'work_kind': args.work_kind,
        'timeout_seconds': timeout,
        'decision': decision,
        'human_acceptance': False,
        'provider_calls': False,
        'evidence': {'records': len(selected), 'profiles': profiles},
        'admission': {'fleet_sources': statuses, 'stop': stop,
                      'agents': admission},
        'advice': {'suggestions': suggestions, 'limitations': list(LIMITATIONS)},
    }
    if args.json:
        sys.stdout.write(json.dumps(report_out, indent=2, ensure_ascii=True,
                                    allow_nan=False) + '\n')
    else:
        sys.stdout.write(render_suggest(report_out) + '\n')
    return 0


def fmt_age(seconds):
    return '%g' % seconds


def render_show(report):
    lines = []
    lines.append('Project: ' + report['project'].encode('unicode_escape').decode('ascii'))
    lines.append('Records: {} | Task type filter: {}'.format(
        report['records'], report['task_type'] if report['task_type'] else 'none'))
    if not report['profiles']:
        lines.append('No experience records'
                     + (' for this task type.' if report['task_type'] else '.'))
    for profile in report['profiles']:
        lines.append('')
        lines.append('Profile {} / {} / {} / {} / {}'.format(
            profile['account_alias'], profile['model'], profile['route'],
            profile['effort'], profile['task_type']))
        corrections = profile['corrections']
        if corrections['known_total'] is not None:
            burden = '{} known across {} record(s), {} unknown'.format(
                corrections['known_total'], corrections['known_records'],
                corrections['unknown_records'])
        else:
            burden = 'unknown across {} record(s)'.format(
                corrections['unknown_records'])
        lines.append('  attempts {} across {} tasks; reported accepted tasks {}; '
                     'quality issues {};'.format(
                         profile['attempts'], profile['tasks'],
                         profile['accepted_tasks'], profile['quality_issues']))
        lines.append('  operational failures {}; unaccepted attempts {}; '
                     'correction burden {}'.format(
                         profile['operational_failures'],
                         profile['unaccepted_attempts'], burden))
        lines.append('  newest observation {}; sample age {}s'.format(
            profile['newest_observation'], fmt_age(profile['sample_age_seconds'])))
    lines.append('')
    lines.append('Operator-reported metadata only; effective model and effort unknown.')
    lines.append('No universal model score. Human acceptance: false. Provider calls: false.')
    return '\n'.join(lines)


def render_suggest(report):
    lines = []
    lines.append('Project: ' + report['project'].encode('unicode_escape').decode('ascii'))
    lines.append('Task type: {} | Work kind: {} | Timeout: {}s'.format(
        report['task_type'], report['work_kind'], report['timeout_seconds']))
    lines.append('Decision: ' + report['decision'])
    evidence = report['evidence']
    lines.append('')
    lines.append('Evidence ({} record(s) for this task type):'.format(evidence['records']))
    if not evidence['profiles']:
        lines.append('  no experience records for this task type')
    for profile in evidence['profiles']:
        corrections = profile['corrections']
        burden = (str(corrections['known_total'])
                  if corrections['known_total'] is not None else 'unknown')
        lines.append('  {} / {} / {} / {}: {} recent reported accepted task(s), '
                     '{} quality issue(s), correction burden {}'.format(
                         profile['account_alias'], profile['model'],
                         profile['route'], profile['effort'],
                         profile['recent_accepted_tasks'],
                         profile['quality_issues'], burden))
        for example in profile['accepted_examples']:
            lines.append('    example: task {} accepted {}'.format(
                example['task'], example['observed_at']))
    lines.append('')
    lines.append('Local admission (bounded local observation; never provider state):')
    for name in sorted(report['admission']['agents']):
        agent = report['admission']['agents'][name]
        state = agent['admission_state']
        if agent['reasons']:
            state += ' (' + ', '.join(agent['reasons']) + ')'
        lines.append('  {}: {} | auth: {} | allowance: {}'.format(
            name, state, agent['auth'], agent['allowance']))
    lines.append('')
    if report['decision'] == 'conditional_suggestions':
        lines.append('Conditional suggestions (all qualifying options; operator decides):')
        for index, suggestion in enumerate(report['advice']['suggestions'], 1):
            head = '{}. {} / {} / {} / {}'.format(
                index, suggestion['account_alias'], suggestion['model'],
                suggestion['route'], suggestion['effort'])
            if suggestion['recommendable']:
                lines.append('  ' + head + ' — admission clear; conditional')
            else:
                lines.append('  ' + head + ' — not a positive recommendation now')
            lines.append('     recent accepted tasks {}; quality issues {}; '
                         'correction burden {}; conditions: {}'.format(
                             suggestion['recent_accepted_tasks'],
                             suggestion['quality_issues'],
                             suggestion['corrections']['known_total']
                             if suggestion['corrections']['known_total'] is not None
                             else 'unknown',
                             ', '.join(suggestion['conditions'])))
    else:
        lines.append('Fewer than three distinct reported accepted tasks in the last '
                     '{} days for any'.format(RECENT_DAYS))
        lines.append('eligible profile; no worker selected. Visible examples stay above.')
    lines.append('')
    for limitation in report['advice']['limitations']:
        lines.append('Limitation: ' + limitation)
    lines.append('Human acceptance: false. Provider calls: false.')
    return '\n'.join(lines)


def check_duplicate_flags(argv):
    seen = set()
    for token in argv:
        if token.startswith('--'):
            name = token.split('=', 1)[0]
            if name in seen:
                fail('duplicate option: ' + name)
            seen.add(name)


def resolve_root(project):
    if not project:
        fail('no project selected; pass --project PATH')
    root = os.path.realpath(os.path.abspath(project))
    for required in ('coord', 'wt'):
        if not os.path.isdir(os.path.join(root, required)):
            fail('no Unio workspace (coord/ and wt/) under: '
                 + project.encode('unicode_escape').decode('ascii'))
    return root


def main(argv=None):
    native = list(sys.argv[1:] if argv is None else argv)
    if not native:
        fail('installed runner path missing')
    runner = native.pop(0)
    if not native:
        sys.stdout.write(HELP)
        return 0
    command = native.pop(0)
    if command in ('-h', '--help'):
        sys.stdout.write(HELP)
        return 0
    if command not in ('record', 'show', 'suggest'):
        fail("unknown command '" + command.encode('unicode_escape').decode('ascii')
             + "' (use record, show or suggest)")
    check_duplicate_flags(native)
    if command == 'record':
        parser = argparse.ArgumentParser(
            prog='unio experience record', allow_abbrev=False,
            description='Record one final operator assessment of one native task revision.')
        parser.add_argument('worker', metavar='WORKER')
        parser.add_argument('task', metavar='TASK')
        parser.add_argument('--model', required=True, metavar='MODEL',
                            help='operator-reported requested model (bounded ASCII token)')
        parser.add_argument('--route', required=True, metavar='ROUTE',
                            help='declared route; one of: ' + ', '.join(ROUTES))
        parser.add_argument('--effort', required=True, metavar='EFFORT',
                            help='operator-reported requested effort; one of: '
                                 + ', '.join(EFFORTS))
        parser.add_argument('--task-type', required=True, dest='task_type',
                            metavar='TYPE', help='exact task type label')
        parser.add_argument('--outcome', required=True, metavar='OUTCOME',
                            help='one of: ' + ', '.join(OUTCOMES))
        parser.add_argument('--corrections', metavar='N',
                            help='operator-reported correction count 0..10000 '
                                 '(missing means unknown, not zero)')
        parser.add_argument('--project', metavar='PATH',
                            help='explicit physical project root (coord/ and wt/)')
        args = parser.parse_args(native)
        return cmd_record(runner, resolve_root(args.project), args)
    if command == 'show':
        parser = argparse.ArgumentParser(
            prog='unio experience show', allow_abbrev=False,
            description='Show stored experience evidence grouped by profile.')
        parser.add_argument('--task-type', dest='task_type', metavar='TYPE',
                            help='only records with this exact task type')
        parser.add_argument('--json', action='store_true',
                            help='write exactly one schema-1 JSON object')
        parser.add_argument('--project', metavar='PATH',
                            help='explicit physical project root (coord/ and wt/)')
        args = parser.parse_args(native)
        return cmd_show(resolve_root(args.project), args)
    parser = argparse.ArgumentParser(
        prog='unio experience suggest', allow_abbrev=False,
        description='Conditional worker selection advice for one task type.')
    parser.add_argument('--task-type', required=True, dest='task_type',
                        metavar='TYPE', help='exact task type label')
    parser.add_argument('--work-kind', choices=WORK_KINDS, default='implementation',
                        dest='work_kind', metavar='KIND',
                        help='advice kind (default implementation; free routes '
                             'are eligible for routine advice only)')
    parser.add_argument('--json', action='store_true',
                        help='write exactly one schema-1 JSON object')
    parser.add_argument('--timeout', default=str(SUGGEST_TIMEOUT_DEFAULT),
                        metavar='SECONDS',
                        help='whole observation deadline, 1..60 seconds (default 10)')
    parser.add_argument('--project', metavar='PATH',
                        help='explicit physical project root (coord/ and wt/)')
    args = parser.parse_args(native)
    return cmd_suggest(runner, resolve_root(args.project), args)


if __name__ == '__main__':
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write('unio experience: interrupted\n')
        raise SystemExit(130)
