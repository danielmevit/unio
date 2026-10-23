# Unio 0.5.23 — clearer admission, reviews and delivery

Owner-authorized release from the reviewed reliability candidate. The runtime
passed the complete quality gate; release preparation changes only documentation.
The independent Claude Code2.1.309 / requested Opus5.5 XHIGH review approved the
runtime, followed by the existing lead's assessment. Effective serving identity
and effort remain Unknown without independent attestation.

## Changes

- Configure admission with `UNIO_ADMISSION_TIMEOUT`:1–300seconds, default30.
  Distinguish deadline, EOF, partial reply, holder, storage and capacity failures.
  Preserve atomic account slots, STOP, owner grants and no provider call after
  failed admission.
- Observe current reviews separately from historical records, structured findings
  completeness and human acceptance. Stale approvals stay stale. A verdict alone
  does not establish readiness.
- Declare optional required text artifacts bound to the actual Source, task,
  command and revision. Missing or changed delivery fails verification separately
  from the real process exit; partial artifacts and original failures remain.
- Support linked user configuration, wider collection reviewer IDs and readable
  Source results when configuration observation fails. Artifact reads and public
  HTTP input rules remain strict.
- Avoid constructing review material for unreviewed result observations. Reviewed
  evidence retains closing revision, configuration and stream checks. Explicit
  review diagnostics still expose material hashes before a review exists.
- Retain the first managed-session CLI slice: bounded status/output and idempotent
  steering of an already authorized active turn. It adds no automatic new turn,
  retry or lead takeover.
- Document the owner's personal workflow across projects using Unio: one
  independent external reviewer plus the existing lead's final assessment.
  Codex leads prefer eligible Opus5.5 XHIGH; account reservations and holds remain.

## Evidence

The full `bash tools/quality-check.sh` passed on exact `a936848`, exit0, in
2975.855seconds on2026-10-23. The isolated clone remained clean; the gate made no
real provider calls. Separate native task verifications and meaningful regression
checks passed. Earlier failed calls, gates and reviews remain preserved.

Independent approval covers runtime `2fa351b`. The later generated installer
change only copies two already-reviewed canonical guide bodies; every other
installer byte is identical. No review receipt is rewritten for another revision.
The lead verified the actual deltas and disclosed all12 nonblocking observations.

An owned `/mnt/d` observation returned corrected results in8.322/7.811seconds
versus a same-pass0.5.22 baseline of11.875/7.934seconds. Load changed from the
earlier failing observation, so this is neither a general speedup ratio nor a
guarantee for every reviewed history.

Delivery follows the existing checked flow: reproducible artifacts, isolated
installation/selftest, prior-version upgrade and explicit rollback, preserved
configuration/operator templates, installation before publication, then official
download hash verification. Its dated receipts remain local; publication status
comes from the official GitHub release rather than this preparation document.

## Known limits

Conservative same-revision recovery remains: a pre-provider refusal or context-less
legacy review can keep readiness false after a later approval. Large reviewed
histories can exceed consumer time/size limits. These are the first follow-ups;
no automatic retries, history deletion or fake commits were added to evade them.

Required artifacts are opt-in UTF-8 text, use the exact documented heading and
require the route to write `UNIO_DELIVERY_DIR`. Remaining UI consumers, per-artifact
diagnostics, broader analysis/binary contracts and explicit history supersession
need separately validated changes. Runtime support remains Linux/WSL; full managed
lead ownership, phone access, native Windows and macOS follow later.

See the [candidate evidence](development/RELIABILITY-0.5.23-CANDIDATE.md),
[field dispositions](development/VECTO-RELIABILITY-2026-10-21.md),
[admission guide](development/ADMISSION-DEADLINES.md),
[review status](development/REVIEW-STATUS.md) and
[required delivery](development/REQUIRED-DELIVERY.md).
