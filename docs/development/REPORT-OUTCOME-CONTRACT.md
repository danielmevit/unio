# Declared task outcomes — operator round contract

Status: frozen implementation contract for operator items 5–6; no claim of shipped behavior.

Existing tasks retain their current behavior. An optional `## Outcome` section declares
one plain value: `implementation` or `report-only`. Absence means legacy behavior;
malformed, duplicate or unknown declarations receive an actionable refusal before a
provider call. Ignore fenced examples when parsing task metadata. Do not infer intent
or a blockage by matching arbitrary model prose.

An explicit implementation task requires repository access. A recognized canonical
proposal-only Copilot or Perplexity route must refuse with a nonzero exit and the
stable outcome `blocked_no_repo_access`, before invoking the provider. Preserve the
real source exit when one exists; a pre-dispatch blockage is not a fabricated run.
Unrecognized custom commands retain legacy compatibility and unknown capabilities.
Optional adapter-side declared-mode guards cover otherwise wrapped canonical adapters.
Existing proposal-only routes and their command shapes continue to work for legacy
or explicitly report-only tasks. A blockage must not bench an account or alter limits.

Report-only is an explicit artifact contract, not an empty-work waiver. A successful
current Source must supply a nonempty bounded UTF-8 report, saved as immutable native
run evidence, bound to the task, worker, dispatch/run, command and repository revision.
Use engine-owned paths and hashes, never arbitrary receipt paths. Native Source output
may be captured as the report; proposal adapters may supply their actual answer via an
optional engine-owned report channel so a receipt pointer alone is not the artifact.
Document which channel is used. No provider call is made by verify/result/handoff.

Report-only verification still requires allowed scope and executable Validate lines,
Source exit zero, a fresh matching artifact and passing checks. Compare the repository
against its dispatch snapshot: a report-only task must not change repository content;
it may start on a feature branch containing earlier work. An unchanged repository is
allowed only for this declared, evidenced task type. Empty/missing reports, failed
Sources, changed code, mismatched/stale bindings or failed checks remain failures.

Artifact disappearance or modification after verification must invalidate readiness.
Review material contains the complete current report and its binding; preserve existing
material bounds and refuse instead of clipping. Result and handoff carry additive
artifact/mode provenance without claiming human acceptance. Keep legacy schemas and
strict consumers compatible; use an additive sidecar when existing exact-key records
cannot change safely. The implementation owner may choose the smallest consistent
mechanism satisfying these invariants, and documents any unavoidable conflict.

Tests cover legacy tasks, explicit blocked routes without a provider call, genuine
report-only success without a commit, and failed Source, missing/empty/tampered/stale
artifacts, changed repository, missing Validate and review/handoff freshness. Native
run, verify, review and review-set must agree. Generated installer code remains in sync.
