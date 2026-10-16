#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Finite owner-granted scheduling over the existing planner and dispatcher."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import time

MAX_GRANT = 128 * 1024
MAX_STATE = 2 * 1024 * 1024
MAX_BATCHES = 128
FIELDS = {'schema_version', 'project', 'inventory', 'inventory_sha256', 'expires_at',
          'max_launches', 'poll_seconds', 'run_seconds', 'jobs'}
JOB_FIELDS = {'job_id', 'grant', 'grant_sha256', 'approval_key', 'reservation_key'}


class Refusal(ValueError):
    """Only fixed scheduler messages may cross the public error boundary."""


def require(condition, message):
    if not condition:
        raise Refusal(message)


def load(name):
    path = Path(__file__).resolve().with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def expiry(value):
    require(isinstance(value, str) and len(value) <= 64, 'invalid expiry')
    date = datetime.datetime.fromisoformat(value)
    require(date.tzinfo is not None, 'expiry needs explicit timezone')
    return date


def physical(value, directory=False):
    require(isinstance(value, str) and 0 < len(value) <= 4096
            and os.path.isabs(value) and os.path.normpath(value) == value
            and os.path.realpath(value) == value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value), 'physical path required')
    info = os.lstat(value)
    mode = info.st_mode
    require(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode) and info.st_nlink == 1, 'unsupported path')
    return Path(value)


def read_json(planner, path, limit):
    raw, _ = planner.read_regular(physical(str(path)), limit)
    value = planner.parse_strict_json(raw)
    require(value is not None, 'invalid strict JSON')
    return value, raw


def read_grant(planner, path, creation=True):
    grant, _ = read_json(planner, physical(str(path)), MAX_GRANT)
    require(set(grant) == FIELDS and type(grant['schema_version']) is int
            and grant['schema_version'] == 1, 'invalid grant fields')
    physical(grant['project'], True)
    for name in ('coord', 'repo', 'wt'):
        physical(str(Path(grant['project']) / name), True)
    physical(grant['inventory'])
    require(isinstance(grant['inventory_sha256'], str)
            and planner.HEX64.fullmatch(grant['inventory_sha256']), 'invalid inventory hash')
    for name, high in (('max_launches', 128), ('poll_seconds', 60), ('run_seconds', 7200)):
        require(type(grant[name]) is int and 1 <= grant[name] <= high, 'invalid ' + name)
    date = expiry(grant['expires_at'])
    if creation:
        require(now() < date <= now() + datetime.timedelta(hours=24), 'expiry outside creation window')
    require(isinstance(grant['jobs'], list) and 1 <= len(grant['jobs']) <= 128, 'invalid jobs')
    jobs, reservations = set(), set()
    for job in grant['jobs']:
        require(isinstance(job, dict) and set(job) == JOB_FIELDS, 'invalid job fields')
        for name in ('job_id', 'approval_key', 'reservation_key'):
            require(isinstance(job[name], str) and planner.HEX32.fullmatch(job[name]), 'invalid job key')
        require(isinstance(job['grant_sha256'], str) and planner.HEX64.fullmatch(job['grant_sha256']),
                'invalid dispatch grant hash')
        physical(job['grant'])
        require(job['job_id'] not in jobs and job['reservation_key'] not in reservations, 'duplicate job or reservation')
        jobs.add(job['job_id'])
        reservations.add(job['reservation_key'])
    return grant


def helpers(planner):
    """Pin loaded payloads as well as the native executable's service fingerprint."""
    here = Path(__file__).resolve().parent
    browser = here / 'browser'
    if not browser.is_dir():
        browser = here.parent / 'bridge'
    paths = [here / name for name in ('continuous-delegation.py', 'task-dispatch.py',
                                     'task-plan.py', 'fleet-status.py')]
    paths += [browser / name for name in ('execution_service.py', 'job_store.py', 'plan_store.py')]
    return {str(path): digest(planner.read_regular(physical(str(path)), 8 * 1024 * 1024)[0])
            for path in paths}


def service_for(dispatch, grant):
    module = dispatch.load_service()
    service = module.ExecutionService(grant['project'], grant['engine'], grant['worker'],
                                      grant['reviewer'], grant['config_dir'], grant['template_path'],
                                      grant['worker_lab'], grant['reviewer_lab'])
    return module, service


def checked_job(planner, dispatch, batch, job, runner, row, initial=False):
    raw, _ = planner.read_regular(physical(job['grant']), dispatch.MAX_GRANT_BYTES)
    require(digest(raw) == job['grant_sha256'], 'dispatch grant drift')
    grant = dispatch.read_grant(job['grant'], planner)
    require(grant['engine'] == runner and grant['project'] == batch['project'], 'dispatch route mismatch')
    configured = os.environ.get('UNIO_CONF_DIR')
    require(configured is None or configured == grant['config_dir'], 'configuration route mismatch')
    module, service = service_for(dispatch, grant)
    try:
        with service._locked(), module.JobStore(batch['project']) as store:
            record, binding, state = service._load_job(store, job['job_id'])
            service._check(record, binding, check_stop=False)
            require(record['approval_key'] == job['approval_key'], 'approval mismatch')
            if initial:
                require(record['state'] == 'approved' and record['reservation_key'] is None
                        and state['run_action'] is None, 'job is not unstarted and approved')
            preview = binding['preview']
            require(row['job_id'] == job['job_id'] and row['id'] == preview['task_id']
                    and row['worker'] == preview['worker'] and row['task_sha256'] == preview['task_sha256']
                    and binding['base_revision'] == batch['_base'], 'inventory job binding mismatch')
            return dict(worker=preview['worker'], task=preview['task_id'],
                        task_sha256=preview['task_sha256'], preview_sha256=preview['preview_hash'],
                        scopes=preview['scope'], fingerprints=binding['fingerprints'],
                        startup=binding['startup'])
    finally:
        service.close()


def validate_frozen(planner, frozen):
    grant = frozen['grant']
    require(isinstance(grant, dict) and set(grant) == FIELDS
            and type(grant['schema_version']) is int and grant['schema_version'] == 1,
            'corrupt stored grant')
    for name, high in (('max_launches', 128), ('poll_seconds', 60), ('run_seconds', 7200)):
        require(type(grant[name]) is int and 1 <= grant[name] <= high, 'corrupt stored bounds')
    for name in ('project', 'inventory'):
        require(isinstance(grant[name], str) and 0 < len(grant[name]) <= 4096
                and os.path.isabs(grant[name]) and os.path.normpath(grant[name]) == grant[name],
                'corrupt stored path')
    require(isinstance(grant['inventory_sha256'], str) and planner.HEX64.fullmatch(grant['inventory_sha256']),
            'corrupt inventory hash')
    created = expiry(frozen['created_at'])
    require(created < expiry(grant['expires_at']) <= created + datetime.timedelta(hours=24), 'corrupt expiry')
    require(isinstance(frozen['base'], str) and planner.HEX40.fullmatch(frozen['base']), 'corrupt base')
    require(isinstance(grant['jobs'], list) and 1 <= len(grant['jobs']) <= 128, 'corrupt stored jobs')
    reservations = set()
    ids = set()
    for job in grant['jobs']:
        require(isinstance(job, dict) and set(job) == JOB_FIELDS, 'corrupt stored job')
        for name in ('job_id', 'approval_key', 'reservation_key'):
            require(isinstance(job[name], str) and planner.HEX32.fullmatch(job[name]), 'corrupt stored key')
        require(job['job_id'] not in ids and job['reservation_key'] not in reservations, 'duplicate stored job')
        ids.add(job['job_id'])
        reservations.add(job['reservation_key'])
        require(isinstance(job['grant_sha256'], str) and planner.HEX64.fullmatch(job['grant_sha256'])
                and isinstance(job['grant'], str) and os.path.isabs(job['grant']) and len(job['grant']) <= 4096,
                'corrupt stored grant binding')
    require(isinstance(frozen['helpers'], dict) and 1 <= len(frozen['helpers']) <= 16, 'corrupt helper bindings')
    for path, sha in frozen['helpers'].items():
        require(isinstance(path, str) and os.path.isabs(path) and len(path) <= 4096
                and isinstance(sha, str) and planner.HEX64.fullmatch(sha), 'corrupt helper digest')
    require(isinstance(frozen['bindings'], dict) and set(frozen['bindings']) == ids, 'corrupt bindings')
    for job_id, binding in frozen['bindings'].items():
        require(isinstance(binding, dict) and set(binding) == {'worker', 'task', 'task_sha256',
                'preview_sha256', 'scopes', 'fingerprints', 'startup', 'group'}
                and planner.is_valid_worker_id(binding['worker']) and binding['task'] == 'ui-' + job_id
                and isinstance(binding['group'], str) and 0 < len(binding['group']) <= 100,
                'corrupt frozen identity')
        for name in ('task_sha256', 'preview_sha256'):
            require(isinstance(binding[name], str) and planner.HEX64.fullmatch(binding[name]), 'corrupt preview digest')
        require(isinstance(binding['scopes'], list) and 1 <= len(binding['scopes']) <= 128
                and all(planner.validate_scope_pattern(scope)[0] for scope in binding['scopes']), 'corrupt frozen scope')
        for name in ('startup', 'fingerprints'):
            require(isinstance(binding[name], dict) and set(binding[name]) == {'engine', 'config', 'template'},
                    'corrupt route binding')
            for value in binding[name].values():
                require(isinstance(value, str) and (bool(planner.HEX64.fullmatch(value)) if name == 'fingerprints'
                        else os.path.isabs(value) and 0 < len(value) <= 4096), 'corrupt route value')


class Store:
    """Short cross-batch transactions; separate flock leases belong to runners."""
    def __init__(self, project, planner, create=False):
        self.project, self.planner = physical(str(project), True), planner
        coord = physical(str(self.project / 'coord'), True)
        self.path = coord / 'schedules'
        if create:
            try:
                self.path.mkdir(mode=0o700)
            except FileExistsError:
                pass
        physical(str(self.path), True)

    @contextlib.contextmanager
    def lock(self, path=None, nonblocking=False):
        path = self.path / 'lock' if path is None else path
        physical(str(path.parent), True)
        descriptor = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        try:
            info = os.fstat(descriptor)
            require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'unsafe lock')
            deadline = time.monotonic() + (0 if nonblocking else 5)
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    require(time.monotonic() < deadline, 'runner active' if nonblocking else 'state busy')
                    time.sleep(0.01)
            physical(str(self.path), True)
            require(path.lstat().st_ino == info.st_ino, 'replaced lock')
            yield
        finally:
            os.close(descriptor)

    def directory(self, batch_id):
        require(isinstance(batch_id, str) and self.planner.HEX32.fullmatch(batch_id), 'invalid batch ID')
        return physical(str(self.path / batch_id), True)

    def ids(self):
        entries = list(self.path.iterdir())
        require(len(entries) <= MAX_BATCHES + 1, 'schedule directory bound exceeded')
        result = []
        for path in entries:
            if path.name == 'lock':
                continue
            require(self.planner.HEX32.fullmatch(path.name), 'unsupported schedule entry')
            physical(str(path), True)
            result.append(path.name)
        return sorted(result)

    def write(self, directory, name, value):
        physical(str(directory), True)
        target = directory / name
        if os.path.lexists(target):
            physical(str(target))
            require(target.lstat().st_nlink == 1, 'unsafe state file')
        raw = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(',', ':')).encode() + b'\n'
        require(len(raw) <= MAX_STATE, 'state bound exceeded')
        temporary = directory / ('.write-' + secrets.token_hex(16))
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
            directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        finally:
            if temporary.exists():
                temporary.unlink()

    def read(self, batch_id):
        directory = self.directory(batch_id)
        require(set(p.name for p in directory.iterdir()) <= {'frozen.json', 'state.json', 'runner.lock'},
                'unsupported batch entry; no repair performed')
        for entry in directory.iterdir():
            physical(str(entry))
        frozen, raw = read_json(self.planner, directory / 'frozen.json', MAX_STATE)
        state, _ = read_json(self.planner, directory / 'state.json', MAX_STATE)
        require(set(frozen) == {'schema_version', 'id', 'created_at', 'grant', 'base', 'bindings', 'helpers'}
                and type(frozen['schema_version']) is int and frozen['schema_version'] == 1
                and frozen['id'] == batch_id, 'corrupt frozen batch')
        require(set(state) == {'schema_version', 'id', 'frozen_sha256', 'control', 'attempts', 'jobs'}
                and type(state['schema_version']) is int and state['schema_version'] == 1
                and state['id'] == batch_id and state['frozen_sha256'] == digest(raw)
                and state['control'] in ('active', 'paused', 'stopped')
                and type(state['attempts']) is int, 'corrupt state')
        validate_frozen(self.planner, frozen)
        grant = frozen['grant']
        require(isinstance(grant, dict) and set(grant) == FIELDS and grant['project'] == str(self.project),
                'corrupt stored grant')
        require(isinstance(grant['jobs'], list) and 1 <= len(grant['jobs']) <= 128, 'corrupt stored jobs')
        ids = [job['job_id'] for job in grant['jobs']]
        require(len(ids) == len(set(ids)) and set(state['jobs']) == set(ids)
                and set(frozen['bindings']) == set(ids), 'corrupt job identities')
        require(0 <= state['attempts'] <= grant['max_launches'] <= 128, 'corrupt attempt budget')
        count = 0
        for job_id, item in state['jobs'].items():
            require(self.planner.HEX32.fullmatch(job_id) and isinstance(item, dict)
                    and set(item) == {'attempted', 'launcher', 'launcher_exit', 'source', 'source_exit', 'group', 'reason'}
                    and type(item['attempted']) is bool
                    and item['launcher'] in ('pending', 'unknown', 'refused', 'launch_failed', 'launch_accepted')
                    and item['source'] in ('unknown', 'running', 'succeeded', 'failed')
                    and (item['group'] is None or (isinstance(item['group'], str) and len(item['group']) <= 100))
                    and isinstance(item['reason'], str) and len(item['reason']) <= 160,
                    'corrupt job state')
            for key in ('source_exit', 'launcher_exit'):
                require(item[key] is None or (type(item[key]) is int and -2147483648 <= item[key] <= 2147483647),
                        'corrupt exit code')
            require(item['attempted'] or (item['launcher'] == 'pending' and item['source'] == 'unknown'),
                    'corrupt unattempted state')
            count += item['attempted']
            if item['attempted']:
                require(item['launcher'] != 'pending' and item['group'] == frozen['bindings'][job_id]['group'],
                        'corrupt consumed route')
        require(count == state['attempts'], 'attempt count mismatch')
        return frozen, state

    def save(self, batch_id, state):
        self.write(self.directory(batch_id), 'state.json', state)


def create(store, planner, dispatch, grant_path, runner):
    batch = read_grant(planner, grant_path)
    require(batch['project'] == str(store.project), 'project mismatch')
    physical(batch['inventory'])
    loaded, reason = dispatch.read_inventory(planner, batch['inventory'], batch['inventory_sha256'])
    require(reason is None, 'inventory mismatch')
    inventory, _, _ = loaded
    batch['_base'] = inventory['base_revision']
    bindings = {}
    for job in batch['jobs']:
        rows = [row for row in inventory['tasks'] if row.get('job_id') == job['job_id']]
        require(len(rows) == 1, 'job must occur exactly once in inventory')
        bindings[job['job_id']] = checked_job(planner, dispatch, batch, job, runner, rows[0], initial=True)
    planner.OBSERVATION_DEADLINE = time.monotonic() + 10
    report = planner.build_plan(store.project, inventory, loaded[1], loaded[2], 10, runner=runner)
    require(report['head_revision'] == batch['_base'], 'base mismatch')
    for job_id, binding in bindings.items():
        tasks = [task for task in report['tasks'] if task['job_id'] == job_id]
        require(len(tasks) == 1 and isinstance(tasks[0]['group'], str), 'account route unavailable')
        binding['group'] = tasks[0]['group']
    require(now() < expiry(batch['expires_at']), 'grant expired during creation')
    base = batch.pop('_base')
    batch_id = secrets.token_hex(16)
    frozen = dict(schema_version=1, id=batch_id, created_at=now().isoformat(), grant=batch,
                  base=base, bindings=bindings, helpers=helpers(planner))
    state = dict(schema_version=1, id=batch_id, frozen_sha256='', control='active', attempts=0,
                 jobs={job['job_id']: dict(attempted=False, launcher='pending', launcher_exit=None,
                      source='unknown', source_exit=None, group=None, reason='not_checked') for job in batch['jobs']})
    with store.lock():
        require(len(store.ids()) < MAX_BATCHES, 'batch limit reached')
        directory = store.path / batch_id
        directory.mkdir(mode=0o700)
        store.write(directory, 'frozen.json', frozen)
        raw, _ = planner.read_regular(directory / 'frozen.json', MAX_STATE)
        state['frozen_sha256'] = digest(raw)
        store.save(batch_id, state)
    return batch_id


def spawn(argv, project, config):
    import subprocess
    environment = dict(os.environ, UNIO_CONF_DIR=config, UNIO_AUTO_OFF='0',
                       UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0')
    return subprocess.Popen(argv, cwd=str(project / 'repo'), env=environment,
                            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True, close_fds=True)


def collect(process, timeout):
    """Bound all output, elapsed time and inherited pipes; never interpret stderr."""
    import selectors
    import signal
    import subprocess
    deadline, output, size = time.monotonic() + timeout, bytearray(), 0
    try:
        with selectors.DefaultSelector() as selector:
            for pipe in (process.stdout, process.stderr):
                os.set_blocking(pipe.fileno(), False)
                selector.register(pipe, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None, None
                for key, _ in selector.select(min(remaining, 0.1)):
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    size += len(chunk)
                    if size > 1024 * 1024:
                        return None, None
                    if key.fileobj is process.stdout:
                        output.extend(chunk)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None, None
            return process.wait(timeout=remaining), bytes(output)
    except (OSError, subprocess.TimeoutExpired):
        return None, None
    finally:
        # Terminate the bounded observer/dispatcher process group, never a native
        # detached worker (the native runner establishes its own session).
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            pass
        process.stdout.close()
        process.stderr.close()


def observe_source(planner, dispatch, store, frozen, state, job_id, runner, timeout):
    item = state['jobs'][job_id]
    if (not item['attempted'] or item['source'] in ('succeeded', 'failed')
            or item['launcher'] in ('refused', 'launch_failed')):
        return None
    binding = frozen['bindings'][job_id]
    config = binding['startup']['config']
    if (binding['startup']['engine'] != runner
            or digest(planner.read_regular(physical(runner), 8 * 1024 * 1024)[0]) != binding['fingerprints']['engine']):
        return None
    process = spawn([runner, 'result', binding['worker'], binding['task']], store.project, config)
    code, raw = collect(process, timeout)
    if code != 0 or raw is None:
        return None
    document = planner.parse_strict_json(raw)
    if document is None:
        return None
    module = dispatch.load_service()
    try:
        native = module._native_document(document, binding['worker'], binding['task'])
        source = native['process']
        revision = source['revision']
        if (native['stale'] or revision is None or revision != native['current_revision']
                or revision['task_sha256'] != binding['task_sha256']
                or revision['base_commit'] != frozen['base']):
            return None
        return source['state'], source['exit_code']
    except (ValueError, TypeError, KeyError):
        return None


def released(planner, store, inventory, frozen, job_id):
    """Only explicit matching integration in the new frozen inventory releases scope."""
    binding = frozen['bindings'][job_id]
    entries = [entry for entry in inventory['accepted'] if entry['id'] == binding['task']
               and entry['task_sha256'] == binding['task_sha256']]
    return len(entries) == 1 and planner.is_ancestor_commit(
        store.project / 'repo', entries[0]['revision'], inventory['base_revision'])


def held_reason(planner, store, released_jobs, batch_id, job_id, group, scopes):
    for other_id in store.ids():
        frozen, state = store.read(other_id)
        for other_job, item in state['jobs'].items():
            if not item['attempted']:
                continue
            if other_id == batch_id and other_job == job_id:
                continue
            if (other_id, other_job) in released_jobs:
                continue
            if item['group'] is None:
                return 'scheduled_group_unknown'
            if item['group'] == group and item['source'] not in ('succeeded', 'failed'):
                return 'scheduled_group_occupied'
            held = frozen['bindings'][other_job]['scopes']
            if any(planner.scopes_conflict(a, b) for a in scopes for b in held):
                return 'scheduled_scope_held'
    return None


def pending_reason(store, batch_id, job_id, reason):
    with store.lock():
        _, state = store.read(batch_id)
        if not state['jobs'][job_id]['attempted']:
            state['jobs'][job_id]['reason'] = reason
            store.save(batch_id, state)


def allowed(frozen, state, store):
    return (state['control'] == 'active' and now() < expiry(frozen['grant']['expires_at'])
            and state['attempts'] < frozen['grant']['max_launches']
            and not os.path.lexists(store.project / 'coord' / 'STOP'))


def scheduling_pass(store, planner, dispatch, batch_id, runner, deadline):
    with store.lock():
        frozen, state = store.read(batch_id)
    grant = frozen['grant']
    require(helpers(planner) == frozen['helpers'], 'installed helper identity drift')
    # Observe all known attempted jobs, including another batch's asynchronous
    # launch, before considering new claims. A missing receipt keeps occupancy.
    with store.lock():
        known = [(ident, *store.read(ident)) for ident in store.ids()]
    for ident, other, current in known:
        for job_id in current['jobs']:
            if time.monotonic() >= deadline:
                return
            evidence = observe_source(planner, dispatch, store, other, current, job_id,
                                      runner, min(15, max(0.01, deadline - time.monotonic())))
            if evidence is not None and evidence[0] in ('running', 'succeeded', 'failed'):
                with store.lock():
                    _, latest = store.read(ident)
                    item = latest['jobs'][job_id]
                    if item['source'] not in ('succeeded', 'failed'):
                        item['source'], item['source_exit'] = evidence
                        store.save(ident, latest)
    for job in grant['jobs']:
        job_id = job['job_id']
        with store.lock():
            _, state = store.read(batch_id)
        if not allowed(frozen, state, store) or time.monotonic() >= deadline:
            return
        if state['jobs'][job_id]['attempted']:
            continue
        loaded, reason = dispatch.read_inventory(planner, grant['inventory'], grant['inventory_sha256'])
        require(reason is None, 'frozen inventory drift')
        inventory, raw, age = loaded
        require(inventory['base_revision'] == frozen['base'], 'base drift')
        batch = dict(grant, _base=frozen['base'])
        rows = [row for row in inventory['tasks'] if row.get('job_id') == job_id]
        require(len(rows) == 1, 'frozen job missing')
        binding = checked_job(planner, dispatch, batch, job, runner, rows[0])
        require(binding == {key: value for key, value in frozen['bindings'][job_id].items() if key != 'group'},
                'prepared binding drift')
        timeout = min(10, max(0.01, deadline - time.monotonic()))
        config = binding['startup']['config']
        helper = Path(__file__).resolve().with_name('task-plan.py')
        process = spawn([sys.executable, '-I', '-S', '-B', str(helper), runner, '--project',
                         str(store.project), '--inventory', grant['inventory'], '--timeout', '10', '--json'],
                        store.project, config)
        code, output = collect(process, timeout)
        report = planner.parse_strict_json(output) if output is not None else None
        if code != 0 or not isinstance(report, dict):
            pending_reason(store, batch_id, job_id, 'plan_unavailable')
            continue
        require(report.get('inventory_hash') == grant['inventory_sha256']
                and report.get('base_revision') == frozen['base'], 'plan identity mismatch')
        tasks = [task for task in report['tasks'] if task.get('job_id') == job_id]
        require(len(tasks) == 1, 'plan job identity mismatch')
        task = tasks[0]
        if task['status'] != 'ready' or report['head_revision'] != frozen['base'] or report['stop']:
            codes = {'group_full', 'project_STOP', 'scope_conflict', 'already_integrated',
                     'awaiting_owner_approval', 'job_reserved', 'job_completion_unknown',
                     'policy_unavailable', 'agent_unknown', 'agent_off', 'binary_missing',
                     'binary_unknown', 'auth_signed_out', 'zero_allowance', 'dependency_cycle',
                     'disjointness_unknown', 'base_revision_mismatch'}
            reason = next((value for value in task['reasons'] if value in codes), None)
            pending_reason(store, batch_id, job_id, reason or 'plan_' + task['status'])
            continue
        require(task['worker'] == binding['worker'] and task['id'] == binding['task']
                and task['scopes'] == binding['scopes']
                and task['group'] == frozen['bindings'][job_id]['group'], 'plan route mismatch')
        if time.monotonic() >= deadline:
            return
        argv = [sys.executable, '-I', '-S', '-B', str(Path(__file__).resolve().with_name('task-dispatch.py')),
                runner, '--grant', job['grant'], '--project', str(store.project), '--json', 'start',
                '--job-id', job_id, '--approval-key', job['approval_key'],
                '--reservation-key', job['reservation_key'], '--inventory', grant['inventory'],
                '--inventory-sha256', grant['inventory_sha256'], '--timeout', '10']
        # Evaluate frozen explicit acceptance outside the short state lock. New
        # claims are still read and serialized inside it below.
        planner.OBSERVATION_DEADLINE = min(deadline, time.monotonic() + 5)
        with store.lock():
            snapshots = [(ident, *store.read(ident)) for ident in store.ids()]
        released_jobs = {(ident, old_job) for ident, old, old_state in snapshots
                         for old_job, old_item in old_state['jobs'].items() if old_item['attempted']
                         and released(planner, store, inventory, old, old_job)}
        process = None
        with store.lock():
            _, latest = store.read(batch_id)
            if (not allowed(frozen, latest, store) or latest['jobs'][job_id]['attempted']
                    or time.monotonic() >= deadline):
                continue
            reason = held_reason(planner, store, released_jobs, batch_id, job_id, task['group'], binding['scopes'])
            item = latest['jobs'][job_id]
            if reason:
                item['reason'] = reason
                store.save(batch_id, latest)
                continue
            # Durable reservation and attempt precede even Popen. A crash here
            # is permanently Unknown; neither restart nor resume refunds it.
            item.update(attempted=True, launcher='unknown', group=task['group'], reason='attempt_recorded')
            latest['attempts'] += 1
            store.save(batch_id, latest)
            try:
                process = spawn(argv, store.project, config)
            except OSError:
                pass
        if process is None:
            code, output = None, None
        else:
            code, output = collect(process, min(60, max(0.01, deadline - time.monotonic())))
        result = planner.parse_strict_json(output) if output is not None else None
        outcome = 'unknown'
        launcher_exit = None
        if (isinstance(result, dict) and result.get('schema_version') == 1 and result.get('operation') == 'start'
                and result.get('outcome') in ('refused', 'launch_failed', 'launch_accepted', 'unknown')):
            # A successful report must identify this exact task/preview. Refusal
            # may have no job at all. Never scrape raw output into state/status.
            if result['outcome'] == 'refused' and code == 1:
                outcome = 'refused'
            elif (isinstance(result.get('job'), dict) and result['job'].get('id') == job_id
                  and result.get('task') == {'id': binding['task'], 'sha256': binding['task_sha256']}
                  and result.get('preview_sha256') == binding['preview_sha256']):
                if result['outcome'] == 'launch_accepted' and code == 0:
                    outcome = 'launch_accepted'
                elif result['outcome'] == 'launch_failed' and code == 1:
                    outcome = 'launch_failed'
                execution = result.get('execution')
                if (isinstance(execution, dict) and type(execution.get('launcher_exit')) is int
                        and -2147483648 <= execution['launcher_exit'] <= 2147483647):
                    launcher_exit = execution['launcher_exit']
        with store.lock():
            _, latest = store.read(batch_id)
            latest['jobs'][job_id].update(launcher=outcome, launcher_exit=launcher_exit,
                                           reason='attempt_consumed')
            store.save(batch_id, latest)


def run(store, planner, dispatch, batch_id, runner, once):
    with store.lock(store.directory(batch_id) / 'runner.lock', nonblocking=True):
        with store.lock():
            frozen, _ = store.read(batch_id)
        deadline = time.monotonic() + frozen['grant']['run_seconds']
        # --once is one bounded pass, also constrained by the grant run duration.
        while time.monotonic() < deadline:
            with store.lock():
                frozen, state = store.read(batch_id)
            if state['control'] != 'active' or now() >= expiry(frozen['grant']['expires_at']):
                break
            scheduling_pass(store, planner, dispatch, batch_id, runner, deadline)
            if once:
                break
            with store.lock():
                _, state = store.read(batch_id)
            if not allowed(frozen, state, store) or all(j['attempted'] for j in state['jobs'].values()):
                break
            # Short sleep slices make STOP and controls responsive without a daemon.
            wake = min(deadline, time.monotonic() + frozen['grant']['poll_seconds'])
            while time.monotonic() < wake:
                time.sleep(min(0.2, max(0, wake - time.monotonic())))
                with store.lock():
                    _, state = store.read(batch_id)
                if not allowed(frozen, state, store):
                    return


def public(frozen, state):
    return dict(schema_version=1, id=state['id'], control=state['control'], attempts=state['attempts'],
                max_launches=frozen['grant']['max_launches'], expires_at=frozen['grant']['expires_at'],
                expired=now() >= expiry(frozen['grant']['expires_at']), allowance='Unknown',
                jobs=[dict(job_id=job_id, **item) for job_id, item in state['jobs'].items()])


def main(argv=None):
    native = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(prog='unio schedule', allow_abbrev=False,
        description='Finite approved-job scheduling. No approval, retry, acceptance or merge. '
                    'Pause/stop prevent new attempts and leave launched native workers running.')
    parser.add_argument('--project')
    parser.add_argument('--json', action='store_true')
    commands = parser.add_subparsers(dest='command', required=True)
    for command in ('create', 'run', 'status', 'pause', 'resume', 'stop'):
        child = commands.add_parser(command, allow_abbrev=False)
        # Support options before or after the subcommand without overwriting globals.
        child.add_argument('--project', default=argparse.SUPPRESS)
        child.add_argument('--json', action='store_true', default=argparse.SUPPRESS)
        if command == 'create':
            child.add_argument('--grant', required=True)
        else:
            child.add_argument('id', nargs='?' if command == 'status' else None)
        if command == 'run':
            child.add_argument('--once', action='store_true')
    if native[:1] in (['-h'], ['--help']):
        parser.print_help()
        return 0
    require(bool(native) and not native[0].startswith('-'), 'native runner missing')
    runner = str(physical(native.pop(0)))
    args = parser.parse_args(native)
    planner = load('task-plan')
    dispatch = None
    if args.command in ('create', 'run'):
        dispatch = load('task-dispatch')
    if args.command == 'create':
        grant = read_grant(planner, args.grant)
        root = grant['project']
        require(args.project is None or args.project == root, 'project mismatch')
    else:
        require(args.project is not None, '--project required')
        root = args.project
    store = Store(root, planner, create=args.command == 'create')
    if args.command == 'create':
        batch_id = create(store, planner, dispatch, args.grant, runner)
    else:
        batch_id = args.id
    if args.command == 'run':
        run(store, planner, dispatch, batch_id, runner, args.once)
    with store.lock():
        ids = store.ids() if batch_id is None else [batch_id]
        reports = []
        for ident in ids:
            frozen, state = store.read(ident)
            if args.command in ('pause', 'resume', 'stop'):
                require(state['control'] != 'stopped' or args.command == 'stop', 'stopped batch is terminal')
                state['control'] = {'pause': 'paused', 'resume': 'active', 'stop': 'stopped'}[args.command]
                store.save(ident, state)
            reports.append(public(frozen, state))
    if args.json:
        print(json.dumps(reports[0] if batch_id else dict(schema_version=1, batches=reports), ensure_ascii=True))
    else:
        for report in reports:
            print('Schedule {}: {} | attempts {}/{} | expired {}'.format(
                report['id'], report['control'], report['attempts'], report['max_launches'], report['expired']))
            for job in report['jobs']:
                print('  {}: launcher {}; Source {} (exit {}); {}'.format(
                    job['job_id'], job['launcher'], job['source'], job['source_exit'], job['reason']))
        print('Launcher acceptance is not Source success, review or integration. Allowance Unknown.')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write('unio schedule: interrupted; recorded attempts remain consumed\n')
        sys.exit(130)
    except Refusal as error:
        sys.stderr.write('unio schedule: ' + str(error) + '; no repair performed\n')
        sys.exit(1)
    except Exception:  # public refusal never includes private input or exception text
        sys.stderr.write('unio schedule: refused unsafe, stale, unavailable or corrupt inputs; no repair performed\n')
        sys.exit(1)
