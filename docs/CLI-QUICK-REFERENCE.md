# CLI quick reference

One page for the commands used every day. Full detail: `unio help` and the
docs under `docs/`. Layout: `PROJECT/<clone>` (base branch), `PROJECT/wt/<w>`
(one worktree per worker), `PROJECT/coord/` (tasks, reports, results, locks).

## Running work

| Command | What it does |
| --- | --- |
| `unio run [-b] <worker> <task-id>` | Run `coord/tasks/<task-id>.md` in the worker's worktree. `-b` detaches. |
| `unio wait <task-id> [<task-id>...] [--any] [--timeout s]` | Bounded read-only wait for the exact native attempt(s); returns the attempt's recorded worker exit when known, Unknown when its immutable receipt is lost. |
| `unio tail [task] [-f] [--lines N]` | Print a run's log tail; `-f` follows live. |
| `unio kill <task-id>` | Stop a background run (whole session). |
| `unio report <task-id> [lines]` | Read a task's report. |
| `unio verify <worker> <task>` | Machine gate: scope lines + `Validate` commands + commit sanity. |
| `unio status` | Off-agents, tasks, reports, review queue, running jobs. |
| `unio stop` / `unio resume` | Project kill switch for ALL new runs. |

## Background readiness (`run -b`)

`unio run -b` reports `started in background` **only after the detached child
acknowledges this exact launch**:

- the parent creates a fresh private acknowledgement file for this launch
  (`coord/.locks/bg-ack.*`, removed when the parent exits);
- the child writes `started` only after its task-addressed identity
  (`coord/reports/<task>.pid` + `<task>.own`) is safely published — after
  authoritative admission, so a refused child can never be reported as
  started;
- a child that exits before that (STOP, admission refusal, startup refusal)
  acknowledges `refused`, and the parent reports the refusal instead;
- if no matching acknowledgement arrives within the bound, the parent
  reports `background start Unknown` — never a start claim, never a signal,
  never an automatic retry.

The child publishes its PID and ownership before acknowledging the launch.
A fast run can finish and retire those files before the parent prints its
message. Use `unio wait` to read the recorded exit. The acknowledgement wait
is bounded by
`UNIO_BG_ACK_TIMEOUT` (whole seconds 1..900; default: admission timeout + 30)
and makes `run -b` block for the child's pre-start preparation (admission,
disk preflight, git checks) instead of returning instantly.

## `unio wait`

```
unio wait <task-id> [<task-id>...] [--any] [--timeout seconds]
```

Waits for background runs **read-only**: it binds the exact native attempt
for each task — the attempt identity minted under the retry-state lock
(`coord/retries/<task>/state.json`) is the single exact marker, frozen into
the structured result before the Source runs and carried by an immutable
per-attempt terminal receipt
(`coord/results/<worker>/<task>.attempts/<attempt-id>.json`). A pending
attempt is watched through its published shell identity (ownership record
plus matching pid file, verified against stable local identity: boot id,
pid, start ticks, session id, uid); a terminal attempt is bound directly and
resolved from its immutable receipt, so an immediately finishing worker or a
retired control file never hides the exact exit.

- **Exact attempts, never substitutions** — when a newer attempt replaces the
  task-addressed result view, a waiter already bound to an older attempt
  still returns that attempt's original exit from its immutable receipt; if
  the receipt is lost, the outcome is Unknown. A later result is never
  substituted. The structured result only counts while it still names the
  bound attempt. While polling, an exact receipt for the bound attempt takes
  precedence over a pending flag plus a live shell identity, so an attempt
  whose terminal exit already exists is resolved from that receipt
  immediately. The live owner proof is bound to the same native attempt
  generation as the sampled ledger entry (the ledger is re-read after the
  ownership/pid sample): a same-worker replacement run that supplies its own
  live identity after an older attempt was observed pending is a mixed
  observation — resampled a bounded number of times, then rejected, never
  attached to the older attempt.
- **Multiple handles** — the public ownership record selects the worker;
  without one, a ledger naming exactly one worker is still unambiguous, and
  a ledger naming several workers is refused (`nothing is bound`) rather
  than guessed. Give concurrent assignments distinct task IDs and use
  `unio result <worker> <task>` to inspect a specific worker's stored result.
- **Deterministic behavior** — tasks are bound in argument order; duplicates
  are refused; a task with nothing to bind fails the whole wait before any
  watching starts (with the last stored result as clearly unbound context).
- **Exit codes** — a single task returns the worker's actual exit code;
  several tasks return 0 (all zero), 1 (any recorded exit nonzero) or 2 (any
  Unknown, or any attempt still running at the deadline — a partial
  completion is never success, even when another task exited 0). `--any`
  returns the first bound attempt to end (ties in argument order) with its
  actual exit code, or 2 if it is Unknown; the tasks that have not ended are
  reported as `still running (remaining work still in progress; no signal
  was sent)` — timeout wording is used only when the deadline actually
  passed. Unknown is always reported as text with a conventional failure
  exit — there is no magic exit code for Unknown.
- **Receipt writer fault** — the immutable per-attempt receipt is
  supplemental evidence: if only that extra write fails (storage refusal,
  ENOSPC), a diagnostic is printed and the canonical structured result still
  records the truthful exact attempt exit; `unio wait` then resolves from the
  canonical result naming the bound attempt.
- **Handled cases** — already completed attempt (control files retired),
  fast completion, task reuse (each attempt keeps its own receipt), stale
  or malformed pid evidence, pid reuse (start-ticks mismatch), detached or
  rebooted shells (a stale identity is never claimed running), concurrent
  launch of the same task (the waiter stays bound to its attempt), lost
  public identity, orphan (shell died without recording an exit →
  completion Unknown), and a bounded `--timeout` (default 3600, whole
  seconds 1..86400).
- **Never** — no signal to the worker (that is `unio kill`), no provider or
  model call, no policy or worker mutation, no retry. Ctrl-C stops only the
  waiter; the detached run keeps going.

## Compatibility

- `run -b` output still starts with `started in background` (now with the
  session pid); scripts matching that prefix keep working.
- `run -b` now blocks until the child acknowledges (typically a few
  seconds; bounded by `UNIO_BG_ACK_TIMEOUT`). Callers that need the old
  fire-and-forget timing can background the command itself.
- A confirmed startup refusal or an Unknown acknowledgement returns exit 2. If acknowledgement is Unknown, check the recorded attempt before launching again.
- New environment variable: `UNIO_BG_ACK_TIMEOUT` (invalid values refuse
  before any admission or grant, like `UNIO_ADMISSION_TIMEOUT`).
- STOP, owner grants, authoritative child admission, the worker lock, real
  accounts, cleanup and foreground semantics are unchanged.
