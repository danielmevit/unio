# Free model routes and project trials

Owner-approved candidate list, checked on 2026-10-07. These are exact OpenCode
Zen routes, separate from the owner's exhausted OpenCode Go subscription.
The owner now permits all listed routes when they are verifiably free; this
supersedes the earlier MiMo/LongCat-only exception for future assignments.
Use existing native authentication. No billing changes or paid fallback.

**Routine worker-only role:** every free route in this pool may perform
precise supporting assignments such as documentation, formatting, mechanical
edits, boilerplate or predefined checks. Free models must never lead, own
main features, make final acceptance decisions or replace the lead during a
cooldown. This applies in every future session. Substantive implementation
belongs to available Grok, Antigravity/Gemini, Claude Code or Codex workers;
see [the standing model roles](ai/MODEL-ROLES.md). This is the owner's routing
policy, not a measured reasoning-score claim.

[OpenCode's official pricing](https://opencode.ai/docs/zen/#pricing) lists
all eleven as free. A read-only local `opencode models opencode --verbose`
on 2026-10-07 found ten with input, output, cache-read and cache-write costs
all zero. Exo Free was absent from the local catalog despite the screenshot
and official listing. Do not dispatch Exo until local route eligibility is
established. The catalog proves configuration/pricing metadata, not usable
quota, successful transport, code quality or permanent free access.

Before every assignment, recheck current official pricing and native costs.
Refuse missing/conflicting/nonzero prices. Pin both the primary and helper
`small_model` to the eligible route and disable paid fallback. Do not
silently switch a failed free call onto its paid model counterpart.

## Current route snapshot — 2026-10-21

OpenCode CLI 1.19.3 now exposes additional free routes. The official
[model pricing table](https://opencode.ai/v2/docs/console/models/#pricing)
and native catalog agree on zero input/output/cache prices for the three below.
Free access is promotional and must be rechecked before a new assignment.
These are configured routes, not proof of usable allowance or effective identity.
Earlier dated inventories and trials below remain historical evidence.

| Exact verified-free route | Exposed variants | Requested setting under the current ceiling | Supporting work |
| --- | --- | --- | --- |
| `opencode/glm-5.3-flash-free` | low, high, max | high | Supplied-context documentation checks and mechanical inventories |
| `opencode/deepseek-v4.1-flash-free` | low, high, max | high | Bounded predefined checks and supplementary observations |
| `opencode/minimax-m3.1-flash-free` | low, medium, high, xhigh, max | xhigh | Documentation consistency, formatting and inventories |

The owner's default is now the highest supported **permitted** effort for free
workers. This workspace still excludes max/ultra; xhigh is the ceiling. A route
with no exposed override stays Unknown. Pin primary and helper models to the
same eligible free ID. Calls already frozen retain their original settings.
Free workers keep the supporting role defined above.

The corresponding `opencode-go/glm-5.3-flash` and
`opencode-go/deepseek-v4.1-flash` are different subscription routes with nonzero
catalog prices. They may use the owner's included Go allowance, never an extra
pay-as-you-go fallback. Model names alone do not establish shared-account
capacity. Native/catalog availability is not a successful provider call.

## Inventory and routine assignments

These task suggestions are routing guidance, not established quality rankings.
Supported effort variants below come from this installed gateway, not guesses
from a different model, CLI or direct lab API. Start at high or the supported
middle for the task; when no override is exposed, record effort as unknown.

| Display name | Exact route | Price/availability evidence | Observed effort variants | Routine supporting assignment |
| --- | --- | --- | --- | --- |
| Exo Free | `opencode/exo-free` | Official free listing; missing locally | Not observed | Availability check before any assignment |
| Fledge Alpha Free | `opencode/fledge-alpha-free` | Native input/output/cache all 0 | low, high, max | Predefined checks or boilerplate; current country unavailable |
| Ling 3.1 Flash Free | `opencode/ling-3.1-flash-free` | Native input/output/cache all 0 | low, medium, high | File/link inventories or documentation checks |
| LongCat 2.5 Preview Free | `opencode/longcat-2.5-preview-free` | Native input/output/cache all 0 | low, medium, high | Documentation consistency and mechanical inventories |
| Space Bunny Free | `opencode/space-bunny-free` | Native input/output/cache all 0 | low, medium, high, xhigh, max | Formatting or mechanical edits; identity not verified |
| MiMo-V2.6-Flash Free | `opencode/mimo-v2.6-flash-free` | Native input/output/cache all 0 | No exposed override | Documentation, simple configuration and predefined checks |
| Muse Spark 1.3 Free | `opencode/muse-spark-1.3-contributor-free` | Native input/output/cache all 0 | minimal, low, medium, high, xhigh | Documentation and mechanical changes |
| Ling 3.0 Flash Fin Free | `opencode/ling-3.0-flash-fin-free` | Native input/output/cache all 0 | low, medium, high | Structured inventories; do not infer expertise from its name |
| Nemotron 3.5 Lightning Free | `opencode/nemotron-3.5-lightning-free` | Native input/output/cache all 0 | No exposed override | Execute predefined regression checks |
| Nemotron 3 Ultra Free | `opencode/nemotron-3-ultra-free` | Native input/output/cache all 0 | No exposed override | Predefined checks and supplementary inventories |
| Big Pickle | `opencode/big-pickle` | Native input/output/cache all 0 | No exposed override | Formatting and documentation; identity not verified |

## What the small research establishes

The exact [LongCat 2.5 release notes](https://longcat.ai/platform/docs/ChangeLog.html)
describe coding, image understanding and development-tool integration. This
provides capability context, while current Unio policy limits it to routine support; it does not prove superiority over
another agent or the same results through OpenCode's free gateway.

[NVIDIA's Lightning cookbook](https://github.com/NVIDIA-NeMo/Nemotron/blob/main/usage-cookbook/Nemotron-3.5-Lightning/README.md)
describes fast reasoning, coding and structured tool use. Under the current role policy, use it for predefined checks or mechanical
work; the capability claim does not authorize main feature ownership.

The [Ling 3.1 gateway announcement](https://vercel.com/changelog/ling-3-1-flash-is-now-available-on-ai-gateway)
describes coding, multi-step analysis and tool use. That is capability context
from another gateway; its pricing, promotion dates and effort controls do not
apply to the OpenCode Zen route. Test the actual route used by Unio.

For MiMo, Muse Spark and the remaining candidates, gateway metadata provides
route and effort eligibility, while model quality is still a local question.
Do not apply another MiMo version's published scores to V2.6 Flash. Stealth
names such as Big Pickle and Space Bunny do not establish their underlying
AI lab: they cannot count as an independently identified review lab without
verified provenance. Fledge/Exo identity is likewise not established here.

## What Unio has actually observed

| Exact model and task | Actual outcome | What can be concluded |
| --- | --- | --- |
| MiMo V2.6 Flash: LEAD-POLICY-STARTUP-DOCS-1 review, 2026-10-06 | Native exit 0, complete material, APPROVE; candidate subsequently integrated. | It completed this bounded documentation review. This does not establish defect-detection accuracy or coding ability. |
| LongCat 2.5 Preview: ROADMAP-PRIORITIES-1 review, 2026-10-06 | Native exit 0 and APPROVE. | It completed one scoped roadmap assessment at high effort. |
| LongCat 2.5 Preview: LEAD-POLICY-STARTUP-DOCS-1 review, 2026-10-06 | Native exit 0, complete material, APPROVE at medium effort; candidate subsequently integrated. | It completed a second documentation review; the sample remains small. |
| Nemotron 3 Ultra: BROWSER-API-ERRORS-1 review, 2026-10-06 | Native exit 0, complete material, APPROVE. | It completed a code-review call; approval alone does not establish that it found all defects or that the whole workflow was shipped. |
| MiMo V2.6 Flash: WORK-POLICY-1 Source, 2026-10-07 | Native timeout exit 124 after the 1500-second worker bound, with delayed shutdown; zero commits or changed files. No verification/review/acceptance. | It did not deliver this broad CLI/state assignment. This is a task/route-specific failure, not a judgment of code that was never produced. |
| Muse Spark1.3: WORK-POLICY-CLI-1 Source, 2026-10-07 | Saved two commits; native Source0 and focused4/4 PASS, but personal lead review REQUEST-CHANGES for proven state-update and file-write gaps. Not accepted or merged. | It delivered a bounded candidate in about seven minutes. Passing its initial checks did not establish correctness; acceptance depends on fixing the demonstrated findings. |
| Fledge Alpha: WORK-POLICY-STATE-FIX-1 Source, 2026-10-07 | Provider refused: model unavailable in the current country; exit1, zero edits, no verification or acceptance. No retry. | A catalog route with zero costs did not establish local transport availability or code quality. |
| Muse Spark1.3: WORK-POLICY-GUARD-1 Source, 2026-10-07 | Lead stopped the run after the owner restricted free workers to routine support; two edited files preserved unverified. Native exit241, no verification or acceptance. | An operator reroute is not a model quality verdict. Main implementation transfers to the designated implementation agents. |

The underlying private receipts remain in the workspace. Do not publish raw
prompts, log output or authentication to make these conclusions portable.
Update this table with exact checked outcomes after each Source finishes;
a model's final self-report is not sufficient evidence.

## Trials should deliver work, not consume it

Use pending routine project tasks: a documentation correction, formatting,
a file/link inventory, a mechanical edit or execution of predefined checks.
Give core features, complex fixes and UI implementation to main workers. Keep
scopes and expectations clear and compare similar work before recommending
one model over another. Avoid eleven-way races or benchmark chores invented
solely to fill a scoreboard. Each trial follows the current
[work mode and budget tier](WORK-MODES.md), invocation rules and owner scope.

Treat aliases sharing a gateway/account allowance as one budget group; in
low tier, one independent workflow may occupy that group at once. Internal
helpers can support the same authorized assignment. Different model names
and AI labs do not automatically establish different subscription budgets.
Do not launch a second Zen trial while another occupies that shared group.

The planned [project evidence feature](development/MODEL-EXPERIENCE.md)
will collect outcomes automatically and explain task-fit recommendations.
Until delivered, use native receipts, `unio score`, focused checks, actual
review findings and dated conclusions. No new rating engine is claimed here.
