#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Loopback-only read-only Activity preview; no dispatch or project writes."""
import argparse
from datetime import datetime
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import selectors
import shutil
import signal
from pathlib import Path
import subprocess
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ASSETS = Path(__file__).resolve().parent
TOP_FIELDS = {'schema_version','observed_at','stopped','agents','results','retries','recent_events','warnings','evidence'}
DEFAULT_OBSERVER_TIMEOUT = 30
DASHBOARD_LAUNCH = 'UNIO_DASHBOARD_LAUNCH'  # internal: set only by the managed dashboard helper


def observer_timeout(value):
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        raise argparse.ArgumentTypeError('observer timeout must be 1 through 120 seconds') from None
    if isinstance(value, bool) or not 1 <= seconds <= 120:
        raise argparse.ArgumentTypeError('observer timeout must be 1 through 120 seconds')
    return seconds


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('duplicate JSON field')
        value[key] = item
    return value


class Observer:
    def __init__(self, project, engine, timeout=DEFAULT_OBSERVER_TIMEOUT):
        self.project, self.engine, self.timeout = project, engine, observer_timeout(timeout)
        self.lock = threading.Lock()
        self.cached = None
        self.expires = 0

    def read(self):
        with self.lock:
            if time.monotonic() < self.expires:
                return self.cached
            self.cached = None
            try:
                result = subprocess.run([str(self.engine),'watch','--once','--json'],
                    cwd=self.project/'repo', stdin=subprocess.DEVNULL, capture_output=True, timeout=self.timeout)
                if result.returncode or len(result.stdout) > 8 * 1024 * 1024:
                    raise ValueError('observer failed')
                data = json.loads(result.stdout)
                if (not isinstance(data,dict) or type(data.get('schema_version')) is not int or data['schema_version'] != 1
                    or type(data.get('stopped')) is not bool or any(not isinstance(data.get(k),list)
                        for k in ('agents','results','retries','recent_events','warnings'))):
                    raise ValueError('unsupported observer document')
                # Producer is the fixed owner-selected CLI. Never include arbitrary
                # stdout/stderr or unexpected top-level fields in an HTTP response.
                self.cached = {k:v for k,v in data.items() if k in TOP_FIELDS}
            except (ValueError,OSError,subprocess.TimeoutExpired):
                self.cached = None
            self.expires = time.monotonic() + 1
            return self.cached


# ---------------------------------------------------------------- limits
# Read-only allowance overview. Only these fixed installed native reads run,
# with the server-selected project; the requester chooses nothing. No provider
# refresh, model, auth, policy, bench or execution command is ever started.
LIMITS_TTL = 5.0
LIMITS_TIMEOUT = 10.0
LIMITS_MAX_OUTPUT = 262144
LIMIT_LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
LIMIT_BUCKET = re.compile(r'[A-Za-z0-9][A-Za-z0-9._:-]{0,63}')
LIMIT_TIME = re.compile(r'[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]{8,15}(?:Z|[+-][0-9]{2}:[0-9]{2})')
LIMIT_MODES = ('yolo', 'medium', 'safe')
LIMIT_TIERS = ('low', 'medium', 'high')
WINDOW_STATUSES = ('fresh', 'stale', 'expired', 'unknown', 'historical')
CODEX_REASONS = frozenset((
    'binary_missing', 'start_failed', 'timeout', 'exited', 'output_limit', 'invalid_message',
    'unexpected_request', 'request_failed', 'not_signed_in', 'unsupported_account',
    'invalid_account', 'invalid_rate_limits', 'no_valid_window', 'internal_error',
    'invalid_bucket', 'invalid_window', 'implausible_reset', 'not_refreshed'))
MAX_LIMIT_ENTRIES = 32


class LimitsRefused(ValueError):
    """A native document outside the strict contract: shown as Unknown."""


def bounded_run(argv, cwd, timeout=LIMITS_TIMEOUT, limit=LIMITS_MAX_OUTPUT):
    """Fixed argv, no shell; stdout capped and stderr discarded unread."""
    process = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    chunks, size, deadline = [], 0, time.monotonic() + timeout
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LimitsRefused('deadline')
                if not selector.select(min(0.2, remaining)):
                    continue
                chunk = os.read(process.stdout.fileno(), 65536)
                if not chunk:
                    break
                size += len(chunk)
                if size > limit:
                    raise LimitsRefused('output limit')
                chunks.append(chunk)
        code = process.wait(timeout=max(0.1, deadline - time.monotonic()))
    except (LimitsRefused, subprocess.TimeoutExpired):
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        process.wait()
        raise LimitsRefused('bounded read failed') from None
    finally:
        process.stdout.close()
    if code:
        raise LimitsRefused('unsupported command')
    try:
        return json.loads(b''.join(chunks).decode('utf-8'), object_pairs_hook=unique_object)
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise LimitsRefused('not JSON') from None


def _limit_expect(condition):
    if not condition:
        raise LimitsRefused('outside the limits contract')


def _limit_label(value, pattern=LIMIT_LABEL):
    _limit_expect(isinstance(value, str) and pattern.fullmatch(value) is not None)
    return value


def _limit_time(value, nullable=True):
    if value is None and nullable:
        return None
    _limit_expect(isinstance(value, str) and LIMIT_TIME.fullmatch(value) is not None)
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        _limit_expect(parsed.tzinfo is not None)
    except (ValueError, OverflowError):
        raise LimitsRefused('invalid calendar time') from None
    return value


def _limit_number(value, low=None, high=None):
    _limit_expect(type(value) in (int, float))
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    _limit_expect(finite)
    _limit_expect((low is None or value >= low) and (high is None or value <= high))
    return value


def _limit_count_map(value):
    _limit_expect(isinstance(value, dict) and len(value) <= MAX_LIMIT_ENTRIES)
    result = {}
    for key, count in value.items():
        _limit_expect(type(count) is int and 0 <= count <= 1000)
        result[_limit_label(key)] = count
    return result


def limits_policy(doc):
    _limit_expect(isinstance(doc, dict) and type(doc.get('schema_version')) is int and doc['schema_version'] == 1)
    _limit_expect(doc.get('mode') in LIMIT_MODES and doc.get('tier') in LIMIT_TIERS)
    _limit_expect(doc.get('workflow_enforcement') == 'native_workflows')
    limit = doc.get('workflow_limit_per_group')
    _limit_expect(type(limit) is int and 1 <= limit <= 64)
    accounts = doc.get('accounts')
    _limit_expect(isinstance(accounts, dict) and len(accounts) <= MAX_LIMIT_ENTRIES)
    lead, group = doc.get('lead_agent'), doc.get('lead_group')
    return {'state': 'ok', 'mode': doc['mode'], 'tier': doc['tier'],
            'lead_agent': None if lead is None else _limit_label(lead),
            'lead_group': None if group is None else _limit_label(group),
            'accounts': {_limit_label(a): _limit_label(g) for a, g in accounts.items()},
            'workflow_limit_per_group': limit,
            'active_native_workflows': _limit_count_map(doc.get('active_native_workflows')),
            'active_with_lead': _limit_count_map(doc.get('active_with_lead'))}


def _limit_window(window, source):
    """One window; malformed numbers become an explicit invalid entry, never valid-looking."""
    _limit_expect(isinstance(window, dict))
    status = window.get('status')
    if status not in WINDOW_STATUSES:
        return {'status': 'invalid', 'source': source}
    try:
        minutes = window.get('window_minutes')
        _limit_expect(type(minutes) is int and 1 <= minutes <= 527040)
        last = _limit_number(window.get('last_reading_remaining_percent'), 0, 100)
        usable = window.get('usable_remaining_percent')
        if usable is not None:
            _limit_expect(status == 'fresh' and _limit_number(usable, 0, 100) == last)
        age = window.get('age_seconds')
        return {'status': status, 'source': source, 'window_minutes': minutes,
                'remaining_percent': last, 'usable_remaining_percent': usable,
                'reset_at': _limit_time(window.get('reset_at')),
                'observed_at': _limit_time(window.get('observed_at')),
                'age_seconds': None if age is None else _limit_number(age)}
    except LimitsRefused:
        return {'status': 'invalid', 'source': source}


def limits_manual(doc):
    _limit_expect(isinstance(doc, dict) and type(doc.get('schema_version')) is int and doc['schema_version'] == 1)
    state = doc.get('state')
    _limit_expect(state in ('ok', 'missing', 'invalid'))
    groups = doc.get('groups')
    _limit_expect(isinstance(groups, dict) and len(groups) <= MAX_LIMIT_ENTRIES)
    result = {}
    for name, group in groups.items():
        _limit_expect(isinstance(group, dict) and isinstance(group.get('windows'), dict))
        _limit_expect(len(group['windows']) <= MAX_LIMIT_ENTRIES)
        windows = {}
        for label, window in group['windows'].items():
            entry = _limit_window(window, 'manual')
            if entry['status'] != 'invalid':
                _limit_expect(window.get('source') == 'manual')
            windows[_limit_label(label)] = entry
        result[_limit_label(name)] = {'windows': windows}
    return {'state': state, 'checked_at': _limit_time(doc.get('checked_at'), False),
            'max_age_seconds': _limit_number(doc.get('max_age_seconds'), 1), 'groups': result}


def _limit_buckets(buckets, observed_at, age):
    _limit_expect(isinstance(buckets, dict) and len(buckets) <= 16)
    result = {}
    for key, bucket in buckets.items():
        _limit_expect(isinstance(bucket, dict) and isinstance(bucket.get('windows'), dict))
        windows = {}
        for name in ('primary', 'secondary'):
            window = bucket['windows'].get(name)
            if window is None:
                windows[name] = None
            elif isinstance(window, dict) and window.get('status') == 'unknown' and 'window_minutes' not in window:
                windows[name] = {'status': 'unknown', 'source': 'codex'}
            else:
                _limit_expect(isinstance(window, dict))
                windows[name] = _limit_window(dict(window, observed_at=observed_at, age_seconds=age), 'codex')
        result[_limit_label(key, LIMIT_BUCKET)] = {'windows': windows}
    return result


def limits_codex(doc):
    _limit_expect(isinstance(doc, dict) and type(doc.get('schema_version')) is int
                  and doc['schema_version'] == 1 and doc.get('provider') == 'codex')
    state = doc.get('state')
    _limit_expect(state in ('ok', 'missing', 'invalid'))
    groups = doc.get('groups')
    _limit_expect(isinstance(groups, dict) and len(groups) <= MAX_LIMIT_ENTRIES)
    result = {}
    for name, entry in groups.items():
        _limit_expect(isinstance(entry, dict) and entry.get('source') == 'codex')
        _limit_expect(entry.get('state') in ('ok', 'unknown'))
        reason = entry.get('reason')
        _limit_expect(reason is None or isinstance(reason, str) and reason in CODEX_REASONS)
        observed = _limit_time(entry.get('observed_at'))
        age = entry.get('age_seconds')
        age = None if age is None else _limit_number(age)
        view = {'state': entry['state'], 'reason': reason, 'attempted_at': _limit_time(entry.get('attempted_at')),
                'observed_at': observed, 'age_seconds': age,
                'buckets': _limit_buckets(entry.get('buckets') or {}, observed, age), 'last_good': None}
        last = entry.get('last_good')
        if last is not None:
            _limit_expect(isinstance(last, dict) and last.get('historical') is True)
            last_age = _limit_number(last.get('age_seconds'))
            last_observed = _limit_time(last.get('observed_at'), False)
            view['last_good'] = {'observed_at': last_observed, 'age_seconds': last_age,
                                 'buckets': _limit_buckets(last.get('buckets'), last_observed, last_age)}
        result[_limit_label(name)] = view
    return {'state': state, 'checked_at': _limit_time(doc.get('checked_at'), False), 'groups': result}


class LimitsObserver:
    SECTIONS = (('policy', limits_policy), ('manual', limits_manual), ('codex', limits_codex))

    def __init__(self, project, engine, ttl=LIMITS_TTL, timeout=LIMITS_TIMEOUT):
        self.project, self.engine = project, engine
        self.ttl, self.timeout = max(LIMITS_TTL, ttl), timeout
        self.lock = threading.Lock()
        self.cached = None
        self.expires = 0

    def commands(self):
        """The only argv ever run, all fixed; the project is chosen at startup."""
        project = str(self.project)
        return {'policy': [str(self.engine), 'policy', '--json'],
                'manual': [str(self.engine), 'capacity', '--project', project, 'show', '--json'],
                'codex': [str(self.engine), 'capacity', '--project', project, 'show', '--provider', 'codex', '--json']}

    def read(self):
        with self.lock:
            if self.cached is not None and time.monotonic() < self.expires:
                return self.cached
            view = {'schema_version': 1, 'source': 'installed native reads; no provider call'}
            commands = self.commands()
            for name, sanitize in self.SECTIONS:
                try:
                    view[name] = sanitize(bounded_run(commands[name], self.project / 'repo', self.timeout))
                except (LimitsRefused, OSError, subprocess.SubprocessError):
                    view[name] = {'state': 'unknown'}
            self.cached = view
            self.expires = time.monotonic() + self.ttl
            return view


class ActivityServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, port, observer, plans=None, execution=None, progress=None, files=None, limits=None):
        super().__init__(('127.0.0.1',port), ActivityHandler)
        self.observer = observer
        self.limits = limits
        self.plans = plans
        self.execution = execution
        self.progress = progress
        self.files = files
        self.dashboard = None  # bounded managed-launch metadata; absent for foreground launches
        protected = plans is not None or execution is not None or progress is not None or files is not None
        self.session_token = secrets.token_urlsafe(32) if protected else None
        self.origin = 'http://127.0.0.1:' + str(self.server_port)

    def server_close(self):
        if self.files is not None:
            self.files.close()
        if self.progress is not None:
            self.progress.close()
        if self.execution is not None:
            self.execution.close()
        super().server_close()


class ActivityHandler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass  # no request paths or query strings copied into task history

    def respond(self, code, data, content_type='application/json; charset=utf-8'):
        self.send_response(code)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'none'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
        self.end_headers()
        self.wfile.write(data)

    def error_response(self, code, error):
        self.respond(code,json.dumps(dict(schema_version=1,error=error)).encode())

    def execution_error_response(self, error):
        status, code = 503, 'native_unavailable'
        try:
            from execution_service import ERRORS, ExecutionError
            # Establish actual inheritance before reading mutable public fields;
            # a class name or a spoofed __class__ cannot grant public-error status.
            if issubclass(type(error), ExecutionError):
                public_code, public_status = error.code, error.status
                if (type(public_code) is str and type(public_status) is int
                        and ERRORS.get(public_code) == public_status):
                    status, code = public_status, public_code
        except Exception:
            pass  # Broken error properties/imports remain fixed internal errors.
        return self.error_response(status, code)

    def progress_error_response(self, error):
        status, code = 503, 'progress_unavailable'
        try:
            from progress import ERRORS, ProgressError
            if issubclass(type(error), ProgressError):
                public_code, public_status = error.code, error.status
                if (type(public_code) is str and type(public_status) is int
                        and ERRORS.get(public_code) == public_status):
                    status, code = public_status, public_code
        except Exception:
            pass
        return self.error_response(status, code)

    def files_error_response(self, error):
        status, code = 503, 'files_unavailable'
        try:
            from worker_files import ERRORS, WorkerFilesError
            if issubclass(type(error), WorkerFilesError):
                public_code, public_status = error.code, error.status
                if (type(public_code) is str and type(public_status) is int
                        and ERRORS.get(public_code) == public_status):
                    status, code = public_status, public_code
        except Exception:
            pass
        return self.error_response(status, code)

    def origin_allowed(self, write=False):
        if self.headers.get_all('Host') != [self.server.origin.removeprefix('http://')]:
            self.error_response(403, 'host_refused')
            return False
        origins = self.headers.get_all('Origin') or []
        if origins != [self.server.origin] and (write or origins):
            self.error_response(403, 'origin_refused')
            return False
        return True

    def token_allowed(self):
        supplied = self.headers.get_all('X-Unio-Session') or []
        if (len(supplied) != 1 or self.server.session_token is None
                or not hmac.compare_digest(supplied[0].encode(), self.server.session_token.encode())):
            self.error_response(403, 'session_refused')
            return False
        return True

    def do_GET(self):
        if not self.origin_allowed():
            return
        if self.path == '/api/dashboard':
            if self.server.dashboard is None:
                return self.error_response(404, 'not_found')
            return self.respond(200, json.dumps(self.server.dashboard, ensure_ascii=True).encode())
        if self.path == '/api/session':
            return self.respond(200, json.dumps(dict(schema_version=1,
                manual_drafts=self.server.plans is not None,
                execution=self.server.execution is not None,
                progress_output=self.server.progress is not None,
                worker_files=self.server.files is not None,
                token=self.server.session_token)).encode())
        if self.path.startswith('/api/worker-files'):
            if self.server.files is None:
                return self.error_response(404, 'not_found')
            if not self.token_allowed():
                return
            if self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Content-Length'):
                return self.error_response(400, 'invalid_request')
            match = re.fullmatch(r'/api/worker-files/workers(?:/([0-9a-f]{64})/files(?:/([0-9a-f]{64}))?)?', self.path)
            if match is None:
                return self.error_response(400, 'invalid_request')
            worker_id, file_id = match.groups()
            try:
                if worker_id is None:
                    value = self.server.files.workers()
                elif file_id is None:
                    value = self.server.files.files(worker_id)
                else:
                    value = self.server.files.preview(worker_id, file_id)
                return self.respond(200, json.dumps(value, ensure_ascii=True).encode())
            except Exception as error:
                return self.files_error_response(error)
        if self.path.startswith('/api/progress'):
            if self.server.progress is None:
                return self.error_response(404, 'not_found')
            if not self.token_allowed():
                return
            # Observation accepts no body/framing ambiguity, even an empty body.
            if self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Content-Length'):
                return self.error_response(400, 'invalid_request')
            match = re.fullmatch(r'/api/progress/workers/([0-9a-f]{64})(?:/runs/([0-9a-f]{64})(/output)?)?(?:\?cursor=([A-Za-z0-9_-]{1,512}))?', self.path)
            try:
                if self.path == '/api/progress/workers':
                    value = self.server.progress.workers()
                elif re.fullmatch(r'/api/progress/workers/[0-9a-f]{64}/runs', self.path):
                    value = self.server.progress.runs(self.path.split('/')[4])
                elif match:
                    worker, run, output, cursor = match.groups()
                    if cursor and not output:
                        return self.error_response(400, 'invalid_request')
                    value = self.server.progress.get(worker_id=worker, run_id=run, cursor=cursor, output=bool(output))
                else:
                    return self.error_response(400, 'invalid_request')
                return self.respond(200, json.dumps(value, ensure_ascii=True).encode())
            except Exception as error:
                return self.progress_error_response(error)

        if self.server.plans is not None and self.path.startswith('/api/plans/'):
            if not self.token_allowed():
                return
            identity = self.path.removeprefix('/api/plans/')
            if re.fullmatch('[0-9a-f]{32}', identity) is None:
                return self.error_response(400, 'invalid_plan_id')
            try:
                draft = self.server.plans.get(identity)
            except FileNotFoundError:
                return self.error_response(404, 'plan_not_found')
            except (ValueError, OSError):
                return self.error_response(503, 'draft_unavailable')
            return self.respond(200, json.dumps(draft, ensure_ascii=True).encode())

        if self.server.execution is not None and self.path.startswith('/api/jobs'):
            if not self.token_allowed():
                return
            if self.path == '/api/jobs':
                try:
                    return self.respond(200, json.dumps(dict(schema_version=1, jobs=self.server.execution.jobs()), ensure_ascii=True).encode())
                except Exception as e:
                    return self.execution_error_response(e)
            identity = self.path.removeprefix('/api/jobs/')
            if re.fullmatch('[0-9a-f]{32}', identity) is None:
                return self.error_response(400, 'invalid_request')
            try:
                job = self.server.execution.get(job_id=identity)
                return self.respond(200, json.dumps(job, ensure_ascii=True).encode())
            except Exception as e:
                return self.execution_error_response(e)

        if self.path == '/api/limits':
            # Read-only and cached; a missing observer or old native command is Unknown.
            if self.headers.get_all('Transfer-Encoding') or self.headers.get_all('Content-Length'):
                return self.error_response(400, 'invalid_request')
            if self.server.limits is None:
                view = {'schema_version': 1, 'policy': {'state': 'unknown'}, 'manual': {'state': 'unknown'},
                        'codex': {'state': 'unknown'}}
            else:
                view = self.server.limits.read()
            return self.respond(200, json.dumps(view, ensure_ascii=True, allow_nan=False).encode())
        if self.path == '/api/activity':
            snapshot = self.server.observer.read()
            if snapshot is None: return self.error_response(503,'activity_unavailable')
            return self.respond(200,json.dumps(snapshot,ensure_ascii=True).encode())
        routes = {'/':('index.html','text/html; charset=utf-8'),
                  '/activity.js':('activity.js','text/javascript; charset=utf-8'),
                  '/drafts.js':('drafts.js','text/javascript; charset=utf-8'),
                  '/theme.js':('theme.js','text/javascript; charset=utf-8'),
                  '/activity.css':('activity.css','text/css; charset=utf-8')}
        if self.path in routes:
            name, content_type = routes[self.path]
            return self.respond(200, (ASSETS/name).read_bytes(), content_type)
        if self.path in ('/jobs.js', '/worker_console.js'):
            try:
                return self.respond(200, (ASSETS/self.path[1:]).read_bytes(), 'text/javascript; charset=utf-8')
            except FileNotFoundError:
                return self.error_response(404, 'not_found')
        return self.error_response(404, 'not_found')

    def do_POST(self):
        if self.path.startswith('/api/worker-files'):
            if self.server.files is None:
                return self.error_response(404, 'not_found')
            return self.error_response(405, 'read_only')
        if self.path.startswith('/api/progress'):
            return self.error_response(405, 'read_only')
        if self.server.plans is None and self.server.execution is None:
            return self.error_response(405, 'read_only')
        if not self.origin_allowed(write=True) or not self.token_allowed():
            return
        if not (self.path == '/api/plans' or self.path.startswith('/api/jobs')):
            return self.error_response(404, 'not_found')
        if self.path.startswith('/api/jobs') and self.server.execution is None:
            return self.error_response(404, 'not_found')
        if self.path == '/api/plans' and self.server.plans is None:
            return self.error_response(404, 'not_found')

        if self.headers.get('Transfer-Encoding') is not None:
            return self.error_response(400, 'invalid_body')
        lengths = self.headers.get_all('Content-Length') or []
        if not lengths:
            return self.error_response(411, 'length_required')
        if len(lengths) != 1 or re.fullmatch('[0-9]{1,6}', lengths[0]) is None:
            return self.error_response(400, 'invalid_body')
        length = int(lengths[0])
        if length > 32768:
            return self.error_response(413, 'body_too_large')
        if self.headers.get('Content-Type', '').split(';', 1)[0].strip().lower() != 'application/json':
            return self.error_response(415, 'json_required')
        try:
            self.connection.settimeout(5)
            raw = self.rfile.read(length)
            if len(raw) != length:
                return self.error_response(400, 'invalid_body')
            body = json.loads(raw.decode('utf-8'), object_pairs_hook=unique_object)
        except TimeoutError:
            return self.error_response(408, 'body_timeout')
        except (ValueError, OSError):
            return self.error_response(400, 'invalid_body')
        if not isinstance(body, dict):
            return self.error_response(400, 'invalid_request')

        if self.path == '/api/plans':
            if set(body) != {'request'}:
                return self.error_response(400, 'invalid_request')
            try:
                draft = self.server.plans.create(body['request'])
            except ValueError:
                return self.error_response(400, 'invalid_request')
            except OSError:
                return self.error_response(503, 'draft_unavailable')
            return self.respond(201, json.dumps(draft, ensure_ascii=True).encode())

        # /api/jobs endpoints
        try:
            if self.path == '/api/jobs':
                if set(body) != {'draft_id', 'expected_hash', 'request_key'}:
                    return self.error_response(400, 'invalid_request')
                job = self.server.execution.prepare(**body)
                return self.respond(201, json.dumps(job, ensure_ascii=True).encode())

            parts = self.path.split('/')
            if len(parts) == 5 and parts[1] == 'api' and parts[2] == 'jobs':
                job_id = parts[3]
                action = parts[4]
                if re.fullmatch('[0-9a-f]{32}', job_id) is None:
                    return self.error_response(400, 'invalid_request')

                if action == 'approve':
                    if set(body) != {'expected_hash', 'approval_key', 'preview_hash'}:
                        return self.error_response(400, 'invalid_request')
                    job = self.server.execution.approve(job_id=job_id, **body)
                elif action == 'start':
                    if set(body) != {'approval_key', 'reservation_key'}:
                        return self.error_response(400, 'invalid_request')
                    job = self.server.execution.start(job_id=job_id, **body)
                elif action in ('verify', 'review', 'stop'):
                    if set(body) != {'action_key'}:
                        return self.error_response(400, 'invalid_request')
                    # use getattr so it handles stop, verify, review
                    method = getattr(self.server.execution, action)
                    job = method(job_id=job_id, **body)
                elif action == 'accept':
                    if set(body) != {'revision_hash', 'action_key'}:
                        return self.error_response(400, 'invalid_request')
                    job = self.server.execution.accept(job_id=job_id, **body)
                elif action == 'cancel':
                    if set(body) != set():
                        return self.error_response(400, 'invalid_request')
                    job = self.server.execution.cancel(job_id=job_id)
                else:
                    return self.error_response(404, 'not_found')
                return self.respond(200, json.dumps(job, ensure_ascii=True).encode())

            return self.error_response(404, 'not_found')
        except Exception as e:
            return self.execution_error_response(e)

    def reject_method(self):
        if self.path.startswith('/api/worker-files'):
            if self.server.files is None:
                return self.error_response(404, 'not_found')
            return self.error_response(405, 'read_only')
        self.error_response(405,'read_only')

    do_PUT = do_PATCH = do_DELETE = do_OPTIONS = do_HEAD = reject_method



def open_preview(origin):
    try:
        opened = webbrowser.open(origin, new=2)
    except (webbrowser.Error, OSError):
        opened = False
    if not opened:
        print('Browser could not be opened. Open ' + origin + ' manually.', flush=True)


def serve_preview(server, open_browser=False):
    if getattr(server, 'execution', None) is not None:
        print(server.origin + ' — explicit execution preview; an approved job can start one configured worker run and one configured review', flush=True)
    else:
        mode = 'manual draft preview' if getattr(server, 'plans', None) is not None else 'read-only Activity preview'
        print(server.origin + ' — ' + mode + '; no provider dispatch', flush=True)
    if getattr(server, 'progress', None) is not None:
        print('Protected Source output observation enabled for trusted startup grants; observation never dispatches', flush=True)
    if getattr(server, 'files', None) is not None:
        print('Protected worktree file observation enabled for trusted startup workers; observation never edits or dispatches', flush=True)
    if open_browser:
        # A slow desktop opener must not delay the listening observation service.
        threading.Thread(target=open_preview, args=(server.origin,), daemon=True).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def resolve_engine(explicit):
    """Use an explicit executable, or the unio command on PATH."""
    if explicit is None:
        found = shutil.which('unio')
        if not found:
            raise ValueError('unio engine not found on PATH; pass --engine')
        engine = Path(found).absolute()
    else:
        engine = Path(explicit).absolute()
    if not engine.is_file():
        raise ValueError('engine executable not found')
    return engine


def managed_dashboard(launch, server, project, installed_version):
    """Identity for a managed read-only launch; never tokens, paths or configuration."""
    if (launch is None or installed_version is None or re.fullmatch('[0-9a-f]{32}', launch) is None
            or re.fullmatch('[0-9A-Za-z.+_-]{1,64}', installed_version) is None
            or any(getattr(server, name) is not None for name in ('plans', 'execution', 'progress', 'files'))):
        return None
    return dict(schema_version=1, managed=True, mode='read-only', version=installed_version,
                project_hash=hashlib.sha256(str(project).encode('utf-8', 'surrogateescape')).hexdigest(),
                launch_nonce=launch)


def main(argv=None, *, engine_override=None, project_default=None, installed_version=None):
    # Read once and drop it so observer children never inherit the launch nonce.
    launch = os.environ.pop(DASHBOARD_LAUNCH, None)
    parser = argparse.ArgumentParser(prog='unio browser' if engine_override is not None else None,
                                     description='Unio local browser workspace')
    parser.add_argument('--project',type=Path,required=project_default is None,default=project_default,
                        help='enclosing workspace with repo/, coord/, wt/ (inferred by unio browser when inside a workspace)')
    if engine_override is None:
        parser.add_argument('--engine',type=Path,help='CLI executable supporting watch --once --json (default: unio on PATH)')
    else:
        parser.set_defaults(engine=engine_override)
    parser.add_argument('--observer-timeout',type=observer_timeout,default=DEFAULT_OBSERVER_TIMEOUT,
                        help='native observation deadline in seconds, 1 through 120 (default: 30)')
    parser.add_argument('--port',type=int,default=0,help='loopback port, 0 chooses an unused port')
    parser.add_argument('--open-browser',action='store_true',help='optionally open this loopback read-only preview in the default browser')
    parser.add_argument('--enable-plan-drafts',action='store_true',help='opt in to manual draft storage only; never starts workers')
    parser.add_argument('--enable-progress-output',action='store_true',help='allow protected Source output observation only')
    parser.add_argument('--progress-binding',action='append',default=[],help='trusted WORKER:TASK allowlist entry')
    parser.add_argument('--progress-worker',action='append',default=[],help='trusted worker grant for its latest owned native task')
    parser.add_argument('--enable-worker-files',action='store_true',help='allow read-only tracked worktree text observation')
    parser.add_argument('--files-worker',action='append',default=[],help='trusted worker whose wt/WORKER tree may be listed')
    parser.add_argument('--enable-execution',action='store_true',help='opt in to execution mode')
    parser.add_argument('--worker',type=str,help='worker label')
    parser.add_argument('--reviewer',type=str,help='reviewer label')
    parser.add_argument('--worker-company',type=str,help='worker company label')
    parser.add_argument('--reviewer-company',type=str,help='reviewer company label')
    parser.add_argument('--config-dir',type=Path,help='config dir path')
    parser.add_argument('--task-template',type=Path,help='task template path')
    options = parser.parse_args(argv)
    if not 0 <= options.port <= 65535: parser.error('port must be 0 through 65535')
    project = options.project.absolute()
    if project.is_symlink() or project.resolve() != project or any(not (project/p).is_dir() for p in ('repo','coord','wt')):
        parser.error('project must be a real enclosing Unio workspace')
    try:
        engine = resolve_engine(options.engine)
    except ValueError as error:
        parser.error(str(error))

    execution_opts = [options.worker, options.reviewer, options.worker_company, options.reviewer_company, options.config_dir, options.task_template]
    if any(opt is not None for opt in execution_opts) and not options.enable_execution:
        parser.error('partial execution settings without explicit mode refuse at startup')
    if options.enable_execution and not all(opt is not None for opt in execution_opts):
        parser.error('--enable-execution requires all execution startup inputs')

    progress_grants = bool(options.progress_binding) or bool(options.progress_worker)
    if progress_grants != options.enable_progress_output:
        parser.error('--enable-progress-output requires --progress-binding or --progress-worker; grants require explicit output mode')
    if bool(options.files_worker) != options.enable_worker_files:
        parser.error('--enable-worker-files requires --files-worker; file grants require explicit files mode')
    progress = None
    plans = None
    execution = None
    files = None
    try:
        if options.enable_plan_drafts or options.enable_execution:
            from plan_store import PlanStore
            plans = PlanStore(project)
        if options.enable_execution:
            from execution_service import ExecutionService
            execution = ExecutionService(project, engine, options.worker, options.reviewer, options.config_dir, options.task_template, options.worker_company, options.reviewer_company)
        if options.enable_progress_output:
            from progress import ProgressService
            bindings = [entry.split(':') for entry in options.progress_binding]
            if any(len(entry) != 2 for entry in bindings):
                parser.error('invalid progress binding')
            try:
                progress = ProgressService(project, engine, bindings, workers=options.progress_worker)
            except (ValueError, OSError):
                parser.error('invalid progress startup configuration')
        if options.enable_worker_files:
            from worker_files import WorkerFilesService
            try:
                files = WorkerFilesService(project, options.files_worker)
            except (ValueError, OSError):
                parser.error('invalid worker files startup configuration')
        server = ActivityServer(options.port, Observer(project, engine, timeout=options.observer_timeout), plans=plans,
                                execution=execution, progress=progress, files=files, limits=LimitsObserver(project, engine))
        server.dashboard = managed_dashboard(launch, server, project, installed_version)
        if engine_override is not None:
            print('Unio ' + installed_version + ' browser', flush=True)
            print('Project: ' + str(project), flush=True)
            print('Engine: ' + str(engine), flush=True)
            configuration = project / 'coord' / 'agents.conf'
            if not configuration.is_file():
                configuration = Path(os.environ['UNIO_CONF_DIR']) / 'agents.conf'
            print('Configuration: ' + str(configuration), flush=True)
        serve_preview(server, options.open_browser)
    finally:
        if files is not None:
            files.close()
        if progress is not None:
            progress.close()
        if plans is not None:
            plans.close()
        if execution is not None:
            execution.close()

if __name__ == '__main__':
    main()
