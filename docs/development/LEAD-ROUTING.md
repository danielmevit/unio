# Lead routing, reasoning effort and spending

Read [the current agent fleet](AGENT-FLEET.md), this policy, [bounded escalation](../ai/LEAD-ESCALATION.md), the
[model scoreboard](MODEL-SCOREBOARD.md) and [model effort](MODEL-EFFORT.md) before planning
assignments and at the start of each new lead session. Follow the owner's
current instructions and the selected project's rules. These defaults apply
whenever Unio is active; they are not permission to spend beyond an owner's
approved plans, task scope or invocation budget.


## Select review, effort and concurrency separately

Read the [Low / Medium / Max reasoning profiles](https://github.com/danielmevit/unio/blob/main/docs/ai/REASONING-PROFILES.md)
(or installed `templates/REASONING-PROFILES.md`) at startup. New-project prompts
provide explicit effort and coordination-tier fields. Any effort profile
can accompany YOLO, Balanced or Thorough. The owner can switch any axis for
future assignments; preserve the other two, record the choice in the project's
instructions/handoff, and map only verified supported model controls.

Low is the economical default; same-model/shared-subscription workers start
at the lowest supported effort, with max off. Owner-selected Medium adapts effort and can use supported max for hard
reasoning; Max requests each route's highest permitted setting for new tasks.
These profile names are lead instructions, not universal native effort flags
or an implemented `unio effort` command. Explicit project route holds and
spending restrictions remain. Frozen active tasks keep their original settings.

The xhigh/no-max defaults below remain the current Unio development workspace's
policy. An explicit owner's effort selection sets their new project's policy;
do not treat this workspace's default ceiling as a universal model limitation.
No profile changes account concurrency, role restrictions or actual allowance.

## Same-model and shared-subscription effort default

Owner update, 2026-10-16: when assigning a worker that uses the lead's model
or shared subscription, start at its lowest supported reasoning effort.
For Codex CLI / GPT-6.1 Sol, request `low`. An explicit owner effort or profile
choice overrides this default; record it and preserve frozen assignments. Keep capable implementation models;
this is an effort choice, not permission to replace them with free chore agents.
Other routes retain their owner-approved defaults and verified controls.

Assess the actual result and checks. If reasoning is insufficient, raise only
to the next supported effort for a separately authorized continuation, recording
why, prior work and every outcome. For example, Sol can progress low → medium
→ high → xhigh where the installed route supports those settings. Max/ultra
still requires the owner's explicit permission. Quota, authentication and
transport failures are operational failures, not evidence that low is too weak.
Do not increase effort to fix those failures or discard an unsuccessful attempt.

Frozen running assignments keep their settings. Changes normally apply to the
next assignment; only a supported managed-session control can request a later
turn setting, without promising to change current reasoning. An escalation
does not authorize a retry forbidden by the owner, reset task history, open
extra shared-account slots or bypass STOP. Preserve the real lead reservation.

After each final assessment, record route, requested model, requested effort,
task type, Source result, native checks, acceptance, correction burden and
elapsed time. Use `unio experience record` / `show`: profiles already separate
model, route, effort and task type. Keep CLI/version, timestamps and elapsed
work in the dated task receipts and scoreboard. Effective effort/model and
per-task allowance savings stay Unknown unless measured. Compare similar
tasks and retain sample counts; one result is not a universal model ranking.

Owner authorization, 2026-10-16: low-effort Sol workers and necessary
continuations are standing-authorized; do not ask permission for their count.
This replaces the earlier per-task no-retry restriction for low-effort Sol
work. Preserve failed attempts, diagnose the cause and continue from saved
work. Keep one focused shared-budget correction alongside the lead at a time,
with the real lead/account reservation and temporary medium only as needed.
It authorizes no extra paid tokens, parallel account drain or blind retry loop.

## Mandatory task estimates and progress summaries

The lead must give the owner a rough elapsed-time estimate before starting
each task or milestone, including delegated work, fixes, documentation and
release work. State the useful outcome and a realistic time range. Separate
implementation from checks, publication and installation where applicable,
and name material uncertainty such as an unavailable worker or a dependency.
Group routine commands into their task's estimate.

While work is underway, the lead must proactively send a concise overall
summary at least every **10 minutes**, including time spent waiting for workers
or checks. Do not wait for the owner to ask. Include:

- What finished since the previous summary and what is still in progress.
- Which workers are active, their tasks and the latest observed progress.
- Any blocker or decision affecting delivery.
- Elapsed time against the estimate and an updated remaining-time range.
- The next concrete step.

Send an earlier update when a material failure, delay, scope change or worker
completion changes the plan. Revise the estimate promptly when findings change
it; if the original range is exceeded, explain why and give a new range. At task
completion or a handoff, report the outcome and actual elapsed time when known,
then estimate the next task before starting it. Record estimates, start times
and checkpoints in the coordination log or task notes so a resumed lead can
continue reporting from evidence. Keep normal shorter progress updates between
these summaries when useful or required by the active session's instructions.

Estimates guide priorities; they are not guarantees, token or quota readings,
or automatic time limits on a healthy worker. Preserve the current bounded
scope and release checked work before continually expanding it. These are
mandatory instructions for an active lead; they do not create a background
notification service while the lead session is stopped.

## Answer questions and continue authorized work

A progress question, explanation request or correction steers the active task;
it does not pause or cancel it. Answer briefly, then continue the authorized
work in the same turn. Do not end the turn just because you answered, a worker
started, or a milestone checkpoint finished. Work through the agreed scope,
using independent useful work while a worker or check runs. Pause only when
the owner asks, required information or authority is genuinely missing, or
an actual access, capacity or runtime limit prevents further progress.

Keep estimates and concise progress updates current. Before an unavoidable
stop, preserve coherent commits and unfinished work, record every active job
and its latest receipt, and leave the exact next step. Never imply the lead is
still working after its turn ends. A started background worker may continue;
identify it separately. This is lead guidance, not an automatic keep-alive or
cooldown service, and it never overrides STOP, budget limits or owner holds.

## Report the whole fleet when asked for status

An owner-requested status report covers every configured or approved route,
including active, queued, idle, benched, unavailable and owner-reserved agents.
Give the subscription route, CLI/adapter, current or latest requested model
and effort, task/state and the reason an idle route is unused. Separate
Mistral/Vibe GLM, OpenCode Go GLM and Perplexity GLM explicitly. Show options
sharing one account as one shared budget, not extra independent capacity.

An installed binary or enabled alias does not establish provider readiness.
Keep unverified model identity, effort, free pricing and allowance Unknown;
do not make inference calls or read authentication stores just to fill a
status table. Owner holds take priority over an alias's enabled flag. Preserve
those holds in the project's instructions and handoff until explicitly revoked.

## Check the local launcher before admission

For each newly prepared or changed Source/review launcher, check syntax without
executing it: use `ast.parse` for a local Python wrapper or `bash -n` for a shell
wrapper. Verify the pinned CLI version, adapter/config hashes and required private
receipt directories before opening a native workflow. Transport prompts as files
or safely encoded data rather than interpolating prose into source literals.
These local checks make no model call and do not authorize command probes,
credential inspection or changes to a frozen active run.

Preserve a failed admission separately from any actual provider invocation.
Correcting a demonstrated local setup defect does not prove a model failed or
returned capacity. Reuse unchanged passing code validation only after confirming
the exact revision and clean worktree; preserve the original failed evidence.

## Name the model route in every work summary

Owner rule, recorded 2026-10-12: a model name alone does not identify the
account or tool doing the work. At assignment, completion, failure and every
overall progress summary, name the subscription/provider route, CLI or
adapter, requested model, requested effort, task and observed state. Give the
CLI version at assignment and preserve it with the dated run receipt. Later
short updates may omit the unchanged version, but must still identify the
route; do not call three different accounts simply "GLM".

For example:

- Mistral subscription / Vibe CLI / GLM 5.3 (`zai-glm-5-3`) / high — task
  X: checkpoint committed; tests pending.
- OpenCode Go / OpenCode CLI / GLM 5.3 / high — task Y: running; last
  observed action and its time.
- Perplexity Pro / Perplexity adapter / GLM 5.3 / Thinking enabled — task
  Z: proposal returned; implementation and acceptance pending.
- GitHub Copilot Free / Copilot CLI / Auto Balance / effort not exposed —
  checklist returned; underlying model and AI lab unknown unless native
  evidence establishes them.

Use the actual configured model ID in receipts; these examples are not model
availability checks or authorization for paid fallback. Keep requested and
observed model/effort distinct. A route chooses the tool/account; an AI lab
identifies the model's origin, when known. An Auto route may not establish a
fixed model or lab. Preserve Unknown where the provider supplies no evidence.

Each task's durable log/handoff records its task and worker IDs, provider and
subscription route, CLI/adapter version, requested model and effort, actual
start/end timestamps from `date`, saved revision, checks and result. Distinguish
native preparation from a started provider session, and a source exit from
lead acceptance. Record failed routes and replacements separately. Say which
workers are active, finished or unavailable; do not imply background activity
from an old receipt. Never include authentication tokens or private account
identifiers in public summaries.

## Mandatory continuity until the authorized work is complete

The lead must keep progressing through the agreed task and its necessary
checks, integration, publication or installation when those steps are already
authorized. A progress report, completed subtask, documentation update or status
question is a checkpoint within that work. Keep working after the update;
do not end the session merely to ask the owner to say "continue" again.

End the turn when the agreed deliverable is complete, the owner explicitly
pauses or cancels it, or a genuine blocker requires input, authority or an
external change. While a worker or check runs, advance useful independent work
within the approved scope and account limits, or monitor it and report progress.
Never invent additional tasks just to keep the session running.

Before an unavoidable stop or usage limit, preserve coherent commits and any
unfinished recoverable work, then write a dated handoff with the current
revision, actual checks, active processes, blockers and the exact next action.
Tell the owner what is saved and whether any process is still running. Claim
background work only when an actual launched process is still active; an ended
lead turn does not continue coordinating work by itself. Preserve the original
objective across interruptions and resume it from the saved checkpoint.

## Show the dashboard link at session start

Owner rule: at the beginning of every Unio lead session, after identifying
the project, run `unio dashboard ensure --open-browser` and show the printed
`http://127.0.0.1:PORT` link in an update to the owner. During the same
session and its continuations, reuse that dashboard; `unio dashboard status`
reports the link without starting anything. Skip this only when the owner
opts out. If no desktop browser opens, for example on a headless machine,
the printed link is enough.

This is a startup rule for cooperating leads that read these instructions.
It is not detection of every AI CLI on the machine: Unio cannot turn an
existing CLI conversation into a managed session by guessing its process, and
the dashboard shows recorded Unio activity, not that conversation. The
read-only dashboard stays up until `unio dashboard stop`, independent of STOP
and of any AI usage limit, and stopping it never stops workers. Service details
are in [the browser launcher contract](BROWSER-LAUNCHER-CONTRACT.md).

## Match the agent to the work

Read [the standing model roles](../ai/MODEL-ROLES.md) before each session.
Grok, Antigravity/Gemini, Claude Code and Codex are the main implementation
agents. Use available workers from that group for product features, core
behavior, UI, complex debugging and substantive security corrections. The
owner's designated lead normally plans, coordinates, reviews and integrates.
For Unio development, delegate fixes the lead would otherwise implement to
Codex CLI / GPT-6.1 Sol (`gpt-6.1-sol`) / low by default through Unio. The lead defines
the scope/checks, coordinates, reviews and integrates; it does not repair
the implementation inline. The owner permits one focused Sol correction
worker beside the registered lead, with real shared-budget accounting and a
recorded temporary native tier change if required. Read the
[2026-10-13 correction rule](../ai/LEAD-ESCALATION.md#dedicated-fix-worker--unio-owner-rule-2026-10-13).
For other projects without an owner override, a worker and one suitable
replacement may escalate to implementation in the existing lead session. Follow
[bounded escalation](../ai/LEAD-ESCALATION.md) and consult the
[model scoreboard](MODEL-SCOREBOARD.md) before delegation. This does not
create another workflow or grant extra spending or integration authority.

Use the [verified free worker pool](../FREE-MODELS.md) only for routine
support: documentation, formatting, inventories, mechanical changes,
boilerplate, predefined checks and supplementary observations. Free routes
must never lead, own main feature implementation, decide final acceptance or
replace the lead during a cooldown. Increasing effort does not promote a
free model into another role. Escalate difficult findings to a main worker.
This is a standing owner policy, not an invented reasoning-score ranking.

Choose using task fit and current availability. Low tier counts the lead's
workflow; a second job on its shared allowance requires an explicit owner
exception such as the focused Sol correction rule above.
If Codex leads and Claude is exhausted, use available Grok and
Antigravity/Gemini for implementation. Antigravity (`agy`) is a multi-model
CLI; record its selected model and AI lab. A past capacity failure is dated
evidence: check the owner's new availability report instead of treating it
as permanent, while preserving invocation and no-paid-fallback rules.

Keep available agents moving on approved, independent tasks rather than
waiting for an entire batch to finish. Low tier is one independent workflow
per shared account, including the lead; different accounts can run together.
Track dependencies and scope ownership, revisit the ready queue when a worker
finishes, and return to its saved result without blocking unrelated work.
Do not invent chores merely to keep models busy. Follow
[the parallel work policy](PARALLEL-WORK.md), preserve frozen runs and integrate
dependent changes in order. The lead assesses each complete change under the
current owner review policy.

## Consult local task experience before choosing a worker

When the installed release provides `unio experience`, inspect the relevant
task type before assigning work:

```bash
unio experience show --task-type "implementation"
unio experience suggest --task-type "implementation"
```

Choose a useful exact category for the actual task; documentation evidence does
not establish security or UI ability. Read the displayed examples, dates,
sample size, correction burden and local account blocks alongside the curated
scoreboard and current owner instructions. Fewer than three distinct reported
accepted tasks in 90 days provides examples only, not a recommendation. Even
enough evidence gives conditional advice: a clear local slot does not prove
sign-in, allowance or provider readiness. Never use old reset estimates as
restored capacity or promote a free/proposal route into feature ownership.

After reviewing a completed native task, explicitly record its final assessment
with requested model, route, effort and task type. Keep accepted reports,
quality issues, operational failures and unaccepted output separate. Source
exit zero is not acceptance; a local budget stop is not measured subscription
exhaustion. Unknown effective identity, corrections and allowance stay unknown.
Record before changing the worker revision or base: stale evidence is refused.
Identical replay adds no sample; conflicting assessments are refused unchanged.
This command is a local record, not a new review, human acceptance or dispatch.
See the [frozen first-slice boundaries](https://github.com/danielmevit/unio/blob/main/docs/development/MODEL-EXPERIENCE-CONTRACT.md).

## No extra token charges by default

Use the owner's existing funded subscriptions. OpenCode subscription models
use the `opencode-go` route. Do not substitute a pay-as-you-go model or buy
credits, top up, change billing, create an account or alter authentication
to get around a limit. Those actions require explicit owner authorization.

The eleven exact Zen free routes in [the inventory](../FREE-MODELS.md) are
an owner-approved exception for worker assignments while prices remain zero.
Before each new assignment, check current official pricing and native input,
output and cache costs. Missing, conflicting or nonzero cost means the route
is ineligible. Pin the primary model and any title/helper `small_model` to
the same eligible free model. Do not enable paid fallback or silently replace
an unavailable free model. Exo's local eligibility is still unestablished.
See [OpenCode's pricing](https://opencode.ai/docs/zen/#pricing).

## Start at high or the supported middle

Choose high, or the model's supported middle level, for ordinary work.
Medium is appropriate for routine chores on models that expose it. Keep
GLM 5.3 at high. LongCat's observed low/medium/high scale permits medium for
routine work; MiMo V2.6 Flash exposes no effort variant on this route, so
record the inherited/effective setting as unknown rather than inventing one.

Raise effort only when evidence shows reasoning difficulty. Use a supported
next level, such as high to xhigh. Xhigh is the owner-selected ceiling;
do not request max or ultra on any model. Routes exposing only high remain at
high; routes with only max need another eligible model. Record the reason,
time bound and current allowance.
Return ordinary later tasks to the default. Authentication, quota, transport
and missing-tool failures need their actual causes resolved; more reasoning
will not fix them. Read the model effort guide for route-specific exceptions.

## Check capacity and preserve work

An installed CLI or model catalog does not prove sign-in, quota or availability.
Use supported account metadata when available; otherwise record Unknown or a
dated owner reading. Distinguish five-hour, weekly and monthly limits, and
keep a reset estimate separate from actual restored capacity. Never repeatedly
call a known unavailable route to test whether waiting fixed it.

Freeze each task, scope, model, effort, configuration and time bound before
its authorized invocation. Record actual requested/effective settings, route,
AI lab, allowance evidence and its age. Respect one-invocation/no-retry rules;
a concrete defect may justify a new scoped correction, not an unchanged retry.
Resume Unio before authorized calls and stop it afterward. Preserve failures.

Make coherent scoped commits early, before lengthy final checks, and maintain
clear handoffs. Do not rely on the final AI response to preserve work. Treat
unfinished recovery data as unverified. Since 0.5.4, native runs capture
baseline, changed periodic and final recovery saves (`unio save`); a lead still
commits early, because a save is not acceptance. Portable checkpoint recovery
across tools and the [temporary acting-lead handover](LEAD-CAPACITY-HANDOVER.md)
remain planned work; these instructions do not claim that those features are
implemented.

## Delegate more as the lead's allowance falls

This is a current lead instruction, not native runtime automation. As the
lead's trustworthy allowance falls, delegate implementation to other eligible
main workers and conserve the lead for coordination, review and recovery.
Suggested operating defaults: below about 20% remaining in either the 5h or
the weekly window, delegate implementation first; below about 10%, prepare a
handover packet. These are not native thresholds and not proof of availability.
Use only a fresh observed reading with its source and age (`unio capacity
show`, or the browser's Designated AI agents & limits section); a missing,
stale or expired reading stays Unknown, and a passed reset is not recovered
allowance. `unio lead <agent>` registers a reservation only; it does not move a
live CLI conversation or switch to an acting lead. See
[lead capacity handover](LEAD-CAPACITY-HANDOVER.md).

Read [task time budgets](TASK-TIME-BUDGETS.md) before choosing a deadline.
Give substantial implementation about 90 minutes, with up to two hours for
heavier work. Keep Unio, wrapper and CLI limits consistent; keep individual
checks bounded and save early progress. A task timeout is not evidence of
exhausted subscription allowance.

## Independent reviews and owner control

Keep source execution, checks, review, acceptance, merge and publication distinct.
Use independent agents from different AI labs under the project's review rules;
the project's current owner instructions decide the review count and the
lead always performs its own assessment. The current Unio session uses
personal lead review without extra reviewer workers, under the owner-selected
YOLO mode. Preserve that explicit exception in review receipts.
Prepare reviewers separately with complete material and no peer verdicts.
Supplementary routine checks do not replace a competent final security review.
Fixes require fresh reviews of the changed candidate. Reviews reduce risk;
they cannot guarantee every error will be found.

Run the checks frozen for the task and push the exact accepted revision.
Under the current YOLO cadence, use focused checks per coherent feature and
reserve the full repository gate for release or demonstrated need. Keep releases and installation within the owner's authorization.
The owner remains in control of plans, spending and published changes.

## Where leads find these instructions

In the Unio source repository, this file and the model effort guide are in
`docs/development/`; the development index and continuation prompt link here.
The local workspace entry instructions and installed lead template should
point to readable copies before any assignment. Preserve existing owner role
cards when adding those references; do not replace custom instructions.

## Work policy commands

Before planning or delegation, run `unio policy` and read the
[work modes guide](../WORK-MODES.md) (installed as
`coord/docs/WORK-MODES.md` after `unio init`). The mode shapes scope and review
planning; the tier caps independent workflows per shared provider/account
budget (low 1, medium 2, high 4, lead included). Register the lead with
`unio lead <agent>` and group aliases sharing one budget with
`unio account <agent> <group>`. This slice provides guidance and native slot enforcement via strict budget groups.

This document is an operating policy for the lead. The current runner does
not automatically enforce these routing choices, read pricing, escalate
reasoning effort or expose a fleet-wide quota meter. Standalone installer
packaging of the guides is part of shipping work; do not infer its completion
from the presence of a repository document or a manual local guide update.

## Owner routing preference — 2026-10-07

Prefer Grok for nuanced reasoning, security and control logic, and tests that
need precise lifecycle or failure analysis. Use current Gemini workers for
bounded mechanical implementation with a clear contract and observable checks.
Claude and Codex remain main implementation options when their accounts are
available and the selected tier permits another workflow.

This preference reflects the owner's assessment and Unio's recorded experience.
Recent Gemini candidates passed focused checks but still needed lead corrections:
the work-saving draft omitted required schema and restore rules, and a timeout
fixture understated process lifetime and missed children after parent exit.
Treat a successful worker exit and green checks as evidence to inspect; personally
review the actual change before acceptance under the selected review policy.
These runs do not establish a universal model ranking.

Reassess Gemini when a newer model is actually available on the owner's route,
using completed Unio tasks and observed defects. A version announcement alone
does not change assignments. Record the exact model, effort, route and result.

Availability still controls dispatch. Preserve exhausted-account failures;
an explicit new owner assignment can authorize one fresh task attempt, without
any paid fallback, account change or automatic retry. Low tier permits one
independent workflow per shared account, so queue reasoning tasks behind an
active Grok task. Free Zen workers keep their routine supporting role.

Recorded 2026-10-16T21:06:58+02:00

<!-- UNIO_OWNER_CONTINUE_MILESTONES_20261016 -->
## Continue across authorized milestones — owner clarification

A completed version is a checkpoint, not a pause, when the owner has already
authorized further milestone work. The lead records delivery, scopes the next
functional priority, gives an estimate and continues in the same turn without
waiting for another "continue". Status questions likewise do not pause work.
Stop for an explicit owner break or an actual authority, information, access,
capacity or runtime block; preserve receipts, jobs and the exact next step first.
Do not imply work continues after the lead's turn ends. This applies to leads;
a worker still finishes only its one frozen assignment.
<!-- /UNIO_OWNER_CONTINUE_MILESTONES_20261016 -->
