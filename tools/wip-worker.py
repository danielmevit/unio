# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Bounded WIP extension embedded in the native safe-save namespace.

No provider calls. Observations, ownership, private IO and index parsing use
v19 primitives. Mutating Git deliberately retains normal configured hooks.
"""


def wip_setting(root, action='status'):
    path = under(root, 'coord', 'wip.json')
    # Validate the parent even when the setting is absent.
    fd = open_dir(under(root, 'coord'))
    try:
        st = os.fstat(fd)
        if st.st_uid != os.getuid() or st.st_mode & 0o022:
            raise Refuse('io_error', 'unsafe coord directory')
    finally:
        os.close(fd)
    if action in ('on', 'off'):
        if os.path.lexists(path):
            wip_setting(root)
        atomic_private(path, canon({'schema_version': 1, 'enabled': action == 'on'}))
    try:
        st, raw = read_path(path, 4096)
    except FileNotFoundError:
        return False
    if st.st_uid != os.getuid() or st.st_nlink != 1 or st.st_mode & 0o077:
        raise Refuse('io_error', 'wip.json must be private and owned')
    doc = strict_json(raw, 4096, 'WIP setting')
    if (not isinstance(doc, dict) or set(doc) != {'schema_version', 'enabled'}
            or type(doc['schema_version']) is not int or doc['schema_version'] != 1
            or type(doc['enabled']) is not bool):
        raise Refuse('incomplete', 'malformed WIP setting; repair coord/wip.json explicitly')
    return doc['enabled']


def wip_store(root):
    path = under(root, 'coord', 'reports', '.wip')
    private_dir(path, True)
    return path


def wip_paths(obs):
    return sorted(p for p in set(obs['files']) | set(obs['head_map'])
                  if p not in obs['files'] or p not in obs['head_map']
                  or git_oid(obs['repo']['fmt'], obs['files'][p][1]) != obs['head_map'][p][1]
                  or ('100755' if int(obs['files'][p][0], 8) & 0o111 else '100644') != obs['head_map'][p][0])


def wip_clean_index(obs):
    if parse_index(obs['index_raw'], obs['repo']['fmt']) != obs['head_map']:
        raise Refuse('incomplete', 'staged/partial index unsupported; leave index intact and commit manually')


def wip_scope(raw, paths):
    lines = raw.decode('utf-8').splitlines()
    if lines.count('## Allowed scope') != 1:
        raise Refuse('incomplete', 'WIP needs one explicit Allowed scope section')
    scope = []
    for line in lines[lines.index('## Allowed scope') + 1:]:
        if line.startswith('#'):
            break
        if line.startswith('- '):
            p = line[2:].strip()
            # Conservative v1: exact relative files and trailing-slash trees.
            check_path(p.rstrip('/'))
            if any(c in p for c in '*?[]'):
                raise Refuse('incomplete', 'WIP v1 scope supports literal paths/directories only')
            scope.append(p)
    if not scope or len(scope) > 128:
        raise Refuse('incomplete', 'missing or excessive WIP scope')
    for p in paths:
        check_secret(p, 'WIP scope')
        if re.search(r'(^|/)(\.npmrc|\.pypirc|\.netrc|\.git-credentials|\.ssh|\.aws|credentials|secrets?|tokens?)(/|\.|$)|\.(key|keystore|jks)$', p, re.I):
            raise Refuse('secret_name', 'secret-looking WIP path: ' + p)
        if not any(p == s or s.endswith('/') and p.startswith(s) for s in scope):
            raise Refuse('incomplete', 'out-of-scope edit: ' + p)


def wip_prepare(root, worker, task):
    run_id = inherited_run(root, worker, task)
    doc = dict(worker=worker, task=task, run_id=run_id, started_at=stamp(), ready=False)
    try:
        doc['enabled'] = wip_setting(root)
        if doc['enabled']:
            budget = Budget(30)
            obs, raw = capture(root, worker, task, budget)
            wip_clean_index(obs)
            if wip_paths(obs):
                raise Refuse('incomplete', 'initial worktree must be clean; existing user edits are never auto-staged')
            wip_scope(raw, [])
            again, _ = capture(root, worker, task, budget)
            if not same(obs, again) or obs['index_raw'] != again['index_raw']:
                raise Refuse('unstable', 'initial bytes changed')
            doc.update(ready=True, task_sha256=sha(raw), head=obs['git']['head_commit'])
    except (Refuse, OSError, ValueError) as e:
        doc['reason'] = str(e)
    write_private(under(wip_store(root), run_id + '.start.json'), canon(doc))


def wip_git(wt, budget, index, *args, codes=(0,)):
    # Safe-save read flags disable hooks; remove only that flag for mutation.
    opts = [v for i in range(0, len(GIT_OPTS), 2)
            if GIT_OPTS[i + 1] != 'core.hooksPath=/dev/null' for v in GIT_OPTS[i:i + 2]]
    return run(['git', '-C', wt] + opts + list(args), budget, env=git_env(index), codes=codes, what='WIP Git')


def wip_finish(root, worker, task, original_exit):
    run_id = inherited_run(root, worker, task)
    doc = dict(schema_version=1, worker=worker, task=task, run_id=run_id,
               original_exit=int(original_exit), observed_at=stamp(), outcome='refused',
               revision=None, paths=[], accepted=False)
    # An interrupted attempt is never replayed, even if its final receipt is absent.
    write_private(under(wip_store(root), run_id + '.claim.json'),
                  canon(dict(worker=worker, task=task, run_id=run_id, original_exit=int(original_exit), started_at=stamp())))
    commit_started = False
    try:
        enabled = wip_setting(root)
        if not enabled or int(original_exit) == 0:
            doc.update(outcome='skipped', reason='default/off' if not enabled else 'Source exited successfully')
        else:
            record = load_owner(owner_path(root, task, worker))
            if (not record or record['worker'] != worker or record['task'] != task
                    or record['shell_pid'] != os.getppid() or not parent_matches(record)
                    or record['provider_pid'] is None or session_members(record)[0] != 'clear'):
                raise Refuse('unknown', 'exact owned provider quiescence is unproved')
            doc['owner'] = record
            start = strict_json(read_path(under(wip_store(root), run_id + '.start.json'), MIB)[1], MIB, 'WIP start')
            if (start.get('run_id') != run_id or start.get('worker') != worker or start.get('task') != task
                    or start.get('ready') is not True):
                raise Refuse('incomplete', 'initial safety checks did not pass: ' + str(start.get('reason', 'not enabled at start')))
            budget = Budget(30)
            obs, raw = capture(root, worker, task, budget)
            if sha(raw) != start['task_sha256']:
                raise Refuse('unstable', 'task instructions changed')
            wip_clean_index(obs)
            paths = wip_paths(obs)
            wip_scope(raw, paths)
            for p in paths:
                if p in obs['files']:
                    body = obs['files'][p][1]
                    if b'\0' in body:
                        raise Refuse('unsupported_type', 'WIP v1 supports UTF-8 text only: ' + p)
                    body.decode('utf-8')
            again, _ = capture(root, worker, task, budget)
            if not same(obs, again) or obs['index_raw'] != again['index_raw']:
                raise Refuse('unstable', 'changing bytes; retry manually after writers stop')
            if not paths:
                doc.update(outcome='skipped', reason='no uncommitted changes')
            else:
                wt, gd = obs['repo']['wt'], obs['repo']['gitdir']
                with tempfile.TemporaryDirectory(prefix='unio-wip-', dir=gd) as scratch:
                    index = os.path.join(scratch, 'index')
                    write_private(index, obs['index_raw'])
                    wip_git(wt, budget, index, '--literal-pathspecs', 'add', '--', *paths)
                    staged = parse_index(read_path(index, MAX_OBSERVED)[1], obs['repo']['fmt'])
                    expected = dict(obs['head_map'])
                    for p in paths:
                        if p not in obs['files']:
                            expected.pop(p, None)
                        else:
                            mode, body = obs['files'][p]
                            expected[p] = ('100755' if int(mode, 8) & 0o111 else '100644', git_oid(obs['repo']['fmt'], body))
                    if staged != expected:
                        raise Refuse('unstable', 'staged bytes differ from checked files')
                    again, _ = capture(root, worker, task, budget)
                    if not same(obs, again) or obs['index_raw'] != again['index_raw'] or session_members(record)[0] != 'clear':
                        raise Refuse('unstable', 'state changed before commit')
                    doc['paths'] = paths
                    # One normal commit, with configured hooks. No retry.
                    commit_started = True
                    rc, out = wip_git(wt, budget, index, 'commit', '-m', 'WIP: %s (Source exit %s; unaccepted)' % (task, original_exit), codes=(0, 1))
                    head = git_out(wt, budget, 'rev-parse', 'HEAD').decode().strip()
                    if rc:
                        if head != obs['git']['head_commit'] or read_path(os.path.join(gd, 'index'), MAX_OBSERVED)[1] != obs['index_raw']:
                            raise Refuse('unknown', 'commit failed and original HEAD/index restoration cannot be proven')
                        commit_started = False
                        raise Refuse('incomplete', 'Git commit/hook failed; edits and original index retained; commit manually')
                    doc['revision'] = head
                    if (git_out(wt, budget, 'rev-parse', 'HEAD^').decode().strip() != obs['git']['head_commit']
                            or tree_paths(wt, budget, head, True) != expected
                            or read_path(os.path.join(gd, 'index'), MAX_OBSERVED)[1] != obs['index_raw']):
                        raise Refuse('unknown', 'hook/concurrent state changed; inspect HEAD and index manually')
                    post, _ = capture(root, worker, task, budget)
                    if post['files'] != obs['files']:
                        raise Refuse('unknown', 'bytes changed during hooks/commit; inspect saved state and HEAD manually')
                    install_index(gd, read_path(index, MAX_OBSERVED)[1], obs['index_raw'])
                    doc.update(outcome='created', reason='scoped unaccepted WIP; original Source failure persists')
    except (Refuse, OSError, ValueError, KeyError, TypeError) as e:
        doc.update(outcome='unknown' if commit_started or isinstance(e, Refuse) and e.code == 'unknown' else 'refused', reason=str(e))
    atomic_private(under(wip_store(root), run_id + '.json'), canon(doc))
    print('WIP %s: %s%s; receipt: coord/reports/.wip/%s.json; saves: unio save inspect --worker %s; handoff: coord/reports/%s.md' %
          (doc['outcome'], (doc.get('revision') + ' — ') if doc.get('revision') else '', doc['reason'], run_id, worker, task))


def wip_main(root, args):
    if len(args) != 1 or args[0] not in ('on', 'off', 'status'):
        raise Refuse('incomplete', 'usage: unio wip on|off|status')
    enabled = wip_setting(root, args[0])
    print('WIP %s (project opt-in; failed Source remains failed/unaccepted; UTF-8 text, clean initial state, literal task scope)' % ('on' if enabled else 'off'))
