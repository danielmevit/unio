# Required delivery correction — 0.5.23 unreleased

Route: existing ChatGPT subscription / Codex CLI **0.163.0** (verified with
`codex --version`) / requested **gpt-6.1-sol / low**. Effective model identity
and effort remain **Unknown**. Task type: implementation. One dedicated worker;
no additional providers or subagents were invoked. All validation was mock-only.

Frozen base: `23bb4597e118f7a2c4674dec2acbef388b9fe629`.
First explicit dated receipt: **2026-10-22T22:47:42+02:00**. Earlier inspection
was not timed. End receipt: **2026-10-23T00:12:50.274440+02:00**.
Measured receipt span: **5108.274 seconds**; this is wall time,
not provider inference time or measured token use. Wall timestamps diverged
from monotonic check timers during the run (see the raw start/end/elapsed
receipts). The entire worker elapsed time is therefore not reliably measured;
use the per-command monotonic/suite durations below.

## Delivered implementation

- Reserve root engine metadata names, case aliases and prefix collisions before
  Source; retain strict opt-in declarations and undeclared legacy behavior.
- Exclusively create fresh delivery directories; retain immutable dispatch binding
  and prompt. Validate schema, worker/task/run/command/task hash, dispatch revision,
  existing outcome provenance, current command, metadata identity and exact bytes.
- Walk all evidence path components without following symlinks. Bound nonblocking
  reads to owned, singly-linked regular UTF-8/NUL-free files. Detect replacement
  and byte/stat drift. Use safe exclusive metadata and handoff destination writes.
- Preserve native Source exits (mock observations include 0, 7 and timeout 124).
  Missing required output fails aggregate validation independently, gates review,
  and saves the delivery reason in the report. Retain bounded partials as incomplete;
  changed or vanished observed output is stale. No semantic report classifier.
- Recheck material and handoff evidence; include complete bounded artifact, binding
  and prompt bytes or refuse. Supply current delivery environment to separate verify
  and clear inherited delivery variables for undeclared tasks. Refuse unsafe
  delivery before exposing validation paths or executing validation commands.
- Add installed mock regressions, private TMPDIR/project fixtures, parent process
  bounds and the delivery suite in `tools/quality-check.sh`. Update the guide and
  regenerate affected embedded helper/guide copies. Keep B projection/config
  freshness and implementation/report-only gates intact.

Implementation checkpoints: `31bbea9`, `6e3a7f3`, `ba155dc`, `3d8c4dc`,
`ed858a5`, `045ea05`, `22dc4a4`, and guide update `ed3cebc`. Validation
below identifies each tested revision. Changes after `ba155dc` are delivery-only
saved-report, schema/identity, validation preflight and safe
handoff destination corrections. Unchanged adapter, undeclared outcome and B
coherence/branding checks are retained rather than falsely relabelled as reruns.

## Actual validation

Elapsed values below are measured parent-command seconds, except the two focused
rows which use unittest suite seconds. Every row completed with exit 0.

| Command | Revision | Exit | Count | Elapsed seconds |
| --- | --- | ---: | --- | ---: |
| `bash -n unio-install.sh` | `ed3cebc` | 0 | 1 command | 0.108 |
| `python3 -B tools/embed-task-outcomes.py --check` | `ed3cebc` | 0 | 1 command | 0.162 |
| `python3 -B tools/embed-adapters.py --check` | `ed3cebc` | 0 | 1 command | 0.384 |
| `python3 -B tests/unio-adapter-outcome.py` | `ba155dc` | 0 | 10 tests | 57.23 |
| `python3 -B tests/unio-required-delivery.py` | `ed858a5` | 0 | 29 tests | 1336.774 |
| `python3 -B tests/unio-task-outcomes.py` | `ba155dc` | 0 | 15 tests | 755.595 |
| `python3 -B tests/unio-review-coherence.py` | `ba155dc` | 0 | 5 tests | 392.594 |
| `bash tests/unio-branding.sh` | `ba155dc` | 0 | 1 shell suite | 116.127 |
| `python3 -B tests/unio-required-delivery.py` (5 selected methods; exact argv in focused-final.json) | `045ea05` | 0 | 5 tests | 349.248 |
| `python3 -B tests/unio-required-delivery.py RequiredDeliveryIntegration.test_source_missing_artifact_incomplete_delivery` | `22dc4a4` | 0 | 1 test | 53.796 |

`git diff --check` also passed on the final implementation. The complete final
delivery suite ran 29 tests in 1336.502 seconds inside its runner on ed858a5.
Afterward, five focused tests on 045ea05 cover the preflight change, and one
focused test on 22dc4a4 covers blocked-validation reporting. The entire 29-test
suite was not rerun after those last preflight/reporting changes. This is a
validation limitation, not a claim that all 29 ran on the final revision.
The isolated corrected mutation regression passed 1 test in 264.814 seconds
on `3d8c4dc` before the final full delivery rerun.

## Preserved failures and superseded checks

- Frozen `23bb459` baseline: two selected regressions failed as expected in
  67.263 seconds: ancestor-symlink reading was allowed, and installed verify
  returned 0 for missing required output. The baseline wrapper exited 0 only
  because it explicitly required those two failures; this is not a passing baseline.
- Initial coherent checkpoint: 20 delivery tests passed in 549.692 seconds.
- Initial branding attempt: overall exit 1 / nested installer exit 2 while the
  installer was being regenerated. Its precise root cause was not isolated.
  The preserved static-candidate rerun passed; the original failure is retained.
- Expanded `ba155dc` delivery run: 28 tests / 1 failure / exit 1, suite time
  1121.495 seconds. It found the missing saved delivery reason. An isolated
  reproduction also failed 1 test in 164.903 seconds; `3d8c4dc` fixed it.
- Two partial check batches were intentionally stopped when superseded by code
  corrections. Their logs and interruption receipts remain separate; neither
  is claimed passing. Isolated disposable fixture trees may remain under TMPDIR.
- Original C Mistral subscription GLM/Medium infrastructure failures and Gemini
  terminalERROR remain historical failures. Their CLI/version/effective settings
  were not reverified here. Saved Gemini `23bb459` is still unaccepted. No peer
  review conclusions were used to implement this correction.

## Handoff and limits

Raw dated receipts, logs, baseline fixture and check scripts are preserved at:
`/mnt/d/Vibe Coding/_vm/unio/tmp/unio-next/vecto-reliability-20261021/delivery-sol-correction-low-launchfix-20261022/fixtures/delivery-correction-receipts-20261022-001250`.

Lead acceptance: **not-recorded / Unknown**. Human: **pending**. The outer
Unio worker Source exit is recorded by the caller after return; it is not yet
observable from inside this worker. Mock Source exits and check exits above
are actual observations, not acceptance.

No full hour gate, independent provider reviews, push, release, global install,
Vecto change, auth/billing/account mapping/STOP/tier/grant change was performed.
Installed global 0.5.22 was not modified. 0.5.23 remains unreleased. The lead owns
its separate full gate, required independent reviews, assessment and integration.
This contract covers explicit bounded text artifacts only.
