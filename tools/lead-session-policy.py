#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Native lead session policy admission and lease controller.

Enforces actual initialized project policy before any owned Codex app-server
process or turn operation (contract 0532-ADAPTIVE-LEAD-ADMISSION-V4 and
0532-ADAPTIVE-ADMISSION-CORRECTIONS-V5):
- project STOP (coord/STOP);
- installed and project-level off holds with duration expiry;
- native real account/group mapping and existing explicit lead registration;
- tier limits and native active slot counts (counting the registered lead exactly once);
- atomic short policy transaction + non-blocking owned lease lock (coord/.locks/lead-session.lock);
- setter guard preventing lead/account changes during an active owned invocation.
"""
import contextlib
import datetime
import fcntl
import json
import os
from pathlib import Path
import stat
import time

MAX_POLICY_BYTES = 16384
MAX_SLOT_META = 4096
LIMITS = {'low': 1, 'medium': 2, 'high': 4}
TIERS = frozenset(LIMITS)
MODES = frozenset(('yolo', 'medium', 'safe'))
ALLOWED_KEYS = frozenset(('schema_version', 'mode', 'tier', 'lead_agent', 'accounts', 'updated_at'))
WPSLOT_PREFIX = 'wpslot-'
DEFAULT_LEAD_AGENT = 'codex'


class Refusal(Exception):
    """A controlled policy admission refusal."""


def check_label(value, what):
    """Validate label strictly matching native policy rules."""
    if (not isinstance(value, str) or not value or value in ('.', '..')
            or '..' in value or value.startswith('-')
            or any(c.isspace() or ord(c) < 32 or c in '/\\' for c in value)):
        raise Refusal('invalid %s label: %r' % (what, value))


def check_updated_at(value):
    """Validate ISO timestamp with timezone."""
    if type(value) is not str:
        raise Refusal('project policy state has an invalid updated_at')
    try:
        val = value.replace('Z', '+00:00') if value.endswith('Z') else value
        parsed = datetime.datetime.fromisoformat(val)
    except ValueError:
        raise Refusal('project policy state has an invalid updated_at')
    if parsed.tzinfo is None:
        raise Refusal('project policy state has an invalid updated_at')


def check_control_path(root, *parts):
    """Ensure paths are within root and contain no symlinks or traversal."""
    if not isinstance(root, (str, Path)) or not root:
        raise Refusal('refusing unsafe workspace root: ' + repr(root))
    root_str = str(root)
    if not os.path.isdir(root_str):
        raise Refusal('refusing unsafe workspace root (not a directory): ' + repr(root_str))
    if os.path.islink(root_str):
        raise Refusal('refusing unsafe workspace root (symlink): ' + repr(root_str))
    for part in parts:
        if not part or part in ('.', '..') or '..' in str(part).split('/') or str(part).startswith('-'):
            raise Refusal('refusing unsafe control path component: ' + repr(part))
    node = root_str
    for part in parts:
        for component in str(part).split('/'):
            if component in ('', '.', '..'):
                raise Refusal('refusing unsafe control path component: ' + repr(part))
            node = os.path.join(node, component)
            if os.path.islink(node):
                raise Refusal('refusing unsafe control path (symlink): ' + repr(node))
    return node


def is_project_stop_active(root):
    """Check whether project-wide coord/STOP exists."""
    stop = os.path.join(str(root), 'coord', 'STOP')
    return os.path.lexists(stop) or os.path.exists(stop)


def check_project_stop(root):
    """Refuse if project STOP is active."""
    if is_project_stop_active(root):
        raise Refusal('project STOP is active: lead session operations are blocked')


def _read_regular_file(path, bound):
    """Read regular file bounded without following symlinks."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        return None
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            raise Refusal('refusing unsafe control file (not a regular unlinked file): ' + path)
        if st.st_size > bound:
            raise Refusal('refusing oversized control file: ' + path)
        data = os.read(fd, bound + 1)
        if len(data) > bound:
            raise Refusal('refusing oversized control file: ' + path)
        return data
    finally:
        os.close(fd)


def check_off_hold(root, agent):
    """Check installed and project-level off holds with duration expiry."""
    markers = []
    # Project-level off hold (read-only observation)
    proj_marker = os.path.join(str(root), 'coord', 'off', agent)
    if os.path.lexists(proj_marker):
        markers.append(proj_marker)
    # Installed-level off hold
    confs = []
    for env_var in ('UNIO_CONF_DIR', 'CONF_DIR'):
        val = os.environ.get(env_var)
        if val:
            confs.append(val)
    if not confs:
        try:
            confs.append(str(Path.home() / '.config' / 'unio'))
        except Exception:
            pass
    for conf_dir in confs:
        if conf_dir and os.path.isdir(conf_dir):
            inst_marker = os.path.join(conf_dir, 'off', agent)
            if os.path.lexists(inst_marker) and inst_marker not in markers:
                markers.append(inst_marker)
    now = time.time()
    for marker in markers:
        raw = _read_regular_file(marker, 256)
        if raw is None:
            # If marker exists but cannot be read normally, fail closed
            raise Refusal("registered lead '%s' is off: hold is active" % agent)
        text = raw.decode('utf-8', errors='replace').strip()
        benched = True
        if text.isdigit():
            exp = int(text)
            benched = (exp > now)
        if benched:
            raise Refusal("registered lead '%s' is off: hold is active" % agent)


def read_project_policy(root):
    """Read and strictly validate coord/work-policy.json."""
    path = os.path.join(str(root), 'coord', 'work-policy.json')
    if not os.path.lexists(path):
        raise Refusal('project work-policy not initialized (coord/work-policy.json missing)')
    if os.path.islink(path):
        raise Refusal('refusing unsafe policy state (symlink): ' + path)
    raw = _read_regular_file(path, MAX_POLICY_BYTES)
    if raw is None:
        raise Refusal('cannot read project policy state: ' + path)
    try:
        text = raw.decode('utf-8')
    except UnicodeDecodeError:
        raise Refusal('project policy state is not UTF-8: ' + path)

    def _unique_object(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('duplicate key: ' + str(key))
            obj[key] = value
        return obj

    try:
        doc = json.loads(text, object_pairs_hook=_unique_object)
    except ValueError as exc:
        raise Refusal('project policy state is malformed: ' + str(exc))

    if not isinstance(doc, dict):
        raise Refusal('project policy state is malformed (not a JSON object)')
    unknown = set(doc) - ALLOWED_KEYS
    if unknown:
        raise Refusal('project policy state has unknown keys: ' + ', '.join(sorted(unknown)))
    if type(doc.get('schema_version')) is not int or doc.get('schema_version') != 1:
        raise Refusal('project policy state has unknown schema (schema_version must be 1)')
    for required in ('mode', 'tier', 'lead_agent', 'accounts'):
        if required not in doc:
            raise Refusal('project policy state missing required key: ' + required)
    if doc.get('mode') not in MODES:
        raise Refusal('project policy state has invalid mode: ' + repr(doc.get('mode')))
    if doc.get('tier') not in TIERS:
        raise Refusal('project policy state has invalid tier: ' + repr(doc.get('tier')))
    lead = doc.get('lead_agent')
    if lead is not None:
        if type(lead) is not str:
            raise Refusal('project policy state has invalid lead_agent')
        check_label(lead, 'lead agent')
    accounts = doc.get('accounts')
    if type(accounts) is not dict:
        raise Refusal('project policy state has invalid accounts mapping')
    for k, v in accounts.items():
        if type(k) is not str or type(v) is not str:
            raise Refusal('project policy state has invalid account mapping entry')
        check_label(k, 'account agent')
        check_label(v, 'account group')
    if 'updated_at' in doc:
        check_updated_at(doc['updated_at'])
    return doc


def count_active_slots(root, group):
    """Count currently locked native workflow slots in the given budget group.

    Fails closed on unreadable or unsafe slot state (matching native count_active).
    A missing directory legitimately returns 0 active workflows.
    """
    check_label(group, 'budget group')
    check_control_path(root, 'coord', '.locks', 'work-policy-slots', group)
    directory = os.path.join(str(root), 'coord', '.locks', 'work-policy-slots', group)
    if not os.path.lexists(directory):
        return 0
    if os.path.islink(directory):
        raise Refusal('refusing unsafe slot directory (symlink): ' + directory)
    if not os.path.isdir(directory):
        raise Refusal('refusing unsafe slot directory (not a directory): ' + directory)
    active = 0
    try:
        names = os.listdir(directory)
    except OSError as exc:
        raise Refusal('cannot list slot directory %s: %s' % (directory, exc)) from exc
    for name in sorted(names):
        if not name.startswith(WPSLOT_PREFIX) or not name.endswith('.json'):
            continue
        path = os.path.join(directory, name)
        if os.path.islink(path):
            raise Refusal('refusing unsafe slot (symlink): ' + path)
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise Refusal('cannot open slot %s: %s' % (path, exc)) from exc
        try:
            st = os.fstat(fd)
            if not stat.S_ISREG(st.st_mode):
                raise Refusal('refusing unsafe slot (not a regular file): ' + path)
            if st.st_nlink != 1:
                raise Refusal('refusing unsafe slot (hardlinked): ' + path)
            if st.st_size > MAX_SLOT_META:
                raise Refusal('refusing unsafe slot (oversized): ' + path)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                # Busy: slot is locked by an active native workflow
                active += 1
                continue
            # Slot is unlocked (inactive); validate its contents like native read_slot_meta
            try:
                chunks = []
                total = 0
                while True:
                    piece = os.read(fd, 2048)
                    if not piece:
                        break
                    total += len(piece)
                    if total > MAX_SLOT_META:
                        raise Refusal('refusing unsafe slot (oversized): ' + path)
                    chunks.append(piece)
                try:
                    meta = json.loads(b''.join(chunks).decode('utf-8'))
                except (ValueError, UnicodeDecodeError) as exc:
                    raise Refusal('refusing unsafe slot (malformed json): %s' % path)
                if (not isinstance(meta, dict) or meta.get('schema_version') != 1
                        or type(meta.get('group')) is not str or type(meta.get('agent')) is not str
                        or type(meta.get('worker')) is not str or type(meta.get('task')) is not str
                        or meta.get('kind') not in ('run', 'review')):
                    raise Refusal('refusing unsafe slot (invalid schema): ' + path)
                check_label(meta['group'], 'budget group')
                check_label(meta['agent'], 'slot agent')
                if 'created_at' in meta:
                    check_updated_at(meta['created_at'])
            finally:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            os.close(fd)
    return active


class OwnedLeadLease:
    """Lock-backed lease for one active owned lead invocation."""

    def __init__(self, fd, path):
        self._fd = fd
        self._path = path
        self._released = False

    def release(self):
        if self._released:
            return
        self._released = True
        try:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
        except OSError:
            pass
        try:
            os.close(self._fd)
        except OSError:
            pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()


def admit_lead(root, expected_agent=DEFAULT_LEAD_AGENT, budget_label=None):
    """Enforce atomic native admission under policy and lease locks.

    1. Validates workspace root and coord directory existence.
    2. Acquires the non-blocking owned lease lock (coord/.locks/lead-session.lock).
       Conflicting active owned invocations refuse immediately.
    3. Takes a short policy transaction lock (coord/.locks/work-policy.lock).
    4. Validates:
       - project STOP is clear;
       - project policy exists and is strictly valid;
       - lead registration exists and matches expected_agent;
       - installed and project-level off holds are clear / expired;
       - budget group mapping resolves correctly (mismatched budget_label refuses);
       - group capacity (active native workflows + 1 lead reservation <= tier limit).
    5. Releases the policy lock (does NOT hold it across the turn/model invocation).
    6. Returns (policy_doc, lead_group, lease).
    """
    check_control_path(root, 'coord')
    coord_dir = os.path.join(str(root), 'coord')
    if not os.path.isdir(coord_dir) or os.path.islink(coord_dir):
        raise Refusal('project coord directory not found: ' + coord_dir)
    locks_dir = os.path.join(coord_dir, '.locks')
    try:
        os.makedirs(locks_dir, exist_ok=True)
    except OSError as exc:
        raise Refusal('cannot create locks directory: ' + str(exc)) from exc

    lease_path = os.path.join(locks_dir, 'lead-session.lock')
    if os.path.islink(lease_path):
        raise Refusal('refusing unsafe lease lock path (symlink): ' + lease_path)
    try:
        fd_lease = os.open(lease_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    except OSError as exc:
        raise Refusal('cannot open lease lock: ' + str(exc)) from exc

    try:
        try:
            fcntl.flock(fd_lease, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refusal('active owned lead session already running in workspace')

        # Short policy transaction lock
        policy_lock = os.path.join(locks_dir, 'work-policy.lock')
        if os.path.islink(policy_lock):
            raise Refusal('refusing unsafe policy lock path (symlink): ' + policy_lock)
        fd_pol = os.open(policy_lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o644)
        try:
            fcntl.flock(fd_pol, fcntl.LOCK_EX)
            try:
                # 1. Project STOP
                check_project_stop(root)

                # 2. Strict policy read
                doc = read_project_policy(root)

                # 3. Lead registration check
                lead = doc.get('lead_agent')
                if lead is None:
                    raise Refusal("no lead registered in project policy; register with 'unio lead <agent>' first")
                if expected_agent is not None and lead != expected_agent:
                    raise Refusal("registered lead mismatch: policy has '%s', expected '%s'"
                                  % (lead, expected_agent))

                # 4. Off hold check
                check_off_hold(root, lead)

                # 5. Account & group mapping
                group = doc['accounts'].get(lead, lead)
                if budget_label is not None:
                    check_label(budget_label, 'budget label')
                    if budget_label != group:
                        raise Refusal("budget label mismatch: requested '%s', but registered lead '%s' is in group '%s'"
                                      % (budget_label, lead, group))

                # 6. Group capacity check (native active workflows + 1 lead reservation <= cap)
                cap = LIMITS[doc['tier']]
                native_active = count_active_slots(root, group)
                lead_reservation = 1
                if native_active + lead_reservation > cap:
                    raise Refusal("budget group '%s' at capacity: %d active native workflow(s) plus %d lead reservation, "
                                  "exceeding tier '%s' limit of %d"
                                  % (group, native_active, lead_reservation, doc['tier'], cap))

                # Record lease metadata
                meta = (json.dumps({'pid': os.getpid(), 'lead_agent': lead,
                                    'group': group, 'acquired_at': time.time()}) + '\n').encode('utf-8')
                os.ftruncate(fd_lease, 0)
                os.lseek(fd_lease, 0, os.SEEK_SET)
                os.write(fd_lease, meta)
                os.fsync(fd_lease)
            finally:
                try:
                    fcntl.flock(fd_pol, fcntl.LOCK_UN)
                finally:
                    os.close(fd_pol)
        except BaseException:
            raise
    except BaseException:
        try:
            fcntl.flock(fd_lease, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd_lease)
        raise

    return doc, group, OwnedLeadLease(fd_lease, lease_path)


@contextlib.contextmanager
def lead_session_guard(root):
    """Guard for setters (set-lead, set-account) against active owned lead invocations.

    Attempts a non-blocking lock on coord/.locks/lead-session.lock. If busy,
    refuses because an owned lead invocation is actively running.
    """
    locks_dir = os.path.join(str(root), 'coord', '.locks')
    lease_path = os.path.join(locks_dir, 'lead-session.lock')
    if not os.path.lexists(lease_path):
        yield
        return
    try:
        fd = os.open(lease_path, os.O_RDWR | os.O_NOFOLLOW)
    except OSError:
        yield
        return
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise Refusal('active owned lead session is running')
        try:
            yield
        finally:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:
                pass
    finally:
        os.close(fd)
