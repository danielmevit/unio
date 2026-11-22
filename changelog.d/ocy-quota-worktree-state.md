# Interrupted Git worktree reporting and suspected Grok 402 balance exhaustion

## Added / Changed
- **Read-only Git in-progress state and bounded unmerged paths** (`unio-install.sh`):
  - Reported Git merge/rebase/cherry-pick/revert/bisect/sequencer operations and bounded unmerged paths (up to 20 paths plus total count) read-only from `.git` metadata and `ls-files --unmerged -z` in end-of-run output and `coord/reports/<task>.md` without mutating, resetting, or aborting the worktree.
  - Preserved original Source exit codes even when post-run snapshots fail (`end-unbound`).
- **Suspected Grok 402 balance exhaustion** (`unio-install.sh`):
  - Extended `LIMIT_RE` to recognize `(usage )?balance (is )?exhausted` (such as `API error (status 402 Payment Required): Grok Build usage balance exhausted`) in the normalized 60-line failure tail as suspected limit language (`wall=1`), surfacing `unio off <agent>` recovery guidance while keeping `Adapter outcome: Unknown` and original failure accounting.
- **Deferred**:
  - Confirmed `quota_exhausted` adapter classification, loop-brake exemptions, and automatic holds (`quota-auto-off`) remain deferred because exact typed terminal quota evidence for the installed Grok CLI path is unavailable and project-scoped auto-off without global `$OFF_DIR` leakage or manual-hold race hazards is not established.
