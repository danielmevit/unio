# Unio 0.5.34 — reliable worker launches and clearer failure reports

The release candidate makes it easier to see whether a worker started, what exit belonged to an attempt and what stopped verification. The full release gate and installation are pending.

## Start and wait for a worker

After preparing a task as usual, run `unio run -b WORKER TASK`. A successful startup acknowledgement can be followed by immediate completion. Use `unio wait TASK --timeout 30` to retrieve the recorded exit even if the worker finished before you started waiting. If the runner could not establish startup or the attempt's exit can't be proven, Unio reports Unknown.

You can wait for several tasks together or use `--any` for the first completion. The timeout stops the wait. Workers continue separately. Full command examples are in the [CLI quick reference](CLI-QUICK-REFERENCE.md).

## Diagnose worker failures

The saved task report records the actual exit. When the worktree has an interrupted Git operation or unmerged files, the report displays the observed state so you can inspect it. When output suggests a quota or balance problem, the report labels the clue as suspected. You may need more than the default number of lines to see it. Try `unio report TASK 100`. Provider hints alone do not change availability holds. [Capacity and stop reasons](PROVIDER-CAPACITY.md)

If verification requires the existing run ledger and encounters a malformed row, it reports the ledger path, line number and error type. The original ledger remains available for inspection. Valid persisted Source evidence retains its normal behavior.

## Review and validation

Antigravity subscription / agy 1.5.14 / Gemini 4 Hydrogen Medium and Mistral subscription / Vibe 3.1.3 provided scoped implementation and independent reviews. The existing lead assessed the exact changes and reran targeted offline cases. The wait implementation was recovered from a timed-out Mistral 4 High run. Native verification on the preserved revision passed separately, and an independent reviewer approved the preserved changes. The original run remains recorded as incomplete.

## Follow-up work

The registered worker-branch check and commit-by-commit scope enforcement are separate changes under development. Existing-session effort control and the proposed Rust supervisor follow this worker reliability work. [Development roadmap](development/ROADMAP.md)
