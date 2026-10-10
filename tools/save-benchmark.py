#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Bounded, offline save-performance probe for an installed Unio engine.

Builds a tiny private Git fixture (two workers, one known task, hooks and
template injection disabled) inside a caller-owned scratch directory and
measures `save create`, worker `save inspect`, `save usage` and
`watch --once --json` with monotonic clocks, hard subprocess deadlines and
byte-capped output. It never touches the real project's saves, tasks,
worktrees, configuration or credentials, makes no provider call, installs
nothing and mounts nothing. Results are written as schema-1 JSON to a private
receipt inside the benchmark workspace and printed to stdout.

Exit codes: 0 every planned measurement was recorded (engine exits are
observations, not probe failures); 1 the probe stopped early (unsafe input,
fixture failure or deadline); 2 usage error.
"""
import argparse
import json
import os
import re
import select
import shutil
import signal
import stat
import subprocess
import sys
import time
from pathlib import Path

SCHEMA_VERSION = 1
OUTPUT_CAP_BYTES = 256 * 1024
MAX_SAVES = 3
WORKERS = ('bench-a', 'bench-b')
TASK = 'BENCH'
NAME_RE = re.compile(r'\A[A-Za-z0-9][A-Za-z0-9._-]*\Z')
SAVE_ID_RE = re.compile(r'^saved ([0-9a-f]{32}):', re.M)


def fail(message):
    print('save-benchmark: %s' % message, file=sys.stderr)
    sys.exit(2)


class RunResult:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        if 'exit_code' in kwargs:
            self.returncode = kwargs['exit_code']
        else:
            self.returncode = None


def run_bounded(argv, cwd, env, timeout, cap=OUTPUT_CAP_BYTES):
    """One subprocess with a hard deadline and per-stream byte caps.

    Reading stops at the cap and the process is killed, so a runaway engine
    can neither block the probe nor exhaust memory with unbounded output.
    """
    started = time.monotonic()
    proc = subprocess.Popen(argv, cwd=str(cwd), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=True)
    streams = {proc.stdout.fileno(): bytearray(), proc.stderr.fileno(): bytearray()}
    for fd in streams:
        os.set_blocking(fd, False)
    eof, truncated = set(), False
    deadline = started + timeout
    while len(eof) < len(streams):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        open_fds = [fd for fd in streams if fd not in eof]
        try:
            ready, _, _ = select.select(open_fds, [], [], min(remaining, 0.25))
        except InterruptedError:
            continue
        for fd in ready:
            try:
                chunk = os.read(fd, 65536)
            except (BlockingIOError, OSError):
                continue
            if not chunk:
                eof.add(fd)
                continue
            buf = streams[fd]
            room = cap - len(buf)
            if room > 0:
                buf.extend(chunk[:room])
                truncated = truncated or len(chunk) > room
            else:
                truncated = True
        if truncated:
            break
    timed_out = len(eof) < len(streams) and not truncated
    if timed_out or truncated:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        proc.wait()
    out = bytes(streams[proc.stdout.fileno()])
    err = bytes(streams[proc.stderr.fileno()])
    proc.stdout.close()
    proc.stderr.close()
    return RunResult(duration_seconds=round(time.monotonic() - started, 6),
                     exit_code=None if (timed_out or truncated) else proc.returncode, stdout=out.decode(errors='replace'),
                     stderr=err.decode(errors='replace'), timed_out=timed_out,
                     output_truncated=truncated)


class Probe:
    def __init__(self, args):
        self.args = args
        self.failures = []
        self.steps = []
        self.started = time.monotonic()
        self.deadline = self.started + args.total_timeout

    def out_of_time(self, step):
        return time.monotonic() >= self.deadline and self.failures.append(
            'total timeout reached before %s' % step) is None

    def git(self, cwd, *git_args, data=None):
        timeout = min(self.args.step_timeout, max(0.1, self.deadline - time.monotonic()))
        try:
            return subprocess.run(['git', *git_args], cwd=str(cwd), env=self.env,
                                 input=data, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            class Dummy:
                returncode = 124
                stdout = b''
                stderr = b'git command timed out'
            return Dummy()

    def engine(self, cwd, *engine_args):
        if self.out_of_time(' '.join(engine_args)):
            return None
        timeout = min(self.args.step_timeout, max(0.1, self.deadline - time.monotonic()))
        return run_bounded([str(self.engine_path), *engine_args], cwd=cwd,
                           env=self.env, timeout=timeout)

    # ---- fixture -------------------------------------------------------
    def build_fixture(self, child):
        conf = child / 'conf'
        (conf / 'templates').mkdir(parents=True)
        (conf / 'off').mkdir()
        for name, text in (('board.md', '# Board\n'), ('TASK.md', '# Task\n'),
                           ('PROTOCOL.md', '# Protocol\n'), ('MASTER.md', '# Master\n'),
                           ('WORKER.md', '# Worker {{WORKER}}\n'), ('WORK-MODES.md', '# Work Modes\n'),
                           ('LEAD-ESCALATION.md', '# Lead Escalation\n'),
                           ('MODEL-SCOREBOARD.md', '# Model Scoreboard\n'),
                           ('AGENT-FLEET.md', '# Agent Fleet\n')):
            (conf / 'templates' / name).write_text(text)
        project = child / 'project'
        repo = project / 'repo'
        repo.mkdir(parents=True)
        (child / 'home').mkdir()
        self.env = dict(os.environ,
                        UNIO_CONF_DIR=str(conf), UNIO_AUTO_OFF='0', UNIO_AUTO_SYNC='0',
                        UNIO_AUTO_VERIFY='0', HOME=str(child / 'home'),
                        GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_SYSTEM='/dev/null',
                        GIT_AUTHOR_NAME='bench', GIT_COMMITTER_NAME='bench',
                        GIT_AUTHOR_EMAIL='bench@example.invalid',
                        GIT_COMMITTER_EMAIL='bench@example.invalid',
                        GIT_OPTIONAL_LOCKS='0')
        r = self.git(repo, 'init', '-q', '--template=', '-b', 'main')
        if r.returncode:
            return 'git init failed: %s' % r.stderr.decode(errors='replace').strip()
        (repo / '.git' / 'info').mkdir(exist_ok=True)
        # Hooks never run (including the guard hooks `init` writes) and no
        # git sample templates are injected into the fixture.
        for key, value in (('core.hooksPath', '/dev/null'), ('core.fsmonitor', 'false'),
                           ('commit.gpgsign', 'false')):
            r = self.git(repo, 'config', key, value)
            if r.returncode:
                return 'git config %s failed' % key
        files = {
            '.gitignore': 'cache/\n*.log\n',
            'README.md': 'base readme\n',
            'app/main.py': 'print("base")\n',
            'data/blob.bin': (bytes(range(256)) * 8),
            'docs/guide.md': 'guide\n',
        }
        for name, data in files.items():
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data if isinstance(data, bytes) else data.encode())
        for step in (('add', '-A'), ('commit', '-qm', 'base')):
            r = self.git(repo, *step)
            if r.returncode:
                return 'git %s failed: %s' % (step[0], r.stderr.decode(errors='replace').strip())
        r = self.engine(repo, 'init', *WORKERS)
        if r is None or r.returncode:
            return 'engine init failed: %s' % (r.stderr.strip() if r else 'timeout')
        # Safety: without these, engine commands would walk up and could find
        # a real enclosing Unio project. Refuse before anything else runs.
        if not (project / 'coord').is_dir() or not (project / 'wt').is_dir():
            return 'engine init did not create the fixture coord/ and wt/ directories'
        tasks = project / 'coord' / 'tasks'
        tasks.mkdir(exist_ok=True)
        (tasks / (TASK + '.md')).write_text(
            '# %s\nBenchmark fixture task.\n## Allowed scope\n- none\n## Validate\n$ true\n' % TASK)
        # A stub agent records any invocation; save/inspect/watch never call it.
        (project / 'coord' / 'agents.conf').write_text(
            "bench-none=sh -c 'echo called >> \"%s" % (project / 'coord' / 'provider-calls') + "\"'\n")
        r = self.engine(repo, 'stop')
        if r is None or r.returncode or not (project / 'coord' / 'STOP').exists():
            return 'engine stop failed: %s' % (r.stderr.strip() if r else 'timeout')
        return self.make_workload(project)

    def make_workload(self, project):
        a = project / 'wt' / WORKERS[0]
        (a / 'app' / 'main.py').write_text('print("staged change")\n')
        r = self.git(a, 'add', 'app/main.py')
        if r.returncode:
            return 'git add failed'
        (a / 'README.md').write_text('unstaged readme\n')
        r = self.git(a, 'rm', '-q', 'docs/guide.md')
        if r.returncode:
            return 'git rm failed'
        (a / 'notes').mkdir()
        (a / 'notes' / 'new.txt').write_text('untracked note v1\n')
        (a / 'img.bin').write_bytes(bytes(reversed(range(256))) + b'\0\0\xff')
        return None

    def workload_counts(self, project):
        a = project / 'wt' / WORKERS[0]
        counts = {'tracked_paths': 0, 'worktree_files': 0, 'worktree_bytes': 0,
                  'staged': 0, 'unstaged': 0, 'untracked': 0, 'removed': 0}
        r = self.git(a, 'ls-files', '-z')
        if r.returncode == 0:
            counts['tracked_paths'] = len([n for n in r.stdout.split(b'\0') if n])
        for dirpath, dirnames, filenames in os.walk(a):
            dirnames[:] = [d for d in dirnames if d != '.git']
            for name in filenames:
                p = Path(dirpath) / name
                counts['worktree_files'] += 1
                try:
                    counts['worktree_bytes'] += p.lstat().st_size
                except OSError:
                    pass
        r = self.git(a, 'status', '--porcelain=v1', '-z', '--untracked-files=all')
        if r.returncode == 0:
            for entry in r.stdout.split(b'\0'):
                if not entry:
                    continue
                code = entry[:2].decode(errors='replace')
                if '?' in code:
                    counts['untracked'] += 1
                elif code[0] in 'MARC':
                    counts['staged'] += 1
                elif code[1] in 'MD':
                    counts['unstaged'] += 1
        return counts

    # ---- measurements --------------------------------------------------
    def measure(self, child):
        project = child / 'project'
        repo = project / 'repo'
        saves = self.args.saves
        results = {'save_create': [], 'save_inspect_worker': None,
                   'save_usage': None, 'watch_once_json': None}
        for attempt in range(1, saves + 1):
            r = self.engine(repo, 'save', 'create', WORKERS[0], TASK)
            if r is None:
                break
            save_id = None
            m = SAVE_ID_RE.search(r.stdout)
            if m:
                save_id = m.group(1)
            # Never claim a save from exit alone: confirm the published
            # manifest inside the fixture's private save store.
            confirmed = bool(save_id) and (project / 'coord' / 'saves' / save_id
                                           / 'manifest.json').is_file()
            results['save_create'].append(dict(
                attempt=attempt, duration_seconds=r.duration_seconds,
                exit_code=r.exit_code, save_id=save_id,
                confirmed_by_manifest=confirmed, timed_out=r.timed_out,
                output_truncated=r.output_truncated,
                stderr_excerpt=r.stderr.strip()[:200] or None))
            if r.timed_out or r.output_truncated:
                self.failures.append('save create %d bounded after %.3fs' % (attempt, r.duration_seconds))
            if attempt < saves:
                note = project / 'wt' / WORKERS[0] / 'notes' / 'new.txt'
                if note.exists():
                    note.write_text('untracked note v%d\n' % (attempt + 1))
        r = self.engine(repo, 'save', 'inspect', '--worker', WORKERS[0], '--json')
        if r is not None:
            valid = False
            try:
                json.loads(r.stdout)
                valid = True
            except ValueError:
                pass
            results['save_inspect_worker'] = dict(
                duration_seconds=r.duration_seconds, exit_code=r.exit_code,
                json_valid=valid, timed_out=r.timed_out,
                output_truncated=r.output_truncated)
        r = self.engine(repo, 'save', 'usage', '--json')
        if r is not None:
            results['save_usage'] = dict(
                duration_seconds=r.duration_seconds, exit_code=r.exit_code,
                supported=r.exit_code == 0, timed_out=r.timed_out,
                output_truncated=r.output_truncated,
                detail=(r.stderr.strip().splitlines() or [''])[0][:200] or None)
        r = self.engine(repo, 'watch', '--once', '--json')
        if r is not None:
            valid = False
            try:
                for line in r.stdout.splitlines():
                    if line.strip():
                        json.loads(line)
                        valid = True
                        break
            except ValueError:
                pass
            results['watch_once_json'] = dict(
                duration_seconds=r.duration_seconds, exit_code=r.exit_code,
                json_valid=valid, timed_out=r.timed_out,
                output_truncated=r.output_truncated)
        return results

    # ---- filesystem ----------------------------------------------------
    def filesystem(self, path):
        info = {'stat_f_type': None, 'proc_mounts_type': None,
                'mount_point': None, 'device': None}
        try:
            r = subprocess.run(['stat', '-f', '-c', '%T', str(path)],
                               capture_output=True, timeout=10)
            if r.returncode == 0:
                info['stat_f_type'] = r.stdout.decode().strip()
        except (OSError, subprocess.TimeoutExpired):
            pass
        try:
            mounts = []
            for line in Path('/proc/mounts').read_text().splitlines():
                parts = line.split()
                if len(parts) >= 3:
                    mounts.append((parts[1], parts[0], parts[2]))
            best = ''
            for point, device, fs_type in mounts:
                if str(path).startswith(point) and len(point) > len(best):
                    best, info['mount_point'] = point, point
                    info['proc_mounts_type'], info['device'] = fs_type, device
        except OSError:
            pass
        return info

    # ---- cleanup -------------------------------------------------------
    def cleanup(self, child):
        if not self.args.cleanup:
            return False
        parent = self.scratch_real
        try:
            st = os.lstat(child)
        except OSError:
            return False
        if (not stat.S_ISDIR(st.st_mode) or os.path.islink(child)
                or Path(os.path.realpath(child)).parent != parent
                or child.name != self.args.workspace):
            self.failures.append('cleanup refused: workspace changed on disk')
            return False
        shutil.rmtree(child)
        return True

    # ---- top level -----------------------------------------------------
    def run(self):
        args = self.args
        engine = Path(args.engine)
        if not engine.exists():
            fail('engine does not exist: %s' % args.engine)
        engine = engine.resolve(strict=True)
        if not engine.is_file() or not os.access(engine, os.X_OK):
            fail('engine must be an executable regular file')
        self.engine_path = engine
        scratch = Path(args.scratch)
        try:
            st = os.lstat(scratch)
        except OSError:
            fail('scratch directory does not exist: %s' % args.scratch)
        if not stat.S_ISDIR(st.st_mode):
            fail('scratch must be a real directory, not a symlink or file')
        if st.st_uid != os.geteuid():
            fail('scratch must be owned by the calling user')
        if not os.access(scratch, os.W_OK):
            fail('scratch must be writable')
        self.scratch_real = Path(os.path.realpath(scratch))
        if self.scratch_real == Path(self.scratch_real.anchor):
            fail('refusing to use a filesystem root as scratch')
        if not NAME_RE.match(args.workspace):
            fail('workspace name must match %s' % NAME_RE.pattern)
        child = self.scratch_real / args.workspace
        if os.path.lexists(child):
            fail('refusing to reuse existing benchmark workspace: %s' % child)
        os.mkdir(child, 0o700)
        started_at = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
        fixture_error = self.build_fixture(child)
        measurements = None
        if fixture_error:
            self.failures.append('fixture: %s' % fixture_error)
        else:
            measurements = self.measure(child)
        calls_file = child / 'project' / 'coord' / 'provider-calls'
        provider_calls = 0
        if calls_file.exists():
            provider_calls = len(calls_file.read_text().splitlines())
        receipt = {
            'schema_version': SCHEMA_VERSION,
            'probe': 'save-benchmark',
            'started_at': started_at,
            'finished_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'engine': {'given_path': args.engine, 'resolved_path': str(engine),
                       'version_line': None, 'version': None},
            'scratch': {'given_path': args.scratch,
                        'workspace': args.workspace,
                        'filesystem': self.filesystem(child)},
            'fixture': {'workers': list(WORKERS), 'task': TASK,
                        'hooks_disabled': True, 'template_injection_disabled': True,
                        'provider_calls_recorded': provider_calls},
            'workload': self.workload_counts(child / 'project') if not fixture_error else None,
            'measurements': measurements,
            'save_count': len(measurements['save_create']) if measurements else 0,
            'failures': self.failures,
            'bounds': {'step_timeout_seconds': args.step_timeout,
                       'total_timeout_seconds': args.total_timeout,
                       'output_cap_bytes': OUTPUT_CAP_BYTES,
                       'max_saves': MAX_SAVES},
            'cleanup': {'requested': args.cleanup, 'performed': False},
        }
        r = self.engine(child, 'version')
        if r is not None:
            receipt['engine']['version_line'] = r.stdout.splitlines()[0] if r.stdout else None
            m = re.match(r'Unio (\S+)', r.stdout)
            if m:
                receipt['engine']['version'] = m.group(1)
        receipt['cleanup']['performed'] = self.cleanup(child)
        if not receipt['cleanup']['performed']:
            receipt_path = child / 'receipt.json'
            receipt_path.write_text(json.dumps(receipt, indent=2) + '\n')
            os.chmod(receipt_path, 0o600)
        print(json.dumps(receipt, indent=2))
        if fixture_error or any(f.startswith('total timeout') for f in self.failures):
            sys.exit(1)
        sys.exit(0)


def main():
    parser = argparse.ArgumentParser(
        prog='save-benchmark.py',
        description='Bounded offline save-performance probe for an installed Unio engine.')
    parser.add_argument('--engine', required=True, metavar='PATH',
                        help='installed unio executable to measure (never modified)')
    parser.add_argument('--scratch', required=True, metavar='DIRECTORY',
                        help='caller-owned real directory for a new private benchmark workspace')
    parser.add_argument('--workspace', default=None, metavar='NAME',
                        help='name of the new child workspace (default: save-benchmark-<timestamp>-<pid>)')
    parser.add_argument('--saves', type=int, default=MAX_SAVES, metavar='N',
                        help='number of save-create calls to measure, 1..%d (default %d)' % (MAX_SAVES, MAX_SAVES))
    parser.add_argument('--step-timeout', type=float, default=60.0, metavar='SECONDS',
                        help='hard per-subprocess deadline (default 60)')
    parser.add_argument('--total-timeout', type=float, default=300.0, metavar='SECONDS',
                        help='hard deadline for the entire probe (default 300)')
    parser.add_argument('--cleanup', action='store_true',
                        help='remove exactly the newly created benchmark workspace afterwards')
    args = parser.parse_args()
    if not 1 <= args.saves <= MAX_SAVES:
        fail('--saves must be between 1 and %d' % MAX_SAVES)
    if args.step_timeout <= 0 or args.total_timeout <= 0:
        fail('timeouts must be positive')
    if args.workspace is None:
        args.workspace = 'save-benchmark-%s-%d' % (
            time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()), os.getpid())
    Probe(args).run()


if __name__ == '__main__':
    main()
