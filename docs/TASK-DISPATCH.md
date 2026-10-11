# Dispatch one approved task

`unio dispatch` prepares a saved request, records your approval and starts one
exact task after fresh local checks. You choose each step explicitly.

**Availability:** implemented in development source; not included in published
v0.5.9. Use an isolated installation from the matching source revision. The
command reuses Unio's existing execution service and approval stores.

## Choose the project and agents

Create a UTF-8 JSON grant containing exactly these fields. Replace the example
paths and labels with your actual physical paths and configured workers:

```json
{
  "schema_version": 1,
  "project": "/srv/project",
  "engine": "/opt/unio/bin/unio",
  "config_dir": "/srv/unio-config",
  "template_path": "/srv/unio-config/task-template.json",
  "worker": "grok-feature",
  "reviewer": "claude",
  "worker_lab": "xAI",
  "reviewer_lab": "Anthropic"
}
```

`project` is the enclosing directory containing `repo/`, `coord/` and `wt/`.
`engine` must name the exact Unio executable you invoke, and `config_dir` must
match its `UNIO_CONF_DIR`. The existing JSON task template supplies instructions,
allowed paths and validation commands. Use accurate, different AI-lab labels;
the grant does not independently verify a route's identity.

The grant is trusted host authority, separate from task text or model output.
It is limited to 16 KiB. Duplicate or unknown fields, incorrect types and
symlinks are refused. Its paths must be absolute physical paths. Agent commands
retain the existing trusted-host execution boundary.

## Prepare, inspect and approve

Start with a saved browser draft and its actual ID and SHA-256. There is no new
draft-creation CLI. Set `GRANT` to your grant file and supply the existing draft
values and an explicit owner-chosen request key:

```bash
unio dispatch --grant "$GRANT" --json prepare \
  --draft-id "$DRAFT_ID" --draft-sha256 "$DRAFT_SHA256" \
  --request-key "$REQUEST_KEY"
```

IDs and keys are 32 lowercase hexadecimal characters; SHA-256 values are 64.
Keep your keys and responses. Prepare returns `job.id`, `task.id`, `task.sha256`
and `preview_sha256`; it makes no provider call.

Inspect `coord/ui-execution/bindings/<job-id>.md` and the returned preview.
Confirm the request, worker, allowed paths and validation commands. Then
explicitly approve the same draft and preview:

```bash
unio dispatch --grant "$GRANT" --json approve \
  --job-id "$JOB_ID" --draft-sha256 "$DRAFT_SHA256" \
  --preview-sha256 "$PREVIEW_SHA256" --approval-key "$APPROVAL_KEY"
```

Approval also makes no provider call. The native task file remains unpublished
until start. Global options such as `--grant`, `--project` and `--json` precede
the operation. Optional `--project` must identify the granted project.

## Check the inventory and start

Create a [task inventory](TASK-PLAN.md) naming the approved job and its compiled
task hash. Replace every illustrative value below with the exact observed one:

```json
{
  "schema_version": 1,
  "base_revision": "0123456789abcdef0123456789abcdef01234567",
  "accepted": [],
  "tasks": [{
    "id": "ui-JOB_ID",
    "job_id": "JOB_ID",
    "task_sha256": "COMPILED_TASK_SHA256",
    "worker": "grok-feature",
    "depends_on": []
  }]
}
```

`base_revision` is the full current base commit. `ui-JOB_ID` must contain that
job's actual ID; `task_sha256` is the compiled task hash, not the draft hash.
List other relevant work too. Dependencies require explicit accepted revision
evidence; a successful run alone does not establish integration.

Inspect the read-only recommendation, hash the exact inventory bytes and
explicitly request one launch:

```bash
unio plan --project "$PROJECT" --inventory "$INVENTORY"
INVENTORY_SHA256=$(sha256sum -- "$INVENTORY" | cut -d ' ' -f 1)
unio dispatch --grant "$GRANT" --json start \
  --job-id "$JOB_ID" --approval-key "$APPROVAL_KEY" \
  --reservation-key "$RESERVATION_KEY" --inventory "$INVENTORY" \
  --inventory-sha256 "$INVENTORY_SHA256" --timeout 10
```

Start rereads the inventory and checks its hash, exact job/task/worker/base
binding and a fresh `ready` recommendation under the shared execution lock.
STOP, unmet dependencies, conflicting scopes, full account groups and stale or
unsupported evidence refuse before reservation and native task publication.
Listed reserved or uncertain jobs retain conflicting scopes even before their
detached worker acquires a native slot. The supplied inventory cannot establish
the scope of every omitted or unmanaged session. Unknown allowance remains
unknown; native admission still checks the actual worker/account slot.

## Read the outcome

Launcher acceptance means the background launch was accepted. Worker success,
checks, review and integration are separate evidence. This command provides
no scheduler, automatic approval, retry, review or merge.

A repeated start with the same keys returns existing evidence and never launches
again. An uncertain result stays uncertain. Keep the keys, inspect the job and
native reports, and resolve the recorded attempt; changing a reservation key
does not authorize another launch.

JSON and text output expose bounded identifiers, hashes, states and reasons,
without raw requests, validation commands or private keys. Exit codes are `0`
for prepare/approval/launcher acceptance, `1` for refusal or known launch failure,
`2` for invalid arguments or grant, and `3` for an unknown outcome.

See the [implementation contract](TASK-DISPATCH-CONTRACT.md) for exact boundaries.
