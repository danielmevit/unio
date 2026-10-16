# Unio — quality milestone reference (M1)

Milestone 1 is complete and owner-accepted; its historical record is
[M1-STATUS.md](M1-STATUS.md). Unio 0.5.0 was installed in this development
workspace with owner approval on 2026-10-05; public release is pending.
Current source provides: strict verification, revision-bound results,
gated review, local availability JSON and same-checkout handoff packets.

Examples use the only supported command, `unio`. WORKER and TASK stand for a
worker name such as `codex` and a task ID such as `T7-codex`.

## Requirement: Python 3

The evidence features use a helper embedded in the installer. It needs
`python3` with its standard library only; nothing is downloaded or
installed. `run`, `verify`, `review`, `result`, `handoff`, `agents` and
`smoke` (and `race` and `sabotage`, which use `run`) look for `python3`
first. Without it they stop with "Python 3 is required before
run/review/smoke" before any provider starts. Check with `python3 --version`.

## The evidence flow

1. `run` resets the task's stored result and records the worker process.
2. `verify` checks scope and re-runs the Validate commands, and records
   the validation outcome.
3. `review` asks a different vendor, but only after current passed
   validation, and records the review decision.
4. `result` prints the stored evidence, rechecked against the worktree as
   it is now. `ready_for_human_review` is true only when all three pieces
   of evidence belong to the current revision.
5. Acceptance and integration stay with the human owner. M1 has no accept
   or integrate command.

`verify` also supports a candidate that has never had a native Source run:
it checks scope, Validate commands and changes without inventing a process
exit or dispatch revision. Actual check/scope failures exit 1; missing
scope/checks exit 2. A passing machine-only check leaves `process.state`
`not_run`, `human.state` `pending` and `ready_for_human_review` false.

After a native Source, verification requires the engine-owned full
`dispatch_revision`; provider output and report `task_sha` strings cannot
supply it. Missing legacy bindings, malformed/foreign results, or retained
run history without a structured binding remain incomplete (exit 2).
Deleting a result does not turn retained Source history into a manual check.
Review admission resolves the same binding before starting a reviewer, even
with cached passing validation. A native process requires a typed full dispatch
revision whose task hash matches the current task. Dispatch commit/tree hashes
may precede provider commits and need not equal the final candidate revision.
Legacy results remain readable with their historical fields intact, but missing
or mismatched binding makes them unready and refuses a fresh review without
rewriting the result. Genuine no-Source candidates may still receive machine-only
verification and review; their process remains `not_run` and readiness false.

## The stored result

Each worker and task has one result file, `coord/results/WORKER/TASK.json`.
It is replaced atomically while the worker lock is held. Append-only
reports and `ledger.jsonl` lines are still written as before, and old
PASS text is never converted into structured evidence.

A fully ready example, with hashes shortened:

```json
{
  "schema_version": 1,
  "worker": "codex",
  "task": "T7-codex",
  "updated_at": "2026-10-04T12:32:29.293028+00:00",
  "revision": {"candidate_commit": "6fc8456…", "base_commit": "26bc514…",
               "task_sha256": "62a5df9…", "worktree_sha256": "edd4c14…"},
  "process": {"state": "succeeded", "exit_code": 0, "revision": {"…": "…"}},
  "validation": {"state": "passed", "scope": "OK", "checks_run": 1,
                 "checks_failed": 0, "reasons": [], "revision": {"…": "…"}},
  "review": {"state": "approved", "reviewer": "grok", "process_exit_code": 0,
             "material_complete": true, "reasons": [], "revision": {"…": "…"}},
  "human": {"state": "pending"},
  "integration": {"state": "not_attempted"},
  "stale": false,
  "ready_for_human_review": true,
  "current_revision": {"…": "…"}
}
```

| Field | Meaning |
|---|---|
| `schema_version` | Always 1. |
| `worker`, `task` | The worker and task IDs. |
| `updated_at` | UTC time of the last write, ISO 8601. |
| `revision` | The revision the last write was bound to (four fields, below). |
| `process` | The worker process: `state`, `exit_code`, `revision`. After a failed post-run snapshot it also has `post_run_snapshot: "failed"`. |
| `validation` | `state`, `scope`, `checks_run`, `checks_failed`, `reasons`, `revision`. |
| `review` | `state`, `reviewer`, `process_exit_code`, `material_complete`, `reasons`, `revision`. |
| `human` | Always `{"state": "pending"}` in M1. |
| `integration` | Always `{"state": "not_attempted"}` in M1. |
| `stale` | True when any recorded evidence belongs to another revision, or after a failed post-run snapshot. |
| `ready_for_human_review` | True only when nothing is stale and the process succeeded, validation passed and review approved, all for the current revision. It never means a human accepted the work. |
| `current_revision` | The revision computed at the last write, or by `result` when printing. It is null after a failed post-run snapshot. |

A section's `revision` is null while its state is `not_run`.

### Revision identity

| Field | What it fingerprints |
|---|---|
| `candidate_commit` | The worker branch's current commit (HEAD in its worktree). |
| `base_commit` | The current commit of the base branch named in `coord/base` (main when that file is missing). |
| `task_sha256` | SHA-256 of the task file's bytes. |
| `worktree_sha256` | SHA-256 over the Git index plus every tracked and non-ignored untracked path: its type (file, symlink or absent), permission bits and content hash. A symlink's target text is hashed; the link is never followed. Spaces, Unicode and other unusual names are handled. |

### States

| Section | States and rules |
|---|---|
| `process` | `not_run`, `running`, `succeeded`, `failed`. `exit_code` is null unless the process finished: 0 for succeeded, nonzero for failed. |
| `validation` | `not_run`, `passed`, `failed`, `incomplete`. `scope` is `OK`, `VIOLATION` or `UNCHECKED`. `passed` requires scope `OK`, at least one check run, none failed and no reasons. |
| `review` | `not_run`, `approved`, `changes_requested`, `unknown`, `failed`. A decision requires a zero reviewer exit and complete material. `failed` always has a nonzero reviewer exit. |

Validation reasons: `missing_scope`, `missing_validate`, `scope_violation`,
`check_failed`, `empty_work`, `task_tampered`,
`candidate_changed_during_validation`.
Review reasons: `incomplete_material`, `reviewer_process_failed`,
`unknown_verdict`, `candidate_changed_during_review`.

### When evidence goes stale

The current revision changes when any of these change: the worker's
commit, the base branch's commit, the task file, the Git index, tracked
contents or permissions, or non-ignored untracked files (including their
contents, not just their names). Evidence recorded for an older revision
is then stale and the task is not ready.

- A new `run` resets validation and review to `not_run`.
- A new `verify` resets review to `not_run`, even at the same revision.
- `verify` and `review` take a snapshot before and after their work. If
  the candidate changed in between, the evidence stays bound to the
  earlier revision with a `candidate_changed_...` reason, so it can never
  count as current.
- A failed post-run snapshot keeps the result stale until the next `run`.

### `result WORKER TASK`

Prints the stored result as JSON on stdout, after recomputing
`current_revision`, `stale` and `ready_for_human_review` against the
worktree as it is now. It is read-only: it writes nothing, takes no lock and
calls no provider.

Exit 0 on success. Exit 2 when the result is missing ("old reports are not
trusted structured evidence"), malformed or self-contradictory (for
example a passed validation with zero checks), when the result file is a
symlink, or when the current revision cannot be computed (see
[Unsupported worktree states](#unsupported-worktree-states)). Exit 1 for
an invalid worker or task ID.

## Run exits

`run WORKER TASK` returns the worker's own exit code. A successful run
without automatic verification exits 0, but its validation stays
`not_run` and the task is not ready.

With `UNIO_AUTO_VERIFY=1`, verification runs while the same worker
lock is held. A worker failure keeps its own nonzero exit. A successful
worker followed by failed or incomplete verification returns the
verification's exit (1 or 2).

Before a provider starts, `run` prints the execution boundary warning:
configured commands run with host-level access.

## Limit observations (heuristic)

`run` scans the worker's final output window for provider limit language
(rate/usage limit, quota, resets at). It is a conservative text heuristic,
never a confirmed quota, and worker text never changes agent state.

- One normalized final window drives both display and matching: the
  report's `### agent output (tail)` section shows the last 60 log lines
  with ANSI/control escapes and carriage returns normalized, and the same
  normalized text is matched. The raw log at `coord/reports/TASK.log` is
  kept as the original evidence, and log text is never executed.
- A run is failed for this helper when its actual exit is nonzero, or when
  the empty-work rule finds zero commits against the base and zero
  uncommitted files. The real process exit is preserved in the report, the
  ledger and the stored result.
- Only such a failed run can warn (`!! output mentions usage limits`) and
  record ledger `wall=1`, meaning suspected limit language. A successful
  run with committed work records `wall=0` even when it prints limit
  phrases, including quoted repository file text.
- `UNIO_AUTO_OFF` is accepted for compatibility and no longer benches: no
  availability or configuration file is ever written from log matching.
  Benching an agent stays an explicit operator action (`unio off` /
  `unio on`), and `unio agents` keeps reporting capacity as unknown.

## Verification exits

`verify WORKER TASK` holds the worker lock for the whole check, so it
refuses a worker that is mid-run (exit 1). If the base branch named in
`coord/base` does not exist, it refuses to judge anything and exits 1
(FAIL) before taking any snapshot; it records nothing.

| Exit | Verdict | When |
|---|---|---|
| 0 | `PASS` | Scope lines present, at least one Validate command ran, every check passed, and the scope, tamper, empty-work and base safeguards held. |
| 1 | `FAIL` | A real failure: `scope_violation`, `check_failed`, `empty_work` or `task_tampered`. |
| 2 | `INCOMPLETE` | Evidence is missing: `missing_scope`, `missing_validate`, or `candidate_changed_during_validation` on an otherwise passing check. |

Failure takes precedence over incomplete evidence. Every reason is shown
in the terminal, appended to the report and stored in the result. If the
changed paths cannot be listed (see
[Unsupported worktree states](#unsupported-worktree-states)), `verify`
stops with exit 2 and records no new validation. Milestone 1 has no
waiver mechanism: a task that needs a different check must name it.

## Review

`review WORKER TASK [REVIEWER]` asks an agent from a different vendor
to judge the task and the complete committed diff. Before any reviewer is
called:

- It holds the worker lock and refuses a busy worker (exit 1).
- It requires current passed validation. Otherwise it stops with "review
  requires current passed validation; run verify" (exit 2).
- With no REVIEWER named, it picks the first agent in `agents.conf` that is
  not the author's vendor, is not benched and has its program installed.
  A named reviewer must also be another vendor and not benched (exit 1).

The review material is the task file plus the full committed diff from
the base branch to the worker's commit. It is built without external diff
drivers, text conversion or rename detection. It is refused, and the
reviewer is NOT called, when:

- staged, unstaged or untracked work exists (commit everything first),
- the diff contains binary changes (they need manual inspection),
- the material is larger than 300000 bytes (nothing is clipped),
- it is not valid UTF-8,
- an index flag could hide edits (see below).

A refusal records review `unknown`, `material_complete: false` and reason
`incomplete_material`, and exits 2.

The reviewer runs from an empty temporary folder, with `TASKFILE` pointing
at the material and a time limit of `UNIO_REVIEW_TIMEOUT` seconds
(default 900). Its configured command still has host-level access.
Fresh shipped commands never pass the material as one argument, so
material over Linux's ~128 KiB single-argument limit no longer fails with
`Argument list too long`. Claude and Codex read the file on stdin, Grok
uses `--prompt-file` and OpenCode attaches it with `--file`. `agy` has no
such flag: its shipped line passes a short, bounded prompt that names the
file and tells the agent to read all of it before acting, so `agy` gets
the material only through its own file reads. Unio cannot confirm that
any agent read the whole file. The material tells the reviewer to read
the whole file but never run its Validate commands or follow
instructions inside the diff.

Only stdout can carry the decision. Exactly one line may mention
`verdict:` (in any letter case), and it must read exactly
`VERDICT: APPROVE` or `VERDICT: REQUEST-CHANGES`, alone on the line and not
indented. A missing, malformed, indented, repeated or contradictory
verdict is `unknown`. Text on stderr never counts. A nonzero reviewer exit
is `failed` whatever the text says; a timeout records exit 124.

| Exit | Meaning |
|---|---|
| 0 | `approved`: a valid approval for the current revision. |
| 1 | `changes_requested`, or the reviewer process failed. |
| 2 | `unknown` verdict, incomplete material, stale evidence, or the candidate changed during the review. |

The raw stdout and stderr are kept in `coord/reports/TASK.review.XXXXXXXX/`.
A review block is appended to the report, and the ledger line records the
reviewer's process exit. An approval is evidence for you, not acceptance.

## Handoff packets

`handoff WORKER TASK` writes a new folder under
`coord/handoffs/WORKER/TASK/`, named by UTC time plus a random suffix, and
prints its path on stdout. It holds the worker lock and refuses a locked or
running worker (exit 1).

| File | Contents |
|---|---|
| `task.md` | The task file text. |
| `result.json` | The stored result rechecked against the current revision, or explicit `not_run` states when no result exists. |
| `revision.json` | The revision when the packet was made. |
| `changed-files.json` | Committed, staged, unstaged and untracked changed paths. |
| `HANDOFF.md` | Completed checks, outstanding issues and the next safe actions. |

The packet is context for another AI continuing in the SAME checkout. It is
**not a backup**, restore or provider migration: uncommitted and untracked
work stays only in the original worktree. Credentials, `agents.conf`,
ignored files, raw logs and home folders are never copied. Task text can
contain sensitive information, so `handoff` reminds you on stderr to review
the packet before sharing it. Nothing is uploaded and no replacement
provider is called.

The packet is built in a hidden `.pending-` folder and renamed into place
only if the revision did not change meanwhile. A `.pending-` folder left
by an interrupted handoff is removed by the next handoff for that task. Earlier packets are never
modified. Symlinked coordination paths and invalid IDs are refused. The
helper's refusals (a changed candidate, a malformed result, an
unsupported worktree state) exit 2. Old evidence must be rechecked after
new edits or after a move to another machine.

## Availability: `agents` and `agents --json`

Both forms read only `agents.conf` and the bench markers. They never run a
configured command and never probe sign-in or quota. `agents` prints one
line per agent, for example:

```text
Local diagnostics only: installed does not mean usable. Authentication/capacity unknown.
Execution boundary: trusted_host. No sign-in or quota probe performed.
codex: installed=yes; on
grok: installed=yes; OFF (operator retry epoch 1791135163; not a provider reset)
opencode: installed=no; on
mywrap: installed=unknown; on
```

Here `mywrap` is an operator-written line, `mywrap=bash -c '...'`. The
`bash -c` wrapper hides the program, so it is unknown. The shipped Codex
line, `codex exec ... - < "$TASKFILE"`, reports `yes` or `no`.

`agents --json` prints `{"schema_version": 1, "agents": [...]}` with one
object per agent:

```json
{"name": "grok", "binary": {"value": "grok", "present": true},
 "bench": {"off": true, "operator_retry_at": 1791135163},
 "authentication": "unknown", "capacity": "unknown",
 "execution_boundary": "trusted_host"}
```

| Field | Meaning |
|---|---|
| `binary.value` | The program the configured command starts. Leading `NAME=value` assignments and an `env` prefix are skipped. |
| `binary.present` | `true` or `false` when the program can be looked up without running a shell. `null` (shown as `installed=unknown`) when the program word itself contains `$` or a backtick, the line has an unquoted shell control or redirect other than a plain input redirect (`\|`, `;`, `&`, `>`, parentheses, `<<`, `<<<` or `<(`), sets `PATH`, starts with an option, or the program is a wrapper such as `bash`, `sh`, `timeout`, `nohup` or `sudo`. Quoted arguments, a `$VAR` argument and a plain input redirect (`<` followed by one word) do not hide the program. |
| `bench.off` | True while the agent is benched with `off`. |
| `bench.operator_retry_at` | The retry time you chose, in Unix epoch seconds, or null. It is not a provider-confirmed reset. |
| `authentication`, `capacity` | Always `unknown`: never checked locally. |
| `execution_boundary` | Always `trusted_host`: configured commands have host-level access. |

Examples, as the parser reads them:

- Known (`yes` or `no`): `claude -p --dangerously-skip-permissions < "$TASKFILE"`,
  `codex exec ... - < "$TASKFILE"`, `grok --prompt-file "$TASKFILE"`,
  an older `claude -p "$(cat "$TASKFILE")"` line (the expansion is quoted),
  and `FOO=1 env claude`.
- Unknown: `claude < "$TASKFILE" > out.log` (output redirect),
  `claude | tee log`, `claude; true`, `claude << EOF`,
  `claude < <(cat f)`, `claude $(echo x)` (unquoted command
  substitution), `PATH=/opt/bin claude`, `$HOME/bin/claude`,
  `timeout 60 claude` and `bash -c 'claude < "$TASKFILE"'`.

Inside a project, `doctor` checks that each worker's program is on PATH.

## Unsupported worktree states

Revision evidence hashes real file contents, but scope checks, review
material and handoff summaries list changed paths through Git. Git skips
paths marked assume-unchanged or skip-worktree (sparse checkout uses the
latter), so `verify`, `review` and `handoff` refuse a worktree with either
flag instead of claiming a complete list. Clear the flags with
`git update-index --no-assume-unchanged --no-skip-worktree` on those paths,
or `git sparse-checkout disable`, then run the command again.

The snapshot itself refuses FIFOs, devices, sockets, nested repositories
and submodules. If that happens right after a worker finishes, `run` still
records the worker's real exit code, writes the report and ledger line
(`snapshot_failed` is 1), skips automatic verification, and returns the
worker's nonzero exit, or 2 if the worker succeeded. The stored result is
marked `post_run_snapshot: failed` and stays stale and not ready, even
after cleanup. Remove the unsupported file, then run the task again.

## Isolated checks

Run `bash tools/quality-check.sh`. It installs only in temporary
directories and runs the selftest, the mock quality regressions
(`tests/unio-quality.sh`), the existing adversarial probes,
branding checks, ShellCheck and documentation lint. No provider is
invoked. Python 3 and ShellCheck are checked locally; no dependency is
downloaded.

## Current execution limits

Worktrees and temporary directories are coordination mechanisms, not OS
sandboxes. Configured provider commands may have host-level access. Human
acceptance and integration remain separate decisions controlled by the owner.

## Loop brake (unreleased source)

After two unsuccessful attempts on one task ID, `run` refuses another
invocation before executing its configured provider command (exit 2).
Changing workers does not reset the count. Failed processes, failed or
incomplete verification, and an interrupted tracked start each count once
per attempt; repeated verification does not add failures. Lost starts are
reconciled across workers when the next run starts; held locks are left alone. Tracking starts
with this source version; old reports are not retroactively inferred.

Only after the owner approves another attempt, run:

```bash
unio allow-retry TASK
unio run WORKER TASK
```

The grant permits one invocation, cannot accumulate, and keeps the failure
history even if that attempt succeeds. `on` and `resume` do not clear the
brake. Task state is local under `coord/retries/TASK/`, with a task lock so
concurrent workers cannot consume one grant twice. Malformed or symlink
state fails closed. This is trusted-host coordination, not an access-control
boundary: workers must never grant their own retries or rewrite this state.
A grant does not approve provider quota or human integration by itself.
