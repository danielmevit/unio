# Automatic-save helper investigation — 2026-10-13

Task: `AUTO-SAVE-HELPER-SOL-1`. Implementation route: existing ChatGPT
subscription, Codex CLI 0.162.1, requested `gpt-6.1-sol` / high. Effective
model, effort and allowance are Unknown. Lead acceptance is pending.

## Preserved historical evidence

The Mistral subscription / Vibe 2.26.1 / requested `zai-glm-5-3` / high
Source returned 3 at its local cumulative token cap. Native exit was also 3;
this is not measured subscription exhaustion. Its controller reported five
helper exits of -9 and one unstable-byte refusal with helper exit 1.

The Antigravity / agy 1.3.3 / requested `gemini-3.1-pro-high` / high
replacement Source, adapter and native run returned 0. Its controller reported
18 helper exits of -9. Requested model/effort remain distinct from effective
Unknown settings. Neither worker's latest save-attempt record identifies a
last good snapshot. Surviving Git commits do not establish save success;
Source completion and subsequent lead acceptance are separate outcomes.

A negative helper exit of -9 means SIGKILL. Those historical controller logs
do not identify the sender, capture phase, elapsed capture time or kernel
resource evidence. Historical root cause is therefore not yet established.

## Initial measurement

The historical task trees contain 400–405 tracked paths and approximately
5.44–5.58 MB of file content. The existing active save store has 32 snapshots
with 236–263 paths apiece. A read-only metadata validation of that store on
the mounted Windows filesystem took 12.71 seconds. This operation validates
stored file types, modes and sizes; it does not establish content integrity.
Current capture publication repeats metadata validation and deep validation
of older saves, and failure reporting scans the store again. This is a
measured cost and a reproduction target, not proof of the historical kill.

Full private receipts, measurements and the disposable workload remain in the
task's private workspace. Original run receipts and save evidence are retained.
