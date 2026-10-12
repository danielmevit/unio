# Review the same work in parallel

`unio review-set` asks an explicit set of agents to review the same committed
work at once. It keeps separate evidence for each reviewer and combines their
recorded verdicts. You decide whether to accept and merge the work.

**Availability:** released in Unio v0.5.11 and available in later releases.
Check `unio version` before using it; v0.5.9 does not include these commands.
See the [collection contract](REVIEW-COLLECTION-CONTRACT.md).

## Start a collection

Replace these illustrative names with your worker, task and configured,
available reviewer aliases:

```bash
unio review-set "worker-a" "task-a" "reviewer-a" "reviewer-b"
```

This makes real reviewer calls and uses their allowances. Supply 2–8 distinct
aliases, each different from the author alias. The task needs current verify
PASS and clean, committed, complete UTF-8 text material within the existing
300000-byte limit. Every alias is checked before calls begin.

Separate account groups can work concurrently. Shared budgets still apply,
including the lead reservation in low tier. A full group is refused without a
call; other admitted reviewers can finish. The missing attempt stays incomplete.
There is no queue, retry, replacement reviewer or quota/sign-in probe.

STOP prevents new collections and is rechecked before each provider starts.
Already running calls follow the normal timeout and interruption behavior.

## Read the combined evidence

The command prints its collection ID and an ordinary summary. Read the current
evidence again without calling any agent:

```bash
unio reviews "worker-a" "task-a" --expect "reviewer-a,reviewer-b"
unio reviews "worker-a" "task-a" --expect "reviewer-a,reviewer-b" --json
```

Each attempt has its own receipt and raw streams. The collection descriptor
records the requested aliases and lifecycle; `completed` means the children
returned. Approval, acceptance and integration are separate decisions.

Missing, failed, stale and interrupted evidence remains visible. A new approval
cannot erase an earlier request for changes on the same revision. Summaries
exclude raw reviewer prose; inspect the local raw files when you need findings.
The existing latest-single-review result remains separate from a collection.

| Exit | Meaning |
| --- | --- |
| 0 | Complete unchanged collection, with all recorded current reviews approved |
| 1 | Current evidence requests changes; other evidence may also be incomplete |
| 2 | Other incomplete/unknown outcomes or invalid input |

An interrupted collection returns its signal exit. JSON summaries always report
`human_acceptance=false`.

## Choose independent reviewers deliberately

Different aliases and account groups do not by themselves establish different
AI labs. Requested/effective models and effort remain Unknown when trustworthy
metadata is unavailable. Choose known suitable routes rather than treating an
alias count as proof of independence.

See [review receipts](REVIEW-RECEIPTS.md) for exact revision/material bindings
and the local summary's evidence rules.
