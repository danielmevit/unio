# Unio — keep one project in one folder

Owner rule, recorded 2026-10-04. This is a standing instruction for future
Unio work, not merely a suggestion for this session.

## One enclosing workspace

All project-owned source, working copies, tasks, reports, checkpoints,
design references, generated deliverables and scratch belong INSIDE one
`unio` workspace (or legacy `frugal-flock` folder). Do not create associated sibling folders or leave
important work in shared temporary directories. Ask before using a different
storage layout. Do not move unrelated projects into this workspace.

The current local workspace is `D:\Vibe Coding\_vm\unio` on Windows,
or `/mnt/d/Vibe Coding/_vm/unio` in WSL. See the completed
[relocation record](WORKSPACE-RENAME.md); historical evidence retains its old paths.

```text
unio/
  repo/          Main Git checkout: stable source, documentation and prompt
  wt/codex-lead/ Private lead checkpoints and handoff
  wt/.../        Other registered worktrees; keep inactive histories intact
  coord/         Task orders, reports, locks and coordination history
  artifacts/     Private project-specific references and obsolete prototypes
  tmp/           Disposable project-local test/install directories
```

`wt` is short for Git worktrees: separate working copies sharing one Git
history. They are not separate products, and not security sandboxes. The
runner expects `repo`, `wt` and `coord` under the same workspace; keeping
that convention avoids an application-code change.

`repo/` is the Git repository root, not the whole workspace. Files under
`coord/`, `artifacts/`, and `tmp/` are LOCAL and are not automatically pushed
to GitHub. Do not publish raw logs, credentials, private task text or browser
profiles merely to make a backup. Local checkpoints are not off-device
backups; use an owner-approved backup destination when requested.

## Agent log: read first, write last

Owner rule, recorded 2026-10-04. It applies to every AI agent, of any vendor
or model, lead or worker. The live log is `coord/AGENT-LOG.md` in the
enclosing workspace. It is local, shared by every worktree, and not pushed.

- Before starting, read its newest entries. The newest work may be on
  another agent's branch and worktree. Read that branch first, build on
  it, and never redo, reset or overwrite it.
- Say what you are about to do, then manage the work yourself in small,
  tested checkpoints.
- After every checkpoint, and before stopping or hitting a usage limit,
  add an entry at the top of the log: local date and time with UTC offset,
  agent and exact model, worktree, branch and SHA, what changed, the tests
  actually run with results, state, and the one next task. Also update
  [continue-with-ai-prompt.md](continue-with-ai-prompt.md) on your branch, and keep provider guidance current.
- Never edit or delete older entries. Without the local workspace (a fresh
  clone), the continuation prompt and M1 status carry the same facts.

## Tools and credentials are different

Installed CLIs, native authentication stores and shared tool-managed caches
may remain in their standard system locations. Do not copy secrets into
this project or rewrite global settings for a folder reorganization.
Use the project-local `tmp/` for scratch files and, where supported,
`TMPDIR` when running disposable checks. Do not repurpose HOME or CODEX_HOME.

## Git and handoffs

- Work on the branch matching the actual worker: Codex uses `agent/codex`
  in `wt/codex`, not a leftover provider's name.
- Preserve existing changes, commits, worktrees and append-only reports.
  Moving a workspace never authorizes deleting another worker's history.
- Repair and verify linked-worktree references after relocation. Do not
  move worktrees during an active run or start overlapping writers.
- Follow the main/worker role cards; the owner retains integration and
  release authority. A fast-forwarded worker is not an integration into main.
- Make small single-issue checkpoints. Update
  [continue-with-ai-prompt.md](continue-with-ai-prompt.md) after each with
  the exact branch/SHA, actual tests, blockers, active workers and next task.
- Historical reports may contain old paths/names. Keep history truthful;
  update current instructions and explicitly identify the replacement path.

On another machine, choose its own enclosing `unio` or `frugal-flock` folder and keep
the same relationships. Do not hard-code this computer's drive into runtime
code. Read this rule before creating files or additional workspaces.

Before assigning any provider, read [docs/PROVIDER-CAPACITY.md](../PROVIDER-CAPACITY.md)
and the newest log entries. Existing owner authorization for available AI
work on Unio and milestones persists; do not request it again for routine
assignments. Preserve invocation budgets, no-retry rules and review evidence.

## Lead continuity

Answer status or explanation questions briefly, then continue authorized work
in the same turn. A question does not pause the task. Follow the canonical
[lead continuity rule](LEAD-ROUTING.md#answer-questions-and-continue-authorized-work);
preserve work and active-job receipts before any unavoidable stop.
