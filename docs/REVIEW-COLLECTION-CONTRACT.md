# Concurrent review collection

Frozen 2026-10-11. Development source follow-up to
[review receipts](REVIEW-RECEIPTS-CONTRACT.md), not a published feature.
Collect one explicitly requested reviewer set over the same complete material.
Preserve native account limits and actual failures. Never retry, substitute a
reviewer, queue a call, merge work or grant human acceptance automatically.

## CLI and preflight

```text
unio review-set <worker> <task> <reviewer1> <reviewer2> [reviewer3 ...]
```

Accept 2–8 distinct reviewer aliases; reject duplicates, malformed labels,
options and counts before reading project state. Sole `--help`/`-h` works
outside a project. Add normal help and worker/task/agent completion.

Reuse single-review requirements: configured nonbenched reviewers distinct from
the author alias, current verify PASS, clean committed complete UTF-8 text
material, existing 300000-byte limit and safe native paths. Validate every
alias before any provider call. Refuse STOP before creation/admission and
recheck it for each child immediately before invoking its provider. No quota,
authentication, model availability or network probe is authorized by preflight.

Hold the existing worker lock through collection and final observation. Capture
the common task/diff bytes and their hash once before starting reviewers. Give
each child its own private copy and existing per-account policy header. Different
eligible account groups can overlap; aliases sharing a full budget are refused
without a call. A low-tier lead reservation still consumes its group's slot.
Partial admission is allowed and stays explicit; never wait for a freed slot.

## Existing admission needs separate identities

`policy_admit_hold` writes `<task>.prompt.md` and `<task>.policy.json`. Using the
original task label for concurrent children would overwrite these files.
Give each admission a distinct valid internal label, `rset-<collection-id>-<n>`.
Record that label in its attempt descriptor. Use the actual original worker
and task for receipt revision/material bindings. Internal labels are admission
identities, not invented Source tasks or replacement task files.

Reuse `policy_admit_hold`, `policy_release_slot`, the native process-tree
cleanup, timeout and verdict helpers. Each child owns its policy descriptors,
provider PID and cleanup trap; close inherited worker-lock/admission descriptors
in the provider. Keep the parent's worker lock alive until children finish.
`UNIO_REVIEW_TIMEOUT` applies to each invoked reviewer. No paid fallback, new
account, authentication change, model switch or invented effective effort.

## Receipts and collection descriptor

Before any call, allocate private independent raw folders with the existing
`<task>.review.XXXXXXXX` convention and empty streams. Each completed attempt
uses the existing exact receipt schema, actual admitted group, process exit,
before/after snapshot and original common material/log hashes. Budget refusal
has unknown/null exit/incomplete material. A child interrupted before receipt
publication leaves raw evidence unbound. Never fabricate a verdict from logs
alone or overwrite an existing receipt. Preserve stderr separately.

Create a private `coord/reports/<task>.review-set.XXXXXXXX/collection.json`
before calls. Schema 1 has exactly:

| Field | Meaning |
| --- | --- |
| `schema_version` | integer 1 |
| `id` | new 32-character lowercase hex collection ID |
| `worker`, `task` | original native identifiers |
| `reviewers` | ordered explicit alias list |
| `started_at`, `finished_at` | timezone timestamps; finished is initially null |
| `state` | `running`, `completed`, `interrupted` or `unknown` |
| `before`, `after` | native revision dictionaries; after initially null or unavailable |
| `material_sha256` | original common material hash |
| `attempts` | ordered descriptors, one per requested alias |
| `reasons` | bounded diagnostic labels |

Each attempt has exactly `reviewer`, `policy_task`, `raw_directory` (leaf name,
never an absolute path), and `receipt_id` (null until a valid receipt exists).
Bind final IDs to their exact descriptor/worker/task/reviewer/material before
recording them. Reuse safe atomic JSON writing for owned descriptor updates;
the descriptor is lifecycle evidence, not an acceptance store. `completed`
means children returned, not that they approved. Bound descriptor reads to
64 KiB, use strict duplicate/nonfinite/type checks if reading it, and never
consume arbitrary paths from it. Keep all incomplete state and original logs.

On INT/TERM, stop/reap only owned children through native cleanup and best-effort
record interruption. SIGKILL cannot guarantee finalization. After children
finish, capture a second revision; failed observation or mutation stays Unknown
or stale without changing actual raw process exits/verdicts. Protect independent
common material and check its original hash; a mutated child copy cannot be
reported as an approval of the original input.

## Result and output

Keep `unio review` and its latest-single-review structured result semantics.
The collector does not rewrite that field to an aggregate or last-finisher
verdict. All new receipts remain readable by existing `unio reviews`.

After finalization, release the worker lock before asking the existing read-only
summary for the explicit expected aliases. It rechecks current revision/lock;
intervening work makes evidence incomplete. Include older same-revision requests
for changes; never hide them behind this collection. Print the collection ID
and ordinary combined text summary, excluding raw prose, commands and paths.
Exit 0 only for complete unchanged collection plus `all_recorded_approved`,
1 for current `changes_requested`, and 2 for all other outcomes/invalid input.
Interrupted collection returns its signal exit, never success. Summary still
reports `human_acceptance=false`; alias/account counts never prove AI-lab identity.

## Focused acceptance

Use tiny real-Git projects and isolated installed mock agents. Prove distinct
groups overlap using a barrier, and each receives the correct individual header
and identical core material. Prove shared-group/lead refusal without a call,
STOP preflight, malformed/duplicate aliases and incomplete material before calls,
mixed verdicts/process failures, immutable individual receipts, current historical
requests for changes, unchanged single-review result, mid-review mutation and
parent interruption with owned-child cleanup/slot release. Avoid a timing-only
overlap assertion. No browser changes, live reviewer calls or broad release gate
are required for this bounded source slice.
