# Unio — Copyright (C) 2026 Daniel Mitev; Daniel Mevit (@danielmevit)
# https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE. No warranty.
"""Agent authentication readiness observation storage under coord/readiness/."""
from datetime import datetime, timedelta, timezone
import errno
import fcntl
import json
import math
import os
import re
import stat
import uuid
import time

SCHEMA_VERSION = 1
STATE = 'observations.json'
LOCK = '.observations.lock'
MAX_STATE_BYTES = 65536
MAX_AGENTS = 32
MAX_TIMESTAMP_CHARS = 64
MAX_AGE_LIMIT = 366 * 24 * 3600
DEFAULT_MAX_AGE = 900
CLOCK_SKEW = timedelta(0)
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
REQUIRED_GOOD = {'source', 'observed_at', 'loggedIn'}
ALLOWED_GOOD = {'source', 'observed_at', 'loggedIn', 'authMethod', 'apiProvider', 'subscriptionType'}
REQUIRED_FAILED = {'source', 'observed_at', 'error'}
NATIVE_LABELS = {
    'authMethod': frozenset(('claude.ai', 'api_key', 'oauth', 'none')),
    'apiProvider': frozenset(('firstParty', 'bedrock', 'vertex', 'foundry')),
    'subscriptionType': frozenset(('pro', 'max', 'team', 'enterprise', 'free')),
}
FAILURES = frozenset(('unsupported_version', 'version_failed', 'native_failed',
                      'timeout', 'output_overflow', 'invalid_status', 'launch_failed'))

def _private(info, directory=False):
    if (info.st_uid != os.getuid() or info.st_mode & 0o077
            or (not directory and (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1))):
        raise ReadinessError('readiness storage must be private, owned and single-link')

class ReadinessError(ValueError):
    """Refused input, unsafe path or unusable existing state."""

def _now(now):
    now = datetime.now(timezone.utc) if now is None else now
    if not isinstance(now, datetime) or now.tzinfo is None:
        raise ReadinessError('now must be a timezone-aware datetime')
    return now

def validate_label(value, name='label'):
    if not isinstance(value, str) or LABEL.fullmatch(value) is None:
        raise ReadinessError(f'{name} must be 1-64 ASCII letters, digits, ".", "_" or "-", '
                             'starting with a letter or digit')
    return value

def parse_timestamp(value, name='timestamp'):
    if not isinstance(value, str) or not value or len(value) > MAX_TIMESTAMP_CHARS:
        raise ReadinessError(f'{name} must be an ISO 8601 string of at most {MAX_TIMESTAMP_CHARS} characters')
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ReadinessError(f'{name} is not a valid ISO 8601 time') from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ReadinessError(f'{name} must include a timezone offset')
    try:
        return parsed.astimezone(timezone.utc)
    except (OverflowError, ValueError):
        raise ReadinessError(f'{name} is outside the supported UTC range') from None

def validate_max_age(value):
    if type(value) is not int or not 1 <= value <= MAX_AGE_LIMIT:
        raise ReadinessError(f'max age must be an integer number of seconds from 1 through {MAX_AGE_LIMIT}')
    return value

def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ReadinessError('state contains a duplicate JSON key')
        result[key] = value
    return result

def _reject_constant(name):
    raise ReadinessError(f'state contains non-finite number {name}')

def _decode(raw):
    if len(raw) > MAX_STATE_BYTES:
        raise ReadinessError(f'state exceeds {MAX_STATE_BYTES} bytes')
    try:
        text = raw.decode('utf-8')
        data = json.loads(text, object_pairs_hook=_strict_object, parse_constant=_reject_constant)
    except ReadinessError:
        raise
    except (UnicodeDecodeError, ValueError, RecursionError):
        raise ReadinessError('state is not strict UTF-8 JSON') from None
    return validate_state(data)

def _validate_observation(obs, is_good):
    if not isinstance(obs, dict):
        raise ReadinessError('observation must be an object')
    if is_good:
        if not REQUIRED_GOOD <= set(obs):
            raise ReadinessError('good observation missing required fields')
        if not set(obs) <= ALLOWED_GOOD:
            raise ReadinessError('good observation has unexpected fields')
        if type(obs['loggedIn']) is not bool:
            raise ReadinessError('loggedIn must be a boolean')
        for name, allowed in NATIVE_LABELS.items():
            if name in obs and (not isinstance(obs[name], str) or obs[name] not in allowed):
                raise ReadinessError('unsupported native status label')
    else:
        if not REQUIRED_FAILED <= set(obs):
            raise ReadinessError('failed observation missing required fields')
        if not set(obs) <= REQUIRED_FAILED:
            raise ReadinessError('failed observation has unexpected fields')
        if not isinstance(obs['error'], str) or obs['error'] not in FAILURES:
            raise ReadinessError('unsupported failure reason')

    if obs['source'] != 'native':
        raise ReadinessError('unsupported observation source')
    parse_timestamp(obs['observed_at'], 'observed time')

def validate_state(data):
    if not isinstance(data, dict) or set(data) != {'schema_version', 'agents'}:
        raise ReadinessError('state must contain exactly schema_version and agents')
    if type(data['schema_version']) is not int or data['schema_version'] != SCHEMA_VERSION:
        raise ReadinessError('unsupported state schema_version')
    agents = data['agents']
    if not isinstance(agents, dict) or len(agents) > MAX_AGENTS:
        raise ReadinessError(f'agents must be an object with at most {MAX_AGENTS} entries')
    for agent, obs in agents.items():
        validate_label(agent, 'stored agent')
        if not isinstance(obs, dict) or 'latest' not in obs or not set(obs) <= {'latest', 'last_good'}:
            raise ReadinessError('stored agent data must be an object')
        if 'last_good' in obs:
            _validate_observation(obs['last_good'], True)
        if 'latest' in obs:
            if not isinstance(obs['latest'], dict):
                raise ReadinessError('latest observation must be an object')
            is_good = 'loggedIn' in obs['latest']
            _validate_observation(obs['latest'], is_good)
        if 'last_good' in obs:
            if parse_timestamp(obs['last_good']['observed_at']) > parse_timestamp(obs['latest']['observed_at']):
                raise ReadinessError('historical observation is newer than latest')
        if 'loggedIn' in obs['latest'] and obs.get('last_good') != obs['latest']:
            raise ReadinessError('latest good observation must match last good')
    return data

class ReadinessStore:
    def __init__(self, project):
        path = os.path.abspath(os.fspath(project))
        if os.path.realpath(path) != path:
            raise ReadinessError('project must be a real path without symlinks')
        if not os.path.isdir(path):
            raise ReadinessError('project must be an existing directory')
        self.project = path

    def _open_directory(self, create):
        try:
            current = os.open(self.project, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        except OSError as error:
            raise ReadinessError(f'cannot open project: {error.strerror}') from None
        try:
            if os.fstat(current).st_uid != os.getuid():
                raise ReadinessError('project must be owned by current user')
            for name in ('coord', 'readiness'):
                if create:
                    try:
                        os.mkdir(name, mode=0o700, dir_fd=current)
                    except FileExistsError:
                        pass
                try:
                    child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current)
                except FileNotFoundError:
                    if create:
                        raise
                    return None
                except OSError as error:
                    if error.errno in (errno.ELOOP, errno.ENOTDIR):
                        raise ReadinessError(f'{name} must be a real directory, not a symlink or file') from None
                    raise
                try:
                    if os.fstat(child).st_uid != os.getuid():
                        raise ReadinessError('coordination directory must be owned by current user')
                    if name == 'readiness':
                        _private(os.fstat(child), directory=True)
                except BaseException:
                    os.close(child)
                    raise
                os.close(current)
                current = child
            result, current = current, None
            return result
        finally:
            if current is not None:
                os.close(current)

    @staticmethod
    def _read(directory):
        try:
            descriptor = os.open(STATE, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return None
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise ReadinessError('state file must not be a symlink') from None
            raise
        with os.fdopen(descriptor, 'rb') as source:
            _private(os.fstat(source.fileno()))
            raw = source.read(MAX_STATE_BYTES + 1)
        return _decode(raw)

    @staticmethod
    def _lock(directory):
        try:
            descriptor = os.open(LOCK, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK,
                                 0o600, dir_fd=directory)
        except OSError as error:
            if error.errno == errno.ELOOP:
                raise ReadinessError('lock file must not be a symlink') from None
            raise
        try:
            _private(os.fstat(descriptor))
            deadline = time.monotonic() + 2
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise ReadinessError('readiness store busy') from None
                    time.sleep(0.025)
        except BaseException:
            os.close(descriptor)
            raise
        return descriptor

    @staticmethod
    def _write(directory, data):
        validate_state(data)
        raw = (json.dumps(data, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
        if len(raw) > MAX_STATE_BYTES:
            raise ReadinessError(f'state would exceed {MAX_STATE_BYTES} bytes')
        temporary = f'.observations.{uuid.uuid4().hex}.tmp'
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                             0o600, dir_fd=directory)
        try:
            with os.fdopen(descriptor, 'wb') as output:
                output.write(raw)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, STATE, src_dir_fd=directory, dst_dir_fd=directory)
            os.fsync(directory)
        finally:
            try:
                os.unlink(temporary, dir_fd=directory)
            except FileNotFoundError:
                pass

    def record_good(self, agent, source, logged_in, auth_method=None, api_provider=None, subscription_type=None, observed_at=None, now=None):
        now = _now(now)
        validate_label(agent, 'agent')
        if observed_at is None:
            observed_at = now.isoformat()
        else:
            observed = parse_timestamp(observed_at, 'observed time')
            if observed > now + CLOCK_SKEW:
                raise ReadinessError('observed time is in the future')

        obs = {
            'source': source,
            'observed_at': observed_at,
            'loggedIn': logged_in
        }
        if auth_method is not None:
            obs['authMethod'] = auth_method
        if api_provider is not None:
            obs['apiProvider'] = api_provider
        if subscription_type is not None:
            obs['subscriptionType'] = subscription_type

        self._merge_observation(agent, obs, is_good=True)
        return obs

    def record_failure(self, agent, source, error_msg, observed_at=None, now=None):
        now = _now(now)
        validate_label(agent, 'agent')
        if observed_at is None:
            observed_at = now.isoformat()
        else:
            observed = parse_timestamp(observed_at, 'observed time')
            if observed > now + CLOCK_SKEW:
                raise ReadinessError('observed time is in the future')

        obs = {
            'source': source,
            'observed_at': observed_at,
            'error': error_msg
        }

        self._merge_observation(agent, obs, is_good=False)
        return obs

    def _merge_observation(self, agent, obs, is_good):
        _validate_observation(obs, is_good)
        directory = self._open_directory(create=True)
        try:
            lock = self._lock(directory)
            try:
                data = self._read(directory) or {'schema_version': SCHEMA_VERSION, 'agents': {}}
                agents = data['agents']
                if agent not in agents and len(agents) >= MAX_AGENTS:
                    raise ReadinessError(f'refusing more than {MAX_AGENTS} agents')

                agent_data = agents.setdefault(agent, {})

                if 'latest' in agent_data:
                    stored = parse_timestamp(agent_data['latest']['observed_at'])
                    observed = parse_timestamp(obs['observed_at'])
                    if observed == stored:
                        raise ReadinessError('duplicate reading: this agent already has that observed time')
                    if observed < stored:
                        raise ReadinessError('refusing a reading older than the stored one for this agent')

                agent_data['latest'] = obs
                if is_good:
                    agent_data['last_good'] = obs

                self._write(directory, data)
            finally:
                os.close(lock)
        finally:
            os.close(directory)

    def show(self, agent=None, max_age_seconds=DEFAULT_MAX_AGE, now=None):
        now = _now(now)
        validate_max_age(max_age_seconds)
        if agent is not None:
            validate_label(agent, 'agent')
        view = {'schema_version': SCHEMA_VERSION, 'checked_at': now.astimezone(timezone.utc).isoformat(),
                'max_age_seconds': max_age_seconds, 'state': 'missing', 'error': None, 'agents': {}}
        data = None
        directory = self._open_directory(create=False)
        if directory is not None:
            try:
                data = self._read(directory)
            except ReadinessError as error:
                view['state'], view['error'] = 'invalid', str(error)
            finally:
                os.close(directory)
        if data is not None:
            view['state'] = 'ok'
        stored = data['agents'] if data else {}
        for name in [agent] if agent is not None else sorted(stored):
            agent_data = stored.get(name)
            if not agent_data:
                view['agents'][name] = {'status': 'unknown', 'authentication': 'unknown', 'capacity': 'unknown', 'dispatch_readiness': 'unknown'}
                continue
            view['agents'][name] = self._agent_view(agent_data, max_age_seconds, now)
        return view

    def _agent_view(self, agent_data, max_age_seconds, now):
        latest = agent_data.get('latest')
        if not latest:
            return {'status': 'unknown', 'authentication': 'unknown', 'capacity': 'unknown', 'dispatch_readiness': 'unknown'}

        observed = parse_timestamp(latest['observed_at'])
        age = (now - observed).total_seconds()

        status = 'unknown'
        if observed > now + CLOCK_SKEW:
            status = 'unknown'
        elif age > max_age_seconds:
            status = 'stale'
        elif 'error' in latest:
            status = 'failed'
        else:
            status = 'fresh'

        view = {
            'status': status,
            'authentication': ('signed_in' if latest['loggedIn'] else 'signed_out') if status == 'fresh' else 'unknown',
            'capacity': 'unknown',
            'dispatch_readiness': 'unknown',
            'source': latest['source'],
            'observed_at': latest['observed_at'],
            'age_seconds': round(age, 3),
            'latest_observation': latest
        }

        if 'last_good' in agent_data:
            last_good = agent_data['last_good']
            lg_observed = parse_timestamp(last_good['observed_at'])
            lg_age = (now - lg_observed).total_seconds()
            view['last_good_observation'] = last_good
            view['last_good_age_seconds'] = round(lg_age, 3)

        return view

