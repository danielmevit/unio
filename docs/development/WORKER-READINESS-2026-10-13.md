# Worker readiness — 13 October 2026

These are small, owner-authorized readiness checks through installed Unio 0.5.14, observed at 2026-10-13T17:11:26+02:00. They are not coding benchmarks, comparative model scores or promises about remaining allowance. Each frozen task had one Source invocation. Tests sharing one budget ran sequentially; separate budgets could overlap. No extra paid-token route, account/authentication change or automatic model substitution was used.

| Route / CLI or adapter version | Requested model | Requested effort | Actual diagnostic outcome | Source / native exit |
| --- | --- | --- | --- | --- |
| Mistral subscription / Vibe vibe 2.26.1 | `mistral-medium-3-5` | high | Exact diagnostic response received | 0 / 0 |
| Mistral subscription / Vibe vibe 2.26.1 | `glm-5-3` | high | Exact diagnostic response received | 0 / 0 |
| Antigravity / agy 1.3.4 | `gemini-3.1-pro-high` | high | Selector absent from current CLI catalog; zero turns/tokens | 1 / 1 |
| GitHub Copilot Free / Copilot CLI 1.0.95. | `auto-balance` | not configurable | Exact diagnostic response received | 0 / 0 |
| Perplexity Pro / pinned web adapter perplexity-web-mcp-cli 0.16.1 | `glm53` | Thinking on; depth Unknown | Exact diagnostic response received | 0 / 0 |
| Perplexity Pro / pinned web adapter perplexity-web-mcp-cli 0.16.1 | `kimi_k3` | Thinking on; depth Unknown | Exact diagnostic response received | 0 / 0 |
| Perplexity Pro / pinned web adapter perplexity-web-mcp-cli 0.16.1 | `gpt6_sol` | Thinking on; depth Unknown | Exact diagnostic response received | 0 / 0 |
| OpenCode Go 1.18.35 | `opencode-go/glm-5.3` | high | Native log: Go usage limit exceeded; CLI remained open until timeout | 124 / 124 |
| OpenCode Go 1.18.35 | `opencode-go/qwen3.8-max` | medium | Native log: Go usage limit exceeded; CLI remained open until timeout | 124 / 124 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/big-pickle` | native default; Unknown | HTTP 403: free-tier access rejected under all-tools-denied test profile | 1 / 1 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/exo-free` | high | HTTP 410: model deprecated | 1 / 1 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/ling-3.0-flash-fin-free` | high | HTTP 400: model unavailable | 1 / 1 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/ling-3.1-flash-free` | high | Exact diagnostic response received | 0 / 0 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/longcat-2.5-preview-free` | high | Exact diagnostic response received | 0 / 0 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/mimo-v2.6-flash-free` | native default; Unknown | Exact diagnostic response received | 0 / 0 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/muse-spark-1.3-contributor-free` | high | Exact diagnostic response received | 0 / 0 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/nemotron-3-ultra-free` | native default; Unknown | Exact diagnostic response received | 0 / 0 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/nemotron-3.5-lightning-free` | native default; Unknown | Exact diagnostic response received | 0 / 0 |
| OpenCode Zen, zero-cost catalog route 1.18.35 | `opencode/space-bunny-free` | high | Exact diagnostic response received | 0 / 0 |
| Antigravity / agy 1.3.4 | `gemini-3.8-flash-high` | high | Exact diagnostic response received | 0 / 0 |

## What to use next

- Mistral/Vibe GLM and Medium, the current Antigravity Gemini selector, Copilot Auto Balance and Perplexity Thinking routes returned real responses. This supports current connectivity, not acceptance of an implementation.
- OpenCode Go reported an actual usage limit. Its remaining allowance and reset time were not established. Do not replace it with a paid Zen model or bench working free Zen routes just because Go is exhausted.
- Free models remain routine supporting workers, never lead or primary feature owners. Every tested Zen route was listed with zero input/output/cache cost; all helper/title/summary/compaction models were pinned to the same route. Fledge Alpha Free was absent; the newly listed Step 5 Preview Free was not owner-approved and was not called.
- The first Big Pickle test denied all tools and received a 403 FreeTierError. A matching [OpenCode issue](https://github.com/anomalyco/opencode/issues/53347) reports a permission-manifest correlation. We changed only not-yet-admitted tests to native tool permissions (Bash/edit ask, no automatic approval), with the same instruction to use no tools or edits. No failed task was replayed. Big Pickle with that corrected profile remains untested; the exact cause of its rejection is not proven.
- Exo and Ling Fin were listed active locally but their live calls reported deprecated/unavailable. Catalog presence is weaker evidence than an actual successful response.
- Requested settings do not prove effective model/lab/effort identity. Those effective identities and all worker allowances remain Unknown. Copilot Auto Balance does not identify a fixed underlying model. Perplexity uses Thinking on, with depth Unknown. Models without an exposed effort override use the native default, recorded as Unknown.

## Routes not given another model turn

- ChatGPT / Codex CLI 0.162.1: the read-only native account/rate-limit check at 16:32 +0200 reported 69% of the five-hour window and 80% of the weekly window remaining. This is a dated reading, not a live promise. The prior genuine Sol high implementation finished Source/native 0; the dedicated findings-completion task is recorded separately.
- Grok CLI 1.0.52: local preflight reported not authenticated. Its model list is not proof of signed-in availability. No login, model turn or claim of exhausted quota.
- Claude Code 2.1.296: owner-held; no invocation and no new quota inference.

## Implementation evidence is separate

The subsequent Mistral subscription / Vibe 2.26.1 / GLM 5.3 high task `REVIEW-FINDINGS-VIBE-1` stopped at its configured per-run cumulative token cap: Source/native 3 after 583.561 seconds, 4,046,959 reported tokens and estimated $5.8820756. This is not proof of the owner’s monthly allowance being exhausted. The lead preserved exact private bytes and WIP commit `ef24582`; the unchanged draft suite failed (12 test methods, five failures and two errors). It was not accepted or merged. A distinct dedicated ChatGPT subscription / Codex CLI 0.162.1 / GPT-6.1 Sol high completion preserved early commit `1ca4351` and completed `66a9daa`, Source/native 0. Its 19 findings, 9 receipt and 6 collection checks passed. Original native verification was INCOMPLETE because the frozen task used incorrect Markdown headings; that record remains separate from a machine-only acceptance task using the same scope/checks. The separate machine acceptance passed scope (12 patterns) and all six commands; the lead accepted the inspected implementation. See the development handoff for final release outcomes.

Private task text, raw provider logs, usage receipts, authentication stores and account identifiers are not published. Local dated start/end receipts retain original Source and native outcomes, response checks, revisions and failures under `tmp/unio-next/fleet-check-20261013/` and `tmp/unio-next/receipts/`. Native OpenCode transport retries were observed within one Source despite the requested SDK retry setting; one wrapper invocation does not prove one HTTP attempt. That adapter reliability gap remains a separate follow-up. CodeGraph improvements are explicitly deferred.
