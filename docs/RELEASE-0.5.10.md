# Unio 0.5.10 — safer recovery and daily-use improvements

Published from the frozen recovery and daily-use snapshot `db78932` after the
complete release gate, installer, upgrade/rollback and official download checks.
[Release and downloads](https://github.com/danielmevit/unio/releases/tag/v0.5.10).

This release improves recovery and everyday use without adding another
subscription or changing the selected work mode or tier.

## Keep useful saved work

Older eligible recovery saves move into a private archive instead of being
deleted, including when the project reaches its 32-active-save limit. Each
worker's newest valid save, claim pins and corrupt evidence stay protected.
Archived IDs still work with inspect, restore and separately authorized
continuation. Files, manifests, task context and Git bundles retain their bytes.

```bash
unio save usage --json
unio save inspect SAVE_ID --json
```

The archive is bounded to 128 saves or 512 MiB. When archival cannot proceed,
Unio refuses a new save and keeps the existing history; it never purges the
archive automatically. Usage is a local metadata observation, not content
verification, and reports Unknown for busy or unsafe evidence. See
[work saving](WORK-SAVING.md) for limits and recovery commands.

## Separate sign-in from allowance

```bash
unio readiness refresh claude
unio readiness show --agent claude --json
```

Refresh explicitly runs bounded, non-generating native metadata commands for
the checked Claude Code 2.1.296. Only allowlisted fields enter the private cache;
email, tokens and account identifiers are discarded. Other versions and agents
remain unsupported. The dashboard reads this cache without refreshing a
provider. Missing, stale and failed observations remain Unknown. Signed in
never means available allowance or permission to run. See
[authentication observations](development/AGENT-READINESS.md).

## Resume your dashboard view

Task search, worker, lifecycle and category filters survive reloads of the same
dashboard URL. Reset clears those filters while preserving theme and list/map
preferences. Missing restored choices reconcile after the first live reading;
blocked browser storage leaves the filters usable for the current page.

The [daily-use guide](DAILY-USE.md) explains the normal lead/worker loop, mode and
tier controls, results, recovery and dashboard startup. Run
`unio dashboard ensure --open-browser` to get your current local link.

The existing experimental lead cooldown limitation remains unchanged. Phone
pairing and automatic acting-lead handover remain future milestones.

[Release and downloads](https://github.com/danielmevit/unio/releases/tag/v0.5.10).
