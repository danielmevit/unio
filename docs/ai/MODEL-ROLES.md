# Model roles — standing Unio instructions

Read this before assigning work in every new lead session. These defaults
apply across sessions, handoffs and cooldown recovery; they are not a temporary
choice for one run. The owner can explicitly change the policy.

| Role | Agents | Work they own |
| --- | --- | --- |
| Lead | The owner's designated subscription agent | Planning, contracts, delegation, coordination, final assessment and authorized integration; follow the owner's explicit correction route before direct implementation |
| Main implementation workers | Grok, Antigravity/Gemini, Claude Code and Codex | Product features, core behavior, architecture within the assigned scope, complex debugging, UI and substantive security corrections |
| Optional implementation workers | Explicitly approved Mistral Vibe / GLM 5.3 and Medium 3.5 routes | Scoped implementation through the pinned adapter; inspect actual results |
| Research and proposal workers | Perplexity Pro Thinking routes | Selected-context research and code drafts for a capable implementation agent to check and apply |
| Routine supporting workers | The verified-free OpenCode Zen pool and owner-approved Copilot Free / Auto Balance route | Documentation, formatting, inventories, mechanical edits, boilerplate, running predefined checks and supplementary observations |

The free pool must **never lead, own main feature implementation, perform
final acceptance or replace a subscription lead during a cooldown**. A free
worker follows a precise bounded task and reports results to the lead. If a
routine assignment reveals a design problem, difficult bug or security issue,
preserve the findings and give the substantive work to a main implementation
worker. Raising a free model's effort does not change its permitted role.

The distinction is an owner-selected routing policy, not a claim that every
listed model has a measured quality or reasoning score. See the exact free
routes and checked outcomes in [the inventory](../FREE-MODELS.md).

## When delegation struggles

For Unio development, the [2026-10-13 dedicated correction rule](LEAD-ESCALATION.md#dedicated-fix-worker--unio-owner-rule-2026-10-13)
supersedes direct lead fixes: dispatch one bounded Codex CLI / GPT-6.1 Sol /
high task through Unio, then personally assess its result. One such correction
worker alongside the registered lead is explicitly owner-authorized; preserve
the real shared budget and record/restore any temporary native tier change.
Other project owners can explicitly select their own correction route.

Follow [worker, replacement, lead](LEAD-ESCALATION.md): one suitable worker,
one capable available replacement, then, absent an owner override, the lead finishes the
remaining correction in its existing session. Preserve the previous work
and failures; do not send a struggling model another blind attempt. In low
tier this is the same lead workflow, not permission for another worker CLI.
Consult the [task-fit scoreboard](../development/MODEL-SCOREBOARD.md).

## Choose available workers without duplicating the lead

Choose among the main implementation agents by task fit, current allowance
and the owner's latest availability information. Antigravity (`agy`) is the
multi-model platform used for Gemini here; record its actual selected model.
Do not silently substitute a different account, CLI or paid API route.

In low tier, an agent already serving as lead occupies its shared budget's
single independent workflow. For example, a Codex lead must not launch a
second independent Codex implementation session without an explicit owner
exception. The focused Unio correction rule above is such an exception. Other
available budgets
can work concurrently. Authorized helpers inside one workflow are allowed;
they do not turn it into several independent features or test assignments.
Read the separate [mode and tier guide](../WORK-MODES.md).

Capacity changes are temporary; role definitions persist. If Claude has hit
a weekly limit and Codex leads, assign substantive work to available Grok
and Antigravity/Gemini. Revisit dated failures when the owner reports restored
availability, using supported metadata or one authorized task invocation.
An installed CLI or model list alone does not prove usable quota. Preserve
actual failures; never blindly retry a frozen task or promote a free worker
because a main implementation route is unavailable.

## Spending and verification

Use existing owner-approved subscriptions. Free workers require current
official and native zero prices, with primary and helper models pinned to
the same eligible free route. No paid fallback, purchases, billing or
authentication changes. Follow the [routing and effort guide](../development/LEAD-ROUTING.md).

Use the selected work mode and the task's frozen checks. A supporting worker's
output, successful script run or approval does not replace the lead's review
or establish acceptance. Record real outcomes rather than running a separate
benchmark campaign to fill a scorecard. These are instructions for agents;
the runtime does not automatically identify a model's class from its name.

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
