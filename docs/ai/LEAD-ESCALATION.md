# Finish struggling tasks without an endless worker loop

Standing lead policy, owner-approved on 2026-10-08. Delegate first, preserve
useful work, and take responsibility when delegation stops making progress.
Read this at startup and before assigning a correction.

## Dedicated fix worker — Unio owner rule, 2026-10-13

For Unio development, when the lead finds a defect or would otherwise repair
a worker's implementation itself, delegate the bounded correction through
Unio to **Codex CLI / GPT-6.1 Sol (`gpt-6.1-sol`) / high effort**. The lead
defines the failure, scope and checks, then reviews and integrates the result.
It must not silently implement the fix in the coordinating session. This
supersedes the earlier direct-lead takeover default for this workspace.
Other project owners can explicitly choose their own correction route.

Use the existing approved ChatGPT subscription, a dedicated worker worktree,
a pinned per-run configuration and one native Source invocation per task.
Commit early and preserve previous edits, failed outcomes and dated receipts.
Report preparation, actual provider invocation, committed work, checks and
lead acceptance separately. Requested identity and effort are not proof of
effective settings or remaining allowance. If the route cannot finish,
preserve its work and report the actual failure; do not invent success, retry
blindly or fall back to an inline lead fix.

The owner authorizes **one focused Sol correction worker at a time alongside
the coordinating lead**, including when they share the Codex subscription.
This is an explicit exception to this workspace's usual low-tier concurrency,
not extra allowance or permission for unrelated parallel Codex assignments.
Keep the real shared budget mapping and registered lead. If native low-tier
admission would refuse the second slot, record the exception, temporarily
select `unio tier medium` for the correction cycle, and restore the prior tier
once the worker is idle. Keep unrelated admissions closed with STOP while
the correction runs; never fake another account group or erase the lead.

Resume before the authorized native run and stop new admissions afterward.
Keep current spending, review and integration rules. No API-key fallback,
additional token purchase, max/ultra effort or extra review fleet is implied.

## Worker, replacement, lead

1. Give a suitable worker one bounded assignment with a clear scope and
   meaningful checks. Judge its actual changes and results. Repeatedly missing
   the same demonstrated constraint, repairing one broken fixture per full
   test run, or reporting success before results exist signals poor progress.
   Quiet output or a difficult task taking time is not sufficient evidence.
2. If it cannot finish, preserve its commits, unfinished edits and real result.
   Give one other capable, available model a concrete correction with the
   failing evidence and saved work. Prefer a different AI lab when suitable.
   Respect the current run's deadline and the owner's interruption policy;
   obtain an orderly handoff before changing ownership. Do not blindly retry.
3. Apply an owner's explicit correction route first, including the dedicated
   Sol rule above for Unio development. Without such an override, if the
   replacement also cannot finish, the lead implements the remaining
   correction directly in its existing session. Do not send the problem back
   to either struggling model or start a ladder of weaker workers. When no
   eligible replacement is available, the lead can take over sooner.

This is a ceiling on unsuccessful delegation for the same unresolved problem,
not a two-attempt limit on an entire milestone. Do not reset that history by
renaming a task. A small repair needed after competent progress is different
from repeated failure to converge; record the reason for the decision.

Operational failures such as exhausted quota, authentication or a broken
connection are separate from code-quality findings. They can make a route
ineligible, but they do not establish that its model writes poor code.
Do not spend more calls probing a known unavailable route or raise effort
to solve a quota error. Preserve the failure and use an eligible route or
the existing lead.

## A takeover keeps the workflow intact

- Keep the previous worker's branch, failed results and useful edits. Reuse
  checked evidence and repair the demonstrated gap instead of restarting.
- Wait until the old writer and its owned children are idle. Freeze the new
  task, base, scope, ownership and checks before editing a dedicated branch.
  Preserve uncommitted work before cleanup; do not reset or clean it away.
- Without an explicit owner exception, in low tier direct work is part of the existing lead workflow. Do not
  spawn another lead-provider CLI, worker or independent test agent. Keep
  the lead reservation; do not bypass budget admission by changing aliases.
- Make an early coherent commit, run checks appropriate to the change and
  maintain a handoff. Use the selected work mode: focused checks for YOLO,
  with the full required gate at release. Test corrections must preserve
  their behavioral assertion; never make a failure pass by deleting coverage.
- Identify lead-authored code and self-review honestly. It is not an
  independent AI-lab verdict. Follow the owner's review and integration
  requirements; taking over grants no extra spending or merge authority.
- If the lead lacks required access, authority or allowance, preserve a
  truthful handoff and report the specific blocker. Do not promote a free
  supporting worker into lead or final acceptance.

Record the task, exact model/route/effort, demonstrated failure, saved revision,
replacement outcome and takeover decision in the coordination log and update
the model task-fit guide. Keep in-progress outcomes pending. A native Source
that was not run remains not run; local lead edits and checks must never be
presented as a successful delegated Source invocation.

## Where this is enforced

This is a rule for the lead, carried by startup instructions and installed
templates. The runner does not automatically diagnose model struggles,
switch models or turn worker output into policy. Native scope, workflow
locks, STOP, receipts and acceptance checks still apply. See the
[task-fit scoreboard](https://github.com/danielmevit/unio/blob/main/docs/development/MODEL-SCOREBOARD.md)
and [work modes](https://github.com/danielmevit/unio/blob/main/docs/WORK-MODES.md).
