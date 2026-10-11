# Independent review receipts: first implementation slice

Frozen 2026-10-11 after explicit dispatch integration. Development source,
not part of published/installed v0.5.9. This slice preserves each existing
single review and adds a read-only summary. Parallel reviewer orchestration
is a later slice; no new provider call, retry or acceptance is authorized by
reading a summary. Preserve the current structured result schema and review
admission, verdict parsing, gates, locks and exit behavior.

## CLI

Keep `unio review <worker> <task> [agent]`. Add:

```text
unio reviews <worker> <task> [--expect agent[,agent...]] [--json]
```

Help must work outside a project. Reject malformed/duplicate options and
expected-agent labels before reading project state. Expected aliases are
explicit caller requirements, not discovered availability or AI-lab identity.
Deduplicate exact aliases; cap expected reviewers at 16. Never sign in, probe
quota, execute Validate commands or call a configured agent from `reviews`.

## Preserve each completed review attempt

The native review already creates `coord/reports/<task>.review.XXXXXXXX/` with
separate `stdout.log` and `stderr.log`. Add a new `receipt.json` there, never
overwrite a previous receipt or infer bindings for old raw log folders. Record
the original common task/diff material hash before reviewer invocation; policy
headers may differ per account and are not evidence of different code material.

Receipt schema 1 has exactly these fields:

| Field | Value |
| --- | --- |
| `schema_version` | integer 1 |
| `id` | new 32-character lowercase hex identifier |
| `worker`, `task`, `reviewer` | actual native identifiers |
| `recorded_at` | ISO timestamp with timezone |
| `policy_group` | actual admitted/attempted budget label, or null if unavailable |
| `requested_model`, `effective_model`, `requested_effort`, `effective_effort` | `"unknown"`; do not infer them from an alias, command string or model output |
| `state` | `approved`, `changes_requested`, `unknown` or `failed` |
| `process_exit_code` | actual nonnegative exit or null when no reviewer was invoked |
| `material_complete` | boolean, true only when complete common material was supplied to an invoked reviewer |
| `reasons` | at most 16 bounded diagnostic labels |
| `before`, `after` | exact native revision dictionaries; `after` may be null if observation failed |
| `material_sha256` | hash of the original common review material |
| `stdout`, `stderr` | each exactly `{ "sha256": HASH, "bytes": NONNEGATIVE_INTEGER }` for the preserved corresponding log |

Revision dictionaries retain the existing four fields: `candidate_commit`,
`base_commit`, `task_sha256`, `worktree_sha256`. Respect their actual Git/hash
lengths and native validation. Capture `before` and material before provider
execution, then `after`. Preserve the actual process code and verdict even
when a later revision check makes the receipt stale. A printed approval with
nonzero process exit never qualifies as approval.

Record budget refusal after material preparation as `unknown`, null process
exit, `material_complete=false`, reason `budget_refused` and empty raw streams;
do not call the provider. Pre-material refusals retain existing behavior and
need no synthetic receipt. A failed final snapshot must preserve raw logs and
an uncertain receipt with `after=null`, rather than silently discarding evidence.
An interrupted attempt can remain without a receipt; readers report that
folder as unbound/incomplete instead of claiming the review completed.

Write receipts privately with exclusive atomic publication and fsync before
success. Reuse standard-library utilities and existing quality/review helpers;
no separate store, migration, model metadata scraping or command execution.
If new receipt publication fails, preserve raw evidence and return nonzero;
an otherwise successful review must not appear to have saved a receipt.
Do not change `unio result`/browser readiness or claim a summary is acceptance.

## Read and combine evidence

Reuse the current native quality snapshot and common-material construction.
A summary must match the exact current four-field revision, current material
hash, receipt identity and raw-log hashes/lengths. Reobserve the revision after
reading; drift or a held worker lock makes current evidence Unknown. Inspect
locks read-only: never create coordination files or directories to summarize.
The command works while STOP is set and makes no coordination writes.

Inspect at most 256 matching review folders. Read receipt JSON at most 64 KiB
with strict UTF-8, duplicate-key/nonfinite/type/unknown-field rejection. Refuse
symlinks, special files and unsafe path components; hash logs in bounded chunks,
with a 16 MiB per-log ceiling. Unsupported, missing, oversized or corrupt
evidence remains visible as incomplete/unresolved. Never include raw stdout,
stderr, task text, private commands or credentials in summary output.

Report every matching receipt separately, including old/stale/unknown/failed
entries and unbound historical raw folders. Old valid receipts bound to another
worker are excluded from that worker's summary. Never use old unbound logs as
current review evidence. Duplicate calls to one reviewer do not become two
independent reviewers; show distinct agent aliases and shared groups honestly.
AI-lab/model independence remains Unknown without trustworthy route evidence.

Current `changes_requested` wins the summary decision even alongside failed or
missing reviewers; keep `incomplete=true` as appropriate. Any other current
unknown/failed/unreadable evidence, missing expected alias, held lock or drift
makes the decision `incomplete`. With no current evidence use `not_run`. Only
when all current recorded reviews approve, with no unresolved evidence or
missing expected alias, use `all_recorded_approved`. Historical stale records
stay visible without invalidating a complete new current set; unbound records
cannot establish such a set and remain explicitly unresolved. Preserve all
current requested changes even if a second call by that reviewer approves.

JSON output uses schema 1 with worker/task, current revision/material hash,
decision, incomplete flag, expected/missing/distinct reviewer lists, counts and
bounded per-entry evidence/reasons. Its acceptance claim is always
`human_acceptance=false`. Text shows the same facts clearly. Exit 0 only for
`all_recorded_approved`, 1 for current `changes_requested`, 2 for other states
or malformed/unsupported input. This is a summary of recorded reviews, never
a majority vote, retry grant, human approval or integration decision.

## Focused acceptance

Use a copied standalone installer in isolated paths with spaces, real tiny Git
workspaces and mock agents only. Cover two preserved approvals and an expected
missing third alias; request-changes plus approval/failure; duplicate reviewer
calls; native nonzero/timeout without losing raw logs; task/code/base drift;
tampered/missing/oversized/symlink/duplicate-key receipts or streams; budget
refusal without provider call; busy worker; unbound historical folder; read-only
operation and STOP; installed help/completion. Existing single-review contract
fixtures must still pass. No live reviewer run or full release gate is needed
for this source slice; publication remains a separate versioned gate.
