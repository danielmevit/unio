#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Read-only effort capability boundary. No managed Source backend yet."""
import argparse
import datetime
import json
from pathlib import Path
import re

LEVELS = ('low', 'medium', 'high', 'xhigh')
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z')
REASON = ('No owned managed Codex app-server Source backend is installed. '
          'Legacy exec and unmanaged sessions cannot be attached. '
          'No effort request was queued or sent; the current turn is unchanged.')


def inspect(project, worker, effort=None):
    """Do not infer a live task, slot, model or effort from files/process names."""
    if not ID.fullmatch(worker):
        raise ValueError('invalid worker identifier')
    root = Path(project)
    if not root.is_absolute() or root.is_symlink():
        raise ValueError('project must be a physical absolute directory')
    for path in (root, root / 'coord', root / 'wt', root / 'wt' / worker):
        if path.is_symlink() or not path.is_dir():
            raise ValueError('missing or unsafe project/worker directory')
    if root.resolve() != root:
        raise ValueError('project path contains replaced or nonphysical components')
    if effort is not None and effort not in LEVELS:
        raise ValueError('supported request levels: low medium high xhigh')
    return {
        'schema_version': 1,
        'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'worker': worker,
        'operation': 'request' if effort is not None else 'get',
        'state': 'unsupported',
        'requested_effort': effort,
        'native_acknowledged': False,
        'configured_effort': None,
        'pending_next_supported_turn': False,
        'effective_effort': 'Unknown',
        'model': 'Unknown',
        'task': 'Unknown',
        'managed_worker_identity': 'Unknown',
        'subscription_route': 'Unknown',
        'cli_version': 'Unknown',
        'reason': REASON,
        'application_boundary': 'subsequent turns only (native schema capability; backend unavailable)',
    }


def main():
    parser = argparse.ArgumentParser(description='Inspect/request worker reasoning effort. '
        'Bounded first slice: requests are unsupported until an owned managed Source backend exists. '
        'No provider calls, restart, interrupt or new turn. Effective effort stays Unknown.')
    parser.add_argument('--project', required=True)
    parser.add_argument('worker')
    parser.add_argument('effort', nargs='?', choices=LEVELS)
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    try:
        result = inspect(args.project, args.worker, args.effort)
    except (ValueError, OSError) as exc:
        parser.exit(2, 'unio worker-effort: ' + str(exc) + '\n')
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f'{args.worker}: unsupported; effective effort Unknown')
        print(result['reason'])
        print(result['application_boundary'])
    return 2 if args.effort is not None else 0


if __name__ == '__main__':
    raise SystemExit(main())
