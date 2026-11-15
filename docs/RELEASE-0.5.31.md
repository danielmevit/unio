# Unio 0.5.31 — Clearer lead controls and durable review defaults

Use the experimental, opt-in `unio lead-session` Codex backend for explicit turns with requested LOW or XHIGH effort. The current requested level is primary; adaptive/manual policy and queued next-turn changes are separate. Waiting and uncertain delivery are labelled honestly. This does not adopt an existing AI CLI or provide a complete autonomous scheduler.

## Changes

- Inspect implementation-task scope before spending a worker run with `unio verify WORKER TASK --preview [--json]`. It runs no declared checks or provider and does not establish admission, delivery, verification PASS or acceptance.

- Use the experimental, opt-in `unio lead-session` Codex backend for explicit turns with requested LOW or XHIGH effort. The current requested level is primary; adaptive/manual policy and queued next-turn changes are separate. Waiting and uncertain delivery are labelled honestly. This does not adopt an existing AI CLI or provide a complete autonomous scheduler.

- Keep owned turns alive until completion or a configured deadline. Exact-thread interruption and recovery preserve partial work and distinguish acknowledgement, process exit and observed terminal state. Rejected requests retain pending effort and review wakeups; unknown ownership fails closed.

- Use Fast, Balanced and Thorough as public work-pace names. Legacy `yolo` input and stored schema-1 values remain compatible; pace does not grant permissions.

- Carry review and budget guidance into new projects through the managed `LEAD-REVIEW-POLICY.md`, fresh lead templates and an idempotent project-startup pointer. Prefer OpenAI↔Claude/Opus review, delegate substantial work when the lead has little allowance, and label a fresh same-model/higher-effort fallback honestly as same-lab. Preserve stronger project approvals and existing custom configuration. These are cooperating-lead defaults, not an automatic reviewer selector.

- Record installed Vibe and Antigravity CLI versions as provenance rather than rejecting an unlisted version. Actual model, argument, effort and protocol failures still fail. Starter guides distinguish ordinary fixed-effort sessions from an explicit managed-lead trial.

## Validation

The full combined `bash tools/quality-check.sh` gate passed on frozen code `3cac0d87903b4f919d3e29d8728f8dd2f570751c` (recorded 4219.748 seconds; source unchanged). A private installation and all six offline smoke checks passed. The release package records exact source and validation provenance.

Claude Pro / Claude Code 2.1.325 / requested Opus 5.5 XHIGH performed the broad current-code review and a fresh correction-delta review. The delta verdict is APPROVE; its source and report checks exited 0. The existing OpenAI lead assessed scope and risk. The fresh worker review uses the same AI lab as some author work under the owner's low-headroom exception; it is not cross-lab coverage. Effective model and effort remain Unknown. Original failed checks and operational failures remain separate evidence.

The corrected regressions preserve exact Fast/legacy-mode behavior, Bash completion semantics and private-file permission checks. The display fixture now passes under umasks 077 and 022; an unsafe public sidecar still fails closed. A passed process or test alone never establishes delivery or human acceptance.

## Known limits and next patch

- Live Codex interrupt, approval and stale-turn behavior remains unverified; the owned branch was exercised through executable fakes. Effective model and effort remain Unknown without provider evidence.

- Under unusual prolonged control-lock contention, a completed run can return busy. Inspect the recorded state and keep the same request ID; do not blindly create a new request.

- A stopped owner with an unrecoverable proven provider turn refuses replacement. This preserves evidence and ownership; an explicit retirement workflow and clearer recovery guidance are next-patch work.

- Additional stored-wait regression coverage, pending-request ABA generation handling and minor completion/copy improvements are deferred. The read-only four-question onboarding planner is a separate development slice and is not shipped here.

## Guides

[Task preview](TASK-PREVIEW.md), [Managed lead](ADAPTIVE-LEAD-EFFORT.md), [Effort display](LEAD-EFFORT-DISPLAY.md), [Review defaults](ai/LEAD-REVIEW-POLICY.md), [New-user starters](ai/NEW-USER-STARTERS.md).
