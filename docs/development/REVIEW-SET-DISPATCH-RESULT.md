# Review-set current dispatch result

`unio review-set` reports the outcome of its own collection separately from the
read-only historical review summary. A `completed` descriptor means that all
attempt receipts were bound; it does not prove that reviewers were invoked.

Exit 0 requires every requested reviewer in this collection to have an actual
invocation, process exit 0 and APPROVE, with complete bound receipts, unchanged
material/candidate and a successful historical summary. Earlier current approvals
remain valid history but cannot supply a missing invocation in a fresh batch.

The collection status line includes `invoked=N/T`, `refused=N`, `invalid=N` and
`dispatch_exit=N`. These describe only this dispatch; `Recorded reviews` below
it retains the existing aggregate history semantics. `dispatch_exit=0` is a
necessary condition for command success, not final acceptance: historical current
change requests, failures or incomplete contracts can still block the command.

A missing/consumed owner grant or partial admission returns 2, including when
older approvals exist. Admitted attempts stopped before invocation also count as
refused. Invalid child evidence or an invoked nonzero process/REQUEST-CHANGES
returns 1 unless this same collection also contains a refusal (which takes exit
2 precedence). An unknown verdict without a process failure, drift, unavailable
snapshot or incomplete material returns 2. Signals retain their signal exit.
No refused attempt authorizes a provider call or consumes a second grant.

Receipt and collection schemas are unchanged. Proven pre-provider refusals stay
visible as unknown history without permanently vetoing a later complete batch.
Genuine current failures/change requests, stale/unknown evidence and incomplete
contracts keep their conservative aggregate treatment. No history is deleted,
no consent is synthesized, and no lab identity or human acceptance is inferred.

The installed offline regression suite is `tests/unio-review-collection.py`.
Its seven cases cover granted success and replay, old approvals followed by a
fresh refusal, partial shared-group admission, actual process failure and
REQUEST-CHANGES, invalid child evidence, drift/material failure, STOP and cleanup.
Run it using the lead-provided private fixture wrapper for this frozen task;
no live provider invocation or full Source gate is needed.
