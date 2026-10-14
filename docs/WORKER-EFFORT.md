# Managed Codex Source and worker effort

Opt in with a separate agents.conf entry (keep existing codex exec unchanged):

```ini
codex-managed=python3 -I -S -B "${UNIO_CONF_DIR:-$HOME/.config/unio}/lib/codex-worker.py" run --model gpt-6.1-sol --effort low
```

Map this alias to the same existing Codex account budget group using the native
work policy. For an existing group named `codex`, use:

```sh
unio account codex-managed codex
unio init codex-managed
unio run codex-managed TASK
```

Use the owner's actual existing group if it has a different name. The registered
lead still consumes its slot; select the owner's authorized native concurrency
tier before admission. No allowance is inferred from the slot count.
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
