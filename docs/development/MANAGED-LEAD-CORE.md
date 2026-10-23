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
