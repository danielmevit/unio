# Unio Protocol — system specification for AI agents

<!--
Unio — Copyright (C) 2026 Daniel Mitev
Original project: https://github.com/danielmevit/unio
-->

Audience: AI agents (lead or worker) operating inside a Unio project.
Status: normative. If your role card (MASTER.md / WORKER.md) conflicts with
this document, the role card wins. The human owner (Daniel) outranks both.

## 1. SYSTEM

Unio coordinates one interactive LEAD session and N headless WORKER
runs from different AI CLIs (claude, codex, agy/antigravity, grok,
opencode) on one shared git repository. Isolation is per-worker git
worktrees. Coordination is plain files. Integration is human-gated merges.
Execution boundary: `trusted_host`. Configured agent commands run with the
owner's host access; worktrees and temporary directories are coordination
mechanisms, not OS sandboxes.

Roles:
- OWNER (human): approves plans, reads diffs, merges to base, releases.
  Sole merge authority. Sole release authority.
- LEAD (interactive session in `repo/`): plans, freezes contracts, writes
  task files, dispatches workers, verifies results, recommends merges.
  Never implements feature code. Never merges.
- WORKER (headless run in `wt/<name>/`): executes exactly one task file,
  commits in its own worktree, reports. No memory between runs.

## 2. FILESYSTEM CONTRACT

Layout relative to project root:

| Path | Content | Write access |
|---|---|---|
| `repo/` | The repository, checked out on the base branch | OWNER, LEAD (docs/contracts only) |
| `repo/changelog.d/<ID>.md` | Changelog fragment per task; rolled into CHANGELOG.md at release | the task's WORKER |
| `wt/<worker>/` | Worktree on branch `agent/<worker>` | that WORKER only |
| `coord/base` | Base branch name (single word, normally `dev`) | OWNER |
| `coord/docs/` | Operating playbooks + this protocol | OWNER |
| `coord/board.md` | Task board, one row per task | LEAD only |
| `coord/tasks/<ID>-<worker>.md` | Task files (work orders) | LEAD only |
| `coord/reports/<task>.md` | Append-only run history per task | Unio tooling |
| `coord/reports/<task>.log` | Latest run's full output (overwritten) | Unio tooling |
| `coord/reports/ledger.jsonl` | Append-only machine ledger: one JSON object per event | Unio tooling |
| `coord/reports/<task>.review.*/` | Raw reviewer stdout and stderr, one folder per review | Unio tooling |
| `coord/results/<w>/<task>.json` | Structured result (schema 1), replaced atomically under the worker lock | Unio tooling |
| `coord/handoffs/<w>/<task>/` | One new context packet per `handoff`; earlier packets are kept | Unio tooling |
| `coord/blockers.md` | Blocker notes | anyone, APPEND only |
| `coord/STOP` | If present: all new runs refused | OWNER |

Transient control files (tooling-owned, never edit): `coord/.locks/<w>.lock`
(one run per worker) and `coord/reports/<task>.pid` (background run's
process id, removed on exit).

Data-source rule: historical analysis MUST read `reports/*.md` (append-only,
all runs) or `ledger.jsonl` (append-only, machine-readable). `*.log` holds
only the latest run and MUST NOT be used as history.

Timing rule: `duration_s` is measured on a monotonic clock and therefore
excludes time the machine spent asleep; `wall_s` is the wall-clock elapsed
time and `suspended` is 1 when the two diverge by more than a minute. A
suspended run's elapsed time is meaningless — `unio score` excludes it
from averages, and any other analysis MUST do the same.

Enforcement at init: `unio init` refuses to scaffold while likely
secret files are tracked (override: UNIO_ALLOW_SECRETS=1), and
installs git hooks: a worker worktree can commit only on its own
`agent/<w>` branch and can never push, and every merge into the base
branch is recorded as a ledger `merge` event (post-merge hook).

## 3. DATA FORMATS

Report run-block (appended to `coord/reports/<task>.md` per run):

```text
## run <ISO8601 timestamp> — worker=<worker> agent=<agent> exit=<int> duration=<int>s task_sha=<sha256>
[!! post-run snapshot failed — exit=<int> recorded; structured result unbound and not ready]
### git status (branch, staged/unstaged)
<porcelain v1 output>
### committed diffstat vs <base>
<diffstat or "(none)">
### verdict
commits=<n> files=<n> insertions=<n> deletions=<n> uncommitted=<n>
[!! empty-diff warning when exit=0 with no changes]
### agent output (tail)
~~~
<last 60 log lines, ANSI/control escapes and carriage returns normalized>
~~~
```

The `agent output (tail)` window is the final 60 log lines with ANSI/control
escapes and carriage returns normalized; the raw `*.log` file keeps the
original evidence, and normalization never executes log text.

Verify block (appended by `unio verify`):
`### verify <ts> — worker=<w> scope=<OK|VIOLATION|UNCHECKED>
validate=<passed>/<run> empty=<0|1> verdict=<PASS|FAIL|INCOMPLETE>` plus
out-of-scope paths, individual reasons, and per-command results. PASS exits
0 only with scope and at least one passing Validate command, with existing
safeguards satisfied. Missing scope/checks exits 2 (INCOMPLETE); actual
failures take precedence and exit nonzero, normally 1. No waiver is provided.
Index entries flagged assume-unchanged or skip-worktree make verify exit 2
before any verdict, because Git diff/status would omit their edits.

Ledger events (`coord/reports/ledger.jsonl`, one JSON object per line):

```text
{"event":"run_start","ts":…,"task":…,"worker":…,"agent":…}
{"event":"run","ts":…,"task":…,"worker":…,"agent":…,"exit":n,"duration_s":n,
 "wall_s":n,"suspended":0|1,"snapshot_failed":0|1,
 "commits":n,"files":n,"insertions":n,"deletions":n,"uncommitted":n,"wall":0|1}
{"event":"verify","ts":…,"task":…,"worker":…,"scope":"OK|VIOLATION|UNCHECKED",
 "validate_run":n,"validate_failed":n,"commits":n,"empty":0|1,"verdict":…}
{"event":"review","ts":…,"task":…,"worker":…,"reviewer":…,"exit":n,"decision":…}
{"event":"race","ts":…,"task":…,"workers":"w1 w2 …"}
{"event":"merge","ts":…,"worker":…,"subject":"<merge commit subject>"}
```

Structured result (`coord/results/<w>/<task>.json`, Python 3 stdlib helper):

```text
schema_version 1, worker, task, updated_at, current_revision
revision    candidate_commit, base_commit, task_sha256, worktree_sha256
            (index + tracked + nonignored untracked contents, not just names)
process     state not_run|running|succeeded|failed, exit_code, revision
            [post_run_snapshot: "failed" — always stale, never ready]
validation  state not_run|passed|failed|incomplete, scope, checks_run,
            checks_failed, reasons, revision
review      state not_run|approved|changes_requested|unknown|failed,
            reviewer, process_exit_code, material_complete, reasons, revision
human       {"state": "pending"}        integration {"state": "not_attempted"}
stale, ready_for_human_review
```

Every section records the revision it was produced at. A new run resets
validation and review; a new verify resets review. `stale` is true when any
evidence revision differs from the current one (commit, base, task file,
index, tracked or nonignored untracked content). `ready_for_human_review`
needs a succeeded process, passed validation and approved review, all at the
current revision and not stale. It is never human acceptance or permission
to integrate. `unio result` prints this JSON only, recomputed against
the current worktree; a missing or malformed file fails closed (exit 2), and
old report text is never backfilled as structured evidence.

Loop brake: after two failed attempts on a task ID, `run` refuses before
calling a provider (exit 2), shared across workers. Nonzero exits, failed or
incomplete verification and interrupted tracked starts count once per
attempt. Repeated verification does not add failures. Only the owner may
use `unio allow-retry TASK` to grant one invocation; grants do not
accumulate or erase failures. State is local in `coord/retries/TASK/`,
locked across workers; malformed or symlink state fails closed. Tracking
starts with this source version, without inferring historical outcomes.
Workers must not grant themselves retries. This is trusted-host coordination,
not an access-control boundary or provider-quota approval.

Review gate: `unio review` needs current passed validation. Its
material is the task file plus the full committed diff against base. It is
refused (exit 2, review recorded `unknown`, `material_complete` false) for
staged, unstaged or untracked work, binary changes, non-UTF-8 data, more than
300000 bytes, or flagged index entries; nothing is ever clipped. The
reviewer's stdout must hold exactly one standalone `VERDICT: APPROVE` or
`VERDICT: REQUEST-CHANGES` line; stderr never counts. Exits: 0 approved;
1 changes requested or reviewer process failure (timeout is 124); 2 unknown
verdict, incomplete material, stale evidence, or a candidate that changed
during the review.

Handoff packet: `coord/handoffs/<w>/<task>/<timestamp>-<id>/` holds
`task.md`, `result.json`, `revision.json`, `changed-files.json` and
`HANDOFF.md`, published by an atomic rename. It is refused while the worker
lock is held, and is not published if the candidate changes meanwhile. It is
context for the same checkout, NOT a backup, restore or provider migration:
uncommitted and untracked contents stay in the source worktree. Credentials,
agents.conf, ignored files and raw logs are never copied; task text may be
sensitive, so review a packet before sharing it.

Activity monitor: `unio watch [--once] [--json] [--interval seconds]`
observes local results, worker locks, retry-brake state, STOP, agent diagnostics
and up to 20 recent ledger events. It calls no provider, rewrites no evidence,
and reads no raw logs or task contents. JSON snapshots emit initially and
on changes. Decisions are recorded, not current readiness; use result to
recheck. Running evidence with a free worker lock has completion_unknown,
keeping its native state/null exit. A free lock does not rule out detached
processes. Capacity/auth stay unknown; wall signals are runner log patterns,
and operator retry times are not provider resets. See docs/WATCH-USAGE.md.

Availability (`unio agents --json`, local only, never executes a
configured command or probes sign-in or quota):

```text
{"schema_version":1,"agents":[{"name":…,"binary":{"value":…,
 "present":true|false|null},"bench":{"off":…,"operator_retry_at":…},
 "authentication":"unknown","capacity":"unknown",
 "execution_boundary":"trusted_host"}]}
```

Task file schema (LEAD writes; template at `coord/tasks/TEMPLATE.md`):
sections `Goal` (one testable outcome), `Context` (self-contained — the
worker has zero prior memory), `Allowed scope` (exhaustive; every
`- path` line is a machine-enforced pattern — globs allowed, trailing `/`
means the subtree, `changelog.d/` is implicitly allowed), `Constraints`,
`Validate` (every `$ command` line is machine-run by verify and must exit
0), `Done means` (observable + committed + changelog fragment where the
repo keeps a changelog), `Report` (required final sections: SUMMARY /
FILES CHANGED / TESTS RUN + RESULTS / ASSUMPTIONS / RISKS / NEEDS-REVIEW).

Board row schema: `| ID | worker | state | branch | scope | done-when |`
with state ∈ {todo, doing, blocked, review, done}.

Worker→agent resolution: agent id = worker name up to first `-`
(worker `codex-2` → agent `codex`).

## 4. THE `unio` COMMANDS (local shell tool)

To be explicit: these are subcommands of the local `unio` shell
script. No AI-provider API is involved anywhere in this system — every
agent is an official CLI running under its own subscription LOGIN
(cached on the machine), never an API key.

```text
unio init [w1 w2 ...]     scaffold worktrees + coord (idempotent);
                               secrets preflight; guard hooks
unio agents [--json]      list agents: binary present, on/off state;
                               --json = schema 1, local only (see §3)
unio smoke                one tiny live call per agent from a neutral
                               dir (still trusted_host); OK / WARN (reply
                               lacks "ok") / FAIL
unio selftest             full-loop rehearsal in a sandbox repo with
                               mock agents; zero quota; nonzero on failure
unio run [-b] <w> <task>  execute coord/tasks/<task>.md as worker <w>
                               in wt/<w>; -b = background; per-worker lock;
                               writes report+log+ledger+structured result;
                               a failed worker's own exit code wins
unio tail [task] [-f]     print log tail (default 40 lines; -f to follow)
unio kill <task>          terminate a background run (whole session,
                               including the agent under `timeout`)
unio report <task> [n]    print the last n (default 60) lines of a
                               task's append-only report
unio version              installed tool version + config path
unio verify <w> <task>    machine gate assist: diff vs the task's
                               "- path" scope lines + run its "$ " Validate
                               lines in the worktree + commit sanity;
                               appends verify block and records validation;
                               exit 0 PASS, 1 FAIL (violation, failed check,
                               empty diff, tampered task), 2 INCOMPLETE (no
                               scope or no Validate lines) or unsupported
                               worktree state
unio diff <w> [--stat]    changes on agent/<w> vs base: committed and
                               uncommitted, separately
unio review <w> <task> [agent]  cross-vendor review: a DIFFERENT agent
                               judges task order + committed diff from a
                               neutral dir; gated and parsed as in §3;
                               exit 0 approved, 1 changes/failure, 2 unknown
unio result <w> <task>    structured result JSON on stdout only; no
                               provider call; exit 2 if missing, malformed or
                               the worktree state is unsupported
unio handoff <w> <task>   new same-checkout context packet under
                               coord/handoffs (see §3); not a backup
unio sync [w]             bring base's merged work into worker
                               branches (ff when fully merged, merge
                               otherwise; skips dirty/running; aborts and
                               reports on conflict)
unio race <task> <w1> <w2> [...]  copy <task>.md to <task>-<w>.md per
                               worker and dispatch all in background;
                               OWNER merges at most one winner
unio sabotage <w>         saboteur seat: sync <w>, generate a SAB-*
                               task from the template, dispatch background
unio score [root]         per-worker scorecard from ledger.jsonl:
                               runs, ok/fail, walls, verify rate, merges,
                               avg duration
unio doctor               preflight the project: base branch present,
                               agent binaries, python3, worktree health,
                               stale pidfiles, disk headroom; nonzero on error
unio new <url> [name] [w...]  bootstrap a project: clone -> dev branch
                               -> init -> copy $CONF/playbooks/*.md into
                               coord/docs/
unio status               off-agents, tasks, reports, review queue
                               (unreviewed commits per worker), running jobs
unio off <agent> [dur]    bench agent (dur: 30m|5h|7d; absent=manual);
                               run refuses benched agents; expiry auto-clears
unio on <agent>           un-bench
unio stop | resume        create/remove coord/STOP (global run gate)
```

Environment: `UNIO_TIMEOUT` (seconds, default 3600) caps each run;
`UNIO_VERIFY_TIMEOUT` (default 900) caps each Validate command;
`UNIO_REVIEW_TIMEOUT` (default 900) caps a review call.
`UNIO_AUTO_OFF` is accepted for compatibility and has no effect: worker
output never benches an agent or writes availability/configuration state.
A limit warning and ledger `wall=1` mean suspected limit language in a
failed-for-the-helper run's normalized final window — actual exit nonzero,
or zero commits against the base and zero uncommitted files — never a
confirmed provider quota. A successful run with work stays `wall=0` and
keeps its real exit whatever it printed. Benching remains an explicit
operator action (`unio off` / `unio on`). `UNIO_AUTO_VERIFY=1` makes
every run append its own verify verdict after finishing. If the worker
succeeds but verification fails or is incomplete, run returns the
verification's nonzero exit; a failed worker retains its own exit code.
`UNIO_AUTO_SYNC=1` fast-forwards a worker onto the base branch
before a run when the worktree is clean, so it never builds against
stale code (otherwise `run` warns and leaves it to the operator).
`UNIO_ALLOW_SECRETS=1` overrides the init secrets preflight. Python 3
(standard library only, nothing downloaded) is required by run, verify,
review, smoke, agents, result and handoff. Unsupported worktree states fail
closed with exit 2: assume-unchanged or skip-worktree index flags (verify,
review, handoff); FIFOs, devices, sockets, nested repositories and submodules
(run, verify, review, result, handoff). Agent
invocation templates live in `~/.config/unio/agents.conf` (project
override: `coord/agents.conf`).

Fleet intelligence: `unio score` (ledger-based, always available)
and the companion tool `myapp <project-root>` (full scorecard incl.
pre-ledger history from reports/*.md). LEAD SHOULD consult one of them
when assigning tasks.

## 5. LIFECYCLE

1. OWNER states intent to LEAD.
2. LEAD reads coord/docs/*, repo docs (AGENTS.md router, docs/ai/), and
   `unio agents`; produces a task breakdown; WAITS for OWNER "go".
3. LEAD freezes shared contracts (types/schemas/fixtures) as commits on
   the base branch BEFORE dispatching dependent tasks; task files cite
   contract paths @ sha.
4. LEAD dispatches via `unio run`; parallel tasks MUST have disjoint
   Allowed-scope sets (changelog.d/ exempt — one file per task); at most
   one task per cycle may modify dependency manifests (package files,
   lockfiles, migrations). Race tasks are the sanctioned exception to
   disjointness: several workers, same scope, at most one merge.
5. WORKER executes its task file exactly: modifies only Allowed-scope
   paths, runs Validate, writes its changelog fragment, commits only files
   it changed (never blanket staging), ends output with the Report
   sections.
6. LEAD verifies, machine first: `unio verify` (scope + Validate +
   commit sanity), then reads the report and `unio diff`; for risky
   diffs also `unio review`. `unio result` shows whether that
   evidence is still current. Reports are claims; diffs, verify verdicts and
   logs are ground truth.
7. OWNER merges accepted branches into base (`git merge --no-ff`).
   Acceptance gate: verify PASS, clean build, tests green, smoke run,
   changelog fragment where the repo keeps a changelog. After the merge
   cycle, LEAD runs `unio sync` so all workshops rebuild on the new
   base.
8. Releases: OWNER-only, explicit, base→main + tag. At release, LEAD rolls
   changelog.d/ fragments into CHANGELOG.md. Order: merge fix → verify →
   tag.

## 6. INVARIANTS (hard rules, numbered)

- I1  A WORKER writes only inside its own worktree, only within the task's
      Allowed scope.
- I2  Out-of-scope need ⇒ do NOT touch it: finish what is in scope, state
      the need in NEEDS-REVIEW (and blockers.md if blocking). Flagging
      beats fixing — recorded precedent.
- I3  OWNER controls integration. LEAD merges only with owner authorization.
- I4  LEAD normally delegates feature code. After one worker and one suitable
      replacement cannot finish, LEAD directly corrects the remaining problem
      in its existing session; preserve work, checks and integration authority.
      Read LEAD-ESCALATION.md and MODEL-SCOREBOARD.md in coord/docs/.
- I5  Workers never switch branches, never push, never touch base/main.
      (Enforced by guard hooks; the rule stands even where hooks are absent.)
- I6  Same obstacle twice ⇒ stop, write blockers.md; do not improvise
      architecture.
- I7  coord/STOP present ⇒ no new runs, no new dispatches.
- I8  Contracts cited in a task file are frozen: request changes via
      blockers.md, never edit them.
- I9  Benched (OFF) agents get no work; LEAD reroutes by the fallback
      policy in MASTER.md.
- I10 Verification is evidence-based: a claim without a diff/test/log
      backing it is treated as unverified. `unio verify` is the
      mechanical floor of that evidence, not its ceiling.
- I11 Workers never edit CHANGELOG.md; changelog entries are per-task
      fragments in changelog.d/, rolled up at release by LEAD/OWNER.
- I12 A run that claims success with an empty diff (no commits, no
      uncommitted changes) is treated as FAILED.
- I13 `ready_for_human_review` is never human acceptance or permission to
      merge; only OWNER accepts and integrates.
- I14 Evidence is bound to a revision. After any change to commit, base,
      task file or worktree content, earlier verify/review results are
      stale: verify again, then review again.
- I15 A handoff packet is context for the same checkout, not a backup,
      restore or provider migration.
- I16 Worktrees are not sandboxes. The execution boundary is the trusted
      host.

## 7. FAILURE PROTOCOL

| Condition | Required behavior |
|---|---|
| Auth/token error in output | Report it verbatim; OWNER re-logins the CLI; task is rerunnable. |
| Suspected limit language (rate/usage limit, quota, resets at) in a failed run's normalized final window | Heuristic only, never a confirmed quota; LEAD may suggest `unio off <agent> 5h` (weekly: 7d) and reroute. |
| Validate commands fail | Do not claim success. Report failure + hypothesis. |
| `unio verify` reports SCOPE VIOLATION | Reject the branch; LEAD re-briefs with corrected scope; a violating diff is never merged as-is. |
| `unio verify` reports INCOMPLETE (exit 2) | The task has no scope or no Validate lines: LEAD adds them. There is no waiver. |
| Unsupported worktree state (flagged index entries, FIFO, device, socket, nested repository, submodule) | Clear it (`git update-index --no-assume-unchanged --no-skip-worktree`, `git sparse-checkout disable`, or remove the file), then rerun the command. |
| Run reports "post-run snapshot failed" | The worker's real exit is recorded but the result stays stale. Fix the worktree, then run the task again. |
| `unio result` shows stale evidence | Verify again, then review again. Never reuse old evidence. |
| Review refused as incomplete material | Commit all work. Binary, non-UTF-8 or oversized changes need manual inspection. |
| Worker lock busy ("already running a task") | Wait or `unio status`; abort a stray background run with `unio kill <task>`. |
| Stale index.lock after a killed run | Cleared automatically at the next `unio run`; if git still complains, remove `<gitdir>/index.lock` by hand. |
| Blocked on missing contract/file | I2/I6: flag, don't fix; wait. |
| Task file ambiguous | LEAD: rewrite it. WORKER: state the ambiguity and the interpretation chosen; prefer the narrower reading. |
| Merge conflict on integration | OWNER decision; LEAD proposes resolution order; nobody force-merges. Routine prevention: `unio sync` after every merge cycle. |

## 8. REFERENCES

- Role cards: `MASTER.md` (lead), `WORKER.md` (worker) — override this doc.
- Owner playbooks: `coord/docs/ai-project-setup-playbook.md`,
  `coord/docs/ai-full-build-recipe.md` — define working style (dev/main
  model, verified milestones, evaluation-first, docs upkeep).
- Human documentation: docs/HANDBOOK.md, docs/MASTER-PLAN.md,
  docs/SETUP.md in the Unio docs repository.
