# Unio 0.5.24 — operational quality of life (unreleased candidate)

Recorded 2026-10-25T06:20:05+01:00. This is a private candidate, not a published release.
Official/main/installed stable remains0.5.23. Publication, main push and global
installation require owner authorization.

## SUMMARY

Improve how existing Unio runs operate before managed lead ownership, dashboard
expansion, phone pairing or native desktop work. The candidate focuses on truthful
review results, reduced checkpoint bookkeeping, bounded assessment observation
and useful foreground run diagnostics.

## ITEMS LANDED

- Review-dispatch/history fixes preserve original attempts and current change
  requests, and prevent a newly refused batch from borrowing historical approval
  to claim successful dispatch. Independent component audits and the foundation
  quality gate passed.
- Checkpoint metadata reuse under the real store lock removes one redundant
  traversal, preserving corruption handling, retention, pins and restore.
  Focused78/31/29/186checks, independent reviews and combined94d29082 gate passed.
- Experience record --timeout accepts1..300/default30 without relaxing result
  freshness or record rules. Native4PASS with13experience/15fleet tests, independent
  Opus5.5XHIGH approval and lead byte proof passed. One real lookup succeeded
  in46.58s with120s after earlier30s timeouts; additional assessments succeeded
  in45–53s. These are bounded observations, not controlled speedup benchmarks.
- Human foreground phase lines distinguish checkpoint attempts, provider command
  completion, cleanup and finalization. Native checks include12kill cases and
  52native-stop checks plus phase/branding regressions. A first shared-FD defect
  was reproduced by the lead, corrected by SolLOW and approved in a fresh
  independent Opus5.5XHIGH review.

All four pieces are privately integrated. The final whole merged0.5.24 quality
gate is pending. See [batch evidence](development/OPERATIONAL-QUALITY-2026-10-25.md).
An approval, passing test or process exit never grants human acceptance.

## ITEMS DEFERRED + WHY

- Remaining mounted-filesystem full-save deadlines and broader helper/route
  visibility need separately measured work; these fixes do not cure all delays.
- Effort-capability reporting, bounded enclosing review context, explicit asset
  delivery and cross-workspace account visibility remain operational backlog.
- Owned lead launch/lifecycle and interface/platform expansion are deferred by
  owner priority. Reviewed internal core/RPC components remain preserved, with
  no claim of an installed persistent lead session.

## FILES CHANGED

Runtime and checks include unio-install.sh, tools/model-experience.py,
tests/unio-model-experience.py, tests/unio-run-phases.py, review collection/
selftest checks and the quality gate registration. Operating guides and changelog
fragments retain individual scope/evidence. The exact revision and tree are
frozen in the local final-gate receipt before execution.

## RISKS

Automatic captures can still exceed configured budgets. Increasing an observation
bound gives an explicit longer wait, not faster execution or permission to skip
checks. Run phases are best effort: background-b discards them, sockets/non-TTY
devices may drop them, and regular-file I/O has no hard latency guarantee.
Model/effort settings and scores are requested/operator-reported; effective
identity and unobserved capacity remain Unknown. Cross-workspace native account
counts and complete managed lead ownership are not implemented.

## NEEDS-REVIEW

Finish the frozen full quality gate and final lead assessment. Then prepare
reviewable release/install artifacts; do not publish, push main or replace the
global runner without explicit owner authorization. No further feature is added
to the frozen candidate.
