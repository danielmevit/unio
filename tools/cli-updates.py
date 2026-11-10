#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms: NOTICE.
"""Machine-level AI CLI version facts and explicit, held-safe updates.

Installed by tools/embed-cli-updates.py as $CONF_DIR/lib/cli-updates.py and
driven by `unio update clis`. Standard library only; no shell, no eval.

Safety contract (frozen 2026-11-10):
- `check` records facts only: installed version, latest-version metadata,
  cache age, install method, busy/lead holds, support and compatibility
  Unknown. A check NEVER calls an installing updater. The only tool
  commands it may run are a plain read-only `--version` and grok's
  documented read-only `update --check --json`. Nothing from agents.conf,
  task files, reports, cache text or downloaded URLs is ever executed or
  evaluated; every subprocess is a fixed argv array from the table below.
- `update` is the explicit update request, but until a shared native
  maintenance/admission lease (unio run/review <-> updater) is implemented,
  it REFUSES to install for EVERY present target with the explicit reason
  `maintenance_not_implemented` plus that CLI's frozen manual plan. No
  updater or installing probe is ever constructed or executed by this
  module — regardless of STOP, process state, cache content, flags or
  environment (there is deliberately no bypass). The frozen updater
  commands in the table below are safe manual plans only, never argv this
  code runs. Busy/lead facts reported by `check` stay honest observations,
  never permission and never idle confirmation. Updating is not claimed
  complete: automatic installation is deferred (docs/CLI-UPDATES.md).
  Updates runDangerously never touch route/adapter version guards or pins:
  compatibility stays Unknown until proven by real use.
- `startup` prints one read-only freshness line for human entry points
  (doctor, resume). Missing/fresh caches cause no network; a stale cache
  (default 24 h) spawns one bounded background refresh (own lock, hard
  deadline, no stdout). The background refresh never executes any CLI
  binary or updater — only filesystem metadata and official metadata URLs.
  Corrupt/missing cache means Unknown, never authorization to run
  anything. No secrets or account identifiers are ever stored or read.

Routes and commands below were verified read-only on the host on
2026-11-10 (agy 1.5.4, vibe 3.1.1 via `uv tool list`, grok 1.0.77,
copilot 1.0.108, opencode 1.19.5, claude 2.1.322 npm, codex 0.167.0).
That is a dated observation, not a pin on any version.

Env: UNIO_CONF_DIR-dir default is UNIO_CONF_DIR then ~/.config/unio;
UNIO_CLI_UPDATES_MAX_AGE (seconds, default 86400);
UNIO_CLI_UPDATES_TIMEOUT (metadata seconds per request, default 10);
UNIO_CLI_UPDATES_DEADLINE (startup refresh total seconds, default 45);
UNIO_CLI_UPDATES_OFF=1 disables startup awareness entirely (offline/tests);
UNIO_CLI_UPDATES_OFFLINE=1 forbids all network metadata fetches honestly.
"""
import argparse
import errno
import fcntl
import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
SOURCE_LABEL = 'cli-updates'
UA = 'unio-cli-updates/1 (+https://github.com/danielmevit/unio)'
VERSION_RE = re.compile(r'(\d+\.\d+(?:\.\d+)*(?:[-+][0-9A-Za-z.]+)?)')
DELETED_SUFFIX = ' (deleted)'
# The cache is data, never a command: bytes are bounded BEFORE any read
# (fstat) and again during the read (stat/read race), and nothing that is
# not a small regular file is ever parsed.
CACHE_MAX_BYTES = 262144

# One entry per recognized route. update_argv exists only to build the
# frozen MANUAL plan a refusal prints; no code path executes it (installs
# are refused with maintenance_not_implemented until a shared native
# maintenance lease exists). version_argv and the grok check argv are
# read-only. latest is the official metadata strategy:
# (kind, repo/package) resolved only when the detected install method
# makes that source authoritative, otherwise latest stays Unknown.
ROUTES = {
    'antigravity': {
        'name': 'antigravity', 'group': 'google',
        'aliases': ('antigravity', 'agy'), 'binary': 'agy',
        'version_argv': ('--version',),
        'update_argv': ('update',), 'update_label': 'agy update',
        'update_support': 'native', 'latest': ('github', 'google-antigravity/antigravity-cli'),
        'latest_any_method': True,
    },
    'vibe': {
        'name': 'vibe', 'group': 'mistral',
        'aliases': ('vibe', 'mistral-vibe', 'mistral-vibe-cli'), 'binary': 'vibe',
        'version_argv': ('--version',),
        'update_argv': None,  # resolved at update time: uv tool upgrade mistral-vibe
        'update_label': 'uv tool upgrade mistral-vibe (verified uv-managed install only)',
        'update_support': 'uv-tool', 'latest': ('pypi', 'mistral-vibe'),
        'latest_any_method': False,
    },
    'grok': {
        'name': 'grok', 'group': 'xai',
        'aliases': ('grok',), 'binary': 'grok',
        'version_argv': ('--version',),
        'check_argv': ('update', '--check', '--json'),  # documented read-only
        'update_argv': ('update', '--stable'), 'update_label': 'grok update --stable',
        'update_support': 'native', 'latest': ('grok-check', ''),
        'latest_any_method': True,
    },
    'copilot': {
        'name': 'copilot', 'group': 'github',
        'aliases': ('copilot', 'github-copilot', 'copilot-cli'), 'binary': 'copilot',
        'version_argv': ('--version',),
        'update_argv': ('update', 'stable'), 'update_label': 'copilot update stable',
        'update_support': 'native', 'latest': ('npm', '@github/copilot'),
        'latest_any_method': False,
    },
    'opencode': {
        'name': 'opencode', 'group': 'zen',
        'aliases': ('opencode', 'open-code', 'opencode-ai'), 'binary': 'opencode',
        'version_argv': ('--version',),
        'update_argv': ('upgrade',),  # never --major: that is a separate migration
        'update_label': 'opencode upgrade (no --major)',
        'update_support': 'native', 'latest': ('npm', 'opencode-ai'),
        'latest_any_method': False,
    },
    'claude': {
        'name': 'claude', 'group': 'anthropic',
        'aliases': ('claude', 'claude-code'), 'binary': 'claude',
        'version_argv': ('--version',),
        'update_argv': None, 'update_label': 'manual (claude update; unio only checks)',
        'update_support': 'check-only', 'latest': ('npm', '@anthropic-ai/claude-code'),
        'latest_any_method': False,
    },
    'codex': {
        'name': 'codex', 'group': 'openai',
        'aliases': ('codex', 'codex-cli'), 'binary': 'codex',
        'version_argv': ('--version',),
        'update_argv': None, 'update_label': 'manual (lead-only route; unio only checks)',
        'update_support': 'check-only', 'latest': ('npm', '@openai/codex'),
        'latest_any_method': False,
    },
}
ROUTE_ORDER = ('antigravity', 'vibe', 'grok', 'copilot', 'opencode', 'claude', 'codex')
ALIAS_TO_ROUTE = {alias: route['name'] for route in ROUTES.values() for alias in route['aliases']}
# Path facts used to label an install method honestly. A label only states
# where the resolved executable lives; it never authorizes an update.
METHOD_MARKERS = (
    ('/node_modules/', 'npm'),
    ('/.grok/', 'grok-managed'),
    ('/.codex/packages/', 'codex-standalone'),
    ('/.opencode/', 'opencode-native'),
    ('/uv/tools/mistral-vibe/', 'uv-tool'),
)
UV_TOOL_PACKAGE = 'mistral-vibe'
UV_TOOL_ROOT_MARKER = '/uv/tools/mistral-vibe/'
BUSY_NOTE = ('busy facts are observations, never permission and never idle proof: '
             'detection covers this project (worker locks, STOP) and same-uid native '
             'processes with exact validated executable identity (a verified uv-managed '
             'vibe covers both its bin launcher and its site-packages native binary); a '
             'nonzero count of unidentifiable same-uid processes means Unknown. Other '
             'users, other hosts and cross-workspace unmanaged sessions stay unknown; '
             'unio refuses installs regardless (docs/CLI-UPDATES.md)')


class UsageError(Exception):
    pass


class NetworkDisabled(Exception):
    pass


def now():
    return datetime.now(timezone.utc)


def iso(dt=None):
    return (dt or now()).replace(microsecond=0).isoformat()


def parse_iso(text):
    try:
        stamp = datetime.fromisoformat(text)
        if stamp.tzinfo is None:
            raise ValueError('naive timestamp')
        return stamp
    except (TypeError, ValueError):
        return None


def age_seconds(text):
    stamp = parse_iso(text) if isinstance(text, str) else None
    if stamp is None:
        return None
    return max(0.0, (now() - stamp).total_seconds())


def env_int(name, default, low, high):
    raw = os.environ.get(name, '')
    if not raw:
        return default
    try:
        value = int(raw, 10)
    except ValueError:
        return default
    return max(low, min(high, value))


def opt_off():
    return os.environ.get('UNIO_CLI_UPDATES_OFF', '0') == '1'


def opt_offline():
    return os.environ.get('UNIO_CLI_UPDATES_OFFLINE', '0') == '1'


def state_dir(conf):
    return Path(conf) / 'cli-updates'


def cache_path(conf):
    return state_dir(conf) / 'cache.json'


def _reject_nonfinite_constant(name):
    raise ValueError('nonfinite constant %r refuses the cache' % name)


def _checked_number(text):
    value = float(text)
    if value != value or value == float('inf') or value == float('-inf'):
        raise ValueError('nonfinite number refuses the cache')
    return value


def _reject_duplicate_keys(pairs):
    seen = set()
    for key, _ in pairs:
        if key in seen:
            raise ValueError('duplicate key %r refuses the cache' % key)
        seen.add(key)
    return dict(pairs)


def load_cache(conf):
    """Strict-additive cache load with bounded, no-follow reads. The byte
    bound is enforced BEFORE any read (fstat size) and again during the read
    (a stat/read race cannot exceed the cap); O_NOFOLLOW refuses a symlink
    outright. Malformed, deep (RecursionError), duplicate-keyed or nonfinite
    documents and nonregular or oversized files all mean Unknown — never a
    traceback, never a trust decision, and nothing is ever executed."""
    path = cache_path(conf)
    try:
        handle = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    except OSError:
        return None
    data = b''
    try:
        try:
            meta = os.fstat(handle)
            if not stat.S_ISREG(meta.st_mode) or meta.st_size > CACHE_MAX_BYTES:
                return None
            while len(data) <= CACHE_MAX_BYTES:
                block = os.read(handle,
                                min(65536, CACHE_MAX_BYTES + 1 - len(data)))
                if not block:
                    break
                data += block
        except OSError:
            return None
    finally:
        os.close(handle)
    if len(data) > CACHE_MAX_BYTES:
        return None
    try:
        document = json.loads(data.decode('utf-8'),
                             object_pairs_hook=_reject_duplicate_keys,
                             parse_constant=_reject_nonfinite_constant,
                             parse_float=_checked_number)
    except (ValueError, UnicodeError, RecursionError):
        return None
    if not isinstance(document, dict) or document.get('schema_version') != SCHEMA_VERSION \
            or document.get('kind') != 'unio-cli-updates' or not isinstance(document.get('routes'), dict):
        return None
    routes = {}
    for name, entry in document['routes'].items():
        if name in ROUTES and isinstance(entry, dict):
            routes[name] = entry
    return {'schema_version': SCHEMA_VERSION, 'kind': 'unio-cli-updates',
            'startup_checked_at': document.get('startup_checked_at'),
            'routes': routes}


def save_cache(conf, cache):
    """Atomic replace through a private unique temp file: no fixed-name
    collisions, and independent concurrent checks can never unlink or
    overwrite unrelated files. A symlinked state directory or cache is
    refused, never followed (no hostile file swaps through this code)."""
    directory = state_dir(conf)
    path = cache_path(conf)
    tmp_name = None
    payload = json.dumps(cache, indent=2, sort_keys=True) + '\n'
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            return False, 'refused: state directory is a symlink'
        if path.is_symlink():
            return False, 'refused: cache is a symlink'
        tmp_handle, tmp_name = tempfile.mkstemp(dir=str(directory),
                                                prefix='.cache-', suffix='.tmp')
        try:
            with os.fdopen(tmp_handle, 'w', encoding='utf-8') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        except OSError:
            return False, 'cache write failed'  # tmp cleaned in finally
        if path.is_symlink():  # raced into a symlink after the pre-check
            return False, 'refused: cache is a symlink'
        os.replace(tmp_name, path)
        tmp_name = None
        return True, ''
    except OSError as failure:
        return False, 'cache write failed: %s' % failure
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


def merge_route_entry(cache, name, entry):
    routes = cache.setdefault('routes', {})
    if not isinstance(routes.get(name), dict):
        routes[name] = {}
    routes[name].update({key: value for key, value in entry.items() if value is not None})


def cached_latest(route, cache, max_age):
    entry = (cache or {}).get('routes', {}).get(route['name'], {}) if cache else None
    latest = entry.get('latest') if isinstance(entry, dict) else None
    if not isinstance(latest, dict):
        return None
    if latest.get('version') or latest.get('status', '').startswith('unsupported'):
        checked = age_seconds(latest.get('checked_at'))
        if checked is not None and checked <= max_age:
            return latest
    return None


# Read-only probes never install: where a CLI documents an official
# environment flag that suppresses its native auto-updater, the probe
# sets it. No other flags are invented, and no probe ever runs an updater.
PROBE_ENV_FLAGS = {'claude': {'DISABLE_AUTOUPDATER': '1'}}
PROBE_TIME_BOUND = 20  # seconds: version/metadata probe wall bound


def probe_environment(route=None):
    environment = dict(os.environ)
    environment.update(PROBE_ENV_FLAGS.get((route or {}).get('name'), {}))
    return environment


def _terminate_owned_session(process):
    """Clean only the exactly owned child: start_new_session made it a
    session/group leader with its own pgid, so killpg reaches only that
    group and its children — never any other session."""
    try:
        group = os.getpgid(process.pid)
    except OSError:
        group = None
    if group is not None and group != os.getpgid(0):
        try:
            os.killpg(group, signal.SIGKILL)
        except OSError:
            pass
    try:
        process.kill()
    except OSError:
        pass
    try:
        process.wait(timeout=5)
    except OSError:
        pass


def run_bounded(argv, timeout, cwd=None, env=None, limit=16384):
    """Fixed argv array only. Output size and wall time are bounded DURING
    capture — never capture-everything-then-slice, and no owned child can
    outlive its bound: past the byte limit or the deadline the child session
    is killed (only its own group). A version probe can never mutate an
    install."""
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env,
                                   stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
    except OSError:
        return None, ''
    fd = process.stdout.fileno()
    deadline = time.monotonic() + timeout
    chunks, total, timed_out = [], 0, False
    try:
        while total <= limit:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                timed_out = True
                break
            ready, _, _ = select.select([fd], [], [], min(remaining, 1.0))
            if not ready:
                continue
            block = os.read(fd, min(65536, limit + 1 - total))
            if not block:
                break  # EOF
            chunks.append(block)
            total += len(block)
    except OSError:
        timed_out = True
    finally:
        try:
            process.stdout.close()
        except OSError:
            pass
    truncated = total > limit
    if truncated or timed_out:
        _terminate_owned_session(process)
        return None, b''.join(chunks)[:limit].decode('utf-8', errors='replace')
    try:
        remaining = max(0.0, deadline - time.monotonic())
        # EOF may precede exit; a still-live child gets the rest of its bound
        process.wait(timeout=remaining if remaining > 0 else 0.1)
    except subprocess.TimeoutExpired:
        _terminate_owned_session(process)
        return None, ''.join(
            chunk.decode('utf-8', errors='replace') for chunk in chunks)
    except OSError:
        return None, ''
    text = b''.join(chunks)[:limit].decode('utf-8', errors='replace')
    return process.returncode, text


def resolve_binary(route):
    path = shutil.which(route['binary'])
    real = None
    if path:
        try:
            real = os.path.realpath(path)
        except OSError:
            real = None
    return path, real


def detect_method(route, real, allow_exec):
    """Honest install-method label; never a guess that enables an update.
    Path markers are pure facts. The uv label is additionally verified by
    `uv tool list` (read-only) in the explicit check/update paths."""
    if real:
        for marker, method in METHOD_MARKERS:
            if marker in real:
                return method
    if allow_exec and route['name'] == 'vibe':
        uv = shutil.which('uv')
        if uv:
            code, text = run_bounded([uv, 'tool', 'list'], 30, env=probe_environment(route))
            if code == 0:
                for line in text.splitlines():
                    if line.strip().startswith(UV_TOOL_PACKAGE + ' v'):
                        return 'uv-tool'
    return 'unknown'


def probe_version(route, path, cwd, timeout=PROBE_TIME_BOUND):
    if not path:
        return None, None
    code, text = run_bounded([path, *route['version_argv']], timeout, cwd=cwd,
                             env=probe_environment(route))
    version = None
    for line in text.splitlines():
        match = VERSION_RE.search(line.strip())
        if match:
            version = match.group(1)
            break
    return version, code


def fetch_json(url, timeout):
    if opt_offline():
        raise NetworkDisabled()
    request = Request(url, headers={'User-Agent': UA, 'Accept': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        data = response.read(65536 + 1)
    if len(data) > 65536:
        raise ValueError('metadata response too large')
    return json.loads(data.decode('utf-8'))


def latest_for(route, method, path, conf, timeout, allow_tool_exec, cache, max_age):
    """Latest-version facts. Fresh cache entries are reused (no network).
    A strategy outside its supported install method stays Unknown."""
    name = route['name']
    fresh = cached_latest(route, cache, max_age)
    if fresh is not None:
        merged = dict(fresh)
        merged['source'] = fresh.get('source') or route['latest'][0]
        return merged, True
    strategy, argument = route['latest']
    allowed = route['latest_any_method'] or method in ('uv-tool', 'npm')
    latest = {'version': None, 'status': 'unknown', 'source': None, 'checked_at': iso()}
    if not allowed:
        latest['status'] = 'unsupported-install-method'
        latest['source'] = '%s:%s' % (strategy, argument) if strategy != 'grok-check' else 'grok-update-check'
    elif strategy == 'github':
        latest['source'] = 'github-release:%s' % argument
        try:
            document = fetch_json('https://api.github.com/repos/%s/releases/latest' % argument, timeout)
            tag = str(document.get('tag_name') or '').strip()
            match = VERSION_RE.search(tag.lstrip('vV'))
            latest['version'] = match.group(1) if match else None
            latest['status'] = 'ok' if latest['version'] else 'unparseable-metadata'
        except (NetworkDisabled, URLError, OSError, ValueError) as failure:
            latest['status'] = 'network-disabled' if isinstance(failure, NetworkDisabled) else 'unavailable'
    elif strategy == 'pypi':
        latest['source'] = 'pypi:%s' % argument
        try:
            document = fetch_json('https://pypi.org/pypi/%s/json' % argument, timeout)
            version = str((document.get('info') or {}).get('version') or '').strip()
            match = VERSION_RE.search(version)
            latest['version'] = match.group(1) if match else None
            latest['status'] = 'ok' if latest['version'] else 'unparseable-metadata'
        except (NetworkDisabled, URLError, OSError, ValueError) as failure:
            latest['status'] = 'network-disabled' if isinstance(failure, NetworkDisabled) else 'unavailable'
    elif strategy == 'npm':
        latest['source'] = 'npm:%s' % argument
        try:
            document = fetch_json('https://registry.npmjs.org/%s/latest' % argument, timeout)
            match = VERSION_RE.search(str(document.get('version') or ''))
            latest['version'] = match.group(1) if match else None
            latest['status'] = 'ok' if latest['version'] else 'unparseable-metadata'
        except (NetworkDisabled, URLError, OSError, ValueError) as failure:
            latest['status'] = 'network-disabled' if isinstance(failure, NetworkDisabled) else 'unavailable'
    elif strategy == 'grok-check':
        latest['source'] = 'grok-update-check'
        if not allow_tool_exec or not path:
            latest['status'] = 'not-refreshed-here'  # the background refresh never executes CLIs
        else:
            code, text = run_bounded([path, *route['check_argv']], 40, cwd=conf,
                                     env=probe_environment(route))
            try:
                document = json.loads(text.strip().splitlines()[0]) if text.strip() else {}
                match = VERSION_RE.search(str(document.get('latestVersion') or ''))
                latest['version'] = match.group(1) if match else None
                latest['status'] = 'ok' if latest['version'] else 'unparseable-metadata'
            except (ValueError, IndexError):
                latest['status'] = 'unavailable' if code == 0 else 'tool-error'
    return latest, False


def resolve_selection(names, default_installed=True):
    selected = []
    if not names:
        for name in ROUTE_ORDER:
            if shutil.which(ROUTES[name]['binary']):
                selected.append(name)
        return selected
    for requested in names:
        name = ALIAS_TO_ROUTE.get(requested)
        if name is None:
            raise UsageError("unknown agent '%s' — recognized: %s"
                             % (requested, ', '.join(ROUTE_ORDER)))
        if name not in selected:
            selected.append(name)  # aliases deduplicate onto one route report
    return selected


def held_worker_locks(project):
    """Project worker locks, probed exactly like the engine's lock_probe:
    flock on the lock file itself; existence alone means nothing."""
    if not project:
        return []
    locks = Path(project) / 'coord' / '.locks'
    held = []
    try:
        names = sorted(locks.glob('*.lock'))
    except OSError:
        return []
    for lock_file in names[:64]:
        try:
            handle = os.open(lock_file, os.O_RDONLY)
        except OSError:
            held.append(lock_file.name)  # unreadable lock: ambiguous -> busy
            continue
        try:
            fcntl.flock(handle, fcntl.LOCK_SH | fcntl.LOCK_NB)
        except OSError:
            held.append(lock_file.name)
        finally:
            os.close(handle)
    return held


def native_identity_candidates(real):
    """Exact executable identities for a route's install. Only the validated
    uv-managed vibe layout adds a second candidate — the `bin/vibe` launcher
    and `lib/pythonX/site-packages/vibe/_bin/vibe-rs` belong to one install
    (verified live on 2026-11-10: a live Source matched the native identity,
    never the launcher). Everything else is a single exact path; identities
    are never inferred from process names or guessed paths."""
    if not real:
        return []
    candidates = [real]
    index = real.find(UV_TOOL_ROOT_MARKER)
    if index >= 0 and real.endswith('/bin/vibe'):
        root = Path(real[:index + len(UV_TOOL_ROOT_MARKER)])
        try:
            lib = root / 'lib'
            if not lib.is_symlink() and lib.is_dir():
                for python_dir in sorted(lib.glob('python*/site-packages'))[:8]:
                    native = python_dir / 'vibe' / '_bin' / 'vibe-rs'
                    if native.is_symlink() or not native.is_file():
                        continue
                    resolved = os.path.realpath(str(native))
                    if resolved not in candidates:
                        candidates.append(resolved)
        except OSError:
            pass
    return candidates


def native_identity(real, exclude_pids=()):
    """Minimal-privilege /proc scan; exact executable identity only. /proc
    <pid>/exe or an exact cmdline element must equal one of the validated
    candidate paths — never a process-name guess. Other users' processes
    are invisible and reported as such; same-uid non-dumpable processes
    (system daemons) cannot be identified either and are counted as an
    honestly stated visibility limit: the count is Unknown cover, never a
    confirmed-idle statement."""
    active, obscured = [], 0
    if not real or not os.path.isdir('/proc'):
        return active, None  # no identity scan possible: busy state unknown
    candidates = [os.fsencode(item) for item in native_identity_candidates(real)]
    candidateset = set(candidates)
    self_pid = os.getpid()
    try:
        entries = os.listdir('/proc')
    except OSError:
        return active, None
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in exclude_pids or pid == self_pid:
            continue
        base = '/proc/%d' % pid
        try:
            if os.stat(base).st_uid != os.getuid():
                continue  # cross-user processes are invisible by design
        except OSError:
            continue
        exe = None
        try:
            exe = os.readlink(base + '/exe')
        except OSError as failure:
            if failure.errno == errno.ENOENT:
                continue  # zombie/kernel thread: no executable identity
            obscured += 1
            continue
        if exe.endswith(DELETED_SUFFIX):
            exe = exe[:-len(DELETED_SUFFIX)]
        if os.fsencode(exe) in candidateset:
            active.append(pid)
            continue
        try:
            text = open(base + '/cmdline', 'rb').read(4096)
        except OSError:
            continue
        parts = [part for part in text.split(b'\0')[:6]]
        if any(candidate in parts for candidate in candidates):
            active.append(pid)
    return active, obscured


def stop_active(project):
    if not project:
        return False
    stop = Path(project) / 'coord' / 'STOP'
    try:
        return stop.is_file()
    except OSError:
        return True  # unreadable coord ambiguity is treated as held


def build_route(route, conf, project, max_age, timeout, cache, allow_tool_exec):
    name = route['name']
    path, real = resolve_binary(route)
    method = detect_method(route, real, allow_tool_exec)
    presence = {'name': name, 'present': bool(path), 'binary': route['binary'],
                'binary_path': path, 'binary_realpath': real, 'install_method': method}
    installed = {'name': name, 'version': None, 'exit': None, 'checked_at': None}
    present_busy = []  # exact-identity findings only
    obscured = 0
    identities = []
    if path:
        version, code = probe_version(route, path, str(conf))
        installed = {'name': name, 'version': version, 'exit': code, 'checked_at': iso()}
        active, hidden = native_identity(real)
        identities = native_identity_candidates(real)
        if active:
            present_busy.append('native-process-active')
        if hidden is None or hidden > 0:
            # Unreadable or unidentifiable same-uid processes mean Unknown;
            # a zero-or-obscured scan never confirms idle.
            present_busy.append('busy-identity-unknown')
        obscured = hidden if hidden is not None else 0
    latest, from_cache = latest_for(route, method, path, conf, timeout,
                                    allow_tool_exec, cache, max_age)
    reasons = []
    if stop_active(project):
        reasons.append('stop-active')
    if held_worker_locks(project):
        reasons.append('worker-run-active')
    reasons.extend(present_busy)
    supported = route['update_support']
    if not path:
        state = 'absent'
    elif supported == 'check-only':
        state = 'check-only'
    elif supported == 'uv-tool' and method != 'uv-tool':
        state = 'manual'
    else:
        # Installs are deferred until a shared maintenance lease exists;
        # 'supported' would overclaim, and busy observations never permit.
        state = 'maintenance_not_implemented'
    return {
        'name': name, 'group': route['group'], 'aliases': list(route['aliases']),
        'binary': route['binary'], 'present': bool(path), 'binary_path': path,
        'binary_realpath': real, 'install_method': method,
        'installed_version': installed['version'], 'version_checked_at': installed['checked_at'],
        'version_exit': installed['exit'],
        'latest_version': latest['version'], 'latest_status': latest['status'],
        'latest_source': latest.get('source'), 'latest_checked_at': latest.get('checked_at'),
        'latest_from_cache': from_cache,
        'update_support': supported, 'update_label': route['update_label'],
        'update_state': state, 'update_blocked_reasons': reasons,
        'obscured_processes': obscured, 'native_identities_checked': identities,
        'visibility_note': BUSY_NOTE,
        'compatibility': 'unknown',
    }


def human_route(row):
    installed = row['installed_version'] or 'Unknown'
    if row['latest_version']:
        latest = row['latest_version'] + ' (%s, %s)' % (row['latest_source'], row['latest_status'])
        verdict = 'current' if row['latest_version'] == row['installed_version'] else 'NEWER AVAILABLE'
    else:
        latest = 'Unknown (%s)' % row['latest_status']
        verdict = 'latest unknown'
    lines = ['  %s: installed %s, latest %s — %s' % (row['name'], installed, latest, verdict)]
    if not row['present']:
        lines.append('    absent — nothing installed is risked (skipped everywhere)')
        return '\n'.join(lines)
    lines.append('    %s · method %s · update: %s · update state: %s'
                 % (row['binary_path'], row['install_method'], row['update_label'], row['update_state']))
    if row['update_state'] == MAINTENANCE_REASON:
        lines.append('    install deferred: unio never runs any updater until a shared '
                     'maintenance lease exists — use the manual plan above when idle')
    if row['update_blocked_reasons']:
        lines.append('    busy observations (never permission, and never idle proof): %s'
                     % ', '.join(row['update_blocked_reasons']))
    if row.get('obscured_processes'):
        lines.append('    visibility: busy fact Unknown beside %d unidentifiable same-uid '
                     'process(es) (/proc); other users, other hosts and cross-workspace '
                     'sessions stay unknown' % row['obscured_processes'])
    lines.append('    compatibility unknown — updating never proves route/adapter compatibility '
                 '(guards and pins are not touched by unio)')
    return '\n'.join(lines)


def do_check(args):
    timeout = args.timeout
    names = resolve_selection(args.agents)
    cache = load_cache(args.conf)
    rows, cache = [], cache or {'schema_version': SCHEMA_VERSION, 'kind': 'unio-cli-updates',
                                'startup_checked_at': None, 'routes': {}}
    for name in names:
        row = build_route(ROUTES[name], args.conf, args.project, args.max_age,
                          timeout, cache, allow_tool_exec=True)
        rows.append(row)
        merge_route_entry(cache, name, {'presence': {
            'present': row['present'], 'binary_path': row['binary_path'],
            'binary_realpath': row['binary_realpath'], 'install_method': row['install_method']}})
        merge_route_entry(cache, name, {'installed': {
            'version': row['installed_version'], 'exit': row['version_exit'],
            'checked_at': row['version_checked_at']}})
        cached_latest = {
            'version': row['latest_version'], 'status': row['latest_status'],
            'source': row['latest_source'], 'checked_at': row['latest_checked_at']}
        merge_route_entry(cache, name, {'latest': cached_latest})
    cache['startup_checked_at'] = iso()
    written, why = save_cache(args.conf, cache)
    document = {
        'schema_version': SCHEMA_VERSION, 'checked_at': iso(), 'source': SOURCE_LABEL,
        'fresh_within_seconds': args.max_age,
        'project': {'root': args.project, 'stop_active': stop_active(args.project)},
        'routes': rows, 'cache_writable': written,
    }
    if not written:
        document['cache_write_refused'] = why
    report = json.dumps(document, indent=2, sort_keys=True) if args.json else \
        'AI CLI update check — %s (facts only; no model, auth or billing calls)\n%s' \
        % (iso(), '\n'.join(human_route(row) for row in rows) or '  no recognized CLI installed')
    print(report)
    failed = [row for row in rows if row['present'] and row['version_exit'] not in (0, None)]
    return 1 if failed else 0


MAINTENANCE_REASON = 'maintenance_not_implemented'
MANUAL_UPDATE_NOTE = ('until a shared run/review maintenance lease exists, unio never '
                      'installs: run the official updater yourself when the route is '
                      'idle, then unio update clis --check (docs/CLI-UPDATES.md)')


def do_update(args):
    """Explicit update request under the frozen install refusal. Every
    PRESENT target is refused with `maintenance_not_implemented` and its
    frozen manual plan; absent targets are skipped truthfully. Nothing is
    executed: no updater, no installing probe, no version probe, no
    process scan, no cache write — regardless of STOP, locks, process
    state, cache content, flags or environment. Busy facts are reported
    as observations by `--check`; they never become permission here."""
    names = resolve_selection(args.agents)
    results = []
    for name in names:
        route = ROUTES[name]
        path, _real = resolve_binary(route)
        row = {'name': route['name'], 'action': 'skipped', 'reason': None,
               'updater_executed': False, 'updater_exit': None,
               'updater_command': None, 'manual': None, 'compatibility': 'unknown'}
        if not path:
            row['reason'] = 'absent on PATH'
            results.append(row)
            continue
        row.update(action='refused', reason=MAINTENANCE_REASON,
                   updater_command=route['update_label'],
                   manual='%s — %s' % (route['update_label'], MANUAL_UPDATE_NOTE))
        results.append(row)
    refused = [row for row in results if row['action'] == 'refused']
    document = {'schema_version': SCHEMA_VERSION, 'command': 'update',
                'finished_at': iso(),
                'install_policy': ('maintenance_not_implemented: unio never installs; '
                                   'no updater is constructed or executed by unio'),
                'project': {'root': args.project},
                'routes': results, 'compatibility': 'unknown'}
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        lines = ['AI CLI update — %s (installs refused: maintenance coordination '
                 'is not implemented; manual plans below)' % iso()]
        for row in results:
            lines.append('  %s: %s%s' % (row['name'], row['action'],
                                         ' — %s' % row['reason'] if row['reason'] else ''))
            if row['manual']:
                lines.append('    manual plan: %s' % row['manual'])
        print('\n'.join(lines))
    return 1 if refused else 0


def spawn_refresh(conf):
    try:
        subprocess.Popen([sys.executable, '-I', '-S', '-B', os.path.abspath(__file__),
                          '--conf', str(conf), 'startup-refresh'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         stdin=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


def do_startup(args):
    if opt_off():
        return 0
    cache = load_cache(args.conf)
    age = age_seconds((cache or {}).get('startup_checked_at'))
    refresh_note = ''
    if age is None:
        head = 'cli-updates: AI CLI version facts never checked'
        started = spawn_refresh(args.conf) if not args.no_refresh else False
        refresh_note = ' — background refresh started' if started else ' (background refresh unavailable)'
    elif age <= args.max_age:
        head = 'cli-updates: AI CLI facts checked %.0f s ago (fresh)' % age
    else:
        head = 'cli-updates: AI CLI facts checked %.0f s ago (stale)' % age
        started = spawn_refresh(args.conf) if not args.no_refresh else False
        if started:
            refresh_note = ' — background refresh started'
    print(head + refresh_note + " — 'unio update clis --check' for the facts (docs/CLI-UPDATES.md)")
    return 0


class Deadline(Exception):
    pass


def _alarm(signum, frame):
    raise Deadline('deadline exceeded')


def do_startup_refresh(args):
    """Bounded background refresh: no CLI execution, no updater, owned lock,
    no stdout. Default deadline UNIO_CLI_UPDATES_DEADLINE (45 s)."""
    deadline = env_int('UNIO_CLI_UPDATES_DEADLINE', 45, 5, 600)
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(deadline)
    directory = state_dir(args.conf)
    try:
        directory.mkdir(parents=True, exist_ok=True)
        if directory.is_symlink():
            return 0
        handle = os.open(directory / 'refresh.lock', os.O_RDWR | os.O_CREAT, 0o600)
    except OSError:
        return 0
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(handle)
            return 0  # a bounded owned refresh is already running
        os.truncate(handle, 0)
        os.write(handle, ('pid %d started %s deadline %ds\n' % (os.getpid(), iso(), deadline)).encode())
        cache = load_cache(args.conf) or {'schema_version': SCHEMA_VERSION,
                                          'kind': 'unio-cli-updates', 'startup_checked_at': None,
                                          'routes': {}}
        timeout = env_int('UNIO_CLI_UPDATES_TIMEOUT', 10, 1, 60)
        max_age = env_int('UNIO_CLI_UPDATES_MAX_AGE', 86400, 60, 864000)
        for name in ROUTE_ORDER:
            try:
                route = ROUTES[name]
                path, real = resolve_binary(route)
                method = detect_method(route, real, allow_exec=False)
                latest, from_cache = latest_for(route, method, path, args.conf, timeout,
                                                allow_tool_exec=False, cache=cache, max_age=max_age)
                merge_route_entry(cache, name, {'presence': {
                    'present': bool(path), 'binary_path': path, 'binary_realpath': real,
                    'install_method': method}})
                if not from_cache:
                    merge_route_entry(cache, name, {'latest': latest})
            except Exception:  # one route never aborts the bounded refresh
                continue
        cache['startup_checked_at'] = iso()
        try:
            save_cache(args.conf, cache)
        except Exception:
            pass
    except Deadline:
        pass
    finally:
        try:
            fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            os.close(handle)
    return 0


def build_parser():
    parser = argparse.ArgumentParser(prog='cli-updates', allow_abbrev=False,
                                      description='Machine-level AI CLI version facts and explicit updates')
    parser.add_argument('--conf', required=True, metavar='DIR', help='Unio config directory')
    parser.add_argument('--project', metavar='PATH', help='project root when inside a Unio project')
    commands = parser.add_subparsers(dest='mode', required=True)
    check = commands.add_parser('check', allow_abbrev=False,
                                description='facts only; never installs or calls an updater')
    check.add_argument('--json', action='store_true', help='strict additive versioned JSON')
    check.add_argument('--max-age-seconds', type=int, default=86400,
                       help='cache freshness bound (bounded 60..864000; default 86400 = daily)')
    check.add_argument('--timeout', type=int, default=10,
                       help='metadata request bound in seconds')
    check.add_argument('agents', nargs='*', metavar='AGENT', help='route or alias (default: installed routes)')
    update = commands.add_parser('update', allow_abbrev=False,
                                 description='explicit update request; installs are refused '
                                 '(maintenance_not_implemented) with manual plans only')
    update.add_argument('--json', action='store_true', help='strict additive versioned JSON')
    update.add_argument('agents', nargs='*', metavar='AGENT', help='route or alias (default: installed routes)')
    startup = commands.add_parser('startup', allow_abbrev=False,
                                  description='one read-only freshness line for human entry points')
    startup.add_argument('--label', default=None, help=argparse.SUPPRESS)
    startup.add_argument('--no-refresh', action='store_true', help='do not spawn the background refresh')
    startup.add_argument('--max-age-seconds', type=int, default=86400,
                         help='fresh/stale bound (default 86400 = daily)')
    commands.add_parser('startup-refresh', allow_abbrev=False,
                        help=argparse.SUPPRESS)  # internal bounded no-CLI refresh
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    if getattr(args, 'max_age_seconds', None) is not None:
        args.max_age = max(60, min(864000, args.max_age_seconds))
    else:
        args.max_age = env_int('UNIO_CLI_UPDATES_MAX_AGE', 86400, 60, 864000)
    if args.mode == 'startup-refresh':
        return do_startup_refresh(args)
    if args.mode == 'startup':
        return do_startup(args)
    conf = Path(args.conf)
    if not conf.is_dir():
        print('cli-updates: config directory missing: %s' % conf, file=sys.stderr)
        return 2
    try:
        if args.mode == 'check':
            return do_check(args)
        if args.mode == 'update':
            return do_update(args)
    except UsageError as failure:
        print('cli-updates: %s' % failure, file=sys.stderr)
        return 2
    return 2


if __name__ == '__main__':
    sys.exit(main())
