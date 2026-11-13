# Review report links (observational)

First slice of the 0.5.30 review-report contract. See
docs/development/contracts/0530-REVIEW-REPORTS.md for the authoritative
behavioral contract; this guide explains how to use the commands.

A separately assigned report-only reviewer produces a report against an
exact, frozen packet of target material. The commands below make that
report discoverable against its target task without changing any native
decision: attaching a report review has no approval, readiness or
human-acceptance effect, and the default `unio reviews`, `unio reviews
--findings` and `unio result` outputs stay byte-identical.

## When to use this

- A reviewer runs on a different worker/task as a report-only Source
  (its task declares `## Outcome` with `report-only`).
- You want the review's semantic verdict and typed findings visible
  against the target task, as an observation, never as acceptance.

## The three commands

### 1. Prepare a packet

```text
unio review-packet <worker> <task> [--path PATH]...
```

Prepares bounded local material with no provider call. Requires a current
verify PASS and clean, committed, text-only material (the same limits as
native review material: 300000 bytes, UTF-8, no binary diffs). Prints JSON
with a 32-hex packet id, the manifest SHA-256 and the exact declaration to
paste into the reviewer task. The declaration is a `## Review packet`
section containing one fenced `json` block whose single line is:

`{"id":"<32hex>","manifest_sha256":"<64hex>","schema_version":1}`

Without `--path`, coverage is `task_material` (the whole native protocol-2
review material). With explicit `--path` arguments, coverage is `paths`:
each path must be a safe relative path inside the target worktree (no
globs, no `..`, no symlinks, bounded UTF-8 text file). Coverage labels
describe the supplied material, never whole-app approval.

The packet is stored privately under `coord/review-packets/<id>/` and must
be created BEFORE the reviewer Source is dispatched.

### 2. Write the reviewer task

The reviewer task must contain exactly one active `## Review packet`
section with exactly one fenced JSON object (the declaration above). It
must also declare the required artifacts:

```text
## Required artifacts
summary.md
verdict.json
findings.json
```

`verdict.json` must be exactly
`{"schema_version":1,"verdict":"APPROVE"}` or
`{"schema_version":1,"verdict":"REQUEST-CHANGES"}`. `findings.json` uses
the typed `unio-findings-v1` findings schema (a JSON object
`{"schema_version":1,"findings":[...]}` with severity, path, line, summary
and detail fields; see docs/REVIEW-FINDINGS.md). Run and verify the
reviewer task normally.

### 3. Attach and view

```text
unio reviews-bind <target-worker> <target-task> <source-worker> <source-task>
unio reviews <target-worker> <target-task> --reports [--json]
```

Binding verifies, with the existing native validators, that the source is
a current successful report-only Source with a complete immutable
delivery, that its native-frozen predispatch prompt (not the current
prose) carries the declaration, and that packet bytes, target revision and
target material still match exactly. The declaration is read from the
frozen predispatch evidence; a declaration added or changed after
dispatch refuses. A drifted target (new commits since the packet) refuses:
create a new packet instead of attaching stale material.

Binding is idempotent: attaching the same target, packet and source
evidence again is a no-op replay. Replays never overwrite evidence, and a
corrupt receipt history refuses rather than re-binds.

The `--reports` view is separate from the default review views. It lists
each attached report review with its semantic verdict, findings count,
coverage and current/stale state, and always states that human acceptance
is not granted and the native readiness effect is none. `--reports`
cannot be combined with `--findings` or `--expect`. Exit 0 means every
attached review is currently valid; exit 1 means at least one is stale or
invalid; exit 2 is a hard refusal.

## What stays unchanged

- Native review receipts (`coord/reports/<task>.review.XXXXXXXX/`), the
  default `reviews`/`--findings` projections and `review_current` are
  untouched. Report reviews live in a separate
  `<task>.report-review.<id>` namespace that pre-0.5.30 readers ignore.
- Result readiness, owner acceptance, gates and account slots are
  untouched. A REQUEST-CHANGES report stays visible next to a later
  APPROVE; scoped reports never aggregate into approval.
- Reading a source requires its per-run route context to remain valid
  (the source worker's agents.conf command must still match its frozen
  dispatch evidence); identity checks are never weakened to force a bind.
- Model identity stays Unknown: supplied material is not proof of model
  attention or effective identity, and nothing here is remote attestation.

## STOP and busy states

Read-only `--reports` views work during STOP. `review-packet` and
`reviews-bind` refuse while STOP is active or while the target/source
worker holds a live lock, before any work or publication.
