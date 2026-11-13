# BACKGROUND-STARTUP-REFUSAL-20261113

Make the pre-provider Gitdir-resolution / index.lock startup refusal of `unio run` visible in the task's durable evidence through a dated, distinct `## startup-refused` fragment.

### Background and Confirmed Gap
The index-lock safety fix fails closed before provider/admission, but a background launch hides the explanation: `unio run -b` prints its launch acknowledgement (`started in background …`) and exits 0 — an acknowledgement, never a Source success — while the detached child detects the worktree's `index.lock` (or an unresolvable Git directory), refuses, and dies with its stderr discarded by `nohup … >/dev/null 2>&1`. Independent lead review confirmed no task report, log, or ledger line explained the refusal.

### Visible, Bounded Diagnostic
- New small top-level `startup_refuse_report` helper; `cmd_run`'s two pre-provider startup diagnostic branches (Gitdir resolution failure, existing `index.lock`) call it before their unchanged `die`.
- Appends a dated, distinct `## startup-refused <timestamp> — phase=<phase> worker=<worker> agent=<agent> task=<task>` fragment to the task report (`coord/reports/<task>.md`) and log (`coord/reports/<task>.log`), visible through `unio report` and `unio tail`.
- The fragment names the phase (`gitdir-resolution` or `git-index-lock`), the worker/task, the original actionable reason, states that no provider was started (no admission, slot, owner grant or retry), and explicitly that this is not a budget, quota or code-quality failure.
- Append-only: existing reports/logs (sentinels, prior and later normal-run content) are never rewritten; the helper refuses to follow a symlinked or non-regular report/log entry; it never fails the run.
- No fabricated evidence: no invented Source/adapter/provider exit, no forged or replaced canonical task results, reports, logs, ledger history, owner grants, retries or reviews. The helper writes no ledger line.

### Preserved Semantics
- Foreground refusal: nonzero exit and the original stderr diagnostic unchanged.
- Background: parent acknowledgement (exit 0, launch acknowledgement only) unchanged; child refusal exactness unchanged (exit 1, original message).
- Worker flock and cleanup traps, admission and all other startup paths untouched; no automatic retries, lock deletion or staleness heuristics; no provider call, slot allocation or owner-grant consumption after refusal.
- Normal foreground/background successful runs behave normally; their `## run …` fragments follow refusal fragments append-only when present.
- New offline regression test `tests/unio-startup-refusal.py` (disposable install/project/offline provider counter, bounded polling of background outcome) added to the quality gate as exactly one line.
