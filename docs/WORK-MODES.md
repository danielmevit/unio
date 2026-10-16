# Work modes and subscription tiers

Unio has three independent choices: the review protocol, coordination budget
and [Low / Medium / Max reasoning effort](ai/REASONING-PROFILES.md). Native mode
and tier switches persist; reasoning effort currently guides the lead. Choose them deliberately; a larger subscription does
not require a slower workflow, and a smaller one should not exhaust the lead.

Available in [Unio 0.5.3](https://github.com/danielmevit/unio/releases/tag/v0.5.3): mode, tier, policy, lead and
account commands, persistence in `coord/work-policy.json`, visibility, worker
instructions and native workflow admission. Policy reports
`workflow_enforcement` as `native_workflows`.
Foreground/background Source runs and independent reviews hold one locked
slot per shared budget group, admitted before any provider call. The base switches shipped in 0.5.3; matching `balanced`/`thorough` command
names and public labels are the 0.5.13 update.

## Choose the pace

| Mode | How the lead organizes work | Checks and review |
| --- | --- | --- |
| `yolo` | Finish a useful feature in a coherent batch. Delegate implementation and keep coordination brief. | Focused checks for changed behavior, a real smoke check where relevant, and a brief lead review. Avoid routine extra reviewer calls. Run the full required gate at a release boundary. |
| `balanced` | Deliver manageable feature batches with more integration attention. | Focused and relevant integration checks; one independent review for substantive implementation batches, a second for sensitive changes or unresolved disagreement, then lead assessment. |
| `thorough` | Plan risks, interfaces, failure cases and rollback before small reviewable batches. | Broader integration/security checks and the required project gate; two capable independent reviews from different known AI labs, both different from the author, then lead assessment and owner acceptance under existing authority. |

`balanced` is the default (`medium` is its compatibility alias). A mode shapes the next task's scope, validation and
review plan; it never silently removes an already frozen task's Validate
commands. Required checks must actually pass. Repeat or broaden checks only
when changed code, a failure or an unresolved concern justifies it. Record
what was checked and what remains unchecked.

Modes do not alter sandbox permissions, authorization, billing, automatic
retries, worker limit handling or acceptance rules. They do not interpret
an AI's output as an instruction to change policy. Releases still need their
required quality gate and the owner's authorization.

## Choose a coordination budget

These tiers describe the usable subscription budget for this project's lead
and workers. They are owner-selected planning profiles, not particular paid
plans, prices, model quality levels, reasoning levels or measured quota.

| Tier | Independent workflows per shared provider/account budget | Instructions for the lead |
| --- | --- | --- |
| `low` | 1, including the lead | Delegate implementation to other available providers. Normally keep the lead on planning, concise review, integration and handoffs. Direct takeover after worker escalation uses the existing lead session. Do not start another independent feature, test job or worker on the lead's provider. |
| `balanced` | 2, including the lead | Allow a second independent workflow on a provider when its capacity justifies it. Prefer useful work on other funded providers before consuming the lead's reserve. |
| `high` | 4, including the lead | Allow more independent workflows when useful and capacity permits. Do not create busywork or run every assignment at maximum effort. |

See [bounded escalation](ai/LEAD-ESCALATION.md) for direct lead takeover after
unsuccessful delegation; it does not add a workflow or relax these limits.

`low` is the default. This is a limit per shared budget group, not a limit
on the whole team: Codex can lead while Claude and GLM work on separate
assignments, provided their budgets are separate and available.

The unit is an **independent workflow**: a lead session, a Source assignment
or an independent review assignment. Subagents may help with that workflow
when its task and permissions allow them. They must not become separate
Unio feature or test assignments under the same provider in low tier. They
still consume that provider's allowance; use them only when useful. Unio's
native locks count top-level workflows, not every child process or internal
model request, and do not bypass a task's explicit no-subagents rule.

Use `unio lead codex` to register the lead's provider reservation; it counts
as one workflow in that budget group until explicitly cleared with
`unio lead none`. Registration is a planning reservation, not a claim to
have detected the lead process or its quota. A new lead reads and reconciles
the reservation before delegation. Without registration, native worker
limits still apply, but Unio cannot count an unmanaged lead CLI.

Worker labels use their configured agent prefix, such as codex in
codex-backend, to identify the default budget group. Operators can group
aliases or gateways sharing quota with `unio account AGENT GROUP`. For
example, distinct OpenCode model aliases using one Go subscription must
map to the same group. These names identify shared limits, not credentials;
Unio never guesses account ownership or reads authentication to group them.

Native concurrency is enforced across foreground and background Source
calls and independent native review calls within the workspace. A busy
budget rejects dispatch before a provider call; it does not queue, retry
or kill existing workers. Changing tier or grouping does not cancel active
runs. Existing runs retain their group; changing an occupied agent's group
or the registered lead's group must refuse until its reservation is clear.
New dispatches use the current tier and count already occupied group slots.

Lead and worker guidance is supplied to the AI, but Unio does not control
an already running lead CLI or external agents launched directly outside
Unio. The first implementation counts registered native workflows in this
workspace; cross-workspace/account-wide scheduling and automatic account
identification remain future work. Supported capacity readings and dated
manual readings remain separate from this chosen profile. Missing capacity
stays Unknown. Higher tiers never create extra allowance.

## Choose reasoning effort independently

Select **Low**, **Medium** or **Max** in the startup prompt, independently of
review protocol and coordination tier. **Low** is the default: conserve
allowance with a capable model at supported middle/high, escalating only
when needed up to xhigh, with max off. **Medium** adapts effort to difficulty,
including supported max for hard reasoning when explicitly selected. **Max**
requests each route's highest permitted verified effort for new assignments.
A fixed high-only route remains high; these labels are not universal CLI flags.

The owner can change one choice during the project while preserving the other
two. The lead records it in project instructions/handoff and applies verified
controls to future assignments, leaving frozen active runs unchanged. There
is no native `unio effort` command or automatic live-CLI effort change yet.
Read the [reasoning profiles guide](ai/REASONING-PROFILES.md) and route-specific
[model effort guide](development/MODEL-EFFORT.md). Preserve explicit route
holds, actual allowance, spending restrictions and requested/effective Unknowns.
Do not downgrade models or change billing/fallback because a tier changed.

## Commands and visibility

From a Unio project, the command surface is:

```bash
unio mode yolo
unio tier low
unio lead codex
unio policy
unio policy --json

# Change just one setting; the other persists.
unio mode balanced
unio tier high

# Change review protocol without changing tier or reasoning effort.
unio mode thorough

# Show the current value without changing it.
unio mode
unio tier
unio lead
unio account

# Group two configured aliases sharing the same budget.
unio account opencode go-primary
unio account glm go-primary
```

Public mode values are `yolo`, `balanced`, `thorough`; old `medium` and `safe`
values remain aliases for Balanced and Thorough. Allowed tier values are
`low`, `medium`, `high`. Reject extra arguments and invalid values.
Both settings are workspace-wide and persist across sessions in
`coord/work-policy.json`. A missing file means the documented defaults;
malformed, unknown-schema or unsafe policy files fail locally instead of
silently resetting settings. Setter operations validate before writing and
replace the file atomically under a shared lock.

The policy JSON keeps schema 1 and its compatibility `mode` values
(`yolo`/`medium`/`safe`), adding `protocol` (`yolo`/`balanced`/`thorough`). The
stored mode values remain readable by older runners. JSON also includes
`tier`, an optional update timestamp,
the effective per-group workflow limit, lead reservation, account mappings,
lead delegation guidance and an explicit
capacity value of `unknown`; it does not manufacture subscription readings.
Human output states the active mode, tier, per-group workflow limit, lead
reservation, account mappings and lead expectations.
`unio init`, `unio status` and help expose the controls. Completion offers
valid switch values.

Fresh lead templates instruct the lead to read `unio policy` before planning
or delegation and point to the installed copy of this guide. Initialization
preserves custom MASTER.md content and adds an idempotent readable policy
reference. Repository AI onboarding and the lead routing guide link here.
Existing projects can read their policy without reinitializing workers.

Each new run snapshots its chosen policy in a local run receipt and supplies
the guidance with the task through the existing file/stdin prompt transport.
The original task remains unchanged and is still the task-hash and scope
validation authority. Wrappers that need the original task path use
`UNIO_ORIGINAL_TASKFILE`; `TASKFILE` identifies the effective worker prompt.
No long prompt is inserted into argv or environment variables. Existing
runs retain their snapshot when a setting changes.

Unio does not autonomously choose arbitrary tests or launch additional AI
reviewers from a mode switch. The lead uses the selected guidance to design
the next task, and the native runner enforces its explicit validation rules
and per-group workflow concurrency. Browser selectors and per-account scheduling can
build on the same policy later; this first implementation establishes the
core CLI, persistence, visibility and worker instructions.

## Current Unio development workflow

Owner direction on 2026-10-07 is **YOLO + low tier**, with implementation
delegated through Unio and personal lead review. Complete visible feature
batches, use focused native validation and reuse still-valid evidence. Do
not run the whole repository suite after every small source or docs change.
Run the full repository gate before publishing a release, or earlier when
actual changes or failures warrant it. Already running frozen checks keep
their original evidence; historical review and test failures remain recorded.

The [roadmap](development/ROADMAP.md) and [version plan](VERSION-PLAN.md)
describe delivery sequencing. Runtime completion is recorded in the command
implementation's changelog and tests, not inferred from this contract.

Native shared-lead admission additionally requires an explicit one-use owner
[lead budget grant](development/LEAD-BUDGET-CONSENT.md), even at medium/high.
`unio lead-budget grant <agent> <worker> <task> <run|review>` expires in 15
minutes and never raises the tier cap. `show` preserves history; `revoke <id>`
withdraws unused consent. Alias grouping remains an explicit owner duty.

Failed-run WIP preservation is a separate, default-off project setting:
`unio wip on|off|status`. It does not change mode, tier, lead consent or account
ownership. See [WORK-WIP.md](WORK-WIP.md); a WIP commit remains failed and unaccepted.
