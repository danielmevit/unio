# Managed lead Codex RPC bridge — transport contract and limits

Status: parallel prototype slice, 2026-10-24. `tools/managed-lead-codex.py`
is an importable bridge connecting the managed lead core's
`send_turn(facts)` seam to ONE already owned, already initialized Codex
app-server RPC connection and thread. It is NOT final integration or
acceptance: the backend core (`tools/managed-lead.py`) and all existing
runtime/CLI/admission/installer code are unchanged, and the full combined
gate is not claimed. A future native owner creates the connection and
thread, routes notifications and claims the real registered lead exactly
once. Schemas referenced: offline Codex 0.163.0 app-server JSON schemas
(`TurnStartParams`, `TurnStartResponse`, `TurnStartedNotification`,
`TurnCompletedNotification`, `AgentMessageDeltaNotification`,
`CommandExecutionOutputDeltaNotification`); they establish fields for that
CLI, not all future runtime behavior.

## Injected seam

- `CodexLeadTransport(rpc, thread_id, *, model, effort, rejection=RPCRejected,
  buffer_events=64, buffer_bytes=262144)` — the caller injects the owned
  RPC callable (the conceptual `Server.rpc` seam of `tools/codex-worker.py`)
  and the explicit typed-rejection exception class (or tuple). Every other
  raised exception is ambiguous and stays uncertain. `SystemExit` and
  `KeyboardInterrupt` propagate like a host crash.
- `bind(session)` binds exactly one core lead session; `status()` is a
  read-only view. Construction, bind, status and refused core
  authority/ownership make zero RPC calls. The bridge infers no human
  authority from CLI or role; the core's authority/ownership callbacks
  remain the only admission path.
- The pinned requested model/effort must match the session record at bind
  time; the requested effort is sent explicitly with every `turn/start`
  (`{'threadId', 'effort', 'input': [{'type': 'text', 'text'}]}`).
  Requested config is never effective proof: `effective` stays `Unknown`.

## Frozen transport contract

- A core-approved `send_turn` makes exactly ONE `turn/start` for the bound
  thread and text: no retries, resends, automatic resume, extra RPCs or paid
  fallback. A valid acknowledgement (`{'turn': {'id': <bounded>}}`, not for
  a foreign thread) binds the returned provider turn id to the exact local
  session/generation/turn from the facts.
- Wrong, malformed, foreign-thread or lost acknowledgements and untyped RPC
  failures return `uncertain` — never rejection or success. An explicit
  typed RPC rejection returns `rejected`; the core reconciles it against
  matching activity and may preserve uncertainty.
- Supported notifications: `turn/started`, `item/agentMessage/delta`,
  `item/commandExecution/outputDelta`, `turn/completed`. Every event must
  match the bound thread AND the exact provider turn validated by an
  acknowledgement. Only bounded selected delta text (16 KiB per event) and
  lifecycle fields enter the core — never raw envelopes, credentials,
  account ids or arbitrary event dictionaries. `completed`/`failed`/
  `interrupted` map to terminal turn facts with `exit_code=None`: a turn
  completing is NOT Source/adapter/process exit or accepted delivery.
- Same-thread notifications arriving during the synchronous RPC before its
  reply are held in a bounded event/byte buffer and replayed in order only
  after a valid correlated acknowledgement. Early same-thread events never
  prove which local turn they belong to; the first observed provider id is
  never adopted. Stale, foreign, duplicate and unsupported events cannot
  terminate another turn or impersonate complete history. Attributed events
  for an already validated turn are delivered live, including while a new
  submission is in flight.
- `handle_notification` returns a controlled result
  (`ignored`/`buffered`/`dropped`/`observed`/`refused`) and never raises.
  A core refusal — including a saved terminal fact plus a journal-write
  error (`terminal saved; output ...`) — is retained verbatim in the
  result and is never converted into proof of process exit or delivery.

## Explicit gap limitation

On event-buffer overflow or an oversized delta the bridge preserves an
explicit gap instead of inventing complete output. The core has no public
gap marker, so the bridge records exactly one honest lifecycle fact
(`bridge_output_gap`, with a cause detail) for the bound turn and reports
`gap`/`gap_recorded` in its status. If the core cannot record the gap (for
example a closed archive), the limitation stays visible in the status; the
bridge never fakes an archive-limit marker of a different kind and never
silently claims complete history.

## Unsupported in this slice

- Reopening/rebinding never recovers an unproven provider-turn mapping and
  never resends pending work. After owner or connection loss,
  reconciliation is unsupported/Unknown until the future native owner
  proves it. No persistent provider-id schema was added to the core.
- No process launch, connection initialization, thread
  start/resume/fork/adopt, UI, task database, scheduler, terminal emulator,
  network/auth API or sidecar persistence. Existing single-turn worker
  behavior (`tools/codex-worker.py`) is byte-identical and untouched.
- Native admission, the lead reservation, slot release, cooldown and retry
  decisions remain with the future native caller; the bridge never claims
  the registered lead and counts as no workflow by itself.

## Verification

`python3 -B tests/unio-managed-lead-codex.py` exercises, with a
deterministic fake owned connection and zero real providers: two completed
turns on one connection with exact correlations; idempotent owner replay
with no extra RPC; refused authority/ownership, changed request and active
pending with zero calls; explicit typed rejection (with early events
discarded); timeout/lost/malformed/wrong-thread acknowledgements; early
matching and foreign events around the synchronous call; wrong/stale/
duplicate turns; oversized delta and early-buffer overflow with explicit
gaps; failed/interrupted terminals with `exit_code=None`; unknown mapping
after reopen; core output-write errors including a saved terminal fact
plus journal-write error; and proof that every owned RPC call is exactly
one `turn/start` with no thread/process lifecycle RPC. State and RPC call
counts are asserted outside the notification callbacks. The suite is
registered in `tools/quality-check.sh` beside the managed lead core suite.
