# Change a worker's reasoning effort during work

Status: bounded capability/refusal CLI slice implemented on 2026-10-13;
managed Source backend and native effort application remain unimplemented.
Part of the next worker-reliability milestone, after review-findings delivery.
`unio worker-effort WORKER [low|medium|high|xhigh] [--json]` reports unsupported
and refuses requests without provider calls. See [the shipped guide](../WORKER-EFFORT.md).
This is not a completed effort switch.

## Intended experience

An owner or authorized lead can inspect a particular worker's reasoning setting
and request a different supported level while its task is running. The worker's
identity, task, saved work and real account budget remain visible. A change from
high to low should not require manually recreating the task or hiding an extra
session from the lead.

Expose the same state in the CLI and, subsequently, the dashboard. Distinguish
requested, pending, applied, unsupported and unverified settings. Show when the
change takes effect; never claim a setting affected reasoning that had already
happened. Requested effort and effective effort remain separate facts.

## Route support

Interactive Codex offers reasoning controls, but Unio currently launches its
worker through a headless `codex exec` invocation with a startup configuration.
Unio does not currently provide a live control channel to that invocation.
Start the implementation with a capability audit of the installed Codex CLI's
supported session/control interfaces. Determine the actual application boundary
(next request, next turn, or another supported boundary) rather than assuming
that an interactive UI action maps to an available headless operation.

Use an existing supported control interface when possible. If a route requires
stopping and resuming, identify that requirement before acting, preserve a
checkpoint, and require the existing authorization for a new invocation.
Never disguise a restart as an in-place update, replay a failed task blindly,
or silently consume another workflow slot. Cancellation must not discard work
or cut an owned tool operation without the necessary cleanup.

Discover levels per route and model. Low/medium/high/xhigh are not universal.
Fixed selectors, Thinking toggles and models with no verified effort override
need explicit capability descriptions. Do not substitute a different model,
subscription or paid-token route to satisfy an unsupported effort request.
Owner ceilings still apply; this Unio development workspace excludes max/ultra.

## Coordination and evidence

Keep this separate from review protocol (YOLO/Balanced/Thorough), subscription
concurrency tier (low/medium/high), and the documented Low/Medium/Max reasoning
profiles. A per-worker setting change must not change other workers or the lead.
Preserve real shared-account mappings and the registered lead reservation.
Do not create a second independent session on a low-tier shared account.

Record a dated request and result: task, worker, subscription route, CLI/adapter
version, model, old and new requested settings, verified capability, application
boundary, actual outcome, revision/checkpoint and effective Unknowns. Record
restarts and failures separately. Preserve STOP, attempt limits, owned-process
cleanup, independent-review evidence and human control.

## First bounded slice

Begin with Codex session control and one worker. Prove that a requested change
is applied at a supported boundary without losing edits or duplicating the
workflow, and that unsupported changes fail clearly. Cover busy-tool handling,
cancellation, restart-required routes, real budget accounting and truthful
receipts with isolated tests. Use an owner-authorized small live acceptance
only after offline checks. Add dashboard controls after the CLI behavior works.

Initial estimate: 4–8 hours for a bounded Codex-first slice, subject to the
capability audit. Additional adapters and dashboard controls need separate
estimates. Implement after the current milestone and the owner's requested
break; do not add this feature to the review-findings release.
