# Unio 0.5.28 — installation and startup safety

Unreleased candidate. Final corrections, current-code review and the required
combined gate are pending. A local version string is not a publication claim.

## Practical changes

The standalone installer refuses accidental sourcing before changing the
caller's shell or installing files. Its suggested command quotes paths with
spaces. Normal executed and pipe-to-Bash installation remain supported.

The main runtime is written to private staging on its destination filesystem
and published by replacing the file entry atomically. Existing open readers
keep the previous inode. A failure before publication leaves the old runtime
intact; a destination changed into a directory fails rather than nesting the
runtime and claiming success. Only this invocation's staging is cleaned.

Worker startup preserves an existing Git index lock, including a live writer's
lock or an entry of Unknown ownership. It refuses before provider invocation
and directs the operator to inspect the lock. Unio's worker lock does not
serialize interactive Git commands or other unmanaged writers.

See [installer guarantees](development/INSTALLER-SAFETY.md) and
[Git lock guidance](development/INDEX-LOCK-SAFETY.md).

## Limits

Atomic replacement applies to the main runtime, not the entire installation.
Generated helpers, configuration and templates still require idle maintenance.
The installer and worker worktrees are not operating-system sandboxes.

Existing Git locks are not automatically classified as stale or removed.
Investigate active Git writers before manually removing an abandoned lock.
No deadline-based release of Unknown process ownership is introduced here.

Background parent acknowledgement does not establish provider execution,
delivery, verification, review or acceptance. A focused visibility correction
is being prepared and is not yet part of an accepted release.

## Assessment and validation

The initial installer and Git-lock changes have independent current-code
review and lead reproduction evidence. The original installer review is
preserved alongside later lead-discovered defects and their correction;
approval was not transferred to changed code. Final followups need fresh
review and the one full combined quality gate before delivery.

The separate Fable assessment is advisory product and architecture work.
Fable first understands and scores the app, then recommends improvements.
Implementation workers own reproductions, regression tests and fixes. The
incomplete earlier audit is not a whole-app approval or release prerequisite.

Ownership/dashboard, phone, Windows and macOS expansion remain later work.
