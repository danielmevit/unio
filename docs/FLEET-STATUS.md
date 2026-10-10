# unio fleet

`unio fleet [--project PATH] [--json]`

Provides a single compact observation of local agent admission rules, configured shared limits, active Native Workflows, and cached provider readings. This tool helps humans and the registered lead understand *why* an agent is blocked locally without assembling five different inspection commands.

## Constraints

- This command is strictly **observation-only**. It never initiates network connections, parses credential files directly, runs a quota probe, or modifies state.
- Provider capacity and authentication facts reflect only the **cached** metadata observed during the last `unio readiness refresh` or `unio capacity refresh`.
- Stale or expired allowance percent is never presented as currently available.

## Text output

The text view gives a summary of the project settings (Mode, Tier, Lead, STOP) and a breakdown per shared group:

```text
$ unio fleet
Project: /work/my-app
Mode: yolo | Tier: low | Lead: codex

Group [codex] - Occupied: 1/1
  Cached Allowance: stale (stale), age: 100s
    Bucket [codex] Window [primary]: expired - remaining: 20% (resets at 2026-10-10T20:00:00+00:00)
  Agent codex: BLOCKED (group_full) | Cached auth: ok (age 120s)

Group [antigravity] - Occupied: 0/1
  Agent antigravity: CLEAR (all local checks clear) | Cached auth: ok (age 200s)

Note: Observation reflects cached readings and local facts only. External sessions and provider readiness are uncounted.
```

## JSON format

Use `--json` for scripting.

```json
{
  "schema_version": 1,
  "project": "/work/my-app",
  "timestamp": "2026-10-10T12:00:00+00:00",
  "stop": false,
  "mode": "yolo",
  "tier": "low",
  "lead_agent": "codex",
  "groups": {
    "codex": {
      "limit": 1,
      "occupied": 1,
      "agents": {
        "codex": {
          "admission_state": "blocked",
          "reasons": ["group_full"],
          "cached_auth": {
            "status": "ok",
            "age_seconds": 120
          }
        }
      }
    }
  }
}
```
