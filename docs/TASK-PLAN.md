# Explain concurrent task recommendations before dispatch

`unio plan` explains concurrent task recommendations before dispatch. It is
available in installed Unio and makes no executor or provider calls, runs no
validation commands, creates no queues or databases, and does not mutate state.

```bash
unio plan --inventory "/path/to/inventory.json"
unio plan --inventory "/path/to/inventory.json" --json
unio plan --inventory "/path/to/inventory.json" --project "/work/my project" --timeout 15
```

Run it from inside a Unio workspace, or select the project workspace containing
`coord/` and `wt/` with `--project`. `--help` works outside projects. The default
whole-observation timeout is 10 seconds (range 1–60).
It covers Git queries and local fleet collection together. Unavailable or
timed-out evidence stays unresolved. Git children are bounded and reaped;
the command does not poll a provider or execute task validation commands.

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

The example uses illustrative hashes. From the repository checkout, obtain
the actual base with `git rev-parse HEAD` and a task hash with
`sha256sum "../coord/tasks/TASK-1.md"`. Replace the example values before use.
Keep accepted records under the lead/owner's control: they are explicit
statements of accepted integration, not evidence inferred from worker output.

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

## Existing queue observations

When `job_id` is supplied, the planner validates the existing queue schema,
approval/reservation record and exact immutable draft hash. It uses pure
validators without constructing queue or draft stores. Missing state stays
absent; corrupt or unsupported evidence is unresolved. An approved queue
record makes a task eligible for consideration, and never grants dispatch.

SQLite reads use read-only immutable mode bound to an open file descriptor.
Active journal, WAL or shared-memory sidecars make the observation unresolved.
Inventory, task and draft reads reject special files and symlink components
and enforce byte limits. Queue credentials and raw task text are not displayed.

## Prepared material support

Prepared-material observation is available in installed Unio.

When an inventory task includes `job_id`, the read-only planner supports reading
the existing compiled binding in `coord/ui-execution/bindings/<job-id>.md` and its
split companion files (`<job-id>.json`, `<job-id>.request.json`, `<job-id>.scope.json`,
`<job-id>.validate.json`) when the corresponding native task `coord/tasks/ui-<job-id>.md`
is genuinely absent.

- **Precedence**: An existing native task path (`coord/tasks/<id>.md`) always takes
  precedence. If a native file exists—including symlinks, special files, unreadable
  files, or tampered contents—the planner never falls back to prepared bindings.
- **Strict identity**: Only a task entry with ID `ui-<job-id>` may bind the prepared
  material for that `job_id`. Non-matching task IDs cannot use the compiled binding.
- **Companion and digest validation**: Physical metadata in `<job-id>.json` and bounded
  companions are strictly checked: job ID, draft ID, draft hash, worker, base revision,
  task SHA-256, and canonical preview digest (`preview_hash`). Reconstructed task
  markdown prefix, suffix, scope, validate commands, and instructions are validated.
- **Stale base refusal**: A prepared binding bound to a base revision different from
  the inventory's `base_revision` is marked `unresolved` (`prepared_base_mismatch`).
- **Tamper refusal**: Any altered companion or hash discrepancy marks the row `unresolved`
  (`altered_companion` or `task_hash_mismatch`).
- **Existing queue and draft evidence**: The existing read-only SQLite queue observer
  (`coord/ui-jobs.sqlite3`) and draft store (`coord/ui-plans/`) must report an `approved`
  job record consistent with the binding's inputs (`draft_id`, `draft_sha256`, `request_key`).
  Jobs in `awaiting_owner_approval` or `cancelled` states remain blocked.
- **Read-only integrity**: The planner never constructs `ExecutionService`, `JobStore`,
  or `PlanStore`, never issues approvals or launches, and makes zero file modifications
  or provider calls.
