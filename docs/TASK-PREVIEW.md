# Task scope preview

First slice of the 0.5.31 task-preview contract. See
docs/development/contracts/0531-TASK-PREVIEW.md for the authoritative
behavioral contract; this guide explains how to use the command.

`unio verify WORKER TASK --preview [--json]` shows the current
implementation-task scope before any Source exists. Use it to catch
inherited committed, staged, unstaged or untracked paths that would
surprise a later model call. It is an observation: Validate commands
are not run, provider calls are 0, and admission, delivery and
acceptance are not established. It never emits a verify PASS and never
claims a future dispatch is safe.

Unflagged `unio verify` is unchanged. It still runs Validate commands,
appends a verify block and records validation. `--preview` is entirely
opt-in so ordinary runs gain no extra startup I/O.

## Command

```text
unio verify <worker> <task> --preview [--json]
```

Flags may appear before or after the worker and task names. `--json`
without `--preview` is still ignored by unflagged verify, which runs
Validate. Shell completion therefore offers `--json` only after
`--preview` is already present.

## What it shows

- Current base ref and commit, HEAD, task hash and worktree hash
- Declared outcome mode (`legacy`, `implementation` or `report-only`)
- Classified changed paths: committed, staged, unstaged, untracked
- Canonical allowed-scope patterns and annotation warnings
- Out-of-scope paths (native `scope_allowed`, including implicit
  `changelog.d/`)
- Declared `$ ` Validate commands (listed, never executed)
- Required artifact names when the task declares them
- Whether project STOP is active (preview stays read-only)

Human and JSON views carry the same facts. JSON uses
`schema_version` 1 and discriminator `kind: "task-preview"`.

## Exits

| Exit | Meaning |
| --- | --- |
| 0 | Implementation (or legacy) paths currently in declared scope |
| 1 | Scope mismatch: at least one current path is out of scope |
| 2 | Missing scope or Validate, invalid required-artifact syntax, report-only unsupported, busy worker, invalid/unknown worker or task ID, change during observation (including after Python facts, while canonical task-section parsing still runs), or unsupported/unknown Git state |

Zero current changes is a valid observation (exit 0 when scope and
Validate are present). It is not accepted or no-op delivery.

Report-only tasks return exit 2 with `scope_status` `unsupported` and
reason `report_only_not_predicted`. Source freshness is not predicted
in this first slice.

## Coordination

Preview takes the existing nonblocking participating worker lock so a
native Source cannot race the observation. A busy worker is refused
(exit 2). Invalid worker or task IDs are unknown on this path (exit 2)
and take no lock, run no Validate and call no provider. Unflagged
`unio verify` still refuses those IDs with `check_id`/`die` (exit 1).
Lock metadata is the only coordination bookkeeping: no receipts,
results, ledger, saves or task edits. STOP remains read-only.
Unsupported Git or file states fail closed through the existing
snapshot/changed helpers. A conservative snapshot after canonical
task-section parsing binds the whole observation: if the task or Git
state moved, preview returns `scope_status` `changed` (exit 2) and
never claims `in_scope` with a mixed task hash and scope list.

## What it does not do

- Run Validate commands or create/update validation results
- Call a provider
- Establish admission, delivery or acceptance
- Claim that a later `unio run` or `unio verify` will pass
- Change unflagged verify, Source, review, result or save semantics
