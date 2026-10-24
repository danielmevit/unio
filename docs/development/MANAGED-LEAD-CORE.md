# Managed lead-session core — backend component contract

Status: first backend slice, 2026-10-24. `tools/managed-lead.py` is an
importable state/controller component for persistent multi-turn lead
sessions. It is NOT installed lead continuity: there is no public `unio`
command, no provider launcher and no native integration in this slice.
The later native caller owns admission, the lead reservation and the
owned transport.

## What this component enforces

- One private lead session record per opaque `lead-<hex>` identity under
  `coord/sessions/` (`<id>.json` state, `<id>.jsonl` output journal,
  `<id>.lock` state lock). The role is explicitly `lead`; worker-role or
  malformed records refuse to open.
- Distinct states: `idle`, `pending` (intent reserved, transport outcome
  not established), `running`, `outcome_unknown` (ambiguous transport,
  never replayed) and `terminal` (history-only; permits the next authorized
  owner turn). A terminal record preserves failures and partial state and
  is not proof of task delivery, passing checks, a successful process or
  human acceptance.
- Monotonic generation: each terminal turn advances it; every effect
  requires the exact current session id and generation.
- Bounded next-turn input: nonempty UTF-8 text, no NUL, at most 8192
  bytes. Request IDs are bounded portable labels.
- Before any transport call the controller requires, in order: valid
  input shape, exact session binding, an open state (`idle`/`terminal`),
  the exact generation, a positive injected authority whose role is
  `lead`, current injected ownership, and free request-history capacity.
  Worker-role or missing authority and missing ownership refuse before
  transport.
- Idempotent request IDs: intent is reserved durably (fsynced state
  write) BEFORE the transport call. Replaying the same ID with the same
  content returns the recorded result with no new call; changed content
  refuses. A transport crash, raise or invalid reply leaves the request
  `pending`/`outcome_unknown` and it is never replayed or resent. Request
  storage is bounded (`max_requests`, 1–256, fixed at creation); on
  exhaustion new IDs refuse and recorded IDs are never evicted.
- Provider observations (`observe_turn_started`, `observe_terminal`,
  `observe_owner`, `observe_output`) are accepted only for the matching
  recorded session/generation/turn. Reopen never creates a provider
  turn and never auto-resumes: pending work stays explicitly uncertain
  until an authorized matching reconciliation observation. The
  constructor and all reads make zero transport/model calls.
- Bounded output journal: append-only records with monotonic cursors;
  only selected `agent_message`/`command_output` deltas and whitelisted
  lifecycle facts are stored — never full provider envelopes,
  credentials or account IDs. Bounds: 64 KiB per record, 1 MiB archive
  (then an `archive_limit` marker closes it), 256 KiB / 500 records per
  read page (default 100). Reading stops at the first corrupt, torn,
  out-of-order or oversized record and reports `gap`/`truncated`
  explicitly; it never skips corruption.
- State defense: path traversal and symlinked components refuse, files
  must be regular, owned, hard-linked once and mode 0600, and state
  content is strictly validated with a 512 KiB bound. Malformed or
  oversized state refuses; it is never silently reset.

## Injected narrow interfaces

The caller injects three callables; the component adds no process,
platform or network logic of its own (file locking uses `fcntl` where
available and refuses where not).

- `transport`: object with `send_turn(facts)` (or a plain callable).
  `facts` is `{'session_id', 'generation', 'turn_id', 'text'}` — no
  credentials. A reply `{'status': 'accepted'|'rejected'|'uncertain'}`
  is recorded once; anything else, or a raised `Exception`, is
  `uncertain`. `SystemExit`/`KeyboardInterrupt` propagate like a host
  crash and leave the reserved intent pending.
- `authority(facts) -> {'role': 'lead', 'authorized': True}`: anything
  else, including a raised exception, refuses before transport.
- `ownership(facts) -> True`: anything else refuses before transport.

## What the future native caller must own

- Native admission and the already-authorized lead reservation: this
  component never acquires, holds or releases native account slots and
  must be counted as exactly one registered lead workflow, never more.
- Real account mappings, owner grants and STOP semantics (STOP blocks
  new admissions; it does not rewrite recorded history).
- Slot release on terminal outcomes, cooldown policy and any retry
  decision: this component never auto-resumes and never replays.
- The owned transport implementation and process/platform backends
  (POSIX process launch, native Windows/macOS) — deliberately absent here.
- Passing the exact session id and current generation to every owner
  request, and reconciling `pending`/`outcome_unknown` sessions only
  through authorized matching observations.

## Boundary honesty

Trusted-host, same-user controls: private files and an advisory state
lock protect against accidents and stale callers, not against a hostile
local user. This component does not provide operating-system isolation,
does not prove provider-side delivery beyond recorded observations, and
does not by itself deliver the managed lead-continuity milestone.

## Verification

`python3 -B tests/unio-managed-lead.py` exercises, with a deterministic
fake transport and zero provider calls: multiple completed turns,
duplicate and changed request IDs, concurrent submissions from two
controller instances, ambiguous send then reopen with zero replay,
crash-pending reopen and reconciliation, wrong-role/authority/ownership/
generation refusals, mismatched terminal events, bounded output with
explicit gaps, archive exhaustion, malformed/unsafe/oversized state and
request-history exhaustion. Tests import `tools/managed-lead.py`
directly.

## Persistence correction — 2026-10-24

The first Vibe backend Source reproduced four defects: a missing journal prefix
looked complete, a JSON array journal record raised AttributeError, persisted
identity was not bound to the controller filename, and a predictable temporary
hardlink could be truncated before a transport call. That Source and its commits
remain historical evidence, not acceptance.

Reads now compare the validated contiguous journal prefix and byte count with
recorded metadata; missing, extra, torn or malformed records report a gap and
truncation (unsafe files refuse). Reads never repair or replay. Appends first
validate that agreement, so a later observation cannot conceal disagreement.
This adds a bounded full-journal scan per append: filling an archive with n
records parses O(n²) records in total, under the session lock, as well as
repeating I/O. Request identity membership is precomputed once per scan,
removing the per-record linear request search. No throughput improvement has
been measured. A validated-prefix cache is deferred because invalidation must
still detect truncation, replacement and in-place corruption; this correction
retains complete detection rather than introducing a cache trust assumption.
Persisted identity and turn/request/generation/result relationships are checked
on every state load, and malformed Unicode refuses in a controlled way.

State replacement uses an unpredictable exclusive mode-0600 temporary file,
fsync and atomic replacement, without opening predictable stale temporary paths.
Existing unsafe state targets refuse, including hardlinks, symlinks and FIFOs.
Persistence failures before durable intent completion make zero transport calls;
a failure after replacement may leave pending intent, which remains uncertain
and is never automatically resent. Directory fsync errors are no longer ignored.
These defenses remain trusted-host, same-user controls, not isolation against a
hostile same-user process or public observer authorization. Native admission,
account slots, STOP, provider launching and effective model/effort verification
remain outside this backend; effective settings stay Unknown.


## Independent-review corrections — 2026-10-24

The private internal state requires every schema key, including nullable keys,
with nested turn/request/result/history relationships validated on load and
before replacement. This unpublished schema adds `journal_error`; it does not
change worker session records or external receipt/report formats. Existing
private managed-lead records missing required keys refuse rather than migrate.
External exit codes and lifecycle integers must be signed 32-bit values;
invalid types, Unicode and huge integers refuse before serialization. Directory,
journal read/write and lock errors become controlled refusals (status reports
`journal_status: Unknown` if its journal cannot be inspected).

A send reply is reconciled with observations already received outside the lock.
Rejection after a proven start or terminal observation records an `uncertain`
request result (`outcome_unknown` request state), preserving the running turn's
accepted delivery or the terminal fact, exit code and generation. A running
turn stays active until a matching terminal observation. Accepted/uncertain
replies also preserve those facts. Reopening or resubmitting the same request
never replays the call or overwrites its recorded result.

Archive writers reserve 512 bytes of headroom for the complete final marker;
the marker itself is checked against the reader's real archive bound. Status
keeps `archive_limited` for an actual successfully appended archive-limit marker.
`journal_status` distinguishes `ok`, `archive_limit`, `journal_disagreement`,
`journal_write_failed` and `Unknown`; `journal_error` retains a lifecycle
persistence failure independently. Output reads add `disagreement` to distinguish
corruption/metadata mismatch from the intentional gap of a complete cap marker.

Journal append/fsync and state replacement are separate durable operations.
A crash or failed state save after an append leaves the original journal ahead
of the persisted cursor/byte count. Reopen/status reports disagreement, output
reads expose the gap, and appends refuse without changing the original bytes.
No automatic rollback, truncation, replay, cursor advancement or history repair
is attempted. A later matching terminal observation can still save the terminal
failure and original exit code in state: it records `journal_error` and raises
an explicit refusal (`terminal saved; output ...`) rather than reporting a
successful journal write. A terminal observation whose state save itself fails
remains uncommitted; the failure propagates. An fsync error after replacement
may already have replaced the state but still refuses because durability is
unconfirmed. Partial writes are preserved and also surface as disagreement.

Explicit owner recovery for these windows (auditing the extra bytes, establishing
which observations are authoritative, then rebuilding a consistent journal and
state) remains unsupported. Lifecycle write errors remain recorded and close
further appends; there is no public repair or error-clearing operation. These
limitations are separate from normal archive exhaustion and native turn recovery.
The regression suite injects failure between append and replacement for output,
terminal and owner events, checks reopen/status/output and terminal failure
preservation, deletes every required state/nested key, covers reply/observation
orderings, directly tests replacement destination defenses, and isolates the
unsafe FIFO lock probe in a subprocess with a five-second timeout.
