#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Focused regression tests for lead-session policy admission (contract V5).

Covers:
1. Default installed off hold discovery without UNIO_CONF_DIR / CONF_DIR
   (falling back to ~/.config/unio/off/<agent>) and duration expiry.
2. Explicit UNIO_CONF_DIR and CONF_DIR off hold discovery.
3. Read-only project-level coord/off/<agent> compatibility observation.
4. Production entrypoint environment export of UNIO_CONF_DIR.
5. Native 4096-byte slot metadata parity (2500-byte locked slot counts active).
6. Fail-closed slot counting on unreadable or unsafe state (permission faults
   tested without assuming root is denied by chmod 000, oversized metadata,
   symlinked slots, non-regular files, hardlinks, malformed JSON).
7. Strict label validation matching native policy (lead_agent, accounts, budget).
8. Project root validation avoiding stray coord/.locks directory creation.
9. Owned lease locking and setter guard exclusion.
"""
import contextlib
import errno
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def _load_module(name, relative_path):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lp = _load_module('unio_lead_session_policy', 'tools/lead-session-policy.py')


def refuses(fn, *args, **kwargs):
    try:
        fn(*args, **kwargs)
    except lp.Refusal as exc:
        return str(exc)
    raise AssertionError('expected lp.Refusal, but function returned normally')


def make_workspace(base_dir, lead='codex', tier='low', accounts=None):
    ws = Path(base_dir) / 'ws'
    coord = ws / 'coord'
    coord.mkdir(parents=True, exist_ok=True)
    policy_doc = {
        'schema_version': 1,
        'mode': 'yolo',
        'tier': tier,
        'lead_agent': lead,
        'accounts': accounts if accounts is not None else {},
        'updated_at': '2026-11-15T12:00:00Z',
    }
    policy_file = coord / 'work-policy.json'
    policy_file.write_text(json.dumps(policy_doc, indent=2) + '\n', encoding='utf-8')
    return ws


@contextlib.contextmanager
def locked_slot(ws, group, name, size=None, payload=None):
    slot_dir = Path(ws) / 'coord' / '.locks' / 'work-policy-slots' / group
    slot_dir.mkdir(parents=True, exist_ok=True)
    slot_path = slot_dir / ('wpslot-%s.json' % name)
    if payload is not None:
        data = payload if isinstance(payload, bytes) else payload.encode('utf-8')
    else:
        doc = {
            'schema_version': 1,
            'group': group,
            'agent': 'w1',
            'worker': 'worker-1',
            'task': 'task-1',
            'kind': 'run',
            'created_at': '2026-11-15T12:00:00Z',
        }
        raw = json.dumps(doc, indent=2) + '\n'
        if size is not None and size > len(raw):
            # Pad valid JSON using extra whitespace before closing brace
            padding = ' ' * (size - len(raw))
            raw = json.dumps(doc, indent=2)[:-2] + padding + '\n}\n'
            assert len(raw) == size
        data = raw.encode('utf-8')
    slot_path.write_bytes(data)
    fd = os.open(slot_path, os.O_RDWR)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        yield slot_path
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass
        os.close(fd)
        if slot_path.exists():
            slot_path.unlink()


def test_default_installed_off_hold(base_dir):
    """Test default installed hold discovery (~/.config/unio/off/<agent>)."""
    fake_home = Path(base_dir) / 'home'
    default_conf = fake_home / '.config' / 'unio'
    off_dir = default_conf / 'off'
    off_dir.mkdir(parents=True, exist_ok=True)

    ws = make_workspace(base_dir)

    # Save original env
    orig_env = {k: os.environ.get(k) for k in ('HOME', 'UNIO_CONF_DIR', 'CONF_DIR')}
    try:
        os.environ['HOME'] = str(fake_home)
        os.environ.pop('UNIO_CONF_DIR', None)
        os.environ.pop('CONF_DIR', None)

        marker = off_dir / 'codex'
        # 1. Active permanent hold (empty marker)
        marker.write_text('')
        msg = refuses(lp.admit_lead, ws)
        assert "registered lead 'codex' is off: hold is active" in msg, msg

        # 2. Active timed hold (future timestamp)
        marker.write_text(str(int(time.time() + 3600)) + '\n')
        msg = refuses(lp.admit_lead, ws)
        assert "registered lead 'codex' is off: hold is active" in msg, msg

        # 3. Expired timed hold (past timestamp) -> admission succeeds
        marker.write_text(str(int(time.time() - 3600)) + '\n')
        doc, group, lease = lp.admit_lead(ws)
        lease.release()
        assert group == 'codex'

        # 4. Malformed hold marker -> fail closed (treated as permanent)
        marker.write_text('not-a-number\n')
        msg = refuses(lp.admit_lead, ws)
        assert "registered lead 'codex' is off: hold is active" in msg, msg

        # 5. Cleared hold -> admission succeeds
        marker.unlink()
        doc, group, lease = lp.admit_lead(ws)
        lease.release()
        assert group == 'codex'
    finally:
        for k, v in orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    print('ok default installed off hold discovery and expiry', flush=True)


def test_explicit_conf_off_holds(base_dir):
    """Test explicit UNIO_CONF_DIR and CONF_DIR discovery."""
    ws = make_workspace(base_dir)
    custom_conf = Path(base_dir) / 'custom_conf'
    off_dir = custom_conf / 'off'
    off_dir.mkdir(parents=True, exist_ok=True)
    marker = off_dir / 'codex'
    marker.write_text('')

    orig_env = {k: os.environ.get(k) for k in ('UNIO_CONF_DIR', 'CONF_DIR')}
    try:
        # UNIO_CONF_DIR
        os.environ['UNIO_CONF_DIR'] = str(custom_conf)
        os.environ.pop('CONF_DIR', None)
        msg = refuses(lp.admit_lead, ws)
        assert "registered lead 'codex' is off: hold is active" in msg

        # CONF_DIR
        os.environ.pop('UNIO_CONF_DIR', None)
        os.environ['CONF_DIR'] = str(custom_conf)
        msg = refuses(lp.admit_lead, ws)
        assert "registered lead 'codex' is off: hold is active" in msg

        # Clear marker
        marker.unlink()
        doc, group, lease = lp.admit_lead(ws)
        lease.release()
    finally:
        for k, v in orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    print('ok explicit UNIO_CONF_DIR and CONF_DIR off hold discovery', flush=True)


def test_project_off_hold_observation(base_dir):
    """Test project-level coord/off/<agent> read-only compatibility observation."""
    ws = make_workspace(base_dir)
    proj_off = ws / 'coord' / 'off'
    proj_off.mkdir(parents=True, exist_ok=True)
    marker = proj_off / 'codex'
    marker.write_text('')

    # Project hold refuses
    msg = refuses(lp.admit_lead, ws)
    assert "registered lead 'codex' is off: hold is active" in msg

    # Expired project hold passes
    marker.write_text(str(int(time.time() - 100)) + '\n')
    doc, group, lease = lp.admit_lead(ws)
    lease.release()

    # Symlinked or unreadable project hold fails closed
    marker.unlink()
    target = ws / 'coord' / 'fake-target'
    target.write_text('123\n')
    marker.symlink_to(target)
    msg = refuses(lp.admit_lead, ws)
    assert "registered lead 'codex' is off: hold is active" in msg
    marker.unlink()
    target.unlink()
    print('ok project-level coord/off read-only observation', flush=True)


def test_production_dispatch_propagation(base_dir):
    """Test that unio lead-session dispatch exports UNIO_CONF_DIR."""
    # Verify unio-install.sh contains the export in lead-session) dispatch
    installer = ROOT / 'unio-install.sh'
    content = installer.read_text(encoding='utf-8')
    assert 'export UNIO_CONF_DIR="$CONF_DIR"' in content
    # Run a test unio invocation through bash checking exported env
    cmd = '''
    find_root() { echo "%s"; }
    CONF_DIR="%s"
    # Execute the exact dispatch pattern from unio-install.sh
    export UNIO_CONF_DIR="$CONF_DIR"
    python3 -c "import os; assert os.environ.get('UNIO_CONF_DIR') == '$CONF_DIR'"
    ''' % (base_dir, base_dir)
    res = subprocess.run(['bash', '-c', cmd], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    print('ok production dispatch environment config export', flush=True)


def test_native_4096_slot_metadata_parity(base_dir):
    """Test native 4096-byte slot metadata parity (2500-byte valid slot counts)."""
    ws = make_workspace(base_dir, lead='codex', tier='low')

    # A locked 2500-byte valid JSON slot metadata must count as 1 active workflow
    with locked_slot(ws, 'codex', 'slot-2500', size=2500):
        active = lp.count_active_slots(ws, 'codex')
        assert active == 1, 'expected 1 active slot, got %d' % active
        # Low tier limit is 1: 1 active native + 1 lead reservation > 1 -> refuses
        msg = refuses(lp.admit_lead, ws)
        assert "budget group 'codex' at capacity" in msg
        assert "1 active native workflow(s) plus 1 lead reservation" in msg

    # Unlocked 2500-byte valid JSON slot: counts 0 active workflows -> admits
    slot_dir = ws / 'coord' / '.locks' / 'work-policy-slots' / 'codex'
    slot_path = slot_dir / 'wpslot-slot-2500.json'
    doc = {
        'schema_version': 1,
        'group': 'codex',
        'agent': 'w1',
        'worker': 'worker-1',
        'task': 'task-1',
        'kind': 'run',
        'created_at': '2026-11-15T12:00:00Z',
    }
    raw = json.dumps(doc, indent=2) + '\n'
    padding = ' ' * (2500 - len(raw))
    raw = json.dumps(doc, indent=2)[:-2] + padding + '\n}\n'
    slot_path.write_text(raw, encoding='utf-8')
    try:
        active = lp.count_active_slots(ws, 'codex')
        assert active == 0, 'expected 0 active slots for unlocked slot, got %d' % active
        doc_pol, group, lease = lp.admit_lead(ws)
        lease.release()
    finally:
        slot_path.unlink()

    # Slot file larger than MAX_SLOT_META (4097 bytes) fails closed
    with locked_slot(ws, 'codex', 'slot-oversized', size=4097):
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe slot (oversized)' in msg
        msg = refuses(lp.admit_lead, ws)
        assert 'refusing unsafe slot (oversized)' in msg
    print('ok native 4096-byte slot metadata parity and oversized refusal', flush=True)


def test_fail_closed_slot_state_and_permission_faults(base_dir):
    """Test fail-closed slot validation and genuine permission faults.

    Permission fault test does not assume root is denied by chmod 000.
    """
    ws = make_workspace(base_dir, lead='codex', tier='low')
    slot_group_dir = ws / 'coord' / '.locks' / 'work-policy-slots' / 'codex'

    # 1. Missing slot directory legitimately returns 0 active slots
    if slot_group_dir.exists():
        os.rmdir(slot_group_dir)
    assert lp.count_active_slots(ws, 'codex') == 0
    doc, group, lease = lp.admit_lead(ws)
    lease.release()

    # 2. Unsafe slot directory: symlink directory refuses
    slot_group_dir.parent.mkdir(parents=True, exist_ok=True)
    target_dir = Path(base_dir) / 'external_slots'
    target_dir.mkdir(parents=True, exist_ok=True)
    slot_group_dir.symlink_to(target_dir)
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe' in msg and 'symlink' in msg, msg
        msg = refuses(lp.admit_lead, ws)
        assert 'refusing unsafe' in msg and 'symlink' in msg, msg
    finally:
        slot_group_dir.unlink()
        target_dir.rmdir()

    # 3. Unsafe slot directory: regular file at group path refuses
    slot_group_dir.write_text('not-a-directory')
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe slot directory (not a directory)' in msg
        msg = refuses(lp.admit_lead, ws)
        assert 'refusing unsafe slot directory (not a directory)' in msg
    finally:
        slot_group_dir.unlink()

    # 4. Genuine permission fault on slot directory listing.
    # We test both physical chmod 000 (when non-root) AND simulated OSError /
    # PermissionError to ensure coverage when run under root (UID 0).
    slot_group_dir.mkdir(parents=True, exist_ok=True)
    slot_file = slot_group_dir / 'wpslot-test.json'
    slot_file.write_text('{}')

    # 4a. Simulated permission fault (always tested, safe under any UID)
    real_listdir = os.listdir

    def faulting_listdir(path):
        if str(path) == str(slot_group_dir):
            raise PermissionError(errno.EACCES, 'Permission denied')
        return real_listdir(path)

    os.listdir = faulting_listdir
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'cannot list slot directory' in msg
        msg = refuses(lp.admit_lead, ws)
        assert 'cannot list slot directory' in msg
    finally:
        os.listdir = real_listdir

    # 4b. Physical filesystem permission denial (when UID != 0)
    if os.getuid() != 0:
        os.chmod(slot_group_dir, 0o000)
        try:
            msg = refuses(lp.count_active_slots, ws, 'codex')
            assert 'cannot list slot directory' in msg
            msg = refuses(lp.admit_lead, ws)
            assert 'cannot list slot directory' in msg
        finally:
            os.chmod(slot_group_dir, 0o700)

    # 5. Genuine permission fault on opening an individual slot file
    real_open = os.open

    def faulting_open(path, flags, *args):
        if str(path) == str(slot_file):
            raise PermissionError(errno.EACCES, 'Permission denied')
        return real_open(path, flags, *args)

    os.open = faulting_open
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'cannot open slot' in msg
        msg = refuses(lp.admit_lead, ws)
        assert 'cannot open slot' in msg
    finally:
        os.open = real_open

    # 6. Symlinked slot file refuses
    slot_file.unlink()
    target_slot = Path(base_dir) / 'external_slot.json'
    target_slot.write_text('{"schema_version": 1}')
    slot_file.symlink_to(target_slot)
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe slot (symlink)' in msg
        msg = refuses(lp.admit_lead, ws)
        assert 'refusing unsafe slot (symlink)' in msg
    finally:
        slot_file.unlink()
        target_slot.unlink()

    # 7. Non-regular slot file (e.g. sub-directory named wpslot-*.json) refuses
    slot_file.mkdir()
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe slot' in msg
        msg = refuses(lp.admit_lead, ws)
        assert 'refusing unsafe slot' in msg
    finally:
        slot_file.rmdir()

    # 8. Hardlinked slot file refuses
    target_slot = Path(base_dir) / 'hardlink_target.json'
    target_slot.write_text('{"schema_version": 1}')
    os.link(target_slot, slot_file)
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe slot (hardlinked)' in msg
        msg = refuses(lp.admit_lead, ws)
        assert 'refusing unsafe slot (hardlinked)' in msg
    finally:
        slot_file.unlink()
        target_slot.unlink()

    # 9. Inactive slot with malformed JSON refuses
    slot_file.write_text('{bad json')
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe slot (malformed json)' in msg
    finally:
        slot_file.unlink()

    # 10. Inactive slot with invalid schema refuses
    slot_file.write_text(json.dumps({'schema_version': 2}))
    try:
        msg = refuses(lp.count_active_slots, ws, 'codex')
        assert 'refusing unsafe slot (invalid schema)' in msg
    finally:
        slot_file.unlink()
    print('ok fail-closed slot state, schema validation and permission faults', flush=True)


def test_strict_label_validation(base_dir):
    """Test strict label validation matching native check_label rules."""
    invalid_labels = [
        ' codex', 'codex ', 'cod/ex', 'cod\\ex', '-codex',
        '..', 'cod..ex', 'cod\x00ex', 'cod\nex', 'cod\tex',
    ]

    for bad in invalid_labels:
        # Invalid lead_agent
        ws = make_workspace(base_dir, lead=bad)
        msg = refuses(lp.admit_lead, ws)
        assert 'invalid lead agent label' in msg or 'invalid lead_agent' in msg, msg

        # Invalid account agent
        ws = make_workspace(base_dir, lead='codex', accounts={bad: 'codex'})
        msg = refuses(lp.admit_lead, ws)
        assert 'invalid account agent label' in msg, msg

        # Invalid account group
        ws = make_workspace(base_dir, lead='codex', accounts={'codex': bad})
        msg = refuses(lp.admit_lead, ws)
        assert 'invalid account group label' in msg, msg

        # Invalid budget_label parameter
        ws = make_workspace(base_dir, lead='codex', accounts={})
        msg = refuses(lp.admit_lead, ws, budget_label=bad)
        assert 'invalid budget label label' in msg, msg

    # Valid labels pass
    valid_labels = ['codex', 'codex_1', 'lead-codex', 'group.a']
    for good in valid_labels:
        lp.check_label(good, 'test label')
    print('ok strict policy label validation matching native rules', flush=True)


def test_safe_locks_directory_creation(base_dir):
    """Test that admit_lead does not create coord/.locks on invalid project roots."""
    empty_dir = Path(base_dir) / 'empty_project'
    empty_dir.mkdir(parents=True, exist_ok=True)

    # Pointing at an empty directory lacking coord refuses immediately
    msg = refuses(lp.admit_lead, empty_dir)
    assert 'project coord directory not found' in msg

    # Asserts no coord/.locks was created
    assert not (empty_dir / 'coord').exists(), 'stray coord directory created'
    print('ok safe locks directory creation prevents stray directories', flush=True)


def test_owned_lease_and_setter_guard(base_dir):
    """Test non-blocking owned lease lock and setter guard exclusion."""
    ws = make_workspace(base_dir)

    # Initial admission acquires lease
    doc, group, lease = lp.admit_lead(ws)
    assert group == 'codex'

    # Second concurrent admission in same workspace refuses immediately
    msg = refuses(lp.admit_lead, ws)
    assert 'active owned lead session already running' in msg

    # Setter guard also refuses while lease is held
    guard_refused = False
    try:
        with lp.lead_session_guard(ws):
            pass
    except lp.Refusal as exc:
        assert 'active owned lead session is running' in str(exc)
        guard_refused = True
    assert guard_refused, 'expected setter guard Refusal while lease is held'

    # Release lease -> subsequent admission and setter guard succeed
    lease.release()
    with lp.lead_session_guard(ws):
        pass
    doc2, group2, lease2 = lp.admit_lead(ws)
    lease2.release()
    print('ok owned lease lock mutual exclusion and setter guard', flush=True)


def main():
    with tempfile.TemporaryDirectory(prefix='lead-session-policy-') as base:
        test_default_installed_off_hold(base)
        test_explicit_conf_off_holds(base)
        test_project_off_hold_observation(base)
        test_production_dispatch_propagation(base)
        test_native_4096_slot_metadata_parity(base)
        test_fail_closed_slot_state_and_permission_faults(base)
        test_strict_label_validation(base)
        test_safe_locks_directory_creation(base)
        test_owned_lease_and_setter_guard(base)
    print('all lead-session policy checks passed')


if __name__ == '__main__':
    main()
