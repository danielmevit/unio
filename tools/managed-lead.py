#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Managed lead-session core: private multi-turn lead state controller.

Importable backend component for persistent multi-turn lead sessions. It
owns the session state record, idempotent owner request IDs and a bounded
output journal under ``coord/sessions/``. It never launches a provider,
never acquires or bypasses native account slots, and makes no model calls:
the future native caller supplies the already-authorized lead reservation,
the owned transport and the authority/ownership decisions through injected
callables. This is a trusted-host, same-user component; it does not provide
operating-system isolation.

Enforced by this component:
- stable opaque lead session identity and monotonic generation; the role is
  explicitly ``lead`` and worker-role records are refused;
- distinct ``idle``, ``pending``, ``running``, ``outcome_unknown`` and
  ``terminal`` (history-only) states; ending one turn permits another
  authorized owner turn and is not proof of task delivery, passing checks,
  a successful process or human acceptance;
- bounded next-turn input (<= 8192 UTF-8 bytes, nonempty, no NUL) accepted
  only with the exact session/generation, a positive injected lead
  authority and current ownership, all checked before any transport call;
- idempotent owner request IDs: intent is reserved durably BEFORE the
  transport call; an identical replay returns the recorded result without
  another call, changed content refuses, and an ambiguous or crashed
  submission stays ``outcome_unknown`` and is never replayed or resent;
  request storage is bounded and refuses on exhaustion instead of evicting
  recorded IDs;
- provider observations (turn started, terminal, owner, output) are
  accepted only for the matching recorded session/generation/turn;
  reopening after a host crash never creates a provider turn and never
  auto-resumes: pending work stays explicitly uncertain until an authorized
  matching reconciliation observation arrives;
- bounded append-only output journal with monotonic cursors and explicit
  gap/truncation reporting; only selected text and lifecycle facts are
  stored, never full provider envelopes, credentials or account IDs;
- private state paths defended against traversal, symlinks, unsupported
  file types, loose permissions and malformed or oversized content.

The future native caller still owns: native admission and the lead
reservation, real account mappings, owner grants, STOP semantics, slot
release, process/platform backends, and counting the registered lead
exactly once. See docs/development/MANAGED-LEAD-CORE.md.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import time
import uuid

MAX_INPUT_BYTES = 8192
STATE_BOUND = 512 * 1024
RECORD_BOUND = 64 * 1024
ARCHIVE_BOUND = 1024 * 1024
PAGE_BOUND = 256 * 1024
DEFAULT_LIMIT = 100
MAX_LIMIT = 500
MAX_REQUESTS = 64
HISTORY_BOUND = 32
LOCK_WAIT = 5.0
# Writers keep headroom for a complete closing marker; cursor is archive-bounded.
MARKER_HEADROOM = 512
INT_MIN, INT_MAX = -(2 ** 31), 2 ** 31 - 1
STATE_KEYS = frozenset("session_id role generation state workspace budget_label route model "
                       "effort effective turn last_turn history requests max_requests "
                       "turns_completed turns_failed output_cursor archive_bytes "
                       "archive_limited journal_error created_at updated_at".split())
STATES = ('idle', 'pending', 'running', 'outcome_unknown', 'terminal')
TURN_STATUS = ('completed', 'failed', 'interrupted', 'unknown')
REQUEST_STATUS = ('pending', 'accepted', 'rejected', 'outcome_unknown')
RESULT_STATUS = ('accepted', 'rejected', 'uncertain')
OUTPUT_KINDS = ('agent_message', 'command_output', 'lifecycle')
LABEL = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]{0,63}')
SESSION_ID = re.compile(r'lead-[0-9a-f]{24}')
TURN_ID = re.compile(r'turn-[0-9a-f]{16}')
SHA256 = re.compile(r'[0-9a-f]{64}')
CAUTION = ('recorded state is not proof of task delivery, passing checks, '
           'a successful process or human acceptance')


class Refusal(Exception):
    """A controlled refusal or persistence error; effects may already be committed."""


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())


def safe_path(path):
    path = Path(path).absolute()
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise Refusal('unsafe path')
    return path


def _sessions_dir(root):
    path = safe_path(Path(root) / 'coord' / 'sessions')
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path, 0o700)
    except OSError as exc:
        raise Refusal("session directory unavailable") from exc
    return path


def _read_owned_file(path, bound):
    safe_path(path)
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise Refusal('unsafe state file')
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid() or st.st_mode & 0o077
                or st.st_size > bound):
            raise Refusal('unsafe state file')
        with os.fdopen(fd, 'rb') as stream:
            fd = None
            data = stream.read(bound + 1)
        if len(data) > bound:
            raise Refusal('state bound exceeded')
        return data
    except OSError as exc:
        raise Refusal("state read failed") from exc
    finally:
        if fd is not None:
            os.close(fd)


def _atomic_write(path, data):
    safe_path(path)
    # Never open a predictable stale name, even with O_NOFOLLOW: hardlinks
    # would still truncate another inode. Same-user hostile races are outside
    # this trusted-host component's isolation guarantees.
    if path.exists():
        _read_owned_file(path, STATE_BOUND)
    tmp = path.parent / ('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    fd = None
    created = False
    try:
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL
                     | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
        created = True
        with os.fdopen(fd, 'wb') as stream:
            fd = None
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        dir_fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError as exc:
        raise Refusal('durable state write failed') from exc
    finally:
        if fd is not None:
            os.close(fd)
        if created:
            try:
                os.unlink(tmp)
            except FileNotFoundError:
                pass
            except OSError as exc:
                raise Refusal('state temp cleanup failed') from exc


def _append_owned(path, line):
    safe_path(path)
    try:
        fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError:
        raise Refusal('unsafe output journal')
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid() or st.st_mode & 0o077):
            raise Refusal('unsafe output journal')
        view = memoryview(line)
        while view:
            written = os.write(fd, view)
            if not written:
                raise OSError('short journal write')
            view = view[written:]
        os.fsync(fd)
    except OSError as exc:
        raise Refusal("output journal write failed") from exc
    finally:
        try:
            os.close(fd)
        except OSError as exc:
            raise Refusal('output journal close failed') from exc


def _acquire_lock(path):
    try:
        import fcntl
    except ImportError:
        raise Refusal('session locking unsupported on this platform')
    safe_path(path)
    try:
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    except OSError:
        raise Refusal('unsafe lock file')
    try:
        st = os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                or st.st_uid != os.getuid() or st.st_mode & 0o077):
            raise Refusal('unsafe lock file')
        deadline = time.monotonic() + LOCK_WAIT
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return fd
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise Refusal('session state busy')
                time.sleep(0.02)
    except OSError as exc:
        os.close(fd)
        raise Refusal("session lock failed") from exc
    except BaseException:
        os.close(fd)
        raise


def _valid_int(value):
    return type(value) is int and INT_MIN <= value <= INT_MAX


def _validate_turn_record(record, statuses):
    return (isinstance(record, dict)
            and {'turn_id', 'generation', 'status', 'exit_code', 'ended_at'} <= record.keys()
            and isinstance(record.get('turn_id'), str) and TURN_ID.fullmatch(record['turn_id'])
            and type(record.get('generation')) is int and record['generation'] >= 1
            and record.get('status') in statuses
            and (record.get('exit_code') is None or _valid_int(record.get('exit_code')))
            and isinstance(record.get('ended_at'), str))


def _valid_unicode(value):
    try:
        if isinstance(value, str):
            value.encode('utf-8')
        elif isinstance(value, dict):
            return all(_valid_unicode(k) and _valid_unicode(v)
                       for k, v in value.items())
        elif isinstance(value, list):
            return all(_valid_unicode(v) for v in value)
        return True
    except (UnicodeError, RecursionError):
        return False


def _validate_state(doc):
    def refuse():
        raise Refusal('invalid session state')

    if (not isinstance(doc, dict) or set(doc) != STATE_KEYS
            or not _valid_unicode(doc)):
        refuse()
    if not isinstance(doc.get('session_id'), str) or not SESSION_ID.fullmatch(doc['session_id']):
        refuse()
    if doc.get('role') != 'lead':
        refuse()
    if type(doc.get('generation')) is not int or doc['generation'] < 1:
        refuse()
    if doc.get('state') not in STATES:
        refuse()
    for key in ('workspace', 'budget_label', 'route', 'model', 'effort'):
        value = doc.get(key)
        if not isinstance(value, str) or not value or '\x00' in value or len(value) > 4096:
            refuse()
    if doc.get('effective') != 'Unknown':
        refuse()
    if type(doc.get('max_requests')) is not int or not 1 <= doc['max_requests'] <= 256:
        refuse()
    turn = doc.get('turn')
    if turn is not None and not (
            isinstance(turn, dict)
            and {'turn_id', 'generation', 'delivery'} <= turn.keys()
            and isinstance(turn.get('turn_id'), str) and TURN_ID.fullmatch(turn['turn_id'])
            and type(turn.get('generation')) is int and turn['generation'] >= 1
            and turn.get('delivery') in ('unknown', 'accepted')):
        refuse()
    if doc.get('last_turn') is not None and not _validate_turn_record(doc['last_turn'], TURN_STATUS):
        refuse()
    history = doc.get('history')
    if not isinstance(history, list) or len(history) > HISTORY_BOUND:
        refuse()
    for item in history:
        if not _validate_turn_record(item, TURN_STATUS + ('rejected',)):
            refuse()
    requests = doc.get('requests')
    if not isinstance(requests, dict) or len(requests) > doc['max_requests']:
        refuse()
    for key, value in requests.items():
        if not isinstance(key, str) or not LABEL.fullmatch(key):
            refuse()
        if not (isinstance(value, dict)
                and {'sha256', 'state', 'generation', 'turn_id', 'result'} <= value.keys()
                and isinstance(value.get('sha256'), str) and SHA256.fullmatch(value['sha256'])
                and value.get('state') in REQUEST_STATUS
                and type(value.get('generation')) is int and value['generation'] >= 1
                and isinstance(value.get('turn_id'), str) and TURN_ID.fullmatch(value['turn_id'])):
            refuse()
        result = value.get('result')
        if result is not None and not (isinstance(result, dict)
                                       and result.get('state') in RESULT_STATUS):
            refuse()
    active = doc['state'] in ('pending', 'running', 'outcome_unknown')
    if active != (turn is not None):
        refuse()
    if turn is not None:
        if turn['generation'] != doc['generation']:
            refuse()
        matches = [v for v in requests.values()
                   if v['turn_id'] == turn['turn_id']
                   and v['generation'] == turn['generation']]
        if len(matches) != 1 or matches[0]['state'] == 'rejected':
            refuse()
    last_turn = doc.get('last_turn')
    if ((last_turn is not None
         and last_turn['generation'] != doc['generation'] - 1)
            or (doc['state'] == 'terminal' and last_turn is None)):
        refuse()
    if turn is not None and turn['delivery'] != (
            'accepted' if doc['state'] == 'running' else 'unknown'):
        refuse()
    seen = set()
    for key, value in requests.items():
        identity = value['turn_id']
        if identity in seen or value['generation'] > doc['generation']:
            refuse()
        seen.add(identity)
        result = value.get('result')
        if (value['state'] == 'pending') != (result is None):
            refuse()
        if result is not None and (
                result.get('session_id') != doc['session_id']
                or result.get('request_id') != key
                or type(result.get('generation')) is not int
                or result['generation'] != value['generation']
                or result.get('turn_id') != identity
                or result['state'] != {'accepted': 'accepted', 'rejected': 'rejected',
                                       'outcome_unknown': 'uncertain'}.get(value['state'])):
            refuse()
    for item in history + ([doc['last_turn']] if doc.get('last_turn') else []):
        if (item['generation'] > doc['generation']
                or (item['status'] != 'rejected'
                    and item['generation'] >= doc['generation'])
                or not any(v['turn_id'] == item['turn_id']
                           and v['generation'] == item['generation']
                           for v in requests.values())):
            refuse()
    for key in ('output_cursor', 'archive_bytes', 'turns_completed', 'turns_failed'):
        if type(doc.get(key)) is not int or doc[key] < 0:
            refuse()
    if (doc['archive_bytes'] > ARCHIVE_BOUND
            or doc['output_cursor'] > ARCHIVE_BOUND
            or doc['journal_error'] not in (None, 'journal_disagreement', 'journal_write_failed')):
        refuse()
    if type(doc.get('archive_limited')) is not bool:
        refuse()
    for key in ('created_at', 'updated_at'):
        if not isinstance(doc.get(key), str):
            refuse()
    return doc


class LeadSession:
    """Controller for one persistent lead session.

    All effects flow through the injected ``transport`` (owned by the future
    native caller), ``authority`` and ``ownership`` callables. The
    constructor and every read make zero transport/model calls.
    """

    def __init__(self, root, session_id, *, transport, authority, ownership):
        if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
            raise Refusal('invalid session id')
        self.root = safe_path(Path(root))
        self.session_id = session_id
        directory = _sessions_dir(self.root)
        self.meta_path = directory / (session_id + '.json')
        self.journal_path = directory / (session_id + '.jsonl')
        self.lock_path = directory / (session_id + '.lock')
        self.transport = transport
        self.authority = authority
        self.ownership = ownership
        self._lock_fd = None
        self._state = None
        self._output_activity = None  # retain local evidence even if its save fails
        with self._guard():
            pass  # load and validate only; zero transport/model calls

    # -- internal helpers -------------------------------------------------

    def _check_session(self, session_id):
        if not isinstance(session_id, str) or not SESSION_ID.fullmatch(session_id):
            raise Refusal('invalid session id')
        if session_id != self.session_id:
            raise Refusal('session mismatch')

    @contextlib.contextmanager
    def _guard(self):
        if self._lock_fd is not None:
            raise Refusal('reentrant session guard')
        self._lock_fd = _acquire_lock(self.lock_path)
        try:
            self._load()
            yield
        finally:
            fd, self._lock_fd = self._lock_fd, None
            os.close(fd)

    def _load(self):
        if not self.meta_path.exists():
            raise Refusal('unknown lead session')
        data = _read_owned_file(self.meta_path, STATE_BOUND)
        try:
            doc = json.loads(data)
        except (ValueError, UnicodeError, RecursionError):
            raise Refusal('invalid session state')
        self._state = _validate_state(doc)
        if self._state['session_id'] != self.session_id:
            raise Refusal('session identity mismatch')

    def _save(self):
        _validate_state(self._state)
        if self._state['session_id'] != self.session_id:
            raise Refusal('session identity mismatch')
        try:
            data = json.dumps(self._state, ensure_ascii=False).encode('utf-8')
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise Refusal('invalid session state') from exc
        if len(data) > STATE_BOUND:
            raise Refusal('state bound exceeded')
        _atomic_write(self.meta_path, data)

    def _require_authority(self, facts):
        try:
            reply = self.authority(dict(facts))
        except Exception:
            raise Refusal('lead authority unavailable')
        if (not isinstance(reply, dict) or reply.get('role') != 'lead'
                or reply.get('authorized') is not True):
            raise Refusal('lead authority refused')

    def _require_ownership(self, facts):
        try:
            current = self.ownership(dict(facts))
        except Exception:
            raise Refusal('ownership unavailable')
        if current is not True:
            raise Refusal('ownership refused')

    def _transport_fn(self):
        fn = getattr(self.transport, 'send_turn', None)
        if fn is None:
            fn = self.transport if callable(self.transport) else None
        if fn is None:
            raise Refusal('transport unavailable')
        return fn

    def _recorded_result(self, request_id, prev):
        result = prev.get('result')
        if result is None:
            return {'session_id': self.session_id, 'request_id': request_id,
                    'generation': prev['generation'], 'turn_id': prev['turn_id'],
                    'state': 'uncertain',
                    'note': 'intent reserved; transport outcome unknown'}
        return dict(result)

    def _view(self):
        state = self._state
        try:
            journal_status = ('journal_disagreement' if self._read_journal(0, 1)['disagreement']
                              else state['journal_error'] or (
                                  'archive_limit' if state['archive_limited'] else 'ok'))
        except Refusal:
            journal_status = 'Unknown'
        return {
            'session_id': state['session_id'], 'role': 'lead',
            'generation': state['generation'], 'state': state['state'],
            'workspace': state['workspace'], 'budget_label': state['budget_label'],
            'route': state['route'], 'model': state['model'],
            'requested_effort': state['effort'], 'effective': 'Unknown',
            'turn': dict(state['turn']) if state['turn'] else None,
            'last_turn': dict(state['last_turn']) if state['last_turn'] else None,
            'history': [dict(item) for item in state['history']],
            'turns_completed': state['turns_completed'],
            'turns_failed': state['turns_failed'],
            'requests_recorded': len(state['requests']),
            'max_requests': state['max_requests'],
            'output_cursor': state['output_cursor'],
            'archive_limited': state['archive_limited'],
            'journal_status': journal_status, 'journal_error': state['journal_error'],
            'created_at': state['created_at'], 'updated_at': state['updated_at'],
            'caution': CAUTION,
        }

    def _write_journal(self, line):
        if self._state['journal_error']:
            raise Refusal('output ' + self._state['journal_error'])
        page = self._read_journal(0, 1)
        if page['gap']:
            raise Refusal('output journal disagrees with state')
        _append_owned(self.journal_path, line)

    def _append_lifecycle(self, data):
        """Append a lifecycle record; never lose a terminal fact to it."""
        state = self._state
        if state['archive_limited']:
            return None
        rec = {'cursor': state['output_cursor'] + 1, 'kind': 'lifecycle',
               'data': data, 'timestamp': _now()}
        line = (json.dumps(rec, ensure_ascii=False) + '\n').encode('utf-8')
        limited = (len(line) > RECORD_BOUND or
                   state['archive_bytes'] + len(line) + MARKER_HEADROOM > ARCHIVE_BOUND)
        try:
            if limited:
                line = self._archive_marker()
            self._write_journal(line)
        except Refusal as exc:
            state['journal_error'] = ('journal_disagreement' if 'disagree' in str(exc)
                                      else 'journal_write_failed')
            return None
        state['output_cursor'] += 1
        state['archive_bytes'] += len(line)
        state['archive_limited'] = limited
        return state['output_cursor']

    def _archive_marker(self):
        marker = {'cursor': self._state['output_cursor'] + 1, 'kind': 'archive_limit',
                  'data': {'history': 'truncated; subsequent output Unknown'},
                  'timestamp': _now()}
        line = (json.dumps(marker) + '\n').encode('utf-8')
        if (len(line) > MARKER_HEADROOM
                or self._state['archive_bytes'] + len(line) > ARCHIVE_BOUND):
            raise Refusal('no room for archive marker')
        return line

    def _sanitize_output(self, kind, data):
        if not isinstance(data, dict) or not _valid_unicode(data):
            raise Refusal('invalid output data')
        if kind in ('agent_message', 'command_output'):
            if set(data) != {'delta'} or not isinstance(data['delta'], str):
                raise Refusal('invalid output delta')
            return {'delta': data['delta']}
        out = {}
        for key in ('event', 'status', 'exit_code', 'detail'):
            if key in data:
                value = data[key]
                if isinstance(value, bool) or value is not None and not isinstance(value, (str, int)):
                    raise Refusal('invalid lifecycle fact')
                if type(value) is int and not _valid_int(value):
                    raise Refusal('invalid lifecycle fact')
                if isinstance(value, str) and ('\x00' in value or len(value) > 1024):
                    raise Refusal('invalid lifecycle fact')
                out[key] = value
        if not out:
            raise Refusal('invalid lifecycle fact')
        return out

    # -- public interface -------------------------------------------------

    def status(self, *, session_id):
        """Read-only session view. Makes zero transport/model calls."""
        self._check_session(session_id)
        with self._guard():
            return self._view()

    def submit_next_turn(self, *, session_id, generation, request_id, text):
        """Reserve and submit one bounded owner turn input.

        Refuses (before any transport call) on invalid input, session or
        generation mismatch, missing/worker-role authority, missing
        ownership, an already active or uncertain turn, changed content for
        a known request ID, or exhausted request history. Intent is reserved
        durably before the transport call; the transport outcome is then
        recorded exactly once and never replayed.
        """
        self._check_session(session_id)
        if not isinstance(request_id, str) or not LABEL.fullmatch(request_id):
            raise Refusal('invalid request id')
        if type(generation) is not int or generation < 1:
            raise Refusal('invalid generation')
        if not isinstance(text, str) or not text or '\x00' in text:
            raise Refusal('invalid turn input')
        try:
            encoded = text.encode('utf-8')
        except UnicodeError:
            raise Refusal('invalid turn input')
        if len(encoded) > MAX_INPUT_BYTES:
            raise Refusal('turn input bound exceeded')
        content_sha = hashlib.sha256(encoded).hexdigest()
        transport_fn = self._transport_fn()
        with self._guard():
            state = self._state
            requests = state['requests']
            if request_id in requests:
                prev = requests[request_id]
                if prev['sha256'] != content_sha:
                    raise Refusal('changed content for request id')
                return self._recorded_result(request_id, prev)
            if state['state'] not in ('idle', 'terminal'):
                raise Refusal('session is not open for a next turn')
            if generation != state['generation']:
                raise Refusal('stale generation')
            facts = {'action': 'next_turn', 'session_id': self.session_id,
                     'generation': generation, 'request_id': request_id}
            self._require_authority(facts)
            self._require_ownership(facts)
            if len(requests) >= state['max_requests']:
                raise Refusal('request history exhausted')
            turn_id = 'turn-' + uuid.uuid4().hex[:16]
            trial = dict(state)
            trial['requests'] = {**requests, request_id: {
                'sha256': content_sha, 'state': 'pending', 'generation': generation,
                'turn_id': turn_id, 'result': None}}
            if len(json.dumps(trial, ensure_ascii=False).encode('utf-8')) > STATE_BOUND:
                raise Refusal('request history exhausted')
            requests[request_id] = trial['requests'][request_id]
            state['state'] = 'pending'
            state['turn'] = {'turn_id': turn_id, 'generation': generation,
                             'delivery': 'unknown'}
            state['updated_at'] = _now()
            self._save()  # durable intent reserved before the transport call
        # The transport call happens outside the state lock. A crash here
        # leaves the reserved intent pending: explicitly uncertain, never replayed.
        try:
            reply = transport_fn({'session_id': self.session_id,
                                  'generation': generation,
                                  'turn_id': turn_id, 'text': text})
            status = reply.get('status') if isinstance(reply, dict) else None
            if status not in ('accepted', 'rejected', 'uncertain'):
                status = 'uncertain'
        except Exception:
            status = 'uncertain'
        with self._guard():
            state = self._state
            prev = state['requests'].get(request_id)
            if prev is None or prev['state'] != 'pending':
                raise Refusal('session state changed during submission')
            # Matching activity is enough to contradict rejection, without
            # claiming that generic lifecycle output proves running inference.
            turn = state.get('turn')
            observed = (state['generation'] > generation
                        or (turn and turn['turn_id'] == turn_id
                            and (turn['delivery'] == 'accepted'
                                 or state['state'] == 'outcome_unknown'
                                 or self._output_activity == turn_id)))
            if status == 'rejected' and observed:
                status = 'uncertain'
            result = {'session_id': self.session_id, 'request_id': request_id,
                      'generation': generation, 'turn_id': turn_id,
                      'state': {'accepted': 'accepted',
                                'rejected': 'rejected'}.get(status, 'uncertain')}
            prev['state'] = {'accepted': 'accepted',
                             'rejected': 'rejected'}.get(status, 'outcome_unknown')
            prev['result'] = result
            turn = state.get('turn')
            if (state['state'] in ('pending', 'outcome_unknown') and turn
                    and turn['turn_id'] == turn_id):
                if status == 'accepted':
                    state['state'] = 'running'
                    turn['delivery'] = 'accepted'
                elif status == 'rejected':
                    state['state'] = 'idle'
                    state['turn'] = None
                    state['history'].append({'turn_id': turn_id,
                                             'generation': generation,
                                             'status': 'rejected',
                                             'exit_code': None,
                                             'ended_at': _now()})
                    del state['history'][:-HISTORY_BOUND]
                else:
                    state['state'] = 'outcome_unknown'
            state['updated_at'] = _now()
            self._save()
            return dict(result)

    def observe_turn_started(self, *, session_id, generation, turn_id):
        """Accept a provider turn-started observation for the matching turn."""
        self._check_session(session_id)
        if type(generation) is not int or generation < 1:
            raise Refusal('invalid generation')
        with self._guard():
            state = self._state
            turn = state.get('turn')
            if (not turn or turn['turn_id'] != turn_id
                    or turn['generation'] != generation
                    or state['state'] not in ('pending', 'outcome_unknown', 'running')):
                raise Refusal('mismatched turn observation')
            if state['state'] != 'running':
                state['state'] = 'running'
                turn['delivery'] = 'accepted'
                state['updated_at'] = _now()
                self._save()
            return self._view()

    def observe_terminal(self, *, session_id, generation, turn_id, status,
                        exit_code=None):
        """Accept a provider terminal observation for the matching turn.

        A terminal record preserves failures and partial state, returns the
        session to a history-only state and permits the next authorized
        owner turn. It is not proof of task delivery or acceptance.
        """
        self._check_session(session_id)
        if type(generation) is not int or generation < 1:
            raise Refusal('invalid generation')
        if status not in TURN_STATUS:
            raise Refusal('invalid terminal status')
        if exit_code is not None and not _valid_int(exit_code):
            raise Refusal('invalid exit code')
        with self._guard():
            state = self._state
            turn = state.get('turn')
            if (not turn or turn['turn_id'] != turn_id
                    or turn['generation'] != generation
                    or state['state'] not in ('pending', 'running', 'outcome_unknown')):
                raise Refusal('mismatched terminal event')
            ended = _now()
            record = {'turn_id': turn_id, 'generation': generation,
                      'status': status, 'exit_code': exit_code, 'ended_at': ended}
            state['state'] = 'terminal'
            state['turn'] = None
            state['last_turn'] = dict(record)
            state['history'].append(dict(record))
            del state['history'][:-HISTORY_BOUND]
            if status == 'completed':
                state['turns_completed'] += 1
            elif status in ('failed', 'interrupted'):
                state['turns_failed'] += 1
            state['generation'] += 1
            state['updated_at'] = ended
            self._append_lifecycle({'event': 'turn_terminal', 'status': status,
                                    'exit_code': exit_code})
            self._save()
            if state['journal_error']:
                raise Refusal('terminal saved; output ' + state['journal_error'])
            return self._view()

    def observe_owner(self, *, session_id, generation, owner):
        """Accept an ownership observation for the matching generation."""
        self._check_session(session_id)
        if type(generation) is not int or generation < 1:
            raise Refusal('invalid generation')
        if not isinstance(owner, str) or not LABEL.fullmatch(owner):
            raise Refusal('invalid owner label')
        with self._guard():
            state = self._state
            if generation != state['generation']:
                raise Refusal('mismatched ownership observation')
            self._append_lifecycle({'event': 'owner_observed', 'owner': owner})
            state['updated_at'] = _now()
            self._save()
            if state['journal_error']:
                raise Refusal('owner observation journal failed: ' + state['journal_error'])
            return self._view()

    def observe_output(self, *, session_id, generation, turn_id, kind, data):
        """Append one bounded selected output observation for a matching turn."""
        self._check_session(session_id)
        if type(generation) is not int or generation < 1:
            raise Refusal('invalid generation')
        if kind not in OUTPUT_KINDS:
            raise Refusal('unsupported output kind')
        with self._guard():
            state = self._state
            active = state.get('turn') or {}
            last = state.get('last_turn') or {}
            if not ((active.get('turn_id') == turn_id
                     and active.get('generation') == generation)
                    or (last.get('turn_id') == turn_id
                        and last.get('generation') == generation)):
                raise Refusal('mismatched output observation')
            data = self._sanitize_output(kind, data)
            if state['archive_limited']:
                raise Refusal('output archive closed')
            rec = {'cursor': state['output_cursor'] + 1, 'kind': kind,
                   'data': data, 'generation': generation, 'turn_id': turn_id,
                   'timestamp': _now()}
            line = (json.dumps(rec, ensure_ascii=False) + '\n').encode('utf-8')
            if len(line) > RECORD_BOUND:
                raise Refusal('output record bound exceeded')
            # Write uncertainty BEFORE journaling. Even a failed/absent append
            # must not let a later contradictory rejection release this turn.
            if active.get('turn_id') == turn_id and state['state'] == 'pending':
                self._output_activity = turn_id
                state['state'] = 'outcome_unknown'
                state['updated_at'] = _now()
                self._save()
            if state['archive_bytes'] + len(line) + MARKER_HEADROOM > ARCHIVE_BOUND:
                mline = self._archive_marker()
                self._write_journal(mline)
                state['output_cursor'] += 1
                state['archive_bytes'] += len(mline)
                state['archive_limited'] = True
                state['updated_at'] = _now()
                self._save()
                return {'cursor': state['output_cursor'], 'state': 'archive_limit'}
            self._write_journal(line)
            state['output_cursor'] += 1
            state['archive_bytes'] += len(line)
            state['updated_at'] = _now()
            self._save()
            return {'cursor': state['output_cursor']}

    def read_output(self, *, session_id, after=0, limit=DEFAULT_LIMIT):
        """Read bounded ordered journal records with explicit gap reporting."""
        self._check_session(session_id)
        if type(after) is not int or after < 0:
            raise Refusal('invalid output bounds')
        if type(limit) is not int or not 1 <= limit <= MAX_LIMIT:
            raise Refusal('invalid output bounds')
        with self._guard():
            return self._read_journal(after, limit)

    def _read_journal(self, after, limit):
        safe_path(self.journal_path)
        try:
            fd = os.open(self.journal_path,
                         os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError:
            raise Refusal('unsafe output journal')
        identities = {(v['turn_id'], v['generation'])
                      for v in self._state['requests'].values()}
        records, last, size, page = [], 0, 0, 0
        marker_seen = False
        gap, truncated, page_full = False, False, False
        try:
            st = os.fstat(fd)
            if (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1
                    or st.st_uid != os.getuid() or st.st_mode & 0o077):
                raise Refusal('unsafe output journal')
            gap = st.st_size > ARCHIVE_BOUND
            with os.fdopen(fd, 'rb') as stream:
                fd = None
                while size < ARCHIVE_BOUND:
                    line = stream.readline(min(RECORD_BOUND + 1,
                                               ARCHIVE_BOUND - size))
                    if not line:
                        break
                    size += len(line)
                    # Stop at the first unknown byte range. Never skip corruption.
                    if len(line) > RECORD_BOUND or not line.endswith(b'\n'):
                        gap = truncated = True
                        break
                    try:
                        rec = json.loads(line)
                        cur = rec.get('cursor') if isinstance(rec, dict) else None
                        kind = rec.get('kind') if isinstance(rec, dict) else None
                        ok = (type(cur) is int and cur == last + 1
                              and not marker_seen
                              and kind in ('agent_message', 'command_output',
                                           'lifecycle', 'archive_limit')
                              and isinstance(rec.get('data'), dict)
                              and isinstance(rec.get('timestamp'), str))
                        if ok and kind in ('agent_message', 'command_output'):
                            ok = (isinstance(rec['data'].get('delta'), str)
                                  and type(rec.get('generation')) is int
                                  and rec['generation'] >= 1
                                  and isinstance(rec.get('turn_id'), str)
                                  and TURN_ID.fullmatch(rec['turn_id'])
                                  and set(rec['data']) == {'delta'}
                                  and (rec['turn_id'], rec['generation']) in identities)
                        if ok and kind == 'lifecycle':
                            facts = rec['data']
                            ok = (bool(facts) and set(facts) <= {
                                'event', 'status', 'exit_code', 'detail', 'owner'}
                                and all(v is None or isinstance(v, str)
                                        or _valid_int(v) for v in facts.values()))
                        if ok and kind == 'archive_limit':
                            ok = rec['data'] == {
                                'history': 'truncated; subsequent output Unknown'}
                        if not ok or not _valid_unicode(rec):
                            raise ValueError('unsupported or unordered record')
                    except (ValueError, UnicodeError, RecursionError):
                        gap = truncated = True
                        break
                    last = cur
                    if kind == 'archive_limit':
                        marker_seen = True
                    if cur > after:
                        if (not page_full and len(records) < limit
                                and page + len(line) <= PAGE_BOUND):
                            records.append(rec)
                            page += len(line)
                        else:
                            page_full = truncated = True
            disagreement = (gap or last != self._state['output_cursor']
                            or size != self._state['archive_bytes']
                            or marker_seen != self._state['archive_limited'])
            gap = disagreement or marker_seen or after > last
            truncated |= gap
            return {'session_id': self.session_id, 'records': records,
                    'next_cursor': records[-1]['cursor'] if records else after,
                    'output_cursor': last, 'truncated': truncated, 'gap': gap,
                    'disagreement': disagreement}
        except OSError as exc:
            raise Refusal('output journal read failed') from exc
        finally:
            if fd is not None:
                os.close(fd)


def create_lead_session(root, *, transport, authority, ownership, workspace,
                        budget_label, route, model, effort,
                        max_requests=MAX_REQUESTS):
    """Create one new private lead session record and return its controller.

    Records the workspace, opaque shared-budget label, requested
    route/model/effort and Unknown effective settings. No credentials or
    account IDs are stored. Creation itself makes no transport call and
    grants no provider turn; native admission and the lead reservation
    remain the future caller's responsibility.
    """
    root_path = safe_path(Path(root))
    for name, value, bound in (('workspace', workspace, 4096),
                               ('budget_label', budget_label, 128),
                               ('route', route, 128), ('model', model, 128),
                               ('effort', effort, 128)):
        if not isinstance(value, str) or not value or '\x00' in value or len(value) > bound or not _valid_unicode(value):
            raise Refusal('invalid ' + name)
    if type(max_requests) is not int or not 1 <= max_requests <= 256:
        raise Refusal('invalid request bound')
    session_id = 'lead-' + uuid.uuid4().hex[:24]
    directory = _sessions_dir(root_path)
    now = _now()
    doc = {
        'session_id': session_id, 'role': 'lead', 'generation': 1,
        'state': 'idle', 'workspace': workspace, 'budget_label': budget_label,
        'route': route, 'model': model, 'effort': effort, 'effective': 'Unknown',
        'turn': None, 'last_turn': None, 'history': [], 'requests': {},
        'max_requests': max_requests, 'turns_completed': 0, 'turns_failed': 0,
        'output_cursor': 0, 'archive_bytes': 0, 'archive_limited': False,
        'journal_error': None,
        'created_at': now, 'updated_at': now,
    }
    data = json.dumps(doc, ensure_ascii=False).encode('utf-8')
    if len(data) > STATE_BOUND:
        raise Refusal('state bound exceeded')
    _atomic_write(directory / (session_id + '.json'), data)
    journal = directory / (session_id + '.jsonl')
    try:
        fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                     0o600)
    except OSError:
        raise Refusal('unsafe output journal')
    os.close(fd)
    return LeadSession(root_path, session_id, transport=transport,
                       authority=authority, ownership=ownership)
