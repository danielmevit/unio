# Unio 0.5.11 — plan, dispatch and review together

This release brings the checked coordination tools into the installed CLI,
alongside measured recovery-save improvements and the latest dashboard.

## See the fleet before assigning work

```bash
unio fleet --json
unio plan --inventory "/path/to/inventory.json" --json
```

Fleet observations explain local agent blocks, shared-account slots and separate
cached sign-in and allowance readings. The planner checks task materials,
dependencies, accepted revisions and conflicting write scopes without launching
an agent. Missing or stale evidence remains Unknown. See the
[fleet guide](FLEET-STATUS.md) and [task planner](TASK-PLAN.md).

## Start an explicitly approved task

`unio dispatch` prepares, approves and starts one saved task through the existing
execution service. Start checks the exact grant, prepared material, inventory,
worker, base, dependencies, shared account and write reservations. Replay keeps
the original attempt; an unknown outcome never starts an automatic retry.
Follow the exact operations and hashes in the [dispatch guide](TASK-DISPATCH.md).

## Keep independent reviews separate

```bash
unio review-set "worker-a" "task-a" "reviewer-a" "reviewer-b"
unio reviews "worker-a" "task-a" --expect "reviewer-a,reviewer-b"
```

An explicit set of two to eight reviewers receives the same complete frozen
material, with separate account admission and immutable attempt receipts. Full
account groups refuse without a provider call, queue or retry. The read-only
summary checks current material and preserves request-changes precedence.
Reviews never grant human acceptance or merge code. See
[review collection](REVIEW-COLLECTION.md) and [review receipts](REVIEW-RECEIPTS.md).

## Reduce measured recovery overhead

Capture batches sibling Git ignore queries while preserving no-follow traversal,
ignored-file exclusion, both snapshot observations and existing safety limits.
Matched-history fixtures reduced ignore queries from 66 to 6 and completed in
about 26 seconds where the earlier attempts reached the 30-second bound.
This does not establish that every real-workspace timeout is fixed. The
[performance guide](development/SAVE-PERFORMANCE.md) includes the source-checkout
probe, reproducible commands and measurement limits.

The installer also includes the owner's latest dashboard refinements and lead
instructions requiring task estimates, proactive summaries and continuity
through authorized delivery. Existing owner templates remain preserved.

Native macOS/Windows support, phone pairing, automatic scheduling and acting-lead
handover remain planned. Lead cooldown restart remains experimental and opt-in;
the genuine subscription-limit-to-restart cycle is still unobserved.

[Release and downloads](https://github.com/danielmevit/unio/releases/tag/v0.5.11).
