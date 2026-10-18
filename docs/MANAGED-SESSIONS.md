# Managed sessions and steering

Introduced in 0.5.22 as the first managed-session CLI slice building on
`tools/codex-worker.py` and the opt-in managed Codex Source (`codexmanaged`).
It provides stable session inspection, ordered output reconnect, and active-turn
steering without starting extra turns, unmanaged CLI instances, or provider calls
for observation.

## CLI interface

```sh
unio session status WORKER [--json]
unio session output WORKER [--after N] [--limit N] [--json]
unio session send WORKER --file PATH --request-id ID [--json]
```

- `unio session status WORKER [--json]`: inspects local session state,
  assigned worker and task, route, model, requested and configured effort,
  effective inference (Unknown), exit code, and output cursor. This operation
  reads only local metadata and makes no provider call. Completed and failed
  session records remain readable historically and work while STOP is set.
  Unsupported routes (e.g. legacy exec) report unsupported.
- `unio session output WORKER [--after N] [--limit N] [--json]`: retrieves
  ordered output records (agent messages, command output, and lifecycle
  events) from `coord/sessions/`. The default limit is 100 records (maximum 500).
  Returns `session_id`, `worker`, `task`, `next_cursor`, and `output_cursor`
  along with `truncated` and `gap` flags, allowing clients to reconnect and
  stream incremental output without silent omissions or duplicates. Invalid
  bounds refuse.
- `unio session send WORKER --file PATH --request-id ID [--json]`: delivers up
  to 8 KiB of nonempty UTF-8 text from a regular private file directly to the
  currently active turn via supported `turn/steer`. Request IDs are bounded
  portable labels. Steering is idempotent: repeating an identical request returns
  the recorded result without invoking another provider RPC. Changing content
  for an existing request ID refuses. If a transport fails or is uncertain,
  it is not silently replayed. Sending input to a completed turn refuses.

## Ownership and boundaries

Sessions run in the existing single-turn managed Source model. Observation and
steering do not start secondary tasks, create new turns, bypass native admission,
or alter startup permissions. File ownership, socket credentials, and live process
identities are validated before control requests take effect. Provider credentials,
tokens, and full RPC envelopes remain private and are excluded from public API output.
Session records survive normal failure and completion under `coord/sessions/`.
Existing STOP meaning is preserved: it blocks new admissions, not the control
channel of an already authorized Source.
