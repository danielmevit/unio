# Unio 0.5.28 — installation and startup safety

The installation and startup-safety release passed its full combined quality
gate, independent scoped reviews, lead assessment and isolated installation
checks. Check the official tag and asset provenance for publication status.

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

Background Git-lock/Gitdir refusals append dated startup-refused explanations
to the task report and log for `unio report` and `unio tail`. A background
parent acknowledgement remains separate from provider execution, delivery,
verification, review and acceptance. The explanation says no provider started
and preserves original report/log content and canonical task results.
Writing a diagnostic remains best effort when its destination is unavailable.

## Assessment and validation

The complete `bash tools/quality-check.sh` gate passed with exit 0 on the frozen
combined candidate. Private installation passed version/help/license/policy
checks; its generated runtime exactly matches the packaged installer body.

Independent Mistral 4 review covers the earlier unchanged installer and Git-lock
safety code. Current Google/Gemini review covers the Z.ai/GLM-authored reporting
helper and startup call sites; current Z.ai/GLM review covers the Google-authored
portable-test corrections. The lead assessed the composition and proved the
unchanged regions and original safety assertions. The failed final Mistral 4
alias-selection attempt supplied no verdict and remains a setup failure.

Diagnostic report writes are best effort, not deadline-guaranteed. Current
regular-file checks are not an adversarial race sandbox. A startup-refusal
fragment does not invent a provider failure or replace canonical task results.
Original failed runs and reviews of earlier revisions remain preserved.

Fable's separate advisory assignment is to understand and score Unio as a
product, then recommend improvements. Implementation workers own reproduction,
regression and stress tests and fixes. The incomplete earlier audit is not a
whole-app approval or a prerequisite for this release.

Ownership/dashboard, phone, Windows and macOS expansion remain later work.
