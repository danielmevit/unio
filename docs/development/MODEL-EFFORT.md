# Choosing model effort in Unio

This is the lead's operating guide for choosing how much reasoning a worker
or reviewer should use. Read it before assigning work. It also applies to
the lead's own next session when that session's settings are controllable.
Owner instructions and the project's run, retry and spending rules take
precedence. This guide does not authorize another invocation.

Read [lead routing and spending](LEAD-ROUTING.md) and [task budgets](TASK-TIME-BUDGETS.md) alongside this guide.
A listed model is an inventory entry, not authorization to use a paid route.


## Current owner override and Antigravity controls — 2026-10-19

Workers sharing the lead's model or subscription start at the lowest supported
effort: Codex CLI / GPT-6.1 Sol uses LOW. Increase one supported step only after
a demonstrated reasoning gap; quota, network and authentication failures do
not justify escalation. Other approved routes retain their high/middle defaults.
This overrides older blanket high defaults below. Coordination tier is separate.

agy1.4.2 lists Gemini3.8Flash low/medium/high, Claude Opus4.6 Thinking and
GPT-OSS120B Medium. The Opus fixed Thinking selector rejects `--effort high`:
use `claude-opus-4-6-thinking` without that flag and record thinking/requested,
effective Unknown. GPT-OSS uses fixed `gpt-oss-120b-medium`. Catalog presence
is not current capacity, a privacy guarantee or proof of separate allowance.
See [actual route trials](AGENT-FLEET.md#observed-antigravity-controls-and-trials--2026-10-19).

## Current selector check — 2026-10-13

Antigravity / agy 1.3.4 currently advertises `gemini-3.8-flash-high`,
`gemini-3.8-flash-medium` and `gemini-3.8-flash-low`. The high selector returned
a successful Unio diagnostic with no separate `--effort` flag. The previously
advertised `gemini-3.1-pro-high` was rejected as unavailable with zero
turns/tokens; its earlier fixed-effort guidance is historical, not current
availability. Run the native `agy models` metadata command before selecting
an exact route, and use the advertised selector rather than inventing a mapping
from generic CLI effort options. Do not replay a failed frozen task automatically.

The [dated readiness evidence](https://github.com/danielmevit/unio/blob/main/docs/development/WORKER-READINESS-2026-10-13.md)
also distinguishes OpenCode Go usage limits from free-model access, deprecation
and availability errors. Catalog presence, a successful tiny answer, and a
remaining-allowance reading establish different facts. None proves effective
model identity or a quality ranking. CodeGraph improvements remain deferred.

## Select review, effort and concurrency separately

Read the [Low / Medium / Max reasoning profiles](https://github.com/danielmevit/unio/blob/main/docs/ai/REASONING-PROFILES.md)
(or installed `templates/REASONING-PROFILES.md`) at startup. New-project prompts
provide explicit effort and coordination-tier fields. Any effort profile
can accompany YOLO, Balanced or Thorough. The owner can switch any axis for
future assignments; preserve the other two, record the choice in the project's
instructions/handoff, and map only verified supported model controls.

Low is the economical default, using LOW for workers sharing the lead
model/subscription and supported middle/high for other routes, with max off. Owner-selected Medium adapts effort and can use supported max for hard
reasoning; Max requests each route's highest permitted setting for new tasks.
These profile names are lead instructions, not universal native effort flags
or an implemented `unio effort` command. Explicit project route holds and
spending restrictions remain. Frozen active tasks keep their original settings.

The xhigh/no-max defaults below remain the current Unio development workspace's
policy. An explicit owner's effort selection sets their new project's policy;
do not treat this workspace's default ceiling as a universal model limitation.
No profile changes account concurrency, role restrictions or actual allowance.

## Default and escalation

Apply the current shared-model/subscription LOW override first. For other
routes start with **high**, or the supported **middle level** for a model whose
scale differs. Use medium for routine documentation, coordination and
well-understood edits when the model supports it. Do not default to maximum effort or a model's more expensive implicit default. The route
table below identifies exceptions where a middle setting is unavailable.

Increase effort when evidence points to reasoning difficulty: an agent
misses interacting constraints, cannot explain a reproducible defect,
overlooks a demonstrated security boundary, or struggles with a genuinely
complex design. First give it the relevant evidence and a focused question.
Missing context and an overly broad task often need a clearer assignment.
Do not increase effort or retry indefinitely: follow
[bounded worker escalation and direct lead takeover](../ai/LEAD-ESCALATION.md)
when one worker and one suitable replacement cannot finish the correction.

Use the next **effective, supported** level, with **xhigh as the ceiling**.
The owner updated this standing policy on 2026-10-09: do not request max or
ultra for any lead, worker or reviewer. High remains the ordinary starting
choice. Routes without xhigh stay at high; do not invent a variant or silently
translate xhigh into max. A route exposing only max is ineligible under this
policy unless another supported non-max setting is verified. Do not omit a
variant to hide a known maximum default. Unknown effective effort stays Unknown.
The capability inventory below may describe levels that this policy forbids.
Record the reason, scope, time limit and known allowance before escalation.
Return the next ordinary task to its default; escalation is not permanent.

Authentication failures, usage limits, database locks, network errors,
prompt-size failures and missing tools are operational problems. Increasing
effort will not fix them. Preserve the actual failure and resolve its cause.
An elapsed reset estimate is not proof that capacity returned.

## Check the actual route

A model, its CLI and its gateway can expose different controls. Check the
exact model ID, installed CLI version and route metadata before choosing a
setting. A flag accepted by a CLI does not prove the model uses that level.
Likewise, a reasoning-capable model need not expose adjustable effort.

The following inventory was researched on **2026-10-06** using official
documentation and installed CLI help/model metadata. It covers the model
pins used in this project; it is not a promise of account availability.
Recheck it when a model, gateway or CLI changes. OpenCode observations below
come from `opencode models opencode-go --verbose` and
`opencode models opencode --verbose`, without generating model responses.

| Agent / exact route | Exposed controls | Starting choice | Escalation and limits |
| --- | --- | --- | --- |
| Codex / `gpt-6.1-sol` | Model: low, medium, high, xhigh, max; CLI configuration `model_reasoning_effort` | low when sharing the lead model/subscription; otherwise current owner-approved default | xhigh ceiling; max is forbidden by owner policy. Do not infer ultra support from another model or client. |
| Claude / `claude-opus-5-5` | low, medium, high, xhigh, max; installed Claude Code accepts `--effort` | high; medium for routine coordination or writing | xhigh ceiling; max is forbidden by owner policy. The model's API default is medium; pin the chosen level explicitly. |
| Antigravity / `gemini-3.1-pro-high`, `gemini-3.1-pro-low` | Native `agy models` exposes High and Low for Gemini 3.1 Pro | `gemini-3.1-pro-high`; omit `--effort` on agy 1.3.4 | High is the top exposed level. Match the low model with low only when deliberately chosen. Generic CLI medium/xhigh/max flags do not create Pro variants; high/xhigh was rejected before inference. |
| Antigravity / `claude-opus-4-6-thinking` | Native catalog lists the Thinking model; `--effort high` was rejected before inference on2026-10-07 | Exact model default; omit `--effort` | Effective reasoning level remains Unknown. This route is separate from Claude Code Opus5.5 and does not expose its effort scale. |
| Grok / `grok-4.7` | low, medium, high, xhigh; installed Grok Build uses `--reasoning-effort` / `--effort` | high; medium for routine work | xhigh is the highest documented level. No documented max on this model. |
| Copilot Free / `auto --auto-tier balance` | Balance is routing; this Auto route rejects explicit effort flags | Omit effort; effective effort Unknown | Native1.0.95 rejected an explicit medium flag before a response. Do not equate Balance with high/xhigh or a fixed model/lab. No max/ultra or local/BYOK fallback. See [Copilot setup](../integrations/GITHUB-COPILOT.md). |
| Perplexity Pro / `glm_5_3_thinking`, `kimik3thinking` | Thinking identifiers only in the pinned connector; no graduated effort control | Explicit Thinking route | No high/xhigh setting; do not map Thinking to max. Effective reasoning depth stays Unknown. See the [matched field trials](https://github.com/danielmevit/unio/blob/main/docs/development/PERPLEXITY-FIELD-TRIALS-2026-10-10.md). |
| GLM / `opencode-go/glm-5.3` | Installed variants: low, high, max; `reasoningEffort` | high, the middle of this scale | Stay at high; max is forbidden. No medium/xhigh variant. Native Z.ai default is max, so pin high rather than omit it. |
| DeepSeek / `opencode-go/deepseek-v4-pro` | Installed variants: high, max; `reasoningEffort` | high | Stay at high; max is forbidden. Direct DeepSeek also documents low, but this installed route does not expose a low variant. Direct API xhigh maps to high, so it is not an escalation. |
| Kimi / `opencode-go/kimi-k3` | Installed variant: max only; `reasoningEffort` | No eligible setting verified under the no-max policy | Only max is catalogued: choose another eligible route rather than silently inherit it. Do not manufacture high. Moonshot's direct K3 API offers low/high/max, but that is a different route. Prefer an already configured adjustable agent when budget control matters. |
| Qwen / `opencode-go/qwen3.8-max` | Installed variants: low, medium, xhigh; route option `effort` | medium, the middle of this scale | xhigh for harder work. Direct Alibaba API maps high/max to xhigh; those labels do not create extra levels. The word max in the model name is not the selected effort. |
| MiniMax / `opencode-go/minimax-m3` | Installed variants: none (thinking disabled), thinking (adaptive thinking) | thinking | A thinking toggle, not a graduated high/xhigh/max scale. M3.1 effort documentation must not be applied to this M3 pin. |
| NVIDIA / `opencode/nemotron-3-ultra-free` | Reasoning capability true; installed variants empty | Inherited route default; requested/effective effort unknown | No exposed effort override on this route. NVIDIA's self-hosted thinking controls do not prove Zen support. |
| InclusionAI / `opencode/ling-3.1-flash-free` | Installed variants: low, medium, high; `reasoningEffort` | high; medium for routine work | high is the highest exposed variant. Endpoint availability is a separate check. |
| Meituan / `opencode/longcat-2.5-preview-free` | Installed variants: low, medium, high; `reasoningEffort` | high; medium for routine work | high is the highest exposed variant. The direct LongCat API's thinking toggle is a different control. Gateway-effective depth needs response evidence. |
| Xiaomi / `opencode/mimo-v2.6-flash-free` | Reasoning capability true; installed variants empty | Inherited route default; requested/effective effort unknown | No exposed effort override. Research did not verify direct effort documentation for this exact V2.6 pin; do not borrow V2.5 settings. |

Empty variants mean **no exposed override**, not no reasoning and not high
by default. If a route cannot meet the requested high/middle policy, record
that exception. Do not silently translate labels or create a custom variant
without verifying the gateway actually supports its parameter. Check advertised model variants rather than inferring from generic CLI effort choices. Unknown effective effort stays unknown.

On **2026-10-07**, the owner clarified the Antigravity Pro choices and a
non-generating `agy models` query confirmed `gemini-3.1-pro-high` (High) and
`gemini-3.1-pro-low` (Low). Those are the exposed Pro variants. The generic
`agy --help` effort list covers other models too; match the model variant
to its effort. A native Pro-high/xhigh dispatch was rejected before inference.
Keep Pro at high by default. Record requested effort separately from the
effective reasoning observed in a response.

On **2026-10-13**, agy **1.3.4** rejected the matching high model plus
`--effort high` before inference (zero turns/tokens). For these fixed Gemini
variants, select `--model gemini-3.1-pro-high` or deliberately select the low
model, and **omit `--effort`**. This supersedes the older matching-flag example;
the generic effort list does not establish a supported override for this model.
The rejection is CLI evidence, not a Gemini code-quality or quota verdict.

## How the lead applies a choice

Use a separate per-run configuration and a wrapper pinned to the exact
model and setting. Avoid changing global CLI settings or a shared wrapper
under a running task. A frozen task's existing model/effort stays unchanged.

Examples of the effort portion of a wrapper are:

```bash
codex exec -m gpt-6.1-sol -c 'model_reasoning_effort="high"' -
claude --model claude-opus-5-5 --effort high
agy --model gemini-3.1-pro-high
grok --model grok-4.7 --reasoning-effort high
opencode run --model opencode-go/glm-5.3 --variant high
opencode run --model opencode-go/qwen3.8-max --variant medium
opencode run --model opencode-go/minimax-m3 --variant thinking
```

These illustrate flags; they are not complete unattended-run commands.
Preserve the project's permission mode, safe prompt transport, timeouts and
native Unio lifecycle. Quote paths, including the config directory. Check
installed help before using a command on a different machine.

For every new assignment, record:

- Exact model ID, AI lab, CLI version and gateway route.
- Requested effort, its actual flag/variant and the evidence supporting it.
- Effective effort if the response proves it; otherwise **unknown**.
- Why this level fits the task, especially any escalation to xhigh.
- Time/spending bounds, observed capacity and the age of that observation.
- Task ID and any relationship to an earlier failed or corrected task.

Choosing another effort does not waive task scope, owner approval, retry
restrictions or review requirements. Under a one-invocation rule, do not
rerun an unchanged task merely to increase effort. A genuine correction
needs a bounded new task describing the demonstrated defect. Preserve the
original call, logs and result. Adjust the next authorized assignment;
mid-session changes require an explicitly supported, authorized mechanism.

Reviewers choose their own supported level for the task's risk. Keep their
reviews independent, check the same complete candidate, and honor the
project's required number of reviews from different AI labs. Higher effort
does not replace verification or guarantee that every mistake is caught.

## Primary references

- [GPT-6.1 Sol model controls](https://developers.openai.com/api/docs/models/gpt-6.1-sol) and [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).
- [Claude effort and Opus 5.5](https://platform.claude.com/docs/en/build-with-claude/effort).
- [Gemini thinking levels](https://ai.google.dev/gemini-api/docs/thinking).
- [Grok reasoning controls](https://docs.x.ai/developers/model-capabilities/text/reasoning).
- [GLM-5.3 reasoning parameters](https://docs.z.ai/guides/llm/glm-5.3).
- [DeepSeek thinking and effort mappings](https://api-docs.deepseek.com/guides/thinking_mode/).
- [Moonshot's Kimi K3 announcement](https://forum.moonshot.ai/t/kimi-k3-is-here-our-most-capable-model/480); its direct API differs from this project's Go route.
- [Alibaba's Qwen parameters and mappings](https://www.alibabacloud.com/help/en/model-studio/qwen-api-via-openai-chat-completions).
- [MiniMax model-specific controls](https://platform.minimax.io/docs/guides/text-generation).
- [NVIDIA's Nemotron Ultra model card](https://build.nvidia.com/nvidia/nemotron-3-ultra-550b-a55b/modelcard), [InclusionAI's Ling repository](https://github.com/inclusionAI/Ling), [LongCat's OpenCode integration](https://longcat.chat/platform/docs/OpenCode.html) and [Xiaomi's thinking guide](https://platform.xiaomimimo.com/docs/en-US/usage-guide/passing-back-reasoning_content). These do not establish every Zen gateway override.
- [OpenCode variants](https://opencode.ai/docs/models/) and [Zen routes](https://opencode.ai/docs/zen/). Match their current catalogue to the installed CLI's resolved metadata.

Provider documentation describes capabilities; local metadata describes the
exposed route; actual run receipts describe what was requested and observed.
Keep those three kinds of evidence distinct.

## Free worker override — 2026-10-21

For verified-free supporting workers, use the exact route's highest supported
setting within the current Unio development ceiling (xhigh, no max/ultra).
MiniMax M3.1 Flash Free currently maps to xhigh; GLM 5.3 Flash Free and DeepSeek
V4.1 Flash Free map to high. Empty variant metadata means no exposed override,
so requested/effective effort remain Unknown. Recheck native variants and all
zero prices for each assignment; don't infer effort from a model's name.
This supersedes routine-medium suggestions for future free workers. Existing
frozen assignments and subscription-worker defaults remain unchanged. See
[the routing rule](LEAD-ROUTING.md#free-supporting-workers-use-their-highest-permitted-effort).

## Opus final-review effort — owner update, 2026-10-23T09:44:09+02:00

Preferred final review: Claude subscription / Claude Code / `claude-opus-5-5` /
`xhigh` whenever available and eligible. Native CLI2.1.303 advertises xhigh and
a real Oct23 review completed with that request. Pin `--model claude-opus-5-5`
and `--effort xhigh`; requested settings and reported client model labels are
not proof of effective serving identity/effort. Preserve Unknowns and exact exits.
Do not silently downgrade, use max/ultra, buy API tokens, override a hold or assume
quota from sign-in. Keep a second independent reviewer from another AI lab and
the lead assessment. This reviewer preference does not raise implementation
worker defaults: shared Codex/Sol workers still start LOW, with evidence-based
gradual escalation. See LEAD-ROUTING.md for availability and fallback rules.
