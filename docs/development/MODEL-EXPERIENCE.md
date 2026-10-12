# Model experience from real project work

Owner-approved feature direction, 2026-10-07. The first bounded CLI slice
shipped in **[0.5.12](https://github.com/danielmevit/unio/releases/tag/v0.5.12)**, under the
[frozen contract](MODEL-EXPERIENCE-CONTRACT.md): explicit final assessments tied
to native task revisions, local task-specific evidence and conditional advice
using the existing fleet observation. It is published and installed; the complete
gate, exact assets, upgrade/rollback and official download checks passed.
See the [operator guide](../MODEL-EXPERIENCE.md) for the implemented commands.
Automatic metadata capture, routing and richer review-quality profiles remain
planned. The existing
`unio score` command already summarizes per-worker ledger results. It does
not yet provide model-specific task profiles, automatic routing, review
accuracy or causal comparisons. Extend that evidence rather than adding a
separate synthetic benchmark program. The
[curated model scoreboard and task-fit guide](MODEL-SCOREBOARD.md) is available
now as lead guidance; see the current version plan before assuming that a
development-source command is installed.
[Bounded escalation](../ai/LEAD-ESCALATION.md) records when the lead takes over
a struggling correction instead of spending another worker session.

## Product behavior

Unio should help the owner and lead choose an agent for a particular project
and task using results from actual work. Show why a recommendation exists,
its sample size and age, and whether it is based on observed project work,
an official capability description or an untested hypothesis.

Profiles are scoped to exact model/version, CLI/gateway, requested/effective
effort and task type. A good docs reviewer is not automatically a good UI
builder or shell debugger. Record language/stack, project type, task size,
YOLO/medium/safe mode and subscription tier so results remain interpretable.
Shared budget grouping remains separate from AI lab provenance.

## Evidence to collect

- Exact task/base/candidate and native receipt references, with outcome links.
- Source exit and actual focused/full verification results separately.
- Whether the changes were accepted and integrated, plus rejected/saved work.
- Demonstrated corrections and rework after review; do not treat every review
  comment as a proven defect or every APPROVE as a high-quality assessment.
- Time spent implementing, checking, reviewing and recovering, with completion
  and interruption distinguished. Compare time to accepted work, not tokens
  emitted or raw output length.
- Tokens, cost and allowance observations only when supported evidence exists.
  Missing values stay Unknown; CLI token reports are not subscription meters.
- Connection/auth/usage failures separately from code-quality failures.
- Later regressions or owner feedback tied to the original candidate.

Use the current append-only ledger and exact native result provenance. Keep
raw private prompts/code/logs local; public summaries contain only deliberate,
reviewed conclusions. Capturing deterministic metadata should use no extra AI
calls, and normal work should not trigger an automatic review/benchmark fleet.

## Recommendations and fair comparisons

Start new routes as untested. Use [the free model inventory](../FREE-MODELS.md)
and official capability notes to propose bounded, useful trials on real tasks.
Update task-specific conclusions only from checked outcomes. Preserve failed
runs; report low sample size, confounding route/effort changes and dated data.
Avoid a universal score that hides whether an agent failed transport, generated
bad code or simply received a harder task. Prefer transparent counts and
examples to a fake percentage confidence.

Passive learning from regular project work is the default. An optional matched
comparison can use the same frozen task/base, scoped working copies and check
criteria when the owner wants the extra work. It must still honor per-group
workflow limits and invocation budgets, and merge at most one actual candidate.
Do not copy findings into another model's supposedly independent review.

Before automatic routing, offer an explainable suggestion that the lead or
owner can override: relevant accepted tasks, demonstrated findings, correction
burden, measured duration, current availability and cost eligibility. Never
route around a limit with a paid fallback or make weak evidence look certain.

## Delivery sequence

1. Add validated model/route/effort/task labels and outcome bindings to existing
   receipts without weakening their revision checks or exposing private text.
2. Add local task-specific aggregation to `unio score` (human and JSON views),
   including unknown metadata and small/old samples. Proposed richer selectors
   are not implemented commands yet.
3. Expose understandable profiles to first-contact lead instructions and the
   browser interface, alongside work mode and account-budget state.
4. Add opt-in suggestions after sufficient practical evidence exists. Assess
   routing benefits against accepted work and rework, rather than assuming
   automation improves performance.

Freeze the schema and backward-compatible migration before implementation.
The first bounded slice should prove that a correct accepted task, a quality
failure, a transport failure and an unaccepted Source cannot be conflated;
small/empty samples must not create a confident recommendation. This belongs
to the approved roadmap after core work controls and existing delivery work,
with its own version assigned when the implementation scope is frozen.
