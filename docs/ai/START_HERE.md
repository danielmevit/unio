# Start a Unio AI session

Identify your role before taking action. A lead reads MASTER.md and the
project's own instructions; a worker reads WORKER.md and its one assigned
task. Do not turn a worker session into a competing lead or start additional
AI calls outside that task.

## Start a separate project session

Starting from an empty folder with a new idea? Follow
[Build a new project using Unio](NEW-PROJECT-PROMPT.md) for the launch
commands and a paste-ready lead prompt. No existing repository is required.
Choose its YOLO, Medium or Safe-first block. The selected work mode changes
validation and review planning; all three default to low subscription tier.

Open another terminal and start the chosen AI coding CLI in the other
project's checkout. This is a fresh conversation with its own task; it does
not take over a lead on another project. Existing sessions can stay open.

For a project already initialized with Unio, use its `repo/` folder and
the [README startup prompt](../../README.md#start-with-your-ai). For a
repository you want to clone into a new workspace, for example:

```bash
cd "/path/to/your/projects"
unio new "YOUR_REPOSITORY_URL" "my-other-project" antigravity
cd "my-other-project/repo"
claude
```

Replace the URL, project name and worker alias with your own choices.
This example sets up an Antigravity worker and opens Claude as the lead;
initialization does not start worker jobs. The repository needs at least one
commit. Give the new lead the task for this project, then follow the startup
checks below. It registers `claude` in this workspace only.

For an existing local checkout, preserve uncommitted work and inspect its
layout before initialization. `unio init` puts `coord/` and `wt/` beside the
Git checkout, so each project needs its own enclosing workspace. Do not
initialize unrelated checkouts into a shared coordination directory or
reclone an existing working copy just to start another conversation.

Use this project's instructions, coordination records and dashboard. The
Unio development repository's milestone handoff is for developing Unio;
another project does not inherit those tasks. A separate Git worktree alone
is not a separate Unio workspace or coordination policy.

Subscription allowances still belong to the actual shared accounts. Native
workflow caps count this workspace, not sessions in other workspaces. In low
tier, manually respect accounts already occupied elsewhere: for example,
another project's active Codex lead means no additional independent Codex
worker on that same subscription. A separate project creates no extra quota.

## Start as the lead

Start your AI coding CLI in the initialized project's `repo/` folder, beside
the workspace's `coord/` and `wt/` folders. For example, to use Claude Code:

```bash
cd "/path/to/my-project/repo"
claude
```

Use your actual project path and preferred CLI. Then paste the
[README startup prompt](../../README.md#start-with-your-ai) and describe your
task. The lead should:

1. Read applicable `AGENTS.md`, `MASTER.md`, the guides below, the newest
   coordination log and current handoff. In this repository the handoff is
   `docs/development/continue-with-ai-prompt.md`; in other projects use their
   own handoff. Private workspace files may be absent in a fresh clone.
2. Check `unio version`, `unio doctor`, `unio agents --json` and
   `unio policy --json`. These make no AI calls. Read reported warnings;
   installed binaries alone do not prove authentication or spare allowance.
   `unio smoke` makes live calls and is not part of this startup check.
3. Check this workspace's lead reservation and current coordination state.
   For a new project, register the configured alias for its lead using
   `unio lead`. If a lead is already active on this same project, follow the
   handover procedure below instead of replacing it. For Claude Code
   configured as `claude`:

   ```bash
   unio lead claude
   unio policy --json
   ```

   Use the alias in `unio agents --json`, not a guessed model name. The CLI
   command and alias can differ: `agy` commonly uses `antigravity`. Consult
   `unio account` and retain mappings for aliases sharing one subscription.
4. Run `unio dashboard ensure --open-browser` and show the returned local
   URL. Give a time estimate, confirm the intended task and delegate bounded
   work through Unio under the owner's existing authorization. Resume new
   runs only when authorized; stop new runs after the assignment cycle.

For an existing checkout not yet initialized, follow the
[setup guide](../SETUP.md) before these project commands. Do not run
`unio new` or `unio init` again on an already initialized workspace.
Other projects receive their lead guides under `../coord/docs/` during
initialization; use those when this repository's `docs/ai/` is absent.

## Switch to a different lead

This procedure replaces the lead on the same project. Starting a separate
project session does not require handing over or closing another project.

Ask the outgoing lead to finish or checkpoint the agreed task, record actual
checks, active workers and the exact next action, and leave a dated handoff
and coordination-log entry. End that lead's coordinating session before
starting the replacement. Keep any running workers and their original
receipts intact; the new lead must inspect them before assigning more work.

Start the replacement CLI in the same `repo/` folder and use the startup
steps above. `unio lead claude`, for example, replaces the previous lead
reservation once it can be admitted. In low tier, that reservation uses the
one workflow slot for its shared account: do not dispatch another independent
worker on that account. Other eligible accounts can still work concurrently.
If registration refuses, resolve the reported capacity or cooldown condition;
do not bypass it with another alias or tier change.

Registration accounts for a lead; it does not start, stop or attach a CLI,
transfer chat history, or automatically elect a replacement. The new lead
gets context from files and receipts. The dashboard shows recorded Unio
activity and stays available independently of the lead's conversation.
Automatic acting-lead handover remains planned.

## Leads: read these before planning or delegation

Read [lead routing and spending](../development/LEAD-ROUTING.md),
[bounded escalation](LEAD-ESCALATION.md),
[model scoreboard and task fit](../development/MODEL-SCOREBOARD.md),
[model effort](../development/MODEL-EFFORT.md),
[standing model roles](MODEL-ROLES.md),
[work modes and subscription tiers](../WORK-MODES.md), and
[workspace rules](../development/WORKSPACE-RULES.md). Run `unio policy`
before planning or delegation: the mode shapes scope and review planning
and the tier strictly caps independent concurrent native workflows per shared budget
(low 1, medium 2, high 4, lead included), rejecting over-dispatch. The installed copy is
`coord/docs/WORK-MODES.md` after `unio init`. Then use the
[current handoff](../development/continue-with-ai-prompt.md), the newest
workspace coordination log and actual current worker receipts. Existing
MASTER.md reading instructions name this startup file; it supplies the
public repository entry point instead of relying on unpublished role cards.

Main implementation belongs to available Grok, Antigravity/Gemini, Claude
Code or Codex workers. Keep the designated lead on planning, coordination
and final assessment by default. If a worker and one suitable replacement
struggle, the lead directly completes the correction in its existing session.
Low tier must not create another independent session on the lead's allowance.

Use the [verified free OpenCode pool](../FREE-MODELS.md) only for routine
support such as docs, formatting, inventories, boilerplate and predefined
checks. Free models must not lead, own main features or replace the lead
through a cooldown. This rule persists in every session. OpenCode subscription
models use Go; free routes require current zero prices and pinned free helper
models. No paid fallback, extra token charges, purchases or billing/auth changes.

Start reasoning at high or the supported middle; only escalate supported
levels for demonstrated difficulty, up to xhigh. Never request max or ultra;
use high when xhigh is unavailable. Read [task budgets](../development/TASK-TIME-BUDGETS.md)
before setting token, price and time limits. An
installed model or an elapsed reset estimate does not establish quota.
Preserve frozen tasks, one-invocation rules, early commits, actual checks,
independent reviews and owner control. Read the complete guides for exceptions.

These guides document operating policy. The runner gates native workflow
slots but does not enforce pricing or adapt reasoning effort automatically.
The installer supplies lead guides; initialization copies them into
`coord/docs/`. Existing custom instructions are preserved, so an older project
may need an explicit reference to the current readable guides.

## Optional subscription routes

Read the [adapter guides](../integrations/README.md) before assigning Mistral
Vibe or Perplexity work. Vibe is an explicitly pinned implementation CLI;
Perplexity researches and saves draft code proposals for a separate capable
implementation agent to review, apply and validate. Keep same-subscription
aliases in one budget group and never count an unknown effective model as
independent cross-lab acceptance. External installation and sign-in are manual.
No adapter authorizes paid fallback or an extra lead-provider workflow.

## Workers: follow the assigned scope

Use the assigned task and role card, preserve other workers' files and commit
coherent changes early. Report actual source exit and checks separately.
Do not merge, publish, change billing, retry a frozen task or create other
AI calls unless the task and owner explicitly authorize it. A source commit
alone does not establish verification, review, acceptance or public delivery.

Before delegating, read the [agent fleet guide](../development/AGENT-FLEET.md)
for approved account routes, useful assignments and current exclusions. Local
models are excluded under the current owner rule; Copilot Free uses its GitHub
Auto Balance route, not a local provider.
