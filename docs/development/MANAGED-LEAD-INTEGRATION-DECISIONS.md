# Managed lead integration decisions

Lead assessment 2026-10-24T02:23:02+02:00; design guidance, not installed functionality.
The Mistral subscription/Vibe2.26.1/GLM5.3/HIGH proposal is supporting
analysis. Its original native verification failed because the lead requested a
commit in a report-only task. Both scope and document checks passed. Preserve
that failed contract; local fixed-command artifact validation is separate from
model delivery and semantic acceptance. No new AI call is used to revalidate it.

## Decisions before implementation

- Keep real account grouping. The proposal's example unio lead codexmanaged
  is unsafe to copy here without an explicit correct account mapping:
  group_of returns accounts.get(agent, agent), and codexmanaged is currently
  unmapped. Prefer the existing codex identity with an explicitly selected
  supported managed backend, or require verified same-account configuration.
  A new alias must not create apparently independent subscription capacity.
- Use an accepted private commit as the frozen dependency. The backend does
  not need a separate published release before native integration. Publication
  is the final owner-authorized step, avoiding a circular release dependency.
- The backend validates local session/generation/turn identities. It does not
  yet bind provider thread/turn IDs. The owned transport must establish and
  preserve those correlations, including acknowledgements and early events.
  Generated protocol schemas establish fields, not runtime behavior guarantees.
- Claim the registered lead exactly once under the existing admission lock;
  refuse a second owned claim before effects. Preserve grants for workers,
  owner holds, actual mappings and Unknown unmanaged/cross-workspace activity.
  Registration/alias/group changes while claimed need explicit tested refusal
  or coordinated owner transition; a slot must never become an uncounted lead.
- A CLI invocation is not proof of a human operator. Require explicit owner
  enablement/start authority and the native ownership chain; do not infer
  consent from a role label. Retain the trusted-host/same-user limitation.
- STOP blocks a new lead start and a deliberate new turn. Active-turn steering
  remains under its existing contract. No automatic resume, uncertain resend,
  thread adoption or paid fallback. Clearly distinguish a confirmed turn end,
  a live process, delivery, checks and acceptance.
- Preserve existing closed JSON schemas. Do not add the proposed lead_reservation
  field to an unchanged strict policy schema. Put new detail in the new lead
  status endpoint or a deliberately versioned opt-in projection; update all
  relevant consumers/tests. Existing receipt/report readers remain compatible.
- Freeze an approved lead checkout/branch, not an unconditional public-main cwd.
  Reuse the owned supervisor/process identity and control channel. Status and
  output are local reads; a disconnected observer must not launch a replacement.

## Smallest useful implementation sequence

1. Owned Codex transport binding: reuse the existing RPC seam, with exact
   thread/turn correlation and deterministic fake tests. No new process or UI.
2. Native lead claim and persistent Source: explicit start/stop/next-turn,
   one real lead count, STOP/grants/ownership and original cleanup. Preserve
   the existing single-turn worker route and package the accepted backend.
3. Public CLI/docs and complete gate, then isolated real supported-route trial
   when authorized and capacity permits. Installation/publication stay separate.

Initial estimate remains2–4working days for one complete supported route;
transport roughly1–2focused hours, native ownership roughly1–2working days,
with meaningful checks/review and uncertainty included. The proposal's estimate
in sessions is not an elapsed-time estimate or a promise of faster delivery.
No new task DB, IDE, terminal emulator, scheduler or Windows process layer is
needed for this first route. Windows follows; macOS remains after Windows.

Before implementing, refreeze corrected accepted backend source and its error
contract: a terminal fact may be saved even when its journal reports failure.
Preserve output gaps and distinguish corruption/write failure from archive cap.
Bounded request history needs an explicit owner handoff on exhaustion; do not
silently evict request IDs. Full-journal parsing cost is still an optimization
backlog, not a measured performance improvement.

The original proposal's phrase no provider called means the worker launched no
additional provider: there was one actual Mistral/Vibe model invocation. Requested
model/effort and catalog labels do not prove effective serving identity.

## Extend the existing dashboard — 2026-10-24T22:38:53+02:00

The user-facing goal is one project view containing both the managed lead
session and the existing workers. Extend bridge/ and its local API; do not build
a replacement dashboard or a second orchestration interface. This is the planned
UX direction, not a claim that UI integration has shipped.

- Add a lead entry showing the project/session, requested route and settings,
  recorded turn state, latest selected output and timestamps. Uncertain state,
  missing output and effective Unknown remain visible. A completed turn is not
  task acceptance. Reuse existing activity/detail patterns where practical.
- The browser talks to Unio's local backend. The backend checks the exact owned
  session, authority and policy before sending supported input to the provider
  connection. Never expose a direct provider RPC channel or credentials in the
  browser. Existing worker/task/review views keep their canonical records.
- Build read-only lead visibility first, then supported next-message, steering
  and stop controls. CLI and browser must address the same managed session, with
  no second model conversation, implicit adoption or duplicate launch. Ordinary
  separately started CLIs are not automatically attached. Start with the tested
  Codex route; support for another lead route requires its own evidence.
- The browser is a client of the owned backend process. Opening/reloading a tab
  must not launch a replacement, and closing a tab must not silently stop the
  lead. Define backend lifetime explicitly when implementing the supervisor.
- Native ownership/policy and persistent launch/control come before dashboard
  edits. The current ownership worker has no bridge/ or site/ scope. Phone
  pairing and remote session control follow later; no whole-PC remote desktop
  or new desktop shell is required for this stage.
