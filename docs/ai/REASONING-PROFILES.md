# Reasoning effort: Low / Medium / Max

Unio has separate choices for how carefully work is checked, how many
independent workflows share an account, and how much reasoning each model
uses. Increasing one does not silently change the others.

| Choice | Options | What it changes |
| --- | --- | --- |
| Review protocol | YOLO, Balanced, Thorough | Task size, validation, independent reviews and acceptance planning. Commands are `yolo`, `balanced`, `thorough` in 0.5.13; older runners use `medium`/`safe` for the last two. |
| Coordination tier | low, medium, high | Native per-workspace concurrency caps: 1, 2 or 4 independent workflows per shared account, including the lead. |
| Reasoning profile | Low, Medium, Max | Instructions for choosing the supported effort of the lead, workers and reviewers on future assignments. |

These are Unio effort profiles, not identical native flags: **Low does not
mean pass `--effort low` to every model**. It means conserve allowance while
starting same-model/shared-subscription workers at the lowest supported effort;
other routes use their approved supported default. The lead maps the selected
profile to each route's verified controls and explains any fixed limit.

The [new-project prompts](NEW-PROJECT-PROMPT.md) start at **low coordination
tier + Low reasoning**. Balanced is the middle review protocol; its
matching CLI value is `balanced` in 0.5.13 (`medium` remains an alias). Any review protocol can use any
reasoning profile: Thorough can use Low, and YOLO can use Max.

## Same-model and shared-subscription effort default

Owner update, 2026-10-16: when assigning a worker that uses the lead's model
or shared subscription, start at its lowest supported reasoning effort.
For Codex CLI / GPT-6.1 Sol, request `low`. Keep capable implementation models;
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

## Three interchangeable reasoning profiles

| Profile | Normal behavior | Escalation |
| --- | --- | --- |
| Low — default | Start workers sharing the lead's model/subscription at the lowest supported effort; otherwise use the approved supported default. Keep a capable model on implementation; this is not a switch to weaker free models. | Raise to supported high/xhigh only when the evidence warrants it. Max stays off. |
| Medium — variable effort | Start at high for substantive work. Use supported middle for straightforward coordination or routine work. | Use supported xhigh, and max when a difficult reasoning problem warrants it and the owner selected this profile. Return to the normal level for subsequent simpler tasks. |
| Max — highest permitted effort | Request the highest verified supported and permitted setting for every new controllable lead, worker and reviewer task. | No routine effort reduction. A route whose highest eligible setting is high stays at high; unsupported levels are never invented. |

Low is a spending/effort preference, not a claim that models share one
scale. A model name containing "max" does not establish its reasoning level.
Use the route-specific [model effort guide](../development/MODEL-EFFORT.md)
and current installed help or trustworthy model metadata.

An owner's explicit selection of Medium or Max opts that project's
future assignments into supported max. It supersedes the new-project
prompt's default xhigh ceiling, without changing another project's policy.
The lead must not raise the profile on its own. Separate explicit route
holds or prohibitions remain until the owner changes them; no profile
authorizes ultra, invented effort controls or a forbidden paid route.

The model inventory also records Unio development's default effort policy.
Those default caps are distinct from a model's supported controls. An explicit
profile selection sets the new project's policy; preserve any additional
model-specific hold actually imposed on that project. Do not import the
development workspace's default ceiling as an unchangeable model capability.

Higher effort can spend the existing allowance faster. It does not create
extra quota, raise concurrency caps or authorize paid-token overage. Neither
a quota error nor a network failure is a reason to increase effort.

## Mix and change the settings independently

Any review protocol works with any reasoning profile and coordination tier.
For example, YOLO + Max + low tier means fast focused checks, the highest
permitted reasoning setting and one independent workflow per shared account.
Thorough + Low + low tier means broader independent reviews with economical
reasoning and the same concurrency limit. Reviewers also consume their account's
workflow slot; low tier does not prohibit using distinct available accounts.

Change one setting at a time. The lead must preserve the other two, record
the new choice in this project's instructions/handoff, and use it for future
assignments without asking for the same authorization on every task. A
review-protocol change cannot cancel frozen checks; an effort change cannot
restart or rewrite an active run; a tier change cannot invent extra quota.

## How the owner changes it

Edit the `Reasoning effort` field before pasting a startup prompt, or tell
an existing lead, for example:

```text
Keep Balanced review and low coordination tier. Switch reasoning effort to Medium
for future assignments. I authorize supported max when difficult reasoning
warrants it; keep explicit model holds and spending restrictions.
```

Or:

```text
Keep the current review protocol and coordination tier. Switch reasoning effort to
Max for all future assignments. I authorize supported max; request each
route's highest permitted supported effort and explain any cap or unavailable
control. Preserve account limits, explicit route holds and spending rules.
```

To lower effort again:

```text
Switch reasoning effort back to Low for future assignments. Keep my current
review protocol and coordination tier; max is off again.
```

The lead records the owner's selection in this project's own instructions
and handoff. Put the requested profile, exact route and selected effort into
each new task and its per-run configuration. Verify the route's actual
controls; do not assume flags translate across CLIs. Preserve requested and
effective effort separately, with Unknown for unverified effective settings.

The selection persists as a project instruction until the owner changes it;
do not request the same approval for every task. A worker's output cannot
authorize a profile change. Already-running tasks keep their frozen settings
and evidence. Do not interrupt, retry or edit their wrappers to apply a new
profile. If an interactive lead cannot change effort live, explain that
limitation and apply it at the next supported, orderly session boundary.

## Current implementation boundary

Reasoning profiles are **documented lead instructions**, not a native runtime
setting or automatic effort controller. There is no `unio effort` command.
The native `unio mode` and `unio tier` switches already exist; neither selects
or guarantees model effort. A cooperating lead applies the chosen profile
through verified model controls for new runs and records what was requested.

Persisted native selection and per-route enforcement are a
[planned milestone](../development/ROADMAP.md#reasoning-profile-selector).
The Unio development workspace retains its current owner-approved YOLO/low
workflow and high/supported-middle default with an xhigh ceiling. Publishing
these options does not enable max in that workspace.
