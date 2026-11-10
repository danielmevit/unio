# Use Mistral Vibe as an optional Unio worker

This optional adapter runs your installed Vibe CLI in one of exactly two
explicitly validated versions: the pinned **2.26.1** and the validated
**3.1.1**. Any other version refuses before any provider invocation
(`unsupported_cli`), and a model alias that is not validated for the detected
version refuses before launch as well.

- On 2.26.1 the adapter supports GLM 5.3 (`zai-glm-5-3`, AI lab Z.ai) and
  Mistral Medium 3.5 (`mistral-medium-3-5`, AI lab Mistral), selected through
  the tested process-local `VIBE_*` model overlay, with `--output streaming`.
- On 3.1.1 the adapter supports GLM 5.3 (`glm-5-3` → wire `zai-glm-5-3`) and
  Mistral Large 4 (`mistral-large-4-0-3` → wire `mistral-large-4-0`, AI lab
  Mistral), selected through the documented `--model ALIAS` flag, with
  `--output json`. The `VIBE_*` model overlay is a 2.26.1-only mechanism and
  is never assumed on 3.1.1.

All models use the Mistral transport and share one subscription budget.

## Where the adapter lives

- Source checkout: `tools/vibe-worker.py`.
- Installed copy: `~/.config/unio/lib/adapters/vibe-worker.py` (or under
  `$UNIO_CONF_DIR`). Unio 0.5.8 and later package the exact reviewed script.
  Use the source-checkout path with 0.5.7 or earlier.

`unio integrations` (or `--json`) shows the installed path and whether the file
is present. It reads only file metadata: it never runs Vibe or the adapter, so
`installed: true` says nothing about sign-in or remaining allowance.

## Configure an explicit worker

Sign in manually through the native Vibe CLI using the intended subscription.
The adapter does not install Vibe, log in, copy credentials, change billing or
select another provider as fallback. It preserves the native HOME/VIBE_HOME
location; process-local model overrides do not change the owner's config files.
The owner remains responsible for selecting a funded native account.

Create an existing private receipts directory, then add shell command lines to
an explicit Unio `agents.conf`. Replace the example paths with your own quoted
absolute paths. TASKFILE supplies the prompt without putting its contents in argv.

```text
vibeglm=python3 '/path/to/repo/tools/vibe-worker.py' --model glm-5-3 --receipt-dir '/path/to/private receipts'
vibe35=python3 '/path/to/repo/tools/vibe-worker.py' --model mistral-medium-3-5 --receipt-dir '/path/to/private receipts'
vibem4=python3 '/path/to/repo/tools/vibe-worker.py' --model mistral-large-4-0-3 --receipt-dir '/path/to/private receipts'
```

Command shapes are identical across versions; the adapter detects
`vibe --version` at launch and applies the matching, validated behavior. The
`--model` choice is validated per version: `mistral-large-4-0-3` is refused on
2.26.1 and `mistral-medium-3-5` is refused on 3.1.1, always before the provider
is invoked. The offline route-contract preflight accepts the union of aliases
and cap choices; the adapter applies the version-specific rule before launch
with the same shared parser and bounds, so dispatch and execution agree.

With an installer that packages the adapter, point the same lines at the
installed copy instead, for example
`python3 '/home/you/.config/unio/lib/adapters/vibe-worker.py' --model glm-5-3 ...`.
Both copies are byte-identical; pins, effort and bounds do not change.

The file uses `alias=command`, not TOML worker sections. Make the directory
owner-only (for example `mkdir -m 700 '/path/to/private receipts'`). Map both aliases
to the same shared budget before running them:

```bash
unio account vibeglm mistral
unio account vibe35 mistral
unio resume
UNIO_TIMEOUT=5460 unio run vibeglm-feature TASK-ID
unio stop
unio verify vibeglm-feature TASK-ID
```

Low tier permits one independent workflow in that Mistral group. Different
Mistral, OpenCode and Perplexity accounts remain separate even if they offer the
same GLM model. Follow the current project's invocation, review and acceptance
rules; an adapter's exit zero alone does not establish acceptable code.

## Model pins, effort and task bounds

On 2.26.1 the exact wire model, full definition, positive prices, one-model
wire-name allowlist, compaction model and utility selections are explicit
process-local overlays. Title generation, experiments, updates, connectors,
MCP and subagent calls are disabled. On 3.1.1 no `VIBE_*` model overlay is
used; the exact alias is passed as `--model` and the CLI resolves it against
the owner's own catalog. The built-in auto-approve agent receives only
bash/read_file/write_file/edit/grep tools on both versions. Worktrees and
these flags provide trusted-host execution, not an operating-system sandbox.

The per-session selection is verified from the native export's returned
metadata, not from the catalog default: the receipt records
`session_selection` as `verified` only when the export's redacted config shows
the requested alias, expected wire name and requested thinking; contradictory
metadata is an explicit `mismatch` and missing metadata stays `unknown`.
Neither can be recorded as a verified selection. Configuration/export metadata
is not server identity evidence: effective model/effort and remaining
subscription allowance remain Unknown on every version.

High is the default; optional `--thinking {low,medium,high}` remains accepted
on both versions. On 2.26.1 the level travels through the process-local model
override; on 3.1.1 there is no per-run thinking flag, so the level comes from
the alias's catalog entry and the adapter verifies it from session metadata,
recording a mismatch explicitly instead of silently substituting. Do not
promise xhigh or server-proven effective effort on this route. The standing
[effort policy](../development/MODEL-EFFORT.md) permits at most supported xhigh on
other routes.

Ordinary implementation defaults are 2,000,000 cumulative tokens, $5 estimated
price, 120 turns and 90 minutes. Substantial work can explicitly select up to 16,000,000 cumulative tokens,
$10, up to 180 turns and 120 minutes. Values must be finite decimal numbers
within those supported bounds (parsed as integers/floats only; nan/inf/hex or
fractional integers are refused). These bounds are the adapter's documented
supported range and are identical for the dispatch contract and the adapter,
on both versions. There is no hidden universal turn policy: 120 is only the
default and the owner picks a task-sized value.

On 3.1.1 each cap additionally accepts the documented choice `none`, which
omits the native flag so the CLI's own default applies; the observed native
limits are then recorded from the export (`null` means omitted). Omission is
not an unlimited-provider claim and never permits a paid fallback. On 2.26.1
`none` is refused before launch. The adapter's owned-process supervisor bound
(`--time-limit` value plus 20 seconds, or 7220 when omitted), the output
bounds and the outer `UNIO_TIMEOUT` remain separate, recorded limits.

Keep the native Unio deadline above the CLI allowance plus shutdown margin:
5460 seconds for the default, or 7260 for a 7200-second CLI task. An earlier
outer timeout still wins; increasing only --max-tokens cannot extend it.

Token totals include context sent again across steps; they are different from a
model's context window or per-response output budget. A final call can overshoot
Vibe's token/estimated-price threshold. Explicit model prices make its estimate
meaningful, but do not measure remaining included monthly allowance or prevent
subscription overage by themselves. A local token/time/price stop is not provider
exhaustion, and never changes Unio's bench, policy or authentication state.
See [task budgets](../development/TASK-TIME-BUDGETS.md) for planning guidance.

## Receipts and actual outcomes

Each invocation creates a new private run directory beneath the explicit existing
parent. It contains a bounded frozen UTF-8 task copy, native stdout and native export/
journal. Those files can contain task text and session data: keep them private.
The adapter stdout and `receipt.json` contain only allowlisted operational metadata,
never the raw prompt, answer, config, exception or authentication material.

The receipt reports the detected CLI version, requested/configured model and
requested thinking, actual process exit, time, task hash, selected bounds,
omitted caps, the supervisor bound, the export-observed native limits and the
`session_selection` verdict. Effective model/effort and remaining
subscription allowance remain Unknown. Native schema-1 usage uses input_tokens,
output_tokens, cached_input_tokens and total_tokens; cached input is included
in input_tokens and never double-counted in the total. cost_usd is the CLI's
catalog-rate estimate, not an invoice, a guaranteed bill ceiling or proof of
subscription spend; native missing usage/cost remain null. For the unpriced
Mistral Large 4 alias, USD telemetry stays Unknown (never 0/free) even when
the native export carries a cost figure derived from catalog rates. Additive
budget telemetry prefers native usage, then partial cumulative owned-stream
estimates (2.26.1) or the message-list assistant count (3.1.1); see
[worker observations](../WORKER-OUTCOMES.md) for the estimation caveats. Malformed, duplicate or
nonfinite export data cannot establish success. A nonzero native result is preserved;
a missing/invalid export after exit zero makes the adapter fail with exit 2,
and exit 0 alone never establishes required-delivery completeness (the native
required-artifact gates stay authoritative).

On 3.1.1 the headless run uses `--output json`: stdout is one JSON message
list. The actual final completed assistant reply is the LAST assistant entry
of that list and can carry a verdict/summary absent from the saved export
report; the adapter never selects an earlier acknowledgement. The receipt
records only bounded provenance for it (list length, assistant count, final
index, SHA-256, byte sizes); the raw message list stays in the private
`native-stdout.log`. A malformed or non-list stdout is recorded as `invalid`
without changing the exit semantics.

Vibe exits 0 when finished, 1 on usage/configuration errors, 2 for infrastructure
failure, and 3 for limits/refusal (including its own `--time-limit` deadline).
Its socket-only exit 4 is preserved if encountered, though this adapter does
not select a socket. Adapter deadline exit is 124; graceful interruption is
130. The adapter starts one CLI invocation with no replay and sets Vibe's
retry elapsed budget to zero on 2.26.1; this does not prove every SDK internal
retry is disabled. Owned process groups are cleaned up on deadline/output
overflow.

The initial GLM trial stopped at a local 200k cumulative cap; Medium 3.5 stopped at
600k after producing partial code. These are not subscription-limit observations or
a fair reasoning comparison. Preserve them, use larger task-sized bounds for new
authorized work, and judge models by accepted real task outcomes. A catalog entry
for a newer Mistral model does not establish this account's access or its quality.

## Live progress during a run

On 2.26.1 the provider invocation uses the installed CLI's documented
`--output streaming` route: one newline-delimited JSON record per completed
session history entry (installed 2.26.1 schema, camelCase fields; entries have
`type` message, reasoning, effect, callback, checkpoint or notice, and effects
carry `detail.kind` with a settled `state.status`). On 3.1.1 the headless run
uses `--output json` (a single message list printed at the end), so no
per-record events exist and the adapter prints only the liveness heartbeat
during the run. Every raw byte still lands in the bounded private
native-stdout log on both versions. The adapter's own stdout prints only fixed
allowlisted operational labels (2.26.1), flushed as each record is recognized:

```text
Vibe progress: assistant response observed
Vibe progress: assistant reasoning observed
Vibe progress: running shell command
Vibe progress: reading file
Vibe progress: editing file
Vibe progress: writing file
Vibe progress: searching files
Vibe progress: updating task list
Vibe progress: tool call observed
Vibe progress: tool failure observed
```

During about 30 seconds with no recognized record, the adapter prints a
liveness-only heartbeat, `Vibe heartbeat: adapter process alive; no new provider
event observed`. It is clearly distinct from an observed provider/tool event and
claims only that the adapter process is alive — never actual reasoning, task
success, readiness, quota or token savings.

Records that are malformed, oversized or of an unmapped shape are counted in the
receipt, never turned into progress. Parsing is incremental and bounded: split
UTF-8 sequences and split records across reads are reassembled, each decoded record is
capped at 262,144 Unicode characters, and a run prints at most 10,000 public lines, so a noisy or
hostile stream can neither grow memory nor spam the log. Overall output bounds and
owned process-group, deadline and cancellation handling are unchanged.

No raw assistant or reasoning text, prompt, tool argument or result, file path,
command string, export, authentication or error text is ever printed publicly.
The receipt and final adapter line add only bounded progress counts and the last
observed label and time; the requested model and requested high effort are explicitly known settings;
effective model/effort and remaining allowance are Unknown, and progress output drives no policy or admission
decision.

Limitations: the stream carries only completed entries, so history entries
may be emitted after an action completes; labels describe observed history, not
certified currently-running tool state. For example, `running shell command`
means such an event was observed in completed history, not that a command is
executing right now. Silence between records is normal while the CLI works; the
heartbeat is the only signal during it. The first slice shows operational
labels only, not message excerpts or a console. This behavior is in the
unreleased 0.5.18 candidate. The stable standalone adapter and public
install remain 0.5.17.

On 2026-10-14, Mistral / Vibe 2.26.1 / requested GLM 5.3 high used frozen
adapter `4dd45a0e4d50190b15332b04c772afa12af7c4febb186d8b2f8e6f32cef2a85b`
on ANTIGRAVITY-OUTCOME-GLM-HIGH-1. The first safe event was at 12:09:17
+02:00 while the adapter was alive. The first liveness heartbeat was at
12:12:18 +02:00. Source exit was 0 and the export finished. The lead
accepted only the later checked correction. Effective model, effort and
remaining allowance stay Unknown. The earlier native exit 3 at the local
4M cumulative cap remains preserved and does not show subscription allowance.

## Test evidence and unresolved live behavior

Offline evidence (no live provider call was made for this change): the 2.26.1
fixture suite (22 tests) is unchanged and green, and new 3.1.1 fixture tests
(12 tests) cover explicit `--model` selection, absence of `VIBE_*` overlays,
`--output json` final-reply provenance, verified/mismatch/unknown selection
from export metadata, cap omission with observed native limits, native
limit/deadline exits and stop reasons, missing/malformed exports, unpriced
USD staying Unknown, version/model gating before any provider call, and
contract parity. The route-contract, adapter-budget, adapter-outcome and
adapter-install suites are green with the regenerated embedded payload.

Unresolved live behavior: no live 3.1.1 provider trial was run from this task;
the lead assigns one separately after review. The real 3.1.1 end-to-end
selection (server-side effective model/effort, actual allowance, and the exact
catalog resolution of each alias on a given account) therefore remains
Unknown and is only verifiable by that assigned trial. The indicative $10
price cap is not billing proof; subscription allowance is never measured.

## References

Real corrected-wrapper trial, 2026-10-09: GLM 5.3 saved the first adapter-packaging
commit, then its native session ended with `infrastructure_failure`/connection
failure and exit 2 after 1,791,060 cumulative tokens, estimated $2.571018.
The local 2M/$5 bounds were not reached. This verifies an actual invocation and
truthful failure export, not completion or remaining subscription capacity.
Opus subsequently completed the saved work through a separately authorized task;
four native checks and personal lead review passed.

- [Mistral subscription billing and usage](https://docs.mistral.ai/admin/billing-usage/subscriptions).
- [Mistral model pricing](https://docs.mistral.ai/inference/pricing).
- [Mistral reasoning controls](https://docs.mistral.ai/studio/conversations/reasoning).
- [Official Vibe source](https://github.com/mistralai/mistral-vibe), matched to installed 2.26.1 and 3.1.1.
