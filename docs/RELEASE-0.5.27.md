# Unio 0.5.27 — recovery and checkpoint maintenance

Recovery and checkpoint-maintenance release scope; check the official tag for publication status.

This update helps an operator recover useful context from a failed task and
manage protected checkpoint history without confusing preserved work with
accepted work.

## Changes

- Failed report-only runs can produce an explicitly incomplete handoff when
  the available report and declared artifacts still match their recorded
  binding. Original failures and missing delivery remain visible. Verification,
  review and readiness retain their success requirements.
- `unio save archive-worker WORKER --plan` previews an explicit archive action
  for one selected worker. Applying the current plan requires its hash and
  `--confirm-inactive`. Valid unclaimed saves, including that worker's latest,
  move to the archive with their IDs and contents preserved. Inspection and
  restoration continue to work. Other workers' protected history, pins,
  corrupt evidence and the ordinary automatic retention policy stay protected.
- Archive failures after a rename or during final bookkeeping report the
  observed moved, remaining or Unknown state. A missing outcome receipt is
  not described as a durable success. No automatic rollback or retry occurs.
- Compact worker and reviewer startup cards are packaged with the installer
  and copied by initialization when absent. Native prompts add a short role
  pointer while preserving the original task bytes. Existing custom project
  cards remain; the cards guide agents rather than sandbox their file access.
- Experience recording explains revision-binding changes more precisely,
  including a changed base. Real installed-workflow tests cover recording
  before and after integration. Use the original run configuration and record
  only a final assessment after review; conflicting assessments remain refused.

## Important limits

Archival frees active checkpoint slots, **not physical disk space**. Active and
archive bounds remain unchanged. The inactive confirmation is the caller's
assertion; an idle native lock cannot prove that no unmanaged process exists.
The command makes no provider call and is available while STOP closes new runs.
No benchmark evidence or owner checkpoint is automatically deleted.

A recovery handoff is context, not a backup or acceptance. A running or
interrupted task without a trustworthy terminal result remains Unknown and
may still refuse handoff. Unwritten work cannot be recovered by this feature;
arbitrary logs and ignored files are not scraped.

Customized startup guides are preserved during upgrades. A guide that predates
the cards can point explicitly to `WORKER-STARTUP-CARD.md` or
`REVIEWER-STARTUP-CARD.md` in project coordination docs or installed templates.
No measured token-saving claim is made.

The immutable experience store is for final assessments. Pending progress and
later corrections to prematurely recorded assessments need separate truthful
coordination notes; this update does not introduce an assessment-amendment API
or accept historical evidence as a fresh approval.

## Preparing correction tasks

Verification scopes the complete worker branch against the project base, not
only the commits made during the latest assignment. When a correction inherits
an earlier feature, its task must account for those inherited paths as well.
Use a separate frozen-start comparison when the worker may edit only a narrower
set of files. Keep an incorrectly scoped task's failure and establish a fresh,
explicit verification contract; do not silently rewrite its task or receipt.

## Validation and review

The complete `bash tools/quality-check.sh` gate passed with exit 0 on the frozen
combined candidate. Scoped independent current-code Mistral 4 reviews and the
lead assessment cover all included runtime changes. The corrected archive
suite passed 43 checks, legacy retention 29 checks and work-saving 186 checks in the
independent review, including a real same-worker save/restore smoke.

The original correction scope failure is preserved: its three validation
commands passed, but its task omitted two unchanged inherited paths. A
separate local whole-candidate verification proved the exact correction delta
and complete authorized scope, then passed its native gate without an AI call.

An isolated 0.5.27 installation passed version/help/license/policy checks and
created an incomplete recovery packet from an actual failed Fable audit.
The packet preserved Source exit 1, the missing-report label and false readiness;
original receipts stayed unchanged. The release package's provenance and
checksums identify the exact source and checks. Final delivery is recorded on
the official release page.

The first combined gate stopped on a three-second admission diagnostic fixture.
A focused test-bound correction preserved production behavior and strict
deadline/EOF distinctions; the historical delay cause remains unproven. The
original failed gate and worker operational failure are preserved separately.

The broader Fable product audit is separate and incomplete; its preliminary
static observations are not a whole-app approval or a demonstrated release
blocker. Desktop, phone, managed lead ownership, old private review-context
proposals and JSON-depth work are outside this release.
