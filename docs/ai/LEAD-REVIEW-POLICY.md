# Lead review policy

This is Unio's default review workflow for cooperating leads. The current
project instructions, the owner's own policy and any stricter project, CI or
human approval requirement prevail. Real account slots, owner holds, STOP and
the spending already included in each subscription stay unchanged.

## Default count and pairing
- One independent current-code reviewer plus the existing lead's final
  assessment: two reviewers in total. The lead already reviews; do not start
  another worker to duplicate that role.
- Prefer a reviewer from a different AI lab than the author and the lead.
  Where both are available, OpenAI models review Claude/Opus work and
  Claude/Opus reviews OpenAI work.
- Add another external reviewer only for a concrete unresolved disagreement,
  a coverage gap or an explicit owner request. Findings and reproductions
  decide correctness, not vote counts.

## When the lead's allowance is low
- Delegate the substantial review to another available subscription and keep
  the lead's final assessment concise: check the diff, tests and findings and
  reproduce material issues.
- Do not start a second workflow on the lead's shared account to relieve the
  lead. It draws from the same allowance and counts against the same slot.
- Allowance readings need a source and age. A manual observation is dated
  evidence, not a native meter or a universal threshold. Unknown is neither
  capacity nor exhaustion.

## Same-model fallback
When no different-lab reviewer is eligible, a fresh reviewer with an isolated
context may use the author's strong model at a higher supported effort, for
example a MEDIUM implementation followed by a fresh XHIGH review of the same
model. Label it honestly as same-lab coverage: it is not cross-lab independence
and does not satisfy a stricter project or CI requirement.

## Waiting instead of weaker substitutes
If the preferred reviewer is unavailable, preserve the work and wait. Do not
automatically substitute an unrequested route, a weaker model or another lab
just to keep calls running. Another-lab fallback needs an explicit owner or
project choice. Never request unsupported effort, use paid API or overage
fallback, invent account groups, or claim quota savings that were not measured.

## Effort and state reporting
- Report the current requested effort (for example LOW or XHIGH) first.
  Adaptive or AUTO is secondary information about the selection policy.
- Keep pending, idle, not started and Unknown distinct. A queued change
  applies to the next turn, not the running one.
- Requested route, model and effort are not proof of effective identity or
  effort; keep effective values Unknown without evidence.
- Judge route fit by recorded task outcomes and effort-specific evidence,
  never by an invented universal score or ranking.

## Review evidence
Reviewers inspect the exact frozen revision and receive no peer conclusions.
A failed call, empty report or bare acknowledgment is not a delivered review.
An approval never transfers to changed code. Record each requested route,
CLI version, model, effort, real exits, checks and acceptance separately.

## What this policy is not
Unio does not select reviewers, schedule models, rewrite reviewer commands or
enforce this policy automatically. The lead chooses an explicit eligible route
with a supported model and effort, then admits it through the native review
commands under the existing admission rules.

## Where it is installed
The installer writes this file to `templates/LEAD-REVIEW-POLICY.md` in the Unio
configuration directory and refreshes it on every installation. Keep local
changes in project instructions or your own owner policy file, not in this
managed copy. A fresh `MASTER.md` template points here. Installation never
overwrites a customized `MASTER.md` template, owner policy or `agents.conf`;
re-running `unio init` appends one marked reference to an older project
`MASTER.md`, or you can add that line yourself. Running sessions pick up the
policy only when they reread their instructions.
