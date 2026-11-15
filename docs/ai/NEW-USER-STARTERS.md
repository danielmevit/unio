# Try Unio on a new project

[Unio on GitHub](https://github.com/danielmevit/unio)

Two basic prompts for starting Unio on a **different project**: one for a
single AI subscription, one for several. Paste one into your AI coding CLI,
opened in that project's folder, and fill in the brackets.

Both follow the same way of working:

- The lead scopes the goal into small tasks and delegates them.
- Each worker gets one focused task in its own worktree (isolated copy).
- Workers run meaningful checks; the lead looks at real code and test results.
- Review: one independent reviewer from another AI lab where available,
  plus the lead's own assessment.
- Every task records the route, model, requested effort, actual exit and
  checks, and ends with a clear handoff.
- Only subscriptions you already have; no paid API fallback.

## Before you start: lead effort

The prompts ask for the **adaptive managed lead** (AUTO effort: LOW for
routine coordination, XHIGH for substantive planning and review, no model
calls while waiting for workers). This is available for testing only; the
current stable release, 0.5.30, does not include it. See
[adaptive lead effort](../ADAPTIVE-LEAD-EFFORT.md).

A prompt cannot change the reasoning effort of an ordinary (unmanaged) CLI
session. If the controls are missing, the lead should say so and keep its
normal effort. To try the managed lead:

1. Use a separate project and session, not a lead that is already working.
2. Retire or close any unmanaged lead for that project yourself first.
3. Start the managed lead explicitly with its supported commands.
4. Manual LOW or XHIGH works only where the route has been verified.

Coordination tier (how many workflows may run per account) and reasoning
effort (how hard a model thinks) are separate settings.

## One subscription

```text
Help me try Unio on this project: [PROJECT PATH].
Goal: [SMALL FEATURE OR FIX].
My only AI subscription: [SUBSCRIPTION / CLI].

Check the installed Unio version, its supported commands and this project's
instructions. Use the managed lead with AUTO effort (LOW for routine
coordination, XHIGH for planning and review, no calls while waiting) only if
those controls actually work here; otherwise tell me and continue normally.

Scope a small task, give me a time estimate, then delegate it through Unio to
a worker in its own worktree with meaningful checks and a clear handoff.

I authorize ONE worker on my subscription beside you, the lead. Keep the real
account mapping and your lead reservation. Use the native budget grant, and a
temporary medium coordination tier only if needed; restore the previous tier
when the worker is idle. This adds no extra allowance. Start the worker at
its lowest supported effort and raise it only for real reasoning problems.

Review the result yourself. Independent review from another AI lab is not
available with one subscription; say so, and follow any stricter project
approval rules. Report what ran, how it exited and what passed. Keep changes
local for this first trial.
```

Simpler alternative: skip the worker exception and run one workflow at a
time. The lead plans and hands off, the session closes, and one worker then
does the task.

## Multiple subscriptions

```text
Help me try Unio on this project: [PROJECT PATH].
Goal: [FEATURE OR FIX].
My subscriptions and CLIs: [LIST THEM].
You are the lead; other subscriptions provide the workers.

Check the installed Unio version, its supported commands, this project's
instructions and the available routes. Use low coordination tier: one
workflow per real shared account, including you. Keep actual account
mappings, holds and STOP.

Use the managed lead with AUTO effort (LOW for routine coordination, XHIGH
for planning and review, no calls while waiting) only if those controls
actually work here; otherwise tell me and continue normally.

Split the goal into focused tasks and give me a time estimate. Delegate
through Unio, one worktree per worker, running independent tasks in parallel
when accounts allow. Give each worker a suitable supported effort, separate
from your own; raise it for reasoning problems, not for network, login or
quota failures.

Check real code and test results. Get one independent review from a
different AI lab than the author, then make your own final assessment. Do not
add more reviewers unless a real disagreement or gap remains. Keep failures
and partial work; follow any stricter project approval rules.

Use included subscriptions only. Give short updates: goal, progress, next
step. Keep changes local for this first trial.
```

These examples do not lift holds in an existing project, and they do not
prove login, model identity, remaining allowance or a successful result.
Requested settings stay Unknown until there is evidence.
