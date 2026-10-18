#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Private, bounded native adapter observations. Never an admission verdict."""
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import stat
import subprocess
import sys

LIMIT = 8192
ENV = 'UNIO_ADAPTER_OUTCOME'
ROUTES = ('vibe', 'antigravity', 'copilot', 'perplexity')
LABELS = {
    'unknown': 'Unknown', 'completed': 'Completed',
    'token_cap': 'Configured token cap', 'price_cap': 'Configured price cap',
    'time_cap': 'Configured time cap', 'turn_cap': 'Configured turn cap',
    'output_cap': 'Configured output cap', 'provider_limit': 'Provider limit observed',
    'auth': 'Authentication failure', 'transport': 'Transport failure',
    'infrastructure': 'Infrastructure failure',
    'setup': 'Setup failure', 'terminal_error': 'Provider terminal error',
    'interrupted': 'Interrupted',
}
BIND_KEYS = {'schema_version', 'task', 'worker', 'run', 'task_sha256',
             'prompt_sha256', 'command_sha256', 'route', 'started_at'}
OUT_KEYS = BIND_KEYS | {'label', 'adapter_exit', 'native_exit', 'finished_at'}
# Additive per-run budget telemetry; absent in older evidence, strictly typed
# when present, and never an acceptance, readiness or quota verdict.
BUDGET_KEY = 'budget'
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}')
HEX = re.compile(r'[a-f0-9]{64}')
RUN = re.compile(r'[a-f0-9]{32}')
STAMP = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)')


def date():
    return subprocess.check_output(['date', '-Is'], text=True, timeout=5).strip()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def directory(path, private=False):
    """Walk from / with no symlink traversal; caller owns the returned fd."""
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        s = os.fstat(fd)
        if private and (s.st_uid != os.getuid() or s.st_mode & 0o077):
            raise ValueError('unsafe directory')
        return fd
    except BaseException:
        os.close(fd)
        raise


def read(path, limit=LIMIT, private=True):
    fd = directory(Path(path).parent, private)
    try:
        f = os.open(Path(path).name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(f, 'rb') as stream:
            s = os.fstat(stream.fileno())
            if (not stat.S_ISREG(s.st_mode) or s.st_nlink != 1 or not 0 < s.st_size <= limit
                    or private and (s.st_uid != os.getuid() or s.st_mode & 0o077)):
                raise ValueError('unsafe file')
            data = stream.read(limit + 1)
            if len(data) > limit:
                raise ValueError('oversized file')
            after = os.fstat(stream.fileno())
            if (s.st_size, s.st_mtime_ns, s.st_ctime_ns) != (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError('file changed while reading')
            return data
    finally:
        os.close(fd)


def pairs(items):
    d = {}
    for k, v in items:
        if k in d:
            raise ValueError('duplicate key')
        d[k] = v
    return d


def load(path, private=True):
    return json.loads(read(path, private=private), object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))


def write(path, value):
    data = (json.dumps(value, sort_keys=True) + '\n').encode()
    if len(data) > LIMIT:
        raise ValueError('oversized record')
    fd = directory(Path(path).parent, True)
    try:
        f = os.open(Path(path).name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(f, 'wb') as stream:
            stream.write(data)
    finally:
        os.close(fd)


def timestamp(value):
    if type(value) is not str or not STAMP.fullmatch(value):
        raise ValueError('timestamp')
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def valid_binding(b):
    return (type(b) is dict and set(b) == BIND_KEYS
            and type(b['schema_version']) is int and b['schema_version'] == 1
            and all(type(b[k]) is str and ID.fullmatch(b[k]) for k in ('task', 'worker'))
            and type(b['run']) is str and RUN.fullmatch(b['run'])
            and all(type(b[k]) is str and HEX.fullmatch(b[k]) for k in ('task_sha256', 'prompt_sha256', 'command_sha256'))
            and type(b['route']) is str and b['route'] in ROUTES + ('unsupported',)
            and bool(timestamp(b['started_at'])))


def route(command, adapters):
    # Exact simple argv only. Shell wrappers, expansions, pipelines and env
    # prefixes are deliberately unsupported, even if they call an adapter.
    if any(c in command for c in '\n\r$`;&|<>()*?{}'):
        return 'unsupported'
    a = shlex.split(command)
    if not a or Path(a.pop(0)).name not in ('python', 'python3'):
        return 'unsupported'
    while a and a[0] in ('-B', '-I', '-S'):
        a.pop(0)
    if not a:
        return 'unsupported'
    for r in ROUTES:
        target = Path(adapters).absolute() / (r + '-worker.py')
        if a[0] == str(target):
            read(target, 1024 * 1024, False)
            return r
    return 'unsupported'


def current(root, worker, task, command, adapters):
    if not ID.fullmatch(worker) or not ID.fullmatch(task):
        raise ValueError('identity')
    # The native retry attempt is authoritative; never select a receipt by
    # stdout, a provider-supplied path or directory enumeration.
    state = load(Path(root) / 'coord/retries' / task / 'state.json', False)
    if (type(state) is not dict or type(state.get('schema_version')) is not int
            or state['schema_version'] != 1 or state.get('task') != task):
        raise ValueError('native state')
    attempt = state['latest'][worker]
    if type(attempt) is not dict or any(type(attempt.get(k)) is not bool for k in ('pending', 'failed')):
        raise ValueError('native attempt')
    run = attempt['id']
    if type(run) is not str or not RUN.fullmatch(run):
        raise ValueError('run')
    return dict(task=task, worker=worker, run=run,
                task_sha256=sha(read(Path(root) / 'coord/tasks' / (task + '.md'), 1048576, False)),
                command_sha256=sha(command.encode()), route=route(command, adapters))


def destination(root, b):
    return Path(root).absolute() / 'coord/reports/.outcomes' / b['run']


def prepare(root, worker, task, command, adapters, prompt):
    b = current(root, worker, task, command, adapters)
    b.update(schema_version=1, prompt_sha256=sha(read(prompt, 1048576, False)), started_at=date())
    if not valid_binding(b):
        raise ValueError('binding')
    store = Path(root).absolute() / 'coord/reports/.outcomes'
    fd = directory(store.parent)
    try:
        try:
            os.mkdir(store.name, 0o700, dir_fd=fd)
        except FileExistsError:
            pass
    finally:
        os.close(fd)
    fd = directory(store, True)
    try:
        os.mkdir(b['run'], 0o700, dir_fd=fd)  # Fresh, never reuse a destination.
    finally:
        os.close(fd)
    dest = destination(root, b)
    write(dest / 'binding.json', b)
    return str(dest)


def classify(r, record):
    # Adapter-owned supervisors supply typed local-bound outcomes only after
    # a private run record exists. Preflight failures without one stay Unknown.
    if r in ('vibe', 'antigravity', 'copilot'):
        local = {'timeout': 'time_cap', 'output_limit': 'output_cap', 'interrupted': 'interrupted'}
        if record.get('outcome') in local:
            return local[record['outcome']]
    if r == 'vibe' and record.get('export_state') == 'valid':
        return {'finished': 'completed', 'token_limit': 'token_cap', 'price_limit': 'price_cap',
                'turn_limit': 'turn_cap', 'deadline': 'time_cap',
                'infrastructure_failure': 'infrastructure', 'config_error': 'setup',
                'usage_error': 'setup'}.get(record['export']['outcome'], 'unknown')
    if r == 'antigravity':
        return {'terminal_success': 'completed', 'terminal_error': 'terminal_error',
                'success_with_error': 'terminal_error'}.get(record.get('outcome'), 'unknown')
    if r == 'copilot':
        return 'completed' if record.get('outcome') == 'proposal_recorded' else 'unknown'
    if r == 'perplexity':
        return {'ok': 'completed', 'rate_limited': 'provider_limit', 'auth_missing': 'auth',
                'auth_denied': 'auth', 'dependency_missing': 'setup', 'dependency_version': 'setup',
                'dependency_broken': 'setup', 'unsupported_model': 'setup',
                'upstream_error': 'transport', 'timeout': 'time_cap',
                'output_overflow': 'output_cap'}.get(record.get('outcome'), 'unknown')
    return 'unknown'


def budget_module():
    """Load the shared telemetry module installed beside this utility."""
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'unio_adapter_budget', str(Path(__file__).with_name('adapter-budget.py')))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def budget_of(record):
    """Strictly validated additive telemetry from the adapter's own record."""
    module = budget_module()
    if module is None:
        return None
    return module.validate(record.get('budget_telemetry'))


def emit(r, record, prompt, adapter_exit, native_exit):
    """Best-effort observation; never changes the adapter's actual exit."""
    dest = os.environ.get(ENV)
    if not dest:
        return
    try:
        b = load(Path(dest) / 'binding.json')
        if (not valid_binding(b) or b['route'] != r or Path(dest).name != b['run']
                or Path(dest).parent.name != '.outcomes'
                or record.get('task_sha256') != b['prompt_sha256']
                or sha(read(prompt, 1048576, False)) != b['prompt_sha256']):
            return
        budget = budget_of(record)
        label = classify(r, record)
        if 'budget_telemetry' in record and budget is None:
            label = 'unknown'
        outcome = dict(b, label=label,
                       adapter_exit=adapter_exit, native_exit=native_exit, finished_at=date())
        if budget is not None:
            outcome[BUDGET_KEY] = budget
        write(Path(dest) / 'outcome.json', outcome)
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        pass


def observe_full(root, worker, task, command, adapters, source_exit=None):
    """Validated (label, budget) pair; budget is None when absent or unsafe."""
    try:
        expected = current(root, worker, task, command, adapters)
        dest = destination(root, expected)
        b = load(dest / 'binding.json')
        if not valid_binding(b) or any(b[k] != v for k, v in expected.items()) or b['route'] == 'unsupported':
            return 'unknown', None
        if source_exit is None:
            end = load(dest / 'source.json')
            if (type(end) is not dict or set(end) != {'binding', 'source_exit', 'observed_at'}
                    or not valid_binding(end['binding']) or end['binding'] != b
                    or timestamp(end['observed_at']) < timestamp(b['started_at'])):
                return 'unknown', None
            source_exit = end['source_exit']
        o = load(dest / 'outcome.json')
        if (type(source_exit) is not int or not 0 <= source_exit <= 255
                or type(o) is not dict or not OUT_KEYS <= set(o) <= OUT_KEYS | {BUDGET_KEY}
                or not valid_binding({k: o[k] for k in BIND_KEYS}) or any(o[k] != v for k, v in b.items())
                or type(o['label']) is not str or o['label'] not in LABELS
                or type(o['adapter_exit']) is not int or o['adapter_exit'] != source_exit
                or o['native_exit'] is not None and (type(o['native_exit']) is not int or not -127 <= o['native_exit'] <= 255)
                or timestamp(o['finished_at']) < timestamp(b['started_at'])):
            return 'unknown', None
        budget = o.get(BUDGET_KEY)
        if BUDGET_KEY in o:
            module = budget_module()
            if module is None or module.validate(budget) is None:
                return 'unknown', None
        return o['label'], budget
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        return 'unknown', None


def observe(root, worker, task, command, adapters, source_exit=None):
    return observe_full(root, worker, task, command, adapters, source_exit)[0]


def status_all(root, adapters, config):
    # One process and at most 1024 native pairs; enumerate native task IDs,
    # never adapter receipt directories or paths printed by a provider.
    commands = {}
    try:
        for line in read(config, 1048576, False).decode('utf-8').splitlines():
            name, sep, command = line.partition('=')
            if sep and ID.fullmatch(name) and name not in commands:
                commands[name] = command
    except (OSError, ValueError, UnicodeError):
        pass
    fd = directory(Path(root) / 'coord/tasks')
    try:
        with os.scandir(fd) as entries:
            names = []
            for count, entry in enumerate(entries):
                if count >= 1024:
                    print('  Adapter outcome: Unknown (status bound reached)')
                    break
                if entry.name.endswith('.md') and ID.fullmatch(entry.name[:-3]) and entry.name != 'TEMPLATE.md':
                    names.append(entry.name[:-3])
    finally:
        os.close(fd)
    shown = 0
    for task in sorted(names):
        try:
            state = load(Path(root) / 'coord/retries' / task / 'state.json', False)
            latest = state['latest']
            if type(latest) is not dict or len(latest) > 128 or any(not ID.fullmatch(k) for k in latest):
                raise ValueError('native attempts')
        except FileNotFoundError:
            continue
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            print('  ' + task + ': Adapter outcome: Unknown')
            continue
        for worker in sorted(latest):
            if shown >= 1024:
                print('  Adapter outcome: Unknown (status bound reached)')
                return
            shown += 1
            label = observe(root, worker, task, commands.get(worker.split('-')[0], ''), adapters)
            print('  ' + task + ' / ' + worker + ': Adapter outcome: ' + LABELS[label])
    if not shown:
        print('  (no current native adapter observations)')


def main(a):
    if a[:1] == ['status-all'] and len(a) == 4:
        status_all(*a[1:])
        return
    mode, root, worker, task, command, adapters, *extra = a
    if mode == 'prepare':
        print(prepare(root, worker, task, command, adapters, *extra))
    elif mode in ('finish', 'status'):
        if mode == 'finish':
            b = current(root, worker, task, command, adapters)
            dest = destination(root, b)
            binding = load(dest / 'binding.json')
            write(dest / 'source.json', dict(binding=binding, source_exit=int(extra[0]), observed_at=date()))
        label, budget = observe_full(root, worker, task, command, adapters)
        print('Adapter outcome: ' + LABELS[label])
        module = budget_module()
        print('Stop reason: ' + LABELS[label])
        print('Run budget: ' + (module.summary(budget)
                                if module is not None and budget is not None else 'Unknown'))
    else:
        raise ValueError('mode')


if __name__ == '__main__':
    try:
        main(sys.argv[1:])
    except (OSError, ValueError, KeyError, TypeError, RecursionError, subprocess.SubprocessError):
        if sys.argv[1:2] != ['prepare']:
            print('Adapter outcome: Unknown')
        sys.exit(1)
