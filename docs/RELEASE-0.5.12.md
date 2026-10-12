# Unio 0.5.12 — choose workers from experience

This release adds a local record of useful project outcomes and explains which
workers have relevant evidence for the next task. It builds on native results
and the fleet overview without launching another AI session.

## Keep different outcomes separate

After a task finishes, its checks pass and you assess the changes, record the
final outcome with the requested model, route, effort and task type:

```bash
unio experience record "antigravity-feature" "TASK-ID" \
  --model "gemini-3.1-pro-high" --route "antigravity" --effort "high" \
  --task-type "implementation" --outcome "accepted"
unio experience show --task-type "implementation"
```

The record binds to the current native task revision. Source exit and check
facts stay separate from reported acceptance, a reported quality issue, an
operational failure or an unaccepted result. A failed connection is not counted
as bad code; exit zero alone is not accepted work. Missing correction counts,
effective model identity, cost and remaining allowance stay unknown.

These are explicit operator assessments. Recording an accepted outcome never
grants human acceptance, adds a review, merges changes or publishes anything.
Identical replay adds no sample. A conflicting assessment of the same revision
is refused, so record final assessments before changing the worker or base.

## Inspect conditional worker advice

```bash
unio experience suggest --task-type "implementation" --json
unio experience suggest --task-type "documentation" --work-kind "routine"
```

Advice shows task-specific samples alongside current local admission: STOP,
off switches, binary presence, shared-account slots including the lead, and
cached sign-in and allowance observations. Unknown or old readings stay
unknown; a clear local slot does not establish provider readiness.

Fewer than three distinct reported accepted tasks in 90 days supplies examples
without a recommendation. Enough evidence supplies conditional options. Free
Zen and proposal routes remain eligible for routine advice only in this slice.
There is no automatic winner, reservation, routing, retry or account refresh.

Read the [operator guide](MODEL-EXPERIENCE.md) for commands, storage schema,
bounds and refusal cases, and the
[lead guidance](development/LEAD-ROUTING.md#consult-local-task-experience-before-choosing-a-worker)
for applying the evidence without inventing confidence or extra authority.

## Delivery boundaries

Profiles are local to the project and use explicit metadata; automatic capture
and imported historical assessments are future work. This release does not add
finding aggregation, a scheduler, live lead transfer, phone pairing or native
macOS/Windows support. The existing dashboard and website interface are kept.
Lead cooldown restart remains experimental and opt-in, with its genuine
subscription-limit-to-restart cycle unobserved.

The source changelog and version plan distinguish a checked development
candidate from publication. Release downloads include `PROVENANCE.json` for
the exact source, full quality gate and packaged installation evidence.
