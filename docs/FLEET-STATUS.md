# See the local agent fleet

The source candidate adds `unio fleet` for the 0.5.11 follow-up; it is not in
the published 0.5.9 installation. It combines local account slots, agent on/off
and binary facts, cached authentication and recorded allowance in one view.

```bash
unio fleet
unio fleet --json
unio fleet --project "/work/my project" --timeout 15
```

Run it from a project, or select the workspace containing `coord/` and `wt/`
with `--project`. Help works outside a project. The default whole observation
budget is 10 seconds; `--timeout` accepts 1–60. Slow inputs receive a share of the
remaining time so one hang need not hide healthy later inputs.

## Read the explanation

The text view shows project mode, tier, lead and STOP, then occupied slots per
shared account and agent explanations:

```text
Mode: yolo | Tier: low | Lead: codex

Group codex: occupied 1/1
  codex: blocked (shared budget group is full) | auth: unknown
  alias: blocked (shared budget group is full) | auth: unknown

Group mistral: occupied 0/1
  vibeglm: clear (all local checks clear; dispatch readiness unknown) | auth: unknown
```

The registered lead is already included in occupied slots. Aliases sharing an
account share its limit. A clear local check does not establish usable provider
allowance, authentication, adapter dependencies or permission to dispatch.

Local blocks are STOP, an off agent, a missing binary or a full shared group.
Unavailable policy or unknown executable presence makes admission Unknown
unless another known fact blocks it. Unsupported cached authentication stays
Unknown. Nothing is automatically started, refreshed, benched or retried.

Manual and cached Codex allowance are separate. Each reading retains its source,
observation time, age, freshness and optional reset. Current usable percent is
distinct from the last recorded percent. Stale, expired and historical values
are labelled as old readings; a past reset never implies a refill.

## JSON contract

`--json` emits one schema-1 object and no progress text. Exit 0 includes partial
Unknown snapshots. Invalid arguments or a missing project return 2; interruption
returns 130.

- Top level: `schema_version`, `project`, `checked_at`, `timeout_seconds`, `stop`,
  `mode`, `tier`, `lead_agent`, `lead_group`, `sources` and `groups`.
- `sources` names policy, agents, capacity_manual, capacity_codex and readiness.
  Status is ok, missing, invalid, timeout, malformed, overflow, error or
  launch_failed. A native nonzero exit is error; its text is not exposed.
- Each group contains `limit`, `occupied`, `agents`, `manual_allowance` and
  `cached_allowance`. Unknown limits/counts or absent readings are null.
- Each agent contains `admission_state` (clear, blocked or unknown), enum
  `reasons`, `binary_present`, `bench_off`, `dispatch_readiness` (always unknown)
  and `cached_auth`. Authentication metadata is separate from allowance.
- Manual allowance contains named `windows`; cached Codex allowance contains
  named `buckets` with windows and optional historical `last_good`.
  `usable_remaining_percent` is null when no current value is established.
  `last_reading_remaining_percent` is historical context, never an assumed
  usable budget.

## Local observation only

The command uses only the invoking installation's fixed native JSON inspection
commands. It does not execute configured agent commands, make provider requests,
read credential files or create observation stores. It refuses malformed or
unsupported inputs rather than interpreting missing data as spare capacity.
Output is bounded; raw native stderr, command text and auth identity fields are
omitted. Owned child process groups are stopped on timeout, overflow, normal exit
and interruption, including descendants that close their output pipes.

The snapshot is not atomic, a reservation or live provider readiness. External
sessions and other workspaces remain uncounted. Check current native admission
when actually launching work. See [work modes](WORK-MODES.md),
[capacity readings](CAPACITY-READINGS.md) and
[agent fleet assignments](development/AGENT-FLEET.md).
