# Read independent review results

`unio reviews` combines recorded reviews of the exact current work. It shows
who reviewed it, which verdicts disagree and what evidence is still missing.
You remain responsible for accepting and merging the work.

**Availability:** development source; not included in published/installed
v0.5.9. This first slice preserves receipts and reads them. Parallel review
launches are a separate milestone.

## Run reviews, then read their evidence

The existing `unio review` command invokes one reviewer. These two calls each
use an agent's allowance; run them only when authorized and the agents are
available. Replace the illustrative worker, task and reviewer aliases:

```bash
unio review "worker-a" "task-a" "codex"
unio review "worker-a" "task-a" "claude"
```

Read the combined results locally:

```bash
unio reviews "worker-a" "task-a" --expect "codex,claude"
unio reviews "worker-a" "task-a" --expect "codex,claude,gemini" --json
```

`--expect` declares which reviewer aliases you require. The second example
reports Gemini as missing until its current review exists. It does not launch
Gemini, discover its availability or grant permission for another call.

Reading a summary makes no provider call, changes no coordination state and
works while STOP is set. It does not retry, merge or accept work. It preserves
the existing `unio result` behavior.

## What the receipts establish

Each completed native review attempt saves a new `receipt.json` beside its
separate `stdout.log` and `stderr.log` under
`coord/reports/<task>.review.*/`. The receipt records the exact before/after
revision, common task/diff material hash and hashes and lengths of both logs.
The summary checks those bindings against the current work.

Stale, tampered, unsupported or unbound evidence stays visible. Historical
raw logs without a receipt cannot establish a current review. Missing expected
reviewers remain missing. A later approval does not hide an earlier request
for changes on the same revision.

Repeated calls to one alias do not become different reviewers. Shared budget
labels are reported separately; aliases alone do not establish that reviewers
come from different AI labs. Requested/effective model and effort remain
Unknown when trustworthy evidence is unavailable.

## Read the decision

| Decision | Meaning | Exit |
| --- | --- | --- |
| `all_recorded_approved` | Every current recorded review approves, with no unresolved evidence or missing expected alias | 0 |
| `changes_requested` | At least one current review requests changes; failures or missing evidence can also set `incomplete=true` | 1 |
| `incomplete` | Evidence is missing, unknown, failed, unreadable or cannot be established while the worker is busy | 2 |
| `not_run` | No current review evidence | 2 |

Invalid or unsupported input also exits 2. JSON always reports
`human_acceptance=false`: approval by recorded agents is evidence for your
decision, not human acceptance. Summary output excludes raw review prose,
task requests and private commands; inspect local raw files deliberately when
you need the findings.

See the [frozen receipt contract](REVIEW-RECEIPTS-CONTRACT.md) for bounds and
exact evidence rules.
