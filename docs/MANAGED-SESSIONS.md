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

## Recorded history and delivery results

History is limited to 16 MiB per session, 64 KiB per JSONL record, and 1 MiB
of recorded JSONL bytes per output page (also at most 500 records). A record
that would exceed the record or archive bound is replaced by an `archive_limit`
marker; subsequent history is Unknown. Ordinary Source stdout/report streaming
continues, and reaching a history limit does not change a successful provider
outcome. Steering refuses before its RPC if its intent cannot be archived.

Output stops at the first corrupt, unsupported, out-of-order, overbound or torn
record and sets `gap` and `truncated`. A torn final line may be an in-progress
append; observation never skips it to claim a complete transcript. A page limit
sets `truncated` while retaining a contiguous cursor prefix. Reconnect using
`next_cursor`; `output_cursor` describes the validated prefix, not a claim about
unreadable history. A missing transcript with recorded output also reports a gap.

Steering returns `accepted` only for a matching active-turn acknowledgement,
`rejected` for a refusal before delivery or an explicit provider rejection, and
`uncertain` when transport or the acknowledgement cannot establish delivery.
Both rejected and uncertain sends exit nonzero. Identical request IDs return
the cached result without another RPC; changed content refuses. Intent is cached
and archived before transport. An archive error after acknowledgement cannot
turn confirmed acceptance into rejection. This does not provide crash recovery
or automatic retries: a terminated Source never resumes a turn.

Status, output and send validate the exact latest/session/worker/task binding.
An archive recorded as active whose backend identity cannot be established is
`stale`, with its unobserved exit left Unknown (`null`); PID disappearance does
not prove success or failure. Recorded terminal outcomes remain terminal while
process cleanup finishes. Refused authorization or a duplicate exclusive native
claim does not replace existing history. Input is read through an owned regular
file descriptor with no symlink following or blocking FIFO open; the full 8 KiB
UTF-8 instruction fits the bounded control frame, including JSON escaping.

These are trusted-host, same-user controls, not OS isolation. Cleanup signals
only the newly created app-server process group while its leader remains
unreaped, then reaps the leader. Processes deliberately detached into another
session are outside that group and are not signalled.
