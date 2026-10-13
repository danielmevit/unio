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

The diagnostic task applied no implementation correction: the measured workload exceeds the
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

## Configured-budget measurement

`SAVE-BUDGET-SOL-1` adds an operator-selected capture budget; it does not speed
up capture or weaken retained-history validation. The lead accepted the
diagnostic findings as the basis for this new implementation task. Route:
existing ChatGPT subscription / Codex CLI 0.162.1 / requested `gpt-6.1-sol` /
high; effective model, effort and allowance remain Unknown. Implementation
acceptance and the full release gate remain with the lead. No version bump,
release, global installation or owner configuration change is included.

Set `UNIO_SAVE_CAPTURE_TIMEOUT` to positive whole seconds **1–300**; unset
retains **30 seconds**. Invalid values refuse capture before save-store effects,
while read-only inspection/usage remain usable. Manual and automatic baseline,
periodic and final helpers use the same selected capture budget. Agent task
and restore timeouts, shared-account policy and STOP are unchanged. Cancellation
retains the original final-cleanup ceiling of thirty seconds and the one-second
helper escalation grace. See [capture time budget](../WORK-SAVING.md#capture-time-budget)
for commands and tradeoffs.

A new task-local copy of the existing diagnostic fixture was measured on the
same Windows-mounted filesystem: 400 worktree paths, approximately 5.44 MB of
tracked content, 1,024 ignored generated files, and the same initial 32
content-valid saves (one baseline plus 31 synthetic saves of 250 paths and
approximately 3 MB each). The worktree fingerprint was matched to the diagnostic
baseline before each capture. The frozen controller and the new controller ran
sequentially against that private store, using deliberate offline capture mocks;
no diagnostic script or additional provider/model call was executed.

| Baseline capture | Effective budget | Controller elapsed | Actual helper result |
| --- | ---: | ---: | --- |
| Frozen payload `1fa1c47`, default | 30 s | 40.36 s | -9; prior good snapshot retained |
| New payload `558f2de`, explicitly configured | 300 s | 217.33 s | 0; verified snapshot published, one eligible old save archived |

Before: controller TERM at 30.03 seconds, SIGKILL at 31.03 seconds, followed
by failure bookkeeping. After: no controller stop signal, complete old-save
validation and a new snapshot with the same fingerprint. The source HEAD and
raw index remained unchanged, and the previous good save remained content-valid.
The original diagnostic save files were read-only and their hashes were checked.
Raw profiles, stdout/stderr, receipts, fixture failures and reproduction mocks
are retained in private project tmp.

These are individual, instrumented measurements with filesystem/cache variation,
not a throughput benchmark or a historical-kill attribution. A larger budget
deliberately trades longer startup/final-save waits for a chance to complete slow
storage work; this example requires over three minutes despite succeeding.
The default safety bound remains thirty seconds. Failure bookkeeping and
escalation can add elapsed time beyond the selected capture deadline.

The existing automatic failure message now includes the real helper exit and
`capture deadline exceeded (N seconds)` only when the controller actually
initiates a deadline stop. External SIGKILL and Source exits are not relabeled.
Save/result schemas, prior snapshot bytes, integrity checks and retention rules
are unchanged. The new quality-gate suite passed **70 focused runtime checks**:
actual manual/native captures, changed configured outcomes, invalid input before
effects, honest deadline versus external-kill reasons, real exits, last-good
retention, real periodic capture and bounded cancellation. Installer syntax,
CLI environment-help smoke and unrelated-payload byte checks also passed.
The broad saving suites were not replayed during this implementation task.

## Validation

All frozen checks passed: installer syntax; 61 automatic-save checks; 186
manual-save checks; six directory-walk tests; and `git diff --check`. Tests used
task-local installation, configuration and temporary directories. No release
gate or extra AI invocation was started. Recommend accepting the diagnostic
findings; performance correction and historical attribution remain open. The
lead owns acceptance and any release gate.
