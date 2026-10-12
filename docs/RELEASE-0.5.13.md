# Unio 0.5.13 — matching protocols and clearer effort

Protocol names now match their commands, and reasoning effort is a visible,
independent choice in every new-project startup prompt.

## Matching protocol commands

```bash
unio mode yolo
unio mode balanced
unio mode thorough
unio mode
unio policy --json
```

Balanced is the default; Thorough is the strictest review protocol. Human
policy output and new worker guidance use the selected public name.
Existing `medium` and `safe` commands remain compatibility aliases. Stored
schema-1 modes and the JSON `mode` field retain `yolo`/`medium`/`safe` so older
runners can read policy; the additive JSON `protocol` field carries the
matching public name. Mode changes never rewrite active tasks, remove frozen
checks or automatically launch reviewers.

## Choose reasoning effort separately

Every [complete startup prompt](ai/NEW-PROJECT-PROMPT.md) has two independent
fields: `Reasoning effort: Low` and `Coordination tier: low`.

- **Low:** conserve allowance using supported middle/high settings, increase
  only when needed up to xhigh, with max off.
- **Medium:** adjust effort to task difficulty, including supported max for
  difficult reasoning when the owner selected this profile.
- **Max:** request each route's highest permitted verified setting for new
  controllable assignments; explain fixed controls or additional owner caps.

Any effort profile works with any review protocol or coordination tier. Tell
the lead to change one while keeping the other two, and it must remember the
choice in this project's instructions and handoff. Existing runs keep their
frozen configuration. Explicit model holds, available controls and spending
rules remain. Higher effort does not create quota or authorize paid overage.

These profiles are documented lead instructions. There is no native
`unio effort` switch, automatic live-CLI effort change or server-proven
reasoning measurement. The installed `REASONING-PROFILES.md`, startup prompt
and [reasoning guide](ai/REASONING-PROFILES.md) explain the mapping and how to
raise or lower effort without changing review depth or concurrency.

## Delivery and limitations

The bounded offline acceptance covers matching and legacy names, persistence,
independent policy axes, refused writes for invalid/unsafe state and copied
standalone installer guide packaging. Release delivery uses the full repository
gate, artifact smoke, isolated upgrade/restore and an installed candidate before
publication, followed by official-download hash verification.

This release preserves the dashboard, website and brand implementation. The
existing real-workspace automatic-save helper exit -9 remains unresolved;
commit coherent work early. Reasoning profiles do not change this development
workspace's xhigh ceiling. No paid fallback or authentication change is added.
