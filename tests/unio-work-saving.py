#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Manual work saving (slice 1): create, inspect and exact restore.

Offline and mock-only. Installs under a temporary directory, builds a mock
project whose path contains spaces, and drives real Git worktrees with mixed
committed (including a merge), staged, unstaged, untracked, deleted, binary,
empty and executable content. Restores are compared by HEAD, full index and
file bytes/modes; the source is compared byte-for-byte (including its raw
index) before and after. The only configured agent is a stub that records
any invocation; it must never be called.
"""
import fcntl
import json
import os
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from pathlib import Path

source = Path(__file__).resolve().parent.parent
passed = [0]


def check(label, condition=True, detail=None):
    if not condition:
        print('FAIL ' + label, flush=True)
        if detail:
            print(detail, flush=True)
        sys.exit(1)
    passed[0] += 1
    print('  ok %s' % label, flush=True)


with tempfile.TemporaryDirectory(prefix='work-saving-') as directory:
    base = Path(directory)
    calls = base / 'provider-calls'
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid',
               GIT_OPTIONAL_LOCKS='0', UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0')
    env.pop('UNIO_SAVE_TEST_FAULT', None)
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env, check=True, capture_output=True)
    (base / 'conf' / 'agents.conf').write_text("mock=sh -c 'echo called >> \"%s\"'\n" % calls)
    at = str(base / 'bin' / 'unio')
    root = base / 'mock project'
    repo = root / 'repo'
    repo.mkdir(parents=True)

    def git(cwd, *args, data=None):
        return subprocess.run(['git', *args], cwd=cwd, env=env, check=True, capture_output=True,
                              input=data).stdout

    def unio(*args, fault=None, cwd=None, timeout=120):
        e = dict(env, UNIO_SAVE_TEST_FAULT=fault) if fault else env
        return subprocess.run([at, *args], cwd=cwd or repo, env=e, capture_output=True, text=True, timeout=timeout)

    def write(path, data, mode=0o644):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode())
        os.chmod(path, mode)

    # Base commit: binary, empty, executable and nested content.
    write(repo / '.gitignore', 'cache/\n*.log\n.env\n')
    write(repo / 'README.md', 'base readme\n')
    write(repo / 'bin' / 'tool.sh', '#!/bin/sh\necho tool\n', 0o755)
    write(repo / 'data' / 'blob.bin', bytes(range(256)) * 4)
    write(repo / 'empty.txt', b'')
    write(repo / 'docs' / 'old.md', 'old\n')
    write(repo / 'docs' / 'gone.md', 'gone\n')
    write(repo / 'keep' / 'staged.txt', 'staged v1\n')
    write(repo / 'sub' / 'dir' / 'deep.txt', 'deep\n')
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'add', '-A')
    git(repo, 'commit', '-qm', 'base')
    base_commit = git(repo, 'rev-parse', 'HEAD').decode().strip()
    workers = ['mock-' + c for c in 'abcdefghij']
    init = unio('init', *workers)
    check('init creates mock workers', init.returncode == 0)
    coord, wt = root / 'coord', root / 'wt'
    write(coord / 'tasks' / 'T1.md', '# T1\nFinish the feature.\n## Validate\n$ false\n')
    write(coord / 'tasks' / 'T2.md', '# T2\nSecond task.\n')
    unio('stop')
    check('STOP is set for every save command below', (coord / 'STOP').exists())

    def snap(path):
        """Everything on disk (ignored files and role cards too), HEAD and raw index."""
        files = {}
        for dirpath, dirnames, filenames in os.walk(path):
            rel = os.path.relpath(dirpath, path)
            names = list(filenames) + [d for d in dirnames if os.path.islink(os.path.join(dirpath, d))]
            dirnames[:] = [d for d in dirnames if not os.path.islink(os.path.join(dirpath, d))]
            files[rel + '/'] = stat.S_IMODE(os.lstat(dirpath).st_mode)
            for n in names:
                p = os.path.join(dirpath, n)
                key = os.path.normpath(os.path.join(rel, n))
                st = os.lstat(p)
                if rel == '.' and n == '.git':
                    continue
                if stat.S_ISLNK(st.st_mode):
                    files[key] = ('link', os.readlink(p))
                elif stat.S_ISREG(st.st_mode):
                    files[key] = (stat.S_IMODE(st.st_mode), Path(p).read_bytes())
                else:
                    files[key] = ('other', stat.S_IFMT(st.st_mode))
        gitdir = git(path, 'rev-parse', '--absolute-git-dir').decode().strip()
        return dict(head=git(path, 'rev-parse', 'HEAD'), ref=git(path, 'rev-parse', '--symbolic-full-name', 'HEAD'),
                    index=Path(gitdir, 'index').read_bytes(), files=files)

    def view(path):
        """Restorable state: HEAD, full index, nonignored bytes/modes, status."""
        listed = git(path, 'ls-files', '-z', '-c', '-o', '--exclude-standard').split(b'\0')
        try:
            head_listed = git(path, 'ls-tree', '-r', '-z', '--name-only', 'HEAD').split(b'\0')
        except subprocess.CalledProcessError:
            head_listed = []
        files = {}
        for name in sorted(set(n for n in listed + head_listed if n)):
            p = os.path.join(path, os.fsdecode(name))
            if os.path.lexists(p):
                files[name] = (stat.S_IMODE(os.lstat(p).st_mode), Path(p).read_bytes())
        return dict(head=git(path, 'rev-parse', 'HEAD'), index=git(path, 'ls-files', '-s', '-z'),
                    flags=git(path, 'ls-files', '-v', '-z'), files=files,
                    status=git(path, 'status', '--porcelain=v1', '-z', '--untracked-files=all'))

    def saved_id(result):
        m = re.search(r'^saved ([0-9a-f]{32}):', result.stdout, re.M)
        return m.group(1) if m else None

    def manifest(save_id):
        return json.loads((coord / 'saves' / save_id / 'manifest.json').read_text())

    def saves_of(worker):
        out = []
        for p in (coord / 'saves').iterdir():
            if re.fullmatch('[0-9a-f]{32}', p.name):
                try:
                    if json.loads((p / 'manifest.json').read_text()).get('worker') == worker:
                        out.append(p.name)
                except (OSError, ValueError):
                    pass
        return out

    def claims():
        return [json.loads(p.read_text()) for p in (coord / 'saves' / 'claims').glob('*.json')]

    def inspect_worker(worker):
        r = unio('save', 'inspect', '--worker', worker, '--json')
        return r.returncode, json.loads(r.stdout) if r.stdout.strip() else None

    # ---- source A: worker commits (with a merge) plus every dirty kind -----
    a = wt / 'mock-a'
    write(a / 'feature.py', 'print("feature")\n')
    git(a, 'add', 'feature.py')
    git(a, 'commit', '-qm', 'feature')
    blob = git(a, 'hash-object', '-w', '--stdin', data=b'side branch\n').decode().strip()
    side_index = base / 'side-index'
    side_env = dict(env, GIT_INDEX_FILE=str(side_index))
    subprocess.run(['git', 'read-tree', base_commit], cwd=a, env=side_env, check=True)
    subprocess.run(['git', 'update-index', '--add', '--cacheinfo', '100644,%s,side.txt' % blob], cwd=a, env=side_env, check=True)
    tree = subprocess.run(['git', 'write-tree'], cwd=a, env=side_env, check=True, capture_output=True).stdout.decode().strip()
    side = git(a, 'commit-tree', tree, '-p', base_commit, '-m', 'side').decode().strip()
    git(a, 'merge', '-q', '--no-ff', '-m', 'merge side', side)
    write(a / 'keep' / 'staged.txt', 'staged v2\n')
    git(a, 'add', 'keep/staged.txt')
    write(a / 'keep' / 'staged.txt', 'unstaged v3\n')
    write(a / 'README.md', 'unstaged readme\n')
    git(a, 'update-index', '--chmod=+x', 'data/blob.bin')
    git(a, 'rm', '-q', 'docs/old.md')
    os.unlink(a / 'docs' / 'gone.md')
    write(a / 'added.txt', 'staged new file\n')
    git(a, 'add', 'added.txt')
    write(a / 'notes' / 'new.txt', 'private untracked\n', 0o600)
    write(a / 'notes' / 'empty-new', b'')
    write(a / 'bin' / 'run.sh', '#!/bin/sh\necho run\n', 0o755)
    write(a / 'img.bin', bytes(reversed(range(256))) + b'\0\0\xff')
    write(a / 'cache' / 'big.bin', b'ignored cache\n')
    write(a / 'debug.log', 'ignored log\n')
    before_a = snap(a)
    view_a = view(a)
    check('source has role cards (ignored symlinks) beside its work',
          os.path.islink(a / 'CLAUDE.md') and (a / 'WORKER.md').is_file())

    created = unio('save', 'create', 'mock-a', 'T1')
    sid = saved_id(created)
    check('create succeeds while STOP is set', created.returncode == 0 and sid is not None)
    check('source HEAD/index/bytes/modes unchanged by create', snap(a) == before_a)
    store = coord / 'saves'
    sdir = store / sid
    check('store and save are private directories',
          stat.S_IMODE(store.stat().st_mode) == 0o700 and stat.S_IMODE(sdir.stat().st_mode) == 0o700
          and stat.S_IMODE((sdir / 'pool').stat().st_mode) == 0o700)
    check('save holds exactly manifest, context, pool and bundle',
          sorted(os.listdir(sdir)) == ['bundle', 'context', 'manifest.json', 'pool']
          and os.listdir(sdir / 'context') == ['task.md'])
    check('stored files are 0600',
          all(stat.S_IMODE(p.lstat().st_mode) == 0o600 for p in [sdir / 'manifest.json', sdir / 'bundle', sdir / 'context' / 'task.md', *(sdir / 'pool').iterdir()]))
    m = manifest(sid)
    entries = {e['path']: e for e in m['entries']}
    check('manifest has the exact schema-1 keys',
          set(m) == {'schema_version', 'status', 'content_complete', 'save_id', 'worker', 'task', 'run_id', 'reason',
                     'provider_exit', 'observed_at', 'published_at', 'fingerprint', 'git', 'entries', 'context'}
          and m['schema_version'] == 1 and m['status'] == 'complete' and m['content_complete'] is True
          and m['reason'] == 'manual' and m['provider_exit'] is None and m['run_id'] is None)
    check('task context is literal bytes',
          (sdir / 'context' / 'task.md').read_bytes() == (coord / 'tasks' / 'T1.md').read_bytes()
          and m['context']['literal'] is True)
    check('commit range is complete and includes the merge',
          m['git']['base_commit'] == base_commit and len(m['git']['commit_ids']) == 3
          and m['git']['commit_ids'][-1] == git(a, 'rev-parse', 'HEAD').decode().strip()
          and side in m['git']['commit_ids'] and m['git']['bundle_bytes'] == (sdir / 'bundle').stat().st_size)
    check('staged and unstaged bytes are stored separately',
          entries['keep/staged.txt']['index']['sha256'] != entries['keep/staged.txt']['worktree']['sha256'])
    check('index and disk modes are kept separately',
          entries['data/blob.bin']['index']['mode'] == '100755' and entries['data/blob.bin']['worktree']['mode'] == '0644')
    check('deletions are explicit absences',
          entries['docs/old.md'] == {'path': 'docs/old.md', 'index': None, 'worktree': None}
          and entries['docs/gone.md']['index'] is not None and entries['docs/gone.md']['worktree'] is None)
    check('untracked files have a null index',
          entries['notes/new.txt']['index'] is None and entries['notes/new.txt']['worktree']['mode'] == '0600')
    check('empty files are actual blobs',
          entries['notes/empty-new']['worktree']['bytes'] == 0 and entries['empty.txt']['index']['bytes'] == 0
          and (sdir / 'pool' / entries['empty.txt']['index']['sha256']).stat().st_size == 0)
    check('ignored caches and role cards are omitted',
          not any(p.startswith(('cache/', 'WORKER.md', 'CLAUDE.md', 'AGENTS.md', 'GEMINI.md', '.unio-worker')) or p.endswith('.log')
                  for p in entries))
    check('entries are sorted and unique', list(entries) == sorted(entries) and len(entries) == len(m['entries']))

    ins = unio('save', 'inspect', sid, '--json')
    doc = json.loads(ins.stdout)
    check('inspect by ID validates without a worker lock',
          ins.returncode == 0 and doc['valid'] is True and doc['verified'] is False
          and doc['summary']['untracked'] == 4 and doc['summary']['removed'] == 1 and 'entries' not in doc['manifest'])
    rc, w = inspect_worker('mock-a')
    check('inspect --worker shows last good, attempt and live state',
          rc == 0 and w['last_good']['save_id'] == sid and w['latest_attempt']['status'] == 'complete'
          and w['latest_attempt']['save_id'] == sid and w['live'] == 'saved')
    check('inspect is read-only for the source', snap(a) == before_a)
    human = unio('save', 'inspect', sid)
    check('human inspect is short and says unverified', human.returncode == 0 and 'unverified' in human.stdout
          and len(human.stdout.splitlines()) <= 8)

    lock = open(coord / '.locks' / 'mock-a.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX)
    rc, w = inspect_worker('mock-a')
    check('live inspection of a busy worker is Unknown', rc == 0 and w['live'] == 'unknown' and w['last_good']['save_id'] == sid)
    busy = unio('save', 'create', 'mock-a', 'T1')
    check('create refuses a busy source with exit 2', busy.returncode == 2)
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()

    # ---- exact restore --------------------------------------------------
    b = wt / 'mock-b'
    restored = unio('save', 'restore', sid, 'mock-b')
    check('restore succeeds while STOP is set', restored.returncode == 0)
    vb = view(b)
    check('restored HEAD equals source HEAD', vb['head'] == view_a['head'])
    check('restored full index (paths, modes, object IDs) equals source', vb['index'] == view_a['index'] and vb['flags'] == view_a['flags'])
    check('restored nonignored bytes and modes equal source', vb['files'] == view_a['files'])
    check('restored status equals source status', vb['status'] == view_a['status'])
    check('destination role cards and marker preserved',
          (b / '.unio-worker').read_text().strip() == 'mock-b' and 'mock-b' in (b / 'WORKER.md').read_text()
          and os.readlink(b / 'CLAUDE.md') == 'WORKER.md')
    check('ignored source files are not copied', not (b / 'cache').exists() and not (b / 'debug.log').exists())
    check('destination branch moved, other branches did not',
          git(b, 'symbolic-ref', 'HEAD').strip() == b'refs/heads/agent/mock-b'
          and git(repo, 'rev-parse', 'main').decode().strip() == base_commit
          and git(repo, 'rev-parse', 'agent/mock-a') == view_a['head'])
    check('source unchanged by restore', snap(a) == before_a)
    cs = [c for c in claims() if c['save_id'] == sid]
    check('restore records one restored claim',
          len(cs) == 1 and cs[0]['state'] == 'restored' and cs[0]['outcome'] == {'exit_code': 0, 'reason': 'restored'}
          and cs[0]['new_task'] is None and cs[0]['source_fingerprint'] == m['fingerprint'])
    again = unio('save', 'restore', sid, 'mock-b')
    check('restore into a now-dirty destination refuses', again.returncode == 1 and 'destination_rejected' in again.stderr)

    # ---- equal base: no commits, no bundle ------------------------------
    c, d = wt / 'mock-c', wt / 'mock-d'
    write(c / 'README.md', 'equal-base staged\n')
    git(c, 'add', 'README.md')
    write(c / 'README.md', 'equal-base unstaged\n')
    write(c / 'bin' / 'tool.sh', '#!/bin/sh\necho changed\n', 0o700)
    write(c / 'loose.txt', 'loose\n')
    view_c = view(c)
    eq = unio('save', 'create', 'mock-c', 'T2')
    eid = saved_id(eq)
    me = manifest(eid) if eid else {}
    check('equal-base save has no commits and no bundle',
          eq.returncode == 0 and me['git']['commit_ids'] == [] and me['git']['bundle_sha256'] is None
          and me['git']['bundle_bytes'] == 0 and not (store / eid / 'bundle').exists())
    er = unio('save', 'restore', eid, 'mock-d')
    check('equal-base restore is exact', er.returncode == 0 and view(d) == view_c)

    # ---- corrupt or unsafe saves are refused before any mutation --------
    f = wt / 'mock-f'
    before_f = snap(f)

    def refused_cleanly(label, save_id=sid):
        i = unio('save', 'inspect', save_id, '--json')
        r = unio('save', 'restore', save_id, 'mock-f')
        check(label, i.returncode == 1 and json.loads(i.stdout)['valid'] is False
              and r.returncode == 1 and 'invalid_save' in r.stderr and snap(f) == before_f)

    pool_file = sdir / 'pool' / entries['README.md']['worktree']['sha256']
    original = pool_file.read_bytes()
    os.chmod(pool_file, 0o600)
    pool_file.write_bytes(b'X' + original[1:])
    refused_cleanly('flipped pool byte refused; destination untouched')
    pool_file.write_bytes(original)
    pool_file.rename(base / 'moved')
    refused_cleanly('missing pool file refused')
    (base / 'moved').rename(pool_file)
    write(sdir / 'extra', b'x', 0o600)
    refused_cleanly('extra stored file refused')
    os.unlink(sdir / 'extra')
    os.chmod(pool_file, 0o644)
    refused_cleanly('non-private pool file refused')
    os.chmod(pool_file, 0o600)
    mpath = sdir / 'manifest.json'
    mtext = mpath.read_bytes()
    mpath.write_bytes(mtext.replace(b'"schema_version": 1', b'"schema_version": 2'))
    i = unio('save', 'inspect', sid)
    check('unknown schema is named as unsupported', i.returncode == 1 and 'unsupported save schema' in i.stderr)
    refused_cleanly('unknown schema refused')
    mpath.write_bytes(mtext.replace(b'{', b'{"status": "complete", ', 1))
    refused_cleanly('duplicate manifest key refused')
    mpath.write_bytes(mtext.replace(b'"reason": "manual"', b'"reason": "manual", "extra": 1'))
    refused_cleanly('unknown manifest key refused')
    mpath.unlink()
    shutil.copy(base / 'side-index', base / 'unused')
    (base / 'manifest-copy.json').write_bytes(mtext)
    os.symlink(base / 'manifest-copy.json', mpath)
    refused_cleanly('symlinked manifest refused')
    mpath.unlink()
    write(mpath, mtext, 0o600)
    bpath = sdir / 'bundle'
    bundle_bytes = bpath.read_bytes()
    bpath.write_bytes(bundle_bytes[:-30] + bytes(30))
    refused_cleanly('corrupt bundle refused')
    bpath.write_bytes(bundle_bytes)
    check('restored corruption fixtures validate again', unio('save', 'inspect', sid).returncode == 0)
    os.chmod(store, 0o755)
    i = unio('save', 'inspect', sid)
    cr = unio('save', 'create', 'mock-c', 'T2')
    check('unsafe (non-private) store refused without repair',
          i.returncode == 1 and cr.returncode == 1 and 'unsafe save store' in cr.stderr
          and stat.S_IMODE(store.stat().st_mode) == 0o755)
    os.chmod(store, 0o700)

    # ---- destination rejection ------------------------------------------
    lock = open(coord / '.locks' / 'mock-f.lock', 'a')
    fcntl.flock(lock, fcntl.LOCK_EX)
    r = unio('save', 'restore', sid, 'mock-f')
    check('busy destination exits 2 untouched', r.returncode == 2 and snap(f) == before_f)
    fcntl.flock(lock, fcntl.LOCK_UN)
    lock.close()
    r = unio('save', 'restore', sid, 'mock-a')
    check('restore into the source worker refused', r.returncode == 1 and snap(a) == before_a)
    write(f / 'stray.txt', 'dirty\n')
    dirty = snap(f)
    r = unio('save', 'restore', sid, 'mock-f')
    check('dirty destination refused untouched', r.returncode == 1 and 'not clean' in r.stderr and snap(f) == dirty)
    os.unlink(f / 'stray.txt')
    h = wt / 'mock-h'
    write(h / 'other.txt', 'other\n')
    git(h, 'add', 'other.txt')
    git(h, 'commit', '-qm', 'other')
    before_h = snap(h)
    r = unio('save', 'restore', sid, 'mock-h')
    check('wrong-base destination refused untouched', r.returncode == 1 and 'saved base' in r.stderr and snap(h) == before_h)
    r = unio('save', 'restore', sid, 'mock-nope')
    check('missing destination refused', r.returncode == 1)
    r = unio('save', 'restore', 'not-a-save-id', 'mock-f')
    check('malformed save ID is a usage error', r.returncode == 2)
    r = unio('save', 'create', '../escape', 'T1')
    check('path-like worker ID is a usage error', r.returncode == 2)

    # Collision with an ignored destination file (the saved .gitignore no
    # longer ignores *.log, so the source's log became saved content).
    i_wt = wt / 'mock-i'
    write(c / '.gitignore', 'cache/\n.env\n')
    write(c / 'notes.log', 'saved log\n')
    col = unio('save', 'create', 'mock-c', 'T2')
    col_id = saved_id(col)
    write(i_wt / 'notes.log', 'destination ignored log\n')
    before_i = snap(i_wt)
    r = unio('save', 'restore', col_id, 'mock-i')
    check('ignored-path collision refused before mutation',
          col.returncode == 0 and r.returncode == 1 and 'collides' in r.stderr and snap(i_wt) == before_i)

    # ---- rollback and Unknown -------------------------------------------
    r = unio('save', 'restore', sid, 'mock-f', fault='restore-after-worktree')
    fc = [x for x in claims() if x['destination'] == 'mock-f']
    check('failed restore rolls back to the exact preimage',
          r.returncode == 1 and 'rolled back' in r.stderr and snap(f) == before_f
          and len(fc) == 1 and fc[0]['state'] == 'failed' and fc[0]['outcome']['exit_code'] == 1)
    r = unio('save', 'restore', sid, 'mock-f')
    check('a proven rollback allows a later explicit restore', r.returncode == 0 and view(f) == view_a)
    g_wt = wt / 'mock-g'
    r = unio('save', 'restore', sid, 'mock-g', fault='restore-after-worktree,restore-rollback')
    gc = [x for x in claims() if x['destination'] == 'mock-g']
    check('unprovable rollback is Unknown with exit 2',
          r.returncode == 2 and 'Unknown' in r.stderr and len(gc) == 1 and gc[0]['state'] == 'unknown')
    r = unio('save', 'restore', eid, 'mock-g')
    check('an Unknown destination is never restored into again', r.returncode == 1 and 'unresolved' in r.stderr)
    check('source unchanged after all restores', snap(a) == before_a)

    # ---- unstable bytes, refusals and last-good retention ---------------
    e = wt / 'mock-e'
    write(e / 'work.txt', 'work v1\n')
    good = unio('save', 'create', 'mock-e', 'T1')
    good_id = saved_id(good)
    check('mock-e has a last good save', good.returncode == 0)
    p = subprocess.Popen([at, 'save', 'create', 'mock-e', 'T1'], cwd=repo, env=dict(env, UNIO_SAVE_TEST_FAULT='between-passes'),
                         stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    stopped = None
    for _ in range(400):
        for pid in os.listdir('/proc'):
            if pid.isdigit():
                try:
                    fields = Path('/proc', pid, 'stat').read_text().rsplit(')', 1)[1].split()
                except OSError:
                    continue
                if fields[0] == 'T' and int(fields[1]) == p.pid:
                    stopped = int(pid)
        if stopped or p.poll() is not None:
            break
        time.sleep(0.05)
    write(e / 'work.txt', 'work v2 changed between observations\n')
    if stopped:
        os.kill(stopped, signal.SIGCONT)
    out, err = p.communicate(timeout=60)
    check('changing bytes between observations refuse as unstable',
          stopped is not None and p.returncode == 1 and 'unstable' in err)
    rc, w = inspect_worker('mock-e')
    check('refused attempt is separate from the kept last good save',
          w['last_good']['save_id'] == good_id and w['latest_attempt']['status'] == 'refused'
          and w['latest_attempt']['reason'] == 'unstable' and w['latest_attempt']['save_id'] is None
          and w['latest_attempt']['last_good_id'] == good_id and w['live'] == 'changed')

    def refuses(label, code):
        before = snap(e)
        count = len(saves_of('mock-e'))
        r = unio('save', 'create', 'mock-e', 'T1')
        ok = r.returncode == 1 and '(%s)' % code in r.stderr and snap(e) == before and len(saves_of('mock-e')) == count
        if not ok:
            print(r.stdout, r.stderr)
        check(label, ok)

    write(e / '.env', 'TOKEN=1\n')
    refuses('ignored secret name refuses', 'secret_name')
    os.unlink(e / '.env')
    write(e / 'keys' / 'id_rsa', 'key\n')
    refuses('secret key file refuses', 'secret_name')
    shutil.rmtree(e / 'keys')
    os.symlink('README.md', e / 'link.md')
    refuses('nonignored symlink refuses', 'unsupported_type')
    git(e, 'add', 'link.md')
    refuses('symlink in the index refuses', 'unsupported_type')
    git(e, 'rm', '-q', '--cached', 'link.md')
    os.unlink(e / 'link.md')
    os.mkfifo(e / 'pipe')
    refuses('FIFO refuses', 'unsupported_type')
    os.unlink(e / 'pipe')
    (e / 'nested' / '.git').mkdir(parents=True)
    refuses('nested repository refuses', 'unsupported_type')
    shutil.rmtree(e / 'nested')
    os.link(e / 'work.txt', e / 'hard.txt')
    refuses('hard link refuses', 'unsupported_type')
    os.unlink(e / 'hard.txt')
    for flag in ('--assume-unchanged', '--skip-worktree'):
        git(e, 'update-index', flag, 'README.md')
        refuses('%s index flag refuses' % flag, 'unsupported_git')
        git(e, 'update-index', '--no-' + flag[2:], 'README.md')
    write(e / 'ita.txt', 'intent\n')
    git(e, 'add', '-N', 'ita.txt')
    refuses('intent-to-add refuses', 'unsupported_git')
    git(e, 'rm', '-q', '--cached', 'ita.txt')
    os.unlink(e / 'ita.txt')
    oid = git(e, 'hash-object', '-w', '--stdin', data=b'conflict\n').decode().strip()
    git(e, 'update-index', '--index-info', data=('100644 %s 1\tconflict.txt\n100644 %s 2\tconflict.txt\n' % (oid, oid)).encode())
    refuses('unmerged index refuses', 'unsupported_git')
    git(e, 'update-index', '--force-remove', 'conflict.txt')
    missing = '1' * 40
    git(e, 'update-index', '--add', '--cacheinfo', '100644,%s,ghost.txt' % missing)
    refuses('missing index blob refuses as incomplete', 'incomplete')
    git(e, 'update-index', '--force-remove', 'ghost.txt')
    egitdir = Path(git(e, 'rev-parse', '--absolute-git-dir').decode().strip())
    write(egitdir / 'MERGE_HEAD', base_commit + '\n')
    refuses('merge in progress refuses', 'unsupported_git')
    os.unlink(egitdir / 'MERGE_HEAD')
    git(e, 'config', 'core.sparseCheckout', 'true')
    refuses('sparse checkout refuses', 'unsupported_git')
    git(e, 'config', '--unset', 'core.sparseCheckout')
    git(e, 'checkout', '-q', '--detach')
    refuses('detached HEAD refuses', 'unsupported_git')
    git(e, 'checkout', '-q', 'agent/mock-e')
    write(e / '-rf', 'x\n')
    refuses('leading-hyphen name refuses', 'unsafe_name')
    os.unlink(e / '-rf')
    write(e / 'back\\slash.txt', 'x\n')
    refuses('backslash name refuses', 'unsafe_name')
    os.unlink(e / 'back\\slash.txt')
    # Index entries, so the check also runs on case-insensitive filesystems.
    for name in ('Case.txt', 'case.txt'):
        git(e, 'update-index', '--add', '--cacheinfo', '100644,%s,%s' % (oid, name))
    refuses('ASCII-case collision refuses', 'unsafe_name')
    git(e, 'update-index', '--force-remove', 'Case.txt', 'case.txt')
    git(e, 'update-index', '-z', '--index-info', data=b'100644 ' + oid.encode() + b'\tbad-\xff.txt\0')
    refuses('non-UTF-8 name refuses', 'unsafe_name')
    git(e, 'update-index', '-z', '--index-info', data=b'0 ' + b'0' * 40 + b'\tbad-\xff.txt\0')
    write(e / 'huge.bin', b'\0' * (4 * 1024 * 1024 + 1))
    refuses('body over 4 MiB refuses', 'excessive')
    os.unlink(e / 'huge.bin')
    write(coord / 'tasks' / 'T1.md', b'#' * (1024 * 1024 + 1))
    refuses('task context over 1 MiB refuses', 'excessive')
    write(coord / 'tasks' / 'T1.md', '# T1\nFinish the feature.\n## Validate\n$ false\n')
    r = unio('save', 'create', 'mock-e', 'T-missing')
    check('missing task refuses as incomplete', r.returncode == 1 and '(incomplete)' in r.stderr)

    j = wt / 'mock-j'
    write(j / 'config' / 'Secrets.YAML', 'password: x\n')
    git(j, 'add', '-A')
    git(j, 'commit', '-qm', 'carry a secret')
    git(j, 'rm', '-q', 'config/Secrets.YAML')
    git(j, 'commit', '-qm', 'delete it again')
    r = unio('save', 'create', 'mock-j', 'T1')
    check('a secret added then deleted in carried history refuses',
          r.returncode == 1 and '(secret_name)' in r.stderr and 'carried commit' in r.stderr and not saves_of('mock-j'))

    # ---- interrupted publication keeps the last good save ----------------
    r = unio('save', 'create', 'mock-e', 'T1', fault='publish-interrupt')
    staged = [n for n in os.listdir(store) if n.startswith('.staging-')]
    rc, w = inspect_worker('mock-e')
    check('interrupted publication leaves no save and keeps the last good',
          r.returncode != 0 and len(staged) == 1 and w['last_good']['save_id'] == good_id
          and saves_of('mock-e') == [good_id])
    ok = unio('save', 'create', 'mock-e', 'T1')
    check('next create cleans abandoned staging',
          ok.returncode == 0 and not [n for n in os.listdir(store) if n.startswith('.staging-')])
    last = saved_id(ok)
    write(e / 'work.txt', 'work v3\n')
    r = unio('save', 'create', 'mock-e', 'T1', fault='publish-after-rename')
    rc, w = inspect_worker('mock-e')
    check('a crash after the rename is still discoverable as last good',
          r.returncode != 0 and w['last_good']['save_id'] not in (good_id, last) and len(saves_of('mock-e')) == 3)

    # ---- retention, pinning and caps -------------------------------------
    for n in range(4):
        write(e / 'work.txt', 'retention %d\n' % n)
        check('retention save %d' % n, unio('save', 'create', 'mock-e', 'T1').returncode == 0)
    kept = saves_of('mock-e')
    check('latest 5 unreferenced saves kept per worker', len(kept) == 5 and good_id not in kept)
    for n in range(5):
        write(a / 'README.md', 'pin %d\n' % n)
        check('pinning save %d' % n, unio('save', 'create', 'mock-a', 'T1').returncode == 0)
    check('a claimed save stays pinned beyond the latest 5', sid in saves_of('mock-a') and len(saves_of('mock-a')) == 6)
    newest = inspect_worker('mock-e')[1]['last_good']['save_id']
    fakes = []
    for n in range(4):
        fake = store / ('%032x' % (0xfeed0000 + n))
        fake.mkdir(mode=0o700)
        write(fake / 'manifest.json', '{"worker": "mock-e", "broken": true}', 0o600)
        fakes.append(fake)
    write(e / 'work.txt', 'over the cap\n')
    r = unio('save', 'create', 'mock-e', 'T1')
    rc, w = inspect_worker('mock-e')
    check('corrupt evidence counts toward the worker cap and refuses',
          r.returncode == 1 and '(excessive)' in r.stderr and w['corrupt_evidence'] == 4
          and w['last_good']['save_id'] == newest and all(x.exists() for x in fakes))
    for fake in fakes:
        shutil.rmtree(fake)
    while len([n for n in os.listdir(store) if re.fullmatch('[0-9a-f]{32}', n)]) < 33:
        junk = store / os.urandom(16).hex()
        junk.mkdir(mode=0o700)
        fakes.append(junk)
    r = unio('save', 'create', 'mock-e', 'T1')
    check('project cap refuses while corrupt evidence fills it', r.returncode == 1 and '(excessive)' in r.stderr)
    for fake in fakes:
        shutil.rmtree(fake, ignore_errors=True)
    check('create works again once evidence is cleared', unio('save', 'create', 'mock-e', 'T1').returncode == 0)

    # ---- retained HEAD paths, including ignored leaves and parents --------
    check('fresh regression workers initialize', unio('init', 'mock-y', 'mock-z', 'mock-x').returncode == 0)
    y, z, x = (wt / ('mock-' + c) for c in 'yzx')
    write(y / '.gitignore', '*.log\n/ign/\n')
    write(y / 'tracked.log', b'tracked-log\x00', 0o640)
    write(y / 'ign/req.txt', b'required bytes\n', 0o750)
    git(y, 'add', '-f', '.gitignore', 'tracked.log', 'ign/req.txt')
    git(y, 'commit', '-qm', 'track ignored required files')
    git(y, 'rm', '--cached', 'tracked.log', 'ign/req.txt')
    retained_before, retained_view = snap(y), view(y)
    r = unio('save', 'create', 'mock-y', 'T1')
    retained_id = saved_id(r)
    check('create preserves ignored HEAD files removed from index', r.returncode == 0 and retained_id)
    retained_entries = {e['path']: e for e in manifest(retained_id)['entries']}
    check('manifest retains leaf and ignored-parent bytes with absent index',
          all(retained_entries[p]['index'] is None and retained_entries[p]['worktree'] is not None
              for p in ('tracked.log', 'ign/req.txt')))
    check('retained save inspects successfully', unio('save', 'inspect', retained_id, '--json').returncode == 0)
    retained_restore = unio('save', 'restore', retained_id, 'mock-z')
    check('retained save restores into a clean different worker',
          retained_restore.returncode == 0,
          'exit %d\n%s\n%s' % (retained_restore.returncode, retained_restore.stdout, retained_restore.stderr))
    check('restored HEAD, full index, status and required bytes/modes exactly match', view(z) == retained_view)
    check('retained source raw index, HEAD and all on-disk state unchanged', snap(y) == retained_before)

    # ---- unsafe native admission never writes targets, workers or evidence -
    locks = coord / '.locks'
    target = base / 'lock target'
    def evidence():
        return {str(p.relative_to(store)): (stat.S_IMODE(p.stat().st_mode), p.read_bytes())
                for p in store.rglob('*') if p.is_file()}

    def install_unsafe(kind, lock):
        lock.unlink(missing_ok=True)
        if kind in ('absent symlink', 'existing symlink', 'hardlink'):
            target.unlink(missing_ok=True)
            if kind != 'absent symlink':
                write(target, b'TARGET MUST NOT CHANGE\x00', 0o640)
            if kind == 'hardlink':
                os.link(target, lock)
            else:
                os.symlink(target, lock)
        elif kind == 'FIFO':
            os.mkfifo(lock)
        elif kind == 'directory':
            lock.mkdir()
        else:
            write(lock, b'LOCK MUST NOT CHANGE\n', 0o666 if kind == 'writable file' else 0o644)
            if kind == 'writable lock parent':
                locks.chmod(0o777)
            elif kind == 'writable coordination parent':
                coord.chmod(0o777)

    def remove_unsafe(lock):
        locks.chmod(0o755)
        coord.chmod(0o755)
        if lock.is_dir() and not lock.is_symlink():
            lock.rmdir()
        else:
            lock.unlink(missing_ok=True)
        target.unlink(missing_ok=True)

    for kind in ('absent symlink', 'existing symlink', 'hardlink', 'FIFO', 'directory',
                 'writable file', 'writable lock parent', 'writable coordination parent'):
        for worker, args in [('mock-y', ('save', 'create', 'mock-y', 'T1')),
                             ('mock-x', ('save', 'restore', retained_id, 'mock-x'))]:
            lock = locks / (worker + '.lock')
            install_unsafe(kind, lock)
            try:
                before_workers, before_evidence = (snap(y), snap(x)), evidence()
                target_before = (target.read_bytes(), stat.S_IMODE(target.stat().st_mode)) if target.exists() else None
                started = time.monotonic()
                r = unio(*args, timeout=8)
                check('%s %s refuses unsafe admission promptly as known failure' % (args[1], kind),
                      r.returncode == 1 and time.monotonic() - started < 8)
                target_after = (target.read_bytes(), stat.S_IMODE(target.stat().st_mode)) if target.exists() else None
                check('%s %s preserves target, source, destination and saved/claim evidence' % (args[1], kind),
                      target_before == target_after and (snap(y), snap(x)) == before_workers and evidence() == before_evidence)
                if worker == 'mock-y':
                    rc, observation = inspect_worker(worker)
                    check('%s live inspection is Unknown without blocking' % kind,
                          rc == 0 and observation['live'] == 'unknown')
                    check('inspect by ID is independent of %s native lock' % kind,
                          unio('save', 'inspect', retained_id, '--json', timeout=8).returncode == 0)
            finally:
                remove_unsafe(lock)

    # A symlinked lock directory is rejected before following it or creating
    # leaf files there. Existing saves can still be inspected read-only.
    original_locks = base / 'original locks'
    outside_locks = base / 'outside locks'
    outside_locks.mkdir()
    locks.rename(original_locks)
    os.symlink(outside_locks, locks)
    try:
        before_workers, before_evidence = (snap(y), snap(x)), evidence()
        check('symlink parent refuses create and restore',
              unio('save', 'create', 'mock-y', 'T1', timeout=8).returncode == 1
              and unio('save', 'restore', retained_id, 'mock-x', timeout=8).returncode == 1)
        rc, observation = inspect_worker('mock-y')
        check('symlink parent live inspection is Unknown', rc == 0 and observation['live'] == 'unknown')
        check('symlink parent leaves outside directory, workers and evidence unchanged',
              not list(outside_locks.iterdir()) and (snap(y), snap(x)) == before_workers and evidence() == before_evidence)
    finally:
        locks.unlink()
        original_locks.rename(locks)

    for worker, args in [('mock-y', ('save', 'create', 'mock-y', 'T1')),
                         ('mock-x', ('save', 'restore', retained_id, 'mock-x'))]:
        lock = locks / (worker + '.lock')
        write(lock, b'legacy native lock\n', 0o644)
        before_workers, before_evidence = (snap(y), snap(x)), evidence()
        with lock.open('rb') as held:
            fcntl.flock(held, fcntl.LOCK_SH | fcntl.LOCK_NB)
            check('%s held legacy lock is busy exit2' % args[1], unio(*args, timeout=8).returncode == 2)
            if worker == 'mock-y':
                rc, observation = inspect_worker(worker)
                check('genuine busy inspection is Unknown', rc == 0 and observation['live'] == 'unknown')
        check('%s contention preserves workers and saved evidence' % args[1],
              (snap(y), snap(x)) == before_workers and evidence() == before_evidence)
        check('%s admits an idle owned legacy0644 lock' % args[1], unio(*args).returncode == 0)
        check('%s does not rewrite legacy lock bytes or permissions' % args[1],
              lock.read_bytes() == b'legacy native lock\n' and stat.S_IMODE(lock.stat().st_mode) == 0o644)
    check('legacy restore still matches retained state exactly', view(x) == retained_view)
    check('retained source remains byte-for-byte unchanged after lock tests', snap(y) == retained_before)

    # Removing every tracked path from the index is supported, even while
    # retained HEAD files remain on disk. Git must publish an actual empty index.
    check('empty-index regression workers initialize', unio('init', 'mock-u', 'mock-v').returncode == 0)
    u, v = wt / 'mock-u', wt / 'mock-v'
    git(u, 'rm', '--cached', '-r', '.')
    empty_before, empty_view = snap(u), view(u)
    check('source has an empty index with retained HEAD files', git(u, 'ls-files', '-s', '-z') == b'')
    r = unio('save', 'create', 'mock-u', 'T1')
    empty_id = saved_id(r)
    check('create captures an empty index', r.returncode == 0 and empty_id)
    check('manifest preserves absent index entries',
          all(e['index'] is None for e in manifest(empty_id)['entries']))
    check('restore materializes a valid empty index', unio('save', 'restore', empty_id, 'mock-v').returncode == 0)
    check('empty-index restore matches HEAD, files, modes and staged removal',
          git(v, 'ls-files', '-s', '-z') == b'' and view(v) == empty_view)
    check('empty-index capture and restore leave source raw state unchanged', snap(u) == empty_before)

    # ---- help, completion and zero provider calls -------------------------
    help_text = unio('help').stdout
    check('help documents the save commands',
          'unio save create <w> <task>' in help_text and 'unio save restore <save-id> <dest>' in help_text)
    usage = unio('save')
    check('bare save prints usage with exit 2', usage.returncode == 2 and 'unio save inspect' in usage.stderr)
    comp = subprocess.run(['bash', '-c', 'source "$1"; cd "$2"; COMP_WORDS=(unio save ""); COMP_CWORD=2; _unio; echo "${COMPREPLY[*]}"',
                           '_', str(base / 'completion' / 'unio'), str(repo)], capture_output=True, text=True, env=env)
    check('completion offers the save subcommands', comp.returncode == 0 and comp.stdout.split() == ['create', 'inspect', 'restore', 'continue', 'usage'])
    check('source unchanged at the end', snap(a)['index'] == before_a['index'] and snap(a)['head'] == before_a['head'])
    check('provider stub was never invoked', not calls.exists())

print('work-saving: %d checks passed' % passed[0])
