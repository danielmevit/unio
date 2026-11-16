0533-EXISTING-SESSION-ATTACH: first experimental connection to the CURRENT RUNNING
shared Codex daemon, enabling adaptive LOW/XHIGH effort on an existing valuable
conversation without restarting, forking, replaying or summarizing it. New
`unio lead-session attach` controls (`inspect`, `attach`, `phase`, `auto`,
`status`, `detach`) in the existing lead-session CLI; the owned
`start`/`run` behaviour, records and codec are unchanged byte-for-byte.

Transport is the diagnosed, source-proven control path of codex-cli 0.169.0:
`codex app-server proxy` is a raw stdio-to-unix-socket byte pump
(`codex-rs/stdio-to-uds/src/lib.rs`) and the daemon's control socket accepts
only a websocket upgrade over that stream
(`app-server-transport/src/transport/unix_socket.rs`, one JSON-RPC message
per websocket TEXT frame in `websocket.rs`). Plain newline JSON — what an
earlier read-only probe sent for 12 seconds — never completes the websocket
handshake and stays unanswered; those failed probe receipts are preserved
alongside the working ones. The connector implements the minimal RFC 6455
client over its own proxy child only: HTTP upgrade verification, masked
frames out, unmasked frames in with ping/pong and fragment reassembly,
bounded reads/writes/time/messages, and it closes ONLY that proxy process
group. The daemon, its other clients and the owner TUI are never started,
restarted, updated, stopped or signalled.

Proven live on 2026-11-16 with bounded zero-inference probes on the existing
daemon: HTTP 101 upgrade accepted, `initialize` answered, and
`thread/loaded/list` returned the loaded-thread count. Zero model calls, zero
turn starts, zero `thread/resume`, zero account or auth reads, zero config
writes; no thread ids appear in any receipt.

Guarantees of the slice: read-only `inspect` reports loaded-ness, status and
control capability and never resumes or creates a thread; explicit `attach`
runs native admission first (STOP, off holds, configured registered lead,
account-group mapping, tier slot counting that counts the lead exactly once,
owned lead lease), refuses duplicates, a second concurrent attached thread
and an unstopped managed owned lead, and requires the EXACT thread id
acknowledged IDLE; `phase` is the explicit cooperating-lead signal
(coordination is low, planning/review are exactly the persisted ceiling,
an explicit effort within that ceiling wins), never relabels a running
turn (pending is shown separately), validates that the thread's own model
advertises the level, and detects native manual changes by comparing the
fresh reading with the record's anchors — a native manual change suspends
AUTO, is never overwritten blindly, and the suspension persists across
commands with no setter and no pending automatic write until the explicit
`attach auto` re-enables (or the owner applies the concrete `attach manual
--effort low|xhigh` override, which pins automatic selection). The only
control RPC is
`thread/settings/update` with EXACTLY `threadId`+`effort` (never model,
service tier, permissions, sandbox or cwd), it applies to future turns only,
a typed rejection is `unavailable` (exit 5) and a timed-out acknowledgement
is `uncertain` (exit 6), preserved and never retried blindly; the effective
provider effort stays Unknown and the owner TUI keeps full manual control
with its manual turns never claimed as Unio-admitted. Attach state is
strictly additive and separate under `coord/lead-session-attach/` and never
rewrites the managed owned records.

Regression coverage: `tests/unio-lead-session-attach.py` drives the production
CLI against an executable fake `codex app-server proxy` implementing the real
websocket transport (handshake, masked framing, read bounds, loaded-list,
exact-id thread/read with `includeTurns: false`, settings ok/reject/silence,
persisted native effort): 53 checks covering framing and bound refusals,
same-id idle attach, active/not-loaded/systemError/foreign refusals, STOP, off
hold, lead mismatch, capacity, busy lease, active managed owner, duplicate
and second-thread attachment, phase kind mapping, suspension persistence
across commands, the explicit owner manual pin, persisted-ceiling binding,
manual precedence with explicit re-enable, pending-under-active-turn,
advertisement honesty (including the optional initial attach effort), typed
rejection and uncertain acknowledgement with authority-not-delivery
re-enable, durable byte-identical attempt receipts across
auto/success/detach/re-attach, crash-aware recording refusal and dangling
intent resolution, status/display truthfulness, detach/re-attach, wire safety
(only permitted RPCs; settings params exactly threadId+effort), state
permissions and the never-touched daemon. Registered in the quality-gate
catalogue as `test-unio-lead-session-attach` (managed-lead lane, explicitly
added after the 125-command baseline); the runner self-test expectation
covers the two explicitly added self-tests and the baseline snapshot and
lane structure are unchanged. Installer embedding updated for
`tools/lead-session-attach.py`.

Correction of three confirmed control-state defects (bounded fix, same
slice; prior guarantees unchanged): (1) persistent manual precedence — a
suspension used to be recorded (`auto=false`) but never checked, so a second
`--kind review` still sent `thread/settings/update xhigh`; a suspended
automatic phase now stays suspended across commands with NO setter and NO
pending automatic write until the owner re-enables with `attach auto`, and a
new explicit owner `attach manual --effort low|xhigh` override applies a
concrete level while pinning automatic phase selection (the stored boolean
is not called enforcement — the refusing gate is). (2) the stored ceiling
now actually binds: automatic planning/review resolve from the validated
persisted record ceiling (previously a nonexistent per-command flag made
`--ceiling low` silently resolve to xhigh), an explicit phase request above
the ceiling refuses instead of silently exceeding the promised bound, the
optional initial `attach --effort` is advertisement-checked too, and only
the reported (never silent) owner manual override may go above it. (3)
original attempts are preserved: every settings attempt now writes a
crash-aware two-line receipt to the thread's append-only bounded attempt
journal (intent persisted BEFORE the mutating RPC — a recording failure is
a refusal with zero settings calls — and the actual
acknowledged/rejected/Unknown outcome afterward); `attach auto` acknowledges
the owner's AUTHORITY to continue, never delivery: the single stored
uncertain acknowledgement is no longer rewritten to
acknowledged-by-owner (an `owner_acknowledged` timestamp is kept separately),
an unresolved Unknown never becomes a successful delivery, and a dangling
intent from an interrupted run blocks updates until the explicit owner
resolution. Record schema is additively versioned (v1 prototype records
load unchanged and gain neutral defaults on their next save); owned legacy
records are untouched.

Second correction: four fake-reproduced existing-session control defects
(bounded fix, same slice; prior guarantees unchanged; every new check was
proven to FAIL on the previous dd570c0 code for the reproduced cause):
(1) the initial `attach attach --effort` now persists the FRESH post-apply
native anchor — the record is saved AFTER the post-apply reread, exactly like
phase/manual do (previously the disk anchor kept the stale pre-apply value, so
a later native manual change back to the pre-attach level could be missed);
a failed post-apply reread persists an explicitly Unknown anchor instead of a
knowingly stale pre-apply effort, the acknowledged delivery fact never
changes, the immutable original attempt receipts stay untouched, and
subsequent manual changes are re-checked against the fresh anchor. (2) a
queued pending choice (recorded while the turn was running) is now CONSUMED
by the later explicit idle `phase` command when it carries no explicit
`--kind`/`--effort` — an explicit new choice intentionally wins, the queue is
never silently replaced by the coordination default (previously the idle
default low applied and cleared the queue) and never dropped at a
still-active boundary; the consume revalidates the persisted ceiling, manual
pin/suspension, admission and the thread's model advertisement at the apply
boundary, and pending stays separate from the current requested level.
(3) read-only local behaviour is now actually read-only: `inspect`/`status`
and every pre-record refusal never create, chmod or write
`coord/lead-session-attach/` — absent state stays absent (also under an active
STOP), existing metadata and modes are unchanged by read commands, and a
present but non-private store refuses reads instead of silently repairing
them; only mutating writes create the private 0700/0600 store, failing closed
on unsafe paths and recording failures. (4) the transport selection
(`codex_binary`, `sock`) persisted at attach is now HONOURED by every later
record-bound control (`phase`, `manual`): omitted flags re-use the attached
endpoint instead of silently defaulting to a possibly different local
daemon/client, and an explicit conflicting endpoint refuses with zero setter
calls until the deliberate detach/re-attach; no daemon, fork or fallback
service is ever started and no history is touched; the saved selection is a
name, never an identity proof — the implicit PATH `codex` default is resolved
per command, the native CLI keeps updating normally (no binary-hash or
version allowlist), and continuity of an implicit default across
installations cannot be established (qualified in the docs). `inspect` keeps
free transport flags as the pre-attach exploration command.

Documentation in the same component follows the CopilotFree AutoBalance
CURRENTFLAGS text audit (two independent documentation observations): the CLI
synopsis now lists every attach subcommand with usable command forms, actual
accepted flags and defaults (including `attach attach --ceiling` default
xhigh) and explains the nested `attach attach` initial-attachment name
instead of hiding it, and the future-turn explicit-phase slice stays
documented as distinct from full AUTO scheduling and mid-turn control.

Regression coverage grows inside the registered suite
(`tests/unio-lead-session-attach.py`, quality-gate entry
`test-unio-lead-session-attach`): fresh fake-proxy checks cover the fresh
post-apply anchor and the subsequent manual-change detection, honest
Unknown anchoring on a failed post-apply reread, queue consumption with
explicit-wins, ceiling revalidation and suspended blocking, absent-store
purity and unchanged metadata/modes for `inspect`/`status` (including STOP),
and the persisted transport selection end to end — the fake proxy records
its own argv, omitted later flags provably cannot run a default real `codex`,
and an explicit conflicting control makes zero `thread/settings/update` calls
on both endpoints. The checks fail on dd570c0 for exactly those causes.
Validation was fake-only: zero real Codex/test-provider calls, zero real
model calls and zero billing inside this correction's validation (the worker
assignment itself is ONE Mistral implementer invocation, stated truthfully in
the delivery report); the installer embedding was regenerated for the
connector, CLI and doc changes, and the quality-gate catalogue, baselines and
lanes are unchanged.

Follow-ups (not claimed): continuous manual-change monitoring while
disconnected, full hands-free per-turn phase classification, worker watching,
and consented live probes of `thread/settings/update` acceptance against a real
loaded thread are open; runtime acceptance of the settings update on a real
shared thread is still Unknown until the owner exercises it.

Third correction: the three fake-reproduced record-boundary defects
(bounded fix, same slice; prior guarantees unchanged; every affected
behaviour was re-reproduced on the previous 28d8550 code before fixing,
fake-only, zero real threads):

(1) journal capacity is reserved for BOTH receipt lines BEFORE the
mutating RPC. A valid 255-entry journal (127 complete attempt pairs
plus an owner-resolution) used to admit the intent line, send
`thread/settings/update`, and then refuse the truthful result receipt
with the false claim that 'no settings call is made'. The connector now
verifies durable room for the intent AND its bounded worst-case
serialized result line - entry count for both lines and byte headroom
covering the full JSON-escaped, multibyte-capable error text - BEFORE
the intent is persisted or the setter is sent, so every
capacity-bound refusal is truthfully zero-call, with no truncation,
deletion or rotation of old receipts. A journal with room for exactly
one two-line attempt still admits it (both receipts land) and the next
attempt then refuses up front. Should a result receipt nevertheless
fail after the request crossed the wire, the failure is reported
truthfully as AFTER the request with the attempt outcome Unknown and
the intent left visibly dangling - never claimed as zero calls.

(2) persisted state binds to the exact request. A valid-shaped record
for thread B copied into thread A's hashed filename used to make
`attach phase --thread-id A` send settings for thread B. Loading now
verifies the stored own thread id against the requested id AND the
stored own workspace against the current canonical workspace, the
record listing verifies filename/content binding and workspace, and
journal entries must belong to the requested thread rather than merely
be structurally valid. Wrong-id, wrong-workspace, misnamed-record and
foreign-journal cases all refuse BEFORE any mutating RPC with zero
setter calls, never select another record or endpoint, and are never
'repaired' by copying, rewriting or deleting evidence; the genuine
additive v1 prototype record migration for the exact same thread and
workspace keeps working.

(3) provider errors are bounded to valid UTF-8 BYTES. Character-count
truncation previously let a 256-Chinese-character typed rejection
(768 UTF-8 bytes) bust the 256-byte receipt bound, so the app lost the
unavailable result and raised 'invalid journal entry' instead. The
error receipt is now truncated at a UTF-8 character boundary within
the byte bound (JSON-escaped characters covered by the reservation
math), the unavailable/uncertain classification is retained - a
bounded rejection never becomes invented success - and the journal
reloads cleanly after multibyte and escaping-heavy rejections.

Same-endpoint contract polish: a proxy EOF is now diagnosed by its
ACTUAL stage (Gemini's LOW follow-up) - an exit before the websocket
handshake completed is reported as an unreachable transport, a close
after the completed handshake as a mid-RPC daemon disconnect - with
both stages fake-tested; and explicitness of `--codex-binary` is
decided by whether the flag was given (parser default None), so an
explicit `--codex-binary codex` refuses against a saved custom
endpoint instead of being silently absorbed, while omitted flags keep
the attached endpoint and the native CLI keeps updating normally (no
binary-hash or version guard).

Regression coverage grows inside the registered suite
(`tests/unio-lead-session-attach.py`, quality-gate entry
`test-unio-lead-session-attach`): 73 checks now cover both
capacity-bound refusal stages (entries and bytes, byte-identical
journals), the exact-one-attempt boundary, the post-request receipt
failure truth wording, the multibyte and JSON-escaped rejection
receipts, wrong-id/wrong-workspace/misnamed/foreign refusals with
zero setter calls, the deliberate-restore resume, the legacy migration
and both EOF stages. The new checks were verified to fail on the
28d8550 code for exactly the reproduced causes; validation was
fake-only (zero real Codex/daemon/model calls), and the installer
embedding was regenerated for the updated connector and CLI.
