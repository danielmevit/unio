# Git Index Lock Safety — Preserving Live and Unknown Locks

## 1. Problem Statement & Confirmed Defect (R-02)

In versions prior to 0.5.28, `unio run` startup contained an eager lock-cleaning routine:
```bash
# a run killed mid-commit can leave git's index.lock behind — clear it
local gd
gd=$(git -C "$wt" rev-parse --path-format=absolute --git-dir 2>/dev/null || true)
if [ -n "$gd" ] && [ -f "$gd/index.lock" ]; then
  rm -f "$gd/index.lock"
  echo "note: removed stale $gd/index.lock (a previous run died mid-commit)" >&2
fi
```

This automatic deletion assumed that because Unio holds a per-worker flock (`$root/coord/.locks/$worker.lock`), any existing `index.lock` in the worker's worktree Git directory must be a dead leftover from a previously interrupted task.

However, a worker flock serializes only Unio worker invocations. It does **not** serialize unmanaged Git processes, interactive user commands (`git commit`, `git add`, `git rebase`), or background tools concurrently accessing the worktree.

In reproduction R-02 (confirmed independently by lead against official 0.5.27 release), an active writer (`git update-index --stdin`) held a legitimate `index.lock`:
1. `unio run` deleted `$gd/index.lock` via `rm -f`, emitted a false note claiming it was "stale", and proceeded to admit the task and invoke the provider.
2. The active writer completed its write pass and attempted to atomically rename its lock to `index`, but failed with:
   `fatal: Unable to write new index file` (exit 128)
3. The staged update was lost, while target file bytes remained untouched.

## 2. Invariants & Safe Bounded Design

To ensure data integrity and prevent race conditions with external Git tooling, Unio adopts a strict fail-closed policy:

1. **Unknown Ownership**:
   An existing `index.lock` has Unknown ownership unless proven otherwise. Unio makes no global serialization claims over unmanaged Git processes and does not guess staleness based on file `mtime`, PID heuristics, or process table inspection.

2. **Zero-Mutation on Contention**:
   If `index.lock` is detected upon `unio run` startup (including regular files, valid symlinks, broken symlinks, FIFOs, sockets, or directories), Unio must leave the filesystem entry, target files, and index bytes untouched.

3. **Early Nonzero Refusal**:
   Startup aborts immediately with a clear diagnostic message before allocating budget slots, admitting the task, or invoking any model provider. No AI quota or billing allowances are consumed when a lock is present.

4. **Robust Gitdir Resolution**:
   If the Git directory for the target worktree cannot be determined, startup fails immediately rather than writing or removing files blindly.

5. **Manual Remediation Guidance**:
   Documentation in `docs/PROTOCOL.md`, `docs/HANDBOOK.md`, and project templates advises operators to inspect active system processes before manually removing an abandoned lock file.

## 3. Visible Startup-Refusal Diagnostics (0.5.28)

A refusal that only a detached child sees is invisible: with `unio run -b`, the
parent prints its launch acknowledgement (`started in background …`) and exits
0 — that acknowledgement is **not** a Source success — while the detached child
detects the Gitdir/index.lock condition, refuses, and dies with its stderr
discarded (`nohup … >/dev/null 2>&1`). Three distinct facts must never be
conflated:

1. **Parent acknowledgement** — exit 0 and the `started in background` line
   only mean the run was launched; they say nothing about provider startup.
2. **Child refusal** — the child still fails closed exactly as in the
   foreground: nonzero exit, the original diagnostic on stderr, the existing
   lock untouched, no admission, no slot, no owner grant, no retry.
3. **Provider not started** — no provider command ran, so there is no Source,
   adapter or provider exit to report; the refusal must never be mislabeled as
   a budget, quota or code-quality failure.

To close that visibility gap, `cmd_run` records the refusal through
`startup_refuse_report` before its (unchanged) `die` for both pre-provider
startup failures: `phase=gitdir-resolution` (Git directory cannot be
determined) and `phase=git-index-lock` (an entry named `index.lock` already
exists). The helper appends a dated, distinct fragment to the task's existing
report and log:

```
## startup-refused 2026-11-13T… — phase=git-index-lock worker=<worker> agent=<agent> task=<task>
  <original actionable reason>
  gitdir: <worktree gitdir>
  No provider was started: no admission, no slot, no owner grant, no retry.
  This is a Git startup refusal, not a budget, quota or code-quality failure.
  Actionable: inspect the worktree lock (or gitdir) manually, confirm no Git writer is active, then run again.
```

The fragment is therefore visible through `unio report <task>` (report file)
and `unio tail <task>` (log file). Appends are strictly append-only: existing
reports and logs — including a previous sentinel or a later normal run's
content — are never rewritten or replaced, and the helper refuses to write
through a symlinked or non-regular report/log entry. The child's exact refusal
(exit 1, original stderr diagnostic) and the parent's acknowledgement
semantics are unchanged. Successful foreground and background runs record
their normal `## run …` fragments and remain appendable after a refusal
fragment.
