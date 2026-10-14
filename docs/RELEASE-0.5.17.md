# Unio 0.5.17 — managed workers and safer project selection

Unio refuses accidental project selection when commands run inside an unrelated
nested Git repository. Mode, tier, lead/account settings and stop/resume refuse
before changing the enclosing workspace. Normal main/worker subdirectories,
physical paths, logical shell symlinks and initialized inner workspaces keep
working. A copied worker marker outside the supported layout grants no bypass.
Direct-child clones and direct wt/ children retain legacy allowance.
This is a layout guard, not repository authentication or an OS sandbox.

## Managed Codex workers

Opt in to a managed Codex Source using the existing ChatGPT CLI sign-in. It binds
its private local control channel to the real admitted task, worker, process and
slot, streams output, preserves the worker exit and cleans up its own channel.
Starting sandbox and approval choices are explicit; omission preserves inherited
settings. Legacy exec workers remain supported.

The experimental worker-effort command inspects this owned Source and requests
supported future-turn effort settings. It cannot change model, permissions or
service tier. A current inference change is not established, and a single-turn
Source can finish before a pending setting is used. Select starting effort in
the alias for the actual task. Read the [setup and boundaries](WORKER-EFFORT.md).
This is a managed-worker/control-channel foundation, not universal live tuning.

Offline installed checks cover ownership, malformed requests, cancellation,
long paths, startup choices and exit preservation. A genuine writable Source
created and committed its requested file, passed verification and acknowledged
a same-level low request. Cross-level requests were tested offline only.
The earlier inherited-read-only write attempt remains unaccepted evidence.

## Recovery and validation

A local storage audit found 34 valid snapshots and one empty duplicate archive
reservation. Only that empty wrapper was reversibly quarantined; saved content
and historical receipts stayed intact. Read the [operator findings](development/SAVE-STORE-RECOVERY-2026-10-14.md).
This was manual local recovery, not a new automatic repair command. Successful
new baselines used an explicitly selected 300-second capture budget; default
30-second success on this populated store remains unproven.

Root-guard implementation used Mistral subscription / Vibe2.26.1 / GLM5.3 high.
The lead found two missed cases despite passing tests; a dedicated ChatGPT /
Codex0.162.1 / GPT-6.1 Sol high correction added the fixes and regressions.
Copilot Free / CLI1.0.95 / Auto Balance drafted the recovery note. Its underlying
model/lab is Unknown. Managed-backend work used the earlier scoped Sol low trial.
Effective identities/efforts and remaining allowances stay Unknown. No additional
AI reviewer fleet was invoked under the owner's YOLO policy.

The final bundle requires one full frozen-source gate, exact artifact smoke,
0.5.16 upgrade/restore, installation checks and official download hashes.
Completed delivery is recorded separately in the [handoff](development/continue-with-ai-prompt.md).

The first combined gate stopped on the command-audit test's dirname shim: it
missed an optional -- before the operand, escaped fixture traversal, and called
MOCK Git. One separation assertion caused eleven subsequent canary failures.
Source and global installation stayed unchanged. A dedicated ChatGPT/Codex
GPT-6.1 Sol high correction60489a9 fixed only that fixture and its regression;
all18audit tests and native verification3/3 passed. The failed gate is retained
beside the fresh final-source release gate. No runtime check was weakened.
