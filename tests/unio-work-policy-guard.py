#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Native work-policy guard regressions. Mock providers only."""
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

source = Path(__file__).resolve().parent.parent

passed = [0]

def check(label, condition=True, out=None):
    if not condition:
        print('FAIL ' + label)
        if out is not None:
            if hasattr(out, 'stdout'):
                print(out.stdout)
                print(out.stderr)
            else:
                print(out)
        sys.exit(1)
    passed[0] += 1
    print('  ok %s' % label)

with tempfile.TemporaryDirectory(prefix='work-policy-guard-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'),
               UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid',
               GIT_COMMITTER_EMAIL='mock@example.invalid',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
               # Holding mocks must outlive admission assertions and recovery
               # bookkeeping. The deliberate timeout case overrides this below.
               UNIO_TIMEOUT='120', UNIO_REVIEW_TIMEOUT='5')
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env,
                   check=True, capture_output=True, timeout=60)
    at = str(base / 'bin' / 'unio')
    root = base / 'mock project'
    repo = root / 'repo'
    repo.mkdir(parents=True)

    owned = []
    detached = []
    open_streams = []

    def descendants(pid):
        found = []
        try:
            raw = Path('/proc/%s/task/%s/children' % (pid, pid)).read_text().split()
        except OSError:
            return found
        for tok in raw:
            if tok.isdigit():
                child = int(tok)
                found.append(child)
                found.extend(descendants(child))
        return found

    def kill_recorded(pid):
        # Sessions captured at creation. Never select processes by command text.
        if pid <= 1:
            return
        try:
            leader = os.getsid(pid) == pid
        except ProcessLookupError:
            return
        if leader:
            signals = (signal.SIGTERM, signal.SIGKILL)
            for sig in signals:
                try:
                    os.killpg(pid, sig)
                except ProcessLookupError:
                    return
                if sig == signal.SIGTERM:
                    deadline = time.time() + 2
                    while time.time() < deadline:
                        try:
                            os.kill(pid, 0)
                        except ProcessLookupError:
                            return
                        time.sleep(0.05)
            return
        tree = [pid, *descendants(pid)]
        for sig in (signal.SIGTERM, signal.SIGKILL):
            for item in tree:
                try:
                    os.kill(item, sig)
                except ProcessLookupError:
                    pass
            if sig == signal.SIGTERM:
                time.sleep(0.2)

    def stop_owned():
        seen = []
        for proc in owned:
            if proc.poll() is None and proc.pid not in seen:
                seen.append(proc.pid)
        for pid in detached:
            if pid > 1 and pid not in seen:
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    continue
                seen.append(pid)
        for pid in seen:
            kill_recorded(pid)
        for proc in owned:
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass

    def note_detached(task):
        pidfile = root / 'coord' / 'reports' / ('%s.pid' % task)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            if pidfile.is_file():
                try:
                    pid = int(pidfile.read_text().strip())
                except (OSError, ValueError):
                    pid = 0
                if pid > 1:
                    detached.append(pid)
                    return pid
            time.sleep(0.1)
        return 0

    def git(*args):
        return subprocess.run(['git', *args], cwd=repo, env=env,
                              check=True, capture_output=True, timeout=30)

    def unio(*args, cwd=None, bg=False, wait=True):
        if not wait or bg:
            fout = open(repo / ('unio_run_%s.out' % args[1]), 'w')
            ferr = open(repo / ('unio_run_%s.err' % args[1]), 'w')
            open_streams.extend((fout, ferr))
            proc = subprocess.Popen([at, *args], cwd=cwd or repo, env=env,
                                    stdout=fout, stderr=ferr, text=True,
                                    start_new_session=True)
            owned.append(proc)
            return proc
        proc = subprocess.Popen([at, *args], cwd=cwd or repo, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, start_new_session=True)
        owned.append(proc)
        try:
            out, err = proc.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            kill_recorded(proc.pid)
            try:
                proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                pass
            raise
        return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)

    try:
        git('init', '--initial-branch=main')
        git('commit', '--allow-empty', '-m', 'initial')

        # We must init from root/repo so find_root uses it, but wait:
        # find_root stops where coord and wt exist. If we init from repo,
        # unio-install.sh will create coord/ and wt/ in root.
        # That is normal.
        unio('init', 'mock1')
        unio('init', 'mock2')
        unio('init', 'mock3')
        unio('init', 'mock4')
        unio('init', 'mock5')

        conf_dir = base / 'conf' / 'agents.conf'
        mock_script = repo / 'mock.sh'
        conf_dir.write_text(f"mock1=bash '{mock_script}'\nmock2=bash '{mock_script}'\nmock3=bash '{mock_script}'\nmock4=bash '{mock_script}'\nmock5=bash '{mock_script}'\n")
        mock_script.write_text("""#!/bin/bash
    if [ -n "${MOCK_MARKER:-}" ]; then
        printf 'ran\\n' >> "$MOCK_MARKER"
    fi
    barrier="${MOCK_BARRIER:-}"
    if [ -n "$barrier" ]; then
        touch "$barrier.started"
        while [ ! -f "$barrier.release" ]; do sleep 0.1; done
    fi
    if [ "${MOCK_TRAP:-0}" = "1" ]; then
        trap 'echo ignored term' TERM
        while true; do sleep 1; done
    fi
    """)
        mock_script.chmod(0o755)

        # tasks MUST be in root/coord/tasks
        (root / 'coord' / 'tasks').mkdir(parents=True, exist_ok=True)
        (root / 'coord' / 'tasks' / 'task1.md').write_text("Task 1 content")
        (root / 'coord' / 'tasks' / 'task2.md').write_text("Task 2 content")
        (root / 'coord' / 'tasks' / 'task3.md').write_text("Task 3 content")
        (root / 'coord' / 'tasks' / 'task4.md').write_text("Task 4 content")
        (root / 'coord' / 'tasks' / 'task5.md').write_text("Task 5 content")
        # Separate lifecycle scenarios must not inherit another case's retry
        # failures. These remain real tasks with normal account admission.
        for name in ('timeout-task', 'after-timeout', 'background-task', 'signal-task'):
            (root / 'coord' / 'tasks' / f'{name}.md').write_text(f'Task {name} content')
        # And we must track them in git for quality paths if needed, wait, coord is NOT in repo!
        # Does unio run require task file to be tracked? NO. quality paths only checks wt/worker.

        # same-lock concurrent setters
        def set_mode(m):
            return unio('mode', m).stdout
        def set_tier(t):
            return unio('tier', t).stdout
        with ThreadPoolExecutor(max_workers=2) as ex:
            mode_out = ex.submit(set_mode, 'yolo')
            tier_out = ex.submit(set_tier, 'high')
            mode_out.result()
            tier_out.result()
        st = unio('policy').stdout
        check('same-lock concurrent setters', 'mode: yolo' in st and 'tier: high' in st)

        # reset state
        unio('tier', 'low')
        unio('mode', 'medium')
        unio('lead', 'none')

        # invalid timestamp
        state_file = root / 'coord' / 'work-policy.json'
        st_json = json.loads(state_file.read_text())
        st_json['updated_at'] = 'invalid'
        state_file.write_text(json.dumps(st_json))
        out = unio('mode', 'safe')
        check('invalid timestamp rejected', out.returncode != 0 and 'invalid updated_at' in out.stderr, out)
        st_json.pop('updated_at')
        state_file.write_text(json.dumps(st_json))

        # unsafe control path symlink
        lock_dir = root / 'coord' / '.locks'
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_file = lock_dir / 'work-policy.lock'
        lock_link = lock_dir / 'work-policy.link'
        if lock_file.exists():
            lock_link.write_bytes(lock_file.read_bytes())
            lock_file.unlink()
        else:
            lock_link.write_text("")
        lock_file.symlink_to(lock_link.name)
        out = unio('mode', 'yolo')
        check('unsafe policy lock symlink', out.returncode != 0 and 'unsafe control path' in out.stderr, out)
        lock_file.unlink()
        if lock_link.exists():
            lock_file.write_bytes(lock_link.read_bytes())

        # same-budget aliases denied before mock command
        unio('account', 'mock1', 'grp1')
        unio('account', 'mock2', 'grp1')
        unio('tier', 'low') # limit 1

        def wait_barrier(path):
            # Provider startup follows a bounded 30s baseline recovery save.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                if Path(path).exists():
                    return
                time.sleep(0.1)
            print(f"timeout waiting for {path}")
            for err_file in repo.glob("unio_run_*.err"):
                print(f"--- {err_file.name} ---")
                print(err_file.read_text())
            for out_file in repo.glob("unio_run_*.out"):
                print(f"--- {out_file.name} ---")
                print(out_file.read_text())
            sys.exit(1)

        env['MOCK_BARRIER'] = str(repo / 'bar1')
        p1 = unio('run', 'mock1', 'task1', wait=False)
        wait_barrier(repo / 'bar1.started')

        out2 = unio('run', 'mock2', 'task2')
        check('same-budget alias denied', out2.returncode != 0 and 'budget refused' in out2.stderr and "budget group 'grp1' holds" in out2.stderr, out2)

        # release bar1
        (repo / 'bar1.release').touch()
        p1.wait(timeout=90)

        # different groups overlap
        unio('account', 'mock1', 'grp1')
        unio('account', 'mock2', 'grp2')
        unio('tier', 'low') # limit 1
        env['MOCK_BARRIER'] = str(repo / 'bar2')
        p1 = unio('run', 'mock1', 'task1', wait=False)
        wait_barrier(repo / 'bar2.started')

        env['MOCK_BARRIER'] = str(repo / 'bar3')
        p2 = unio('run', 'mock2', 'task2', wait=False)
        wait_barrier(repo / 'bar3.started')

        check('different groups overlap allowed', p2.poll() is None)

        (repo / 'bar2.release').touch()
        (repo / 'bar3.release').touch()
        p1.wait(timeout=90)
        p2.wait(timeout=90)
        del env['MOCK_BARRIER']

        # cap2/cap4 and lead inclusion
        unio('tier', 'high') # limit 4
        unio('account', 'mock5', 'grp1')
        unio('lead', 'mock5')

        ps = []
        # limit 4, lead is 1, so we can start 3
        for i, agent in enumerate(['mock1', 'mock2', 'mock3']):
            unio('account', agent, 'grp1')
            grant = unio('lead-budget', 'grant', agent, agent, f'task{i+1}', 'run')
            check('fixture owner grants shared lead task', grant.returncode == 0, grant)
            env['MOCK_BARRIER'] = str(repo / f'bar4_{i}')
            ps.append(unio('run', agent, f'task{i+1}', wait=False))

        for i in range(3):
            wait_barrier(repo / f'bar4_{i}.started')

        unio('account', 'mock4', 'grp1')
        env['MOCK_BARRIER'] = ''


        grant = unio('lead-budget', 'grant', 'mock4', 'mock4', 'task4', 'run')
        check('full-slot probe has owner consent', grant.returncode == 0, grant)
        out_denied = unio('run', 'mock4', 'task4')
        check('cap4 with lead limits properly', out_denied.returncode != 0 and 'budget refused' in out_denied.stderr, out_denied)

        # tier reduction/regroup refusal while busy
        out_tier = unio('tier', 'medium')
        check('tier reduction while busy refused', out_tier.returncode != 0 and 'tier medium refuses' in out_tier.stderr, out_tier)

        out_regroup = unio('account', 'mock1', 'grp2')
        check('regroup occupied agent refused', out_regroup.returncode != 0 and 'holds' in out_regroup.stderr, out_regroup)

        for i in range(3): (repo / f'bar4_{i}.release').touch()
        for p in ps:
            p.wait(timeout=90)


        # held oversized/malformed metadata cannot bypass low cap or lower/regroup
        unio('tier', 'low')
        unio('lead', 'none')

        # 1. Create a held slot by running a background mock that waits
        env['MOCK_BARRIER'] = str(repo / 'bar_oversized')
        p_over = unio('run', 'mock1', 'task1', wait=False)
        wait_barrier(repo / 'bar_oversized.started')

        # 2. Find the slot file and rewrite it to be oversized
        import fcntl
        slot_dir = root / 'coord' / '.locks' / 'work-policy-slots' / 'grp1'
        slot_files = list(slot_dir.glob('wpslot-*.json'))
        check('slot file created', len(slot_files) > 0)
        slot_file = slot_files[0]

        # Rewrite its content to be oversized but STILL HELD by python!
        # Wait, the python process holds the fd. We can just append to the file path to make it oversized.
        try:
            with open(slot_file, 'a') as sf:
                sf.write(" " * 5000)
        except Exception as e:
            print("Failed to append", e)

        # Now verify admission is refused (it's oversized but held, so considered active)
        out_admit = unio('run', 'mock2', 'task2')
        check('held oversized slot refuses admit', out_admit.returncode != 0 and 'budget refused' in out_admit.stderr)

        # Verify tier reduction is refused
        out_tier = unio('tier', 'high') # wait, tier medium... wait, tier reduction.
        unio('tier', 'medium')
        out_tier = unio('tier', 'low')
        check('held oversized slot refuses tier reduction', out_tier.returncode != 0)

        # Verify regroup is refused
        out_regroup = unio('account', 'mock1', 'grp2')
        check('held oversized slot refuses regroup', out_regroup.returncode != 0)

        # release
        (repo / 'bar_oversized.release').touch()
        p_over.wait(timeout=90)

        # hardlinked policy lock rejected with state/sentinel intact
        lock_file = root / 'coord' / '.locks' / 'work-policy.lock'
        lock_link = root / 'coord' / '.locks' / 'work-policy.hardlink'
        if lock_file.exists():
            try:
                os.link(lock_file, lock_link)
                out_hardlink = unio('mode', 'yolo')
                check('hardlinked policy lock rejected', out_hardlink.returncode != 0 and 'hardlinked' in out_hardlink.stderr)
                lock_link.unlink()
            except OSError:
                pass # FS doesn't support hardlinks

        # unsafe admission path rejection before a counted mock command
        # Create an unsafe slot directory (symlink)
        unio('account', 'mock3', 'grp_unsafe')
        unsafe_dir = root / 'coord' / '.locks' / 'work-policy-slots' / 'grp_unsafe'
        if unsafe_dir.exists():
            unsafe_dir.rmdir()
        unsafe_target = root / 'coord' / '.locks' / 'target_unsafe'
        unsafe_target.mkdir(parents=True, exist_ok=True)
        sentinel = unsafe_target / 'sentinel.txt'
        sentinel.write_text('keep-sentinel\n')
        sentinel_bytes = sentinel.read_bytes()
        target_names = sorted(path.name for path in unsafe_target.iterdir())
        marker = repo / 'unsafe-provider-marker'
        marker.unlink(missing_ok=True)
        env['MOCK_MARKER'] = str(marker)
        env.pop('MOCK_BARRIER', None)
        unsafe_dir.symlink_to('target_unsafe')

        out_unsafe = unio('run', 'mock3', 'task3')
        check('unsafe admission path rejection',
              out_unsafe.returncode == 2 and
              'unsafe control path' in out_unsafe.stderr and
              unsafe_dir.name in out_unsafe.stderr and
              unsafe_dir.is_symlink() and
              out_unsafe.stdout == '' and
              not marker.exists() and
              sentinel.read_bytes() == sentinel_bytes and
              sorted(path.name for path in unsafe_target.iterdir()) == target_names,
              out_unsafe)

        unsafe_dir.unlink()
        env.pop('MOCK_MARKER', None)

        # check failure/timeout release
        # Add bounded --kill-after=5s to Source/review timeouts
        # The oversized-slot scenario left medium capacity after a refused
        # reduction. Low capacity makes any leaked shared slot block the probe.
        assert unio('tier', 'low').returncode == 0
        env['MOCK_TRAP'] = "1"
        env['UNIO_TIMEOUT'] = "2" # 2s timeout
        mock_identity_file = repo / 'mock_identity.json'
        mock_identity_file.unlink(missing_ok=True)
        env['MOCK_IDENTITY_FILE'] = str(mock_identity_file)

        unio_wrapper = repo / 'unio_wrapper.sh'
        unio_wrapper.write_text(f"#!/bin/bash\nsleep 5\n\"{at}\" \"$@\"\nres=$?\nsleep 5\nexit $res\n")
        unio_wrapper.chmod(0o755)

        # Publish a real TERM-ignoring child before exec, so observation
        # cannot race discovery of the Bash loop's transient sleeps.
        mock_wrapper = repo / 'mock_wrapper.py'
        mock_wrapper.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, signal, subprocess, time\n"
            "pid = os.getpid()\n"
            "t_mono = time.monotonic()\n"
            "# /proc starttime: field 22 (1-indexed) for PID-reuse detection\n"
            "def proc_identity(p):\n"
            "    try:\n"
            "        raw = open(f'/proc/{p}/stat').read()\n"
            "        fields = raw[raw.rfind(')') + 2:].split()\n"
            "        return {'pid': p, 'starttime': fields[19],\n"
            "                'sid': int(fields[3]), 'state': fields[0]}\n"
            "    except (OSError, IndexError, ValueError):\n"
            "        return None\n"
            "identity = proc_identity(pid)\n"
            "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
            "child = subprocess.Popen(['sleep', '60'])\n"
            "ready_deadline = time.monotonic() + 1\n"
            "while True:\n"
            "    child_identity = proc_identity(child.pid)\n"
            "    if child_identity and child_identity['state'] not in ('Z', 'X', 'x'):\n"
            "        break\n"
            "    remaining = ready_deadline - time.monotonic()\n"
            "    if remaining <= 0:\n"
            "        raise RuntimeError('owned child identity unavailable')\n"
            "    time.sleep(min(0.01, remaining))\n"
            "identity.update(monotonic_start=t_mono, children=[child_identity])\n"
            "idf = os.environ.get('MOCK_IDENTITY_FILE', '')\n"
            "if idf:\n"
            "    tmp = idf + '.tmp'\n"
            "    with open(tmp, 'w') as f:\n"
            "        json.dump(identity, f)\n"
            "    os.rename(tmp, idf)\n"
            f"os.execvp('bash', ['bash', '{mock_script}'])\n"
        )
        mock_wrapper.chmod(0o755)

        conf_dir_file = base / 'conf' / 'agents.conf'
        with open(conf_dir_file, 'a') as f:
            f.write(f"mock_timeout=python3 '{mock_wrapper}'\n")

        unio('init', 'mock_timeout')
        unio('account', 'mock_timeout', 'grp1')

        # Finding 3: single monotonic deadline from Popen for entire harness.
        HARNESS_DEADLINE_SECS = 40
        t0_wall = time.monotonic()
        harness_deadline = t0_wall + HARNESS_DEADLINE_SECS

        def remaining():
            r = harness_deadline - time.monotonic()
            if r <= 0:
                raise TimeoutError("harness deadline exceeded")
            return r

        proc = subprocess.Popen([str(unio_wrapper), 'run', 'mock_timeout', 'timeout-task'],
                                cwd=repo, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        owned.append(proc)

        def read_proc_identity(p):
            try:
                raw = Path(f'/proc/{p}/stat').read_text()
                fields = raw[raw.rfind(')') + 2:].split()
                return {'pid': p, 'starttime': fields[19], 'state': fields[0],
                        'ppid': int(fields[1]), 'pgid': int(fields[2]),
                        'sid': int(fields[3])}
            except (OSError, IndexError, ValueError):
                return None

        ident = None
        recorded_children = []
        t_start = t_end = t1_wall = None
        out_stdout = out_stderr = ''

        def timing_output():
            now = time.monotonic()
            lifetime = (t_end or now) - t_start if t_start is not None else None
            return (f"mock start: {t_start}, end: {t_end}, lifetime: {lifetime}s, "
                    f"wall: {(t1_wall or now)-t0_wall:.2f}s, exit: {proc.poll()}\n"
                    f"identity: {ident}\nstdout:\n{out_stdout}\nstderr:\n{out_stderr}")

        def still_executing(record):
            remaining()
            current = read_proc_identity(record['pid'])
            remaining()
            # PID reuse proves the recorded process ended, but cannot serve
            # as the required initial live observation.
            return (current is not None and current['starttime'] == record['starttime']
                    and current['state'] not in ('Z', 'X', 'x'))

        def cleanup_timeout():
            # The timeout command may own a separate process group within
            # our session, even after the Popen session leader has exited.
            cleanup_deadline = time.monotonic() + 3
            groups = {proc.pid}
            sessions = {proc.pid}
            # The provider runs in its own session. Include that session's
            # groups so a failed observation cannot leave the fixture behind.
            if ident and ident.get('sid'):
                sessions.add(ident['sid'])
            for record in recorded_children:
                if record.get('sid'):
                    sessions.add(record['sid'])
            for entry in Path('/proc').iterdir():
                if time.monotonic() >= cleanup_deadline:
                    break
                if not entry.name.isdigit():
                    continue
                current = read_proc_identity(int(entry.name))
                if current and current['sid'] in sessions:
                    groups.add(current['pgid'])
            for group in groups:
                try:
                    os.killpg(group, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            try:
                return proc.communicate(timeout=max(0, cleanup_deadline - time.monotonic()))
            except subprocess.TimeoutExpired:
                # An inherited pipe must never extend the cleanup budget.
                for stream in (proc.stdout, proc.stderr):
                    if stream:
                        stream.close()
                return '', ''

        try:
            # All observations, sleeps and collection share this deadline.
            while True:
                remaining()
                if mock_identity_file.exists():
                    ident = json.loads(mock_identity_file.read_text())
                    t_start = ident['monotonic_start']
                    recorded_children = ident['children']
                    break
                if proc.poll() is not None:
                    out_stdout, out_stderr = proc.communicate(timeout=remaining())
                    break
                time.sleep(min(0.1, remaining()))

            check('mock provider started', ident is not None, timing_output())
            check('mock child recorded', bool(recorded_children), timing_output())
            for record in [ident, *recorded_children]:
                remaining()
                current = read_proc_identity(record['pid'])
                check('mock identity observed live in provider session',
                      bool(record['starttime']) and record['sid'] != proc.pid
                      and current is not None
                      and current['starttime'] == record['starttime']
                      and current['sid'] == record['sid']
                      and current['state'] not in ('Z', 'X', 'x')
                      and (record is ident or (current['ppid'] == ident['pid']
                                               and current['sid'] == ident['sid'])),
                      timing_output() + f"\nobserved: {current}")
                remaining()

            while True:
                remaining()
                if not still_executing(ident):
                    t_end = time.monotonic()
                    remaining()
                    break
                time.sleep(min(0.1, remaining()))

            out_stdout, out_stderr = proc.communicate(timeout=remaining())
            t1_wall = time.monotonic()
            remaining()
            duration = t_end - t_start
            out_msg = timing_output()
            check('harness execution within 40s', t1_wall - t0_wall <= HARNESS_DEADLINE_SECS, out_msg)
            check('timeout enforced', proc.returncode in (124, 137) and 0 <= duration <= 9, out_msg)
            check('delayed fixture bookkeeping exceeds old assertion', t1_wall - t0_wall > 15, out_msg)
            leftover_children = [c for c in recorded_children if still_executing(c)]
            check('no leftover live mock child',
                  not still_executing(ident) and not leftover_children,
                  out_msg + f"\nleftover: {leftover_children}")
        except (subprocess.TimeoutExpired, TimeoutError):
            out_stdout, out_stderr = cleanup_timeout()
            check('harness execution deadline', False, timing_output())

        print(f"  lifecycle: {duration:.2f}s, wall: {t1_wall-t0_wall:.2f}s, exit: {proc.returncode}")

        env['UNIO_TIMEOUT'] = '120'
        del env['MOCK_TRAP']
        del env['MOCK_IDENTITY_FILE']
        policy_after_timeout = unio('policy', '--json')
        released = (policy_after_timeout.returncode == 0 and
                    json.loads(policy_after_timeout.stdout)['active_native_workflows'].get('grp1', 0) == 0)
        out_next = unio('run', 'mock1', 'after-timeout')
        check('slot released on timeout/failure', released and out_next.returncode == 0,
              f'policy:\n{policy_after_timeout.stdout}\nprobe:\n{out_next.stdout}\n{out_next.stderr}')

        # original task/hash preserved and policy header/sidecar consistent
        prompt_file = root / 'coord' / 'reports' / 'after-timeout.prompt.md'
        sidecar_file = root / 'coord' / 'reports' / 'after-timeout.policy.json'
        check('prompt/sidecar exists', prompt_file.exists() and sidecar_file.exists())

        prompt_text = prompt_file.read_text()
        check('policy header applied', 'Unio work-policy header' in prompt_text and 'Task after-timeout content' in prompt_text)

        sidecar_json = json.loads(sidecar_file.read_text())
        check('sidecar JSON consistent', sidecar_json['group'] == 'grp1' and 'policy' in sidecar_json)

        # background Source and independent reviewer accounting
        unio('tier', 'low')
        unio('lead', 'none')

        # test background Source
        env['MOCK_BARRIER'] = str(repo / 'bar5')
        unio('run', '-b', 'mock1', 'background-task', wait=False)
        note_detached('background-task')
        wait_barrier(repo / 'bar5.started')

        out_fg = unio('run', 'mock2', 'task2')
        check('background Source accounted', out_fg.returncode != 0 and 'budget refused' in out_fg.stderr, out_fg)

        (repo / 'bar5.release').touch()

        # wait for background to finish properly
        released_bg = False
        for _ in range(150):
            out_pol = unio('policy', '--json')
            try:
                pol_json = json.loads(out_pol.stdout)
            except json.JSONDecodeError:
                time.sleep(0.1)
                continue
            if pol_json.get('active_native_workflows', {}).get('grp1', 0) == 0:
                out_stat = unio('status')
                mock1_line = next((line for line in out_stat.stdout.splitlines() if line.startswith('  mock1 ')), '')
                if mock1_line and '<< RUNNING' not in mock1_line:
                    released_bg = True
                    break
            time.sleep(0.1)
        check('background Source released its slot', released_bg)

        # test independent reviewer accounting
        # The unsafe-path case left mock3 on its own group. Share grp1 with the
        # reviewer, or this run is a legal second group and its provider starts.
        unio('account', 'mock3', 'grp1')
        # inject passed validation
        result_path = root / 'coord' / 'results' / 'mock2' / 'task2.json'
        injector = (
            'import json\n'
            'f = %r\n'
            'd = json.load(open(f))\n'
            'd["validation"] = {\n'
            '    "state": "passed",\n'
            '    "revision": d["current_revision"],\n'
            '    "scope": "OK",\n'
            '    "checks_run": 1,\n'
            '    "checks_failed": 0,\n'
            '    "reasons": []\n'
            '}\n'
            'json.dump(d, open(f, "w"))\n'
        ) % str(result_path)
        subprocess.run(['python3', '-c', injector], timeout=20, check=True)
        env['UNIO_REVIEW_TIMEOUT'] = '30'
        env['MOCK_BARRIER'] = str(repo / 'bar6')
        p_rev = unio('review', 'mock2', 'task2', 'mock1', wait=False)
        wait_barrier(repo / 'bar6.started')
        # The refusal probe must not inherit the reviewer's hold. A missed
        # refusal then returns on the provider timeout instead of blocking.
        env.pop('MOCK_BARRIER', None)
        env['UNIO_TIMEOUT'] = '5'
        marker = repo / 'reviewer-budget-marker'
        marker.unlink(missing_ok=True)
        env['MOCK_MARKER'] = str(marker)

        out_rev2 = unio('run', 'mock3', 'task3')
        check('reviewer accounted',
              out_rev2.returncode == 2 and 'budget refused' in out_rev2.stderr
              and "budget group 'grp1' holds" in out_rev2.stderr
              and not marker.exists(),
              out_rev2)
        env.pop('MOCK_MARKER', None)

        (repo / 'bar6.release').touch()
        try:
            p_rev.wait(timeout=90)
        except subprocess.TimeoutExpired:
            kill_recorded(p_rev.pid)
            raise
        held_after = []
        slot_dir = root / 'coord' / '.locks' / 'work-policy-slots'
        if slot_dir.is_dir():
            for slot in slot_dir.rglob('wpslot-*.json'):
                if slot.is_symlink():
                    continue
                fd = os.open(slot, os.O_RDONLY)
                try:
                    try:
                        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        held_after.append(slot)
                    else:
                        fcntl.flock(fd, fcntl.LOCK_UN)
                finally:
                    os.close(fd)
        check('reviewer slot released after the reviewer finishes', held_after == [])

        def signal_reaps(proc):
            kids = descendants(proc.pid)
            os.kill(proc.pid, signal.SIGTERM)
            # Source TERM still performs its bounded final recovery save before
            # the shell releases ownership; include that work in collection.
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                alive = [pid for pid in kids if Path('/proc/%s' % pid).exists()]
                if proc.poll() is not None and not alive:
                    return True
                time.sleep(0.1)
            return False

        env['MOCK_BARRIER'] = str(repo / 'bar_term')
        env['UNIO_TIMEOUT'] = '30'
        (repo / 'bar_term.started').unlink(missing_ok=True)
        (repo / 'bar_term.release').unlink(missing_ok=True)
        p_term = unio('run', 'mock1', 'signal-task', wait=False)
        wait_barrier(repo / 'bar_term.started')
        check('run signal reaps the provider and holder', signal_reaps(p_term))

        env['MOCK_BARRIER'] = str(repo / 'bar_term_review')
        env['UNIO_REVIEW_TIMEOUT'] = '30'
        (repo / 'bar_term_review.started').unlink(missing_ok=True)
        (repo / 'bar_term_review.release').unlink(missing_ok=True)
        p_sig = unio('review', 'mock2', 'task2', 'mock1', wait=False)
        wait_barrier(repo / 'bar_term_review.started')
        check('review signal reaps the provider and holder', signal_reaps(p_sig))

        print('work-policy-guard: done (%d checks passed)' % passed[0])
    finally:
        stop_owned()
        for stream in open_streams:
            stream.close()
