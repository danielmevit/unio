# Review-set current dispatch result

`unio review-set` reports the outcome of its own collection separately from the
read-only historical review summary. A `completed` descriptor means that all
attempt receipts were bound; it does not prove that reviewers were invoked.

Exit 0 requires every requested reviewer in this collection to have an actual
invocation, process exit 0 and APPROVE, with complete bound receipts, unchanged
material/candidate and a successful historical summary. Earlier current approvals
remain valid history but cannot supply a missing invocation in a fresh batch.

The collection status line includes `invoked=N/T`, `refused=N`, `invalid=N` and
`dispatch_exit=N`. `invoked` counts VERIFIED invocations only. Invalid attempts
have Unknown invocation status: their provider may have run, so a numeric
`invoked=0` next to `invalid>0` is not proof of no calls. These describe only this dispatch; `Recorded reviews` below
it retains the existing aggregate history semantics. `dispatch_exit=0` is a
necessary condition for command success, not final acceptance: historical current
change requests, failures or incomplete contracts can still block the command.

The final CLI exit is 1 whenever the historical summary contains a current
recorded REQUEST-CHANGES, including partial/refused dispatches or finalizer
failure. Otherwise a missing/consumed owner grant, partial admission, invalid
child evidence or actual reviewer process failure returns 2. Process failures
keep their real exit and failed state in receipts; they are not change requests.
Admitted attempts stopped before invocation count as refused. Unknown verdicts,
drift, unavailable snapshots and incomplete material also return 2. Signals
retain their signal exit. No refused attempt authorizes a provider call or
consumes a second grant.

`dispatch_exit` describes this collection only: 2 for refusal, invalid child,
process failure, or a material_changed/receipt_failed attempt; otherwise 1 for a
REQUEST-CHANGES recorded in the successfully bound published receipt (stdout
alone never counts, so a mutated-material change request is 2); 0 only for a
complete approving dispatch; 2 for other incomplete outcomes. Historical
change requests determine final CLI exit 1 independently of this field.

If finalization fails or its output has the wrong collection identity, state,
field count, numeric ranges or inconsistent totals/readiness (bound above
invoked+refused, completed with invalid attempts, or dispatch 1 without a
verified invocation or with refused/invalid attempts), counters remain
`unknown` and `dispatch_exit=2`. Successfully validated helper output alone
supplies numeric counters. An Unknown invocation count never asserts zero calls.

Receipt and collection schemas are unchanged. Only the exact proven
`budget_refused` class (never admitted) is excluded from current verdict
history. Admitted STOP refusals (`stop_active`) remain conservative unknown rows
for the same revision, material and config: a later all-approving batch can
print `dispatch_exit=0` yet the command still exits 2 (`Recorded reviews:
incomplete`), and its approvals do not erase them. Do not fake a commit, alter
legitimate material, erase history, synthesize consent or blindly retry (each
retry spends provider calls); inspect the receipts and leave the decision to
the owner. Early dispatch detection of such known blocking history is backlog.
Genuine current failures/change requests, stale/unknown evidence and incomplete
contracts keep their conservative aggregate treatment. No history is deleted,
no consent is synthesized, and no lab identity or human acceptance is inferred.

The installed offline regression suite is `tests/unio-review-collection.py`.
Cases cover granted success and replay, current changes followed by refusal,
partial shared-group admission with approval or changes, process failure,
invalid child evidence, malformed/mismatched finalizer output, finalizer failure,
admitted STOP before invocation followed by resume and an approving batch that
still exits 2 with unchanged STOP evidence, material mutation with REQUEST-CHANGES
(dispatch 2), impossible finalizer tuples, drift/material failure and signal cleanup.
Fault injection modifies only disposable installed fixture scripts; production
has no fault switches. Tests assert offline call logs, unchanged historical
receipts and native slot cleanup. Run using the lead-provided private fixture
wrapper for this frozen task; no live provider invocation or full Source gate
is needed.
