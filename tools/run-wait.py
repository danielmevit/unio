# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Background launch acknowledgement and bounded task waiter.

Canonical copy, embedded byte-identically into the native save runtime by
tools/embed-run-wait.py. It runs inside that runtime's namespace and reuses
its ownership, identity and bounded-IO primitives; it is not a standalone
program.

Two surfaces live here:

* ``_bg-ack`` / ``_bg-ack-wait`` — the run-specific acknowledgement between a
  ``unio run -b`` parent and its detached child. The parent creates a fresh
  private acknowledgement file for this exact launch; the child writes
  ``started`` only after the task-addressed ownership identity is safely
  published, or ``refused`` from its exit path before that. The parent may
  report ``started`` only after it observes the matching acknowledgement, so a
  stale pidfile, a reused pid or a refused admission can never be reported as
  a start. The wait is bounded and never signals anything.

* ``_wait`` — the public ``unio wait TASK... [--any] [--timeout seconds]``.
  It binds the exact native attempt for each task: the attempt identity
  minted under the retry-state lock (``coord/retries/<task>/state.json``) is
  the single exact marker, frozen into the structured result before the
  Source runs and carried by an immutable per-attempt terminal receipt. A
  pending attempt is watched through its published shell identity (ownership
  record plus matching pidfile, verified against stable local identity:
  boot id, pid, start ticks, session id, uid); a terminal attempt is bound
  directly and resolved from its immutable receipt, so an immediately
  finishing worker or a retired control file never hides the exact exit.
  When a newer attempt replaces the task-addressed result view, the waiter
  still returns the bound attempt's original exit from its receipt; if that
  immutable evidence is lost, the outcome is Unknown — a later result is
  never substituted. The live owner proof is bound to the same native
  attempt generation as the sampled ledger entry (the generation-bound
  durable record): a same-worker replacement run that supplies its own live
  identity after the reader observed an older attempt pending is a mixed
  observation and is resampled bounded, or rejected — never attached to the
  older attempt. While polling, an exact receipt for the bound attempt takes
  precedence over any pending flag plus live identity, so an attempt whose
  terminal exit already exists is resolved from that receipt immediately.
  It is read-only: no signal, no provider or model call, no policy or worker
  mutation, no retry. Interrupt stops only the waiter. Unknown outcomes are
  reported as Unknown text with a conventional failure exit, never a magic
  exit code. After an ``--any`` winner the remaining tasks are reported as
  still in progress; timeout wording is used only on an actual deadline.
"""

BG_ACK_KEYS = {'schema_version', 'status', 'boot_id', 'worker', 'task',
               'shell_pid', 'shell_start', 'shell_sid', 'reason'}
BG_ACK_STATUSES = ('started', 'refused')
BG_ACK_LIMIT = 4096
BG_ACK_MAX_SECONDS = 900
WAIT_DEFAULT_TIMEOUT = 3600
WAIT_MAX_TIMEOUT = 86400
WAIT_POLL_SECONDS = 0.1
WAIT_BIND_SAMPLES = 3
WAIT_RESULT_LIMIT = 2 * 1024 * 1024
WAIT_ATTEMPT_LIMIT = 65536
WAIT_ATTEMPT_ID = re.compile(r'[0-9a-f]{32}')


def _ack_reason_ok(reason):
    return (isinstance(reason, str) and len(reason) <= 128
            and not any(ord(c) < 32 or ord(c) == 127 for c in reason))


def valid_bg_ack(doc):
    if (not isinstance(doc, dict) or set(doc) != BG_ACK_KEYS
            or type(doc.get('schema_version')) is not int or doc.get('schema_version') != 1):
        return False
    if doc.get('status') not in BG_ACK_STATUSES:
        return False
    if not isinstance(doc.get('boot_id'), str) or not BOOT_ID.fullmatch(doc['boot_id']):
        return False
    if not ident(doc.get('worker')) or not ident(doc.get('task')):
        return False
    if not pid_ok(doc.get('shell_pid')) or not pid_ok(doc.get('shell_sid')):
        return False
    if not tick_ok(doc.get('shell_start')):
        return False
    return _ack_reason_ok(doc.get('reason'))


def _ack_check_path(root, path):
    if not isinstance(path, str) or not path or len(path) > 4096:
        raise Refuse('unknown', 'acknowledgement path is invalid')
    locks_dir = under(root, 'coord', '.locks')
    if os.path.dirname(os.path.abspath(path)) != os.path.abspath(locks_dir):
        raise Refuse('unknown', 'acknowledgement path is outside the lock directory')
    return locks_dir


def bg_ack_write(root, path, status, worker, task, reason=''):
    """The detached child publishes its run-specific acknowledgement.

    ``started`` is written only after owner_bind has safely published the
    task-addressed identity; ``refused`` comes from the child's exit path
    before that. The file is a fresh private file created by this launch's
    parent: a missing file means the parent stopped waiting, and nothing is
    written. The acknowledging shell must be this run's own runner.
    """
    _ack_check_path(root, path)
    if status not in BG_ACK_STATUSES or not ident(worker) or not ident(task):
        raise Refuse('unknown', 'acknowledgement payload is invalid')
    if not _ack_reason_ok(reason):
        reason = ''
    ppid = os.getppid()
    info = proc_stat(ppid)
    if not isinstance(info, dict) or info['state'] in DEAD_STATES or proc_uid(ppid) != os.getuid():
        raise Refuse('unknown', 'acknowledging shell identity is unavailable')
    if not shell_is_runner(proc_argv(ppid), worker, task):
        raise Refuse('unknown', 'acknowledging shell is not the recorded runner')
    record = {'schema_version': 1, 'status': status, 'boot_id': current_boot(),
              'worker': worker, 'task': task, 'shell_pid': ppid,
              'shell_start': info['start'], 'shell_sid': info['sid'], 'reason': reason}
    if not valid_bg_ack(record):
        raise Refuse('unknown', 'acknowledgement record is malformed')
    data = canon(record) + b'\n'
    try:
        fd = os.open(path, os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    except FileNotFoundError:
        return  # the parent stopped waiting; nothing to acknowledge
    try:
        st = os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid != os.getuid():
            raise Refuse('unknown', 'acknowledgement file is not a private regular file')
        os.ftruncate(fd, 0)
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def bg_ack_wait(root, path, seconds, worker, task):
    """Bounded parent-side wait for this launch's acknowledgement.

    Prints ``started <pid>`` and returns 0 only for a valid run-specific
    ``started`` record; a ``refused`` record and a missed deadline are
    reported on stderr with exit 2. Nothing is signalled and no evidence
    older than this launch's fresh acknowledgement file is trusted.
    """
    _ack_check_path(root, path)
    if type(seconds) is not int or not 1 <= seconds <= BG_ACK_MAX_SECONDS:
        print('unio: background acknowledgement bound must be whole seconds 1..%d' % BG_ACK_MAX_SECONDS,
              file=sys.stderr)
        return 2
    if not ident(worker) or not ident(task):
        print('unio: background acknowledgement identity is invalid', file=sys.stderr)
        return 2
    boot = current_boot()
    deadline = time.monotonic() + seconds
    while True:
        doc = None
        try:
            _, raw = read_path(path, BG_ACK_LIMIT)
        except (OSError, Refuse):
            raw = None
        if raw is not None:
            try:
                doc = strict_json(raw, BG_ACK_LIMIT, 'background acknowledgement')
            except (Refuse, ValueError):
                doc = None
        if (isinstance(doc, dict) and valid_bg_ack(doc) and doc['boot_id'] == boot
                and doc['worker'] == worker and doc['task'] == task):
            if doc['status'] == 'started':
                # The acknowledgement itself is the proof this launch reached
                # readiness; a very fast completion may already have exited.
                print('started %d' % doc['shell_pid'])
                return 0
            print("unio: background run refused before identity was published (%s); "
                  'no start is claimed; inspect the rejection report'
                  % (doc['reason'] or 'refused'), file=sys.stderr)
            return 2
        if time.monotonic() >= deadline:
            print('unio: background start Unknown: no run-specific acknowledgement from the '
                  'detached child within %d seconds; it may still be starting — check unio status '
                  'and the report; nothing was signalled' % seconds, file=sys.stderr)
            return 2
        time.sleep(0.05)


def _wait_result_doc(root, worker, task):
    """Bounded read of one structured result record; never trusts its shape."""
    try:
        _, data = read_path(under(root, 'coord', 'results', worker, task + '.json'), WAIT_RESULT_LIMIT)
    except FileNotFoundError:
        return None
    except (OSError, Refuse):
        return 'unproved'
    try:
        doc = strict_json(data, WAIT_RESULT_LIMIT, 'structured result')
    except (Refuse, ValueError):
        return 'unproved'
    return doc if isinstance(doc, dict) else 'unproved'


def _wait_process(doc):
    """(state, exit_code) from a result record, or (None, None) if unproved."""
    if not isinstance(doc, dict):
        return None, None
    process = doc.get('process')
    if not isinstance(process, dict):
        return None, None
    state = process.get('state')
    if state == 'running':
        return 'running', None
    if state not in ('succeeded', 'failed'):
        return None, None
    code = process.get('exit_code')
    if type(code) is not int or not 0 <= code <= 255:
        return None, None
    return state, code


def _wait_retry_state(root, task):
    """Bounded read of the task's native attempt ledger; never trusts shape."""
    try:
        _, data = read_path(under(root, 'coord', 'retries', task, 'state.json'),
                            WAIT_ATTEMPT_LIMIT)
    except FileNotFoundError:
        return None
    except (OSError, Refuse):
        return 'unproved'
    try:
        doc = strict_json(data, WAIT_ATTEMPT_LIMIT, 'native attempt ledger')
    except (Refuse, ValueError):
        return 'unproved'
    return doc if isinstance(doc, dict) else 'unproved'


def _wait_attempt(latest, worker):
    """The exact native attempt record for one worker, or None if unproved."""
    if not isinstance(latest, dict) or not ident(worker):
        return None
    attempt = latest.get(worker)
    if (not isinstance(attempt, dict) or set(attempt) != {'id', 'pending', 'failed'}
            or not isinstance(attempt['id'], str)
            or WAIT_ATTEMPT_ID.fullmatch(attempt['id']) is None
            or type(attempt['pending']) is not bool or type(attempt['failed']) is not bool):
        return None
    return attempt


def _wait_receipt(root, worker, task, attempt_id):
    """Bounded read of one attempt's immutable terminal receipt.

    Returns the validated receipt document, None when no receipt exists, or
    'unproved' when one exists but cannot be trusted.
    """
    try:
        _, data = read_path(under(root, 'coord', 'results', worker,
                                  task + '.attempts', attempt_id + '.json'),
                            WAIT_ATTEMPT_LIMIT)
    except FileNotFoundError:
        return None
    except (OSError, Refuse):
        return 'unproved'
    try:
        doc = strict_json(data, WAIT_ATTEMPT_LIMIT, 'attempt receipt')
    except (Refuse, ValueError):
        return 'unproved'
    if not isinstance(doc, dict):
        return 'unproved'
    if (type(doc.get('schema_version')) is not int or doc['schema_version'] != 1
            or doc.get('worker') != worker or doc.get('task') != task
            or doc.get('attempt_id') != attempt_id
            or doc.get('state') not in ('succeeded', 'failed')
            or type(doc.get('exit_code')) is not int
            or not 0 <= doc['exit_code'] <= 255):
        return 'unproved'
    return doc


def wait_bind(root, task):
    """Bind the exact native attempt recorded for one task, or refuse.

    The attempt identity minted under the retry-state lock is the single
    exact marker. The public ownership record, when present, selects the
    worker; without one, a ledger naming exactly one worker still identifies
    the attempt unambiguously, and a ledger naming several workers is
    refused rather than guessed (several handles could match — use the
    ownership record's worker by waiting while the run is live, or wait one
    worker's task at a time after the fact). A pending attempt is watched
    through its published shell identity (ownership record plus matching
    pidfile); a terminal attempt is bound directly and resolved from its
    immutable receipt, so a worker that exits immediately, or a control
    file already retired, never hides the exact exit. Nothing is modified:
    bad evidence is reported, never cleaned here.

    The live owner proof is bound to the same native attempt generation as
    the sampled ledger entry: the retry ledger itself is the small
    generation-bound durable record, so after the ownership/pid sample the
    ledger is re-read and must still name the sampled attempt. A same-worker
    replacement run can otherwise supply its own live identity after the
    reader observed an older attempt pending, although that older attempt's
    terminal exit already exists. Such a mixed observation is never bound:
    the sample is resampled a bounded number of times and then rejected.

    Returns (binding, None) on success or (None, (kind, message)) when the
    task has no observable attempt or its identity is stale or malformed.
    """
    last_failure = ('stale', 'the attempt generation kept changing while it was bound')
    for _ in range(WAIT_BIND_SAMPLES):
        state = _wait_retry_state(root, task)
        if state is None:
            return None, ('no-attempt', 'no native attempt ledger for this task')
        if state == 'unproved':
            return None, ('malformed', 'native attempt ledger is unreadable')
        latest = state.get('latest')
        if (state.get('task') != task or type(state.get('schema_version')) is not int
                or state['schema_version'] != 1 or not isinstance(latest, dict)):
            return None, ('malformed', 'native attempt ledger is malformed')
        try:
            own = load_owner(under(root, 'coord', 'reports', task + '.own'))
        except FileNotFoundError:
            own = None
        except Refuse as refused:
            return None, ('malformed', refused.message)
        if own is not None and own['task'] != task:
            return None, ('malformed', 'ownership record names another task')
        if own is not None:
            worker = own['worker']
        elif len(latest) == 1:
            worker = next(iter(latest))
        else:
            return None, ('no-attempt', 'several workers recorded attempts for this task '
                                        'and no public ownership record selects one')
        attempt = _wait_attempt(latest, worker)
        if attempt is None:
            return None, ('malformed', 'native attempt record for this worker is unreadable')
        binding = {'worker': worker, 'task': task, 'attempt_id': attempt['id'],
                   'pending': attempt['pending'], 'shell_pid': None,
                   'shell_start': None, 'shell_sid': None}
        if not attempt['pending']:
            return binding, None
        if own is None:
            # The generation may have moved on (controls retired, replacement
            # run not yet published); confirm against the ledger on resample.
            last_failure = ('stale', 'the recorded attempt is pending but its public '
                                     'ownership record is gone')
            continue
        try:
            _, raw = read_path(under(root, 'coord', 'reports', task + '.pid'), 32)
        except FileNotFoundError:
            last_failure = ('stale', 'pid file is missing while the attempt is pending')
            continue
        except (OSError, Refuse):
            return None, ('malformed', 'pid file is unreadable')
        if not re.fullmatch(rb'[1-9][0-9]{0,8}\n?', raw):
            return None, ('malformed', 'pid file is not a valid background pid')
        if int(raw) != own['shell_pid']:
            return None, ('stale', 'pid file does not match the recorded ownership')
        # Same-generation check: the generation-bound ledger must still name
        # the sampled attempt after the ownership/pid sample was taken.
        state = _wait_retry_state(root, task)
        if state == 'unproved':
            return None, ('malformed', 'native attempt ledger is unreadable')
        latest = state.get('latest') if isinstance(state, dict) else None
        attempt2 = _wait_attempt(latest, worker) if isinstance(latest, dict) else None
        if (attempt2 is None or attempt2['id'] != attempt['id']
                or attempt2['pending'] != attempt['pending']):
            # Mixed observation (e.g. a same-worker run B supplied its live
            # identity after A was observed pending): resample, bounded.
            last_failure = ('stale', 'the attempt generation changed while its live '
                                     'ownership was read; mixed observations are rejected')
            continue
        binding.update(shell_pid=own['shell_pid'], shell_start=own['shell_start'],
                       shell_sid=own['shell_sid'])
        return binding, None
    return None, last_failure


def _wait_live(binding):
    """Stable local identity: same pid, start ticks, session and uid, not dead."""
    info = proc_stat(binding['shell_pid'])
    if not isinstance(info, dict) or info['state'] in DEAD_STATES:
        return False
    if info['start'] != binding['shell_start'] or info['sid'] != binding['shell_sid']:
        return False
    return proc_uid(binding['shell_pid']) == os.getuid()


def _wait_resolve(root, binding):
    """The bound attempt's exact terminal outcome; never a later result.

    The immutable per-attempt receipt is authoritative: it survives a newer
    attempt replacing the task-addressed result view. The structured result
    is consulted only while it still names the bound attempt (same frozen
    attempt identity); anything else is reported as Unknown — a later
    attempt's result is never substituted for the bound one.
    """
    receipt = _wait_receipt(root, binding['worker'], binding['task'], binding['attempt_id'])
    if isinstance(receipt, dict):
        return ('exit', receipt['exit_code'])
    doc = _wait_result_doc(root, binding['worker'], binding['task'])
    if isinstance(doc, dict) and doc.get('attempt_id') == binding['attempt_id']:
        state, code = _wait_process(doc)
        if state in ('succeeded', 'failed'):
            return ('exit', code)
        if state == 'running':
            return ('unknown', 'the bound attempt ended without recording its exit '
                              '(interrupted or crashed; inspect unio report)')
    return ('unknown', 'the immutable receipt for the bound attempt is unavailable '
                       'and no later result may be substituted')


def _wait_last_recorded(root, task):
    """Read-only context: the newest stored result for a task, any worker."""
    try:
        workers = sorted(os.listdir(under(root, 'coord', 'results')))
    except OSError:
        return None
    best = None
    for worker in workers[:64]:
        if not ident(worker):
            continue
        doc = _wait_result_doc(root, worker, task)
        state, code = _wait_process(doc)
        if state is None:
            continue
        updated = doc.get('updated_at') if isinstance(doc, dict) else None
        key = updated if isinstance(updated, str) else ''
        if best is None or key > best[0]:
            best = (key, worker, state, code)
    return best


def _wait_timeout(value):
    if not isinstance(value, str) or not re.fullmatch(r'[0-9]{1,5}', value):
        return None
    seconds = int(value)
    return seconds if 1 <= seconds <= WAIT_MAX_TIMEOUT else None


def wait_main(root, args):
    """Public ``unio wait`` entry: bind, watch, report; read-only throughout.

    Deterministic contract: tasks are bound in argument order (duplicates are
    refused); a task that cannot be bound fails the whole wait before any
    watching starts. Without ``--any`` every bound attempt is watched; the
    exit is 2 if any bound attempt is still running at the deadline or its
    outcome is Unknown, else 1 if any recorded exit is nonzero, else 0 —
    with a single task the worker's actual exit code is returned. A partial
    completion at the deadline is therefore never reported as success: the
    still-running attempts count as incomplete even when another task
    completed normally. With ``--any`` the first bound attempt to end
    (ties in argument order) decides: its actual exit code when known, else
    2; the tasks that have not ended are reported as still in progress, and
    timeout wording is used only when the deadline actually passed.
    Unknown is always reported as text with a conventional failure exit,
    never a magic exit code.
    """
    any_mode = False
    timeout = WAIT_DEFAULT_TIMEOUT
    tasks = []
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == '--any':
            any_mode = True
        elif arg == '--timeout':
            index += 1
            if index >= len(args):
                print('wait: --timeout requires a whole-second value (1..%d)' % WAIT_MAX_TIMEOUT,
                      file=sys.stderr)
                return 2
            timeout = _wait_timeout(args[index])
            if timeout is None:
                print('wait: --timeout must be whole seconds 1..%d' % WAIT_MAX_TIMEOUT,
                      file=sys.stderr)
                return 2
        elif arg.startswith('--timeout='):
            timeout = _wait_timeout(arg[len('--timeout='):])
            if timeout is None:
                print('wait: --timeout must be whole seconds 1..%d' % WAIT_MAX_TIMEOUT,
                      file=sys.stderr)
                return 2
        elif arg.startswith('-'):
            print("wait: unknown option '%s'" % arg[:64], file=sys.stderr)
            return 2
        else:
            task = arg[:-3] if arg.endswith('.md') else arg
            if not ident(task):
                print("wait: invalid task id '%s'" % arg[:64], file=sys.stderr)
                return 2
            if task in tasks:
                print("wait: duplicate task '%s'" % task, file=sys.stderr)
                return 2
            tasks.append(task)
        index += 1
    if not tasks:
        print('usage: unio wait <task-id>... [--any] [--timeout seconds]', file=sys.stderr)
        return 2

    bindings = []
    for task in tasks:
        binding, failure = wait_bind(root, task)
        if binding is None:
            kind, message = failure
            line = "wait: task '%s': %s; nothing is bound" % (task, message)
            if kind == 'no-attempt':
                last = _wait_last_recorded(root, task)
                if last is None:
                    line += "; no stored result for this task either"
                else:
                    line += ("; last stored result (NOT bound to an observed attempt): "
                             "worker %s, %s, exit %s" % (last[1], last[2], last[3]))
            print(line, file=sys.stderr)
            return 2
        bindings.append(binding)

    def describe(binding, outcome):
        where = "task '%s' (worker %s)" % (binding['task'], binding['worker'])
        if outcome is None:
            if deadline_hit:
                return 'wait: %s: still running (timeout after %ds; no signal was sent)' % (where, timeout)
            # The wait ended early (an --any winner): the remaining work is
            # still in progress; timeout wording is only for a real deadline.
            return 'wait: %s: still running (remaining work still in progress; no signal was sent)' % where
        if outcome[0] == 'exit':
            return 'wait: %s: exit %d' % (where, outcome[1])
        return 'wait: %s: completion Unknown (%s)' % (where, outcome[1])

    def stop_on_signal(signum, frame):
        print('wait: interrupted; the waited attempts were not signalled', file=sys.stderr)
        raise SystemExit(143)

    previous_term = signal.signal(signal.SIGTERM, stop_on_signal)
    try:
        deadline = time.monotonic() + timeout
        outcomes = {}
        deadline_hit = False
        while True:
            for position, binding in enumerate(bindings):
                if position in outcomes:
                    continue
                # An exact receipt for the bound attempt takes precedence
                # while polling: a pending flag plus a live shell identity
                # (which a same-worker replacement run may have supplied)
                # never hides the bound attempt's own terminal exit.
                receipt = _wait_receipt(root, binding['worker'], binding['task'],
                                       binding['attempt_id'])
                if isinstance(receipt, dict):
                    outcomes[position] = ('exit', receipt['exit_code'])
                elif binding['pending'] and _wait_live(binding):
                    continue
                else:
                    outcomes[position] = _wait_resolve(root, binding)
            if outcomes and (any_mode or len(outcomes) == len(bindings)):
                break
            if time.monotonic() >= deadline:
                deadline_hit = True
                break
            time.sleep(WAIT_POLL_SECONDS)
    except KeyboardInterrupt:
        print('wait: interrupted; the waited attempts were not signalled', file=sys.stderr)
        return 130
    finally:
        signal.signal(signal.SIGTERM, previous_term)

    for position, binding in enumerate(bindings):
        print(describe(binding, outcomes.get(position)))
    if not outcomes:
        print('wait: timeout after %ds; no bound attempt ended; nothing was signalled' % timeout,
              file=sys.stderr)
        return 2
    if any_mode:
        first = outcomes[min(outcomes)]
        return first[1] if first[0] == 'exit' else 2
    if len(bindings) == 1:
        only = outcomes.get(0)
        return only[1] if only is not None and only[0] == 'exit' else 2
    # Every bound attempt must have ended with a recorded exit; one still
    # running at the deadline makes the whole wait incomplete (exit 2), even
    # when another task completed normally with exit 0.
    for position in range(len(bindings)):
        outcome = outcomes.get(position)
        if outcome is None or outcome[0] != 'exit':
            return 2
    return 1 if any(outcomes[position][1] != 0 for position in outcomes) else 0
