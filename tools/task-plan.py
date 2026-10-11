#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Bounded read-only concurrent task plan observation and recommendations.

Explains concurrent recommendations before dispatch based on an explicit
task inventory, native task markdown scopes, accepted revision evidence,
and fleet status. No executor, provider calls, queue creation or state mutation.
"""

import argparse
import datetime
import hashlib
import importlib.util
import json
import math
import os
import re
import select
import signal
import sqlite3
import stat
import subprocess
import sys
import time
from pathlib import Path

SCHEMA_VERSION = 1
MAX_INVENTORY_BYTES = 256 * 1024
MAX_TASK_FILE_BYTES = 256 * 1024
MAX_DRAFT_FILE_BYTES = 64 * 1024
MAX_DB_BYTES = 4 * 1024 * 1024
MAX_DB_ROWS = 512
MAX_TASKS = 128
MAX_ACCEPTED = 128
MAX_DEPENDENCIES = 128
OBSERVATION_DEADLINE = None


def remaining(cap):
    if OBSERVATION_DEADLINE is None:
        return cap
    return max(0.0, min(cap, OBSERVATION_DEADLINE - time.monotonic()))


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
    return raw, before

HEX32 = re.compile(r'^[0-9a-f]{32}$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')
HEX64 = re.compile(r'^[0-9a-f]{64}$')
WORKER_RE = re.compile(r'^[a-z][a-z0-9_-]{0,63}$')
TASK_ID_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$')
KNOWN_JOB_COLUMNS = (
    'id', 'request_key', 'draft_id', 'draft_sha256', 'worker', 'created_at',
    'state', 'approval_key', 'approved_at', 'reservation_key', 'reserved_at',
    'unknown_at', 'cancelled_at'
)


def fail(message, code=2):
    sys.stderr.write('unio plan: ' + message + '\n')
    raise SystemExit(code)


def is_int(value):
    return type(value) is int


def is_valid_task_id(value):
    return (
        isinstance(value, str)
        and TASK_ID_RE.fullmatch(value) is not None
        and '..' not in value
        and not value.startswith('-')
    )


def is_valid_worker_id(value):
    return isinstance(value, str) and WORKER_RE.fullmatch(value) is not None


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key: ' + str(key))
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


def parse_strict_json(data):
    try:
        obj = json.loads(
            data.decode('utf-8'),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant
        )
        if not isinstance(obj, dict) or not _finite(obj):
            return None
    except (ValueError, UnicodeError, RecursionError):
        return None
    return obj


def load_fleet_status():
    sibling = Path(__file__).resolve().parent / 'fleet-status.py'
    if not sibling.is_file():
        fail('fleet-status helper missing from installed library: ' + str(sibling))
    spec = importlib.util.spec_from_file_location('fleet_status', sibling)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def check_path_no_symlinks(base_dir, relative_path):
    cur = Path(base_dir)
    for part in Path(relative_path).parts:
        cur = cur / part
        if cur.is_symlink():
            return False, 'symlink component detected: ' + part
        try:
            st = cur.lstat()
            if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
                return False, 'special file detected: ' + part
        except OSError:
            pass
    return True, None


def resolve_repo(project_root):
    for candidate in (project_root / 'repo', project_root):
        if candidate.is_dir():
            rc, _ = git_query(candidate, ['rev-parse', '--git-dir'], timeout=2.0)
            if rc == 0:
                return candidate
    return None


def git_query(repo_dir, argv, timeout=5.0):
    timeout = remaining(timeout)
    if timeout <= 0:
        return -1, b''
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_NO_REPLACE_OBJECTS='1')
    try:
        proc = subprocess.Popen(
            ['git', '-C', str(repo_dir)] + list(argv),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            start_new_session=True
        )
    except OSError:
        return -1, b''
    deadline = time.monotonic() + timeout
    streams = {proc.stdout.fileno(), proc.stderr.fileno()}
    for descriptor in streams:
        os.set_blocking(descriptor, False)
    output, seen, stopped, failed = bytearray(), 0, False, False
    try:
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                failed = True
                break
            if not stopped and os.waitid(os.P_PID, proc.pid,
                    os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                stopped = True
            if not streams:
                if stopped:
                    break
                time.sleep(min(.05, left))
                continue
            for descriptor in select.select(list(streams), [], [], min(.05, left))[0]:
                chunk = os.read(descriptor, min(65536, 65536 - seen + 1))
                if not chunk:
                    streams.remove(descriptor)
                    continue
                seen += len(chunk)
                if seen > 65536:
                    failed = True
                    break
                if descriptor == proc.stdout.fileno():
                    output.extend(chunk)
            if failed:
                break
    except OSError:
        failed = True
    finally:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.stdout.close()
        proc.stderr.close()
        proc.wait(timeout=1)
    return (-1, b'') if failed else (proc.returncode, bytes(output))


def get_repo_head(repo_dir, timeout=5.0):
    if repo_dir is None:
        return None
    rc, stdout = git_query(repo_dir, ['rev-parse', '--verify', '-q', 'HEAD^{commit}'], timeout=timeout)
    if rc == 0:
        val = stdout.decode('ascii', 'replace').strip()
        if HEX40.fullmatch(val):
            return val
    return None


def is_ancestor_commit(repo_dir, ancestor, base, timeout=5.0):
    if repo_dir is None:
        return False
    rc, _ = git_query(repo_dir, ['merge-base', '--is-ancestor', ancestor, base], timeout=timeout)
    return rc == 0


def validate_scope_pattern(pattern):
    if not isinstance(pattern, str) or not pattern:
        return False, 'empty scope pattern'
    if '\\' in pattern:
        return False, 'backslash in scope pattern'
    if any(ord(c) < 32 or ord(c) == 127 for c in pattern):
        return False, 'control character in scope pattern'
    if pattern.startswith('/'):
        return False, 'absolute path in scope pattern'
    if pattern == '**':
        return True, None
    parts = pattern.split('/')
    if any(part == '..' for part in parts):
        return False, 'traversal in scope pattern'
    if any(part == '.' for part in parts):
        return False, 'dot component in scope pattern'
    if '' in parts[:-1]:
        return False, 'empty segment or duplicate slash in scope pattern'

    if pattern.endswith('/**'):
        base = pattern[:-3]
        if not base or any(ch in base for ch in ('*', '?', '[', ']')):
            return False, 'invalid recursive glob'
        if os.path.normpath(base) != base:
            return False, 'non-normalized recursive glob'
        return True, None

    if pattern.endswith('/'):
        base = pattern[:-1]
        if not base or any(ch in base for ch in ('*', '?', '[', ']')):
            return False, 'invalid directory scope'
        if os.path.normpath(base) != base:
            return False, 'non-normalized directory scope'
        return True, None

    if any(ch in pattern for ch in ('*', '?', '[', ']')):
        return False, 'unsupported glob pattern'
    if os.path.normpath(pattern) != pattern:
        return False, 'non-normalized path scope'
    return True, None


def scopes_conflict(scope1, scope2):
    if scope1 == '**' or scope2 == '**':
        return True
    if scope1 == scope2:
        return True
    p1 = scope1[:-3] if scope1.endswith('/**') else (scope1[:-1] if scope1.endswith('/') else scope1)
    p2 = scope2[:-3] if scope2.endswith('/**') else (scope2[:-1] if scope2.endswith('/') else scope2)
    is_dir1 = scope1.endswith('/**') or scope1.endswith('/')
    is_dir2 = scope2.endswith('/**') or scope2.endswith('/')

    if p1 == p2:
        return True
    if is_dir1 and p2.startswith(p1 + '/'):
        return True
    if is_dir2 and p1.startswith(p2 + '/'):
        return True
    if p1.startswith(p2 + '/') or p2.startswith(p1 + '/'):
        return True
    return False


def task_scopes_conflict(task_scopes, held_scopes):
    for s1 in task_scopes:
        for s2, held_by in held_scopes:
            if scopes_conflict(s1, s2):
                return True, s1, s2, held_by
    return False, None, None, None


def parse_task_file(coord_dir, task_id, expected_sha256):
    task_file = coord_dir / 'tasks' / (task_id + '.md')
    ok, err = check_path_no_symlinks(coord_dir, Path('tasks') / (task_id + '.md'))
    if not ok:
        return None, None, 'unresolved', 'task_path_unsafe'
    try:
        raw, _ = read_regular(task_file, MAX_TASK_FILE_BYTES)
    except FileNotFoundError:
        return None, None, 'unresolved', 'missing_task_file'
    except (OSError, ValueError):
        return None, None, 'unresolved', 'cannot_read_task_file'

    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        return None, None, 'unresolved', 'task_hash_mismatch'

    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        return None, None, 'unresolved', 'task_file_invalid_utf8'

    lines = text.splitlines()
    scope_headers = [i for i, line in enumerate(lines) if line.strip() == '## Allowed scope']
    if len(scope_headers) != 1:
        return None, None, 'unresolved', 'missing_or_ambiguous_allowed_scope'

    start_idx = scope_headers[0] + 1
    raw_scope_lines = []
    for line in lines[start_idx:]:
        stripped = line.strip()
        if stripped.startswith('#'):
            break
        if stripped.startswith('- '):
            raw_scope_lines.append(stripped[2:].strip())

    if not raw_scope_lines:
        return None, None, 'unresolved', 'empty_allowed_scope'

    validated_scopes = []
    for pat in raw_scope_lines:
        valid, err = validate_scope_pattern(pat)
        if not valid:
            return None, None, 'unresolved', 'unsupported_scope_pattern'
        validated_scopes.append(pat)

    if len(validated_scopes) > 128 or any(len(pat) > 1024 for pat in validated_scopes):
        return None, None, 'unresolved', 'scope_size_exceeded'

    return validated_scopes, actual_sha256, 'ok', None


def observe_browser_job(coord_dir, job_id, worker):
    db_path = coord_dir / 'ui-jobs.sqlite3'
    descriptor, conn = None, None
    deadline = time.monotonic() + remaining(5)
    try:
        if any(os.path.lexists(str(db_path) + suffix)
               for suffix in ('-wal', '-shm', '-journal')):
            return 'unresolved', 'unsupported_queue_sidecar'
        descriptor, before = open_regular(db_path, MAX_DB_BYTES)
        # Keep a no-follow descriptor open throughout SQLite observation. The
        # controlled proc path binds this read-only connection to that inode.
        conn = sqlite3.connect('file:/proc/self/fd/' + str(descriptor)
                               + '?mode=ro&immutable=1', uri=True, timeout=0)
        conn.execute('PRAGMA query_only = ON')
        conn.execute('PRAGMA temp_store = MEMORY')
        conn.set_progress_handler(lambda: int(time.monotonic() >= deadline), 1000)
        installed = Path(__file__).parent / 'browser/job_store.py'
        source = Path(__file__).parent.parent / 'bridge/job_store.py'
        spec = importlib.util.spec_from_file_location('task_plan_job_types',
                                                      installed if installed.is_file() else source)
        types = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(types)
        # These pure validators never construct a store or migrate a database.
        types.JobStore._verify(conn)
        count = conn.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        if count > MAX_DB_ROWS:
            return 'unresolved', 'job_database_row_count_exceeded'
        row = conn.execute(types.SELECT_JOB, (job_id,)).fetchone()
        if not row:
            return 'unresolved', 'job_not_found'
        job = types.JobStore._record(row)
        if job['id'] != job_id or job['worker'] != worker:
            return 'unresolved', 'job_worker_mismatch'
        draft_bytes, _ = read_regular(coord_dir / 'ui-plans' / (job['draft_id'] + '.json'),
                                      MAX_DRAFT_FILE_BYTES)
        if hashlib.sha256(draft_bytes).hexdigest() != job['draft_sha256']:
            return 'unresolved', 'draft_hash_mismatch'
        draft = parse_strict_json(draft_bytes)
        if (draft is None or set(draft) != {'schema_version', 'id', 'created_at', 'state', 'request'}
                or type(draft['schema_version']) is not int or draft['schema_version'] != 1
                or draft['id'] != job['draft_id'] or draft['state'] != 'draft'
                or not isinstance(draft['created_at'], str)
                or datetime.datetime.fromisoformat(draft['created_at']).tzinfo is None):
            return 'unresolved', 'malformed_draft_record'
        types.PlanStore._request(draft['request'])
        after = os.fstat(descriptor)
        if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns)
                != (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            return 'unresolved', 'queue_changed_during_observation'
        if any(os.path.lexists(str(db_path) + suffix)
               for suffix in ('-wal', '-shm', '-journal')):
            return 'unresolved', 'unsupported_queue_sidecar'
        if time.monotonic() >= deadline:
            return 'unresolved', 'queue_observation_timeout'
        if job['state'] == 'approved':
            return 'eligible', None
        return 'blocked', ('awaiting_owner_approval' if job['state'] == 'awaiting_owner_approval'
                           else 'job_' + job['state'])
    except FileNotFoundError:
        return 'unresolved', 'missing_queue_evidence'
    except (sqlite3.Error, OSError, ValueError, TypeError, UnicodeError, OverflowError, RecursionError):
        return 'unresolved', 'invalid_queue_evidence'
    finally:
        if conn is not None:
            conn.close()
        if descriptor is not None:
            os.close(descriptor)


def detect_cycles(unsatisfied_edges):
    cycle_nodes = set()
    visited = {}

    def dfs(node, path):
        visited[node] = 0
        path.append(node)
        for neighbor in unsatisfied_edges.get(node, []):
            if neighbor in visited:
                if visited[neighbor] == 0:
                    idx = path.index(neighbor)
                    cycle_nodes.update(path[idx:])
            else:
                dfs(neighbor, path)
        path.pop()
        visited[node] = 1

    for node in list(unsatisfied_edges.keys()):
        if node not in visited:
            dfs(node, [])

    if cycle_nodes:
        def reaches_cycle(n, seen):
            if n in cycle_nodes:
                return True
            seen.add(n)
            for neighbor in unsatisfied_edges.get(n, []):
                if neighbor not in seen and reaches_cycle(neighbor, seen):
                    return True
            return False

        for node in list(unsatisfied_edges.keys()):
            if node not in cycle_nodes and reaches_cycle(node, set()):
                cycle_nodes.add(node)

    return cycle_nodes


def validate_inventory(raw_bytes):
    if len(raw_bytes) > MAX_INVENTORY_BYTES:
        fail('inventory file exceeds 256 KiB limit')

    obj = parse_strict_json(raw_bytes)
    if obj is None:
        fail('inventory is not valid strict UTF-8 JSON')

    required_keys = {'schema_version', 'base_revision', 'tasks', 'accepted'}
    if set(obj.keys()) != required_keys:
        fail('inventory root must contain exactly schema_version, base_revision, tasks, and accepted')

    if not is_int(obj['schema_version']) or obj['schema_version'] != 1:
        fail('inventory schema_version must be integer 1')

    if not isinstance(obj['base_revision'], str) or not HEX40.fullmatch(obj['base_revision']):
        fail('inventory base_revision must be full 40-character hex commit')

    if not isinstance(obj['tasks'], list) or len(obj['tasks']) > MAX_TASKS:
        fail('inventory tasks must be a list of at most 128 items')

    if not isinstance(obj['accepted'], list) or len(obj['accepted']) > MAX_ACCEPTED:
        fail('inventory accepted must be a list of at most 128 items')

    accepted_map = {}
    for entry in obj['accepted']:
        if not isinstance(entry, dict) or set(entry.keys()) != {'id', 'task_sha256', 'revision'}:
            fail('accepted entry must contain exactly id, task_sha256, and revision')
        if not is_valid_task_id(entry['id']):
            fail('accepted entry id is invalid')
        if not isinstance(entry['task_sha256'], str) or not HEX64.fullmatch(entry['task_sha256']):
            fail('accepted entry task_sha256 must be 64-hex string')
        if not isinstance(entry['revision'], str) or not HEX40.fullmatch(entry['revision']):
            fail('accepted entry revision must be 40-hex string')
        if entry['id'] in accepted_map:
            fail('duplicate or ambiguous accepted task ID: ' + entry['id'])
        accepted_map[entry['id']] = entry

    seen_tasks = set()
    for task in obj['tasks']:
        if not isinstance(task, dict):
            fail('task item must be a dictionary')
        keys = set(task.keys())
        if keys not in ({'id', 'task_sha256', 'worker', 'depends_on'},
                        {'id', 'task_sha256', 'worker', 'depends_on', 'job_id'}):
            fail('task item has invalid or unknown fields')
        if not is_valid_task_id(task['id']):
            fail('task id is invalid')
        if task['id'] in seen_tasks:
            fail('duplicate task ID in inventory: ' + task['id'])
        seen_tasks.add(task['id'])

        if not isinstance(task['task_sha256'], str) or not HEX64.fullmatch(task['task_sha256']):
            fail('task task_sha256 must be 64-hex string: ' + task['id'])
        if not is_valid_worker_id(task['worker']):
            fail('task worker ID is invalid')
        if not isinstance(task['depends_on'], list) or len(task['depends_on']) > MAX_DEPENDENCIES:
            fail('task depends_on must be a list of at most 128 items: ' + task['id'])

        for dep in task['depends_on']:
            if not isinstance(dep, dict) or set(dep.keys()) != {'id', 'task_sha256', 'revision'}:
                fail('dependency item must contain exactly id, task_sha256, and revision')
            if not is_valid_task_id(dep['id']):
                fail('dependency id is invalid')
            if not isinstance(dep['task_sha256'], str) or not HEX64.fullmatch(dep['task_sha256']):
                fail('dependency task_sha256 must be 64-hex string')
            if not isinstance(dep['revision'], str) or not HEX40.fullmatch(dep['revision']):
                fail('dependency revision must be 40-hex string')

        if 'job_id' in task:
            if not isinstance(task['job_id'], str) or not HEX32.fullmatch(task['job_id']):
                fail('task job_id must be 32-hex string: ' + task['id'])

    return obj, accepted_map


def build_plan(root, inventory, raw_bytes, inv_age_seconds, timeout, runner=sys.executable):
    fleet_mod = load_fleet_status()
    coord_dir = root / 'coord'
    stop_file = coord_dir / 'STOP'
    stop = stop_file.exists()

    repo_dir = resolve_repo(root)
    head_revision = get_repo_head(repo_dir, timeout=min(5.0, timeout))

    observed, statuses = fleet_mod.collect(runner, str(root), remaining(timeout))
    fleet_report = fleet_mod.build_report(str(root), timeout, stop, observed, statuses)

    inv_hash = hashlib.sha256(raw_bytes).hexdigest()
    base_revision = inventory['base_revision']
    base_mismatch = (head_revision is None or head_revision != base_revision)

    verified_accepted = {}
    unverified_accepted = set()
    accepted_map = {entry['id']: entry for entry in inventory['accepted']}

    ancestry = {}
    if not base_mismatch and repo_dir is not None:
        for acc_id, entry in accepted_map.items():
            revision = entry['revision']
            if revision not in ancestry:
                ancestry[revision] = is_ancestor_commit(repo_dir, revision, base_revision)
            if ancestry[revision]:
                verified_accepted[acc_id] = entry
            else:
                unverified_accepted.add(acc_id)
    else:
        unverified_accepted.update(accepted_map.keys())

    tasks = sorted(inventory['tasks'], key=lambda t: t['id'])
    policy = observed.get('policy')
    agents_obs = observed.get('agents')
    readiness_obs = observed.get('readiness')

    # Step 1: Pre-process each task individually
    pre_results = {}
    for task in tasks:
        tid = task['id']
        worker = task['worker']
        agent = worker.split('-')[0]
        group = policy['accounts'].get(agent, agent) if policy else agent
        res = {
            'id': tid,
            'status': None,
            'worker': worker,
            'agent': agent,
            'group': group,
            'reasons': [],
            'explanation': None,
            'scopes': [],
            'dependencies': [],
            'job_id': task.get('job_id'),
            'dispatch_readiness': 'unknown',
            '_scope_valid': False,
        }

        if base_mismatch:
            res['status'] = 'unresolved'
            res['reasons'].append('base_revision_mismatch')
            res['explanation'] = (
                f"workspace repo HEAD ({head_revision[:12] if head_revision else 'unknown'}) "
                f"does not match inventory base_revision ({base_revision[:12]})"
            )
            pre_results[tid] = res
            continue

        # Check if already integrated at base
        if tid in accepted_map:
            acc = accepted_map[tid]
            if acc['task_sha256'] == task['task_sha256'] and tid in verified_accepted:
                res['status'] = 'blocked'
                res['reasons'].append('already_integrated')
                res['explanation'] = f"task hash already integrated at base revision {acc['revision'][:12]}"
                pre_results[tid] = res
                continue

        # Parse task file and scope
        scopes, _, parse_st, parse_reason = parse_task_file(coord_dir, tid, task['task_sha256'])
        if parse_st != 'ok':
            res['status'] = 'unresolved'
            res['reasons'].append(parse_reason)
            res['explanation'] = f"task markdown or scope invalid: {parse_reason}"
            pre_results[tid] = res
            continue

        res['scopes'] = scopes
        res['_scope_valid'] = True

        # Check optional browser job
        if task.get('job_id'):
            job_st, job_reason = observe_browser_job(coord_dir, task['job_id'], worker)
            if job_st == 'unresolved':
                res['status'] = 'unresolved'
                res['reasons'].append(job_reason)
                res['explanation'] = f"browser queue observation unresolved: {job_reason}"
                pre_results[tid] = res
                continue
            elif job_st == 'blocked':
                res['status'] = 'blocked'
                res['reasons'].append(job_reason)
                res['explanation'] = f"browser queue job blocked: {job_reason}"
                pre_results[tid] = res
                continue

        # Check dependencies
        dep_blocked_reasons = []
        dep_unresolved_reasons = []
        for dep in task['depends_on']:
            dep_id = dep['id']
            if dep_id not in accepted_map or dep_id in unverified_accepted:
                dep_unresolved_reasons.append(f"missing_acceptance_evidence:{dep_id}")
            else:
                acc = accepted_map[dep_id]
                if dep['task_sha256'] != acc['task_sha256']:
                    dep_blocked_reasons.append(
                        f"dependency_{dep_id}_hash_mismatch: required {dep['task_sha256'][:12]} != accepted {acc['task_sha256'][:12]}"
                    )
                elif dep['revision'] != acc['revision']:
                    dep_blocked_reasons.append(
                        f"dependency_{dep_id}_revision_mismatch: required {dep['revision'][:12]} != accepted {acc['revision'][:12]}"
                    )
                else:
                    res['dependencies'].append({
                        'id': dep_id,
                        'revision': acc['revision'],
                        'task_sha256': acc['task_sha256']
                    })

        if dep_blocked_reasons:
            res['status'] = 'blocked'
            res['reasons'].extend(dep_blocked_reasons)
            res['explanation'] = '; '.join(dep_blocked_reasons)
            pre_results[tid] = res
            continue
        elif dep_unresolved_reasons:
            res['status'] = 'unresolved'
            res['reasons'].extend(dep_unresolved_reasons)
            res['explanation'] = '; '.join(dep_unresolved_reasons)
            pre_results[tid] = res
            continue

        pre_results[tid] = res

    # Step 2: Cycle detection among unsatisfied inventory dependencies
    if not base_mismatch:
        unsatisfied_edges = {}
        inventory_tids = {t['id'] for t in tasks}
        for task in tasks:
            tid = task['id']
            for dep in task['depends_on']:
                dep_id = dep['id']
                if dep_id in inventory_tids and dep_id not in verified_accepted:
                    unsatisfied_edges.setdefault(tid, set()).add(dep_id)

        cycle_nodes = detect_cycles(unsatisfied_edges)
        for tid in cycle_nodes:
            res = pre_results[tid]
            res['status'] = 'unresolved'
            if 'dependency_cycle' not in res['reasons']:
                res['reasons'].append('dependency_cycle')
            res['explanation'] = 'dependency cycle detected among unsatisfied inventory tasks'

    # Step 3: Check for unknown/ambiguous scope on any unfinished task
    if not base_mismatch:
        bad_scope_tasks = []
        for task in tasks:
            tid = task['id']
            res = pre_results[tid]
            if res['status'] == 'blocked' and 'already_integrated' in res['reasons']:
                continue
            if not res['_scope_valid']:
                bad_scope_tasks.append(tid)

        if bad_scope_tasks:
            for task in tasks:
                tid = task['id']
                res = pre_results[tid]
                if res['status'] is None:
                    res['status'] = 'unresolved'
                    res['reasons'].append('disjointness_unknown')
                    res['explanation'] = (
                        f"disjointness cannot be established; unfinished task '{bad_scope_tasks[0]}' "
                        f"has unknown/ambiguous scope"
                    )

    # Step 4: Fleet admission checks for remaining candidate tasks
    if not base_mismatch:
        for task in tasks:
            tid = task['id']
            res = pre_results[tid]
            if res['status'] is not None:
                continue

            if stop:
                res['status'] = 'blocked'
                res['reasons'].append('project_STOP')
                res['explanation'] = 'project STOP is set'
                continue

            if statuses.get('policy') != 'ok':
                res['status'] = 'unresolved'
                res['reasons'].append('policy_unavailable')
                res['explanation'] = 'policy unavailable, account limits unknown'
                continue

            agent_info = None
            if agents_obs:
                agent_info = agents_obs.get(res['agent'])
            if agent_info is None:
                res['status'] = 'unresolved'
                res['reasons'].append('agent_unknown')
                res['explanation'] = f"agent '{res['agent']}' not listed in configured agents"
                continue

            if agent_info.get('bench_off'):
                res['status'] = 'blocked'
                res['reasons'].append('agent_off')
                res['explanation'] = f"agent '{res['agent']}' is off"
                continue

            if agent_info.get('binary_present') is False:
                res['status'] = 'blocked'
                res['reasons'].append('binary_missing')
                res['explanation'] = f"agent '{res['agent']}' binary not installed"
                continue
            elif agent_info.get('binary_present') is None:
                res['status'] = 'unresolved'
                res['reasons'].append('binary_unknown')
                res['explanation'] = f"agent '{res['agent']}' binary presence unknown"
                continue

            # Fresh auth check
            if readiness_obs:
                agent_auth = readiness_obs.get(res['agent'])
                if agent_auth and agent_auth.get('status') == 'fresh' and agent_auth.get('authentication') == 'signed_out':
                    res['status'] = 'blocked'
                    res['reasons'].append('auth_signed_out')
                    res['explanation'] = f"agent '{res['agent']}' authentication is fresh signed_out"
                    continue

            # Fresh zero allowance check
            grp_data = fleet_report['groups'].get(res['group'])
            zero_allowance = False
            if grp_data:
                manual = grp_data.get('manual_allowance')
                if manual and manual.get('status') == 'recorded':
                    for win in manual.get('windows', {}).values():
                        if win.get('status') == 'fresh' and win.get('usable_remaining_percent') == 0:
                            zero_allowance = True
                            break
                cached = grp_data.get('cached_allowance')
                if cached and cached.get('freshness') == 'fresh' and cached.get('state') == 'ok':
                    for bkt in cached.get('buckets', {}).values():
                        for win in bkt.get('windows', {}).values():
                            if win and win.get('status') == 'fresh' and win.get('usable_remaining_percent') == 0:
                                zero_allowance = True
                                break
            if zero_allowance:
                res['status'] = 'blocked'
                res['reasons'].append('zero_allowance')
                res['explanation'] = f"shared budget group '{res['group']}' has fresh zero allowance"
                continue

    # Step 5: Busy groups and inferred active scope
    warnings = []
    occupied_scopes = []  # list of tuples: (scope_pattern, holding_task_or_reason)
    virtual_occupied = {}

    if not base_mismatch:
        busy_groups = {}
        if policy and isinstance(policy.get('active_with_lead'), dict):
            for g_name, occ in policy['active_with_lead'].items():
                if is_int(occ) and occ > 0:
                    busy_groups[g_name] = occ
        for g_name, g_view in fleet_report['groups'].items():
            occ = g_view.get('occupied') or 0
            if occ > 0:
                busy_groups[g_name] = max(busy_groups.get(g_name, 0), occ)
            virtual_occupied[g_name] = occ

        for g_name, occ in busy_groups.items():
            virtual_occupied[g_name] = occ
            # Find unfinished tasks in inventory for this group
            group_tasks = [
                t for t in tasks
                if pre_results[t['id']]['group'] == g_name
                and not (pre_results[t['id']]['status'] == 'blocked'
                         and 'already_integrated' in pre_results[t['id']]['reasons'])
                and pre_results[t['id']]['_scope_valid']
            ]
            if group_tasks:
                for gt in group_tasks:
                    for sc in pre_results[gt['id']]['scopes']:
                        occupied_scopes.append((sc, f"inferred busy task '{gt['id']}' in group '{g_name}'"))
            else:
                warnings.append(
                    f"group '{g_name}' is busy ({occ} occupied) with no task in inventory; active write scope unknown"
                )

    # Step 6: Greedy selection in stable sorted task ID order
    if not base_mismatch:
        for task in tasks:
            tid = task['id']
            res = pre_results[tid]
            if res['status'] is not None:
                continue

            grp = res['group']
            limit = fleet_report['groups'].get(grp, {}).get('limit')
            cur_occ = virtual_occupied.get(grp, 0)

            if limit is not None and cur_occ >= limit:
                res['status'] = 'blocked'
                res['reasons'].append('group_full')
                res['explanation'] = f"shared budget group '{grp}' is full (limit {limit})"
                continue

            conflict, s1, s2, held_by = task_scopes_conflict(res['scopes'], occupied_scopes)
            if conflict:
                res['status'] = 'blocked'
                res['reasons'].append('scope_conflict')
                res['explanation'] = f"write scope '{s1}' conflicts with '{s2}' held by {held_by}"
                continue

            # Task is selected!
            res['status'] = 'ready'
            res['reasons'] = []
            res['explanation'] = (
                "recommended; all local checks clear; provider availability remains unknown "
                "and admission must be rechecked at launch"
            )
            virtual_occupied[grp] = cur_occ + 1
            for sc in res['scopes']:
                occupied_scopes.append((sc, f"task '{tid}'"))

    # Final pass: clean up internal keys
    final_tasks = []
    ready_count = 0
    blocked_count = 0
    unresolved_count = 0

    for task in tasks:
        tid = task['id']
        res = pre_results[tid]
        res.pop('_scope_valid', None)
        if stop:
            res['status'] = 'blocked'
            if 'project_STOP' not in res['reasons']:
                res['reasons'].append('project_STOP')
            res['explanation'] = 'project STOP is set; ' + (res['explanation'] or 'launch is blocked')
        if res['status'] == 'ready':
            ready_count += 1
        elif res['status'] == 'blocked':
            blocked_count += 1
        else:
            res['status'] = 'unresolved'
            unresolved_count += 1
        final_tasks.append(res)

    report = {
        'schema_version': SCHEMA_VERSION,
        'project': str(root.resolve()),
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'timeout_seconds': timeout,
        'base_revision': base_revision,
        'head_revision': head_revision,
        'inventory_hash': inv_hash,
        'inventory_file_age_seconds': round(inv_age_seconds, 2),
        'fleet_age_seconds': round(max(0.0, (datetime.datetime.now(datetime.timezone.utc)
            - datetime.datetime.fromisoformat(fleet_report['checked_at'])).total_seconds()), 3),
        'fleet_sources': statuses,
        'stop': stop,
        'summary': {
            'total': len(final_tasks),
            'ready': ready_count,
            'blocked': blocked_count,
            'unresolved': unresolved_count
        },
        'warnings': warnings,
        'tasks': final_tasks
    }
    return report


def render_text(report):
    lines = []
    lines.append('Project: ' + report['project'].encode('unicode_escape').decode('ascii'))
    lines.append(f"Base revision: {report['base_revision'][:12]} | Repo HEAD: {report['head_revision'][:12] if report['head_revision'] else 'unknown'}")
    lines.append(f"Inventory age: {report['inventory_file_age_seconds']}s | Hash: {report['inventory_hash'][:12]}")
    if report['stop']:
        lines.append('STOP: active (all tasks blocked)')
    lines.append(
        f"Summary: total {report['summary']['total']} | "
        f"ready {report['summary']['ready']} | "
        f"blocked {report['summary']['blocked']} | "
        f"unresolved {report['summary']['unresolved']}"
    )

    if report['warnings']:
        lines.append('')
        lines.append('Warnings:')
        for w in report['warnings']:
            lines.append('  ! ' + w)

    lines.append('')
    for t in report['tasks']:
        st = t['status'].upper()
        line = f"[{st}] {t['id']} (worker: {t['worker']}, group: {t['group']})"
        lines.append(line)
        if t['reasons']:
            lines.append('  reasons: ' + ', '.join(t['reasons']))
        if t['explanation']:
            lines.append('  detail: ' + t['explanation'])
        if t['scopes']:
            lines.append('  scopes: ' + ', '.join(t['scopes']))
        if t['dependencies']:
            deps_str = ', '.join(f"{d['id']}@{d['revision'][:8]}" for d in t['dependencies'])
            lines.append('  dependencies satisfied: ' + deps_str)
        if t['job_id']:
            lines.append('  job_id: ' + t['job_id'])
        lines.append('')

    lines.append('Recommendation only; not launch authority. Provider availability remains unknown.')
    return '\n'.join(lines)


def main(argv=None):
    global OBSERVATION_DEADLINE
    parser = argparse.ArgumentParser(
        prog='unio plan', allow_abbrev=False,
        description='Local read-only concurrent recommendations before dispatch: '
                    'inventory tasks, dependencies, write scopes, and shared budget groups.')
    parser.add_argument('--inventory', metavar='PATH',
                        help='path to schema-1 task inventory JSON file')
    parser.add_argument('--project', metavar='PATH',
                        help='explicit physical project root (coord/ and wt/)')
    parser.add_argument('--json', action='store_true',
                        help='write exactly one schema-1 JSON object')
    parser.add_argument('--timeout', type=int, metavar='SECONDS', default=10,
                        help='whole observation deadline, 1..60 seconds (default 10)')

    native = list(sys.argv[1:] if argv is None else argv)
    if not native:
        fail('arguments missing; pass --help for usage')
    # If the dispatcher passes runner as first argument
    if native[0].startswith('-'):
        fail('installed runner path missing')
    runner = native.pop(0)
    args = parser.parse_args(native)

    if not 1 <= args.timeout <= 60:
        fail('--timeout must be 1..60 seconds')
    if not args.inventory:
        fail('--inventory PATH is required')
    if not args.project:
        fail('no project selected; pass --project PATH')

    OBSERVATION_DEADLINE = time.monotonic() + args.timeout
    inv_path = Path(args.inventory)
    try:
        raw_bytes, st = read_regular(inv_path, MAX_INVENTORY_BYTES)
    except FileNotFoundError:
        fail('inventory file does not exist')
    except ValueError as error:
        if str(error) == 'input_file_exceeds_bound':
            fail('inventory file exceeds 256 KiB limit')
        fail('inventory file must be regular and bounded')
    except OSError:
        fail('inventory file must not be a symlink or have symlink components; it must be readable')

    inv_age = max(0.0, time.time() - st.st_mtime)
    inventory, _ = validate_inventory(raw_bytes)

    root = Path(os.path.realpath(os.path.abspath(args.project)))
    for req in ('coord', 'wt'):
        if (root / req).is_symlink() or not (root / req).is_dir():
            fail('project requires physical coord/ and wt/ directories')

    plan_report = build_plan(root, inventory, raw_bytes, inv_age, args.timeout, runner=runner)

    if args.json:
        sys.stdout.write(json.dumps(plan_report, indent=2, ensure_ascii=True, allow_nan=False) + '\n')
    else:
        sys.stdout.write(render_text(plan_report) + '\n')
    return 0


if __name__ == '__main__':
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write('unio plan: interrupted\n')
        raise SystemExit(130)
