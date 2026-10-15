# Unio 0.5.19 — safer stopping and measured saving

A bounded recovery and compatibility release: stop the provider sessions Unio
started, avoid duplicate save validation, and accept real Copilot result metadata.

## What changes

- **Owned stopping:** cancellation and normal exit sweep nested process groups
  and reparented children within the recorded Linux provider session. Cleanup
  must be confirmed before the final save; unproved cleanup keeps the worker
  and shared-account slot held. Confirm completed cancellation after the runner
  removes its control files. Identity-checked pidfds protect the session sweep.
- **Reliable verification identity:** compare the task with its full
  engine-recorded dispatch revision, rather than hashes in provider output.
  Legacy results remain readable, but missing dispatch evidence refuses
  verification; old report prose is not a substitute for that evidence.
- **Concurrent ownership:** per-worker runtime records keep a refused or
  parallel same-task run from deleting another worker's controls. Public
  background controls select the latest published run without serializing
  provider execution.
- **One retention validation pass:** existing save contents are deeply validated
  once during classification, preserving corrupt evidence, newest saves, claim
  pins and retention caps. The default capture deadline is unchanged.
- **Copilot compatibility:** accept filename-string arrays, including `[]`, in
  CLI 1.0.95 `filesModified` metadata, plus legacy integer fixture counts. Exact
  root assistant text and strict malformed/ambiguous-result refusal remain.
- **Clearer operating guidance:** status covers the full fleet, including idle,
  benched and owner-reserved routes, with subscription/model/effort provenance.
  The roadmap includes selected Eqho transcript/history logic after the Windows
  desktop foundation; it will be reassessed against the owner's latest revision.

## Evidence and limits

Saving's isolated retention phase averaged 16.14 seconds before and 9.91 seconds
with the folded traversal on one fixture/host. Two complete captures per engine
showed no clear overall latency gain. See [the methods and limits](development/SAVE-PERFORMANCE.md).

Stopping uses offline generic-process fixtures, not a live-provider certification.
The recorded-session boundary is not an OS sandbox; processes that leave the
session remain unmanaged. Same-user ownership files are trusted local state,
not authentication against hostile same-user rewriting. See [the ownership contract](development/NATIVE-STOP-CONTRACT.md).

Copilot evidence includes native schema inspection, an exact offline replay of
an actual saved native stream and fake-CLI regressions. A fresh live call through
the corrected parser was not run. See [the result contract](integrations/COPILOT.md).

## Candidate evidence — 2026-10-15

Saving revision `91b97bb` passed native verification and independent
Antigravity/agy 1.3.5 / Gemini 3.8 Flash high review; the lead accepted it.
Copilot revision `721c56c` passed native verification. OpenCode Go /
OpenCode 1.18.35 / Qwen 3.8 Max xhigh requested documentation corrections;
the candidate resolves them without changing parser bytes. Its original
REQUEST-CHANGES verdict remains preserved with the lead's resolution.

Stopping revision `3bb3f5e` finished Source 0 through Antigravity/agy 1.3.5 /
Gemini 3.8 Flash high. Its focused fixtures passed, and an isolated mutation
restoring only the old cleanup ordering failed at the expected final-save
assertion. This is a mutation proof, not a full test of an old release.
All six native verification commands passed. The separate Qwen xhigh review
timed out without a verdict and supplies no approval. The combined installed
selftest later exposed a cancellation-confirmation race; a dedicated ChatGPT /
Codex 0.162.1 / Sol 6.1 high correction finished Source 0 with commits
`14ee672` and `8a47af1`. Its offline checks passed 52 stopping cases, 12 PID
safety cases and all 40 installed selftests, with old-fail/new-pass evidence.
Its six validation commands passed, but legacy native verification incorrectly
read a nested diagnostic hash and failed. The following full gate timed out
near concurrent loop-brake runs; neither result is rewritten as a pass.

A second dedicated ChatGPT / Codex 0.162.1 / Sol 6.1 high correction finished
Source 0 in 22m18s with `53882eb` and `de336b0`. It preserves the full dispatch
revision and isolates runtime ownership. Offline checks passed 12 identity,
38 loop-brake and 52 stopping cases. The bounded loop check passed in about
70 seconds in private tmpfs; a Windows-mounted-fixture timeout is preserved
separately. Current native verification, DeepSeek Go high review and the
corrected combined release gate remain pending.

The combined gate, installation and publication remain pending. Until they
finish, the official and installed release remains 0.5.18.
Original provider failures and saved partial work remain separate from later
accepted revisions. Effective model/effort and remaining allowances are Unknown.
