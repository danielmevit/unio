# Continuous delegation — first bounded batch contract

Frozen for the first 0.5.21 implementation on 2026-10-16. This is a contract,
not a claim of shipped behavior. Reuse the current planner, dispatcher,
ExecutionService and native admission. No UI, site or brand changes.

## Useful first outcome

An owner approves a finite batch of exact existing jobs. Unio starts disjoint
ready jobs on eligible account groups and keeps checking for unstarted jobs as
slots become free. A long-running worker does not require the lead to stop
other independent work. Explain waiting, failed and uncertain jobs plainly.

This first slice schedules existing prepared/approved browser jobs through
`unio dispatch`; it does not invent another native launcher. Owner integration
and dependent approvals remain explicit. A frozen batch does not authorize new
instructions, an updated base, new jobs, automatic acceptance or merge.

## Commands

Provide `unio schedule create --grant PATH`, `run ID`, `status [ID]`, `pause ID`,
`resume ID` and `stop ID`; support `--json`, `--project` and offline help.
`run ID --once` performs one bounded scheduling pass; ordinary `run ID` polls
within the grant's expiry and bounded foreground run duration. No automatic
startup daemon, provider probing or replay. Explain how an owner can run it in
the background using their shell and observe status from another terminal.

Pause and stop prevent further launch attempts; they do not kill native
workers already launched. Resume never renews a grant, resets its attempt
budget or retries failed/unknown jobs. Stop is terminal for that batch. STOP,
expiry and a changed base prevent new calls; status remains usable offline.

## Explicit owner grant

Freeze a strict UTF-8 schema-1 JSON grant, at most 128 KiB, with exactly:
`schema_version`, `project`, `inventory`, `inventory_sha256`, `expires_at`,
`max_launches`, `poll_seconds`, `run_seconds`, `jobs`.
The project is an absolute physical workspace root; inventory is an absolute
physical regular file with schema-1 planner bytes bound by SHA-256. Time uses
an explicit timezone; expiry is future and at most 24 hours at creation.
`max_launches` is an integer 1..128, `poll_seconds` 1..60 and `run_seconds` 1..7200.
Reject bool-as-int, duplicate/unknown keys, NaN, links, special or oversized files.

Each job has exactly `job_id`, `grant`, `grant_sha256`, `approval_key`,
`reservation_key`. The grant is the physical regular existing single-dispatch
grant file, byte-bound by SHA-256; IDs/keys use existing 32-hex rules. Require
unique jobs and reservations. Every job must occur exactly once in the frozen
inventory and match its existing immutable prepared task, worker and approval.
Freeze the invoked engine digest, relevant agents configuration and task-template
digests as local batch bindings. Recheck these before calls; drift refuses.
This is trusted-host owner authority, not authentication against the same user.

The batch never issues missing job approval or shared-lead consent. Native
one-use lead-budget consent, real account slots, bench state and STOP still
apply. A batch cannot change lead, tier, account mappings, efforts or limits.
Unknown allowance remains Unknown and is never displayed as spare capacity.

## Launch and recovery

Reuse the existing fresh planner and `dispatch start` path. Recheck exact
inventory/job/grant/preview identity at launch; planning is not reservation.
Reuse its scope locks and execution-service reservations across batches.
Launch distinct selected scopes/accounts without waiting for completion of
another provider call. Default LOW tier still permits one workflow per group,
including the registered lead; this feature creates no exception.

Persist a job's attempted state and reservation before invoking dispatch.
Increment the finite attempt budget before that call. Refusals after that point
remain recorded attempts, with no automatic retry; planner-blocked jobs consume
no attempts. Persist launcher results separately from actual Source outcomes.
Successful launcher acceptance is neither Source success nor review/acceptance.
Read native results only for bounded observations; never run Verify automatically.

After a crash, interruption or unreadable launch result, an attempted job stays
Unknown or retains existing confirmed evidence. Restart must not call it again,
even if no provider receipt is visible. Never return consumed attempts. Changed
inventory/base requires a new explicitly approved batch; existing dispatcher
reservations and task identity still prevent replay. Dependencies only advance
from explicit accepted integration evidence already valid in the frozen plan.
Future scheduling across new integrations is a separate bounded extension.

## Local state and controls

Store private bounded state under `coord/schedules/`, using unpredictable batch
IDs, a single runner lock per batch and short atomic state updates. Serialize
controls and runner updates so pause/stop cannot be lost to stale writes.
Allow status and pause/stop while the foreground runner is active. Refuse links,
unsupported paths, corrupt state or concurrent runners without repair/deletion.
Store a frozen copy of grant data and digests; raw approval/reservation keys,
requests, commands and private file contents never appear in status, logs or
ordinary JSON output. This is local capability containment, not an OS sandbox.

Use standard library only, matching existing project controls. Bound reads,
subprocess output and deadlines. Pin the exact native runner and installed
helpers; preserve useful behavior from standalone extracted engines and thin
configuration profiles or clearly refuse missing scheduler payloads before a
call. Internal helper is not an AI adapter. Installation calls no provider.

## Focused acceptance

Use offline fixtures and fake native workers; no real model calls in tests.
Cover at least: two disjoint groups launch before either completes; one shared
account stays serialized; pending disjoint work starts after a slot clears;
STOP and pause/stop prevent new calls while running; mismatched scope/base/hash,
missing approval/consent and configuration drift refuse; expired/finite grants;
launch failure, ambiguous result, crash between recorded attempt and dispatch;
restart without replay; concurrent runner refusal; control update races;
no secret keys in output; corrupt/link/special-file refusal; installed helper
identity and standalone/thin-profile behavior. Keep existing dispatcher and
planner behavior unchanged. Do not duplicate the broad gate in task validation.

Register one new focused suite in the release quality gate, generate the helper
byte-identically into the standalone installer and document commands, grant
example, waiting reasons and first-slice limitations. Commit early checkpoints.
Do not bump version or release; the lead integrates and ships the combined tree.
