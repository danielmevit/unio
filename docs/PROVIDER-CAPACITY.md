# Provider capacity and assignment notes

Recorded 2026-10-05. Future leads must read this file together with the newest
workspace agent-log entries before assigning providers. Refresh public rates
and account meters when making a new assignment; this is a dated observation.

## Owner's usage screenshot

Source: `firefox_4XaNhkBi1x.png`, supplied by the owner from ShareX. The
private workspace copy is `artifacts/provider-usage/2026-10-05/opencode-usage.png`
under the enclosing legacy `frugal-flock` workspace. The selected date range,
subscription tier, remaining allowances and separate thinking-token counts
are not visible. Do not infer these from the table.

| Model | Requests | Input | Cache read | Cache write | Output | Displayed cost |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| GLM 5.3 | 81 | 301.8k | 2.3M | — | 154.9k | $1.72 |
| Kimi K3 | 31 | 132.3k | 669.6k | — | 19.1k | $0.88 |
| Qwen 3.8 Max | 27 | 162 | 821.8k | 76.0k | 15.3k | $0.49 |
| DeepSeek V4 Pro | 35 | 183.6k | 1.0M | — | 20.5k | $0.37 |
| MiniMax M3 | 76 | 85.7k | 3.6M | — | 20.7k | $0.27 |
| GLM 5.3 Flash | 1 | 4.3k | 8.9k | — | 9 | <$0.01 |

Qwen input is literally 162, not 162k. Totals: 251 requests and displayed
cost $3.73 to less than $3.74. These rounded aggregates cover different tasks
and efforts; they are neither completed-task counts nor a quality ranking.
GLM accounts for about 46% of displayed cost. Large cache-read totals show
why repeated context also matters. Avoid reading the entire historical log
into every task; provide the relevant newest entries and a self-contained
scope. Keep complete review material when correctness requires it.

## Worker runs and provider requests

One worker or reviewer invocation means one pinned CLI session for its task.
That session can exchange many model requests while reading files, editing,
running tools and checking results. One invocation is not one provider
request, one token budget or one completed task. Historical private receipts
that count `invocations` or `provider_invocations` count those CLI sessions;
they do not establish the number of underlying model requests.

Use the provider's actual usage meter for allowance consumption. Preserve
task attempts, observed model requests/tokens and quota readings as separate
measurements. Repeated context and high effort can consume allowance even
while the lead sees only one active worker. The one-invocation rule prevents
automatic task retries; it does not cap that session to a single model turn.

## Public Go limits, checked 2026-10-05

[OpenCode's official Go documentation](https://opencode.ai/docs/go/) defines
five-hour, weekly and monthly allowances as 20%, 50% and 100% respectively.
Model-specific monthly budgets determine allowance consumption. Published
request counts are estimates, not guaranteed request quotas. Consult the
account's actual meters before scheduling a batch.

Prices below are dollars per million tokens; budgets refer to Go, not Go Plus.

| Model | Input | Output | Cache read | Cache write | Monthly budget |
| --- | ---: | ---: | ---: | ---: | ---: |
| GLM 5.3 | 1.40 | 4.40 | 0.26 | — | 15 |
| Kimi K3 | 3.00 | 15.00 | 0.30 | — | 15 |
| Qwen 3.8 Max | 2.00 | 6.00 | 0.25 | 2.50 | 15 |
| DeepSeek V4 Pro, off-peak | 0.66 | 1.98 | 0.022 | — | 15 |
| DeepSeek V4 Pro, peak | 1.32 | 3.96 | 0.044 | — | 15 |
| MiniMax M3 | 0.30 | 1.20 | 0.06 | — | 60 |
| GLM 5.3 Flash | 0.15 | 0.50 | 0.03 | — | 60 |

The screenshot's dollar sum alone does not establish remaining allowance
because these model budgets differ. Use the console rather than predicting
an exact reset or independent capacity for another Go model. Do not enable
paid balance fallback, upgrade a plan or change billing without owner approval.

## Observed availability and standing execution rules

At about 11:06 +0200 on 2026-10-05, the native OpenCode log recorded
`AI_APICallError: Go usage limit exceeded` for GLM, DeepSeek and Kimi in the
rename batch. Their CLIs remained running without completing useful work;
the lead interrupted them and preserved receipts. A running process is not
proof that a provider is making progress. Check both native provider logs
and Unio run receipts when output stalls.

The owner later reported that the Go five-hour window would reset in
1h57m. A receipt created from `date` recorded an approximate reset of
2026-10-05 13:30:02 +0200. This estimate is historical, not a recurring
schedule, proof that weekly/monthly capacity remains, or permission to
retry the original rename tasks.

The owner authorizes use of available AIs for Unio and milestone work;
ordinary provider assignment and cross-company review need no repeated
permission. For this rename cycle, each task gets one invocation, no
automatic retries, a pinned model/effort, a wall-clock budget and preserved
receipts. The owner explicitly granted one Gemini replacement for B and
one Grok replacement for D after their original Go failures. Further work
must have a distinct, concrete task; do not disguise a retry as a new ID.

Keep GLM 5.3 at high effort. The local live findings in
[FINDINGS-2026-10-05.md](FINDINGS-2026-10-05.md) record task results and
effort compatibility; Flash is not a substitute for the approved GLM race.
Use local verified quality and availability alongside cost when choosing
a model. Do not assume an installed CLI has usable quota, or that the same
company reached through another subscription shares the same capacity.

Resume the orchestrator before authorized runs, stop it after launching or
finishing the bounded batch, preserve interrupted work, and record every
checkpoint in the shared log with timestamps from `date`. Independent
review must come from another company, followed by the lead's own review.
Global installation and release publication still require fresh owner approval.

## Latest owner capacity report

On 2026-10-05 the owner reported that the OpenCode Go five-hour limit had
reset and authorized GLM 5.3 at high effort for this milestone run. This is
a dated owner report, not a live probe or evidence of weekly/monthly headroom.
One bounded task invocation and cross-company review remain required; no
automatic retry or paid fallback is enabled.

## Remaining-quota monitoring roadmap

The owner requested a live indicator and proactive lead checks on
2026-10-05. Read [PROVIDER-QUOTA-MONITORING.md](PROVIDER-QUOTA-MONITORING.md)
for verified adapter inputs and the delivery sequence. A read-only Codex
probe succeeded; remaining OpenCode Go capacity is still Unknown without
an actual account-meter reading. Session costs and reset reports do not
establish current remaining allowance. No fleet-wide meter is implemented.

## Additional owner-authorized Anthropic worker

On 2026-10-05 the owner added Claude Opus 5.5 at high effort for milestone
tasks. The private per-run seat pins `claude-opus-5-5` and `--effort high`,
disables model fallback and retains structured model-usage evidence. Local
CLI 2.1.289 is signed in through first-party Claude Pro. That sign-in does
not establish remaining five-hour or weekly allowance. Do not conflate its
subscription with OpenCode Go or assume an automatic quota adapter exists.

Its first assigned task was QUEUE-APPROVAL-FIX-1: a bounded correction of five
reproduced failures in Gemini's queue candidate. Its structured receipt
confirmed Opus 5.5, high effort and one invocation. The lead then found
additional state/layout failures and assigned a concrete Codex correction.
Two other companies review the final combined candidate, followed by the
lead, under the owner's new separate-review rule. Each invocation still
receives its own receipt and deadline, with no automatic paid retry.

## Lead startup routing policy (2026-10-06)

Read [lead routing and spending](development/LEAD-ROUTING.md) and
[model effort](development/MODEL-EFFORT.md) before every new assignment.
The owner permits the exact verified-free Zen MiMo/LongCat routes for routine
chores; OpenCode subscription models still use Go. No extra per-token spend,
paid fallback or billing/auth changes are authorized. Pin helper models too
and recheck zero input/output/cache prices before each free-route call.
Prefer stronger actually-available subscription agents for complex work and
final assessment. Unknown quota and old reset estimates remain Unknown;
this policy does not restore capacity or implement an automatic meter.

## Interrupted Git worktrees and suspected Grok 402 balance exhaustion

- **Interrupted Git worktrees**: End-of-run output and task reports surface
  Git in-progress metadata (`MERGE_HEAD`, `rebase-merge`, `rebase-apply`,
  `REBASE_HEAD`, `CHERRY_PICK_HEAD`, `REVERT_HEAD`, `BISECT_LOG`, `sequencer`)
  and bounded unmerged paths (up to 20 paths plus `(+N more)` total count)
  read-only from `.git` metadata and `ls-files --unmerged -z` without mutating,
  resetting, or aborting the worktree, preserving original Source exit codes
  even when post-run snapshots fail (`end-unbound`).
- **Suspected Grok 402 balance exhaustion**: When a failed run outputs
  recognizable Grok 402 balance-exhaustion text (such as `API error (status 402
  Payment Required): Grok Build usage balance exhausted`), `LIMIT_RE` flags it as
  suspected limit language (`wall=1`, stderr warning with `unio off <agent>`
  recovery guidance) while keeping `Adapter outcome: Unknown`, preserving the
  real process exit, and incrementing `failed_attempts` normally.
- **Operator action and deferred confirmation/auto-off**: Confirmed
  `quota_exhausted` classification, loop-brake exemptions, and automatic holds
  remain deferred. Exact typed terminal quota evidence for this installed Grok
  CLI path is unavailable (bare stdout/stderr JSON, quoted output, and
  human-prefixed prose are not a supported native error boundary), and
  project-only persistent policy with fail-safe concurrent manual-hold
  coexistence in `$CONF_DIR/off` is not established. Benching (`unio off` /
  `unio on`), loop-brake grants (`unio allow-retry`), and worktree conflict
  resolution remain explicit operator actions.
