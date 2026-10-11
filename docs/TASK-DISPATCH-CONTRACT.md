# Explicit dispatch: implementation contract

Status: planned source work, not part of installed v0.5.9. This bounded slice
connects the checked task planner to the existing execution service. It does
not introduce a scheduler, automatic approvals, retries or a new job store.

The owner supplies a physical UTF-8 JSON grant (schema 1), with exactly these
fields: `schema_version`, `project`, `engine`, `config_dir`, `template_path`,
`worker`, `reviewer`, `worker_lab`, `reviewer_lab`. Paths are absolute physical
paths; `engine` must equal the actual invoked Unio executable. The two lab
labels must differ. This grant is trusted host authority, never task prose or
model output. Bound it to 16 KiB, reject duplicate/unknown fields and symlinks,
and validate arguments before constructing the writing execution service.

The proposed CLI uses global `--grant PATH`, optional `--project PATH` (which
must equal the granted project), and `--json`, followed by one operation:

```text
prepare --draft-id ID --draft-sha256 HASH --request-key KEY
approve --job-id ID --draft-sha256 HASH --preview-sha256 HASH --approval-key KEY
start --job-id ID --approval-key KEY --reservation-key KEY --inventory PATH --inventory-sha256 HASH [--timeout SECONDS]
```

IDs and keys use the execution service's existing 32-character lowercase hex
format; hashes use SHA-256. The owner supplies the exact keys. Each operation
delegates to the existing `ExecutionService.prepare`, `approve` or `start`.
Prepare and approve make no provider call. Start is a single explicit attempt;
replay returns existing evidence, never another launch. Unknown outcomes remain
unknown. Launcher acceptance is not task success, review or integration.

The narrow shared-service extension is an optional keyword-only
`preflight=None` on `ExecutionService.start`. For a fresh start, validate the
callable and invoke `preflight(binding)` inside the existing cross-process
coordination lock, after binding/worker checks but before reservation, action
publication or native task publication. Existing HTTP callers keep their
three-argument behavior. Replayed starts must not rerun preflight or launch.

The CLI's callback rereads the bounded inventory, verifies its exact supplied
hash, validates schema 1 with the existing task-plan helper, and freshly builds
the plan with the granted runner/configuration and a 1–60 second observation
deadline (default 10). The selected row must uniquely bind the job ID,
`ui-<job-id>` task ID, worker, compiled-task hash and binding/base revision,
and be `ready`. Blocked, unresolved, changed or unsupported input refuses
before reservation. Native admission remains the final account/worker guard;
the planner does not claim provider quota or unmanaged-session ownership.

To support this without premature publication, the read-only planner may use
the existing `coord/ui-execution/bindings/<job-id>.md` when the corresponding
native task is absent. Only a matching inventory job/task/worker/base/hash and
consistent existing binding, preview companions, queue and draft qualify.
An existing native task takes precedence: never fall back around a bad file.
Reuse scope parsing and all existing bounds and physical-file rules. Do not
construct stores, create files, execute Validate lines or change queue state.

Package the new helper with a byte-identical marked installer block and safe
destination preflight. Keep source and installed layouts supported; help works
outside a project. Public output is bounded and excludes raw task requests,
commands, approval/reservation keys and credential material.

Acceptance uses focused offline fixtures with the real stores/service and a
mock native launcher: prepare/approve, fresh ready start, exact replay once,
STOP, stale/hash-mismatched/dependency/group/scope refusals, tampered materials,
unknown outcomes, and copied standalone installation. No provider calls or
full release gate are needed to evaluate this source slice. Release checks
remain separate. No dashboard or website presentation changes belong here.
