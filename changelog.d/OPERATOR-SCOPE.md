# Allowed scope human annotation parsing and path disambiguation

- Strip human annotations in balanced parentheses separated by whitespace (such as `- path (only X adjustments)`) under `## Allowed scope`.
- Emit a visible bounded warning in verification output and append-only reports when annotations are stripped.
- Enforce the exact extracted path or glob pattern; annotations grant no waiver authority and do not broaden scope.
- Preserve unannotated paths containing spaces, literal parentheses, globs, and quoted or backticked forms intact.
- Document quoting guidance (`"path (1)"` or `` `path (1)` ``) to disambiguate literal filenames ending in parentheses from annotations.
- Reject path traversal attempts and preserve strict missing scope, missing validate, and scope violation failure semantics.
