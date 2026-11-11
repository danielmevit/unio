# Unio — continue with another AI

This handoff is portable: it requires the public repository, not the
previous conversation, one particular model, or private coordination logs.
If the next AI cannot access GitHub, attach this file and the documents
listed in its reading order.

Historical baseline: M1 (the quality milestone) is implemented, merged into main
and accepted by the owner on 2026-10-04; see [M1 status](M1-STATUS.md).
The [2026-10-04 continuation report](SESSION-HANDOFF-2026-10-04.md) records
the earlier, pre-merge state and is kept as history.
For subsequent sessions use [the continuation prompt](development/continue-with-ai-prompt.md),
the single living prompt refreshed after every small checkpoint. Copy its
prompt section into the next AI chat, and read the local agent log first.
All project-owned files belong under one workspace, per
[WORKSPACE-RULES.md](development/WORKSPACE-RULES.md).

## Product purpose and review practice

Unio connects AI agents from different AI labs. It also supports security
and code quality through independent reviews and task checks, and efficient
work through bounded assignments, preserved evidence and clear handoffs.
Extra review calls use allowance; fewer defects and less repeated work must
be assessed from actual results. Worktrees remain coordination boundaries,
not host security sandboxes.

For current Unio development, the owner requires two independent final AI
reviews from different AI labs, separate from the source authors, followed
by the lead's own overview. Run them concurrently on the same frozen
revision and complete material without sharing peer findings. Corrected
candidates need fresh reviews. This is the development policy, not a
universal automatic requirement of the tool or a guarantee of correctness.

## Historical baseline (2026-10-05)

- Public repository: https://github.com/danielmevit/unio
- Published implementation/README baseline: `f962b6a`. Read the latest main
  for this handoff and the research documents added afterward.
- Product: Unio. Tagline: Your AIs, in sync.
- Command: `unio` only.
- The runtime, templates and completion are embedded in the single
  `unio-install.sh` installer. Unio 0.5.0 is installed in the development
  workspace with owner approval on 2026-10-05. Public release requires
  separate approval; see [version plan](VERSION-PLAN.md).
- The UI and recovery flow are proposals. No frontend framework has been
  selected, and no working graphical app should be assumed to exist.
- Existing baseline checks passed: 40 selftests, 14 adversarial probes,
  branding smoke, ShellCheck, and documentation lint. Re-run appropriate
  checks for new changes; do not reuse those results as proof of new work.

## Earlier milestone plan and boundaries

The owner changed the order: **M1 quality first, UX second**. Complete and
independently verify [QUALITY-M1-CONTRACT.md](QUALITY-M1-CONTRACT.md), frozen
at `e230ad4`, before starting the prototype. See [M1-STATUS.md](M1-STATUS.md)
for the implementation checkpoint, evidence, and unresolved requirements.

M1 covers strict checks, separate revision-bound result states, parsed
reviewer decisions, honest local availability, trusted-host warnings, and
a safe manual next-AI context packet for the same checkout. No waiver
bypass, OS sandbox, dirty-file backup, automatic provider migration, GUI,
or automatic integration is included. Full E4 and E6 remain later work.

After M1 is verified and accepted, build a clickable, locally runnable
prototype with clearly labeled sample data. Validate comprehension before
wiring up providers or an execution service.

Five connected flows must work:

1. Choose a sample project and see sample tool-connection states.
2. Describe a change and review its proposed sample plan.
3. Approve the plan, follow sample progress, and answer a sample question.
4. Simulate a limit, inspect a saved-work summary, and choose a named
   replacement provider, wait/retry, or save for later.
5. Review a sample diff and checks, then request changes or simulate Apply.

One project workspace should contain the conversation and relevant plan,
activity, and review cards. Keep the actual provider names visible; do not
turn the main interface into a wall of terminals or quota charts.

## Earlier prototype acceptance criteria

- The complete journey is clickable and repeatable, with a reset-to-demo
  action and no dead-end primary buttons.
- Every simulated plan, connection, quota limit, checkpoint, and result is
  visibly sample data. No live provider calls or real filesystem/Git actions.
- Unknown capacity remains Unknown; do not invent provider percentages or
  assume another provider inherits conversation memory.
- Pause new work and Stop this run are explained as different actions.
- Failed, missing, or unknown checks cannot enable the successful Apply
  state. Reviewer completion and reviewer approval remain separate.
- Request changes is as discoverable as accepting a result.
- Keyboard navigation, visible focus, text status labels, readable type,
  and narrow-screen behavior are checked. Respect reduced-motion settings.
- Provide exact install/start/build/test commands. Run what the environment
  supports; list anything not run and why. Include tests for state transitions.
- Preserve the existing CLI behavior and coordination schemas. The rename
  contract deliberately removes old command aliases and migrates config once.

## Handoff context packets

`unio handoff WORKER TASK` publishes a local context packet for the same
checkout: context and evidence, never a backup, automatic acceptance, or a
provider migration.

- The packet is context only. It never sets the recorded result, never makes
  a failed or missing delivery ready for human review, and the owner alone
  decides acceptance and integration.
- Successful runs keep the strict complete packet: result, revision, changed
  paths, task text, and for report-only work the complete Source report with
  provenance and bound delivery artifacts.
- Verify, review and readiness keep refusing a failed, missing or
  incomplete delivery. A terminal Source failure with a current unchanged
  snapshot still produces an explicitly incomplete recovery packet:
  the recorded failure, genuinely bound partial report and declared partial
  artifacts are included and labeled (missing artifacts as `MISSING`), and a
  missing report is labeled missing, never fabricated or replaced by raw
  logs. Tampered, unbound, unsafe or changed evidence, and running or locked
  workers, still refuse without publishing anything.
- Read `HANDOFF.md` and `report.md` inside a packet before sharing it, and
  review `task.md` for sensitive information.

## Copy-paste prompt

Use [continue-with-ai-prompt.md](development/continue-with-ai-prompt.md). Keeping the
copy-paste text in one place prevents older handoffs from sending the next
AI to an obsolete branch, folder, or milestone. This document supplies
product context and later acceptance criteria, not a second competing prompt.

For research context, read [the findings index](RESEARCH-FINDINGS.md),
[engine findings](ENGINE-FINDINGS.md), and [team workflows](AI-TEAM-WORKFLOWS.md).
For later UX, use [UX direction](UX-DIRECTION.md),
[feature decisions](FEATURE-DECISIONS.md), and
[Toolcraft reference](TOOLCRAFT-REFERENCE.md). Build original components;
do not import Toolcraft code, assets, templates, or its scaffold. Provider
facts in older research may need rechecking before future product decisions.
The [capacity-aware continuation proposal](CAPACITY-AWARE-CONTINUATION.md)
is future work, not a shipped scheduler or universal quota API.

## Earlier milestone order — consult the living prompt for completion status

1. After M1 acceptance, build and test the mock-data prototype described above.
2. Build a protected, localhost-only, read-only adapter before live controls;
   establish the isolation policy before less-trusted workloads.
3. Add bounded operations, durable jobs, and reconnectable progress.
4. Implement checkpointed provider continuation, with revalidation.
5. Add explicit human-approved integration tied to exact revisions.
6. Test with two newcomers and compare human effort against the old CLI.

Follow [Roadmap](development/ROADMAP.md) for priorities. The project uses AGPL-3.0-only with the attribution/origin terms in
LICENSE and NOTICE; see [LICENSING.md](LICENSING.md). Public visibility and
license obligations are separate facts.
