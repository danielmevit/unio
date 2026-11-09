#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Interrupted-run observation, using private mock runs and private processes only.

Every signalled process is started by this test and its PID comes from its own
private fixture. No model, provider or unrelated process is touched.
"""
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import tempfile
import time

source = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location('run_observation', source / 'tools/run-observation.py')
ro = importlib.util.module_from_spec(spec)
sys.modules['run_observation'] = ro
spec.loader.exec_module(ro)
checks = 0


def check(label, condition=True):
    global checks
    assert condition, label
    checks += 1
    print('  orphan: ' + label, flush=True)


def old(seconds=120):
    return (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=seconds)).isoformat()


def proc_start(pid):
    raw = Path('/proc/%d/stat' % pid).read_bytes()
    return int(raw[raw.rfind(b')') + 2:].split()[19])


def digests(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (root / 'coord').rglob('*') if p.is_file() and not p.is_symlink()}


def unit(base):
    root = str(base / 'unit')
    rp = Path(root)
    worker, task = 'w', 'T1'
    for part in ('coord/results/w', 'coord/.locks', 'coord/reports/.owners/w'):
        (rp / part).mkdir(parents=True)
    result = rp / 'coord/results/w/T1.json'
    own = rp / 'coord/reports/.owners/w/T1.own'
    lock = rp / 'coord/.locks/w.lock'
    rev = dict(candidate_commit='a' * 40, base_commit='b' * 40, task_sha256='c' * 64, worktree_sha256='d' * 64)

    def record(state='running', code=None, at=None):
        doc = dict(schema_version=1, worker=worker, task=task, updated_at=at if at is not None else old(),
                   revision=rev, process=dict(state=state, exit_code=code, revision=rev))
        result.write_text(json.dumps(doc))

    def owner(**changes):
        doc = dict(schema_version=1, boot_id=ro.current_boot(), worker=worker, task=task, shell_pid=999999990,
                   shell_start=1, shell_sid=999999990, provider_pid=None, provider_sid=None, provider_start=None)
        doc.update(changes)
        if own.exists():
            own.unlink()
        own.write_text(json.dumps(doc))
        own.chmod(0o600)

    def see():
        return ro.observe(root, worker, task)

    record()
    o = see()
    check('missing metadata after grace: uncertainty, never certainty',
          o['state'] == 'completion_unknown' and o['interrupted'] is None and o['source_exit'] is None
          and o['detached_processes_ruled_out'] is False and o['blocks_readiness'] and o['owner'] == 'missing')
    check('observing creates no lock file', not lock.exists())
    check('human form says Source exit Unknown', 'Source exit: Unknown' in ro.human_lines(o))
    owner()
    o = see()
    check('dead recorded owner after grace is interrupted', o['state'] == 'completion_unknown' and o['interrupted'] is True and o['owner'] == 'absent')
    owner(boot_id='00000000-0000-4000-8000-000000000000')
    o = see()
    check('previous boot owner is interrupted', o['owner'] == 'previous_boot' and o['state'] == 'completion_unknown')
    alive = subprocess.Popen(['sleep', '60'], start_new_session=True)
    try:
        start = proc_start(alive.pid)
        owner(shell_pid=alive.pid, shell_sid=alive.pid, shell_start=start)
        o = see()
        check('live matched owner stays running', o['state'] == 'running' and o['owner'] == 'live' and o['source_exit'] is None)
        owner(shell_pid=alive.pid, shell_sid=alive.pid, shell_start=start - 1)
        o = see()
        check('reused PID is not ownership', o['owner'] == 'reused' and o['state'] == 'completion_unknown')
        check('observation never signals a process it examined', alive.poll() is None)
    finally:
        alive.kill(); alive.wait()
    leader = subprocess.Popen(['sh', '-c', 'sleep 60 & echo $!; exit 0'], stdout=subprocess.PIPE, text=True, start_new_session=True)
    member = int(leader.stdout.readline())
    leader_pid, leader_start = leader.pid, 0
    leader.wait()
    try:
        owner(shell_pid=leader_pid, shell_sid=leader_pid, shell_start=leader_start)
        o = see()
        check('surviving session member keeps Unknown, not owned or orphaned', o['state'] == 'unknown' and o['owner'] == 'session_members')
    finally:
        os.kill(member, signal.SIGKILL)
    for label, write in (('malformed', lambda: own.write_text('{nope')),
                         ('wrong identity', lambda: owner(task='OTHER')),
                         ('bool schema', lambda: owner(schema_version=True))):
        write(); own.chmod(0o600)
        check(label + ' owner is Unknown', see()['state'] == 'unknown')
    owner(); own.chmod(0o644)
    check('non-private owner is Unknown', see()['state'] == 'unknown')
    own.chmod(0o600)
    link = own.with_name('hard')
    os.link(own, link)
    check('hardlinked owner is Unknown', see()['state'] == 'unknown')
    link.unlink(); own.unlink()
    own.symlink_to(base)
    check('symlinked owner is Unknown', see()['state'] == 'unknown')
    own.unlink()
    os.mkfifo(own)
    check('FIFO owner is Unknown without blocking', see()['state'] == 'unknown')
    own.unlink()
    lock.symlink_to(base / 'elsewhere')
    check('symlinked lock is Unknown', see()['state'] == 'unknown' and see()['worker_lock'] == 'unknown')
    lock.unlink()
    lock.write_bytes(b'')
    with lock.open('rb') as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        o = see()
        check('held lock stays running with old record', o['state'] == 'running' and o['worker_lock'] == 'held')
        check('caller-held lock is not mistaken for a run', ro.observe(root, worker, task, holding=True)['state'] == 'completion_unknown')
        other_task = subprocess.Popen(['sleep', '60'], start_new_session=True)
        try:
            other = dict(schema_version=1, boot_id=ro.current_boot(), worker=worker, task='T2', shell_pid=other_task.pid,
                         shell_start=proc_start(other_task.pid), shell_sid=other_task.pid, provider_pid=None, provider_sid=None, provider_start=None)
            path = own.with_name('T2.own'); path.write_text(json.dumps(other)); path.chmod(0o600)
            o = see()
            check('lock held by a distinct proved task does not make the old record running', o['state'] == 'completion_unknown' and o['interrupted'] is None)
            path.unlink()
        finally:
            other_task.kill(); other_task.wait()
    record(at=old(0))
    o = see()
    check('fresh record with free lock stays inside grace', o['state'] == 'pending_grace' and ro.activity(o) == 'running_recorded' and o['source_exit'] is None)
    record(at=old(-3600))
    check('future time is Unknown', see()['state'] == 'unknown')
    for bad in ('', 'yesterday', '2026-01-01T00:00:00'):
        record(at=bad)
        check('invalid time %r is Unknown' % bad, see()['state'] == 'unknown')
    doc = json.loads(result.read_text()); doc.pop('updated_at'); result.write_text(json.dumps(doc))
    check('missing time is Unknown', see()['state'] == 'unknown')
    record()
    saved = os.environ.get('UNIO_ORPHAN_GRACE_SECONDS')
    try:
        for bad in ('0', '3601', '-1', '1.5', 'x', '', ' 5', '٣'):
            os.environ['UNIO_ORPHAN_GRACE_SECONDS'] = bad
            check('invalid grace %r is Unknown' % bad, see()['state'] == 'unknown')
        for good, age, state in (('1', 5, 'completion_unknown'), ('3600', 5, 'pending_grace')):
            os.environ['UNIO_ORPHAN_GRACE_SECONDS'] = good
            record(at=old(age))
            check('bounded grace %s honored' % good, see()['state'] == state)
    finally:
        if saved is None:
            os.environ.pop('UNIO_ORPHAN_GRACE_SECONDS', None)
        else:
            os.environ['UNIO_ORPHAN_GRACE_SECONDS'] = saved
    for state, code in (('succeeded', 0), ('failed', 7), ('failed', 124)):
        record(state, code)
        o = see()
        check('terminal exit %d stays exactly observed' % code, o['state'] == 'terminal' and o['source_exit'] == code and not o['blocks_readiness'])
    result.write_text('{broken')
    o = see()
    check('malformed record is Unknown and non-ready', o['state'] == 'unknown' and o['blocks_readiness'])
    record('running', 3)
    check('running record with an exit code is malformed', see()['state'] == 'unknown')
    result.unlink(); result.symlink_to(base)
    check('symlinked record is Unknown', see()['state'] == 'unknown')
    result.unlink(); record()
    # An exit crossing the reads: first sample running, later samples terminal.
    original, calls = ro._read_owner, []

    def crossing(*args):
        calls.append(1)
        if len(calls) == 1:
            record('succeeded', 0)
        return original(*args)
    ro._read_owner = crossing
    try:
        o = see()
    finally:
        ro._read_owner = original
    check('exit racing the observation resolves to its recorded exit', o['state'] == 'terminal' and o['source_exit'] == 0)
    record()
    counter = [0]

    def churn(*args):
        counter[0] += 1
        doc = json.loads(result.read_text()); doc['updated_at'] = old(100 + counter[0]); result.write_text(json.dumps(doc))
        return original(*args)
    ro._read_owner = churn
    try:
        o = see()
    finally:
        ro._read_owner = original
    check('evidence that never settles stays Unknown', o['state'] == 'unknown' and 'evidence changed while observing' in o['reasons'])

    # 1. Lead malformed result reproductions:
    # 15000 nested arrays (30001 bytes) in result record must not cause RecursionError
    result.write_text('[' * 15000 + '0' + ']' * 15000)
    o = see()
    check('15000 nested array in result returns Unknown without traceback',
          o['state'] == 'unknown' and o['blocks_readiness'])

    # 15000 nested arrays in owner file must not cause RecursionError
    record('running')
    own.write_text('[' * 15000 + '0' + ']' * 15000)
    own.chmod(0o600)
    o = see()
    check('15000 nested array in owner returns Unknown without traceback',
          o['state'] == 'unknown' and o['blocks_readiness'])

    # Duplicate state keys in result process
    result.write_text('{"schema_version":1,"worker":"w","task":"T1","process":{"state":"running","state":"succeeded","exit_code":0}}')
    o = see()
    check('duplicate state key in result returns Unknown and non-ready',
          o['state'] == 'unknown' and o['blocks_readiness'])

    # Duplicate keys in owner document
    own.write_text('{"schema_version":1,"schema_version":1,"boot_id":%s}' % json.dumps(ro.current_boot()))
    own.chmod(0o600)
    record('running')
    check('duplicate key in owner document returns Unknown', see()['state'] == 'unknown')

    # Missing schema_version in result
    result.write_text('{"worker":"w","task":"T1","process":{"state":"succeeded","exit_code":0}}')
    check('missing schema_version in result returns Unknown and non-ready',
          see()['state'] == 'unknown' and see()['blocks_readiness'])

    # Invalid schema_version type
    result.write_text('{"schema_version":true,"worker":"w","task":"T1","process":{"state":"succeeded","exit_code":0}}')
    check('boolean schema_version in result returns Unknown', see()['state'] == 'unknown')

    # Terminal exit conflicts: failed with exit 0
    record('failed', 0)
    o = see()
    check('failed exit 0 conflict is Unknown and non-ready',
          o['state'] == 'unknown' and o['blocks_readiness'])

    # Terminal exit conflicts: succeeded with exit 1
    record('succeeded', 1)
    check('succeeded exit 1 conflict is Unknown', see()['state'] == 'unknown')

    # Nonfinite JSON constant
    result.write_text('{"schema_version":1,"worker":"w","task":"T1","process":{"state":"succeeded","exit_code":NaN}}')
    check('nonfinite NaN in result returns Unknown', see()['state'] == 'unknown')

    # Legacy failed record with exit_code None preserves Unknown source exit without fabricating 0
    record('failed', None)
    o = see()
    check('legacy failed record with None exit is terminal with Unknown source_exit',
          o['state'] == 'terminal' and o['source_exit'] is None and ro.source_exit_text(o) == 'Unknown'
          and not o['blocks_readiness'])

    # 2. Identifier compatibility (native-safe IDs including colon/Unicode/punctuation):
    for good_id in ('T:1', 'T.sub', 'T_1', 'T+1', 'T@1', 'T-α', 'T:sub:2'):
        check('native-safe identifier %r accepted by _ident' % good_id, ro._ident(good_id))
    for bad_id in ('', '.', '..', 'a..b', '-leading', 'a/b', 'a\\b', 'a b', 'a\nb', 'a' * 201):
        check('unsafe identifier %r rejected by _ident' % bad_id, not ro._ident(bad_id))

    # Test observe, workers_for, status_lines with colon-separated task
    colon_dir = rp / 'coord/results/w:sub'
    colon_dir.mkdir(parents=True, exist_ok=True)
    doc_colon = dict(schema_version=1, worker='w:sub', task='T:1', updated_at=old(120),
                     revision=rev, process=dict(state='failed', exit_code=124, revision=rev))
    (colon_dir / 'T:1.json').write_text(json.dumps(doc_colon))
    o_colon = ro.observe(root, 'w:sub', 'T:1')
    check('colon identifier T:1 observes recorded terminal exit 124',
          o_colon['state'] == 'terminal' and o_colon['source_exit'] == 124 and not o_colon['blocks_readiness'])
    workers_colon, trunc_colon = ro.workers_for(root, 'T:1')
    check('workers_for finds worker with colon identifier', 'w:sub' in workers_colon and not trunc_colon)
    status_colon = ro.status_lines(root)
    check('status_lines executes without error with colon identifiers', isinstance(status_colon, list))

    # 3. Bounded directory enumeration before sorting/materialization:
    enum_root = base / 'enum_test'
    enum_results = enum_root / 'coord/results'
    enum_results.mkdir(parents=True)
    for i in range(7):
        (enum_results / ('worker%d' % i)).mkdir()
    tracker_counts = {}
    original_scandir = ro.os.scandir

    class Tracker:
        def __init__(self, path):
            self.path = os.fspath(path)
            self.inner = original_scandir(path)
        def __enter__(self):
            self.inner.__enter__()
            return self
        def __exit__(self, *args):
            return self.inner.__exit__(*args)
        def __iter__(self):
            return self
        def __next__(self):
            entry = next(self.inner)
            tracker_counts[self.path] = tracker_counts.get(self.path, 0) + 1
            return entry

    ro.os.scandir = Tracker
    old_max_workers = ro.MAX_WORKERS
    ro.MAX_WORKERS = 2
    try:
        obs, truncated = ro.project_observations(str(enum_root))
        check('worker enumeration is capped while iterating before sorting',
              tracker_counts.get(str(enum_results), 0) <= 3 and truncated)
    finally:
        ro.os.scandir = original_scandir
        ro.MAX_WORKERS = old_max_workers

    # Record enumeration cap
    rec_worker = enum_results / 'w_rec'
    rec_worker.mkdir()
    for i in range(7):
        r_doc = dict(schema_version=1, worker='w_rec', task='R%d' % i, updated_at=old(120),
                     revision=rev, process=dict(state='succeeded', exit_code=0, revision=rev))
        (rec_worker / ('R%d.json' % i)).write_text(json.dumps(r_doc))
    tracker_counts.clear()
    ro.os.scandir = Tracker
    old_max_records = ro.MAX_RECORDS
    ro.MAX_RECORDS = 2
    try:
        obs, truncated = ro.project_observations(str(enum_root))
        check('record enumeration is capped while iterating before sorting',
              tracker_counts.get(str(rec_worker), 0) <= 3 and len(obs) == 2 and truncated)
    finally:
        ro.os.scandir = original_scandir
        ro.MAX_RECORDS = old_max_records

    # 4. Prove EXACT shell PID live, not aggregate provider liveness for reused shell:
    fake_root = base / 'fake_proc_test'
    (fake_root / 'coord/results/w').mkdir(parents=True)
    doc_run = dict(schema_version=1, worker='w', task='T_PID', updated_at=old(120),
                   revision=rev, process=dict(state='running', exit_code=None, revision=rev))
    (fake_root / 'coord/results/w/T_PID.json').write_text(json.dumps(doc_run))
    fake_proc = fake_root / 'proc'
    (fake_proc / 'sys/kernel/random').mkdir(parents=True)
    fake_boot = '11111111-1111-4111-8111-111111111111'
    (fake_proc / 'sys/kernel/random/boot_id').write_text(fake_boot + '\n')

    def make_fake_stat(pid, sid, start):
        dp = fake_proc / str(pid)
        dp.mkdir(parents=True, exist_ok=True)
        fields = ['S', '1', '1', str(sid)] + ['0'] * 15 + [str(start)]
        (dp / 'stat').write_text('%d (fake) %s\n' % (pid, ' '.join(fields)))

    # Shell PID 201 has recorded start 88, but current /proc has start 99 (reused)
    # Provider PID 202 has recorded start 77, and current /proc has start 77 (live)
    make_fake_stat(201, 201, 99)
    make_fake_stat(202, 202, 77)
    own_fake = fake_root / 'coord/reports/T_PID.own'
    own_fake.parent.mkdir(parents=True, exist_ok=True)
    own_fake_doc = dict(schema_version=1, boot_id=fake_boot, worker='w', task='T_PID',
                        shell_pid=201, shell_start=88, shell_sid=201,
                        provider_pid=202, provider_sid=202, provider_start=77)
    own_fake.write_text(json.dumps(own_fake_doc))
    own_fake.chmod(0o600)
    (own_fake.parent / 'T_PID.pid').write_text('201\n')
    old_proc_root = ro.PROC_ROOT
    ro.PROC_ROOT = str(fake_proc)
    try:
        check('reused shell identity is rejected as reused', ro._identity(201, 88, 201) == 'reused')
        check('live provider identity is recognized as live', ro._identity(202, 77, 202) == 'live')
        fake_scan = ro.Scan()
        check('owner_state reports run live due to surviving provider', ro.owner_state(own_fake_doc, fake_scan) == 'live')
        p_state, p_pid = ro.pid_evidence(str(fake_root), 'T_PID')
        check('pid_evidence rejects reused shell PID despite live provider', p_state == 'not_live' and p_pid == 201)
        fake_status = ro.status_lines(str(fake_root))
        check('status_lines does not display reused shell PID as background',
              not any('pid 201' in line for line in fake_status))

        # Now test exact match: shell PID start time matches recorded start 88
        make_fake_stat(201, 201, 88)
        p_state_live, p_pid_live = ro.pid_evidence(str(fake_root), 'T_PID')
        check('pid_evidence confirms genuinely matching shell PID as live', p_state_live == 'live' and p_pid_live == 201)
        fake_status_live = ro.status_lines(str(fake_root))
        check('status_lines displays proved shell PID as background',
              any('(background, pid 201)' in line for line in fake_status_live))
    finally:
        ro.PROC_ROOT = old_proc_root


def native(base):
    root = base / 'project'; repo = root / 'repo'; repo.mkdir(parents=True)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0',
               UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='3', UNIO_ORPHAN_GRACE_SECONDS='1',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    for key in [k for k in env if k.startswith('UNIO_') and k not in (
            'UNIO_BIN_DIR', 'UNIO_CONF_DIR', 'UNIO_COMPLETION_DIR', 'UNIO_AUTO_VERIFY', 'UNIO_AUTO_OFF',
            'UNIO_AUTO_SYNC', 'UNIO_TIMEOUT', 'UNIO_ORPHAN_GRACE_SECONDS')]:
        env.pop(key)
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env, check=True, capture_output=True)
    at = str(base / 'bin/unio')

    def call(*args, code=0, timeout=60, extra=None):
        p = subprocess.run([at, *args], cwd=repo, env=dict(env, **(extra or {})), capture_output=True, text=True, timeout=timeout)
        assert code is None or p.returncode == code, (args, p.returncode, p.stdout, p.stderr)
        return p

    def git(*args):
        subprocess.run(['git', *args], cwd=repo, env=env, check=True, capture_output=True)
    git('init', '-q', '-b', 'main'); (repo / 'canary.txt').write_text('seed\n')
    git('add', 'canary.txt'); git('commit', '-qm', 'seed'); call('init', 'mock')
    calls = root / 'calls'; mock = root / 'mock.py'
    mock.write_text('''import os,subprocess,time
from pathlib import Path
with Path(%r).open('a') as f: f.write('called\\n')
mode=os.environ.get('MOCK_MODE','hang')
if mode in('commit','commit-hang'):
    with Path('canary.txt').open('a') as f:f.write('work\\n')
    subprocess.run(['git','add','canary.txt'],check=True);subprocess.run(['git','commit','-qm','mock work'],check=True)
if mode=='sleep-out': time.sleep(30)
if mode in('hang','commit-hang'):
    Path(%r).write_text('up');time.sleep(600)
''' % (str(calls), str(root / 'up')))
    (base / 'conf/agents.conf').write_text('mock=python3 ' + shlex.quote(str(mock)) + ' PRIVATE\n')

    def taskfile(name):
        (root / 'coord/tasks' / (name + '.md')).write_text('# T\n## Allowed scope\n- canary.txt\n## Validate\n$ true\n')

    def crash(name, mode):
        """Start a private run, wait for ownership, then SIGKILL only its own sessions."""
        taskfile(name)
        (root / 'up').unlink(missing_ok=True)
        proc = subprocess.Popen([at, 'run', 'mock', name], cwd=repo, env=dict(env, MOCK_MODE=mode, UNIO_TIMEOUT='300'),
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        own = root / 'coord/reports/.owners/mock' / (name + '.own')
        deadline = time.time() + 60
        doc = None
        while time.time() < deadline:
            if (root / 'up').exists() and own.exists():
                doc = json.loads(own.read_text())
                if doc['provider_pid']:
                    break
            time.sleep(.05)
        assert doc and doc['provider_pid'], 'mock run did not start'
        assert doc['task'] == name and doc['shell_pid'] == proc.pid
        running = call('result', 'mock', name)
        live = json.loads(running.stdout)['runtime_observation']
        check(mode + ': genuinely live run stays running', live['state'] == 'running')
        for sid in (proc.pid, doc['provider_sid']):
            try:
                os.killpg(sid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait()
        deadline = time.time() + 30
        while time.time() < deadline:
            if ro.probe_lock(str(root), 'mock') == 'free':
                break
            time.sleep(.05)
        time.sleep(1.2)  # the fixture's 1 s grace

    for name, mode in (('CRASHSTART', 'hang'), ('CRASHCOMMIT', 'commit-hang')):
        crash(name, mode)
        ledger = root / 'coord/reports/ledger.jsonl'
        started = [json.loads(l) for l in ledger.read_text().splitlines()]
        check(mode + ': ledger has run_start and no end',
              any(e['event'] == 'run_start' and e.get('task') == name for e in started)
              and not any(e['event'] == 'run' and e.get('task') == name for e in started))
        count = calls.read_text().count('called')
        keep = digests(root)
        result = json.loads(call('result', 'mock', name).stdout)
        o = result['runtime_observation']
        check(mode + ': result exposes completion_unknown', o['state'] == 'completion_unknown' and o['interrupted'] is True and o['source_exit'] is None)
        check(mode + ': raw recorded process is not relabelled', result['process']['state'] == 'running' and result['process']['exit_code'] is None)
        check(mode + ': never ready', result['ready_for_human_review'] is False)
        report = call('report', name).stdout
        check(mode + ': report works with no .md', 'completion_unknown' in report and 'Source exit: Unknown' in report and 'mock / ' + name in report)
        check(mode + ': no report file fabricated', not (root / 'coord/reports' / (name + '.md')).exists())
        watch = json.loads(call('watch', '--once', '--json').stdout)
        w = next(x for x in watch['results'] if x['task'] == name)
        check(mode + ': watch agrees', w['activity'] == 'completion_unknown' and w['runtime_observation']['state'] == 'completion_unknown' and w['process']['exit_code'] is None)
        status = call('status').stdout
        check(mode + ': status shows the orphan and not as running', 'mock / ' + name + ' — inspect' in status and 'Completion unknown' in status)
        check(mode + ': observations change no evidence bytes', digests(root) == keep)
        check(mode + ': no provider replay', calls.read_text().count('called') == count)
        packet = Path(call('handoff', 'mock', name).stdout.strip().splitlines()[0])
        text = (packet / 'HANDOFF.md').read_text()
        check(mode + ': handoff is not a delivery', 'Current observation: completion_unknown; Source exit: Unknown' in text and 'not a successful delivery or acceptance' in text)
        check(mode + ': handoff left original evidence alone', all(digests(root).get(k) == v for k, v in keep.items()))
    log = subprocess.run(['git', 'log', '--format=%s', 'agent/mock'], cwd=repo, capture_output=True, text=True).stdout
    check('clean commit made before the crash is preserved', 'mock work' in log)

    # A stale .pid is evidence: it stays, and a live unrelated PID is not reported.
    unrelated = subprocess.Popen(['sleep', '60'])
    try:
        pidfile = root / 'coord/reports/CRASHSTART.pid'
        pidfile.write_text('%d\n' % unrelated.pid)
        status = call('status').stdout
        check('status keeps stale pid evidence', pidfile.exists())
        check('unrelated live PID is not reported as owned', '(background, pid %d)' % unrelated.pid not in status and unrelated.poll() is None)
        check('doctor does not call a bare PID live', 'background run live: CRASHSTART' not in call('doctor', code=None).stdout)
        pidfile.unlink()
    finally:
        unrelated.kill(); unrelated.wait()
    fake = subprocess.Popen(['bash', '-c', 'exec -a "bin/unio run lookalike" sleep 60'])
    try:
        time.sleep(.2)
        check('process-name lookalike is not reported', 'lookalike' not in call('status').stdout and fake.poll() is None)
    finally:
        fake.kill(); fake.wait()

    # Distinct continuation after the old lock is free; original attempt survives.
    before = (root / 'coord/results/mock/CRASHSTART.json').read_bytes()
    taskfile('CONTINUE')
    call('run', 'mock', 'CONTINUE', extra=dict(MOCK_MODE='commit', UNIO_TIMEOUT='60'), timeout=120)
    check('distinct continuation task can run', json.loads(call('result', 'mock', 'CONTINUE').stdout)['runtime_observation']['source_exit'] == 0)
    check('continuation left the original record byte-identical', (root / 'coord/results/mock/CRASHSTART.json').read_bytes() == before)
    check('report shows real report for a finished task', 'last 60 lines' in call('report', 'CONTINUE').stdout)
    check('report with unknown task still refuses', call('report', 'NOSUCHTASK', code=1).returncode == 1)

    # A second worker with the same task must be explicit.
    second = root / 'coord/results/other'; second.mkdir()
    doc = json.loads((root / 'coord/results/mock/CRASHSTART.json').read_text()); doc['worker'] = 'other'
    (second / 'CRASHSTART.json').write_text(json.dumps(doc))
    shown = call('report', 'CRASHSTART').stdout
    check('multiple matching workers are explicit', '2 workers have an unresolved record' in shown and 'mock / CRASHSTART' in shown and 'other / CRASHSTART' in shown)
    (second / 'CRASHSTART.json').unlink(); second.rmdir()

    # Native run with colon identifier (T:1)
    taskfile('COLON:1')
    call('run', 'mock', 'COLON:1', extra=dict(MOCK_MODE='commit', UNIO_TIMEOUT='60'), timeout=120)
    colon_res = json.loads(call('result', 'mock', 'COLON:1').stdout)
    check('native run with colon ID records clean exit 0', colon_res['process']['exit_code'] == 0 and colon_res['runtime_observation']['source_exit'] == 0)
    check('report displays colon ID output without refusal', 'last 60 lines' in call('report', 'COLON:1').stdout)

    # Known timeout stays 124 through every surface.
    taskfile('TIMEOUT124')
    call('run', 'mock', 'TIMEOUT124', code=None, extra=dict(MOCK_MODE='sleep-out', UNIO_TIMEOUT='2'), timeout=120)
    result = json.loads(call('result', 'mock', 'TIMEOUT124').stdout)
    check('known timeout remains 124', result['process']['exit_code'] == 124 and result['runtime_observation']['source_exit'] == 124 and result['runtime_observation']['state'] == 'terminal')

    # VEC152: deterministic reproduction of the current refusal. Editing the
    # tree after a timeout moves the current revision off the recorded one.
    worktree = root / 'wt/mock'
    (worktree / 'canary.txt').write_text('moved after timeout\n')
    subprocess.run(['git', 'add', 'canary.txt'], cwd=worktree, env=env, check=True)
    subprocess.run(['git', 'commit', '-qm', 'later'], cwd=worktree, env=env, check=True)
    spec2 = importlib.util.spec_from_file_location('model_experience', source / 'tools/model-experience.py')
    me = importlib.util.module_from_spec(spec2); sys.modules['model_experience'] = me; spec2.loader.exec_module(me)
    moved = json.loads(call('result', 'mock', 'TIMEOUT124').stdout)
    refused = None
    try:
        me.valid_result(moved, 'mock', 'TIMEOUT124')
    except SystemExit as exc:
        refused = exc
    check('VEC152 reproduced: moved tree after exit 124 has no current binding', refused is not None and refused.code == 2 and moved['process']['exit_code'] == 124 and moved['revision'] != moved['current_revision'])


with tempfile.TemporaryDirectory(prefix='orphan-') as directory:
    base = Path(directory)
    unit(base)
    native(base)
print('orphan observation: %d checks passed' % checks)
