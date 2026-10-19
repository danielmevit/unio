# Assigning the Unio agent fleet

Read this at lead startup alongside [routing](https://github.com/danielmevit/unio/blob/main/docs/development/LEAD-ROUTING.md),
[effort](https://github.com/danielmevit/unio/blob/main/docs/development/MODEL-EFFORT.md), [roles](https://github.com/danielmevit/unio/blob/main/docs/ai/MODEL-ROLES.md) and the
[task-fit scoreboard](https://github.com/danielmevit/unio/blob/main/docs/development/MODEL-SCOREBOARD.md). This is an assignment guide,
not an automatic scheduler or proof that an account has allowance left.
The account inventory below was checked on 2026-10-10. Current owner
instructions and fresher observations take precedence.

## Antigravity worker inventory — 2026-10-19

Owner-authorized additional worker options were confirmed in the installed
agy1.4.2 `models` catalog: `claude-opus-4-6-thinking` (Claude Opus4.6 Thinking),
`claude-sonnet-4-6` (Sonnet4.6 Thinking) and `gpt-oss-120b-medium` (GPT-OSS120B
Medium), alongside Gemini3.8Flash low/medium/high selectors. The owner's new
worker authorization specifically names Opus4.6 and GPT-OSS120B; cataloguing
Sonnet does not itself assign a task. Keep exact subscription route, CLI,
selector and requested effort in each task receipt. Effective identity and
supported per-model effort controls require evidence; do not infer them from
the generic CLI's accepted effort flags.

These are Antigravity routes, separate from Claude Code or ChatGPT account
routes. The owner's Claude Code hold is unchanged. The owner reports different
model allowances, but this catalog exposes no remaining quota, reset or pool
separation. Conservatively retain one Antigravity budget group and sequential
admission until actual independent allowance evidence is available. A catalog
entry is not a successful call, benchmark or proof of available capacity.

Use a bounded real task to assess fit: Opus for substantial review/architecture
work when available; GPT-OSS initially for a clearly scoped worker task. These
are starting assignments, not measured rankings. A hosted GPT-OSS selection
does not establish local execution, self-hosting, fine-tuning access, no third-
party transmission or free usage. Verify deployment and plan terms separately;
no extra paid API fallback or billing changes are authorized.

The packaged Antigravity adapter currently pins Gemini selectors and a specific
CLI version. Do not pretend new catalog entries automatically enable that
adapter. Use an explicit task-frozen custom route with truthful receipts, or
implement/review an adapter extension separately. Preserve existing routes.

### Observed Antigravity controls and trials — 2026-10-19

agy1.4.2 rejected `--effort high` with `claude-opus-4-6-thinking` before
inference. Select that fixed Thinking model without an effort flag; record
requested thinking and effective effort Unknown. Likewise GPT-OSS uses the
fixed `gpt-oss-120b-medium` selector. Generic help flags do not establish
per-model controls. Keep the packaged Gemini adapter's supported surface intact.

Opus completed a real full-code review; a later bounded delta call hit a genuine
quota response with a stated reset wait. That observation applies to that route
at that time, not every Antigravity model. GPT-OSS returned CLI0 but failed to
deliver its claimed report file, so the trial was unaccepted. Gemini delivered
review text but capture/stream failures remain separate from approval. See the
[dated scoreboard](MODEL-SCOREBOARD.md#operator-reliability-observations--2026-10-19).
No model's quota or effective identity can be inferred from another's result.

## GPT-OSS delivery qualification — 2026-10-19 follow-up

The AGY1.4.2 / `gpt-oss-120b-medium` trial's expected report was missing.
A later inspection recovered a report in Antigravity's internal artifact
directory: the model had used tools and written to the wrong destination.
The recovered approval still fails review: it claimed successful tests while
the recorded command returned `pytest: command not found`, and did not establish
the requested full-code coverage. Original failure receipts remain unchanged.

A separate documentation-inventory session returned only a task acknowledgement
and a promise to proceed, with no requested report. These are two observed
incomplete deliveries, not proof that this model cannot use tools or a universal
ranking. Effective identity, effort and remaining allowance remain Unknown.

For this exact route, defer autonomous repository audits and final code approval
until a bounded completion task establishes actual delivery and evidence quality.
Any future inline-answer qualification must assess its real output; it is not
already proven by catalog presence or process exit0. Preserve each attempt.

For report workers, request the completed deliverable in the same invocation,
use the native `report-only` outcome and an adapter that publishes the actual
bounded artifact, and verify its exact binding before acceptance. A heading that
merely says "read-only report" does not select the native outcome. CLI success,
file creation, a valid report and an accepted review are separate facts. Do not
repair an acknowledgement into a report or infer account policy from its text.

## Make each assignment visible

Follow the [mandatory reporting rule](LEAD-ROUTING.md#name-the-model-route-in-every-work-summary).
Tell the owner which subscription/provider route, CLI, model and effort owns
each task, with its current state and latest observed progress. At handoff or
completion, retain dated run evidence and the saved revision. For GLM, always
distinguish Mistral/Vibe, OpenCode Go and Perplexity Pro; the same model name
does not identify the same account, capability or allowance.

## Routing and budget are different

Copilot Auto Balance chooses eligible hosted models for each prompt; it does
not pin a model, AI lab or reasoning level. Unio's low tier admits one independent
workflow per shared account, including its registered lead. Several model names
on that subscription do not create extra groups. Session usage does not show
remaining account allowance.

## Give each account useful work

| Account route | Best starting assignment | Controls and boundaries |
| --- | --- | --- |
| Existing Codex lead | Plan, delegate, inspect actual changes, integrate and preserve handoffs | Keep one existing lead session. Low tier does not permit another independent Codex job on that account. |
| Claude Code / Opus 5.5 | Substantial implementation, UI interaction, stateful corrections and bounded architecture work | High normally; supported xhigh only when justified. Check owner holds and current account availability. |
| Grok | Nuanced control logic, security reasoning and precise failure analysis | Owner-preferred reasoning worker when available; high normally. A historical quota failure is dated evidence. |
| Antigravity / Gemini3.8Flash | Bounded implementation or independent code inspection with clear artifacts | agy1.4.2 lists low/medium/high selectors. Pin the exact selector; verify controls for that route rather than borrowing Gemini3.1Pro settings. Preserve stream errors and correction burden. |
| Mistral Vibe / GLM 5.3 | Implementation from a concrete contract, including more involved code | Explicit GLM/high pin. Use existing monthly subscription; task estimates do not measure remaining allowance. |
| Mistral Vibe / Medium 3.5 | Smaller implementation or mechanical corrections when GLM is busy or unsuitable | Same Mistral budget as GLM: queue behind it in low tier. No fair checked ranking between the two yet. |
| Perplexity Pro / GLM 5.3 Thinking | Research, integration plans and supplementary code analysis using selected public context | Proposal only. Its matched plan separated occupied slots from quota more clearly; this is a small sample. |
| Perplexity Pro / Kimi K3 Thinking | Quick draft functions, small proposed patches and a complementary view of supplied code | Proposal only. Faster in one matched batch; both models generated faulty test fixtures. Independently check proposed code and tests. |
| GitHub Copilot Free / Auto Balance | Documentation drafts, inventories and small mechanical code proposals | One checked documentation draft delivered; native usage labelled GPT-6 Luna. Balance is routing, not effort or a fixed AI lab. Local/BYOK models are excluded. |
| OpenCode Go | Available GLM 5.3, Qwen 3.8, Kimi K3 or other explicitly approved capable routes for implementation | Use Go only, never a paid Zen counterpart. Models share the Go account budget; an old reset estimate proves no current capacity. |
| Verified-free OpenCode Zen pool | Documentation, formatting, inventories, boilerplate and predefined supplementary checks | Routine workers only. Verify current official/native zero input, output and cache prices; pin primary and helpers. Never lead or own main features. |

These assignments use current owner preferences and completed Unio work,
not advertised benchmark scores. Copilot's Free plan is an account tier;
it does not establish the reasoning ability or identity of Auto's selected
model. Start it on small work and widen its scope only with checked results
and owner policy. The [free inventory](https://github.com/danielmevit/unio/blob/main/docs/FREE-MODELS.md) covers all eleven
approved Zen candidates and exact routes; Exo still needs local eligibility.
Keep local models unused on this machine under the owner's current rule.

## Plan a small batch rather than a model race

For a functional milestone, give one capable implementation worker a
concrete change. Meanwhile, a different account can draft documentation or
research a relevant question if that work is independently useful. Scripts
can run deterministic inventories and checks without an AI session. Do not
create busywork or eleven-way benchmarks to keep every model occupied.

For example, Vibe GLM can implement a bounded save-retention correction,
while Copilot drafts its operator explanation from a supplied contract.
Perplexity can analyze a specific unresolved question if the implementation
actually needs it. The lead checks the real patch and test evidence under
the chosen work mode. This example is not an instruction to launch those
jobs without first freezing their tasks and checking account slots.

A research response or proposed patch is not a completed implementation.
A capable implementation worker or the existing lead checks, applies and
validates suitable proposals in its own worktree. Generated tests need
independent scrutiny. The [matched Perplexity report](https://github.com/danielmevit/unio/blob/main/docs/development/PERPLEXITY-FIELD-TRIALS-2026-10-10.md)
shows why successful delivery and test authorship are separate from correctness.

## Group by allowance, not by model name

Low tier permits one independent native workflow per shared account,
including a registered lead. Give all aliases using one subscription the
same budget label with `unio account`. The actual alias must match the
prefix before the first hyphen in its worker name.

| Budget label example | Aliases that belong together |
| --- | --- |
| `codex` | All sessions using that Codex subscription, including the lead |
| `claude` | Claude Code aliases on that Claude subscription |
| `grok` | Grok aliases on that Grok subscription |
| `antigravity` | Models reached through that Antigravity allowance |
| `mistral` | Vibe GLM and Medium 3.5 aliases on the same subscription |
| `perplexity` | Perplexity GLM, Kimi and other approved routes on that Pro account |
| `copilot` | Copilot aliases using that GitHub account |
| `opencode` | Go and free Zen aliases using the same OpenCode account unless separate allowances are established |

GLM through Vibe and GLM through Perplexity do not automatically share
allowance. Conversely, different model names inside one subscription do
not create separate budgets. Groups enforce workflow concurrency, not
current quota. Unmanaged sessions remain uncounted: respect known owner
activity elsewhere. Never merge unrelated accounts solely because their
models come from the same AI lab.

## Before each assignment

1. Read the newest owner instructions, scoreboard and capacity observation.
   Check `unio policy` and current native jobs; availability can be Unknown.
2. Choose a task-fitting route with owner-approved funding. Freeze model or
   Auto profile, supported effort, scope, checks and task-sized deadline.
3. Map its alias to the actual shared budget. Run `unio resume`, then one
   authorized `unio run`; close the batch with `unio stop`.
4. Preserve commits, drafts, failures and receipts. Review the actual result;
   a zero exit or model self-report does not establish acceptance.
5. Update the scoreboard with task, route, settings, observed outcome and
   rework. Keep operational failures separate from code-quality findings.

Workers sharing the lead model/subscription start at the lowest supported effort;
other routes start at high or the supported middle. xhigh is this workspace's ceiling. No max/ultra,
paid fallback, topups or billing changes. Thinking is a route switch, not
an adjustable effort scale. Auto Balance does not pin the underlying lab,
so it cannot establish independent cross-lab review by itself. If a worker
struggles, preserve its evidence and use a suitable replacement. Follow the
current owner LOW-Sol correction rule in LEAD-ROUTING.md: one focused shared-
budget worker beside the lead requires the real account reservation, narrow
consent and temporary coordination tier only as needed. No blind retry loops.

## Setup and evidence

- [Optional integrations](https://github.com/danielmevit/unio/blob/main/docs/integrations/README.md): installed Vibe and
  Perplexity and Copilot adapters; Copilot is packaged starting in 0.5.9.
- [Copilot Free / Balanced](https://github.com/danielmevit/unio/blob/main/docs/integrations/GITHUB-COPILOT.md): native route,
  exclusions, private proposal receipts and current trial status.
- [Capacity and freshness](https://github.com/danielmevit/unio/blob/main/docs/development/CAPACITY-READINGS.md): remaining allowance is
  Unknown unless a supported observation or dated owner reading supplies it.
- [Model experience](https://github.com/danielmevit/unio/blob/main/docs/development/MODEL-EXPERIENCE.md): future automatic task-fit profiles;
  the current guide and scoreboard are instructions, not runtime scoring.
