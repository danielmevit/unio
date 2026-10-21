# Current review observation

Schema 1 result keeps the legacy `review` object and its allowed states unchanged.
`result` and handoff `result.json` add `review_current`, an observation of verified
immutable receipts, not a persisted replacement or acceptance record. The handoff
text labels both current and legacy views. Consumers should use
`review_current.verdict_decision` for current recorded reviews. Entries preserve
actual exits, failures, unknown outcomes and stale history; a current request for
changes blocks even when a later receipt approves.

The projection uses the findings observer: verdict decision, verdict completeness,
findings extraction completeness and machine review readiness are separate fields.
Missing/malformed findings and protocol 1 unstructured legacy output cannot confer
complete readiness. Structured findings require inspection. Expected reviewers are
the union of current collection contracts, when known; an empty list imposes no
universal count. Alias/account groups never establish AI lab independence.
Human remains pending and integration not_attempted. Readiness is only a machine
signal for inspection, never lead/human acceptance.

Observation performs no provider calls or coordination writes. It remains outside
`current()` so gate/material generation cannot recurse. Both exact material hash
protocols are derived from one shared material body per observation, retaining
protocol 1's pre-footer and protocol 2's whole-payload 300000-byte bounds. No
clipping occurs. Result uses its initial snapshot, material construction currently
uses two more snapshots through changed/material, and the observer takes a closing
snapshot (four total). Handoff additionally checks changed paths and a final
snapshot. This is bounded by existing repository snapshot limits, not a constant
runtime promise on slow filesystems. At most 256 receipt and 256 collection folders
are inspected; overflow, invalid evidence, busy workers and drift fail closed.
The legacy `reviews` and findings CLI shapes/decisions remain compatible; their
explicit `--expect` remains authoritative for those invocations.
