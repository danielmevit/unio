# Sol low field trial — 2026-10-13

Four serial Source calls used the existing ChatGPT subscription through
Codex CLI 0.162.1, requesting GPT-6.1 Sol with low effort. The coordinating
lead was configured as GPT-6.1 Sol xhigh. Effective serving identity and
worker effort remained Unknown; requested settings are not serving telemetry.
Real shared-account mapping and the lead reservation stayed intact. One
worker ran at a time, using a recorded temporary medium coordination tier;
low was restored when idle. No extra AI reviewer fleet or paid API fallback.

## Actual outcomes

| Work | Provider elapsed | Lead outcome | Evidence |
| --- | ---: | --- | --- |
| Recovery saving | 54m 13s | Accepted | 29 performance checks and 6 traversal tests |
| Static command audit | 13m 0s | Needed fixture correction | 17 installed fixtures; two test-composition issues found in lead review |
| Audit fixture correction | 2m 17s | Accepted | 17 fixtures pass in worktree and minimal copied source; runtime unchanged |
| Worker effort control | 4m 55s | Incomplete; excluded | 4 packaging and 6 refusal checks; no managed backend or effort RPC |

Every Source and native run returned zero and its exact-revision machine
verification passed. Those facts did not establish feature completion:
the original audit needed a dedicated test correction, and the effort
prototype could only report unsupported/refuse requests. Original outcomes
remain separately recorded. The two accepted milestones ship together in
[v0.5.16](https://github.com/danielmevit/unio/releases/tag/v0.5.16); the
incomplete effort prototype stays on its development branch.

Saving retains complete content validation and both observations while doing
fewer repeated pathname checks. One comparable completed populated fixture
measured 304.93 seconds before and 249.01 seconds after. The first baseline
refused at its selected 300-second budget; both candidate captures completed.
Host I/O/cache variation is uncontrolled, and the default 30-second automatic
budget remains unsolved by this populated fixture. Read the
[measurement record](SAVE-PERFORMANCE.md) for individual observations and limits.

The [command audit](../WORKER-CONNECTIONS.md) inspects local configuration
without executing commands or checking provider readiness. A dedicated
correction made its tests honor caller temporary storage and replaced global
frozen-payload hashes with installed behavioral checks that allow future features.

The [effort-control plan](WORKER-EFFORT-CONTROL.md) still needs an owned managed
Source backend, private channel, native slot binding, actual RPC and supported
application-boundary evidence. Passing refusal checks does not complete it.
The assignment allowed a bounded partial result; future work should target
that concrete missing backend and preserve the current prototype.

## What this says about subscription efficiency

This was not a matched low-versus-high experiment. Dated shared Codex readings
went from 76% remaining at 20:59 to 66% at 21:11, 35% at 21:49 and 11% at 22:23, all local
UTC+02:00. They include the lead, workers and other activity on that subscription;
no per-worker allowance attribution or demonstrated low-effort savings follows.
Raw/cached token counts also do not establish a conversion to allowance.

The lead spent too much effort on coordination and repeated release preparation
before finishing delivery. Keep future scopes concrete, prompts compact and
handoffs clear. Commit early, inspect actual functionality, run focused checks
per task and one final combined gate per release. Preserve honest partial and
failed outcomes instead of promoting green checks into completed milestones.

Private original tasks, dated receipts, intermediate fixture failures and
metadata-probe harness errors stay in the operator workspace. No raw logs,
authentication material or account identifiers are published here.
