# Lead routing, reasoning effort and spending

Read [the current agent fleet](AGENT-FLEET.md), this policy, [bounded escalation](../ai/LEAD-ESCALATION.md), the
[model scoreboard](MODEL-SCOREBOARD.md) and [model effort](MODEL-EFFORT.md) before planning
assignments and at the start of each new lead session. Follow the owner's
current instructions and the selected project's rules. These defaults apply
whenever Unio is active; they are not permission to spend beyond an owner's
approved plans, task scope or invocation budget.

## Give a rough estimate before new features

When introducing a new feature or milestone, tell the owner what the next
useful slice delivers and give a rough elapsed-time range. Distinguish coding
from required checks, publication and installation. Name material uncertainty,
such as an unavailable worker or an unresolved dependency, and update the range
when findings change it. Estimates guide priorities; they are not guarantees
or automatic time limits on a healthy worker. Prefer finishing the current
bounded slice and releasing checked work over continually expanding its scope.

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
After a worker and one suitable replacement fail to finish, it directly
implements the remaining correction in its existing session. Follow
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
workflow, so do not launch a second independent job on its shared allowance.
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
