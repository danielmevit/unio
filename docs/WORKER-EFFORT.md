# Managed Codex Source and worker effort

Opt in with a separate alias `codexmanaged` (no hyphen: native worker names
select the agent before the first hyphen). Keep the existing `codex` exec entry
unchanged. Append this entry once to your existing agents.conf:

```sh
cat >> "${UNIO_CONF_DIR:-$HOME/.config/unio}/agents.conf" <<'UNIO_MANAGED_AGENT'
codexmanaged=python3 -I -S -B "${UNIO_CONF_DIR:-$HOME/.config/unio}/lib/codex-worker.py" run --model gpt-6.1-sol --effort low
UNIO_MANAGED_AGENT
```

From the initialized project repository, map the alias to the real existing
Codex subscription group, initialize its worker, then run an existing task file
`coord/tasks/TASK.md`:

```sh
unio account codexmanaged codex
unio init codexmanaged
unio run codexmanaged TASK
```

Use the owner's actual existing group if it has a different name. Preserve the
registered lead and its reserved slot. Before running, select the owner's
authorized native concurrency tier (for example `unio tier medium` permits one
worker beside a lead in the same group); restore any temporary tier after the
worker is idle. No allowance is inferred from the slot count.
Run `unio run WORKER TASK` normally. The Source launches
`codex app-server --listen stdio://` under the existing CLI subscription login.
It inherits the CLI's existing permission/sandbox settings; configure those
before choosing this noninteractive Source. Provider approval requests are
refused, never automatically approved. No API fallback or model substitution.

`unio worker-effort WORKER --json` inspects the owned running Source.
`unio worker-effort WORKER high --json` requests a supported setting.
Only low, medium, high and xhigh are accepted, intersected with the selected
model's app-server catalog. This command cannot change model, permissions,
sandbox or service tier. Legacy exec and other routes return unsupported.

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
