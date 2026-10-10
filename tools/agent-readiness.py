#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Agent authentication readiness tool."""
import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone

# Add the parent directory to sys.path to allow importing bridge
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from bridge.readiness import ReadinessStore, ReadinessError

def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result

def run_refresh(project_dir, now=None):
    store = ReadinessStore(project_dir)
    if now is None:
        now = datetime.now(timezone.utc)
    
    # Bounded non-generating version check
    try:
        version_proc = subprocess.run(
            ['claude', '--version'], 
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, 
            timeout=5, text=True
        )
        if version_proc.returncode != 0:
            store.record_failure('claude', 'native', 'version check failed', now=now)
            return
        version_out = version_proc.stdout.strip()
        # Pinning the actual installed CLI version checked during this task
        if not version_out.startswith('2.1.295') and not version_out.startswith('2.1.296'):
            store.record_failure('claude', 'native', f'unsupported version: {version_out}', now=now)
            return
    except Exception as e:
        store.record_failure('claude', 'native', f'version check error: {e}', now=now)
        return
        
    try:
        proc = subprocess.run(
            ['claude', 'auth', 'status', '--json'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=10, text=True
        )
        if proc.returncode != 0:
            store.record_failure('claude', 'native', f'nonzero exit: {proc.returncode}', now=now)
            return
        
        output = proc.stdout.strip()
        if not output:
            store.record_failure('claude', 'native', 'empty output', now=now)
            return
            
        if len(output.encode('utf-8')) > 65536:
            store.record_failure('claude', 'native', 'oversized JSON', now=now)
            return
            
        data = json.loads(output, object_pairs_hook=_strict_object)
        
        if not isinstance(data, dict):
            store.record_failure('claude', 'native', 'unexpected type', now=now)
            return
            
        if 'loggedIn' not in data:
            store.record_failure('claude', 'native', 'missing required fields', now=now)
            return
            
        if type(data['loggedIn']) is not bool:
            store.record_failure('claude', 'native', 'unexpected fields/types', now=now)
            return
            
        store.record_good(
            'claude',
            'native',
            data['loggedIn'],
            auth_method=data.get('authMethod'),
            api_provider=data.get('apiProvider'),
            subscription_type=data.get('subscriptionType'),
            now=now
        )
            
    except ValueError as e:
        store.record_failure('claude', 'native', f'malformed/duplicate JSON: {e}', now=now)
    except subprocess.TimeoutExpired:
        store.record_failure('claude', 'native', 'timeout', now=now)
    except Exception as e:
        store.record_failure('claude', 'native', f'unexpected error: {e}', now=now)

def run_show(project_dir, agent=None, output_json=False, now=None):
    store = ReadinessStore(project_dir)
    view = store.show(agent=agent, now=now)
    if output_json:
        print(json.dumps(view, indent=2))
    else:
        for name, data in view['agents'].items():
            print(f"Agent: {name}")
            print(f"  Status: {data['status']}")
            if data['status'] == 'unknown':
                continue
            if 'latest_observation' in data:
                latest = data['latest_observation']
                if 'error' in latest:
                    print(f"  Error: {latest['error']}")
                else:
                    print(f"  Logged In: {latest.get('loggedIn')}")
                    if 'authMethod' in latest: print(f"  Auth Method: {latest['authMethod']}")
                    if 'apiProvider' in latest: print(f"  API Provider: {latest['apiProvider']}")
                    if 'subscriptionType' in latest: print(f"  Subscription Type: {latest['subscriptionType']}")
            print(f"  Observed At: {data.get('observed_at')}")
            print(f"  Age: {data.get('age_seconds')} seconds")
            if 'last_good_observation' in data:
                lg = data['last_good_observation']
                print(f"  Last Good Logged In: {lg.get('loggedIn')} at {lg.get('observed_at')}")
            print()

def main():
    parser = argparse.ArgumentParser(description='Agent authentication readiness tool.')
    parser.add_argument('--project', required=True, help='WORKSPACE project directory')
    subparsers = parser.add_subparsers(dest='command', required=True)
    
    refresh_parser = subparsers.add_parser('refresh')
    refresh_parser.add_argument('agent', choices=['claude'], help='Agent to refresh')
    
    show_parser = subparsers.add_parser('show')
    show_parser.add_argument('--agent', help='Agent name to show')
    show_parser.add_argument('--json', action='store_true', help='Output in JSON format')
    
    args = parser.add_args = parser.parse_args()
    
    try:
        if args.command == 'refresh':
            if args.agent == 'claude':
                run_refresh(args.project)
        elif args.command == 'show':
            run_show(args.project, agent=args.agent, output_json=args.json)
    except ReadinessError as e:
        sys.exit(f"ReadinessError: {e}")
    except Exception as e:
        sys.exit(f"Error: {e}")

if __name__ == '__main__':
    main()
