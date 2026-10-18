# Non-blocking tail by default and safe follow mode

- Change `unio tail [TASK] [--lines N]` to print recent log output (default: last 40 lines) and exit immediately rather than blocking in follow mode.
- Require `-f` or `--follow` to watch append-only logs live.
- Accept practical option ordering (`unio tail TASK -f`, `unio tail -f TASK`, `unio tail TASK --lines N`, `unio tail --lines N TASK`).
- Validate `--lines` as a bounded positive integer (1 to 100,000); reject unknown, duplicate, or ambiguous arguments with actionable errors.
- Enforce task ID validation and prevent path traversal while preserving `.md` suffix compatibility (`TASK.md`).
- Preserve safe path and file names containing spaces when discovering the latest report log.
- Update built-in help, shell completions, and generated background run guidance to suggest `unio tail -f TASK` for live output.
