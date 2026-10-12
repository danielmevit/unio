# Match protocol commands to their names

Owner-requested slice, 2026-10-12: new projects should use the same names in
startup prompts and commands: `yolo`, `balanced`, `thorough`.

## Compatibility and behavior

- Accept `unio mode yolo`, `unio mode balanced`, `unio mode thorough`.
- Continue accepting `medium` and `safe` as compatibility aliases. Reject
  unknown values or surplus arguments before changing any state.
- Keep schema-1 stored modes `yolo` / `medium` / `safe`, so older released
  runners can read an existing project's policy without migration.
- Display `yolo` / `balanced` / `thorough` in the mode command, human policy,
  status/init policy output and newly created worker instructions. Existing
  frozen run evidence is unchanged.
- Preserve JSON `mode` for machine compatibility; add `protocol` with the
  matching public name. Neither field changes concurrency, authority,
  validation obligations, automatic review behavior or effort.
- Help and completion offer the public names and identify old aliases.
- Meaningful offline checks cover every new name, old aliases, persistence,
  switching one axis without changing another, malformed/unsafe state and
  invalid arguments with no write or provider call.

## Separate reasoning choice

The startup guide must prominently show Low / Medium / Max reasoning
profiles, with a Low default. Low means supported middle/high settings with
bounded escalation, not a weaker model. Medium adapts effort to difficulty;
Max requests each route's highest permitted verified setting on new tasks.
Any profile can accompany any review protocol and coordination tier. The
owner can change any axis separately; preserve frozen active tasks, explicit
route restrictions and actual account limits. These effort profiles are
lead instructions in this slice, not an automatic native effort controller.

The existing Unio development workspace retains YOLO/low coordination and
its high/supported-middle default with xhigh ceiling. This slice makes no
max/ultra model call or new paid-token authorization. No UI/site/brand changes.

Implementation estimate: 15–30 minutes for aliases and focused acceptance,
with broader release checks/shipping estimated separately after integration.
