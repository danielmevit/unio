# Continuous delegation

`unio schedule` runs a finite, explicitly approved batch of existing browser
jobs through the existing planner and `dispatch start` helper. It never prepares
or approves jobs, supplies shared-lead consent, retries, verifies, accepts or
merges work. Launcher acceptance, actual Source completion and owner acceptance
are separate phases. Unknown provider allowance remains Unknown.

## Commands

```bash
unio schedule --help
unio schedule create --grant /physical/path/batch-grant.json --json
unio schedule run BATCH_ID --project /physical/workspace --once --json
unio schedule run BATCH_ID --project /physical/workspace
unio schedule status --project /physical/workspace --json
unio schedule status BATCH_ID --project /physical/workspace --json
unio schedule pause BATCH_ID --project /physical/workspace
unio schedule resume BATCH_ID --project /physical/workspace
unio schedule stop BATCH_ID --project /physical/workspace
```

Replace `BATCH_ID` with the unpredictable 32-hex ID returned by `create`.
Options `--project` and `--json` work before or after the operation. Inside an
initialized workspace the installed command can discover the project; `create`
can use the project in its grant. Help works offline without a project.

`run --once` makes one bounded scheduling pass. Ordinary `run` polls in the
foreground, for at most the grant's `run_seconds` and expiry. The owner can use
their own shell to background this foreground loop:

```bash
unio schedule run BATCH_ID --project /physical/workspace >schedule-output.log 2>&1 &
unio schedule status BATCH_ID --project /physical/workspace
unio schedule pause BATCH_ID --project /physical/workspace
```

Pause and stop remain available from another terminal while the runner owns
its lease. They prevent subsequent attempt claims; they do not kill a previously
claimed dispatch or a detached native worker. Stop is terminal. Resume neither
extends expiry nor refunds attempts. Project `coord/STOP`, expiry, a changed
base or binding drift prevents new launches. Status reads only local saved
state and never contacts a provider or refreshes quota.

## Exact owner grant

Create jobs using the existing explicit `unio dispatch` prepare and approve
flow first. Inspect their immutable prepared previews and grant files. A batch
grant is strict UTF-8 schema-1 JSON, at most 128 KiB, with exactly these fields:

```json
{
  "schema_version": 1,
  "project": "/physical/workspace",
  "inventory": "/physical/workspace/approved-inventory.json",
  "inventory_sha256": "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
  "expires_at": "2026-10-17T10:00:00+02:00",
  "max_launches": 8,
  "poll_seconds": 5,
  "run_seconds": 1800,
  "jobs": [
    {
      "job_id": "REPLACE_WITH_32_LOWERCASE_HEX_ID",
      "grant": "/physical/workspace/dispatch-grant.json",
      "grant_sha256": "REPLACE_WITH_64_LOWERCASE_HEX_SHA256",
      "approval_key": "REPLACE_WITH_EXISTING_32_HEX_APPROVAL_KEY",
      "reservation_key": "REPLACE_WITH_UNIQUE_32_HEX_RESERVATION_KEY"
    }
  ]
}
```

The example uses descriptive placeholders; replace them with the real exact
values and a future expiry. Every path must be absolute, normalized and
physical. Input files must be bounded regular files, without symbolic or hard
links or special files. JSON duplicate/unknown keys, nonfinite numbers and
booleans in integer fields are refused. Expiry requires an explicit timezone
and must be future and within 24 hours at creation. `max_launches` is 1..128,
`poll_seconds` 1..60, `run_seconds` 1..7200, and the batch has 1..128 unique jobs
and unique reservation keys.

The inventory uses the existing schema-1 planner format. Each granted job must
occur exactly once and match its immutable task hash, worker, prepared preview,
frozen base and existing approval. The scheduler records the engine, complete
existing service configuration fingerprint, task template, account group and
loaded helper identities. All jobs in one batch use the same configuration
profile; mixed profiles are refused. Before launching it rechecks the original grant and
inventory bytes, prepared binding and a fresh plan. Planner and dispatcher
source files remain unchanged. The internal Python helper is orchestration,
not an AI adapter or an additional native launcher.

No missing approval or one-use shared-lead consent is manufactured. Native
STOP, account mapping, registered lead, subscription tier, bench state and
slot admission still apply. LOW still has one workflow per account group,
including the lead. This slice conservatively serializes scheduled jobs in the
same group even when a higher tier would allow more slots.

## Durable attempts and observations

Private state lives in `coord/schedules/`, with a frozen grant/binding file and
an atomic state file per batch. Creation and updates use private permissions.
A single per-batch runner lease rejects concurrent loops. A separate short
cross-batch lock serializes state updates, controls and launch claims. Neither
pause nor stop can be overwritten by a runner's older state snapshot.

An attempt, exact reservation and budget consumption are durable before the
dispatch process starts. A refusal, failed launch, missing/malformed output,
interruption or crash after that write consumes the attempt permanently.
Restart and resume never replay it, even if no native receipt exists.
Planner-blocked jobs consume no attempts. Creating another batch does not reset
native task identity or dispatcher reservations.

Distinct ready groups can launch while earlier native worker sessions remain
unfinished. A scheduled launch holds conservative virtual group occupancy
until matching bounded native evidence establishes a terminal Source outcome.
No visible native slot or missing result clears that occupancy. Known scheduled
write scopes are retained across batches, including when an earlier inventory
omitted them. Explicit matching accepted integration evidence in a newly
approved inventory, checked against its base ancestry, can release those holds.
Otherwise unresolved overlap refuses. Successful Source completion alone does
not authorize overlapping work or integration.

Native result observations use only the pinned runner's read-only `result`
command and the existing native-document validator, matching the worker, task
hash and batch base. They never run Verify. Saved Source state is a bounded
snapshot: status does not refresh it; another eligible `run --once` can observe
attempted work. Launcher acceptance is never reported as Source 0 or acceptance.

## Waiting and refusal reasons

| Saved reason | Meaning |
| --- | --- |
| `not_checked` | No scheduling pass has considered this job. |
| `group_full` | The fresh planner sees native account occupancy or the lead reservation. |
| `scheduled_group_occupied` | A known scheduled attempt has no confirmed terminal Source outcome. |
| `scheduled_scope_held` | Another consumed scheduled attempt retains an intersecting scope. |
| `scheduled_group_unknown` | An existing scheduled claim cannot establish its account group. |
| `project_STOP` | Native STOP prevents new launches. |
| `scope_conflict` | The existing planner detects a write conflict. |
| `agent_off`, `binary_missing`, `auth_signed_out`, `zero_allowance` | Existing local readiness refuses this route. No provider probe runs. |
| `binding_check_refused` | The bounded existing-service binding check refused or timed out before an attempt. |
| `plan_unavailable`, `plan_unresolved`, `plan_blocked` | A bounded planner observation cannot recommend this job. |
| `attempt_recorded` | Attempt was saved before dispatch; a missing result remains Unknown. |
| `attempt_consumed` | Dispatch returned or became uncertain; this job is never retried. |

Stopped/paused control, expiry and the finite attempt budget also explain why a
batch launches nothing. Unsafe or corrupt paths/state and helper, engine,
configuration, template, route, inventory or base drift refuse without repair
or deletion. Preserve the original records for owner investigation. Ordinary
text/JSON includes job IDs, phase enums and bounded exit evidence; approval and
reservation keys, request text, commands and private file contents are omitted.
This is trusted-host local capability containment, not authentication against
the same OS user and not an OS sandbox.

## First-slice limits and packaging

A batch freezes one base. Owner integration and a renewed approved batch are
explicit; this scheduler does not follow changing branches or approve dependent
jobs. Dependencies advance only from accepted evidence already in the frozen
inventory. No startup daemon, general queue service or automatic retry exists.

The existing dispatcher only checks reserved scopes in its supplied inventory.
The scheduler adds retained scopes for known scheduled attempts across batches;
it does not discover every unmanaged native session or another workspace's
account use. Keep inventories complete and manually respect unmanaged and
cross-workspace sessions. A missing or uncertain receipt can conservatively
hold a group/scope indefinitely; elapsed time alone is not permission to reuse
it. Failed/refused attempts are retained rather than silently repaired.

The installer packages the scheduler byte-identically beside the planner,
dispatcher and browser execution service. Installation invokes no provider.
Extracted standalone engines and thin configuration profiles without those
matching library payloads explicitly refuse `schedule` before any native call;
use a complete matching installation/profile. No alternate launcher or missing
payload fallback is provided.

Reads, JSON state, batch counts, subprocess output and process observation
windows have fixed bounds. State is at most 2 MiB per file, at most 128 batches
are retained, subprocess combined output is at most 1 MiB, planner observations
are at most ten seconds and dispatch observation is at most sixty seconds,
always cut to the remaining foreground duration. The existing service binding check runs as an internal read-only helper with
an aggregate deadline, because its original transport has multiple separate
15-second Git deadlines. Short state-lock waits and subprocess cleanup can
add a bounded tail; no new claim starts once the foreground deadline has passed.

## Focused offline checks

```bash
bash -n unio-install.sh
python3 -B tools/embed-continuous-delegation.py --check
python3 -B tests/unio-continuous-delegation.py
bash tools/check-docs.sh docs/CONTINUOUS-DELEGATION.md docs/CONTINUOUS-DELEGATION-CONTRACT.md
git diff --check
```

The suite uses disposable local projects, real planner/dispatch/service
boundaries and controlled fake native sessions. It includes concurrent disjoint
starts, same-group serialization and completion, active controls/STOP, durable
crash recovery, finite/expired grants, identity drift, malformed/refused launches,
state/path corruption, output bounds, private-key containment and installation
or missing-payload behavior. The focused suite is registered in the release
quality gate; the lead runs the final integrated gate and acceptance.
