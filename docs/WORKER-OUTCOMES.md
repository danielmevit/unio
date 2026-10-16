# Worker stop observations

Native Source reports and `unio status` show `Adapter outcome:` with a fixed
plain label. This is evidence only: Source exits, readiness, schema1 structured
results, work policy, retry brakes, consent and optional WIP retain their rules.
A label never accepts a proposal, changes bench state or authorizes a retry.

Before Source, native creates a fresh private
`coord/reports/.outcomes/<native-attempt-id>/` destination. `binding.json` binds
schema version 1, task and worker, native run ID, original-task and effective
prompt SHA256, exact configured-command SHA256, canonical adapter route and a
`date -Is` start timestamp. The adapter writes one exclusive `outcome.json`
with the same fields plus enumerated label, adapter/native exits and finish
timestamp. Native separately records its real Source exit in `source.json`.
Each JSON is bounded to 8192 bytes, with exact keys and types; duplicate keys,
links, nonregular files, nonprivate evidence, stale or conflicting bindings
produce Unknown. Rejected evidence remains on disk. Status validates the
current native attempt, current task and configured command again, read only.
The status pass is bounded to 1024 tasks/pairs (128 workers per task); excess
evidence is explicitly Unknown rather than scanned without a bound.

Only simple Python argv commands naming the canonical installed adapter path
are supported. Shell wrappers, generic shell routes, unsupported commands,
missing receipts and errors before a bound observation remain Unknown. No
receipt path or free-form error from stdout selects evidence. Standalone
adapters without native binding retain their original contracts and receipts.
The optional agent adapters remain four; the outcome utility is internal.
Same-user trusted_host code can alter local evidence: these unsigned files do
not authenticate the provider or defend against a hostile account owner.

Vibe 2.26.1 labels come only from its validated schema1 export: token, price,
time and turn caps remain distinct; infrastructure failure is Infrastructure
failure; typed configuration/usage errors are Setup failure. Antigravity 1.3.5
labels validated terminal SUCCESS or ERROR (including SUCCESS with an error),
preserving process0/terminalERROR as adapter/Source failure. Missing or invalid
terminal evidence stays Unknown. Neither adapter interprets raw error text as
provider-limit or authentication evidence.

Existing typed adapter-supervisor timeout, output-limit and interruption
observations also have distinct fixed labels, only when a bound run record
exists. Pre-inference errors without that record stay Unknown.

Copilot's existing proposal protocol supports Completed; native failure codes
without a supported reason stay Unknown. Perplexity's existing typed child protocol supports its HTTP429
provider-limit, authentication, dependency/setup, transport, timeout and output
cap states. No new error-message matching is added. Unsupported states stay
Unknown. A provider limit observation establishes neither remaining allowance
nor a reset time/five-hour window. Heartbeats indicate process liveness only.
Raw private adapter receipts and stdout/stderr remain separate and unchanged;
public outcome labels contain no raw errors, account IDs or tokens. Labels
never override the actual native Source or adapter exit, even when they differ.
