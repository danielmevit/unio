# Managed Codex Source and worker effort

Introduced in 0.5.17 as an opt-in experimental managed Source and control
channel. Effort requests configure future turns; a single-turn Source can finish
before a pending choice is used. Starting effort remains selected in the alias.
These examples use low to match the field trial; choose another supported level
according to the project's reasoning policy.

Opt in with a separate alias `codexmanaged` (no hyphen: native worker names
select the agent before the first hyphen). Keep the existing `codex` exec entry
unchanged. Append this entry once to your existing agents.conf:

```sh
cat >> "${UNIO_CONF_DIR:-$HOME/.config/unio}/agents.conf" <<'UNIO_MANAGED_AGENT'
codexmanaged=python3 -I -S -B "${UNIO_CONF_DIR:-$HOME/.config/unio}/lib/codex-worker.py" run --model gpt-6.1-sol --effort low
UNIO_MANAGED_AGENT
```

From the initialized project repository, map the alias to the real existing
Codex subscription group after initializing its worker, then run an existing task file
`coord/tasks/TASK.md`. Initialize locally before setting the shared group so
root discovery selects the intended workspace:

```sh
unio init codexmanaged
unio account codexmanaged codex
unio run codexmanaged TASK
```

Use the owner's actual existing group if it has a different name. Preserve the
registered lead and its reserved slot. Before running, select the owner's
authorized native concurrency tier (for example `unio tier medium` permits one
worker beside a lead in the same group); restore any temporary tier after the
worker is idle. No allowance is inferred from the slot count.
Run `unio run WORKER TASK` normally. The Source launches
`codex app-server --listen stdio://` under the existing CLI subscription login.
By default it inherits the CLI's existing permission/sandbox and approval
settings: omitted startup options are absent from `thread/start`. Provider approval requests are
refused, never automatically approved. No API fallback or model substitution.

For an appropriate local task, explicitly opt in by choosing this alias entry
instead of the inherited-default entry above:

```ini
codexmanaged=python3 -I -S -B "${UNIO_CONF_DIR:-$HOME/.config/unio}/lib/codex-worker.py" run --model gpt-6.1-sol --effort low --sandbox workspace-write
```

For the owner's existing trusted-host coding workflow, when authorized, choose
both settings explicitly:

```ini
codexmanaged=python3 -I -S -B "${UNIO_CONF_DIR:-$HOME/.config/unio}/lib/codex-worker.py" run --model gpt-6.1-sol --effort low --sandbox danger-full-access --approval-policy never
```

`--sandbox` accepts only `read-only`, `workspace-write`, `danger-full-access`.
`--approval-policy` accepts only the schema's fixed string choices `untrusted`,
`on-request`, `never`; granular objects and arbitrary config are not accepted.
Each chosen value is sent only on the single `thread/start` RPC as `sandbox`
or `approvalPolicy`. Either option may be omitted independently. These are
requested startup choices, not proof of effective isolation or permissions.
They do not update the owner's live CLI/profile. Worktrees are not OS sandboxes;
inherited read-only settings cannot write or commit files. An effort update
never selects or grants startup permissions. Keep the same local initialization,
real shared-group mapping and lead reservation procedure for either example.

`unio worker-effort WORKER --json` inspects the owned running Source.
`unio worker-effort WORKER high --json` requests a supported setting.
Only low, medium, high and xhigh are accepted, intersected with the selected
model's app-server catalog. This command cannot change model, permissions,
sandbox or service tier.

When a worker has no active supported control channel (such as legacy exec or
other routes without an owned control socket), `unio worker-effort WORKER [--json]`
reports `state: unsupported` and `live_control: unsupported`, explaining the absence
of an active channel. Where discoverable from `agents.conf`, read-only static facts
are surfaced under `current_configuration` for future launches (`scope: future_launch`,
`provenance: static_agents_conf`). Newly edited configuration is never attributed
as what an already-running or frozen worker started with. Missing, ambiguous,
compound or wrapped routes remain Unknown with an actionable reason. Live-set
requests on unsupported routes continue to fail safely and never edit configuration.
Model reasoning effort remains distinct from coordination tier (`unio tier`) and
review pace, and effective inference effort stays Unknown.

An empty update response means RPC success, not configured effort. Notification
and readback acknowledge configuration for subsequent turns. A request during
the assigned turn remains pending-next-turn; effective inference effort stays
Unknown. The Source starts exactly one assigned turn and never interrupts,
restarts or creates another turn to apply a setting. Pending configuration may
therefore never be used by this Source.

The channel is a private Unix socket in a caller-TMPDIR temporary directory,
with a private manifest in coord/.locks. Native slot identity, holder ownership,
process lifetime and worker/task binding are checked before requests. Requests
are bounded and serialized. No arbitrary thread IDs or provider payloads are
returned to the client. Worker text streams into the ordinary native task log.
This is a trusted-host boundary: same-user code execution is not an OS sandbox.
Do not attach arbitrary existing Codex CLI sessions. Stale manifests fail closed;
after verifying that the old run has ended, remove its stale manifest manually.
