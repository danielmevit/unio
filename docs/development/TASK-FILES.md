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
