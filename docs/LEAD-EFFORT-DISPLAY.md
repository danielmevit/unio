# Lead Effort Display (Effort-First Presentation)

Status: documentation for contracts `docs/development/contracts/0531-EFFORT-PRESENTATION-V8.md` and `docs/development/contracts/EFFORT-FIRST-DISPLAY-V8A.md` (0.5.31 release).

## Principle: Concrete effort first; adaptive policy secondary

In Unio lead sessions (`unio lead-session`), concrete requested reasoning effort (`low` or `xhigh`) is the primary user-facing concern. The adaptive or manual policy describes *how* the next turn's request is chosen and is strictly secondary.

Key rules:
- **Never headline `AUTO` as an effort level**: `auto` is an effort selection policy mode, not a reasoning intensity. The primary effort display shows concrete requested levels (`low`, `xhigh`), or truthful inactive/unstarted states (`not started`, `no active turn`).
- **Exact-turn active derivation**: The active requested effort is derived solely from the durable decision recorded for the exact current running/pending turn. It is never inferred from the ceiling, baseline, pending queue, or historical turns. If no decision record is available for an active turn, it reports `Unknown`.
- **Pre-first-turn is truthful**: Before the first turn has started, no effort has been requested. The display truthfully reports `not started`.
- **Idle and waiting states**: When no turn is active, the display reports `no active turn`, accompanied by the last requested attempt and its recorded outcome (e.g., `completed`, `rejected`, `interrupted`).
- **Provider rejection disclosure**: A provider rejection does not claim effort was consumed. It is disclosed honestly as an undelivered attempt (`rejected, not delivered`).
- **Queued next-turn requests**: An owner's queued next-turn effort (via `unio lead-session effort request <low|xhigh>`) is displayed separately (`pending next: ...`) and never overwrites or alters the running turn's active effort display.
- **Requested vs. Effective Unknown**: The effective model reasoning effort executed by the AI provider backend remains `Unknown`. Unio records and presents only what was requested.
- **Read-only zero provider calls**: Read-only inspection (`status`, `effort show`) makes zero provider or network RPC calls and does not mutate workspace state or unmanaged external TUIs.

## CLI Presentation Examples

### Startup
Before any turn has been executed:
```console
$ unio lead-session start --goal goal.txt --model codex
lead session started: lead-e7b3... (model codex, effort not started, policy adaptive, ceiling xhigh, owned thread ...)
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
- `current_request`: Exact details of the current turn's active request (`active: bool`, `effort`, `kind`, `source`, `turn_id`, `pending_next_turn`).
