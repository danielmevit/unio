#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms: NOTICE.
"""Machine-level AI CLI version facts and explicit, manual-only updates.

Installed by tools/embed-cli-updates.py as $CONF_DIR/lib/cli-updates.py and
driven by `unio update clis`. Standard library only; no shell, no eval.

Safety contract (frozen 2026-11-10, corrected after external review):
- `check` records facts only: installed version, latest-version metadata,
  cache age, install method, busy observations (STOP, worker locks, native
  process identity), support and compatibility Unknown. A check NEVER calls
  an installing updater. The only tool commands it may run are a plain
  read-only `--version` and grok's documented read-only
  `update --check --json`. Nothing from agents.conf, task files, reports,
  cache text or downloaded URLs is ever executed or evaluated; every
  subprocess is a fixed argv array from the table below. Latest-version
  metadata is never fetched for an absent binary.
- `update` is the explicit update request, but until a shared native
  maintenance/admission lease (unio run/review <-> updater) is implemented,
  it REFUSES to install for EVERY present target with a truthful per-route
  reason (`maintenance_not_implemented` for genuinely installable routes,
  `check-only-route` for claude/codex, `manual-unverified-install` for a
  vibe whose uv-managed layout is not verified from the resolved binary)
  plus that CLI's frozen manual plan. No updater or installing probe is
  ever constructed or executed by this module — regardless of STOP,
  process state, cache content, flags or environment (there is
  deliberately no bypass). The frozen updater commands in the table
  below are safe manual plans only, never argv this code runs. Busy facts
  reported by `check` stay honest observations, never permission and
  never idle confirmation. Updating is not claimed complete: automatic
  installation is deferred (docs/CLI-UPDATES.md). Updates — if ever
  implemented — never touch route/adapter version guards or pins:
  compatibility stays Unknown until proven by real use.
- `startup` prints one read-only freshness line for human entry points
  (plain unio/help, doctor, resume) from the cache only: `never checked`,
  `fresh` or `stale`. The bounded background refresh spawns ONLY for
  genuinely interactive owner invocations (stdin AND stdout are a TTY);
  noninteractive, scripted or fixture invocations never touch the network
  and never spawn detached writers — explicit `unio update clis --check`
  is the bounded metadata opt-in. A spawn refresh (owned lock opened
  no-follow and nonblocking, hard SIGALRM deadline plus an exactly-owned
  watchdog child, no stdout) never executes any CLI binary or updater —
  only filesystem metadata and official metadata URLs, and never for an
  absent binary. Corrupt/missing/malformed/future-dated cache means
  Unknown, never authorization to run anything. No secrets or account
  identifiers are ever stored or read.

Routes and commands below were verified read-only on the host on
2026-11-10 (agy 1.5.4, vibe 3.1.1 via `uv tool list`, grok 1.0.77,
copilot 1.0.108, opencode 1.19.5, claude 2.1.322 npm, codex 0.167.0).
That is a dated observation, not a pin on any version.

Env: UNIO_CONF_DIR-dir default is UNIO_CONF_DIR then ~/.config/unio;
UNIO_CLI_UPDATES_MAX_AGE (seconds, default 86400 — the explicit
--max-age-seconds flag overrides it); UNIO_CLI_UPDATES_TIMEOUT (metadata
seconds per request, default 10 — the explicit --timeout flag overrides
it for `check`); UNIO_CLI_UPDATES_DEADLINE (startup refresh total
seconds, default 45 — enforced by SIGALRM plus an exactly-owned watchdog
child 15 s past it); UNIO_CLI_UPDATES_OFF=1 disables startup awareness
entirely (offline/tests); UNIO_CLI_UPDATES_OFFLINE=1 forbids all network
metadata fetches honestly.
"""
import argparse
import errno
import fcntl
import json
import os
import re
import secrets
import select
import shutil
import signal
import stat
import subprocess
import sys
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
# not a small regular file is ever parsed. Opens are NONBLOCKING and
# NOFOLLOW on the state directory and the final file, so a FIFO, device or
# symlink can never block or be followed (the state directory is pinned by
# a dir fd — read paths never follow a swapped parent).
CACHE_MAX_BYTES = 262144
# Clock-skew allowance: timestamps up to this far in the future are treated
# as age 0 (real WSL/host skew is seconds to minutes); anything further in
# the future is Unknown, never fresh-forever.
CLOCK_SKEW_TOLERANCE = 300.0

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
        'update_argv': None,  # manual plan only: uv tool upgrade mistral-vibe
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
    """Age in seconds, or None when unknown. A timestamp in the future
    beyond CLOCK_SKEW_TOLERANCE (WSL/host clock skew is real) is Unknown —
    never a fresh-forever age of 0; a small negative skew keeps the entry
    usable at age 0."""
    stamp = parse_iso(text) if isinstance(text, str) else None
    if stamp is None:
        return None
    delta = (now() - stamp).total_seconds()
    if delta < -CLOCK_SKEW_TOLERANCE:
        return None
    return max(0.0, delta)


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


def _clean_cache_text(value, limit=256):
    """Cache fields are reused and printed only as bounded printable
    strings; wrong-typed, oversized or control-character garbage means
    Unknown for the fact, never a traceback or a trusted value."""
    if not isinstance(value, str) or len(value) > limit:
        return None
    if any(ord(ch) < 0x20 or ord(ch) == 0x7f for ch in value):
        return None
    return value


def _clean_latest_entry(entry):
    """Validate a cached `latest` fact field by field. Returns a clean dict
    or None (a malformed or wrong-typed entry is quiet Unknown). A field
    that is present but not a bounded printable string poisons the whole
    fact — a wrong type is never partially trusted; a version string that
    is not a version poisons it too. Missing fields read as None."""
    if not isinstance(entry, dict):
        return None
    fields = {}
    for key in ('version', 'status', 'source', 'checked_at'):
        if key not in entry:
            fields[key] = None
            continue
        value = entry.get(key)
        if value is None:
            fields[key] = None
            continue
        value = _clean_cache_text(value)
        if value is None:
            return None  # present but wrong-typed/oversized/unprintable
        if key == 'version' and not VERSION_RE.fullmatch(value):
            return None  # a 'version' that is not a version poisons the fact
        fields[key] = value
    if fields['status'] is None:  # status drives reuse decisions
        return None
    return fields


def _open_state_dir(conf):
    """Open the state directory with O_NOFOLLOW|O_DIRECTORY so a symlinked
    (hostile) state directory is refused on read and write, and the final
    file can be opened relative to the pinned dir fd (no parent race)."""
    return os.open(state_dir(conf),
                   os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_DIRECTORY)


def load_cache(conf):
    """Strict-additive cache load with bounded, nonblocking, no-follow reads
    through a pinned state-directory fd. The byte bound is enforced BEFORE
    any read (fstat) and again during the read (a stat/read race cannot
    exceed the cap); O_NOFOLLOW refuses a symlinked final file, the pinned
    O_NOFOLLOW|O_DIRECTORY state-dir fd refuses a symlinked state directory
    and stays immune to a parent swap; O_NONBLOCK plus the regular-file
    check means a FIFO or device can never block startup. Malformed, deep
    (RecursionError), duplicate-keyed, nonfinite, oversized, nonregular or
    wrong-typed-field documents are quiet Unknown — never a traceback,
    never a trust decision, and nothing is ever executed."""
    try:
        directory_fd = _open_state_dir(conf)
    except OSError:
        return None
    try:
        try:
            handle = os.open('cache.json', os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK,
                             dir_fd=directory_fd)
        except OSError:
            return None
    finally:
        os.close(directory_fd)
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
    checked = _clean_cache_text(document.get('startup_checked_at'))
    routes = {}
    for name, entry in document['routes'].items():
        if name in ROUTES and isinstance(entry, dict):
            if isinstance(entry.get('latest'), dict):
                latest = _clean_latest_entry(entry.get('latest'))
                if latest is not None:
                    entry['latest'] = latest
                else:
                    entry.pop('latest', None)  # a wrong-typed fact is Unknown
            routes[name] = entry
    return {'schema_version': SCHEMA_VERSION, 'kind': 'unio-cli-updates',
            'startup_checked_at': checked,
            'routes': routes}


def save_cache(conf, cache):
    """Atomic replace through a private unique temp file: no fixed-name
    collisions, and independent concurrent checks can never unlink or
    overwrite unrelated files. All path-borne operations are confined to
    the state directory through the same O_NOFOLLOW|O_DIRECTORY fd that
    load_cache uses, so a symlinked state directory is refused (never
    followed on write), the temporary file is created, written, replaced
    and cleaned up relative to that SAME pinned fd (never reopening the
    pathname or following a swapped directory), and a symlinked
    cache.json is refused honestly — nothing is ever written through a
    symlink."""
    directory = state_dir(conf)
    payload = json.dumps(cache, indent=2, sort_keys=True) + '\n'
    try:
        directory.mkdir(parents=True, exist_ok=True)
    except OSError as failure:
        return False, 'cache write failed: %s' % failure
    try:
        directory_fd = _open_state_dir(conf)
    except OSError:
        return False, 'refused: state directory is a symlink or unusable'
    tmp_name = None
    try:
        try:
            meta = os.stat('cache.json', dir_fd=directory_fd, follow_symlinks=False)
            if stat.S_ISLNK(meta.st_mode):
                return False, 'refused: cache is a symlink'
        except FileNotFoundError:
            pass
        except OSError:
            return False, 'cache write refused: final path unusable'
        tmp_handle = None
        for _ in range(128):
            candidate = '.cache-%s.tmp' % secrets.token_hex(8)
            try:
                tmp_handle = os.open(candidate,
                                     os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                                     0o600,
                                     dir_fd=directory_fd)
                tmp_name = candidate
                break
            except FileExistsError:
                continue
            except OSError:
                break
        if tmp_handle is None:
            return False, 'cache write failed'
        try:
            try:
                with os.fdopen(tmp_handle, 'w', encoding='utf-8') as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
            except Exception:
                try:
                    os.close(tmp_handle)
                except OSError:
                    pass
                raise
        except OSError:
            return False, 'cache write failed'  # tmp cleaned in finally
        try:
            os.replace(tmp_name, 'cache.json',
                       src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        except OSError:
            return False, 'cache write failed'
        tmp_name = None
        return True, ''
    except OSError as failure:
        return False, 'cache write failed: %s' % failure
    finally:
        if tmp_name is not None:
            try:
                os.unlink(tmp_name, dir_fd=directory_fd)
            except OSError:
                pass
        os.close(directory_fd)


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
    version = latest.get('version')
    status = latest.get('status')
    if not (version is None or isinstance(version, str)) \
            or not isinstance(status, str):
        return None  # wrong-typed cached facts are quiet Unknown
    if version or status.startswith('unsupported'):
        checked = age_seconds(latest.get('checked_at'))  # future-dated = Unknown
        if checked is not None and checked <= max_age:
            return latest
    return None


# Read-only probes never install: where a CLI documents an official
# environment flag that suppresses its native auto-updater, the probe
# sets it. No other flags are invented, and no probe ever runs an updater.
# Vibe's flags are the same documented pair the project's own worker uses
# (tools/vibe-worker.py, unio-install.sh): VIBE_ENABLE_UPDATE_CHECKS /
# VIBE_ENABLE_AUTO_UPDATE = false.
PROBE_ENV_FLAGS = {
    'claude': {'DISABLE_AUTOUPDATER': '1'},
    'vibe': {'VIBE_ENABLE_UPDATE_CHECKS': 'false',
             'VIBE_ENABLE_AUTO_UPDATE': 'false'},
}
PROBE_TIME_BOUND = 20  # seconds: version/metadata probe wall bound


def probe_environment(route=None):
    environment = dict(os.environ)
    environment.update(PROBE_ENV_FLAGS.get((route or {}).get('name'), {}))
    return environment


def _terminate_owned_session(process):
    """Clean only the exactly owned child: start_new_session made it a
    session/group leader with its own pgid, so killpg reaches only that
    group and its children — never any other session. Honest limits: a
    child stuck in an uninterruptible (D) state can survive even SIGKILL;
    a TimeoutExpired from the post-kill wait is swallowed WITHOUT a 'killed'
    claim — the caller sees exit code None (Unknown), never the child's
    own output as a verified exit."""
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
    except (OSError, subprocess.TimeoutExpired):
        pass  # the child may outlive the kill (D state); no false killed claim


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
    The label is bound to the binary actually on PATH: the uv-tool label
    requires the RESOLVED executable to live inside the validated uv tools
    layout (a realpath marker — `uv tool list` output carries no path, so
    it can never be tied to the PATH binary and is deliberately not used
    for identification). No evidence, no label: unknown stays unknown."""
    if real:
        for marker, method in METHOD_MARKERS:
            if marker in real:
                return method
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
    flock on the lock file itself; existence alone means nothing. Opens are
    nonblocking and no-follow with a regular-file check, so a FIFO, device
    or symlinked lock path can never block startup and counts as held
    (an unusable lock file is ambiguous, never idle)."""
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
            handle = os.open(lock_file, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        except OSError:
            held.append(lock_file.name)  # unreadable lock: ambiguous -> busy
            continue
        try:
            if not stat.S_ISREG(os.fstat(handle).st_mode):
                held.append(lock_file.name)  # nonregular lock: ambiguous -> busy
                continue
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
    if path:
        latest, from_cache = latest_for(route, method, path, conf, timeout,
                                        allow_tool_exec, cache, max_age)
    else:
        # Never fetch or execute anything for an absent binary: latest is
        # honestly Unknown for a route with nothing installed to compare.
        latest = {'version': None, 'status': 'absent', 'source': None,
                  'checked_at': iso()}
        from_cache = False
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
CHECK_ONLY_REASON = 'check-only-route'
UNVERIFIED_INSTALL_REASON = 'manual-unverified-install'


def refusal_reason(route, real):
    """Truthful per-route refusal reason. `maintenance_not_implemented` (the
    lease is genuinely missing) is only stated for installable routes whose
    frozen plan applies to the binary on PATH; claude/codex are check-only
    by policy, and a vibe outside the validated uv layout is manual — never
    a reason that implies unio would install it once a lease exists."""
    if route['update_support'] == 'check-only':
        return CHECK_ONLY_REASON
    if route['name'] == 'vibe' and not (real and UV_TOOL_ROOT_MARKER in real):
        return UNVERIFIED_INSTALL_REASON
    return MAINTENANCE_REASON


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
        path, real = resolve_binary(route)
        row = {'name': route['name'], 'action': 'skipped', 'reason': None,
               'updater_executed': False, 'updater_exit': None,
               'updater_command': None, 'manual': None, 'compatibility': 'unknown'}
        if not path:
            row['reason'] = 'absent on PATH'
            results.append(row)
            continue
        reason = refusal_reason(route, real)
        row.update(action='refused', reason=reason,
                   updater_command=route['update_label'],
                   manual='%s — %s' % (route['update_label'], MANUAL_UPDATE_NOTE))
        results.append(row)
    refused = [row for row in results if row['action'] == 'refused']
    document = {'schema_version': SCHEMA_VERSION, 'command': 'update',
                'finished_at': iso(),
                'install_policy': ('no-bypass refusal: unio never installs; no updater '
                                   'is constructed or executed by unio. Per-route '
                                   'refusal reasons are truthful: '
                                   'maintenance_not_implemented (installable route, '
                                   'no maintenance lease yet), check-only-route '
                                   '(claude/codex by policy), '
                                   'manual-unverified-install (vibe outside the '
                                   'validated uv layout)'),
                'project': {'root': args.project},
                'routes': results, 'compatibility': 'unknown'}
    if args.json:
        print(json.dumps(document, indent=2, sort_keys=True))
    else:
        lines = ['AI CLI update — %s (installs refused with a truthful per-route '
                 'reason; manual plans below)' % iso()]
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


def _interactive_entry():
    """Automatic startup refresh is for actual interactive owner invocations
    only (both stdin and stdout are a TTY). Scripted, piped, cron, IDE or
    test-harness invocations are noninteractive: cached facts or Unknown
    only, never a spawned writer (a closed stream question is also not
    interactive)."""
    try:
        return sys.stdin.isatty() and sys.stdout.isatty()
    except (ValueError, OSError):
        return False


def do_startup(args):
    if opt_off():
        return 0
    cache = load_cache(args.conf)
    stamp = (cache or {}).get('startup_checked_at')
    age = age_seconds(stamp)  # a far-future stamp is Unknown, never fresh
    if stamp is None:
        head = 'cli-updates: AI CLI version facts never checked'
    elif age is None:
        head = 'cli-updates: AI CLI facts unknown (unusable cache timestamp)'
    elif age <= args.max_age:
        head = 'cli-updates: AI CLI facts checked %.0f s ago (fresh)' % age
    else:
        head = 'cli-updates: AI CLI facts checked %.0f s ago (stale)' % age
    refresh_note = ''
    if age is None or age > args.max_age:
        # The bounded background refresh is for genuine interactive owner
        # entry only; scripts, pipes and fixtures never spawn writers.
        if args.no_refresh or not _interactive_entry():
            refresh_note = '' if args.no_refresh \
                else ' — background refresh runs only at interactive entry'
        else:
            started = spawn_refresh(args.conf)
            refresh_note = ' — background refresh started' if started \
                else ' (background refresh unavailable)'
    print(head + refresh_note + " — 'unio update clis --check' for the facts (docs/CLI-UPDATES.md)")
    return 0


class Deadline(BaseException):
    """BaseException by design: the per-route `except Exception` guard must
    NEVER swallow the refresh deadline. Raising stops the whole refresh."""


def _alarm(signum, frame):
    raise Deadline('deadline exceeded')


def _parent_start_time():
    """Boot-time-unique /proc identity for the watchdog's exact-parent
    check, so a recycled pid can never be signalled in its place."""
    with open('/proc/self/stat', 'rb') as handle:
        fields = handle.read().rsplit(b')', 1)[1].split()
    return fields[19]  # field 22 overall: process start time in clock ticks


WATCHDOG_GRACE = 15  # seconds past the deadline before the hard SIGKILL


def _watchdog_child(parent_pid, parent_start, limit):
    """Exactly-owned watchdog: bound to this refresh process by pid AND boot
    start time (no recycled-pid misfire). If the parent is still alive
    `limit` seconds after fork — hung in DNS or an unkillable-state syscall
    where SIGALRM cannot run — it receives an exact-pid SIGKILL, so no
    detached refresh child ever outlives its bound. The watchdog exits as
    soon as the parent finishes; it signals only that parent, and makes no
    claim beyond the kill attempt (a D-state parent may survive even this)."""
    interval = 0.25
    try:
        while True:
            try:
                os.kill(parent_pid, 0)
            except OSError:
                os._exit(0)  # parent finished; nothing to bound any more
            if time.monotonic() >= limit:
                break
            try:
                with open('/proc/%d/stat' % parent_pid, 'rb') as handle:
                    started = handle.read().rsplit(b')', 1)[1].split()[19]
            except OSError:
                os._exit(0)  # parent gone
            if started != parent_start:
                os._exit(0)  # pid recycled: never signal an unrelated process
            time.sleep(interval)
        try:
            os.kill(parent_pid, signal.SIGKILL)
        except OSError:
            pass
    except BaseException:
        pass
    os._exit(0)


def do_startup_refresh(args):
    """Bounded background refresh: no CLI execution, no updater, owned lock
    (opened no-follow and nonblocking — a symlinked refresh.lock is refused
    before any truncate/write), no stdout, no fetch for absent binaries.
    The deadline is hard twice over: SIGALRM raises a BaseException that
    no per-route guard swallows, and an exactly-owned watchdog child
    SIGKILLs this process by exact pid if it is still alive
    WATCHDOG_GRACE seconds past the deadline (DNS/slow-read hangs cannot
    outlive their bound). Default deadline UNIO_CLI_UPDATES_DEADLINE (45 s).
    """
    deadline_seconds = env_int('UNIO_CLI_UPDATES_DEADLINE', 45, 5, 600)
    watchdog_pid = None
    kill_at = time.monotonic() + deadline_seconds + WATCHDOG_GRACE
    if os.path.isfile('/proc/self/stat'):
        try:
            parent_start = _parent_start_time()
            watchdog_pid = os.fork()
        except OSError:
            watchdog_pid = None
        if watchdog_pid == 0:
            _watchdog_child(os.getppid(), parent_start, kill_at)  # never returns
    signal.signal(signal.SIGALRM, _alarm)
    signal.alarm(deadline_seconds)
    handle = None
    directory_fd = None
    try:
        directory = state_dir(args.conf)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            directory_fd = _open_state_dir(args.conf)
        except OSError:
            return 0
        try:
            # O_NOFOLLOW: a symlinked refresh.lock is refused before any
            # truncate or write — nothing is ever written through a symlink;
            # O_NONBLOCK plus the regular-file fstat means a FIFO or device
            # lock never blocks and is refused too.
            handle = os.open('refresh.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW
                             | os.O_NONBLOCK, 0o600, dir_fd=directory_fd)
            if not stat.S_ISREG(os.fstat(handle).st_mode):
                os.close(handle)
                handle = None
                return 0
        except OSError:
            return 0
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            os.close(handle)
            handle = None
            return 0  # a bounded owned refresh is already running
        os.truncate(handle, 0)
        os.write(handle, ('pid %d started %s deadline %ds\n'
                          % (os.getpid(), iso(), deadline_seconds)).encode())
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
                merge_route_entry(cache, name, {'presence': {
                    'present': bool(path), 'binary_path': path, 'binary_realpath': real,
                    'install_method': method}})
                if not path:
                    continue  # never fetch latest for an absent binary
                latest, from_cache = latest_for(route, method, path, args.conf, timeout,
                                                allow_tool_exec=False, cache=cache, max_age=max_age)
                if not from_cache:
                    merge_route_entry(cache, name, {'latest': latest})
            except Exception:  # one route never aborts the bounded refresh
                continue                   # (Deadline is BaseException: never swallowed)
        cache['startup_checked_at'] = iso()
        save_cache(args.conf, cache)
    except Deadline:
        pass  # the bound held: stopped by the alarm, cache left stale honestly
    finally:
        try:
            signal.alarm(0)
        except (OSError, ValueError):
            pass
        if handle is not None:
            try:
                fcntl.flock(handle, fcntl.LOCK_UN)
            finally:
                os.close(handle)
        if directory_fd is not None:
            try:
                os.close(directory_fd)
            except OSError:
                pass
        if watchdog_pid:
            # exactly-owned watchdog cleanup: SIGKILL by exact pid, then wait
            try:
                os.kill(watchdog_pid, signal.SIGKILL)
            except OSError:
                pass
            try:
                os.waitpid(watchdog_pid, 0)
            except (OSError, ChildProcessError):
                pass  # already reaped or gone; never a false 'cleaned' claim
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
    check.add_argument('--max-age-seconds', type=int, default=None,
                       help='cache freshness bound (bounded 60..864000; overrides '
                            'UNIO_CLI_UPDATES_MAX_AGE; default 86400 = daily)')
    check.add_argument('--timeout', type=int, default=None,
                       help='metadata request bound in seconds (bounded 1..60; '
                            'overrides UNIO_CLI_UPDATES_TIMEOUT; default 10)')
    check.add_argument('agents', nargs='*', metavar='AGENT', help='route or alias (default: installed routes)')
    update = commands.add_parser('update', allow_abbrev=False,
                                 description='explicit update request; installs are refused '
                                 'with a truthful per-route reason and manual plans only')
    update.add_argument('--json', action='store_true', help='strict additive versioned JSON')
    update.add_argument('agents', nargs='*', metavar='AGENT', help='route or alias (default: installed routes)')
    startup = commands.add_parser('startup', allow_abbrev=False,
                                  description='one read-only freshness line for human entry '
                                  'points; the refresh runs only at interactive entry')
    startup.add_argument('--label', default=None, help=argparse.SUPPRESS)
    startup.add_argument('--no-refresh', action='store_true', help='do not spawn the background refresh')
    startup.add_argument('--max-age-seconds', type=int, default=None,
                         help='fresh/stale bound (overrides '
                              'UNIO_CLI_UPDATES_MAX_AGE; default 86400 = daily)')
    commands.add_parser('startup-refresh', allow_abbrev=False,
                        help=argparse.SUPPRESS)  # internal bounded no-CLI refresh
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    # Explicit flags override the documented env defaults; the env vars
    # themselves override the built-in 86400/10 defaults. An argparse default
    # must never mask UNIO_CLI_UPDATES_MAX_AGE/TIMEOUT (review finding).
    if getattr(args, 'max_age_seconds', None) is not None:
        args.max_age = max(60, min(864000, args.max_age_seconds))
    else:
        args.max_age = env_int('UNIO_CLI_UPDATES_MAX_AGE', 86400, 60, 864000)
    if getattr(args, 'timeout', None) is not None:
        args.timeout = max(1, min(60, args.timeout))
    else:
        args.timeout = env_int('UNIO_CLI_UPDATES_TIMEOUT', 10, 1, 60)
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
