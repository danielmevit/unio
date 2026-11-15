# Adaptive lead effort (experimental)

Status: experimental vertical slice for contracts
`docs/development/contracts/0532-ADAPTIVE-LEAD-EFFORT-V1.md` and the
owner correction `...-V2.md` (0.5.x series, unreleased). `unio
lead-session` is an opt-in managed lead session with adaptive requested
effort. It is not a replacement dashboard, it never adopts an unmanaged
TUI or connection, and `unio lead` keeps its existing budget-reservation
meaning. Per V2, this first adaptive interface exposes only AUTO plus
LOW and XHIGH: no intermediate effort levels are choices in adaptive
mode, while advertised sets containing medium/high and fixed legacy
worker/core settings remain compatible.

## What it does

- One managed lead session per workspace, started explicitly by the owner
  with a goal file and model. The session records the workspace, an opaque
  shared-budget label, route, model, baseline effort and Unknown effective
  settings. No credentials or account ids are stored.
- Automatic effort selection: routine coordination turns request `low`;
  substantive planning and review turns request the ceiling (default and
  maximum `xhigh`; `low` is the only other allowed ceiling). The supported
  model efforts are queried exactly once per session on an explicitly
  authorized owned connection (the `model/list` seam); anything not
  advertised — or outside the known rank `low`, `medium`, `high`, `xhigh`
  (for example `max` or `ultra`) — is refused. There is no fallback
  effort. Medium and high may be advertised (legacy models list them)
  but are not selectable in this interface.
- Every turn is one explicit `run` command. The decided effort is sent
  explicitly as the `effort` override of that one `turn/start` on the same
  owned thread. The app-server schema has no effort override on `turn/steer`,
  so an effort change is only ever applied by the next turn start; the
  effective provider-side effort remains Unknown everywhere.
- Zero model calls while waiting: nothing is ever sent automatically. Status,
  effort, worker, stop and output commands make no provider calls at all.
- Worker terminal events are explicit controlled events. Each queues at most
  one review wakeup; the next turn without an explicit work kind consumes
  exactly one wakeup and is classified as review. Heartbeat or status
  polling can never create a wakeup or trigger inference.
- Manual override suspends automatic selection until `effort auto` is
  selected again. `effort request` records a pending effort that is applied
  only by the next turn, never mid-turn.
- STOP blocks new turns without killing workers, and nothing resumes it
  automatically. No command in this slice clears a STOP; a stopped session
  stays stopped and a new session must be started explicitly.
- Per-turn decisions (turn id, kind, effort, source, reason) are immutable and
  visible in `status`, together with all limits.

## CLI

```sh
unio lead-session start --goal FILE --model MODEL [--ceiling low|xhigh]
                        [--effort auto|low|xhigh]
                        [--max-requests N] [--max-mappings N]
                        [--transport fake] [--fake-efforts low,medium,high,xhigh]
                        [--json]
unio lead-session run --file FILE --request-id ID
                      [--kind coordination|planning|review] [--json]
unio lead-session status [--json]
unio lead-session effort show|auto|manual low|xhigh|request low|xhigh [--reason R]
unio lead-session worker register ID|wait|terminal ID [--json]
unio lead-session stop [--json]
unio lead-session output [--after N] [--limit N] [--json]
```

- `start` requires an explicit owner goal file (bounded, private, regular,
  UTF-8, at most 8 KiB) and model. `--ceiling` bounds planning/review; in
  this first interface it accepts only `low` or `xhigh` (default `xhigh`).
  `--effort auto` records the ceiling as the baseline requested effort;
  an explicit `low` or `xhigh` starts in manual mode; `medium` and `high`
  refuse as not exposed in this first adaptive interface. `--max-mappings`
  is the explicit provider-turn mapping bound (1..64; the legacy bridge
  default of four is unchanged for non-lead use).
- `run` submits one bounded owner turn (at most 8 KiB). Without `--kind`,
  the turn is review when a wakeup is pending, else coordination. Request
  ids are idempotent: an identical replay returns the recorded result with
  zero new provider calls; changed content refuses. The JSON payload
  separates the submission acknowledgement (`status`: accepted/rejected/
  uncertain), the actual turn outcome (`turn_status`: completed/failed/
  interrupted, or null while pending; `turn_completed`) and the observed
  native exit (`provider_exited`, plus a bounded private `stderr_tail`
  when the owned process died). `delivery` states the combined result:
  `completed`, `failed`, `interrupted`, `rejected`, `uncertain` or
  `pending`. Exit codes are truthful: 0 only for an observed completed
  turn (or an explicit `--turn-wait 0` asynchronous acknowledgement,
  which stays `pending` — the owned process is terminated at command
  end, so no background execution is promised); 1 for controlled
  refusals; 2 rejected; 3 uncertain; 4 failed; 5 interrupted; 6 accepted
  but not observed terminal before the wait ended (timeout or provider
  exit). A process exit is never inferred as model success.
- `effort manual` suspends auto; `effort auto` resumes it; `effort request`
  is pending for the next turn only (a newer request replaces an older
  pending one; manual clears it). Both accept only `low` or `xhigh` in
  this first interface; `medium` and `high` refuse.
- `worker register` records a worker; `worker wait` marks the lead as
  waiting; `worker terminal` records one terminal event and queues one
  review wakeup. Duplicate terminal events for the same worker refuse.
- `stop` sets STOP. Workers keep running; new turns refuse; there is no
  automatic or manual resume in this slice.
- `output` reads the bounded ordered journal with explicit gap and
  truncation flags (same limits as managed sessions).

## Ownership, authority and native project admission

- `coord/lead-effort/owner.json` records the one managed lead session per
  workspace. A second `start` refuses while the recorded session is live;
  a stopped session may be replaced by an explicit new start. Unknown or
  mismatched ownership refuses every control operation.
- Project STOP (`coord/STOP`), real installed/project off holds with expiry
  semantics (`coord/off/<agent>`, `$UNIO_CONF_DIR/off/<agent>`), and initialized
  project policy (`coord/work-policy.json`) are enforced before any owned child
  process spawn or turn execution (per contract V4).
- The registered lead agent in project work-policy must match the expected lead
  (`codex`). Absent, mismatched or malformed policy rejects admission before
  child launch. Arbitrary `--budget-label` arguments or fabricated groups are
  refused; the lead's group is resolved from real policy accounts.
- Under `tier: low` (limit 1), the lead reservation is counted exactly once
  (`active_native + 1 <= cap`). If active native workflows occupy the group,
  admission refuses with capacity limit without creating a duplicate slot.
- Short policy transaction and owned lease lock: admission acquires non-blocking
  `coord/.locks/lead-session.lock` first, then briefly acquires
  `coord/.locks/work-policy.lock` to check policy and slot counts. It releases
  `work-policy.lock` immediately so other groups are never blocked during lead
  model inference. The owned lease lock is held during command execution.
  Lead and account setters (`unio set-lead`, `unio set-account`) check the
  owned lease lock with non-blocking flock, preventing races with active owned
  lead turns.
- Read-only status, effort query and pending controls make zero provider calls
  and remain accessible even when project STOP is active.
- Provider turn ids validated by acknowledgements are recorded durably
  outside the core and handed explicitly to the next bridge instance. A
  handoff is proven only when it covers exactly the session's recorded
  non-rejected turns with matching generations; anything missing, extra or
  mismatched refuses. An unacknowledged (outcome_unknown) turn can never be
  handed over: the session reopens for inspection only, an identical replay
  still returns its recorded result, and every new turn refuses. There is
  no id eviction, rebinding, automatic resend or new thread.

## Concurrent controls, ownership and diagnostics

- Control-state changes are short locked transactions. A per-session
  control lock (`coord/lead-effort/<session_id>.lock`) is held only for
  the bounded read-modify-write of the control state — never across a
  model/RPC turn — so concurrent commands never wait on an active turn.
- A `run` never writes its stale pre-turn snapshot back: at persist time
  it re-reads the current control state under the control lock and merges
  only its own effects (proven provider mappings, its immutable decision
  records, its at-most-one pending-effort consumption and at-most-one
  wakeup consumption). A pending effort request, worker terminal wakeup
  or STOP arriving during an active turn therefore survives; a pending
  effort arriving after the current turn's decision applies only from
  the next turn on.
- Mutating controls (`run`, `effort auto|manual|request`, `worker`,
  `stop`) require the current workspace owner session recorded under
  `coord/lead-effort/owner.json`, even when `--session` is supplied
  explicitly. Read-only `status`, `output` and `effort show` stay
  available for a retired session but are explicitly labelled
  `historical: true`.
- An explicit typed provider rejection on initialize/account/model/thread
  operations is a controlled refusal that preserves the method, code and
  bounded reason — never a raw traceback. Typed `turn/start` rejection
  stays distinct from missing or uncertain acknowledgements.
- If the owned process dies mid-turn, the wait stops promptly (no busy
  loop until the deadline), the final buffered terminal events and a
  bounded private stderr tail are drained, the outcome stays
  `pending`/Unknown with `provider_exited: true`, and no terminal status
  is ever inferred from the process exit.

## Honest boundary of this slice

Native project policy admission, STOP, off-holds, tier slot counting, lock-backed
owned lease and the owned app-server connection lifecycle are wired and verified
via executable fake app-server and genuine offline policy fixtures (contract V4).
Real Codex model inference, external network calls, paid credits/billing, and
cross-workspace/unmanaged visibility remain zero/Unknown during development and
validation. No real model calls, billing, or credentials are used.

## Components

- `tools/lead-effort.py` — importable adaptive effort policy (query once,
  rank and ceiling, manual/pending controls, wakeups, immutable decisions).
- `tools/lead-session-policy.py` — native project policy admission, STOP, off holds,
  tier slot counting, lock-backed lease and setter guards.
- `tools/managed-lead.py` — managed lead session core (unchanged).
- `tools/managed-lead-codex.py` — owned Codex bridge with opt-in per-turn
  effort and explicit handoff; legacy defaults preserved exactly.
- `tools/lead-session-codex.py` — owned Codex connection lifecycle and notification
  pumps.
- `tools/lead-session.py` — the `unio lead-session` CLI controller.
- Tests: `tests/unio-lead-effort.py`, `tests/unio-lead-session.py`,
  `tests/unio-lead-session-codex.py`, `tests/unio-managed-lead.py`,
  `tests/unio-managed-lead-codex.py`.
