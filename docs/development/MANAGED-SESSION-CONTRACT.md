# Managed sessions — proposed/unreleased 0.5.23 first CLI slice

Status: frozen implementation contract, 2026-10-19. This is planned behavior,
not shipped in the installed 0.5.22 release.

## Useful outcome

An owner can inspect one Unio-owned Codex Source, reconnect to its recorded
output and send a deliberate message to its currently active turn. Build on
`tools/codex-worker.py` and the existing native admission/worker-effort channel.
This slice uses the supported Codex app-server interface. A terminal emulator,
persistent idle conversation, arbitrary existing CLI attachment, dashboard
controls, cooldown restart and phone pairing are later slices.

## CLI contract

- `unio session status WORKER [--json]`: inspect local owned-session state,
  selected task/model/effort and output cursor, without a provider call.
- `unio session output WORKER [--after N] [--limit N] [--json]`: retrieve bounded,
  ordered recorded output from that session. Return the session identity and
  next cursor so reconnecting does not repeat or silently omit output. Default
  limit 100, maximum 500 records. Invalid bounds refuse.
- `unio session send WORKER --file PATH --request-id ID [--json]`: send at most
  8 KiB of nonempty UTF-8 text to the exact active owned turn via `turn/steer`.
  Request IDs are bounded portable labels. A repeated identical request returns
  its recorded result without another provider RPC; changed content for that
  ID refuses. A failed/uncertain transport is not silently replayed. Reading
  status/output never starts or resumes an agent.

Require exact supported arguments; shell evaluation, arbitrary thread IDs,
model/permission changes, automatic next turns and alternate paid routes are
outside the interface. Unsupported legacy exec/other routes report unsupported.
A completed Source permits historical status/output but never new input.

## Ownership, lifecycle and evidence

Keep one existing native run/task/worktree/account slot. No second CLI, task
retry or new turn is created by observation or steering. Existing STOP meaning
is preserved: it closes new admissions, not the already-authorized Source's
control channel. Describe the trusted-host/same-user boundary honestly.

Keep a stable private per-run session ID, bounded append-only useful output and
terminal outcome under `coord/sessions/`. Expose only selected agent messages,
command output and lifecycle facts, not raw credentials, account IDs or full
provider RPC envelopes. Mark source exit, configured/requested effort and
Unknown effective inference separately. Session records survive normal failure
and completion; observation of completed records is read-only and works under
STOP. An old session is never presented as a live replacement run.

Validate file types, ownership and live native identity before control. Refuse
stale/replaced channels, unsafe paths and wrong-session input before effects.
A supplied session identity must remain bound through reconnect. Output bounds
must report a gap/truncation explicitly rather than pretending completeness.
Private socket ownership and native task binding remain enforced. Owner output
may contain private project text and must not be published with research data.

Preserve real nonzero Source exits and owned-child cleanup on failure,
cancellation and timeout. Do not signal a reaped process group's recycled numeric
ID. No browser/UI/brand/site redesign or new exposed network listener.

## Verification and delivery

Use deterministic fake-app-server tests for actual native launch/control/output,
active-turn steering, duplicate input, completion/failure and stale channels.
Legacy worker-effort tests must remain valid. Package the helper, docs and help
reproducibly in the standalone installer; register meaningful new checks in the
quality gate. No live model calls from offline tests.

Implementation success, native checks, two independent current-code reviews
from different AI labs and lead acceptance are separate. Do not call this full
managed-session milestone completion. Follow with explicit multi-turn ownership,
then existing-dashboard integration and lead continuity.

Official interface reference reviewed 2026-10-19:
https://learn.chatgpt.com/docs/app-server#lifecycle-overview
