# Choose reasoning effort separately

Unio has separate choices for how carefully work is checked, how many
independent workflows share an account, and how much reasoning each model
uses. Increasing one does not silently change the others.

| Choice | Options | What it changes |
| --- | --- | --- |
| Review protocol | YOLO, Balanced, Thorough | Task size, validation, independent reviews and acceptance planning. Native modes are `yolo`, `medium`, `safe`. |
| Coordination tier | low, medium, high | Native per-workspace concurrency caps: 1, 2 or 4 independent workflows per shared account, including the lead. |
| Reasoning profile | Economy, Adaptive, Maximum | Instructions for choosing the supported effort of the lead, workers and reviewers on future assignments. |

The [new-project prompts](NEW-PROJECT-PROMPT.md) start at **low coordination
tier + Economy reasoning**. Balanced is the middle review protocol; its
existing CLI value remains `medium`. Any review protocol can use any
reasoning profile: Thorough can use Economy, and YOLO can use Maximum.

## Three reasoning profiles

| Profile | Normal behavior | Escalation |
| --- | --- | --- |
| Economy — starting profile | Use the model's supported middle level, or high where that is the suitable permitted setting. Keep a capable model on implementation; this is not a switch to weaker free models. | Raise to supported high/xhigh only when the evidence warrants it. Max stays off. |
| Adaptive — variable effort | Start at high for substantive work. Use supported middle for straightforward coordination or routine work. | Use supported xhigh, and max when a difficult reasoning problem warrants it and the owner selected this profile. Return to the normal level for subsequent simpler tasks. |
| Maximum — highest permitted effort | Request the highest verified supported and permitted setting for every new controllable lead, worker and reviewer task. | No routine effort reduction. A route whose highest eligible setting is high stays at high; unsupported levels are never invented. |

Economy is a spending/effort preference, not a claim that models share one
scale. A model name containing "max" does not establish its reasoning level.
Use the route-specific [model effort guide](../development/MODEL-EFFORT.md)
and current installed help or trustworthy model metadata.

An owner's explicit selection of Adaptive or Maximum opts that project's
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

## How the owner changes it

Edit the `Reasoning profile` field before pasting a startup prompt, or tell
an existing lead, for example:

```text
Keep Balanced review and low coordination tier. Switch reasoning to Adaptive
for future assignments. I authorize supported max when difficult reasoning
warrants it; keep explicit model holds and spending restrictions.
```

Or:

```text
Keep the current review protocol and coordination tier. Switch reasoning to
Maximum for all future assignments. I authorize supported max; request each
route's highest permitted supported effort and explain any cap or unavailable
control. Preserve account limits, explicit route holds and spending rules.
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
