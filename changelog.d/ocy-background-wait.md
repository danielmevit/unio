## run -b background readiness and `unio wait`

### Correction: generation-bound owner proof, canonical exit on receipt fault, --any wording (post-af41825)

Three small issues remained after the exact-receipt correction:

- the live owner proof was sampled separately from the retry-state ledger, so
  a same-worker replacement run could supply its own live identity after the
  reader had observed an older attempt pending — although that older
  attempt's terminal exit already existed. The waiter now re-reads the
  generation-bound ledger after the ownership/pid sample: a mixed
  observation is resampled a bounded number of times and then rejected, and
  while polling an exact receipt for the bound attempt takes precedence over
  a pending flag plus a live identity, so the bound attempt's own terminal
  exit is returned immediately;
- a failure of only the supplemental immutable attempt-receipt writer aborted
  the result end write, losing the canonical record. The receipt write is
  now guarded: a clear diagnostic is printed and the original canonical
  result end write still persists the truthful exact attempt exit (actual or
  unbound); storage and task validation protections still fire, they are
  only reported, never bypassed;
- after a successful `--any` winner, the remaining tasks were described with
  timeout wording. They are now reported as still in progress; timeout
  wording is used only when the deadline actually passed.

Existing ownership/kill/recovery/readers are unchanged (no owner-record or
pidfile schema change, no new scheduler, no signal, no provider restart), and
the waiter remains read-only.

### Correction: exact durable attempt receipts (post-43fd307)

Despite the previous verify PASS, three accepted behaviors were wrong:

- a same-worker replacement result was returned to the first run's waiter:
  the waiter read the mutable task-addressed result, so a newer attempt's
  exit (e.g. 9) could be misattributed to an older bound attempt;
- a multi-task all-mode deadline returned 0 when the only completed task
  exited 0 — the still-running tasks were not counted as incomplete;
- a completed attempt could not be bound at all once the public control
  files retired, hiding the exact exit of a fast completion.

The durable contract now uses the native attempt identity already minted
under the retry-state lock (`coord/retries/<task>/state.json`):

- the starting record is frozen before the Source runs and carries the same
  identity (`attempt_id` in the canonical structured result — its shape and
  readers are preserved);
- the terminal evidence carries the same identity as an immutable
  per-attempt receipt
  (`coord/results/<worker>/<task>.attempts/<attempt-id>.json`, created once,
  never replaced);
- a waiter binds the exact attempt; when a newer run replaces the
  task-addressed view it still returns the bound attempt's original exit
  from its receipt, reports Unknown if that immutable evidence is lost, and
  never substitutes a later result;
- a terminal attempt is bound directly from its receipt, so an immediately
  finishing worker or a retired control file never hides the exact exit;
- a partial multi-task deadline is incomplete (exit 2), never success, even
  when another task completed normally with exit 0; `--any` still reports
  its actual winner;
- several workers recording attempts without a public ownership record are
  refused rather than guessed.

Legacy result readers, admissions, signals, STOP, foreground behavior and
all existing `run -b` semantics are unchanged. The waiter remains
read-only: no signal, no provider or model call, no retry.

### Background launch acknowledgement (Ocy report item 2)

`unio run -b` previously printed `started in background` before the detached
child had published anything: the child could still refuse authoritative
admission, and manual `/proc` polling could miss a fast exit or attach to a
reused pid. Now the parent creates a fresh private acknowledgement file for
this exact launch and reports `started` only after the child acknowledges:

- `started` is written by the child only after `owner-bind` has safely
  published the task-addressed identity (`coord/reports/<task>.pid` and
  `<task>.own`), which follows authoritative admission;
- a child that exits before that (STOP, admission or startup refusal)
  acknowledges `refused` from its exit path, and the parent reports the
  refusal — refusal and Unknown are distinguished from started;
- a missed bounded deadline (`UNIO_BG_ACK_TIMEOUT`, whole seconds 1..900,
  default admission timeout + 30) is reported as `background start Unknown`
  with no start claim, no signal and no automatic retry;
- stale evidence cannot be reused: the acknowledgement is a fresh
  run-specific file, never a pid, and the parent removes it on exit.

STOP, owner grants, authoritative child admission, the worker lock, real
accounts, cleanup and foreground semantics are preserved, and fast
completion is preserved (an immediately finishing child still acknowledged
its start).

### New `unio wait` subcommand

`unio wait TASK... [--any] [--timeout seconds]` binds the exact observed
attempt(s), watches stable local identity and returns the actual recorded
worker exit when known. Deterministic multi-task/any behavior, handles an
already completed attempt, stale/malformed pid evidence, pid reuse,
concurrent launch, lost identity, orphan and a bounded timeout. Unknown is
reported as text with a conventional failure exit (no magic exits), and the
waiter never mutates the worker or policy, never signals (interrupt stops
only the waiter) and makes no model calls.

### Files

- `unio-install.sh` — acknowledgement wiring in `run -b` and the detached
  child, `wait` dispatch/help, embedded waiter module
- `tools/run-wait.py`, `tools/embed-run-wait.py` — canonical waiter module
  and its embedder (`python3 -B tools/embed-run-wait.py --check`)
- `tests/unio-run-wait.py` — installed-CLI coverage with a fake worker
- `tests/unio-kill-pid.py` — extended with waiter pid-evidence safety
- `docs/CLI-QUICK-REFERENCE.md` — usage and compatibility notes

### Compatibility

`started in background` remains the output prefix; `run -b` now blocks for
the child's acknowledgement (bounded) instead of returning instantly.
`UNIO_BG_ACK_TIMEOUT` is new and validated like `UNIO_ADMISSION_TIMEOUT`.
No existing command changed meaning.
