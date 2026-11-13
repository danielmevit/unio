# INDEX-LOCK-SAFETY-20261113

Remove automatic `index.lock` deletion from `cmd_run` startup, preserving live and Unknown Git index locks.

### Background and Confirmed Bug (R-02)
Prior to this change, `unio run` startup checked whether `$gd/index.lock` existed and unconditionally removed it (`rm -f`), assuming any lock was a stale artifact from a killed prior run. When an active Git process (such as `git update-index --stdin` or an interactive git command) held `index.lock`, `unio run` deleted the lock while the writer was still alive, labelled the lock stale, and proceeded to invoke the provider. The original Git writer subsequently failed with exit 128 (`fatal: Unable to write new index file`) and its staged changes were lost.

### Safe Bounded Behavior
- Detection at startup: `unio run` detects an existing `index.lock` in the worktree's Git directory (including regular files, symlinks, broken symlinks, and non-regular directory or special entries).
- Fail-closed refusal: `unio run` refuses startup with a non-zero exit code BEFORE provider command execution or account grant consumption.
- Lock and data preservation: The existing lock, target files, and index entries are left completely untouched. Active Git writers are allowed to proceed and complete cleanly.
- No staleness inference: Staleness is not inferred from mtime, pid absence, or process table snapshots, and no auto-rm/cleanup flags are introduced. Ownership is treated as Unknown unless proved.
- Git directory resolution: If the Git directory cannot be established, startup fails cleanly rather than attempting writes or deletions.
- Documentation: Updated `docs/PROTOCOL.md`, `docs/HANDBOOK.md`, and installer's protocol template with consistent manual inspection guidance.
