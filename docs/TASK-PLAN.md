# Explain concurrent task recommendations before dispatch

The source candidate adds `unio plan` for the follow-up; it is not in
the published 0.5.9 installation. It explains concurrent recommendations before
dispatch without running executors, provider calls, verification commands,
creating queues or databases, or mutating state.

```bash
unio plan --inventory /path/to/inventory.json
unio plan --inventory /path/to/inventory.json --json
unio plan --inventory /path/to/inventory.json --project "/work/my project" --timeout 15
```

Run it from inside a Unio workspace, or select the project workspace containing
`coord/` and `wt/` with `--project`. `--help` works outside projects. The default
whole-observation timeout is 10 seconds (range 1–60).

## Inventory Schema (schema_version 1)

The inventory is a strict UTF-8 JSON input document (<=256 KiB) passed via `--inventory`.
Unio never writes or mutates this file. Duplicate keys, non-finite numbers (NaN/Infinity),
boolean-as-integer, and unknown fields are strictly rejected.

```json
{
  "schema_version": 1,
  "base_revision": "71485fa3181091ab4f675188ee7d13f3c45ccfc5",
  "tasks": [
    {
      "id": "TASK-1",
      "task_sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      "worker": "grok",
      "depends_on": [
        {
          "id": "TASK-0",
          "task_sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
          "revision": "71485fa3181091ab4f675188ee7d13f3c45ccfc5"
        }
      ]
    }
  ],
  "accepted": [
    {
      "id": "TASK-0",
      "task_sha256": "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb",
      "revision": "71485fa3181091ab4f675188ee7d13f3c45ccfc5"
    }
  ]
}
```

### Required Fields

- `schema_version`: Must be integer `1`.
- `base_revision`: Full 40-character hex Git commit hash representing the expected repository HEAD.
- `tasks`: List of up to 128 task entries. Each entry requires:
  - `id`: Native task ID (matching `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`).
  - `task_sha256`: 64-hex SHA-256 of the native task markdown file (`coord/tasks/<id>.md`).
  - `worker`: Native worker identifier.
  - `depends_on`: List of up to 128 dependencies (`id`, `task_sha256`, `revision`).
  - `job_id`: Optional 32-hex ID referencing an existing browser queue job in `coord/ui-jobs.sqlite3`.
- `accepted`: List of up to 128 owner/lead accepted records (`id`, `task_sha256`, `revision`).

## How Accepted Records Bind Revisions

A dependency is satisfied only when backed by an explicit record in `accepted`.
- Source exit of zero, PASS verdicts, or `ready_for_human_review` do not satisfy a dependency.
- The accepted `revision` must exist in Git and be an ancestor of `base_revision`.
- Both required `task_sha256` and required `revision` must exactly match the accepted record.
- If an accepted record has a mismatched revision or hash, the dependent task is blocked with the exact mismatch reason.
- If acceptance evidence is missing, the dependent task is unresolved.
- A task whose exact hash is already accepted at base is blocked as `already_integrated` and never rerun.

## Scope Conflicts and Disjointness

Write scopes are parsed solely from the single `## Allowed scope` section in `coord/tasks/<id>.md`.
- Supported scopes: literal relative paths, directory prefixes with trailing `/`, terminal `/**`, and whole-root `**`.
- Backslashes, control characters, absolute paths, traversals (`..`), and unsupported globs are rejected as ambiguous/unresolved.
- Exact and parent/child paths conflict conservatively.
- Whole-root `**` conflicts with all scopes.
- If an unfinished task has unknown or ambiguous scope, disjointness cannot be established; other pending tasks are conservatively marked unresolved.

## Fleet and Greedy Selection

1. The workspace repository HEAD is checked against `base_revision`. If HEAD has changed, all rows become unresolved.
2. If project `coord/STOP` is set, all tasks are blocked (`project_STOP`).
3. Fleet occupied slots and active lead reservations are respected.
4. If an assigned group is busy and inventory lists its unfinished task, that task's scope is conservatively treated as occupied.
5. Eligible candidate tasks are selected greedily in task ID order, consuming virtual group slots and scopes.
6. Later candidates sharing a full budget group or intersecting occupied scopes are blocked with conflict reasons.

## Point-in-Time Recommendation Only

A status of `ready` indicates a local recommendation under observed conditions.
It is not launch authority, an approval, or a guarantee of provider availability.
Live provider readiness and admission must always be rechecked at dispatch.
Exit 0 indicates a valid plan (with any task statuses); exit 2 indicates invalid input, arguments, or an unsupported project.
