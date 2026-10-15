# Unio 0.5.19 — recovery, saving and Copilot preparation (unreleased)

Status: candidate in preparation, 2026-10-15. The published and installed
release remains
[0.5.18](https://github.com/danielmevit/unio/releases/tag/v0.5.18). Nothing
in this bundle is accepted or shipped yet; separate workers are still
finishing the code, and the lead will finalize the evidence after actual
acceptance.

## Proposed benefits

- **Owned native stopping.** Stop the exact provider process tree Unio
  launched: nested process groups and reparented children within an
  explicitly recorded Linux provider session, identity checks through
  pidfds, account-ownership boundaries and a bounded final save. This
  preserves the exact saved Grok stop work produced after its HTTP 402
  usage stop.
- **Measured saving on populated stores.** Fold the duplicate metadata and
  deep passes, isolated by the diagnosis commit 02f316c, into a single
  deep traversal during active classification (implementation 33594e0).
  Full content validation, newest/corrupt/pin protection, capture bounds
  and rollback remain required and unchanged.
- **Exact Copilot result handling.** Accept the documented filename arrays
  Copilot CLI 1.0.95 Auto Balance actually returns in filesModified, plus
  the legacy bounded integer counts (correction 721c56c). A real run that
  ended native 0 but adapter Source 2 on this schema mismatch is the
  motivating case.

## Supported session boundary

The stopping work applies only to a provider session Unio explicitly
records and owns on Linux: the launched process tree, its nested process
groups and children that reparent within that recorded session, checked by
pidfd identity and account ownership. Processes that detach from the
recorded session, processes outside it, and processes not owned by the
recorded account are unmanaged: Unio does not chase or claim them.

## Limits

- **Detached and unmanaged processes are not contained.** The boundary above
  is a recorded-session boundary, not an OS sandbox; a process that escapes
  the recorded session stays outside Unio's control.
- **No genuine live test of the corrected code yet.** The Copilot
  correction passed native verification and an offline replay of the saved
  native stream matches the exact assistant text, but no new live Copilot
  call has used the corrected code, and independent review is pending.
- **No performance claim.** The saving work is a structural change with
  tests and matched measurements still active. No wall-clock speedup,
  filesystem causation or universal improvement is claimed, and the default
  capture budget is unchanged.
- **Stopping is not resolved.** The inherited patch 7588d8e passed seven
  native checks, but lead and independent review found the final capture
  reachable after cleanup Unknown, unreadable-identity handling and
  overbroad foreign-record claims. A bounded correction is active and not
  accepted; this guide does not promise resolution or full containment.

## Current acceptance state (2026-10-15)

- **Owned native stopping:** inherited patch 7588d8e, seven native checks
  passed; lead and independent Gemini review found the defects above; a
  bounded correction is active and not accepted.
- **Saving:** diagnosis 02f316c measured small populated stores and
  isolated the duplicate passes; implementation 33594e0 folds active
  classification into one deep traversal; tests and matched measurements
  are still active. Not accepted.
- **Copilot:** correction 721c56c passed native verification; the offline
  replay of an actual saved native stream matches the exact assistant
  text. Independent review and a live call with the corrected code remain
  pending. Not accepted.

A passing process, passing checks and a reviewer's approval are separate
from acceptance. The lead will finalize the evidence, run the full frozen
gate and publish only after actual acceptance.
