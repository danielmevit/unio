# Explain the goal behind CLI progress

A lead update must connect the current work to the outcome the owner wants.
A task name, component, commit or passing check alone does not explain progress.
This applies during CLI sessions even when a dashboard also shows activity.

## Order of an update

1. State the main feature or operational goal in plain language. Explain what
   the owner will be able to do when it is complete.
2. Explain the current task's relationship to that goal. Identify a prerequisite,
   a directly useful improvement or a discovered detour honestly; do not pretend
   every bug fix implements the headline feature.
3. Describe the concrete behavior being changed: what happens now, what should
   happen, and why the difference matters. Then name the component when useful.
4. Give the actual evidence and state: preparation, active invocation, delivered
   proposal, committed code, verification, independent review, lead acceptance,
   private integration, installation and publication are separate milestones.
5. Say what remains, the next action, and a rough elapsed-time estimate with
   uncertainty. Passing an internal test is not completion of the user-facing goal.

For an overall status, cover the shipped baseline, the current feature and its
finish line, remaining work and the next functional priority. Do not substitute
only the latest worker or test result.

## Status questions: include context and technical detail together

For a status request, cover all of the following in a readable update:

- **Overall goal:** the practical result the owner wants.
- **Feature:** which capability is being built or improved.
- **Current piece:** the exact task/component and how it advances that feature.
- **Technical state:** concrete behavior changed, current worker route/CLI/version,
  requested model/effort, actual exits, meaningful commit or test evidence, review
  verdicts and remaining defects. A heartbeat proves liveness, not useful progress.
- **Next and estimate:** what remains for this task and feature, the next action,
  elapsed/estimated time and uncertainty. Mention parked work when it affects scope.

Do not replace task details with a generic roadmap, or omit the main goal when
giving low-level checks. Full receipts and hashes remain in the handoff; enough
concrete evidence belongs in the CLI answer to make the state assessable.

## Enough detail, without a receipt dump

Use a short connected explanation first. Add technical detail where it explains
a behavior, failure or decision. Keep existing provider reporting: an assignment
identifies subscription route, CLI/version, requested model and effort; results
keep actual exits, checks and acceptance separate. Requested settings are not
proof of effective settings or remaining allowance. Put full hashes, paths and
receipts in the handoff unless needed to assess the point being discussed.

A useful example: the goal is to manage the lead session through Unio. The current
task prevents delayed output from being attached to the wrong instruction. Its
checks establish that correlation, while process ownership and launch controls
remain unfinished. That explains both the task's value and its practical limit.

Give meaningful updates during work; do not manufacture activity or repeatedly
announce an unchanged wait. Answer a status question, then continue already
authorized work. If a real block prevents progress, name it and preserve the
exact next step. Do not imply that the lead keeps coordinating after its turn ends.

## Personal workflow and distribution

For this owner's projects, the current local OWNER-WORKFLOW.md is read by every
Unio lead and carries this reporting instruction. The owner's local AGENTS.md
and the public development handoff link this guide. These are instructions for leads, not an automatic dashboard
feature or an injection into already-running foreign CLI sessions.
