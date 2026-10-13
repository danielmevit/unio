# Worker effort capability boundary

This is a bounded first slice, not a completed effort switch. Run inside a
Unio workspace:

```
unio worker-effort codex-1 --json
unio worker-effort codex-1 low --json
```

Inspection returns exit 0 with `state: unsupported`. A valid request returns
exit 2 with `state: unsupported`, its requested level, no native acknowledgement,
no configured effort and no pending turn. Invalid arguments or unsafe/missing
worker directories return exit 2. Requested effort is an input, not proof of
configuration or execution. Live task, subscription, model, CLI version and
managed identity remain Unknown; no process names or stale reports are used to
invent them. This command is read-only and makes no provider calls.

The installed Codex 0.162.1 schemas expose `thread/settings/update` with effort
for **subsequent turns**. Its response is empty. Configuration evidence is in
`thread/settings/updated.threadSettings.effort` or
`thread/read.thread.reasoningEffort`; neither proves per-request serving effort.
`turn/steer` has no effort field. Never interrupt, restart, continue or start a
new turn to force a request to apply.

Unio still runs the existing configured exec command through Source admission,
STOP, timeout and saving. Legacy exec cannot be retroactively attached. An
owned managed app-server backend, private bounded channel, authenticated current
worker/task/native slot identity, serialized requests and cleanup remain future
work. No channel or receipt store is created by this slice. An external channel
or fabricated state file cannot enable the command. No global configuration,
model, sandbox, permissions, service tier, subscription or account is changed.

Only low/medium/high/xhigh request syntax is accepted; max/ultra are excluded.
This syntax is not a claim that an arbitrary model supports these levels.
Acceptance of a real managed backend requires offline installed fake-app-server
coverage and a separately authorized native acceptance after the Source is idle.
