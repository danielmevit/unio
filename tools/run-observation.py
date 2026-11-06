#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Read-only current observation of native run records.

Edit this file, then run tools/embed-run-observation.py. See
docs/INTERRUPTED-RUNS.md. This module only reads: it never creates locks,
removes pid/ownership files, signals processes, rewrites records or calls a
provider. A process that is absent is never reported as an exit code.
"""
import datetime
import fcntl
import hashlib
import json
import os
import re
import stat
import time

SCHEMA_VERSION = 1
DEFAULT_GRACE_SECONDS = 30
MAX_GRACE_SECONDS = 3600
FUTURE_SKEW_SECONDS = 5
RESULT_LIMIT = 4194304
OWNER_LIMIT = 4096
MAX_WORKERS = 4096
MAX_RECORDS = 20000
MAX_OWNER_FILES = 4096
MAX_PROC_ENTRIES = 65536
MAX_PRINTED = 50
IDENT = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,127}')
BOOT = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
OWNER_KEYS = {'schema_version', 'boot_id', 'worker', 'task', 'shell_pid', 'shell_start', 'shell_sid',
              'provider_pid', 'provider_sid', 'provider_start'}
PROCESS_STATES = ('not_run', 'running', 'succeeded', 'failed')
DEAD_STATES = ('Z', 'X', 'x')
PROC_ROOT = '/proc'
# Owner evidence that proves the recorded identity no longer runs.
OWNER_GONE = ('absent', 'reused', 'previous_boot')
# Owner evidence from which nothing may be concluded.
OWNER_UNPROVED = ('malformed', 'unreadable', 'unproved', 'session_members')


class Evidence(Exception):
    """Unsafe or malformed evidence; the observation becomes Unknown."""


def grace_seconds(environ=None):
    """Return (seconds, None), or (None, reason) for an invalid override."""
    raw = (os.environ if environ is None else environ).get('UNIO_ORPHAN_GRACE_SECONDS')
    if raw is None:
        return DEFAULT_GRACE_SECONDS, None
    if not re.fullmatch(r'[1-9][0-9]{0,3}', raw) or int(raw) > MAX_GRACE_SECONDS:
        return None, 'invalid UNIO_ORPHAN_GRACE_SECONDS (1..3600)'
    return int(raw), None


def _ident(value):
    return isinstance(value, str) and IDENT.fullmatch(value) is not None


def _pid_ok(value):
    return type(value) is int and 1 < value <= 999999999


def _tick_ok(value):
    return type(value) is int and 0 <= value <= 2**63


def _plain_dirs(root, parts):
    """Refuse symlinked or special evidence directories below the project."""
    path = root
    for part in parts:
        path = os.path.join(path, part)
        info = os.lstat(path)
        if not stat.S_ISDIR(info.st_mode):
            raise Evidence('evidence directory is a symlink or special file')
    return path


def _read_evidence(path, limit):
    """Read one private-safe regular file; a raised OSError or Evidence is Unknown."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise Evidence('evidence is a special or hardlinked file')
        if info.st_size > limit:
            raise Evidence('evidence exceeds its size limit')
        data = b''
        while len(data) <= limit:
            chunk = os.read(fd, limit + 1 - len(data))
            if not chunk:
                break
            data += chunk
        if len(data) > limit:
            raise Evidence('evidence exceeds its size limit')
        return info, data
    finally:
        os.close(fd)


def probe_lock(root, worker, holding=False):
    """Return free/held/unknown, without creating the worker lock."""
    try:
        directory = _plain_dirs(root, ('coord', '.locks'))
    except FileNotFoundError:
        return 'free'
    except (OSError, Evidence):
        return 'unknown'
    try:
        fd = os.open(os.path.join(directory, worker + '.lock'),
                     os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
    except FileNotFoundError:
        return 'free'
    except OSError:
        return 'unknown'
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            return 'unknown'
        if holding:  # This caller's own exclusive lock already excludes a run.
            return 'free'
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return 'held'
        except OSError:
            return 'unknown'
        return 'free'
    finally:
        os.close(fd)


def current_boot():
    try:
        with open(os.path.join(PROC_ROOT, 'sys/kernel/random/boot_id'), 'rb') as handle:
            value = handle.read(64).decode('ascii').strip()
    except (OSError, UnicodeDecodeError):
        return None
    return value if BOOT.fullmatch(value) else None


def proc_stat(pid):
    """Return a stat dict, None when absent, or 'unproved' when unreadable."""
    base = os.path.join(PROC_ROOT, str(pid))
    try:
        fd = os.open(os.path.join(base, 'stat'), os.O_RDONLY | os.O_CLOEXEC)
        try:
            raw = os.read(fd, 4096)
            uid = os.fstat(fd).st_uid
        finally:
            os.close(fd)
    except (FileNotFoundError, ProcessLookupError):
        return None
    except OSError:
        return 'unproved'
    end = raw.rfind(b')')
    fields = raw[end + 2:].split() if end >= 0 else []
    if len(fields) < 20:
        return 'unproved'
    try:
        return dict(pid=pid, state=fields[0].decode('ascii', 'replace'), sid=int(fields[3]),
                    start=int(fields[19]), uid=uid)
    except (ValueError, IndexError):
        return 'unproved'


class Scan:
    """One observation pass; shares a bounded process-table read across records."""

    def __init__(self):
        self.boot = current_boot()
        self.now = time.time()
        self.grace, self.grace_error = grace_seconds()
        self._sessions = None

    def sessions(self):
        """Map session id to members (uid-owned, alive), or None when unbounded."""
        if self._sessions is None:
            members = {}
            try:
                with os.scandir(PROC_ROOT) as entries:
                    for count, entry in enumerate(entries):
                        if count >= MAX_PROC_ENTRIES:
                            self._sessions = 'unproved'
                            return self._sessions
                        if not entry.name.isdigit():
                            continue
                        info = proc_stat(int(entry.name))
                        if (isinstance(info, dict) and info['uid'] == os.getuid()
                                and info['state'] not in DEAD_STATES):
                            members.setdefault(info['sid'], []).append(info)
            except OSError:
                self._sessions = 'unproved'
                return self._sessions
            self._sessions = members
        return self._sessions


def _valid_owner(doc):
    if (not isinstance(doc, dict) or set(doc) != OWNER_KEYS
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1):
        return False
    if not isinstance(doc['boot_id'], str) or not BOOT.fullmatch(doc['boot_id']):
        return False
    if not _ident(doc['worker']) or not _ident(doc['task']):
        return False
    if not _pid_ok(doc['shell_pid']) or not _pid_ok(doc['shell_sid']) or not _tick_ok(doc['shell_start']):
        return False
    provider = (doc['provider_pid'], doc['provider_sid'], doc['provider_start'])
    if provider == (None, None, None):
        return True
    return (_pid_ok(provider[0]) and provider[0] == provider[1] and _tick_ok(provider[2])
            and provider[1] != doc['shell_sid'])


def _owner_files(root, worker, task):
    # Task-addressed controls exist only for background runs; the per-worker
    # record is authoritative whenever it is present.
    return (os.path.join(root, 'coord', 'reports', '.owners', worker, task + '.own'),
            os.path.join(root, 'coord', 'reports', task + '.own'))


def _read_owner(root, worker, task):
    """Return (doc, digest, state); doc is only set for a well-formed record."""
    try:
        _plain_dirs(root, ('coord', 'reports'))
        for parent in (('coord', 'reports', '.owners'), ('coord', 'reports', '.owners', worker)):
            try:
                _plain_dirs(root, parent)
            except FileNotFoundError:
                break
    except FileNotFoundError:
        return None, None, 'missing'
    except (OSError, Evidence):
        return None, None, 'unreadable'
    for path in _owner_files(root, worker, task):
        try:
            info, data = _read_evidence(path, OWNER_LIMIT)
        except FileNotFoundError:
            continue
        except (OSError, Evidence):
            return None, None, 'unreadable'
        digest = hashlib.sha256(data).hexdigest()
        if info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & 0o077:
            return None, digest, 'unreadable'
        try:
            doc = json.loads(data)
        except ValueError:
            return None, digest, 'malformed'
        if not _valid_owner(doc) or doc['task'] != task or doc['worker'] != worker:
            return None, digest, 'malformed'
        return doc, digest, 'recorded'
    return None, None, 'missing'


def _identity(pid, start, sid):
    """live, reused (pid names another process), absent, or unproved."""
    if pid is None:
        return 'absent'
    info = proc_stat(pid)
    if info is None:
        return 'absent'
    if info == 'unproved':
        return 'unproved'
    if info['start'] != start:
        return 'reused'
    if info['state'] in DEAD_STATES:
        return 'absent'
    if info['uid'] != os.getuid() or info['sid'] != sid:
        return 'reused'
    return 'live'


def owner_state(doc, scan):
    """Classify recorded ownership; a PID number alone never establishes it."""
    if scan.boot is None:
        return 'unproved'
    if doc['boot_id'] != scan.boot:
        return 'previous_boot'
    shell = _identity(doc['shell_pid'], doc['shell_start'], doc['shell_sid'])
    provider = _identity(doc['provider_pid'], doc['provider_start'], doc['provider_sid'])
    if 'live' in (shell, provider):
        return 'live'
    if 'unproved' in (shell, provider):
        return 'unproved'
    # Descendants may outlive both leaders inside the owned sessions. A session
    # whose leader PID was reused has ended, because a PID cannot be reassigned
    # while its session exists; other members stay unproved, never owned.
    sessions = scan.sessions()
    if sessions == 'unproved':
        return 'unproved'
    # A foreground shell's session is the user's terminal, which is not owned.
    owned = [(doc['provider_sid'], provider)]
    if doc['shell_sid'] == doc['shell_pid']:
        owned.append((doc['shell_sid'], shell))
    for sid, status in owned:
        if sid is None or status == 'reused':
            continue
        if any(member['start'] >= doc['shell_start'] and member['pid'] != os.getpid()
               for member in sessions.get(sid, ())):
            return 'session_members'
    return 'reused' if 'reused' in (shell, provider) else 'absent'


def _other_live_owner(root, worker, task, scan):
    """A distinct task's proved owner explains a held worker lock."""
    directory = os.path.join(root, 'coord', 'reports', '.owners', worker)
    try:
        _plain_dirs(root, ('coord', 'reports', '.owners', worker))
        with os.scandir(directory) as entries:
            for count, entry in enumerate(entries):
                if count >= MAX_OWNER_FILES:
                    return False
                other = entry.name[:-4] if entry.name.endswith('.own') else ''
                if not other or other == task or not _ident(other):
                    continue
                doc, _, state = _read_owner(root, worker, other)
                if state == 'recorded' and owner_state(doc, scan) == 'live':
                    return True
    except (OSError, Evidence):
        return False
    return False


def _read_record(root, worker, task):
    """Return (doc, digest); doc is None and digest a reason on bad evidence."""
    try:
        directory = _plain_dirs(root, ('coord', 'results', worker))
        _, data = _read_evidence(os.path.join(directory, task + '.json'), RESULT_LIMIT)
    except (OSError, Evidence) as exc:
        return None, type(exc).__name__
    digest = hashlib.sha256(data).hexdigest()
    try:
        doc = json.loads(data)
    except ValueError:
        return None, digest
    process = doc.get('process') if isinstance(doc, dict) else None
    if (not isinstance(process, dict) or doc.get('worker') != worker or doc.get('task') != task
            or process.get('state') not in PROCESS_STATES):
        return None, digest
    code = process.get('exit_code')
    if code is not None and type(code) is not int:
        return None, digest
    if process['state'] in ('running', 'not_run') and code is not None:
        return None, digest
    return doc, digest


def _recorded_time(doc):
    value = doc.get('updated_at')
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return parsed.timestamp() if parsed.tzinfo is not None else None


def _sample(root, worker, task, scan, holding):
    doc, record_digest = _read_record(root, worker, task)
    if doc is None or doc['process']['state'] != 'running':
        return doc, (record_digest,), 'free', 'not_applicable'
    lock = probe_lock(root, worker, holding)
    owner_doc, owner_digest, owner = _read_owner(root, worker, task)
    if owner == 'recorded':
        owner = owner_state(owner_doc, scan)
    return doc, (record_digest, lock, owner_digest, owner), lock, owner


def _base(worker, task, scan):
    return dict(schema_version=SCHEMA_VERSION, worker=worker, task=task, state='unknown',
                completion='unknown', interrupted=None, source_exit=None,
                recorded_process_state=None, recorded_at=None, recorded_revision=None,
                worker_lock='not_applicable', owner='not_applicable', grace_seconds=scan.grace,
                detached_processes_ruled_out=False, blocks_readiness=True, reasons=[],
                basis='current read-only observation; process.* stays the recorded fact')


def observe(root, worker, task, scan=None, holding=False):
    """Project the current observation. Inputs are never changed."""
    scan = scan or Scan()
    out = _base(worker, task, scan)
    if not _ident(worker) or not _ident(task):
        out['reasons'].append('invalid worker or task identifier')
        return out
    # A startup or exit can cross these reads. Only two identical samples count;
    # a record that became terminal is simply re-read as terminal.
    doc, first, lock, owner = _sample(root, worker, task, scan, holding)
    second = None
    for _ in range(3):
        doc, second, lock, owner = _sample(root, worker, task, scan, holding)
        if second == first:
            break
        first = second
        second = None
    if second is None:
        out['reasons'].append('evidence changed while observing')
        return out
    if doc is None:
        out['reasons'].append('record unreadable or malformed')
        return out
    process = doc['process']
    recorded = process['state']
    rev = process.get('revision') if isinstance(process.get('revision'), dict) else doc.get('revision')
    commit = rev.get('candidate_commit') if isinstance(rev, dict) else None
    out.update(recorded_process_state=recorded,
               recorded_at=doc.get('updated_at') if isinstance(doc.get('updated_at'), str) else None,
               recorded_revision=commit if isinstance(commit, str) else None)
    if recorded != 'running':
        out.update(state='terminal' if recorded != 'not_run' else 'not_run',
                   completion='recorded' if recorded != 'not_run' else 'not_run',
                   source_exit=process.get('exit_code'), blocks_readiness=False, interrupted=False)
        return out
    out.update(worker_lock=lock, owner=owner)
    if lock == 'unknown':
        out['reasons'].append('worker lock unreadable or unsafe')
        return out
    if lock == 'held':
        if owner != 'live' and _other_live_owner(root, worker, task, scan):
            out.update(state='completion_unknown', interrupted=True if owner in OWNER_GONE else None)
            out['reasons'].append('worker lock is held by another task; no completion recorded here')
            return out
        out.update(state='running', completion='in_progress')
        return out
    if owner == 'live':
        out.update(state='running', completion='in_progress')
        return out
    if owner in OWNER_UNPROVED:
        out['reasons'].append('ownership evidence ' + owner)
        return out
    if scan.grace is None:
        out['reasons'].append(scan.grace_error)
        return out
    when = _recorded_time(doc)
    if when is None:
        out['reasons'].append('recorded time missing or invalid')
        return out
    age = scan.now - when
    if age < -FUTURE_SKEW_SECONDS:
        out['reasons'].append('recorded time is in the future')
        return out
    if age < scan.grace:
        out.update(state='pending_grace')
        out['reasons'].append('free lock inside the grace window; a start or exit may be in flight')
        return out
    out.update(state='completion_unknown', interrupted=True if owner in OWNER_GONE else None)
    out['reasons'].append('free worker lock, no recorded end, owner ' + owner)
    return out


def activity(observation):
    """The existing watch/dashboard activity vocabulary."""
    state = observation['state']
    if state in ('terminal', 'not_run'):
        return observation['recorded_process_state'] or 'Unknown'
    return 'running_recorded' if state in ('running', 'pending_grace') else 'completion_unknown'


def source_exit_text(observation):
    return 'Unknown' if observation['source_exit'] is None else str(observation['source_exit'])


def _clean(value):
    return str(value).encode('unicode_escape').decode('ascii')


def human_lines(observation):
    o = observation
    worker, task = _clean(o['worker']), _clean(o['task'])
    lines = ['Current observation: %s (run %s / %s)' % (o['state'], worker, task),
             'Source exit: %s' % source_exit_text(o),
             'Recorded process state: %s; recorded at: %s; recorded revision: %s' % (
                 _clean(o['recorded_process_state'] or 'Unknown'), _clean(o['recorded_at'] or 'Unknown'),
                 _clean(o['recorded_revision'] or 'Unknown')),
             'Worker lock: %s; owner evidence: %s; interrupted: %s' % (
                 o['worker_lock'], o['owner'], 'Unknown' if o['interrupted'] is None else o['interrupted'])]
    lines.extend('Reason: ' + _clean(reason) for reason in o['reasons'])
    if o['blocks_readiness'] and o['state'] != 'running':
        lines.extend(['No completion is recorded. This is not exit 0, not a timeout and not acceptance;',
                      'a detached process is not ruled out. Original evidence is unchanged.',
                      'Inspect: unio result %s %s; git -C wt/%s log; unio save inspect --worker %s' % (worker, task, worker, worker),
                      'Continue only through a separately authorized new task ID; nothing is replayed.'])
    return lines


def workers_for(root, task, limit=MAX_WORKERS):
    """Worker names with a record for this task, by direct lookup per worker."""
    found, truncated = [], False
    try:
        directory = _plain_dirs(root, ('coord', 'results'))
        with os.scandir(directory) as entries:
            names = []
            for count, entry in enumerate(entries):
                if count >= limit:
                    truncated = True
                    break
                names.append(entry.name)
    except FileNotFoundError:
        return found, False
    except (OSError, Evidence):
        return found, True
    for name in sorted(names):
        if _ident(name) and os.path.lexists(os.path.join(directory, name, task + '.json')):
            found.append(name)
    return found, truncated


def report_observation(root, task):
    """Print unresolved observations for a task. Returns 0 if any was printed."""
    if not _ident(task):
        return 3
    workers, truncated = workers_for(root, task)
    scan = Scan()
    unresolved = [o for o in (observe(root, worker, task, scan) for worker in workers) if o['blocks_readiness']]
    if not unresolved and not truncated:
        return 3
    if len(unresolved) > 1:
        print('%d workers have an unresolved record for this task; each is shown separately.' % len(unresolved))
    for o in unresolved[:MAX_PRINTED]:
        print('\n'.join(human_lines(o)))
    if len(unresolved) > MAX_PRINTED:
        print('... %d more; see unio watch --once --json' % (len(unresolved) - MAX_PRINTED))
    if truncated:
        print('Observation incomplete: results directory unreadable or over its scan limit.')
    print('No task report file is fabricated by this observation.')
    return 0


def project_observations(root):
    """Return (observations, truncated) for every native record, bounded."""
    out, truncated = [], False
    scan = Scan()
    try:
        directory = _plain_dirs(root, ('coord', 'results'))
        with os.scandir(directory) as entries:
            workers = sorted((e.name for e in entries if e.is_dir(follow_symlinks=False)))
    except FileNotFoundError:
        return out, False
    except (OSError, Evidence):
        return out, True
    if len(workers) > MAX_WORKERS:
        workers, truncated = workers[:MAX_WORKERS], True
    for worker in workers:
        if not _ident(worker):
            continue
        try:
            with os.scandir(os.path.join(directory, worker)) as entries:
                tasks = sorted(e.name[:-5] for e in entries if e.name.endswith('.json'))
        except OSError:
            truncated = True
            continue
        for task in tasks:
            if len(out) >= MAX_RECORDS:
                return out, True
            if _ident(task):
                out.append(observe(root, worker, task, scan))
    return out, truncated


def pid_evidence(root, task):
    """Say whether a task's pidfile has proved ownership; never deletes it."""
    path = os.path.join(root, 'coord', 'reports', task + '.pid')
    try:
        _, raw = _read_evidence(path, 32)
    except FileNotFoundError:
        return 'none', None
    except (OSError, Evidence):
        return 'unproved', None
    if not re.fullmatch(rb'[1-9][0-9]{0,8}\n?', raw):
        return 'unproved', None
    pid = int(raw)
    try:
        _, data = _read_evidence(os.path.join(root, 'coord', 'reports', task + '.own'), OWNER_LIMIT)
        doc = json.loads(data)
    except (OSError, Evidence, ValueError):
        return 'unproved', pid
    if not _valid_owner(doc) or doc['task'] != task or doc['shell_pid'] != pid:
        return 'unproved', pid
    return ('live' if owner_state(doc, Scan()) == 'live' else 'not_live'), pid


def status_lines(root):
    """Human status section: owned observation, not raw PID or process names."""
    observations, truncated = project_observations(root)
    running = [o for o in observations if o['state'] == 'running']
    orphans = [o for o in observations if o['state'] == 'completion_unknown']
    other = [o for o in observations if o['state'] in ('unknown', 'pending_grace')]
    lines = []
    for o in running[:MAX_PRINTED]:
        state, pid = pid_evidence(root, o['task'])
        where = ' (background, pid %d)' % pid if state == 'live' else ''
        lines.append('  %s / %s%s — tail: unio tail -f %s' % (_clean(o['worker']), _clean(o['task']), where, _clean(o['task'])))
    if not running:
        lines.append('  (none)')
    lines.append('  Completion unknown (possibly interrupted; Source exit Unknown): %d' % len(orphans))
    for o in orphans[:MAX_PRINTED]:
        lines.append('    %s / %s — inspect: unio report %s' % (_clean(o['worker']), _clean(o['task']), _clean(o['task'])))
    if other:
        lines.append('  Observation Unknown or inside grace: %d' % len(other))
        for o in other[:MAX_PRINTED]:
            lines.append('    %s / %s — %s' % (_clean(o['worker']), _clean(o['task']), o['state']))
    if truncated:
        lines.append('  Observation incomplete: scan limit reached or results unreadable (Unknown).')
    return lines
