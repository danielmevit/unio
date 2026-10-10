#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Local fleet observation: bounded, strict, read-only.

The dispatcher passes the installed Unio runner path and the selected physical
project root. The helper calls only fixed read-only runner argv with cwd at
that root and never a shell. One whole-observation deadline is shared fairly
across the inputs so one hanging source cannot starve the later healthy ones.
Every child runs in its own process group which is always stopped and reaped,
including output-closing children and descendants. Only bounded allowlisted
fields reach the report; raw stderr, configured commands and identity fields
never do. Missing, stale, malformed, timed-out or unsupported inputs stay
unknown; this observes, it never dispatches, refreshes or benches.
"""

import argparse
import datetime
import json
import math
import os
import re
import select
import signal
import subprocess
import sys
import time

SCHEMA_VERSION = 1
CAP_BYTES = 256 * 1024
GRACE_SECONDS = 0.5
POLL_SECONDS = 0.1
READ_CHUNK = 65536
MAX_TEXT = 64
MAX_ENTRIES = 64
MAX_WINDOWS = 16
MAX_BUCKETS = 16
MAX_WINDOW_MINUTES = 366 * 24 * 60
MAX_AGE_SECONDS = 366 * 24 * 3600
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')

MODES = ('yolo', 'medium', 'safe')
TIERS = ('low', 'medium', 'high')
SOURCE_STATES = ('ok', 'timeout', 'malformed', 'overflow', 'error', 'launch_failed')
CAPACITY_STATES = ('ok', 'missing', 'invalid')
RECORD_STATES = ('recorded', 'unknown')
WINDOW_STATES = ('fresh', 'stale', 'expired', 'unknown')
FRESHNESS_STATES = ('fresh', 'stale', 'expired', 'unknown')
READINESS_STATES = ('fresh', 'stale', 'failed', 'unknown')
AUTH_STATES = ('signed_in', 'signed_out', 'unknown')
BUCKET_STATES = ('ok', 'unknown')
ENTRY_STATES = ('ok', 'unknown')

SOURCES = (
    ('policy', ('policy', '--json')),
    ('agents', ('agents', '--json')),
    ('capacity_manual', ('capacity', 'show', '--json')),
    ('capacity_codex', ('capacity', 'show', '--provider', 'codex', '--json')),
    ('readiness', ('readiness', 'show', '--json')),
)

REASON_TEXT = {
    'project_STOP': 'project STOP is set',
    'agent_off': 'agent is off',
    'binary_missing': 'agent binary not installed',
    'binary_unknown': 'agent binary presence unknown',
    'group_full': 'shared budget group is full',
    'policy_unavailable': 'policy unavailable, limits unknown',
}


def fail(message):
    sys.stderr.write('unio fleet: ' + message + '\n')
    raise SystemExit(2)


def is_int(value):
    # bool is a subclass of int; a boolean is never a valid integer here.
    return type(value) is int


def is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def is_label(value):
    return isinstance(value, str) and LABEL.fullmatch(value) is not None


def is_text(value):
    return isinstance(value, str) and 0 < len(value) <= MAX_TEXT


def is_percent(value):
    return is_number(value) and 0 <= value <= 100


def is_age(value):
    return value is None or (is_number(value) and 0 <= value <= MAX_AGE_SECONDS)


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
    roots and undecodable text all fail instead of becoming available state."""
    try:
        obj = json.loads(data.decode('utf-8'), object_pairs_hook=_unique_object,
                         parse_constant=_reject_constant)
    except Exception:
        return None
    if not isinstance(obj, dict) or not _finite(obj):
        return None
    return obj


def _stop_group(proc):
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except OSError:
        pass


def _drain(stream, data):
    """Bounded tail read after the group is dead; True when the cap is exceeded."""
    try:
        fd = stream.fileno()
    except (OSError, ValueError):
        return False
    deadline = time.monotonic() + GRACE_SECONDS
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return False
        try:
            ready, _, _ = select.select([fd], [], [], min(POLL_SECONDS, remaining))
        except (OSError, ValueError):
            return False
        if not ready:
            continue
        try:
            chunk = os.read(fd, READ_CHUNK)
        except OSError:
            return False
        if not chunk:
            return False
        data.extend(chunk)
        if len(data) > CAP_BYTES:
            return True


def observe(runner, root, argv, deadline):
    """Run one fixed runner argv under an owned process group.

    Combined stdout/stderr is collected streamingly and stops at the cap. The
    group is always stopped and reaped, even when the child exits first and
    descendants keep the pipes open; then only a short grace is waited, never
    the remaining deadline.
    """
    try:
        proc = subprocess.Popen(
            [runner] + list(argv), cwd=root, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True)
    except OSError:
        return None, 'launch_failed'
    data = bytearray()
    reason = None
    exited_at = None
    try:
        fd = proc.stdout.fileno()
        while True:
            limit = deadline
            if exited_at is not None:
                limit = min(limit, exited_at + GRACE_SECONDS)
            remaining = limit - time.monotonic()
            if remaining <= 0:
                if exited_at is None:
                    reason = 'timeout'
                break
            ready, _, _ = select.select([fd], [], [], min(POLL_SECONDS, remaining))
            if ready:
                chunk = os.read(fd, READ_CHUNK)
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > CAP_BYTES:
                    reason = 'overflow'
                    break
            elif proc.poll() is not None and exited_at is None:
                # The child itself finished; do not wait the rest of the
                # deadline for descendants that keep the pipes open.
                exited_at = time.monotonic()
    finally:
        _stop_group(proc)
        if reason != 'overflow' and _drain(proc.stdout, data):
            reason = 'overflow'
        try:
            proc.stdout.close()
        except OSError:
            pass
        proc.wait()
    if reason is not None:
        return None, reason
    obj = parse_strict(bytes(data))
    if obj is None:
        return None, 'error' if proc.returncode != 0 else 'malformed'
    return obj, None


def valid_policy(obj):
    """Strict policy view; wrong types (for example boolean schema numbers)
    make the whole source malformed instead of available state."""
    if not is_int(obj.get('schema_version')) or obj['schema_version'] != 1:
        return None
    mode, tier = obj.get('mode'), obj.get('tier')
    if mode not in MODES or tier not in TIERS:
        return None
    lead_agent, lead_group = obj.get('lead_agent'), obj.get('lead_group')
    if lead_agent is not None and not is_label(lead_agent):
        return None
    if lead_group is not None and not is_label(lead_group):
        return None
    accounts = obj.get('accounts')
    if not isinstance(accounts, dict) or len(accounts) > MAX_ENTRIES:
        return None
    for agent, group in accounts.items():
        if not is_label(agent) or not is_label(group):
            return None
    limit = obj.get('workflow_limit_per_group')
    if not is_int(limit) or not 1 <= limit <= 4:
        return None
    active = obj.get('active_with_lead')
    if not isinstance(active, dict) or len(active) > MAX_ENTRIES:
        return None
    for group, count in active.items():
        if not is_label(group) or not is_int(count) or not 0 <= count <= MAX_ENTRIES:
            return None
    return {'mode': mode, 'tier': tier, 'lead_agent': lead_agent,
            'lead_group': lead_group, 'accounts': accounts, 'limit': limit,
            'active_with_lead': active}


def valid_agents(obj):
    """Strict agents view; only binary presence and bench state are copied,
    never the configured command text or any other nested field."""
    if not is_int(obj.get('schema_version')) or obj['schema_version'] != 1:
        return None
    entries = obj.get('agents')
    if not isinstance(entries, list) or len(entries) > MAX_ENTRIES:
        return None
    agents = {}
    for entry in entries:
        if not isinstance(entry, dict) or not is_label(entry.get('name')):
            return None
        name = entry['name']
        if name in agents:
            return None
        binary, bench = entry.get('binary'), entry.get('bench')
        if not isinstance(binary, dict) or not isinstance(bench, dict):
            return None
        present, off = binary.get('present'), bench.get('off')
        if present is not None and not isinstance(present, bool):
            return None
        if not isinstance(off, bool):
            return None
        agents[name] = {'binary_present': present, 'bench_off': off}
    return agents


def _valid_manual_window(window):
    if not isinstance(window, dict) or window.get('source') != 'manual':
        return None
    status = window.get('status')
    if status not in WINDOW_STATES:
        return None
    observed, reset = window.get('observed_at'), window.get('reset_at')
    if observed is not None and not is_text(observed):
        return None
    if reset is not None and not is_text(reset):
        return None
    if not is_age(window.get('age_seconds')):
        return None
    last = window.get('last_reading_remaining_percent')
    usable = window.get('usable_remaining_percent')
    if not is_percent(last):
        return None
    if usable is not None and not is_percent(usable):
        return None
    # Stale, expired and unknown readings never become current capacity.
    if status != 'fresh':
        usable = None
    return {'source': 'manual', 'status': status, 'observed_at': observed,
            'age_seconds': window.get('age_seconds'), 'reset_at': reset,
            'last_reading_remaining_percent': last,
            'usable_remaining_percent': usable}


def valid_manual(obj):
    """Strict manual capacity view: groups.<name>.windows, never buckets."""
    if not is_int(obj.get('schema_version')) or obj['schema_version'] != 1:
        return None
    state = obj.get('state')
    if state not in CAPACITY_STATES:
        return None
    groups = obj.get('groups')
    if not isinstance(groups, dict) or len(groups) > MAX_ENTRIES:
        return None
    normalized = {}
    for group, view in groups.items():
        if not is_label(group) or not isinstance(view, dict):
            return None
        status = view.get('status')
        if status not in RECORD_STATES:
            return None
        windows = view.get('windows')
        if not isinstance(windows, dict) or len(windows) > MAX_WINDOWS:
            return None
        clean = {}
        for window, reading in windows.items():
            if not is_label(window):
                return None
            reading = _valid_manual_window(reading)
            if reading is None:
                return None
            clean[window] = reading
        normalized[group] = {'status': status, 'windows': clean}
    return {'state': state, 'groups': normalized}


def _valid_cached_window(window, historical):
    if not isinstance(window, dict):
        return None
    status = window.get('status')
    if status not in WINDOW_STATES:
        return None
    minutes = window.get('window_minutes')
    if not is_int(minutes) or not 1 <= minutes <= MAX_WINDOW_MINUTES:
        return None
    reset = window.get('reset_at')
    if reset is not None and not is_text(reset):
        return None
    last = window.get('last_reading_remaining_percent')
    if not is_percent(last):
        return None
    usable = window.get('usable_remaining_percent')
    if usable is not None and not is_percent(usable):
        return None
    if historical:
        # A last good reading is history: clearly labeled, never current.
        return {'status': 'historical', 'window_minutes': minutes,
                'reset_at': reset, 'last_reading_remaining_percent': last,
                'usable_remaining_percent': None}
    if status != 'fresh':
        usable = None
    return {'status': status, 'window_minutes': minutes, 'reset_at': reset,
            'last_reading_remaining_percent': last,
            'usable_remaining_percent': usable}


def _valid_cached_buckets(buckets, historical):
    if not isinstance(buckets, dict) or len(buckets) > MAX_BUCKETS:
        return None
    clean = {}
    for key, bucket in buckets.items():
        if not is_label(key) or not isinstance(bucket, dict):
            return None
        status = bucket.get('status')
        if status not in BUCKET_STATES:
            return None
        reason = bucket.get('reason')
        if reason is not None and not is_text(reason):
            return None
        windows = bucket.get('windows')
        if not isinstance(windows, dict) or len(windows) > MAX_WINDOWS:
            return None
        clean_windows = {}
        for name, window in windows.items():
            if not is_label(name):
                return None
            if window is not None:
                window = _valid_cached_window(window, historical)
                if window is None:
                    return None
            clean_windows[name] = window
        clean[key] = {'status': status, 'reason': reason, 'windows': clean_windows}
    return clean


def valid_cached(obj):
    """Strict cached Codex view: groups.<name>.buckets plus a historical
    last_good, normalized separately from the manual windows schema."""
    if not is_int(obj.get('schema_version')) or obj['schema_version'] != 1:
        return None
    if obj.get('provider') != 'codex':
        return None
    state = obj.get('state')
    if state not in CAPACITY_STATES:
        return None
    groups = obj.get('groups')
    if not isinstance(groups, dict) or len(groups) > MAX_ENTRIES:
        return None
    clean_groups = {}
    for group, entry in groups.items():
        if not is_label(group) or not isinstance(entry, dict):
            return None
        if entry.get('source') != 'codex':
            return None
        entry_state = entry.get('state')
        if entry_state not in ENTRY_STATES:
            return None
        reason = entry.get('reason')
        if reason is not None and not is_text(reason):
            return None
        observed = entry.get('observed_at')
        if observed is not None and not is_text(observed):
            return None
        if not is_age(entry.get('age_seconds')):
            return None
        freshness = entry.get('freshness')
        if freshness not in FRESHNESS_STATES:
            return None
        buckets = _valid_cached_buckets(entry.get('buckets'), historical=False)
        if buckets is None:
            return None
        last_good, clean_last = entry.get('last_good'), None
        if last_good is not None:
            if not isinstance(last_good, dict):
                return None
            if not is_text(last_good.get('observed_at')):
                return None
            if not is_age(last_good.get('age_seconds')):
                return None
            history = _valid_cached_buckets(last_good.get('buckets'), historical=True)
            if history is None:
                return None
            clean_last = {'historical': True, 'observed_at': last_good['observed_at'],
                          'age_seconds': last_good.get('age_seconds'), 'buckets': history}
        clean_groups[group] = {'state': entry_state, 'reason': reason,
                               'observed_at': observed,
                               'age_seconds': entry.get('age_seconds'),
                               'freshness': freshness, 'buckets': buckets,
                               'last_good': clean_last}
    return {'state': state, 'groups': clean_groups}


def valid_readiness(obj):
    """Strict readiness view: authentication, status and bounded timing only;
    the raw latest observation and identity fields are never copied."""
    if not is_int(obj.get('schema_version')) or obj['schema_version'] != 1:
        return None
    state = obj.get('state')
    if state not in CAPACITY_STATES:
        return None
    agents = obj.get('agents')
    if not isinstance(agents, dict) or len(agents) > MAX_ENTRIES:
        return None
    clean = {}
    for name, view in agents.items():
        if not is_label(name) or not isinstance(view, dict):
            return None
        status = view.get('status')
        if status not in READINESS_STATES:
            return None
        authentication = view.get('authentication')
        if authentication not in AUTH_STATES:
            return None
        source, observed = view.get('source'), view.get('observed_at')
        if source is not None and not is_text(source):
            return None
        if observed is not None and not is_text(observed):
            return None
        if not is_age(view.get('age_seconds')):
            return None
        # Authentication is only a fact on a fresh observation.
        if status != 'fresh':
            authentication = 'unknown'
        clean[name] = {'status': status, 'authentication': authentication,
                       'source': source, 'observed_at': observed,
                       'age_seconds': view.get('age_seconds')}
    return clean


VALIDATORS = {
    'policy': valid_policy,
    'agents': valid_agents,
    'capacity_manual': valid_manual,
    'capacity_codex': valid_cached,
    'readiness': valid_readiness,
}


def collect(runner, root, timeout):
    """Run every fixed input inside one whole-observation deadline.

    Each input receives an equal share of the time still left, so a hanging
    source consumes only its share and later healthy sources still run.
    """
    overall = time.monotonic() + timeout
    observed, statuses = {}, {}
    total = len(SOURCES)
    for index, (name, argv) in enumerate(SOURCES):
        left = overall - time.monotonic()
        if left <= 0:
            statuses[name] = 'timeout'
            continue
        share = left / (total - index)
        obj, reason = observe(runner, root, argv, time.monotonic() + share)
        if obj is None:
            statuses[name] = reason
            continue
        parsed = VALIDATORS[name](obj)
        if parsed is None:
            statuses[name] = 'malformed'
        else:
            observed[name] = parsed
            statuses[name] = 'ok'
    return observed, statuses


def admission(stop, meta, occupied, limit, policy_ok):
    blocked, unknown = [], []
    if stop:
        blocked.append('project_STOP')
    if meta['bench_off']:
        blocked.append('agent_off')
    if meta['binary_present'] is False:
        blocked.append('binary_missing')
    elif meta['binary_present'] is None:
        unknown.append('binary_unknown')
    if policy_ok:
        if occupied is not None and limit is not None and occupied >= limit:
            blocked.append('group_full')
    else:
        unknown.append('policy_unavailable')
    state = 'blocked' if blocked else ('unknown' if unknown else 'clear')
    return state, blocked + unknown


def build_report(root, timeout, stop, observed, statuses):
    policy = observed.get('policy')
    agents = observed.get('agents')
    manual = observed.get('capacity_manual')
    cached = observed.get('capacity_codex')
    readiness = observed.get('readiness')

    report = {
        'schema_version': SCHEMA_VERSION,
        'project': root,
        'checked_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'timeout_seconds': timeout,
        'stop': stop,
        'mode': policy['mode'] if policy else 'unknown',
        'tier': policy['tier'] if policy else 'unknown',
        'lead_agent': policy['lead_agent'] if policy else None,
        'lead_group': policy['lead_group'] if policy else None,
        'sources': {name: statuses[name] for name, _ in SOURCES},
        'groups': {},
    }
    groups = report['groups']

    def row(name):
        if name not in groups:
            groups[name] = {
                'limit': policy['limit'] if policy else None,
                # active_with_lead already counts the registered lead once.
                'occupied': policy['active_with_lead'].get(name, 0) if policy else None,
                'agents': {}, 'manual_allowance': None, 'cached_allowance': None,
            }
        return groups[name]

    if report['lead_group']:
        row(report['lead_group'])
    if agents:
        for name, meta in agents.items():
            group_name = policy['accounts'].get(name, name) if policy else name
            state, reasons = admission(stop, meta, row(group_name)['occupied'],
                                       row(group_name)['limit'], policy is not None)
            row(group_name)['agents'][name] = {
                'admission_state': state,
                'reasons': reasons,
                'binary_present': meta['binary_present'],
                'bench_off': meta['bench_off'],
                'dispatch_readiness': 'unknown',
                'cached_auth': readiness.get(name) if readiness else None,
            }
    if manual:
        for name, view in manual['groups'].items():
            row(name)['manual_allowance'] = {'state': manual['state'],
                                             'status': view['status'],
                                             'windows': view['windows']}
    if cached:
        for name, view in cached['groups'].items():
            row(name)['cached_allowance'] = view
    return report


def fmt_number(value):
    return '%g' % value


def fmt_percent(value):
    return '%g%%' % value


def group_line(name, row):
    if row['occupied'] is None or row['limit'] is None:
        return 'Group ' + name + ': occupied unknown (policy unavailable)'
    return 'Group {}: occupied {}/{}'.format(name, row['occupied'], row['limit'])


def manual_window_line(window, view):
    percent = fmt_percent(view['last_reading_remaining_percent'])
    if view['status'] == 'fresh':
        text = 'fresh, usable ' + percent
    elif view['status'] == 'expired':
        text = 'expired, last reading ' + percent + ' (past reset; not current)'
    elif view['status'] == 'stale':
        text = 'stale, last reading ' + percent + ' (not current)'
    else:
        text = 'unknown, last reading ' + percent + ' (not current)'
    if view['age_seconds'] is not None:
        text += ', {}s old'.format(fmt_number(view['age_seconds']))
    if view['reset_at']:
        text += ', resets at ' + view['reset_at']
    return window + ': ' + text


def cached_window_line(key, window, view):
    percent = fmt_percent(view['last_reading_remaining_percent'])
    if view['status'] == 'fresh':
        text = 'fresh, usable ' + percent
    elif view['status'] == 'historical':
        text = 'historical, ' + percent + ' (never current)'
    elif view['status'] == 'expired':
        text = 'expired, last reading ' + percent + ' (past reset; not current)'
    elif view['status'] == 'stale':
        text = 'stale, last reading ' + percent + ' (not current)'
    else:
        text = 'unknown, last reading ' + percent + ' (not current)'
    if view['reset_at']:
        text += ', resets at ' + view['reset_at']
    return '{} {}: {}'.format(key, window, text)


def allowance_lines(row):
    lines = []
    manual = row['manual_allowance']
    if manual is not None:
        if manual['status'] == 'recorded' and manual['windows']:
            lines.append('  Manual allowance: recorded')
            for window in sorted(manual['windows']):
                lines.append('    ' + manual_window_line(window, manual['windows'][window]))
        else:
            lines.append('  Manual allowance: no usable recorded reading')
    cached = row['cached_allowance']
    if cached is not None:
        detail = cached['freshness']
        if cached['age_seconds'] is not None:
            detail += ', {}s old'.format(fmt_number(cached['age_seconds']))
        lines.append('  Cached codex allowance: {} ({})'.format(cached['state'], detail))
        for key in sorted(cached['buckets']):
            bucket = cached['buckets'][key]
            for window in sorted(bucket['windows']):
                view = bucket['windows'][window]
                if view is None:
                    lines.append('    {} {}: unknown'.format(key, window))
                else:
                    lines.append('    ' + cached_window_line(key, window, view))
        last = cached['last_good']
        if last is not None:
            percents = [view['last_reading_remaining_percent']
                        for bucket in last['buckets'].values()
                        for view in bucket['windows'].values() if view is not None]
            shown = ', '.join(fmt_percent(value) for value in percents) if percents else 'unknown'
            lines.append('    last good (historical, never current): {} ({}s old)'.format(
                shown, fmt_number(last['age_seconds'])))
    return lines


def agent_lines(row):
    lines = []
    for name in sorted(row['agents']):
        agent = row['agents'][name]
        if agent['admission_state'] == 'clear':
            text = 'clear (all local checks clear; dispatch readiness unknown)'
        else:
            phrases = [REASON_TEXT.get(reason, reason) for reason in agent['reasons']]
            text = agent['admission_state'] + ' (' + '; '.join(phrases) + ')'
        auth = agent['cached_auth']
        if auth and auth['authentication'] != 'unknown':
            auth_text = 'auth: {} ({}, {}s old)'.format(
                auth['authentication'], auth['status'], fmt_number(auth['age_seconds']))
        elif auth:
            auth_text = 'auth: unknown ({})'.format(auth['status'])
        else:
            auth_text = 'auth: unknown'
        lines.append('  {}: {} | {}'.format(name, text, auth_text))
    return lines


def render_text(report):
    lines = []
    head = 'Project: ' + report['project']
    if report['stop']:
        head += '  [STOP active]'
    lines.append(head)
    summary = 'Mode: {} | Tier: {}'.format(report['mode'], report['tier'])
    if report['lead_agent'] is not None:
        summary += ' | Lead: ' + report['lead_agent']
        if report['lead_group'] is not None and report['lead_group'] != report['lead_agent']:
            summary += ' (group ' + report['lead_group'] + ')'
    lines.append(summary)
    failed = [name for name, status in report['sources'].items() if status != 'ok']
    if failed:
        lines.append('Unavailable local inputs (reported as unknown): ' + ', '.join(failed))
    for name in sorted(report['groups']):
        lines.append('')
        lines.append(group_line(name, report['groups'][name]))
        lines.extend(allowance_lines(report['groups'][name]))
        lines.extend(agent_lines(report['groups'][name]))
    lines.append('')
    lines.append('Cached local readings only, never a live provider state; external sessions')
    lines.append('outside this workspace are uncounted. Clear local checks do not claim provider')
    lines.append('readiness: dispatch readiness stays unknown. Observation only; nothing ran.')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog='unio fleet', allow_abbrev=False,
        description='Local read-only fleet observation: agents, shared budget '
                    'groups, STOP facts and cached readings.')
    parser.add_argument('runner', help='installed Unio runner path (from the dispatcher)')
    parser.add_argument('--project', metavar='PATH',
                        help='explicit physical project root (coord/ and wt/)')
    parser.add_argument('--json', action='store_true',
                        help='write exactly one schema-1 JSON object')
    parser.add_argument('--timeout', type=int, metavar='SECONDS', default=10,
                        help='whole observation deadline, 1..60 seconds (default 10)')
    args = parser.parse_args(argv)
    if not 1 <= args.timeout <= 60:
        fail('--timeout must be 1..60 seconds')
    if not args.project:
        fail('no project selected; pass --project PATH')
    root = os.path.realpath(os.path.abspath(args.project))
    for required in ('coord', 'wt'):
        if not os.path.isdir(os.path.join(root, required)):
            fail('no Unio workspace (coord/ and wt/) under: ' + args.project)
    try:
        stop = os.path.exists(os.path.join(root, 'coord', 'STOP'))
    except OSError:
        stop = False
    observed, statuses = collect(args.runner, root, args.timeout)
    report = build_report(root, args.timeout, stop, observed, statuses)
    if args.json:
        sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=True,
                                    allow_nan=False) + '\n')
    else:
        sys.stdout.write(render_text(report) + '\n')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write('unio fleet: interrupted\n')
        raise SystemExit(130)
