# Task File Structure and Allowed Scope Rules

Unio coordinates AI worker tasks through self-contained markdown order files in `coord/tasks/<task-id>.md`.
Workers have no prior conversational memory; every task file must be explicit and self-contained.

## Required Sections

A valid task order contains three core sections:

1. `## Goal`: Clear explanation of the intended work, background, and acceptance criteria.
2. `## Allowed scope`: Exhaustive list of relative file paths or glob patterns that the worker may modify.
3. `## Validate`: Shell commands starting with `$ ` that must exit 0 in the worker's worktree to verify the changes.

Tasks lacking `## Allowed scope` or `## Validate` fail machine verification as `INCOMPLETE` (exit 2).

## Allowed Scope Patterns

Every entry under `## Allowed scope` begins with `- ` followed by a pattern relative to the repository root.

```markdown
## Allowed scope
- src/Core/Centerline.cs
- tests/*.py
- "docs/with spaces/notes (draft).md"
```

### Human Annotations

Operators sometimes add clarifying notes to scope lines to guide workers, for example:
```markdown
- src/Core/Centerline.cs (thin-vs-wide classification only)
- tests/* (new coverage only)
```

The verifier and task planner share this conservative grammar:
- An unquoted path may end with ` (only TEXT)`, where TEXT contains no parentheses. This reserved suffix is an informational annotation and is stripped with a bounded verification warning.
- A path enclosed in matching double quotes, single quotes or backticks may be followed by a balanced parenthesized annotation. The quoted content is preserved literally.
- Every other unquoted suffix is literal: `folder (old)` authorizes that exact path, never `folder`. Quote literal names ending in the reserved ` (only TEXT)` form.
- Globs remain globs; annotations cannot broaden a pattern or waive scope enforcement.

Examples:
```markdown
- src/Core/Centerline.cs (only X adjustments)
- tests/* (only new coverage)
- folder (old)
- "archive (1)" (only metadata)
```

### Path Traversal and Safety

- Path traversal patterns (such as `../outside` or `..`) are rejected and cannot match files in the repository.
- Changes to files outside the declared allowed scope result in a machine gate `scope_violation` failure (`verdict: FAIL`, exit 1).

## Optional declared outcomes

Add the exact heading `## Outcome` followed by one plain value, `implementation`
or `report-only`, on its own line. Fenced examples are ignored. Unknown values,
empty/multiple values, malformed headings and duplicate sections refuse before
provider admission. No declaration retains legacy behavior, including the existing
empty-work failure; task intent is never inferred from prose.

Explicit implementation on a recognized canonical Copilot or Perplexity proposal
route refuses nonzero with `blocked_no_repo_access`, before admission or provider
startup. Wrapped canonical adapters also guard this mode; arbitrary custom
wrappers keep unknown capabilities and legacy route handling.

Report-only requires Source exit zero and an actual nonempty UTF-8 text report
(maximum 262144 bytes, no NUL). Native Sources use complete native output
(stdout/stderr). Copilot and Perplexity publish the actual answer through the
optional engine-owned `UNIO_TASK_REPORT` channel; receipt/proposal path pointers
alone cannot satisfy canonical proposal routes. Do not write a report into the
repository: any repository change since dispatch fails. A task may start on an
existing feature branch. Normal Allowed scope and executable Validate checks
remain required; unchanged content alone never waives legacy empty-work checks.

Native report evidence lives under
`coord/results/<worker>/<task>.outcomes/<run-id>/`. The schema1 result adds optional
`outcome` provenance and `outcome_current` freshness; revision keys and old evidence
remain unchanged. The exclusive report, dispatch binding and effective prompt are
hashed and rechecked by result/review/handoff. The complete report and provenance
enter bounded review material and `report.md` in handoffs; overflow refuses rather
than clipping. Verify/result/handoff never invoke a provider. Local unsigned
evidence remains subject to the existing same-user trust model.
