# Adaptive lead effort (experimental)

Status: experimental vertical slice for contract
`docs/development/contracts/0532-ADAPTIVE-LEAD-EFFORT-V1.md` (0.5.x series,
unreleased). `unio lead-session` is an opt-in managed lead session with
adaptive requested effort. It is not a replacement dashboard, it never adopts
an unmanaged TUI or connection, and `unio lead` keeps its existing
budget-reservation meaning.

## What it does

- One managed lead session per workspace, started explicitly by the owner
  with a goal file and model. The session records the workspace, an opaque
  shared-budget label, route, model, baseline effort and Unknown effective
  settings. No credentials or account ids are stored.
- Automatic effort selection: routine coordination turns request `low`;
  substantive planning and review turns request the configurable ceiling
  (default `xhigh`, never higher than `xhigh`). The supported model efforts
  are queried exactly once per session on an explicitly authorized owned
  connection (the `model/list` seam); anything not advertised — or outside
  the known rank `low`, `medium`, `high`, `xhigh` (for example `max` or
  `ultra`) — is refused. There is no fallback effort.
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
unio lead-session start --goal FILE --model MODEL [--ceiling xhigh]
                        [--effort auto|low|medium|high|xhigh]
                        [--max-requests N] [--max-mappings N]
                        [--transport fake] [--fake-efforts low,medium,high,xhigh]
                        [--json]
unio lead-session run --file FILE --request-id ID
                      [--kind coordination|planning|review] [--json]
unio lead-session status [--json]
unio lead-session effort show|auto|manual EFFORT|request EFFORT [--reason R]
unio lead-session worker register ID|wait|terminal ID [--json]
unio lead-session stop [--json]
unio lead-session output [--after N] [--limit N] [--json]
```

- `start` requires an explicit owner goal file (bounded, private, regular,
  UTF-8, at most 8 KiB) and model. `--ceiling` bounds planning/review; it
  must be a known rank no higher than `xhigh`. `--effort auto` records the
  ceiling as the baseline requested effort; an explicit effort starts in
  manual mode. `--max-mappings` is the explicit provider-turn mapping bound
  (1..64; the legacy bridge default of four is unchanged for non-lead use).
- `run` submits one bounded owner turn (at most 8 KiB). Without `--kind`,
  the turn is review when a wakeup is pending, else coordination. Request
  ids are idempotent: an identical replay returns the recorded result with
  zero new provider calls; changed content refuses.
- `effort manual` suspends auto; `effort auto` resumes it; `effort request`
  is pending for the next turn only (a newer request replaces an older
  pending one; manual clears it).
- `worker register` records a worker; `worker wait` marks the lead as
  waiting; `worker terminal` records one terminal event and queues one
  review wakeup. Duplicate terminal events for the same worker refuse.
- `stop` sets STOP. Workers keep running; new turns refuse; there is no
  automatic or manual resume in this slice.
- `output` reads the bounded ordered journal with explicit gap and
  truncation flags (same limits as managed sessions).

## Ownership, authority and recovery

- `coord/lead-effort/owner.json` records the one managed lead session per
  workspace. A second `start` refuses while the recorded session is live;
  a stopped session may be replaced by an explicit new start. Unknown or
  mismatched ownership refuses every control operation.
- The controller injects the authority and ownership callbacks required by
  the managed lead core; STOP is enforced both by the controller and by the
  injected authority, before any transport call.
- Provider turn ids validated by acknowledgements are recorded durably
  outside the core and handed explicitly to the next bridge instance. A
  handoff is proven only when it covers exactly the session's recorded
  non-rejected turns with matching generations; anything missing, extra or
  mismatched refuses. An unacknowledged (outcome_unknown) turn can never be
  handed over: the session reopens for inspection only, an identical replay
  still returns its recorded result, and every new turn refuses. There is
  no id eviction, rebinding, automatic resend or new thread.

## Honest boundary of this slice

The real owned app-server connection — native thread creation, notification
routing, and the native account/lead reservation that counts the registered
lead exactly once — is not wired in this slice. The default transport refuses
with an explicit message; `--transport fake` selects a deterministic fake
owned connection for tests and demos that implements only `model/list` and
`turn/start` and records every call to a bounded log. No real Codex
invocation, thread, turn or worker happens during development or validation.
Native cross-workspace and unmanaged visibility remain Unknown.

## Components

- `tools/lead-effort.py` — importable adaptive effort policy (query once,
  rank and ceiling, manual/pending controls, wakeups, immutable decisions).
- `tools/managed-lead.py` — managed lead session core (unchanged).
- `tools/managed-lead-codex.py` — owned Codex bridge with opt-in per-turn
  effort and explicit handoff; legacy defaults preserved exactly.
- `tools/lead-session.py` — the `unio lead-session` CLI controller.
- Tests: `tests/unio-lead-effort.py`, `tests/unio-lead-session.py`,
  `tests/unio-managed-lead.py`, `tests/unio-managed-lead-codex.py`.
