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
  plus the lead's own assessment, as in the default
  [lead review policy](LEAD-REVIEW-POLICY.md).
- Every task records the route, model, requested effort, actual exit and
  checks, and ends with a clear handoff.
- Only subscriptions you already have; no paid API fallback.

## Lead effort in these prompts

These prompts run your AI CLI as an ordinary lead at its normal, fixed
reasoning effort. A prompt cannot change the effort of the CLI session it
is pasted into. That is fine: the prompts work without any adaptive
controls.

The prompts tell the AI **not** to start `unio lead-session` itself. A
managed lead started from inside an AI CLI would be a second lead on the
same subscription while the pasted-into session keeps running, and its
budget would not be counted correctly. If you want to try adaptive effort,
use the separate, optional
[managed lead trial](#optional-adaptive-managed-lead-trial) below, driven
by you from a terminal.

Coordination tier (how many workflows may run per account) and reasoning
effort (how hard a model thinks) are separate settings.

## One subscription

```text
Help me try Unio on this project: [PROJECT PATH].
Goal: [SMALL FEATURE OR FIX].
My only AI subscription: [SUBSCRIPTION / CLI].

Check the installed Unio version, its supported commands and this project's
instructions. You are an ordinary lead at your normal effort. Do not start
`unio lead-session` or any other lead session yourself.

Scope a small task, give me a time estimate, then delegate it through Unio to
a worker in its own worktree with meaningful checks and a clear handoff.

I authorize ONE worker on my subscription beside you, the lead. Keep the real
account mapping and your lead reservation. Use the native budget grant, and a
temporary medium coordination tier only if needed; restore the previous tier
when the worker is idle. This adds no extra allowance. Start the worker at
its lowest supported effort and raise it only for real reasoning problems.

Review the result yourself. If my subscription offers only one eligible AI
lab, report that cross-lab review is unavailable. If it offers other labs,
review sequentially within the same account budget. Follow stricter project
approvals. Report what ran, how it exited and what passed. Keep changes local.
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

You are an ordinary lead at your normal effort. Do not start
`unio lead-session` or any other lead session yourself.

Split the goal into focused tasks and give me a time estimate. Delegate
through Unio, one worktree per worker, running independent tasks in parallel
when accounts allow. Give each worker a suitable supported effort, separate
from your own; raise it for reasoning problems, not for network, login or
quota failures.

Check real code and test results. Get one independent worker review from
another AI lab than the lead where available, then make your own assessment.
Honor stricter project rules about independence from the author. Do not
add more reviewers unless a real disagreement or gap remains. Keep failures
and partial work; follow any stricter project approval rules.

Use included subscriptions only. Give short updates: goal, progress, next
step. Keep changes local for this first trial.
```

These examples do not lift holds in an existing project, and they do not
prove login, model identity, remaining allowance or a successful result.
Record requested model and effort explicitly. Effective model and effort
remain Unknown unless there is evidence.

## Optional: adaptive managed lead trial

This is experimental. Use installed Unio 0.5.32 or newer: in 0.5.31 the first `run` fails with `no rollout found` before
any model turn. Check `unio version` and `unio lead-session --help` on
your machine. It is a separate trial that you drive from a terminal. It is
not something to paste into an AI CLI, and it does not take over an
existing AI CLI chat. A new session starts a new thread: give it a goal
file, your turn files and a short handoff, not a whole earlier chat.

What it is: `unio lead-session` owns its own Codex app-server connection
and sends one lead turn each time you run a command. It requests LOW
effort for routine coordination and XHIGH for planning and review. While it
waits for workers, nothing is sent and no inference happens. Status and
control commands make no provider calls. `run` and `recover` make control
calls (connection setup, thread resume or read, interrupt). Control calls
are not inference.

What it is not: it does not recognize planning from your text, it does not
watch workers and it does not schedule phases. You choose `--kind` and you
record worker events. Requested effort is recorded. Effective model and
effort stay Unknown.

Requirements:

- Codex CLI with a ChatGPT subscription login. API keys are refused.
  Other CLIs keep their fixed effort.
- A Unio project whose registered lead is `codex`, with the real account
  group (`unio lead codex`, `unio account codex <group>`).
- **Close your existing AI CLI lead session for this project first.** Only
  then start the managed lead from a separate terminal, so only one lead
  uses that subscription.
- The usual project grants, holds, STOP and stricter review rules still
  apply. The trial adds no allowance.

Commands, from the project folder:

```sh
# 1. Start: owned session; its thread is created by the first turn (policy adaptive: LOW coordination, XHIGH planning/review)
unio lead-session start --goal goal.txt --model <codex-model>

# 2. One lead turn per command. You write each turn's input to a file.
unio lead-session run --file turn-1.txt --request-id t1                  # LOW
unio lead-session run --file plan.txt --request-id t2 --kind planning    # XHIGH

# 3. When the lead delegates a worker, record it; when it finishes, say so
unio lead-session worker register w1
unio lead-session worker terminal w1
unio lead-session run --file review.txt --request-id t3   # review, XHIGH

# 4. Effort controls (LOW or XHIGH only)
unio lead-session effort request xhigh   # pending: next turn only
unio lead-session effort manual low      # manual: suspends AUTO
unio lead-session effort auto            # back to AUTO

# 5. Inspect, recover, stop
unio lead-session status
unio lead-session output
unio lead-session recover [--interrupt]  # a turn whose end was not seen
unio lead-session stop                   # blocks new turns; workers keep running
```

What to expect:

- `run` waits for the turn to finish, up to `--turn-wait` (default 3600
  seconds). At the limit it asks Codex to interrupt that exact turn. If no
  end is confirmed, the result is `unknown` (exit 6) and nothing is resent.
  Use `recover` later on the same thread. `--turn-wait 0` is refused.
- Rerunning the same `--request-id` with the same file returns the
  recorded result and starts no new turn.
- A rejected turn keeps your pending effort request and the review wakeup.
- The shown effort is the concrete requested level of each turn (`low`
  or `xhigh`); the adaptive or manual policy is secondary. Effective
  effort stays Unknown.
- One session allows up to 64 request ids. To continue past a limit, stop
  it and start a new one; the new thread does not carry the old context.
- Lead turns cannot approve commands or file changes. The turn uses your
  own Codex sandbox and approval settings, and any approval request is
  declined. Unio does not widen them.

Details, including safe rollback: [adaptive lead effort](../ADAPTIVE-LEAD-EFFORT.md).
Rolling back to 0.5.31 needs a pre-upgrade state backup; never delete
`coord/lead-effort/` to work around it.
