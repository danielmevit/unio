# Functionality first: milestone review and delivery plan

Current delivery update, 2026-10-11: v0.5.9 is published and installed. Recovery,
packaged browser startup, manual capacity, Codex refresh, the managed dashboard
and optional subscription adapters have shipped. Perplexity account-backed
proposal trials are complete. Recovery archival/usage and cached Claude sign-in
are candidates for v0.5.10; the checked save-performance probe and CLI fleet
overview follow in v0.5.11. The read-only task planner and measured save-engine
optimization remain next functional work. See the [roadmap](ROADMAP.md) for current scope
and the [version plan](../VERSION-PLAN.md) for publication status. The audit
below preserves its 2026-10-08 baseline; its counts and pending statements are
historical.

Recorded 2026-10-08 at the owner's request. This is a source-backed audit and
recommended delivery order. It preserves the approved v0.5.4 recovery scope;
later release numbers and expanded implementation contracts are not assigned.
The current baseline is main `2263931` and published/installed v0.5.3.

Progress after this audit, 2026-10-08: the owner approved functionality first
and deferred UI work and optimization. Automatic native-run saving is now
[accepted in main](https://github.com/danielmevit/unio/commit/01be5a5eb5ef8e314060b7362423d0c47138a6a0),
with baseline, changed periodic and final captures, exact recovery and bounded
cancellation cleanup. [One authorized continuation](https://github.com/danielmevit/unio/commit/940d0dd35dd377c4c7423c88906ea0ae600d899c)
is now accepted too: explicit restore, separate new-task authority and durable
replay protection. The first [lead cooldown runtime](../LEAD-COOLDOWN.md) is now
accepted in source, with offline lifecycle checks, an actual read-only quota
probe and local CLI/configuration compatibility. Real subscription-limit restart
acceptance and the combined v0.5.4 release checks remain. Published/installed
v0.5.3 is unchanged.
The audit counts below describe the earlier baseline, before this delivery.

Validation update, 2026-10-08: see [completed checks, preserved failures and
remaining release work](RECOVERY-ACCEPTANCE-2026-10-08.md). Component coverage does
not replace the final versioned release gate.

## Where the original plan stands

The [five steps approved on 2026-10-05](../NEXT-MILESTONE-CONTRACTS.md)
followed the completed Unio rename:

| Original step | Actual state | What remains |
| --- | --- | --- |
| Limit-policy hardening | Shipped in v0.5.1 | New capacity monitoring is separate; heuristic limit text is still not a trusted account reading. |
| Queue approval, reservation and recovery | Shipped in v0.5.2 | Automated selection of ready dependent tasks is additional product work. |
| Real browser-to-worker workflow | Shipped in v0.5.3 | A simpler packaged launch/setup path and faster observation would improve daily use. |
| Checkpoint-based continuation | Implemented in main, unreleased | Saving, one authorized continuation and the first supported lead cooldown runtime exist; real subscription-limit restart acceptance and combined shipping checks remain. |
| Shipping preparation | Completed for v0.5.0–v0.5.3 | Required again on the completed v0.5.4 tree, then publication and installation. |

Work modes, shared-account tiers and native workflow admission also shipped in
v0.5.3. Model roles, effort guidance, bounded escalation and the curated task-fit
scoreboard exist as instructions. They do not implement an automatic scheduler,
live fleet allowance monitoring or model-specific routing recommendations.

Themes, responsive layout, the radial map, every-node details, status strips and
mouse navigation are accepted in main for v0.5.4. Manual and automatic native-run
saving, one authorized continuation and the first lead cooldown runtime are also in main.
Neither a source merge nor a local preview makes these part of installed v0.5.3.
See the [version plan](../VERSION-PLAN.md) and [current handoff](continue-with-ai-prompt.md).

## What caused the drift

The browser milestone grew to include work-policy controls, protected output and
files, prompt transport, launch accounting and installer upgrade corrections.
Some rework addressed demonstrated defects; the dated
[findings](FINDINGS-2026-10-07.md) preserve that evidence.

After v0.5.3, additional UI requests kept becoming immediate implementation work
while recovery remained unfinished. Of the nine feature merges after the release
source through `2263931`, six concern the dashboard/map, two concern manual saving,
and one concerns lead guidance. A separate merge froze the saving contract.
This describes the recent merge mix, not time spent or the value of each change.

The lead did not keep a firm recovery finish line visible. Instructions, research,
runtime features, source-only additions and published releases also accumulated
in the same roadmap, making progress hard to judge. More documents and successful
checks did not close the remaining continuation feature.

The UI additions are useful and complete. The next priority is reliable work
execution and recovery, with further visual redesign deferred.

## Recommended delivery order

| Priority | Milestone | Useful result | Finish condition |
| --- | --- | --- | --- |
| 1 | Finish recovery in v0.5.4 | Work survives interruptions and can continue without starting over. | Automatic baseline/periodic/final saves, one authorized continuation, one supported lead cooldown adapter, then the combined release gate, publication and verified installation. |
| 2 | Make everyday use straightforward and responsive | Start the correct browser workspace without assembling a Python command; status observation works on a larger project. | A packaged local launch entry point, clear active project/release/configuration, bounded observation and fewer repeated scans. Prove default launch on small and real larger workspaces. |
| 3 | Know worker readiness and shared allowance | The lead can decide whether a worker can take useful work before spending a call. | One account-based view of supported/manual five-hour and longer readings, source/age/reset/Unknown, native busy slots and local route/authentication diagnostics where supported. |
| 4 | Dispatch ready tasks while others run | One busy worker does not stall unrelated work. | Dependency and scope-aware ready queue, explainable assignment/idle reasons, dry-run recommendations, then owner-enabled single-attempt dispatch within existing account caps. |
| 5 | Make independent reviews a native workflow | Cross-lab review needs less custom orchestration and less lead bookkeeping. | Separate parallel review views of the same revision, structured findings and one aggregate result, with review planning governed by mode and owner policy. |
| 6 | Improve routing and context from actual outcomes | Choose suitable models and spend less context and rework per accepted change. | Extend the existing ledger/score with exact model/route/effort/task metadata, task-specific outcomes and transparent recommendations; missing usage stays Unknown. |

Each row is a product milestone with smaller bounded implementation slices. It
does not authorize one giant worker task. Allocate later versions when the exact
scope is frozen, rather than promising a release number for every idea.

### First: close recovery, in dependency order

1. **Automatic saving.** Extend the accepted manual format into native run
   supervision: baseline, changed periodic saves and final capture after exit,
   failure or interruption. Preserve the real provider exit and last good save.
   No final AI answer or voluntary commit is required.
2. **Authorized continuation.** Restore into a different clean idle worker and
   start one separately frozen task under current authority. Preserve source
   work, existing account limits, STOP and retry rules. Unknown/replayed claims
   must not start another provider call; restored edits must survive autosync.
3. **Lead cooldown restart.** Implement the frozen supervisor/adapter contract and deliver
   one supported lead CLI first. Persist waiting outside the AI session; use
   trusted reset evidence or the known five-hour fallback of five hours and one
   minute. Ordinary errors do not become cooldowns. Stop/completion prevents
   restart; a new lead reconciles existing tasks instead of redispatching them.
4. **Release the combined result.** Run the required full gate on the final
   tree, check packaging/upgrade preservation, publish v0.5.4 and install the
   verified release. Do not add another visual feature before this boundary.

The [saving contract](WORK-SAVING-CONTRACT.md) defines the first two slices.
The [lead cooldown plan](LEAD-COOLDOWN-RESTART.md) now has a frozen
[adapter/state/ownership contract](LEAD-COOLDOWN-CONTRACT.md). Its runtime and
offline acceptance are now in main; real subscription-limit restart remains
unrun while this low-tier lead session is active. Manual save corrections,
automatic saving and continuation passed focused checks. The combined source
gate exposed a stale completion assertion and embedded guide mismatch; both
received bounded corrections. Manual 186, automatic 61 and cooldown 106 checks
passed. Finish continuation full acceptance, then genuine restart and final
versioned release validation.

One existing functional issue belongs at release readiness: the real workspace
observation took 10.37 seconds against the default 10-second cutoff. A private
30-second preview override was initially needed. The source now defaults to
30 seconds and exposes a bounded `--observer-timeout` option (1–120 seconds).
Default HTTP observation on the actual workspace returned 200 in 9.754 seconds
after the correction; this proves availability, not a speed improvement. Wider
incremental-scan optimization belongs to priority2. See the [preserved finding](LIVE-WORKSPACE-VIEW.md#large-workspace-observation-follow-up).

### Then: usable coordination, with fewer wasted calls

Priority2 addresses an actual daily-use gap, not a new visual design. Package the
existing workspace and expose implemented controls; defer a broad Settings page.
Record default-launch timing and repeated-scan behavior before and after changes.

Priority3 combines the [allowance plan](../PROVIDER-QUOTA-MONITORING.md) with
connection readiness. Start with timestamped manual input and one verified
read-only adapter; recheck previously demonstrated interfaces at implementation.
Do not delay the whole feature until every provider has an automated meter.
Installed tools, account slots, authentication, remaining allowance and estimated
task cost are different facts. Diagnostics must not spend calls merely to poll
health or change billing/routing on missing information.

Priority4 extends the shipped queue, rather than replacing it. Begin with real
ready/blocked explanations, then bounded dispatch. Keep the existing lead as
planner. Follow [parallel-work policy](PARALLEL-WORK.md) and current tiers:
one independent workflow per shared account in low tier, including the lead.

Priority5 improves a core Unio benefit already available through manual/native
single reviews. It must respect [work modes](../WORK-MODES.md): YOLO uses focused
checks and personal lead review; medium adds independent review when warranted;
safe follows the project's broader review policy. Native parallel review support
does not force extra reviewers on every task or promise to find every defect.

Priority6 learns passively from useful work. Start recording supported metadata
as these milestones run; do not create a separate benchmark project. Task fit,
correction burden and accepted changes matter more than raw model output or
keeping every worker busy. Reuse the [model-experience design](MODEL-EXPERIENCE.md).

## Delivery discipline

- Keep one current milestone, its finish conditions and its next slice visible
  in the roadmap and handoff. Put new ideas in the appropriate later milestone.
  An owner-requested priority change should state what moves and why.
- Use coherent feature batches. Independent funded accounts may work on disjoint
  ready slices; one unfinished worker should not block unrelated authorized work.
  Never manufacture chores merely to fill idle slots.
- Keep this project's YOLO/low policy: focused checks for changed behavior,
  concise personal lead review, and one full required gate at the completed
  release boundary. Repeat or broaden checks for actual changes, failures or
  unresolved findings. Reuse unchanged evidence and keep failures intact.
- Main implementation roles remain Grok, Gemini/Antigravity, Claude and Codex.
  Observe actual availability, the Opus hold and the existing-lead budget slot.
  Verified-free workers are routine support, not feature owners or final approval.
- Report product outcomes and blockers. Source complete, checked, integrated,
  published and installed are separate states. Avoid speculative completion dates
  or quota estimates when the inputs are unknown.

Further Marathon styling, decorative animation, a desktop wrapper, hosted/team
features, new agent integrations, automatic review councils and a larger graph
are deferred. Reopen them for a concrete user need after the core milestones.
