# Lead Effort Display (Effort-First Presentation)

Status: documentation for contract `docs/development/contracts/0531-EFFORT-PRESENTATION-V8.md`, with the bounded truth corrections of `docs/development/contracts/0531-FINAL-REVIEW-CORRECTIONS-V10.md` (0.5.31 release), plus the 0.5.32 completion-housekeeping change (candidate, not yet published).

## Principle: Concrete effort first; adaptive policy secondary

In Unio lead sessions (`unio lead-session`), concrete requested reasoning effort (`low` or `xhigh`) is the primary user-facing concern. The adaptive or manual policy describes *how* the next turn's request is chosen and is strictly secondary.

Key rules:
- **Never headline `AUTO` as an effort level**: `auto` is an effort selection policy mode, not a reasoning intensity. The primary effort display shows concrete requested levels (`low`, `xhigh`), or truthful inactive/unstarted states (`not started`, `no active turn`).
- **Exact-turn active derivation**: The active requested effort is derived solely from the durable decision recorded for the exact current running/pending turn. It is never inferred from the ceiling, baseline, pending queue, or historical turns. If no decision record is available for an active turn, it reports `Unknown`.
- **Pre-first-turn is truthful**: Before the first turn has started, no effort has been requested. The display truthfully reports `not started`.
- **Idle and waiting states**: When no turn is active, the display reports `no active turn`, accompanied by the last requested attempt and its recorded outcome (e.g., `completed`, `rejected`, `interrupted`).
- **Waiting is truthful**: `waiting` is shown only while the lead is actually waiting: at least one registered worker is not terminal, or a terminal worker's review wakeup is still unconsumed. After a turn completes with every worker terminal and no wakeup left, the stored flag is cleared under the short control lock. This cleanup is best-effort housekeeping after the completion was already recorded: if the control state is busy (for example another control command holds the lock longer than the 5-second wait) or unavailable, `run` still reports the genuine completion (exit 0, `delivery: completed`), leaves the stored flag unchanged and adds a fixed `warning` that the housekeeping is uncertain. Views still show the truthful value. A same-request-id replay sends no new turn and retries only the cleanup. Failed, rejected, interrupted or unknown turns never run this cleanup, and they keep their exit codes. A new `worker wait` on a non-terminal worker shows waiting again. Views never make calls to work this out.
- **Known limitation (display only):** if that cleanup was skipped because of contention, the stale stored flag remains. A later `worker register` without `worker wait` can then make views show `waiting` again although no worker is waiting and no wakeup is pending. This never gates or starts a call, and the completed turn stays completed. Treat the earlier `warning` as the signal that the stored flag may be stale. A runtime fix is recorded as backlog work and is not part of 0.5.32.
- **Uncertain is not confirmed**: An active turn whose delivery is `outcome_unknown` keeps its attempted effort but is marked `delivery uncertain, effective Unknown`. It is never shown as an ordinary confirmed active turn. A turn not yet acknowledged is marked `delivery not yet acknowledged`. JSON `current_request.delivery` is `accepted`, `pending` or `uncertain`.
- **Provider rejection disclosure**: A provider rejection does not claim effort was consumed. It is disclosed honestly as an undelivered attempt (`rejected, not delivered`).
- **Queued next-turn requests**: An owner's queued next-turn effort (via `unio lead-session effort request <low|xhigh>`) is displayed separately (`pending next: ...`) and never overwrites or alters the running turn's active effort display.
- **Requested vs. Effective Unknown**: The effective model reasoning effort executed by the AI provider backend remains `Unknown`. Unio records and presents only what was requested.
- **Read-only zero provider calls**: Read-only inspection (`status`, `effort show`) makes zero provider or network RPC calls and does not mutate workspace state or unmanaged external TUIs.

## CLI Presentation Examples

### Startup
Before any turn has been executed:
```console
$ unio lead-session start --goal goal.txt --model gpt-6.1-sol
lead session started: lead-e7b3... (model gpt-6.1-sol, effort not started, policy adaptive, ceiling xhigh, owned thread ...)
```

### Status during active turn
During an active coordination turn requesting low effort:
```console
$ unio lead-session status
lead session lead-e7b3...: state running, generation 2, effort low (policy adaptive), stopped False, waiting False
```

With an opposite next-turn effort queued:
```console
$ unio lead-session effort request xhigh --reason "planning phase"
requested next-turn effort: xhigh (pending next turn only; applied after active turn ends)

$ unio lead-session status
lead session lead-e7b3...: state running, generation 2, effort low (policy adaptive, pending next: xhigh), stopped False, waiting False
```

### Effort show inspection
```console
$ unio lead-session effort show
requested effort: low (active turn turn-a1b2, kind coordination; policy adaptive, ceiling xhigh, pending next: xhigh)
```

When the active turn's delivery is uncertain (`outcome_unknown`):
```console
$ unio lead-session effort show
requested effort: low (active turn turn-a1b2, kind coordination; policy adaptive, ceiling xhigh; delivery uncertain, effective Unknown)
```

When idle after completion:
```console
$ unio lead-session effort show
requested effort: no active turn (policy adaptive, ceiling xhigh; last requested: low (completed))
```

When idle after provider rejection:
```console
$ unio lead-session effort show
requested effort: no active turn (policy adaptive, ceiling xhigh; last attempt: low (rejected, not delivered))
```

### Structured JSON views
For programmatic callers, `_session_view` retains all existing fields (`effort` with `mode="auto"`, `baseline_effort`, `generation`, `state`, etc.) while adding additive structured display objects:
- `effort_display`: Structured summary of active effort, policy mode, ceiling, pending next turn, and last attempt.
- `current_request`: Exact details of the current turn's active request (`active: bool`, `state`, `delivery`, `effort`, `kind`, `source`, `turn_id`, `pending_next_turn`).
- The top-level `waiting` field reports truthful waiting (see above), not a sticky marker.

### Replacing the managed owner
`unio lead-session start` replaces the recorded owner only when that owner is cleanly stopped. It refuses, before any process or inference, when:
- the owner record or the owner's control state is unreadable or unknown. Nothing is reset or forged; inspect `coord/lead-effort/`.
- the stopped owner still has a proven unresolved active turn (an acknowledged provider turn without an observed terminal). Recover it on the same thread first: `unio lead-session recover --session <id> --interrupt`.

A stopped owner whose turn was never acknowledged has no recovery path and may be replaced. Older sessions stay readable with `status --session <id>` (labelled historical).
