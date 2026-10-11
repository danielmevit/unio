# Explain ready and blocked work before dispatch

2026-10-11 update: the [read-only CLI planner](../TASK-PLAN.md) is implemented
as a checked source candidate after the fleet overview. Focused offline tests,
native scope/validation and personal lead review passed. It uses an explicit inventory,
native task hashes/scopes, accepted Git revisions and optional observation of
existing queue records. Dispatch is still unimplemented. The original planning
boundary below is retained; current published/installed 0.5.9 lacks this command.

Next functional slice after the CLI fleet overview. This is the proposed
implementation boundary, not a shipped scheduler or authorization to start work.

## Useful result

Give the lead one read-only plan of the tasks that can proceed independently,
which ones are waiting, and the exact reasons. A busy worker should not hide
ready work on a different account. A second alias of the same subscription
should not appear to create extra capacity.

Start with recommendations and explanations. Add an explicitly enabled,
single-attempt executor in a later slice, using the existing queue's approval,
reservation and replay protections. The planner itself must never run, retry,
bench, approve, reserve, merge or modify a task.

## Build on existing evidence

The existing queue records immutable draft hashes, worker assignment, owner
approval and durable reservation. Native policy records shared-account mappings
and slots, including the registered lead. Native results bind verification to a
revision. Cached allowance and authentication are separate observations.

A Source exit of zero, a successful test, a green review or
`ready_for_human_review` is not human acceptance. The implementation contract
must name the actual accepted/integrated revision evidence used to satisfy each
dependency. Missing or stale evidence means an unresolved dependency, never
assumed completion.

Do not create a second queue or migrate the existing database merely to show a
plan. Existing queue constructors may initialize storage: use an explicitly
read-only observation path and prove that absent state stays absent.

## First implementation contract

Freeze these inputs before assigning code:

- An explicit task inventory with immutable task/draft identity, dependencies,
  allowed write paths and intended worker or eligible worker set.
- A named source of exact dependency completion evidence, including its revision
  and the base against which it remains usable.
- A bounded local fleet observation with STOP, bench/binary facts and shared
  account slots. Unknown inputs remain Unknown.
- A deterministic conflict rule for write scopes. Exact and parent/child paths
  conflict; unsupported or ambiguous glob patterns require serialization or an
  unresolved explanation. A broad scope must not silently appear disjoint.

Show ready, blocked and unresolved separately, with dependency, scope,
account-slot and missing-evidence reasons. Keep a stable ordering so repeated
read-only observations are easy to compare. Display the input revision and age;
this is a point-in-time recommendation, not a reservation or permission to run.

Fresh zero allowance and signed-out observations deserve a visible explanation,
but the planner must not turn cached observations into account policy changes.
Never infer a refreshed budget from a past reset time or call a model to poll
its availability.

## Finish conditions

A focused offline fixture demonstrates independent work proceeding past a busy
account, a lead occupying its low-tier account, shared aliases, dependency
cycles/missing evidence, conflicting scopes and changed revisions. The planner
starts no process that can run an agent and leaves coordination state unchanged.

Only after that slice is accepted should dispatch be implemented. Dispatch must
recheck exact task/revision authority and native admission at launch; a previous
plan cannot bypass STOP, reservations, slots or the retry brake.

## How the first planner should explain a day of work

The planner should explain what could proceed from recorded tasks and fleet
state. Suppose the lead is working on Codex. That occupies its account's one
low-tier slot, so a second independent Codex task is blocked. A documentation
task on Copilot and a separate implementation task on an idle Gemini account
can be ready if their dependencies are satisfied and their write paths do not
conflict. One busy account need not stop independent work on another.

GLM and Medium aliases on the same busy Mistral account share one budget. Both
must wait for that account's slot; a different model name creates no additional
capacity. Conversely, an empty local slot does not prove provider availability.
Cached zero allowance or signed-out status should have separate explanations.
A past reset time is not evidence that allowance has refreshed.

Dependencies require the exact accepted revision of the prerequisite. A task
waiting for a known required revision is blocked until that evidence matches.
Missing acceptance evidence or an ambiguous write-scope pattern makes the task
unresolved. Successful execution, passing tests and a green review alone do
not establish human acceptance. Each ready, blocked or unresolved result should
show its reason, relevant input revision and observation age.

Ready means a recommendation, not approval, a reservation or permission to
dispatch. Later dispatch requires explicit approval and fresh authority and
admission checks; retries are never implicit. The read-only planner is now a
source candidate; its later dispatch capability still requires implementation.

See the [current roadmap](ROADMAP.md), [work policy](../WORK-MODES.md),
[queue contract](../NEXT-MILESTONE-CONTRACTS.md#2-queue-library-contract) and
[model roles](../ai/MODEL-ROLES.md).
