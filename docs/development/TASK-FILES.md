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

The verifier parses human annotations according to strict rules:
- **Recognized annotation syntax**: Separating whitespace followed by balanced parentheses at the end of the line (e.g. ` (annotation text)`).
- **Enforcement**: The verifier strips the trailing human annotation, issues a visible bounded warning in verification output and append-only reports, and enforces the actual path or glob pattern.
- **No waiver authority**: Annotations are informational notes. They grant no authority to waive scope enforcement or modify files outside the parsed path/glob.
- **Glob survival**: Globs with annotations (e.g. `- tests/* (unit tests only)`) enforce the glob pattern (`tests/*`) and do not broaden to `*` or drop the pattern.

### Paths with Spaces, Parentheses, and Disambiguation

Real repository paths often include spaces, literal parentheses, or punctuation. The parser handles them safely:
- **Paths with spaces**: Real paths such as `- path with spaces/my file.txt` are preserved intact. The parser never blindly splits on whitespace.
- **Paths with literal parentheses**: Paths such as `- docs/file (copy).txt` or `- dir/(notes)/file.txt` that do not end in separating whitespace and parentheses are treated as literal paths with no annotation stripped.
- **Ambiguous syntax disambiguation**:
  If a literal file or directory name ends with separating whitespace and parentheses (for example, a file named `archive (1)` with no extension):
  - If written unquoted (`- archive (1)`), the parser treats `(1)` as a human annotation on `archive`, issues a warning, and matches `archive`.
  - **Documented guidance**: To match the literal filename `archive (1)`, enclose the path in double quotes, single quotes, or backticks:
    ```markdown
    - "archive (1)"
    - 'archive (1)'
    - `archive (1)`
    ```
    Quoted and backticked paths preserve their exact inner content verbatim without stripping literal parentheses. If a quoted path is followed by an annotation outside the quotes (e.g. `- "archive (1)" (only metadata)`), only the outer annotation is stripped with a warning.

### Path Traversal and Safety

- Path traversal patterns (such as `../outside` or `..`) are rejected and cannot match files in the repository.
- Changes to files outside the declared allowed scope result in a machine gate `scope_violation` failure (`verdict: FAIL`, exit 1).
