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

New review invocations capture schema 2 `context.json` before admission, containing
the effective configuration SHA-256, reviewer alias and SHA-256 of the command
captured for launch. Selection matches `conf_for_root()`: a regular project
`coord/agents.conf` takes precedence, otherwise the configured directory is used;
an empty `UNIO_CONF_DIR` uses the normal default. The configuration reader follows
supported hardlinks and symlink-managed paths, reads at most 1 MiB, requires a
regular file and checks descriptor/path identity and metadata before and after
reading. Evidence/artifact readers retain their stricter path/link checks.
Preparation verifies that the selected command still equals the captured launch
command. A context failure removes only newly owned raw/material preparations,
including earlier reviewers' preparation when a later review-set context fails.
Interrupted provider streams and historical evidence remain preserved. Receipt schemas and
material protocols do not change. Observation checks the context as a bounded
4096-byte regular, singly linked file and closes its replacement window alongside
the streams. Configuration drift makes those receipts stale. Historical receipts
without this sidecar retain verdict/freshness visibility but have
`config_current: null` and cannot establish machine readiness. No old receipt is
rewritten. Schema 1 contexts remain readable; with a project override their
provenance is Unknown and they cannot establish machine readiness. Inactive global
configuration edits do not invalidate project-bound contexts. Both effective
configuration and command digests must match for schema 2 currentness.
This binds agents.conf, not every host environment or provider setting;
effective provider identity and remaining allowance are still Unknown.

Handoff already owns the worker lock; its internal observer explicitly recognizes
that owned lock. Ordinary result/reviews calls still refuse readiness while a
worker holds the lock. Current verdict and extraction fields in `reviews --json`
use the same verified stream observation as the result projection. Existing
verdict decision/exit semantics remain unchanged by findings-format completeness.

Observed on 2026-10-21 in the supplied offline tmpfs harness (UID 1000, no
effective capabilities), three `result` calls with two current mock receipts took
1.86, 2.00 and 1.94 seconds, during concurrent focused checks. These are fixture
observations, not an isolated benchmark or a Windows-mount latency guarantee.
Per stream the existing 16 MiB evidence bound remains; receipt JSON is 64 KiB,
collection JSON 64 KiB and findings output retains its existing bounds. A full
256-folder history can require substantial bounded I/O. Observation uses existing
Git snapshot helpers, which have no new enclosing wall-clock deadline in this
change. Configuration hashes are read once at observation start and again at the
closing check. Corrupt collection evidence fails closed even with explicit
`--expect`; explicit expectations still control the reviewer list.

Receipt-less folders remain visible as `unbound_legacy_evidence` history and count
as recorded folders, but do not increment unresolved or veto a later bound review.
They establish no current approval. Bound malformed evidence, current failures or
requests for changes, incomplete collection contracts, missing expected reviewers,
active locks, material/revision/configuration drift and folder bounds still prevent
readiness. No historical folder or receipt is deleted or rewritten by observation.

The bundled execution validator accepts both legacy results and the current
projection. For projections it checks identity/revision, completeness and extraction
flags, decisions, evidence/count consistency, reviewer expectations, empty findings,
configuration currentness and dispatch task binding before deriving readiness.
An isolated `machine_review_ready` flag is insufficient. Execution jobs additionally
require their configured reviewer among the verified current reviewers; existing
process/validation, stale revision and explicit human acceptance checks remain.
Scheduler Source observation uses this validator, including review-set-only and
re-verify results whose legacy review remains `not_run`. Validation reasons include
`delivery_failed` and `invalid_report_artifact`; unknown reasons remain invalid.

Configuration observation failures retain the independently observed current
revision and actual Source state/exit. Missing, invalid UTF-8, oversized or unstable
configuration leaves current review unavailable and machine readiness false;
configuration currentness and approval are not inferred. Canonical consumers can
still decode this nonready result. Mismatched projection revisions remain invalid.
Native result reviewer IDs use the engine grammar
`[a-zA-Z0-9_][a-zA-Z0-9_-]{0,127}`, including legacy review and current projection
fields. Public HTTP/draft labels retain their narrower input grammar; this does
not authorize additional reviewer requests. Traversal and overlong IDs refuse.

Unreviewed result projection discovers bounded receipt and collection evidence before
constructing review material. Receipt-less history and malformed bound evidence
remain visible without material/configuration hashes or a second review snapshot;
neither can establish approval. A valid own receipt or collection triggers fresh
material/configuration observation and the existing closing revision, configuration
and stream checks. Hashes are local to one call; no cross-call cache is used.
Source, validation, delivery and the supplied current revision are still observed
independently, and worker busy checks still apply. Consumer deadlines are unchanged.

Explicit `reviews` browsing retains eager material/hash observation, including
protocol-size diagnostics before a review exists. The deferred path is limited
to result projection.
