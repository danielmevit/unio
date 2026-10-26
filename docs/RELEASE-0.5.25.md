# Unio 0.5.25 — checkpoint lookup and worker-effort clarity

Prepared for owner-authorized delivery on 2026-10-26. Both runtime components
and the mechanical release preparation passed independent review and lead
assessment. The one combined quality gate passed (actual exit 0). The installed
0.5.25 CLI passed version, help, license and policy checks before publication;
routing, owner workflow and 15 customized templates were preserved.
Runtime functions and tests match the accepted, gated composition.

## SUMMARY

Two accepted runtime changes, plus release preparation only:

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
  assessment. Exact review and gate receipt hashes are recorded in provenance.
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

## DELIVERY EVIDENCE

The lead's one full combined gate passed on frozen commit `aa5e6d0` (installer
SHA-256 `edbd7c95b6735168b93581939a32934206fa4803b83a380fa59e1361d9d26691`).
Documentation-only status reconciliation does not change runtime or test bytes.
The packaged standalone installer passed isolated install/version/help/license
and embedded-file checks; global binary and configuration remained unchanged.
The actual gate exit was 0 (reported elapsed 78.0 minutes), with tracked source unchanged
and no untracked files in the isolated clone. The full log and dated receipt are
preserved in the private workspace. No real provider was called by the gate.
The owner authorized official publication, main push and local installation.
The installed binary matches the tested standalone payload. Six release files
include an exact Git source archive, installer, license, notice, provenance and
checksums. Publication and official-download results are recorded separately
from build/test acceptance; the immutable package describes its preparation state.
