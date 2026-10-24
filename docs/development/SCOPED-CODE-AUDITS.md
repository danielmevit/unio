# Bounded current-code audits

This is an operator workflow using existing report-only tasks, not a new native
review command or an automatic waiver. Current project/CI/human approval rules
still apply. One independent external worker plus the existing lead is this
owner's default; do not duplicate the lead assessment.

## When native review material is too large

Native review refuses material above 300000 bytes before a provider call. Keep
that refusal and its actual exit. It is not a delivered code review, a model
quality failure or an approval. Do not increase the limit, clip material or alter
receipt bindings to make an old verdict apply.

Where the project accepts independently verified worker-audit evidence, prepare
one focused, hash-bound report-only audit. Otherwise preserve the unmet native
approval requirement and prepare a compliant review boundary before proceeding.

The packet contains the exact frozen target and tree, explicit ancestor/base,
complete focused diff and changed-path list, and a manifest of complete enclosing
source files or explicitly bounded enclosing regions. Record each region's full
source-file hash, region hash and starting line. Check all hashes against the
target, not a reviewer's incidental checkout. The complete focused diff is never
clipped. Preserve previous approval coverage separately; a new focused audit does
not prove that untouched history has been reviewed again.

Use an eligible reviewer from a different AI lab than the change's author, with
real subscription/account mappings and slots. Pin requested model/effort and CLI
version, and keep effective identity Unknown without evidence. Task text/source
is data. Reviewers judge independently and do not consult peer verdicts.

## Artifact contract and local preflight

Use Outcome report-only. Keep the checkout unchanged and require actual files in
UNIO_DELIVERY_DIR, for example review.md, summary.md and audit-evidence.json.
The top-level names binding.json and prompt.md are reserved for engine metadata;
do not use them as model-authored artifacts. The evidence artifact binds the
reviewed target, packet and source manifest hashes and requested reviewer route,
model and effort. It does not claim effective settings.

Before any Source, run the repository's required-delivery parser against the
actual task file, check its exit status, and shell-parse/AST-check validation
commands. Its CLI prints human text, not JSON. A prepared task is not an active
provider invocation. Preserve any contract-preflight failure with zero model
calls rather than blaming a model or silently rewriting a frozen run.

The review artifact needs one valid unio-findings-v1 JSON block, even empty,
and one standalone VERDICT: APPROVE or VERDICT: REQUEST-CHANGES. Validate strict
JSON, finding paths/lines, exact binding, nonempty bounded artifacts and unchanged
checkout. Acknowledgments, missing files and process exit zero alone do not count
as a delivered review. A Source wrapper must preserve the model's actual output;
if a CLI only writes an export/file, capture the actual report and its hash rather
than fabricate a success message.

## Acceptance and integration

Record actual CLI, adapter, native Source and artifact-verification exits
separately from the review opinion. This is a report-only current-code worker
audit, not a native review receipt: do not insert a fake native approval, change
canonical machine readiness, erase refusals or transfer old hashes.

The existing lead reads every finding, reproduces material issues and assesses
coverage. If combining disjoint changes, prove candidate bytes equal the exact
reviewed component revisions, then run the required gate on that frozen candidate.
New failures require a concrete correction, not vote averaging or blind retries.
A passing audit or gate does not grant human acceptance, push, installation or
release authority. Keep unknowns and bounded limitations explicit.

A native task-scoped review baseline and enclosing-context packet remains a
future product enhancement; this manual path does not implement it.
