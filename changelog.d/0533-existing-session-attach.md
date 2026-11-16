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
(coordination is low, planning/review the ceiling, explicit effort wins),
never relabels a running turn (pending is shown separately), validates that
the thread's own model advertises the level, and detects native manual
changes by comparing the fresh reading with the record's anchors — a native
manual change suspends AUTO and is never overwritten blindly; only explicit
`attach auto` re-enables. The only control RPC is
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
persisted native effort): 39 checks covering framing and bound refusals,
same-id idle attach, active/not-loaded/systemError/foreign refusals, STOP, off
hold, lead mismatch, capacity, busy lease, active managed owner, duplicate
and second-thread attachment, phase kind mapping, manual precedence with
explicit re-enable, pending-under-active-turn, advertisement honesty, typed
rejection and uncertain acknowledgement with re-enable, status/display
truthfulness, detach/re-attach, wire safety (only permitted RPCs; settings
params exactly threadId+effort), state permissions and the never-touched
daemon. Registered in the quality-gate catalogue as
`test-unio-lead-session-attach` (managed-lead lane, explicitly added after the
125-command baseline); the runner self-test expectation covers the two
explicitly added self-tests and the baseline snapshot and lane structure are
unchanged. Installer embedding updated for `tools/lead-session-attach.py`.

Follow-ups (not claimed): continuous manual-change monitoring while
disconnected, full hands-free per-turn phase classification, worker watching,
and consented live probes of `thread/settings/update` acceptance against a real
loaded thread are open; runtime acceptance of the settings update on a real
shared thread is still Unknown until the owner exercises it.
