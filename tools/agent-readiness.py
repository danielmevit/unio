#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Explicit non-generating Claude authentication observation; show is local-only."""
import argparse
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bridge.readiness import NATIVE_LABELS, ReadinessStore, ReadinessError

PINNED_VERSION = '2.1.296 (Claude Code)'


class NativeFailure(Exception):
    def __init__(self, reason):
        self.reason = reason


def _native(argv, *, timeout, limit):
    """Read a fixed native command with bounded aggregate output and group cleanup."""
    try:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, start_new_session=True)
    except OSError:
        raise NativeFailure('launch_failed') from None
    selector = selectors.DefaultSelector()
    output = bytearray()
    total = 0
    deadline = time.monotonic() + timeout
    try:
        for pipe in (child.stdout, child.stderr):
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ)
        while selector.get_map() or child.poll() is None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise NativeFailure('timeout')
            if not selector.get_map():
                time.sleep(min(0.025, remaining))
                continue
            for key, _ in selector.select(min(0.1, remaining)):
                try:
                    chunk = os.read(key.fd, min(8192, limit + 1 - total))
                except BlockingIOError:
                    continue
                if not chunk:
                    selector.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > limit:
                    raise NativeFailure('output_overflow')
                if key.fileobj is child.stdout:
                    output.extend(chunk)
        return subprocess.CompletedProcess(argv, child.returncode, output.decode('utf-8'), None)
    finally:
        selector.close()
        # Descendants may keep pipes open after their parent exits. This group
        # belongs to this metadata observation, never to an AI worker session.
        for signum in (signal.SIGTERM, signal.SIGKILL):
            try:
                os.killpg(child.pid, signum)
            except ProcessLookupError:
                pass
        child.stdout.close()
        child.stderr.close()
        try:
            child.wait(timeout=1)
        except subprocess.TimeoutExpired:
            raise NativeFailure('timeout') from None


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate key')
        result[key] = value
    return result


def _constant(_):
    raise ValueError('nonfinite number')


def run_refresh(project_dir, now=None):
    store = ReadinessStore(project_dir)
    now = datetime.now(timezone.utc) if now is None else now
    reason = None
    try:
        version = _native(['claude', '--version'], timeout=5, limit=256)
        if version.returncode != 0:
            reason = 'version_failed'
        elif version.stdout.strip() != PINNED_VERSION:
            reason = 'unsupported_version'
        if reason is None:
            proc = _native(['claude', 'auth', 'status', '--json'], timeout=10, limit=65536)
            if proc.returncode != 0:
                reason = 'native_failed'
            else:
                data = json.loads(proc.stdout, object_pairs_hook=_strict_object, parse_constant=_constant)
                if not isinstance(data, dict) or type(data.get('loggedIn')) is not bool:
                    raise ValueError('invalid status')
                for name, allowed in NATIVE_LABELS.items():
                    if name in data and (not isinstance(data[name], str) or data[name] not in allowed):
                        raise ValueError('invalid label')
                # Unknown fields, including account names and credentials, are
                # discarded in memory and never printed or written.
                store.record_good('claude', 'native', data['loggedIn'],
                                  auth_method=data.get('authMethod'),
                                  api_provider=data.get('apiProvider'),
                                  subscription_type=data.get('subscriptionType'), now=now)
                return 0
    except ReadinessError:
        raise
    except NativeFailure as error:
        reason = error.reason
    except subprocess.TimeoutExpired:
        reason = 'timeout'
    except (ValueError, UnicodeError, RecursionError):
        reason = 'invalid_status'
    store.record_failure('claude', 'native', reason, now=now)
    return 1


def run_show(project_dir, agent=None, output_json=False, now=None):
    view = ReadinessStore(project_dir).show(agent=agent, now=now)
    if output_json:
        print(json.dumps(view, indent=2))
    else:
        print('Authentication observation only; capacity and dispatch readiness remain Unknown.')
        for name, data in view['agents'].items():
            print(f"{name}: authentication={data['authentication']}; observation={data['status']}")
            if 'observed_at' in data:
                print(f"  source={data['source']}; observed={data['observed_at']}; age={data['age_seconds']}s")
            if 'error' in data.get('latest_observation', {}):
                print('  reason=' + data['latest_observation']['error'])
            if 'last_good_observation' in data and data['status'] != 'fresh':
                old = data['last_good_observation']
                print(f"  historical only: loggedIn={old['loggedIn']}; observed={old['observed_at']}")
    return view


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project', required=True, help='Unio workspace directory')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('refresh').add_argument('agent', choices=['claude'])
    show = commands.add_parser('show')
    show.add_argument('--agent')
    show.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'refresh':
            code = run_refresh(args.project)
            run_show(args.project, agent='claude', output_json=True)
            return code
        view = run_show(args.project, agent=args.agent, output_json=args.json)
        return 2 if view['state'] == 'invalid' else 0
    except (ReadinessError, OSError):
        print('agent-readiness: unsafe, unavailable or busy local storage; no fresh reading claimed', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
