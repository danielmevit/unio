# Interrupted native runs

A host or WSL crash can remove a run's supervisor and provider without writing
an end. The original record then still says `process.state=running`. Unio does
not repair it: receipts, ledger, logs, commits and `.pid`/`.own` files stay as
historical evidence, and nothing is retried, signalled or removed.

## Which field to read

`process.*` is what was **recorded**. `runtime_observation` is what can be
**observed now**, added to `unio result`, `unio watch --json` and handoff
`result.json`. The same projection also feeds `unio report`, `unio status` and
the dashboard's `activity`.

| `state` | Meaning | `activity` |
| --- | --- | --- |
| `running` | Worker lock held, or the recorded owner is live | `running_recorded` |
| `pending_grace` | Free lock inside the grace window; a start or exit may be in flight | `running_recorded` |
| `completion_unknown` | Free lock after grace (or lock proved held by another task), no recorded end | `completion_unknown` |
| `unknown` | Evidence is unreadable, unsafe, malformed, unsettled, or surviving session members exist | `completion_unknown` |
| `terminal` / `not_run` | The record's own state; `source_exit` is exactly its exit, including 124 | recorded state |

`source_exit` is JSON `null` and human `Source exit: Unknown` for every
unresolved state. `interrupted` is `true` only when the recorded owner is proved
gone (absent, PID reused or previous boot) and `null` when owner metadata is
missing. `detached_processes_ruled_out` is always `false`: a setsid() outside
the owned sessions cannot be seen. `blocks_readiness` forces
`ready_for_human_review` to false. Human acceptance, current validation and
review remain separate.

## Evidence rules

- The worker lock is opened without creating it. A PID number alone never
  proves ownership: boot ID, start ticks, UID, session, worker and task must match.
- `UNIO_ORPHAN_GRACE_SECONDS` defaults to 30 and accepts 1..3600. An invalid
  value, or a missing, naive or future `updated_at`, gives `unknown`.
- Symlinked, special, hardlinked, oversized or non-private evidence gives `unknown`.
- Samples must match twice, which resists start and exit races.
- A legacy record without owner metadata gets a cautious observation only.

## After an interruption

1. `unio report TASK` — works with no report file and fabricates none. Several
   workers with the same task are listed separately.
2. `unio result WORKER TASK`, `git -C wt/WORKER log` and
   `unio save inspect --worker WORKER` show preserved work.
3. `unio handoff WORKER TASK` may describe the work and unknown completion; it
   is not a successful delivery or acceptance.
4. Continue only through a separately authorized **new task ID**, once the lock
   is free. Retry history and account policy are unchanged, and the old record
   stays as it was.

## Related honest states

**Delivery identity after a remount.** A delivery receipt records the file's
physical identity. A WSL remount can change `st_dev` (observed 114 to 72) while
inode, size, times and content hashes match. That receipt correctly stays stale
and a native review refuses before invoking a provider. Unio does not rebind the
old metadata. A fresh audit of the current code is separate evidence, not a
rewrite of the original Source. Storage-identity portability is a deferred
enhancement.

**Known timeout, then a later gate (VEC152).** Exit 124 stays 124. `unio
experience record` still refuses a result whose `revision` is not its
`current_revision` (`native result has no current revision binding`); a later
passing `unio verify` does not change the Source exit. Recording a historical
operational failure honestly needs its own schema and is a separate follow-up.
