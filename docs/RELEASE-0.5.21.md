# Unio 0.5.21 — bounded continuous delegation

Published and installed on 2026-10-17 (UTC+02:00) from
`ecd88eacabee33e5fa7a99e0e4b80b5aeafec688`. Installation preceded publication.
Reproducible artifacts, all 40 isolated selftests, 0.5.20 upgrade/rollback,
configuration and owner-template preservation, exact installed scheduler/help,
and all six official download hashes passed. Prior tags remain unchanged.

Keep a finite batch of approved work moving as account slots become available.
The scheduler uses the existing planner and dispatcher, retaining native STOP,
shared-account limits and one-use consent before spending the lead's budget.

## Changes

- `unio schedule create`, `run`, `status`, `pause`, `resume` and `stop` manage
  an explicitly approved, expiring batch of existing jobs.
- Distinct ready accounts can start disjoint work without waiting for an
  earlier worker to finish. Conservative group and scope holds cover the
  gap before native background admission and span known batches.
- Attempts are durable before dispatch. A crash, refused launch or uncertain
  result never silently replays the job. Launcher acceptance, Source completion
  and owner acceptance remain separate.
- Pause and stop close new attempts without killing active workers. Reads,
  output and observation deadlines are bounded; status stays local.
- Observer cleanup retains its process leader through all group signals,
  then reaps it, preventing signals to a reused process group.
- Lead instructions require independent current-code reviews from at least
  two AI labs followed by lead assessment. Failed calls are preserved separately.
  The planner/dispatcher availability text and version plan are updated.

See [commands, exact grant fields and waiting reasons](CONTINUOUS-DELEGATION.md).
The first slice freezes its inventory and base: integration, new instructions
and dependent approvals need a renewed explicit batch. It does not approve,
review, accept, merge or retry work automatically. Unknown quota stays Unknown.

## Validation and review

Initial ChatGPT / Codex 0.162.1 / GPT-6.1 Sol LOW scheduler `35f1260`
finished Source 0 and five native checks, but lead inspection reproduced a
cleanup ownership gap. The separate LOW correction `221ffa5` finished Source 0
in 16m25s, passed 37 focused cases and all five native checks. Five mocked
ownership cases fail with the old helper. Planner, dispatcher and service
source bytes remain unchanged.

Antigravity / agy 1.4.0 / Gemini 3.8 Flash HIGH and Mistral subscription /
Vibe 2.26.1 / GLM 5.3 HIGH independently approved `221ffa5`, each with adapter
0 and current bound native approval. The lead inspected the code and qualified
the two informational Vibe notes; neither required a change. Effective model,
effort and remaining allowance remain Unknown.

Integrated `3c04fbd9ad149e3bd172b4c1126652c0e8fab619` passed the complete
`bash tools/quality-check.sh` on 2026-10-16, recorded from 22:12:46 to 22:41:14
UTC+02:00, exit 0 in 1,647.865 seconds. Source and global installation/config
were unchanged. Reviewed and gated executable/test bytes match, apart from the
release version and canonical lead guides. Final prose preserves that runtime.
Offline fixtures exercised fake native workers; a real provider batch through
`unio schedule` was not run.

Original failures remain separate: Mistral's earlier implementation attempt
failed infrastructure before edits; Copilot stopped at a private pre-call
version assertion; a lead-created Python cache invalidated the first review;
OpenCode Go timed out without a verdict; Perplexity was owner-cancelled when
Vibe was selected. None supplies approval or establishes quota exhaustion.

Artifact, upgrade/rollback, installed-payload and official-download checks are
recorded separately in release provenance. Installation precedes publication;
existing configuration and owner templates are preserved.
