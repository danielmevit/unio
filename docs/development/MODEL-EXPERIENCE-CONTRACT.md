# Local worker experience and selection advice

Frozen first slice, 2026-10-12, targeting **0.5.12**. Builds on released
`unio result`, `unio score` and `unio fleet`. This is a local CLI feature;
automatic scheduling, model calls, UI changes and general benchmarking are
outside this slice. Preserve all existing result and review schemas.

## Commands

```text
unio experience record WORKER TASK --model MODEL --route ROUTE --effort EFFORT --task-type TYPE --outcome OUTCOME [--corrections N]
unio experience show [--task-type TYPE] [--json]
unio experience suggest --task-type TYPE [--work-kind implementation|routine] [--json] [--timeout SECONDS]
```

All support `--project PATH` and `--help`; help works outside a workspace.
Flags must be fully spelled and unknown/duplicate inputs refused. Identifiers
use native worker/task rules. Metadata labels are bounded ASCII tokens;
no prompt, source code, arbitrary prose, account identity or configured command
is stored or displayed. Model is the **operator-reported requested model**;
effective model/effort remain unknown. Effort is `unknown`, `none`, `low`,
`medium`, `high`, `xhigh` or `thinking`. Recording historical metadata is not
permission to request model calls. No max/ultra selection is introduced.

Routes are `codex`, `claude`, `grok`, `antigravity`, `mistral-vibe`,
`opencode-go`, `opencode-zen-free`, `perplexity-web`, `copilot-auto` or
`unknown`. Route and model are declarations, never inferred from a worker
name. The native worker prefix alone identifies its configured account alias.
Free Zen, Perplexity and Copilot records are eligible for routine advice only
in this first slice; unknown routes cannot receive implementation advice.
This captures the current owner roles without promoting a free/proposal route
through a successful task or an increased effort setting.

## Record one final assessment of one native task revision

`record` is an explicit operator assessment. It must consume the existing
runner's fixed `result WORKER TASK` command, without a shell, and require a
well-formed, nonstale result for exactly those identifiers and their current
revision. Refuse a running/not-run process, failed post-run snapshot, missing
result, mismatched evidence or unsupported worktree. Use bounded output and
an observation deadline; no provider or authentication call is permitted.

Outcomes stay distinct:

- `accepted`: operator reports accepting the candidate. Require Source exit
  zero and current native validation PASS for the same revision. This records
  the report, **does not grant human acceptance, merge, review or publication**,
  and must never synthesize an independent review. Label it reported acceptance.
- `quality_issue`: operator reports a demonstrated code-quality problem. Keep
  native exit/check facts separately; a green check cannot erase this report.
- `operational_failure`: operator reports transport, authentication, quota or
  infrastructure trouble. Require a nonzero Source exit. It is a failure to
  deliver, not evidence that the model writes bad code.
- `unaccepted`: useful Source/check evidence with no reported acceptance.
  Exit zero alone is never accepted work.

Corrections is an optional operator-reported integer 0..10000. Missing means
unknown, not zero. Duration, tokens, prices, lab and remaining allowance are
unknown unless this slice has an actual bound source; do not invent them.

Store immutable schema-1 records locally under `coord/experience/`, transactionally
with stable identity from worker, task and the complete native revision. Store
the bounded native process/check facts, binding, observation timestamp, record
timestamp, declared profile/outcome/corrections and metadata provenance. Identical
replay is idempotent; a conflicting assessment/label for the same revision is
refused unchanged. No amend/delete/migration-by-reset operation in this slice.
Tell users to record final assessments; later correction history is a future
extension. Different task revisions remain distinct recorded attempts, but
**a task contributes at most once to a profile's accepted-task count**.

Refuse unsafe symlink/hardlink/special-file paths, malformed/unknown store
schemas, oversized records/store, duplicate JSON keys and invalid/nonfinite
types. Concurrent records must not overwrite or duplicate each other. Reads
must not create the store or locks, rewrite legacy data or alter anything.
Missing storage is an empty sample, not corruption. No scanning arbitrary
operator-supplied receipt paths and no reading native authentication stores.

## Show evidence; make advice conditional

Group by account alias, requested model, route, requested effort and exact task
type. Show task/attempt counts, reported accepted tasks, quality issues,
operational failures, unaccepted attempts, known correction burden, newest
observation and sample age. Preserve every outcome and unknown. No universal
numeric model score, fake percentage confidence or causal comparison.

Advice uses only that task type. Fetch the existing bounded fleet observation
with a whole deadline 1..60s, default 10s. Observe current STOP/off/binary,
shared-group slots including lead, cached sign-in and fresh cached allowance;
stale/missing/expired capacity remains unknown. Do not refresh or probe accounts.
Blocked/unknown admission, fresh signed-out state or fresh exhausted allowance
must not become a positive recommendation. A clear local slot is not proof of
provider readiness; unknown auth/quota stays explicitly conditional.

Fewer than three distinct reported accepted tasks in the last 90 days means
`insufficient_evidence`: show the examples, but do not select a worker. Older
observations remain visible and are excluded from that threshold. Eligible
profiles with enough evidence can appear as **conditional suggestions**, ordered
by recent distinct reported accepted tasks, then observed quality-issue count,
then known correction burden, then stable profile labels. Missing correction
burden cannot win a tie against a known zero. Return all qualifying options;
no autonomous winner, reservation, dispatch, retries or budget changes.

JSON is one schema-1 object. Separate evidence, local admission and advice;
include `human_acceptance: false`, `provider_calls: false`, and honest source
status/limitations. Empty samples, partial fleet failure and insufficient
evidence are valid reports, not fabricated recommendations. Corrupt local
experience data fails with exit 2 and no writes. Normal successful reads and
records return 0, usage/refusals return 2. No raw subprocess stderr in output.

## Packaging and acceptance

Package byte-identical helper code in the standalone installer, add command
dispatch/help/completion, one guide and changelog fragment, and register one
focused offline suite in the release gate. Preserve existing installer
payloads, templates, configuration, version, browser/site/brand and workflows.
No dependencies, global installation or provider calls from tests.

Meaningful offline cases cover: real copied standalone install; distinct
accepted/quality/operational/unaccepted evidence; result drift and stale checks;
one revision replay/conflict and concurrent recording; same task revisions not
inflating accepted-task samples; sparse/old/empty samples; route role limits;
lead/shared-account/STOP/off/missing/signed-out/exhausted/unknown admission;
bounded malformed/duplicate/nonfinite/symlink/overflow inputs; read-only reports
and a configured-agent sentinel proving zero provider calls. Use real tiny Git
worktrees and native mock results where feasible, deterministic fake fleet
inputs for boundary cases, and consolidate fixtures instead of replaying broad
suites per assertion. Personal lead review follows the owner YOLO exception.

Initial elapsed estimate: 3–6 hours including implementation, focused checks,
integration and release preparation. A healthy implementation worker gets up to
two hours. Full gate/artifacts/install/publication follow one frozen candidate;
no waiting for a real quota failure or extra model-review fleet.
