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
