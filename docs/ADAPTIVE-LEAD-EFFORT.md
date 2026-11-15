# Adaptive lead effort (experimental)

Status: experimental vertical slice for contracts
`docs/development/contracts/0532-ADAPTIVE-LEAD-EFFORT-V1.md` and the
owner correction `...-V2.md`, with the final review corrections of
`0531-ADAPTIVE-REVIEW-CORRECTIONS-V7.md` (0.5.x series, unreleased). `unio
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
- No inference while waiting: nothing is ever sent automatically. Status,
  effort, worker, stop and output commands open no provider connection at
  all. `run` and `recover` make control RPCs (initialize, account check,
  thread resume/read, and `turn/interrupt` when requested); control RPCs
  are not inference. Only `turn/start` starts a model turn.
- Work kind is never recognized from prose. A turn is `planning` or
  `review` only when the owner passes `--kind`, or `review` when a recorded
  worker terminal wakeup is pending; everything else is `coordination`.
  Worker events are recorded by the owner (`worker register`, `worker
  terminal`); nothing watches workers, and there is no continuous or
  autonomous phase scheduler.
- Each worker terminal event queues at most one review wakeup; the next
  turn without an explicit work kind consumes exactly one wakeup.
  Heartbeat or status polling can never create a wakeup or trigger
  inference.
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
                      [--kind coordination|planning|review] [--reason R]
                      [--turn-wait SECONDS] [--interrupt-drain SECONDS] [--json]
unio lead-session recover [--interrupt] [--drain SECONDS] [--json]
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
  ids are idempotent: an identical replay returns the recorded result and
  starts no new turn (no `turn/start`, no inference). On the owned
  transport a replay still passes admission (STOP, holds, capacity) and
  makes control RPCs (initialize, account, thread resume, possibly thread
  read); it never waits for or interrupts the recorded turn. Changed
  content refuses.
- The JSON payload separates the submission acknowledgement (`status`:
  accepted/rejected/uncertain), the actual turn outcome (`turn_status`:
  completed/failed/interrupted, or null when no terminal was observed;
  `turn_completed`), the wait (`wait.seconds`, `wait.outcome`: `terminal`,
  `deadline`, `provider_exited` or `replay_not_waited`), any deadline
  interrupt (`interrupt`), restored consumption (`restored`) and the
  observed native exit (`provider_exited`, plus a bounded private
  `stderr_tail` when the owned process died). `delivery` is one of
  `completed`, `failed`, `interrupted`, `rejected`, `uncertain` or
  `unknown`. Exit codes: 0 only for an observed completed turn; 1
  controlled refusal; 2 rejected; 3 uncertain; 4 failed; 5 interrupted;
  6 unknown (accepted, no terminal observed). A process exit or an
  interrupt acknowledgement is never inferred as a turn outcome.

### Waiting, deadline and interrupt (owned transport)

- The owned app-server process belongs to the `run` command and is
  terminated when the command ends; terminating it ends that local
  app-server, so the command keeps it alive while the turn runs.
  `--turn-wait` (default 3600 seconds, 1..86400) bounds that wait.
  `--turn-wait 0` is refused before launch: an asynchronous
  acknowledgement would be killed by the same command.
- At the deadline, `run` sends one `turn/interrupt` with the exact proven
  `threadId` and provider `turnId` (the local schema requires both; the
  `{}` response only acknowledges the request). It then drains terminal
  events for `--interrupt-drain` seconds (default 30, 1..600) and reads
  the provider's own thread state once. An observed `turn/completed` or
  terminal thread status is recorded (usually `interrupted`, exit 5).
  Without one, the turn stays active in the session and the outcome is
  `unknown` (exit 6) — an acknowledgement is not terminal proof. Partial
  output, the original request, the thread and the provider-turn mapping
  are kept; nothing is resent.
- What Codex reports later for a turn whose app-server was killed is
  Unknown (no live evidence in this slice). The run never assumes it kept
  computing or finished.

### Recovering a stale turn

`unio lead-session recover` handles a turn that was acknowledged (its
provider id is proven) but whose end was never observed, on the SAME
thread:

1. It passes normal admission (project STOP refuses), then opens one owned
   process, resumes the exact thread and reads the provider's own turn
   status.
2. A terminal provider status is recorded (exit 0).
3. If the provider still reports the turn in progress, plain `recover`
   changes nothing (exit 6). `recover --interrupt` sends one
   `turn/interrupt` for that exact turn, drains terminal events for
   `--drain` seconds and reads the thread again; it records a terminal
   only from that evidence (exit 0), otherwise it stays Unknown (exit 6).
4. It never sends `turn/start`, never resends the request, never fabricates
   a terminal and never replaces or resets the thread. An unacknowledged
   (`outcome_unknown`, unproven) turn refuses before any process starts.

Session STOP does not block `recover` (it starts no turn); project STOP
does.

### Rejected and never-sent turns

A turn that was provably never delivered — a typed `turn/start` rejection
with no contradicting provider activity, or a local refusal before any
`turn/start` (for example the provider-turn mapping bound) — does not use
up the pending effort request or the review wakeup it would have consumed.
The attempted decision stays visible in `status` with outcome `rejected`,
and the `run` payload reports what was kept under `restored`. Newer
pending, manual/auto or wakeup changes written while the attempt ran are
kept. An uncertain attempt (malformed acknowledgement, lost connection,
contradicting activity) is never restored.

### Session lifetime limits

- A session records at most `--max-requests` request ids (default 64),
  including rejected and replayed attempts; then `run` refuses with
  `request history exhausted`.
- The provider-turn mapping bound (`--max-mappings`, default and maximum
  64) and the core history of 32 recorded turns bound how many turns one
  session can hand over. Reaching the mapping bound returns `rejected`
  (no turn sent) with a note, never `uncertain`.
- To continue past a limit, `stop` the session and `start` a new one. The
  new session starts a new thread; the earlier conversation context is
  not carried over.

- `effort manual` suspends auto; `effort auto` resumes it; `effort request`
  is pending for the next turn only (a newer request replaces an older
  pending one; manual clears it). Both accept only `low` or `xhigh` in
  this first interface; `medium` and `high` refuse.
- `worker register` records a worker; `worker wait` marks the lead as
  waiting; `worker terminal` records one terminal event and queues one
  review wakeup. Duplicate terminal events for the same worker refuse.
- `stop` sets STOP. Workers keep running; new turns refuse; there is no
  automatic or manual resume in this slice.
- `recover` reconciles, and with `--interrupt` interrupts, one proven
  stale turn on the same thread (see below).
- `output` reads the bounded ordered journal with explicit gap and
  truncation flags (same limits as managed sessions).

## Ownership, authority and native project admission

- `coord/lead-effort/owner.json` records the one managed lead session per
  workspace. A second `start` refuses while the recorded session is live;
  a stopped session may be replaced by an explicit new start. Unknown or
  mismatched ownership refuses every control operation.
- Project STOP (`coord/STOP`), real installed off holds with expiry semantics
  (`$UNIO_CONF_DIR/off/<agent>`, `$HOME/.config/unio/off/<agent>`), read-only
  compatibility observation of `coord/off/<agent>`, and initialized project policy
  (`coord/work-policy.json`) are enforced before any owned child process spawn or
  turn execution (per contracts V4 and V5). The production `unio lead-session`
  entrypoint exports the resolved configuration to its helper, and direct helper
  use defaults consistently to `~/.config/unio`.
- The registered lead agent in project work-policy must match the expected lead
  (`codex`). Absent, mismatched or malformed policy rejects admission before
  child launch. Arbitrary `--budget-label` arguments or fabricated groups are
  refused; the lead's group is resolved from real policy accounts with strict
  native label validation.
- Under `tier: low` (limit 1), the lead reservation is counted exactly once
  (`active_native + 1 <= cap`). Active native workflows are counted with the full
  native 4096-byte slot metadata bound and fail-closed validation for unreadable,
  oversized or corrupted slot directories and files. If active native workflows
  occupy the group, admission refuses with capacity limit without creating a
  duplicate slot.
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
  `unknown` with `provider_exited: true` (exit 6), and no terminal status
  is ever inferred from the process exit. Use `recover` afterwards.

## Permissions, approvals and owner setup

- The owned connection answers every provider server-to-client request
  (command, file-change and permission approvals, user-input and tool
  requests) with an error (`-32601`). Nothing is auto-approved.
- `thread/start` sets no sandbox or approval policy, so the turn inherits
  the user's own Codex configuration. Whether a managed lead turn can run
  a command such as `unio run ...` without an approval prompt depends on
  that configuration; a turn that needs an approval will see it rejected.
  Unio does not widen permissions, and this slice does not change Codex
  settings.
- Owner setup: a ChatGPT-subscription Codex login (`account/read` must
  report `chatgpt`; `OPENAI_API_KEY`/`CODEX_API_KEY` in the environment
  refuse), an initialized project policy whose registered lead is `codex`
  with a real account group, and no other Codex lead session open on that
  account. Close any existing AI CLI lead session before a separate
  terminal-driven managed trial.
- Live limitations: no real Codex turn has been run through this slice.
  Live `turn/interrupt`, approval handling, stale-turn reporting after a
  killed app-server and the effective model/effort are Unknown.

## Honest boundary of this slice

Native project policy admission, STOP, off-holds, tier slot counting with 4096-byte
metadata bound and fail-closed validation, strict label validation matching native
policy, lock-backed owned lease and the owned app-server connection lifecycle are
wired and verified via executable fake app-server and genuine offline policy
fixtures (contracts V4 and V5).
Deadline interrupt, recovery and rejected-attempt restoration are exercised the
same way: the executable fake app-server only progresses a turn while its own
process lives, so a killed turn stays in progress unless an explicit interrupt
or the provider's own thread state ends it.
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
  effort and explicit handoff; legacy defaults preserved, except the
  intentional V7 change that local mapping-capacity exhaustion returns
  `rejected` (known non-delivery) instead of `uncertain`.
- `tools/lead-session-codex.py` — owned Codex connection lifecycle and notification
  pumps.
- `tools/lead-session.py` — the `unio lead-session` CLI controller.
- Tests: `tests/unio-lead-effort.py`, `tests/unio-lead-session.py`,
  `tests/unio-lead-session-codex.py`, `tests/unio-lead-session-policy.py`,
  `tests/unio-managed-lead.py`, `tests/unio-managed-lead-codex.py`.
