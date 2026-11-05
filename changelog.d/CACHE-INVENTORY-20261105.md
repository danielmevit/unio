Add `unio cache [--dry-run] [--json]`, a bounded read-only inventory of likely
generated .NET `bin`/`obj` directories in inactive registered worker worktrees.
It works with STOP, calls no provider, and has no deletion, compaction or retention
mode. Unknown activity or unsafe contents are excluded with a reason, and partial
results stay explicit. See `docs/BUILD-CACHE-HYGIENE.md`.
