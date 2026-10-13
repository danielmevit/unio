# Automatic-save helper findings — 2026-10-13

Task `AUTO-SAVE-HELPER-SOL-1`: existing ChatGPT subscription / Codex CLI
0.162.1 / requested `gpt-6.1-sol` / high. Effective model, effort and
allowance are Unknown. Lead acceptance is pending. Full measurements and
preserved failures are in the task's private workspace.

## Historical evidence

Mistral subscription / Vibe 2.26.1 / requested `zai-glm-5-3` / high returned
Source, adapter and native exit 3 at a local cumulative token cap, not measured
subscription exhaustion. Its controller reported five helper exits of -9
and one unstable-byte refusal with helper exit 1.

Antigravity / agy 1.3.3 / requested `gemini-3.1-pro-high` / high returned
Source, adapter and native exit 0. Its controller reported 18 helper exits
of -9. Effective model/effort remain Unknown for both routes. Neither latest
save-attempt record identifies a last good snapshot. Git commits survived;
that does not establish save success or lead acceptance.

Helper exit -9 means SIGKILL. Historical logs lack the sender, capture phase,
capture elapsed time and contemporaneous resource evidence. Historical root
cause remains Unknown; the original receipts and save evidence are unchanged.

## Offline reproduction

An isolated clone reads the same Git history and owns separate refs, index,
worktrees and configuration. The matched tree has 400 paths, approximately
5.44 MB of tracked content and 1,024 ignored generated files. Periodic/final
cases add two mock commits and staged/unstaged changes. The populated store
has one fixture baseline plus 31 synthetic, content-valid saves of 250 paths
and approximately 3 MB each. No AI call or original-save mutation was made.

| Capture | Store | Controller elapsed | Helper result |
| --- | --- | ---: | --- |
| Baseline | Empty | 27.60 s | 0; verified snapshot published |
| Baseline | 32 saves | 42.35 s | -9; prior baseline retained |
| Periodic | 32 saves | 41.47 s | -9; prior baseline retained |
| Final, supplied exit 0 | 32 saves | 43.63 s | -9; prior baseline retained |

In each populated-store case the controller sent TERM at 30.04–30.05 seconds
while retention validation was active, then SIGKILL at 31.04–31.06 seconds.
Baseline/final had entered failure bookkeeping by SIGKILL. After reaping,
the controller spent another 10.34–12.50 seconds scanning metadata and
recording failure. Separately, read-only metadata validation of the original
32-save store took 12.71 seconds. Recorded helper RSS stayed below 54 MiB;
initial available host memory exceeded 5 GB. Available kernel logs showed
no OOM kill, which cannot rule out a historical resource kill.

The native mock smoke run also failed all three captures with -9 while
preserving actual Source/native/structured process exit 23, the previous
content-valid save, source HEAD/index and released worker/account ownership.
Its Source was an offline Python script, not a provider invocation.

These individual measurements include filesystem/cache variation and trace
overhead. They establish a controller deadline kill under the mounted Windows
filesystem workload, consistent with the historical symptoms. They do not
identify the historical sender or establish a new regression: the entire save
helper is byte-identical at the historical base, 0.5.12 release and frozen
0.5.13 base.

## Disposition and next action

No implementation correction is applied: the measured workload exceeds the
fixed capture bound, and stopping/reaping retains the prior snapshot. The
table compares workloads, not a before/after code repair. No timeout, integrity
check, secret filter or save-retention rule was changed.

Keep regular scoped Git checkpoints and inspect the actual last good save
before relying on automatic recovery. Next, repeat these three captures with
a disposable matched repository and synthetic store on the host's native
Linux filesystem, using isolated installation/configuration. Record phase
latency, controller signals, memory events and I/O; preserve the original
workspace throughout. That storage comparison has not been measured here.
If it still exceeds the bound, scope a separate repair for repeated store
validation and bounded failure bookkeeping, retaining corrupt-evidence,
last-good, archive-collision, cancellation and index-safety regressions.

## Validation

Installer syntax and six directory-walk tests passed. Frozen manual and
automatic save suites are still running; final results will be recorded before
handoff. The lead owns acceptance and any release gate.
