# Unio 0.5.25 — checkpoint lookup and worker-effort clarity (unreleased)

Private release candidate prepared 2026-10-25. Both runtime components and the
mechanical release preparation passed independent review and lead assessment.
The single combined quality gate started on 2026-10-26 and is running;
publication, main push and global installation still require owner approval.
Runtime functions and tests are frozen at the accepted composition.

## SUMMARY

Two privately accepted runtime changes, plus release preparation only:

- Latest-checkpoint lookup (checkpoint `095b0d6`) validates requested-worker
  candidates from bounded manifest hints before visiting unrelated body pools,
  with bounded rechecks and a conservative fallback to the preserved original
  scan at most once. A genuine fallback refusal propagates exactly.
- Worker-effort clarity (final effort `d73a5b6`) surfaces truthful read-only
  configuration facts for `unio worker-effort WORKER [--json]` when no active
  supported control channel exists, explains channel absence and tags
  discovered configuration as future-launch provenance.

## EVIDENCE

- Both changes passed their native checks and focused suites, and each holds a
  current independent ClaudeCode2.1.310/Opus5.5XHIGH APPROVE plus lead
  assessment. Acceptance is private; no public review is claimed.
- Shallow (`deep=False`) lookup measurements on the 13-save D: fixture report
  medians 604→649ms with four bodies (slower), 1398→746ms with 41 bodies and
  9881→1465ms with 401 bodies, with complete file-operation counters retained
  in the lookup guide. These are local observations with uncontrolled caches,
  not controlled benchmarks.
- Isolated release checks for this candidate cover a private-tmpfs install of
  the assembled installer, `version`/`help`/`license` and the existing
  branding/template check, with zero provider calls.

## KNOWN LIMITS

- Deep (`deep=True`) lookup performance and full-save deadlines are unmeasured;
  the documented small-pool mounted-drive wall-time regression remains.
- Selection, validation, retention and STOP behavior are preserved and not
  re-proven for every mounted workspace.
- Effort status distinguishes current future-launch configuration from frozen
  startup settings, live channel state, pending requests and effective
  Unknown. No universal live-control, effective-model or quota claim is made;
  native effort control shipped in 0.5.17 and this release adds clarity only.
- An existing malformed deeply nested JSON RecursionError predates this
  candidate and is tracked separately; it is not fixed here. Generic
  evidence-failure wording and timeout cleanup remain backlog.
- Dashboard effort controls and UI remain planned future work.

## PENDING

The lead's one full combined gate runs on frozen commit `aa5e6d0` (installer
SHA-256 `edbd7c95b6735168b93581939a32934206fa4803b83a380fa59e1361d9d26691`).
Documentation-only status reconciliation does not change runtime or test bytes.
The packaged standalone installer passed isolated install/version/help/license
and embedded-file checks; global binary and configuration remained unchanged.
The gate's actual exit determines acceptance, followed by owner-authorized
public delivery. Until then the changelog heading stays `unreleased` so the
site does not advertise this version.
