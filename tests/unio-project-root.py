#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Project-root discovery guard regressions. Mock-only, offline.

A nested uninitialized Git repository below an enclosing workspace used
to let find_root walk past the Git boundary, so `unio account mock codex`
run before the inner `unio init` edited the real project's policy. These
regressions freeze the outer policy and STOP bytes and require every
setter plus stop/resume to refuse from unrelated nested repositories —
unborn and committed ones under workspace scratch, ones inside the main
clone, copied worker markers, and a linked worktree — with no lock,
policy or provider activity.
The main clone (non-default name, path with spaces), registered worker
worktrees (.git files, with and without the marker), the workspace root,
non-Git scratch directories, genuine Bash logical symlink paths, an
initialized inner workspace using its own state, and an explicitly targeted
read-only command keep working. No live provider is called; the configured agent
command writes a canary file that must stay absent.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

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


with tempfile.TemporaryDirectory(prefix='project-root-') as directory:
    base = Path(directory)
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'),
               UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'),
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid',
               GIT_COMMITTER_EMAIL='mock@example.invalid',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0')
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env,
                   check=True, capture_output=True, timeout=180)
    at = str(base / 'bin' / 'unio')

    # The only configured agent command writes a canary; it must never run.
    canary = base / 'provider-called.txt'
    (base / 'conf' / 'agents.conf').write_text(
        'mock=bash -c \'printf ran >> "%s"\'\n' % canary)

    def git(*args, cwd):
        return subprocess.run(['git', *args], cwd=str(cwd), env=env,
                              check=True, capture_output=True)

    def unio(*args, cwd):
        return subprocess.run([at, *args], cwd=str(cwd), env=env,
                              capture_output=True, text=True, timeout=60)

    def logical_unio(*args, cwd):
        # subprocess(cwd=symlink) loses Bash's logical PWD. Actually cd in
        # Bash, assert the logical path, and pass all paths as positional args.
        return subprocess.run(
            ['bash', '--noprofile', '--norc', '-c',
             'cd -L -- "$1" && [ "$PWD" = "$1" ] && shift && exec "$@"',
             'logical-unio', str(cwd), at, *args], cwd=str(base), env=env,
            capture_output=True, text=True, timeout=60)

    # Outer project: non-default clone name, spaces in the workspace path.
    root = base / 'guard project'
    clone = root / 'myclone'
    (clone / 'src').mkdir(parents=True)
    git('init', '-q', '-b', 'dev', cwd=clone)
    (clone / 'seed.txt').write_text('seed\n')
    git('add', 'seed.txt', cwd=clone)
    git('commit', '-qm', 'seed', cwd=clone)
    init = unio('init', 'mockworker', cwd=clone)
    check('init scaffolds the outer project', init.returncode == 0, init)
    worker = root / 'wt' / 'mockworker'
    check('worker worktree registered with marker and .git file',
          (worker / '.unio-worker').is_file()
          and (worker / '.git').is_file() and not (worker / '.git').is_dir())
    (worker / 'src').mkdir()

    # A ledger row so the explicitly targeted read-only score works.
    (root / 'coord' / 'reports').mkdir(parents=True, exist_ok=True)
    (root / 'coord' / 'reports' / 'ledger.jsonl').write_text(
        '{"event":"run","worker":"mockworker","exit":"0","duration_s":2,'
        '"wall":"0","suspended":"0"}\n')

    # Known outer policy and STOP, then frozen bytes, mtimes and lock tree.
    for args in (('mode', 'yolo'), ('tier', 'high'), ('lead', 'mock'),
                 ('account', 'mockagent', 'codex')):
        out = unio(*args, cwd=clone / 'src')
        check('outer %s set from the clone' % args[0],
              out.returncode == 0, out)
    out = unio('stop', cwd=root)
    check('outer STOP set from the workspace root',
          out.returncode == 0 and (root / 'coord' / 'STOP').is_file(), out)

    policy_file = root / 'coord' / 'work-policy.json'
    stop_file = root / 'coord' / 'STOP'

    def snapshot():
        locks = sorted((str(p.relative_to(root)), p.is_symlink(),
                        p.lstat().st_mode)
                       for p in (root / 'coord' / '.locks').rglob('*'))
        return (policy_file.read_bytes(), stop_file.read_bytes(), locks)

    def stat_snapshot():
        policy, stop = policy_file.stat(), stop_file.stat()
        return snapshot() + (policy.st_mtime_ns, stop.st_mtime_ns)

    state = stat_snapshot()
    check('canary absent before refusals', not canary.exists())

    # Unrelated nested repositories: unborn and committed under workspace
    # scratch, committed inside the main clone, and a linked worktree.
    scratch = root / 'tmp scratch' / 'unio-next'
    unborn = scratch / 'nested-uninit'
    (unborn / 'sub').mkdir(parents=True)
    git('init', '-q', cwd=unborn)
    fullrepo = scratch / 'nested-full'
    (fullrepo / 'sub').mkdir(parents=True)
    git('init', '-q', '-b', 'main', cwd=fullrepo)
    (fullrepo / 'file.txt').write_text('x\n')
    git('add', 'file.txt', cwd=fullrepo)
    git('commit', '-qm', 'x', cwd=fullrepo)
    linked = scratch / 'nested-linked'
    git('worktree', 'add', str(linked), '-b', 'linked', cwd=fullrepo)
    inside = clone / 'vendor' / 'nested'
    (inside / 'sub').mkdir(parents=True)
    git('init', '-q', '-b', 'main', cwd=inside)
    (inside / 'file.txt').write_text('x\n')
    git('add', 'file.txt', cwd=inside)
    git('commit', '-qm', 'x', cwd=inside)
    check('linked worktree has a .git file',
          (linked / '.git').is_file() and not (linked / '.git').is_dir())

    refusals = (('mode', 'thorough'), ('tier', 'low'), ('lead', 'none'),
                ('account', 'mock', 'codex'), ('stop',), ('resume',))
    locations = (
        ('unborn scratch repo', unborn, (unborn, unborn / 'sub')),
        ('committed scratch repo', fullrepo, (fullrepo, fullrepo / 'sub')),
        ('linked worktree', linked, (linked,)),
        ('repo inside the main clone', inside, (inside, inside / 'sub')),
    )
    for name, boundary, dirs in locations:
        for d in dirs:
            for args in refusals:
                out = unio(*args, cwd=d)
                check('%s: %s refused' % (name, ' '.join(args)),
                      out.returncode != 0
                      and 'refusing to act on the enclosing project' in out.stderr
                      and str(boundary) in out.stderr, out)
        out = unio('account', 'mock', 'codex', cwd=boundary)
        check('%s: refusal explains the boundary and local init' % name,
              'unio init' in out.stderr and str(root) in out.stderr, out)
        check('%s: outer policy, STOP, mtimes and locks unchanged' % name,
              stat_snapshot() == state)
    check('no provider canary after refusals', not canary.exists())

    # A copied marker is not registration proof outside the supported
    # direct clone/wt layout, even inside the main clone's subtree.
    for name, marked in (('marked scratch repo', scratch / 'marked repo'),
                         ('marked repo inside clone', clone / 'vendor' / 'marked repo')):
        (marked / 'sub').mkdir(parents=True)
        git('init', '-q', cwd=marked)
        (marked / '.unio-worker').write_bytes((worker / '.unio-worker').read_bytes())
        for args in (('account', 'unrelated', 'codex'), ('stop',), ('resume',)):
            out = unio(*args, cwd=marked / 'sub')
            check('%s: %s refused despite copied marker' % (name, ' '.join(args)),
                  out.returncode != 0
                  and 'refusing to act on the enclosing project' in out.stderr
                  and str(marked) in out.stderr, out)
            check('%s: exact outer policy/STOP, mtimes and locks frozen' % name,
                  stat_snapshot() == state)

    # Explicitly targeted read-only command still works from a nested repo.
    out = unio('score', str(root), cwd=unborn / 'sub')
    check('explicit score targets the given root',
          out.returncode == 0 and 'mockworker' in out.stdout, out)

    # Preserved entry points: clone, worker worktrees (.git files), the
    # workspace root, non-Git scratch, and a symlinked path.
    plain = root / 'tmp scratch' / 'plain'
    plain.mkdir(parents=True)
    link = base / 'link to clone'
    link.symlink_to(clone)
    for name, d in (('clone subdirectory', clone / 'src'),
                    ('worker worktree root', worker),
                    ('worker subdirectory', worker / 'src'),
                    ('workspace root', root),
                    ('non-Git scratch directory', plain),
                    ('symlinked clone path', link / 'src')):
        out = unio('mode', cwd=d)
        check('%s reads the outer policy' % name,
              out.returncode == 0 and out.stdout.strip() == 'mode: yolo', out)
        out = unio('account', cwd=d)
        check('%s reads outer accounts' % name,
              out.returncode == 0 and 'mockagent=codex' in out.stdout, out)

    # stop/resume keep working from valid locations; bytes return to frozen.
    out = unio('resume', cwd=worker / 'src')
    check('resume from worker subdirectory clears STOP',
          out.returncode == 0 and not stop_file.exists(), out)
    out = unio('stop', cwd=clone / 'src')
    check('stop from clone subdirectory restores STOP bytes',
          out.returncode == 0 and stop_file.read_bytes() == state[1], out)
    out = unio('resume', cwd=root)
    check('resume from workspace root',
          out.returncode == 0 and not stop_file.exists(), out)
    out = unio('stop', cwd=root)
    check('outer STOP bytes back to frozen',
          out.returncode == 0 and stop_file.read_bytes() == state[1], out)

    # A worker worktree from before the marker exists is still selected.
    (worker / '.unio-worker').unlink()
    out = unio('mode', cwd=worker / 'src')
    check('pre-marker worker worktree still selected',
          out.returncode == 0 and out.stdout.strip() == 'mode: yolo', out)
    (worker / '.unio-worker').write_text('mockworker\n')

    # Initialized inner workspace: its own state, outer bytes untouched.
    inner_root = root / 'tmp scratch' / 'inner proj'
    inner_clone = inner_root / 'innerclone'
    (inner_clone / 'src').mkdir(parents=True)
    git('init', '-q', '-b', 'dev', cwd=inner_clone)
    (inner_clone / 'seed.txt').write_text('seed\n')
    git('add', 'seed.txt', cwd=inner_clone)
    git('commit', '-qm', 'seed', cwd=inner_clone)
    out = unio('init', 'innerworker', cwd=inner_clone)
    check('inner project initializes independently',
          out.returncode == 0 and (inner_root / 'wt' / 'innerworker' / '.unio-worker').is_file(), out)
    out = unio('mode', 'thorough', cwd=inner_clone / 'src')
    check('inner clone sets its own policy',
          out.returncode == 0
          and (inner_root / 'coord' / 'work-policy.json').is_file(), out)
    out = unio('mode', cwd=inner_clone / 'src')
    check('inner project reads its own mode',
          out.returncode == 0 and out.stdout.strip() == 'mode: thorough', out)
    out = unio('mode', cwd=clone / 'src')
    check('outer project still reads its own mode',
          out.returncode == 0 and out.stdout.strip() == 'mode: yolo', out)
    out = unio('stop', cwd=inner_clone)
    check('inner stop touches only the inner project',
          out.returncode == 0
          and (inner_root / 'coord' / 'STOP').is_file()
          and stop_file.read_bytes() == state[1], out)
    inner_unborn = inner_root / 'tmp scratch' / 'nested'
    inner_unborn.mkdir(parents=True)
    git('init', '-q', cwd=inner_unborn)
    out = unio('mode', 'balanced', cwd=inner_unborn)
    check('nested repo inside the inner project refuses against it',
          out.returncode != 0
          and 'refusing to act on the enclosing project' in out.stderr
          and str(inner_root) in out.stderr, out)

    check('outer policy, STOP and lock tree still frozen', snapshot() == state[:3])

    # Links under scratch would appear unrelated when walking logical PWD.
    # Spaces, apostrophes and shell syntax also exercise positional passing.
    # Successful setters refresh policy updated_at, so run after byte checks.
    for name, target in (('main', clone), ('worker', worker)):
        logical_link = scratch / (name + " alias ' $(literal)")
        logical_link.symlink_to(target)
        out = logical_unio('tier', 'high', cwd=logical_link / 'src')
        check('Bash logical cd through scratch %s symlink sets outer tier' % name,
              out.returncode == 0, out)
        out = unio('tier', cwd=clone)
        check('logical %s symlink targets outer tier and preserves STOP/locks' % name,
              out.returncode == 0 and out.stdout.strip() == 'tier: high'
              and snapshot()[1:] == state[1:3], out)

    check('no provider canary at the end', not canary.exists())

print('project-root: %d checks passed' % passed[0])
