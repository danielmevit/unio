# Unio roadmap and development priorities

Current delivery,2026-10-19: [v0.5.22](https://github.com/danielmevit/unio/releases/tag/v0.5.22)
is published and installed. All seven operator-reliability improvements passed
independent code reviews, the complete gate and artifact/upgrade/install/download
checks. Next: resume the preserved managed live-session candidate and lead
continuity, then scoped phone access, native Windows before macOS. Windows
includes [app-managed trial expiry](WINDOWS-TRIALS.md), staged localization and
planned Store/winget distribution. Version numbers after22 remain provisional.


Current update, 2026-10-17: [v0.5.21](https://github.com/danielmevit/unio/releases/tag/v0.5.21)
adds a bounded scheduler for finite approved batches. It is published and installed,
with two independent current-code reviews, the full gate and download verification.
Next: managed CLI session ownership and continuity; then session-scoped phone access,
Windows before macOS. See [the version plan](../VERSION-PLAN.md).

## Operator reliability priority — 2026-10-19

Close the seven Vecto operator findings as one v0.5.22 reliability release:
usage/cap visibility, real route-contract validation, nonblocking tail, scope
annotations, blocked/report-only outcomes and early storage errors. All seven
are implemented; final gate/review and delivery are separate pending steps.
See the [round evidence](OPERATOR-LEGIBILITY-2026-10-19.md). Resume the preserved
managed-session candidate afterward, then lead continuity, scoped phone access,
Windows before macOS. The version table is provisional; no unfinished feature
is claimed shipped.

Your AIs, in sync.

Previous update, 2026-10-16: [v0.5.20](https://github.com/danielmevit/unio/releases/tag/v0.5.20)
is published and installed. It adds shared-lead allowance consent, optional
failed-work WIP commits, plain supported stop reasons and opt-in push policy.
Code, independent assessments and the complete quality gate passed. Delivery
installed before publication; reproducible artifacts, 40 isolated selftests,
0.5.19 upgrade/rollback, preserved configuration and all six official download
hashes passed. See [evidence and limits](../RELEASE-0.5.20.md).
UI, site, brand and the owner's separate projects are preserved.

Then continuous delegation, managed live sessions, lead continuity and scoped
phone access. Native Windows precedes macOS in the
[release outlook](RELEASE-OUTLOOK-0.5.19-0.5.24.md). Windows localization includes
Czech, Slovak and Balkan languages, with Serbian Latin only and no Montenegrin;
see the [staged plan](WINDOWS-LOCALIZATION.md).

The functional core includes recovery saving, shared-account policy and capacity
observations, managed daily startup, read-only planning, explicit single-attempt
dispatch, separate review receipts, concurrent collection and task-specific worker
experience. Proposal routes require implementation review. Genuine lead-limit
restart remains experimental/opt-in and unobserved. Retention measurements do
not establish a general full-save speedup or a default-budget guarantee.

Keep useful milestones bundled with one final combined gate. Further dashboard,
website and brand redesign remains lower priority than functional protections.
Earlier dated sections retain their historical context.

## Windows trial requirement — 2026-10-19

The Windows milestone includes [Unio-managed trial expiry](WINDOWS-TRIALS.md),
based on the owner's report that a one-day Store trial stayed usable after its
24-hour period. Enforce the selected trial policy at app/backend boundaries,
preserve work and test expiry/restart/reinstall/offline cases. This is planned
Windows work, not a shipped restriction in the current tool.

## Current focus: finish the functional core

Local save-store recovery is complete: 34 snapshots passed deep validation; only
one proven empty archive reservation was reversibly quarantined. Metadata usage
and subsequent explicit-budget baseline captures succeeded. See the
[operator record](SAVE-STORE-RECOVERY-2026-10-14.md); automatic repair and default
30-second success are not established.

The nested-project guard is accepted from9f62865 after Mistral/Vibe GLM high
implementation and a dedicated Sol high correction. Native and personal checks
cover the original mutation, copied markers and genuine Bash symlinks. See the
[dated findings](PROJECT-ROOT-GUARD-2026-10-14.md). The released0.5.17 combines
this with experimental managed Codex workers; combined gate and shipping checks
passed. Current-inference effort changes remain unfinished.


The owner requested a milestone review on 2026-10-08. The
[functionality-first plan](FUNCTIONALITY-FIRST-PLAN.md) compares the original
five steps with actual releases and source, explains the scope drift and sets
out the recommended order below. This front section is the current planning
entry point; dated history and the earlier priority list remain below.

Limit hardening, the queue and the real browser workflow shipped through
v0.5.3. Recovery shipped in v0.5.4: manual and automatic native-run saves,
one authorized continuation and the first supported lead cooldown runtime.
The browser launcher and work map shipped in v0.5.5; managed daily startup and
shared observation filters shipped in v0.5.7. Measured scan optimization and
responsive observation remain useful. Further visual polish should not displace
functional work.

The [first lead cooldown contract](LEAD-COOLDOWN-CONTRACT.md) is frozen:
Codex exec with a separate structured quota probe, durable ownership and
explicit launch controls. The [source runtime](../LEAD-COOLDOWN.md) now passes
offline acceptance and actual read-only quota/configuration checks. Combined
release checks passed; genuine subscription-limit restart remains unobserved,
as disclosed above. The lead reservation counts toward native tier limits. The
owner's dated Sol-low experiment permits one recorded temporary-medium admission
beside it; ordinary low-tier limits apply outside that scoped exception.

| Priority | Functional milestone | Current state |
| --- | --- | --- |
| Complete | v0.5.4 recovery, release and install | Published and installed after release checks. Genuine lead-limit restart remains unobserved; the feature is experimental and opt-in. |
| 2 | Simple daily use and measured performance | Launcher, daily-use guide, save probe and measured sibling-ignore batching shipped. Remaining real-history save/scan work still needs matched comparisons. |
| 3 — CLI slice shipped | Shared-account allowance and worker readiness | Native slots, manual readings and Codex refresh shipped. Cached Claude authentication shipped in 0.5.10; the shipped 0.5.11 fleet CLI combines local slots, bench/binary facts and cached observations. Other automatic provider readings remain planned. |
| 4 — CLI slice shipped | Ready-task dispatch and dependency handling | Read-only planner and explicit owner-granted single-attempt dispatch shipped in 0.5.11 after focused/native and release checks. Automatic scheduling remains planned. |
| 5 — collection slice shipped | Native independent review pipeline | Released 0.5.11 preserves separate receipts, summarizes exact-revision evidence and collects explicit reviewer sets concurrently. Structured finding aggregation shipped in 0.5.15. |
| 6 — CLI slice shipped | Evidence-based routing and context efficiency | 0.5.12 ships explicit revision assessments, task-specific profiles and conditional local advice. Automatic capture and routing remain planned. |
| 7 — newly requested | macOS and Windows host support | Linux/WSL is the current baseline. Native macOS and Windows need an audited host backend and actual platform acceptance; see the [cross-platform stages](CROSS-PLATFORM.md). |

The Vibe worker-progress slice shipped in v0.5.18: safe fixed labels
and a separate liveness heartbeat, with a genuine live field observation.

### Next useful slices

The optional [CodeGraph Bash evaluation](CODEGRAPH-BASH-EVALUATION-2026-10-12.md)
now has a locally corrected grammar with 32 selected checks, 100 upstream corpus
cases, 8 exact real-CLI boundaries and 7 chosen call links passing. Wider Bash
coverage and embedded-source indexing remain open. The owner has explicitly deferred further CodeGraph improvements. Keep its patch experimental;
it does not replace the functional priorities below or authorize a global
CodeGraph upgrade/index.

The completed scope through 0.5.15 is released and installed. After the
requested break and a new owner continuation, use the
[version plan](../VERSION-PLAN.md) and this order:

1. **Measured save reliability and performance:** sibling-ignore batching is shipped.
   The 2026-10-13 [diagnosis](AUTOSAVE-HELPER-2026-10-13.md) reproduced a controller
   deadline kill on a populated Windows-mounted store. Released and installed 0.5.14
   adds optional bounded capture budgets and honest deadline diagnostics. Its configured capture succeeded in 217.33 seconds, so
   performance remains a separate follow-up. Keep historical kill causes Unknown.
   Initial follow-up estimate: 2–4 hours for a measured bounded optimization slice;
   preserve complete old-save validation, failure evidence and last-good recovery.
2. **Worker connection reliability and effort control:** use the
   [dated route observations](WORKER-READINESS-2026-10-13.md) to validate model
   selectors, distinguish quota/access/deprecation errors, and address native
   transport retries without replaying failed tasks. Audit legacy operator
   configuration separately; do not silently overwrite it. Plan a bounded
   [per-worker effort-control slice](WORKER-EFFORT-CONTROL.md), initially 4–8 hours
   for Codex capability audit and supported request-boundary control. No live
   effort switch is implemented in 0.5.15.
3. **Lead continuity and phone access:** supported session attachment, lead transfer
   after a handoff, then scoped pairing and message delivery. These need session
   ownership and transport work; a local dashboard is not remote control.
4. **macOS and Windows:** finish the platform audit, make the existing WSL2 route
   reproducible, implement native Windows after a backend feasibility checkpoint,
   then port native macOS. Use actual host CI and save/restore checks before
   declaring support. The [interactive session workspace](SESSION-WORKSPACE.md)
   reuses the existing dashboard and engine.

The explicit dispatch slice reuses the existing queue's approval/reservation/
replay protections and rechecks native admission at launch. A previous plan
never acts as a reservation. Further dispatch automation is a separate scope.

Complete one bounded slice before assigning its dependent implementation.
Independent eligible accounts may work on separate ready scopes. Focused checks
and personal lead review are the current YOLO cadence; the full frozen-tree gate
remains required at publication. A source candidate, a release and an installed
version are separate states.

Later ordering is a recommendation from this audit; new version numbers and
task contracts follow bounded planning. Defer additional visual redesign,
a broad Settings page, general cloud expansion and model benchmark
campaigns. The owner-requested session-only phone connection below is a bounded
application feature, not a remote desktop. See the plan for concrete finish
conditions and the [handoff](continue-with-ai-prompt.md) for the next task.

Owner update, 2026-10-11: native macOS and Windows are now explicit delivery
milestones rather than an unspecified desktop expansion. Begin with the bounded
platform audit alongside independent functional work. A possible desktop app
should host the existing interface; it must not introduce a second orchestrator.
The owner is finishing small dashboard/site changes in a separate Opus session;
preserve those scopes while advancing the functional core here.

## Pair a phone with one live session

Owner-requested on 2026-10-09: [mobile session pairing](MOBILE-SESSION-COMPANION.md).
Scan a short-lived QR invitation, confirm on the PC, and grant access to the
selected Unio session. Use a mobile browser for progress, messages to the same
lead and separately authorized approvals. Make connections revocable and expire
access when the session ends. No dedicated Android app is required.

This remains planned. First define supported live-lead attachment and message
delivery; then implement pairing and remote transport. An outbound encrypted
relay is the proposed direction, with hosting/protocol still undecided. Do not
expose a general terminal or another project, create a second lead workflow,
or treat the existing loopback dashboard as a finished remote-control service.
Release number and placement among the remaining functional milestones are
unassigned; the complete plan records the boundaries and acceptance cases.

## Browser appearance and live work overview

Implemented in main on 2026-10-08 for v0.5.4: Light, Dark and System themes,
and an optional live map of workers and tasks. The [UI direction](LIVE-WORKSPACE-VIEW.md)
and [browser guide](../../bridge/README.md) describe grouped history, filters,
24-task pagination, stable exact selection and observation-backed details.
The map uses the existing two-second activity feed and worker/task ownership;
lead/dependency edges need future engine evidence. Focused browser checks and
personal lead review passed. The fluid layout now follows screen width, with
repository/license footer links and the approved “Your AIs, in sync.” tagline.
These theme/map additions shipped in v0.5.4. The launcher, left-to-right flow
and task-first logo cards shipped in v0.5.5; the managed dashboard and shared
filters shipped in v0.5.7. Recovery shipping is complete; prioritize the
functional queue before additional visual polish.

## Work modes and lead budget

On 2026-10-07 the owner approved [YOLO, medium and safe work modes](../WORK-MODES.md)
and separate low, medium and high subscription-budget tiers as core Unio
controls. Persistent CLI switches, visible policy and native shared-budget
workflow admission shipped in v0.5.3. Use YOLO + low tier for this project:
focused checks and personal lead review, with the full gate at release.
Browser selectors and automatic scheduling remain later improvements.

### Reasoning profile selector

Owner update, 2026-10-12: the review protocols are **YOLO / Balanced / Thorough**.
The 0.5.13 update accepts matching `yolo` / `balanced` / `thorough` commands,
with `medium`/`safe` kept as aliases and stored compatibility values. Startup offers
[YOLO, Balanced and Thorough](../ai/NEW-PROJECT-PROMPT.md), separately from
coordination tier and [Low, Medium and Max reasoning](../ai/REASONING-PROFILES.md).
The prompts default to low concurrency and Low. Owners can explicitly
opt another project into occasional supported max or the highest permitted
effort throughout; this does not change Unio development's xhigh ceiling.

Reasoning profiles are currently lead instructions. A future bounded native
slice should persist the owner's selection, expose it in policy/help, record
requested route/effort in run receipts and map only verified supported controls.
Preserve explicit route holds, actual shared budgets, frozen runs and Unknown
effective settings. Automatic effort adaptation and changing a live lead's
settings need separate capability work. There is no native effort-profile
command yet. Initial estimate: **3–6 hours** for a scoped selector/receipt
slice after its contract, with per-route enforcement estimated from the audit.
This planning entry does not displace the current save-failure diagnosis.

## Learn from actual project work

Owner-approved on 2026-10-07: [model experience and task-fit recommendations](MODEL-EXPERIENCE.md)
become a separate Unio feature. Build on the existing ledger/scorecard to record
accepted changes, actual failures, demonstrated review findings, corrections
and time spent, grouped by model/route/effort and task type. Use official model
claims only to propose first trials; recommendations need Unio's own checked
project evidence. The [free model inventory](../FREE-MODELS.md) records the
eleven approved candidates and initial dated observations. The richer runtime
profiles and automatic suggestions are planned, not implemented. The
[curated scoreboard and task-fit guide](MODEL-SCOREBOARD.md) supplies practical
lead guidance now. The standing
[escalation rule](../ai/LEAD-ESCALATION.md) ends unsuccessful delegation after
one worker and one suitable replacement: the existing lead then implements
the correction. Neither guide triggers extra model calls or automatic rerouting.

## Approved delivery priorities

This section preserves the earlier approved sequence and later scope additions.
Use the current focus at the top for the functionality-first recommendation.

Owner-approved on 2026-10-06. The goal is more verified work from existing
subscriptions, with fewer interruptions and less rework. Finish the current
browser milestone, delivered in v0.5.3. Deliver recoverable continuation
before expanding the coordination engine; the subsequent theme/map additions
are accepted in source for v0.5.4.

| Order | Milestone | Intended result | Status |
| --- | --- | --- | --- |
| First | v0.5.3: browser-to-worker workflow | Prepare and approve a task, start a worker once, inspect results and reviews, and accept the exact verified changes. Add actual worker output and console access as described in the [worker progress contract](../WORKER-PROGRESS.md). | [Delivered in v0.5.3](https://github.com/danielmevit/unio/releases/tag/v0.5.3), including UI, output/files, the real worker journey and release checks. |
| Next | v0.5.4: recoverable continuation | Save recoverable work during runs and on failure, then let an owner-enabled supervisor restart the lead CLI after its allowance cooldown using the saved handoff. | Saving, one authorized continuation and the first supported lead cooldown runtime accepted in source. Dark theme/responsive work map and observer budget correction are also in source. Real subscription-limit restart acceptance and combined release checks remain. |

The v0.5.4 scope now includes [automatic work saving](../WORK-SAVING.md),
requested after a real worker reached its quota before committing. This is
partly implemented: manual/automatic native-run saves and one authorized
continuation and the first lead cooldown runtime are in main; real restart acceptance and shipping remain. Context handoffs alone are not
recovery backups. Automatic saving passed its focused offline acceptance,
including real periodic capture, interruption and exact restore; the combined
release gate remains required. Further UI work and optimization wait until
recovery is complete, as the owner approved on 2026-10-08.

On 2026-10-07 the owner added [lead CLI cooldown restart](LEAD-COOLDOWN-RESTART.md)
to the continuation milestone. Unio waits outside the stopped lead process,
using a supported reset time plus one minute or a five-hour-and-one-minute
fallback for a known five-hour limit, then starts the configured lead again.
Repeated limits create new waits; stop and completion cancel further restarts.
Existing worker limit handling stays unchanged. Deliver work saving first so
each restarted session can reconcile the current work without duplicating it.

Future visual milestone, owner-selected on 2026-10-08:
[Marathon-inspired UI direction](../UX-DIRECTION.md#future-visual-milestone-marathon-direction),
using its layout, shapes and UX structure with black/white/charcoal surfaces,
aligned control rows and a compact Settings entry. Neutral surfaces remain;
small semantic status strips are the owner's later color exception. Build original components, preserve responsive and
accessible behavior, and keep task controls functional. Schedule it separately
after current functional work; it does not replace recovery priorities.

The following records the earlier approved order after these two milestones.
The current functionality-first recommendation at the top makes daily launch
and observed runtime reliability more prominent. Implementation boundaries,
release numbers and delivery dates still require bounded planning.

1. **Remaining allowance monitoring.** Show five-hour, weekly and monthly
   windows, reset times and the age of each reading. Use supported automatic
   readings where available and timestamped manual input elsewhere. Keep
   stale or missing capacity visible as Unknown. Account for workers sharing
   a subscription and reserve allowance for checks, reviews and saving work.
   See the [quota monitoring plan](../PROVIDER-QUOTA-MONITORING.md).
2. **More reliable agent connections.** Check authentication, model routes,
   effort settings and prompt delivery where supported. Isolate per-run
   state, distinguish connection errors from exhausted allowances, and fail
   locally on known problems where possible. Preserve actual failures and
   reviewer protections instead of spending requests on blind retries.
3. **Smarter delegation and scheduling.** Divide larger goals into
   finishable tasks with explicit dependencies and file ownership. Run
   independent work together, serialize conflicting changes, and size tasks
   conservatively using current capacity. Explain agent selection and follow
   the owner's allowed routing policy. See the
   [capacity-aware continuation plan](../CAPACITY-AWARE-CONTINUATION.md).
   Owner clarification on 2026-10-07: an unfinished worker should not block
   unrelated tasks. Keep a ready queue, use independent available accounts
   concurrently within the selected tier, and revisit results as they finish.
   Show dependencies and reasons for idle workers. The lead policy applies now;
   an automatic scheduler remains planned. See [parallel work](PARALLEL-WORK.md).
4. **A built-in parallel review pipeline.** Make independent reviews from
   different AI labs a normal Unio workflow, using identical revisions and
   complete material in separate review views. Connect structured findings
   to tests and security checks, followed by the lead's own overview. Add
   targeted reviews when actual gaps require them; reviews reduce mistakes
   without promising to find every bug.
5. **Better reasoning and context efficiency.** Use high or the supported
   middle effort by default, escalating when the task warrants it. Give
   workers focused, complete task context, reuse still-valid evidence, and
   avoid duplicated investigation and repeated repository scans. Keep the
   complete material required for final reviews and record actual model
   controls rather than assuming every route supports the same levels.
6. **Performance measurements that guide decisions.** Extend existing
   ledger and score information to track requests, tokens, elapsed time and
   rework per accepted change, including review and recovery overhead. Choose
   agents using evidence for the kind of task and compare team workflows
   against a single-agent baseline. Also measure local activity observation:
   a 2026-10-08 Windows-mounted workspace scan took 10.37 seconds and exceeded
   the preview server's 10-second deadline. Add a bounded configurable browser
   observation budget and reduce repeated scan work while preserving truthful
   unavailable/stale states. See the [live-workspace finding](LIVE-WORKSPACE-VIEW.md#large-workspace-observation-follow-up).

Task design and reasoning budgets deserve measurement before optimizing
local script overhead. One recorded GLM review took 437 seconds at max and
174 at high, without a better max result. This is a limited local comparison,
not a universal model benchmark. See the
[recorded findings](../FINDINGS-2026-10-05.md#glm-53-speed-setup-versus-model).

The sections below preserve milestone history and detailed design context.
Use the current focus at the top, the [functionality-first plan](FUNCTIONALITY-FIRST-PLAN.md)
and the [version plan](../VERSION-PLAN.md) for sequencing. Dated checkpoints
describe what was known at their timestamps.

Checkpoint rule: one bounded correction at a time; test, commit, then
update [the continuation prompt](continue-with-ai-prompt.md) with the exact
candidate SHA, evidence, blockers, active workers and one next task.
All project-owned work stays inside `/mnt/d/Vibe Coding/_vm/frugal-flock`.
The main checkout is its `repo/` folder; workers use `wt/NAME/`.
Follow [the standing workspace rules](WORKSPACE-RULES.md).
Current delivery checkpoint (2026-10-08): [v0.5.3](https://github.com/danielmevit/unio/releases/tag/v0.5.3)
is published and installed from exact gated source `ae61bf3d11ff`. It includes
the browser workflow, worker output/files and native work modes and tiers.
The earlier 0.5.0, 0.5.1 and 0.5.2 releases remain available. Next is work
saving and checkpoint continuation in 0.5.4, followed by lead cooldown restart.
Completed 0.5.x publication and installation are authorized. The newest
session policy uses personal lead review without extra AI reviewer jobs.
Read the [current continuation prompt](continue-with-ai-prompt.md) and newest
private coordination entries before assigning work. The
[2026-10-05 closing handoff](../SESSION-HANDOFF-2026-10-05.md)
is preserved as an earlier checkpoint.

## Earlier checkpoint (2026-10-05)

- 2026-10-05: Claude is the lead. The waiting-job JobStore library/tests
  were built through the installed Frugal Flock 0.4.0 (legacy build tool) pipeline (GLM 5.3 worker,
  two approved runs, Claude lead review), merged and pushed as 2539c64.
  Owner direction: use Codex, OpenCode GLM, Grok and Antigravity for flock
  work with cross-vendor reviews. Next: approval plus reservation/recovery
  slice (no executor) and job_store_test.py in the routine gate.
- Name and tagline approved by the owner.
- Canonical CLI: `unio` (old aliases `frugal-flock`, `frgl-flc`, and `agentteam` are removed). The Linux `flock` utility must remain untouched.
- Naming contract: [Brand](../BRAND.md).
- UX proposal: [UX direction](../UX-DIRECTION.md). The proposed graphical
  app is not implemented yet.
- Research and evidence: [Findings index](../RESEARCH-FINDINGS.md),
  [competitor comparison](../../research/COMPETITIVE-REVIEW.md), and
  [engine findings](../ENGINE-FINDINGS.md).
- Continue with another AI: [copy-paste prompt](continue-with-ai-prompt.md).
- The rename implementation, commit
  `9314639e79dc8bb9edde151f54cfdf35837c3024`, and the UX documents are now
  integrated into `main` at the owner's explicit request. Existing Git
  history is retained. This work has not installed anything into the
  user's live command/configuration directories.
- Lead verification passed: scope OK, all five frozen validation commands
  passed, one task commit touching 20 paths. Worker checks also passed:
  40/40 selftests, 14/14 adversarial probes, branding smoke, ShellCheck,
  documentation lint, and whitespace checks. Both Word manuals were rebuilt.
  An independent read-only review found no remaining runtime blockers;
  its command-spelling corrections are included in the final commit.
- The first native worker stopped at a provider limit; its edits were
  preserved and handed to a finishing worker. History is in
  `coord/reports/FF-BRAND-codex.md` in the enclosing workspace; the latest CLI log is in the sibling
  `.log` file. That interrupted run is historical, not the final task
  outcome; see the later verification and completion handoff in the report.
- Existing local commits from before this session were preserved. The
  Historical GitHub rename: `agentteam-docs` became
  [frugal-flock](https://github.com/danielmevit/frugal-flock). The rewritten
  README offers a beginner path, optional technical depth, and keywords.
- On 2026-10-05, the owner approved the subsequent rename to
  [Unio](https://github.com/danielmevit/unio); see [the rename contract](../RENAME-UNIO.md).

## 1. M1 — finish quality before UX

The owner explicitly moved reliability ahead of the prototype. Follow
[QUALITY-M1-CONTRACT.md](../QUALITY-M1-CONTRACT.md), frozen at `e230ad4`,
and [the current checkpoint](../M1-STATUS.md). Complete strict verification,
revision-bound results, reviewer verdict parsing, honest availability,
trusted-host warnings, and manual same-checkout context packets. Pass
mock-only regressions and independent source review before owner integration.

This is not full OS isolation, a dirty-file backup, automatic provider
migration, or automatic merging. Keep those limitations visible. Stop at
a verified, handoff-ready checkpoint before starting the UI.

All five M1 items are implemented and merged into main as of 2026-10-04:
strict verification, structured evidence, gated review, local availability,
manual context packets, both correctness fixes, the acceptance-coverage
audit, and updated help, protocol, docs and Word manuals. The final gate
results are in [the current checkpoint](../M1-STATUS.md). The owner
accepted M1 on 2026-10-04. M2 starts when the owner asks for it.

### Clean-clone baseline check

- Follow the README from a fresh clone. Install with
  `bash unio-install.sh`, then run `unio selftest` and
  `unio version` before connecting a live provider.
- Unio supports only `unio`, `UNIO_*` overrides and `~/.config/unio`.
  The installer copies legacy default config once when the new config is
  absent and no override is selected, preserving the old config. Old aliases
  and environment names are not supported; local clone folders stay intact.

## Near-term roadmap (owner-approved 2026-10-04)

Goal: build the Unio app WITH the installed Unio tool (dogfooding) and watch
its behaviour live, so build progress, bugs and errors are visible as they
happen. Only after a stability phase, so the team does not burn tokens in
bug loops.

Assessment of the plan (lead review, Claude Opus 5.5, 2026-10-04): the plan
is sound and on the right path. Reliability first was right, the honesty
rules (no invented quota, no sandbox claims) are right, and clean
continuation after provider limits is the real differentiator. Risks:

- Scope is large for one owner: local service, browser app, launcher,
  checkpointed cross-provider continuation. Deliver thin vertical slices
  and measure benefit before expanding (section 6).
- At that assessment, 0.4.0 had only mock verification. Live canary
  evidence is now recorded in section 1.5; limited real M2 cycles are recorded
  below, while broader dogfood reliability remains unproven.
- At that assessment, the loop brake was only a role-card rule. It is now
  implemented and mock-tested in unreleased source (section 1.5).
- Antigravity failed 2 of 2 live runs (about 55 minutes each).
- Checkpointed handoff (save and move partial work) is the hardest piece;
  the M1 handoff packet is context only.
- The repository now uses AGPL-3.0-only, with required notices and optional
  separate paid agreements for proprietary use (section 7).

Order: M1.5 below, then M2 built by the flock itself (mock-data prototype,
one worker plus a reviewer, owner merges, widen after a few clean cycles),
then the read-only local bridge (section 4), whose first view grows out of
`unio watch`, then capacity-aware handoff (section 5).

## 1.5 M1.5 — stability before dogfooding

Do the M1.5 stability phase, approved by the owner on 2026-10-04, in this
order, one small tested checkpoint each:
1. Live canary: a throwaway repo, one tiny task per agent through run,
   verify, review and result. Tiny tasks only; it uses provider quota.
   Offline preparation is recorded in [the canary checkpoint](../M1.5-LIVE-CANARY.md).
   Antigravity passed its first canary in 22 seconds on 2026-10-04;
   the earlier silent stall did not recur. One worker call, no retry.
   Grok also passed in 35 seconds, one worker call, 2/2 checks and lead review.
   OpenCode Go `opencode-go/glm-5.3` passed in 24 seconds, with the same
   checks and in-session lead review.
   Kimi (`opencode-go/kimi-k3`) also passed in 45 seconds with the same checks.
   Claude Sonnet 5.5/medium passed in 23 seconds, one commit/file, verify
   2/2, lead review and current ready result. Codex's original attempt was
   interrupted and archived; the owner's one approved retest passed in
   26 seconds, one commit/file, verify 2/2, lead approval and live Grok review
   (82s), current ready result. All six canaries now passed; step 1 complete.
   Seven worker invocations/one live reviewer; one explicitly approved
   retest, no automatic retries. Fixture stopped, global settings unchanged.
   The interrupted-activity label limitation is reproduced with mocks and
   recorded for a separate fix; readiness correctly fails closed.
2. Loop brake in the engine: a task that failed twice is refused until
   the owner explicitly allows another attempt.
   Source implementation complete at `d930a87`: one counted failure per
   started attempt across workers, including lost starts with free locks;
   one explicit owner grant via `allow-retry`. Full gate passed: 40 selftests,
   120 existing regressions, 22 brake checks, 14 probes, packaging, ShellCheck
   and docs. Installed 0.4.0 remains unchanged until a deliberate release.
3. Live monitor (`unio watch`): runs, verdicts, failures and limits
   as they happen; it later becomes the app's Activity view.
   Source implementation complete: 26 focused mock checks, standalone
   packaging/aliases/completion, ShellCheck/syntax and full docs lint passed.
   Observed all six recorded canaries without changing coordination hashes
   or calling providers. [Usage and JSON contract](../WATCH-USAGE.md).
   Current readiness still requires `result`; capacity stays unknown.
   Stability follow-up: fresh OpenCode source defaults/examples now use
   --auto, confirmed by current native help and Go canaries. Offline native
   dispatch/verify, no-call legacy diagnostic and reinstall preservation
   passed; packaging/ShellCheck/docs passed. Existing profiles stay untouched.
4. The flock runs on the installed release while it builds the next
   version in the repo; reinstall only at deliberate releases.
   Observed 2026-10-04: installed 0.4.0 executable/global agents.conf hashes
   unchanged through all stability work. New features are source-only.
5. Bench Antigravity for dogfooding until it passes the canary (2 of 2
   earlier live runs failed). The owner requested its inclusion in step 1.
   Canary passed in 22s; local diagnostics currently show enabled, with
   authentication/capacity unknown. Broader dogfooding remains unproven.
Then dogfood on M2 (the mock-data prototype): one worker plus a reviewer,
owner merges; widen after a few clean cycles.

## 2. M2 — prototype one simple project workspace after M1.5

Build a clickable prototype with clearly labeled sample data. One
conversation with the lead, with plan, progress, and review cards beside
it. Keep the main actions literal: Create plan, Approve and start, Stop,
Request changes, and Apply changes.

Cover five connected moments:

1. Open a project and connect an existing coding tool.
2. Describe a change and review a proposed plan.
3. Follow the work and answer a question.
4. Recover from a simulated provider limit using a named replacement.
5. Review the result and approve or request changes.

Use the calm minimal direction in the UX proposal and the
[Toolcraft composition reference](../TOOLCRAFT-REFERENCE.md). Build original
components; do not run its scaffold or import its implementation. Keep technical logs and
advanced controls in detail views. The original plan asked two people new
to the CLI to test the prototype before live execution. The owner explicitly
waived that feedback gate on 2026-10-04 because no testers are available:
use judgment and automated checks. No user sessions have taken place.

Prototype source is implemented in [prototype/](../../prototype/README.md),
2026-10-04 by Codex (`gpt-6.1-sol`, xhigh): original HTML/CSS/JS, no runtime
dependency, all five connected moments, sample data labeled in every state.
Four state tests and the full Chromium browser journey passed, including
explicit replacement/apply, revision invalidation, Stop, focus, escaped text,
mobile inspector collapse and no external requests/page errors. Refresh
restarts the demo; no real provider, checkpoint or project action occurs.
The owner waived the two-person feedback gate on 2026-10-04; the optional
[facilitator guide](../M2-USER-TEST.md) retains two blank records. No
feedback sessions are claimed. Installed-release dogfood: GLM's one keyboard worker
hit its 180s limit with zero work, preserved as failed; root finished locally
and the browser/state checks passed. Claude Opus 5.5/high's separate guide
cycle passed in 83s with 2/2 validation and in-session root review. No retries
or paid reviewer. [Evidence and limits](../M2-DOGFOOD-PLAN.md).
Proceed to small live-control slices using judgment and automated checks.
Explicit run/quota approval, truthful evidence and separate acceptance still apply.

## M1 acceptance details — trustworthy results

Before starting M2, not merely before enabling live UI actions:

- Separate process completion, validation, reviewer decision, human
  acceptance, and integration outcome.
- Missing scope or checks must be incomplete; M1 has no waiver bypass. A
  plain PASS must not hide missing evidence.
- Preserve verification failures separately from the worker process exit.
- Parse reviewer decisions into approved, changes requested, or unknown.
- Associate evidence and approval with exact revisions and worktree state.

These changes belong to M1, not a later frontend task. See the frozen
contract for exact exit codes and regression cases.

## 4. Add the local application bridge

Current checkpoint (2026-10-08): queue approval, reservation and recovery
shipped in v0.5.2. The complete browser milestone is now released as
[v0.5.3](https://github.com/danielmevit/unio/releases/tag/v0.5.3), including execution service/API, UI, protected
output/files and the real funded browser demonstration. Release packaging
and upgrade/rollback checks passed. See the [living prompt](continue-with-ai-prompt.md)
for the next work-saving milestone. The foundation history below
records earlier limitations, not the current queue/service state.

Start with read-only project, agent, and activity views. Then add a fixed,
validated set of operations for plans and runs, a durable job queue, and
progress that survives browser refreshes. Keep credentials in native CLI
authentication stores and bind control to the local machine.

The first [read-only Activity preview](../../bridge/README.md) is implemented in
source: one fixed watch JSON observation endpoint and original browser view,
loopback only, no dispatch or coordination writes. Seven stdlib HTTP tests
and browser failure/recovery/escaping/mobile checks passed. An actual project
observation showed the preserved GLM failure and approved Claude guide,
with all 36 coordination-file hashes unchanged. Runtime/global profile
hashes remain unchanged. [Contract and source-build usage](../BRIDGE-ACTIVITY.md).
Folder selection/launcher/setup, durable queue and live controls are not
implemented. The owner waived the two-user feedback gate; provider calls
still require explicit quota approval. Optional --open-browser now opens the
bound read-only URL with a manual fallback; eleven focused checks passed.
The [manual draft storage foundation](../PLAN-DRAFTS.md) is implemented
and passed eight checks: persisted immutable records/content hashes, no
native tasks or approval/dispatch. A protected --enable-plan-drafts API now
adds only manual create/read, exact Origin/Host/session checks and bounded
JSON. Eight API checks, eleven existing HTTP checks, default browser journey
and actual restart/persistence/token rotation passed. No real-project draft
or provider call. The opt-in Save/reopen form now passes both default/manual
browser journeys, duplicate-submit and failed-session/save/no-retry checks.
Default stays read-only; no AI plan generation, worker/queue or merge control.
The owner reiterated the main build-with-the-flock goal on 2026-10-05.
The first [waiting-job queue slice](../JOB-QUEUE-STORE.md) was built with
the [native dogfood cadence](../DOGFOOD-WORKFLOW.md): a quota-approved GLM
worker, the Claude lead's in-session review and its own merge (2539c64).
Earlier direct root code is not worker success. Queue approval plus
reservation/recovery subsequently completed in v0.5.2; the execution
service followed in v0.5.3, as recorded in the current checkpoint above.


Package a launcher that starts the service and opens the browser. Specify
folder selection, missing-engine setup, provider installation/sign-in,
and failure recovery before claiming a command-free first use.

## 5. Build reliable provider handoff

The owner endorsed [capacity-aware task sizing and clean continuation](../CAPACITY-AWARE-CONTINUATION.md).
The [provider quota monitoring roadmap](../PROVIDER-QUOTA-MONITORING.md)
records the 2026-10-05 request for remaining five-hour, weekly and monthly
indicators, supported provider inputs, manual fallback and lead checks
before dispatch. A Codex read-only probe worked. The 0.5.7 candidate (not
yet released) adds an explicit cached Codex metadata refresh and a read-only
browser overview of every recorded window; other providers stay manual or
Unknown and scheduling does not consume these readings yet.
Preserve this design for a later milestone: periodic supported readings or
manual input, conservative scheduling, and tested recovery checkpoints.
M1's context packet is not a backup of uncommitted files.
The owner also explicitly requested documentation for a future [temporary lead capacity handover](LEAD-CAPACITY-HANDOVER.md) when the primary lead's allowance is exhausted.
It is documented in the 0.5.7 candidate; the runtime and its deterministic
fake capacity/handoff tests are a later milestone.

After a run stops, capture committed and uncommitted work, task context,
completed checks, and unfinished work. Let the user select another
available agent and continue from that checkpoint. Recheck the continued
result before owner acceptance.

Display available, limited, unavailable, or unknown capacity. Show reset
times only when reported by the provider. Do not invent universal quota
percentages or silently enable paid API fallbacks.

## 6. Measure the benefit before expanding

Use the [feature decisions](../FEATURE-DECISIONS.md) to select relevant
competitor ideas. The [workflow guide](../AI-TEAM-WORKFLOWS.md) explains
common AI-team patterns without implying they are all implemented.

Compare a small set of real tasks with the existing CLI workflow and one
capable coding agent. Measure accepted correct changes, active human time,
rework, and recovery from interruptions. Include dependent tasks as well
as easy parallel ones.

Defer a full desktop wrapper, hosted accounts, multi-user collaboration,
advanced races, and additional provider integrations until this basic
journey is useful and understandable.

## 7. Make public participation easier

- License chosen and applied on 2026-10-04: AGPL-3.0-only, copyright
  Daniel Mitev, public attribution Daniel Mevit (@danielmevit). The owner
  explicitly chose true open source, allowing compliant commercial forks,
  with optional paid agreements for proprietary use. Section 7(b)/(c) terms
  preserve the Unio name/author credit and prohibit origin
  misrepresentation in covered copies/variants. Full terms/NOTICE
  ship with the installer; see [licensing guidance](../LICENSING.md).
- Add concise contribution and issue-reporting guidance.
- Define contributor permissions before accepting outside code if paid
  proprietary licensing is planned; AGPL alone does not grant relicensing rights.
- Collect onboarding feedback from both new builders and experienced
  users; keep the README's basic path separate from optional deep dives.

## Improvement Backlog

For a detailed, consolidated inventory of all pending, accepted, and planned functional improvements (including mobile session pairing, allowance monitoring, and scheduling), see the [Improvement Backlog](IMPROVEMENT-BACKLOG.md).
