# Personal Unio lead and review workflow

Owner-specific preferences; other users may choose their own supported routes.

<!-- UNIO_PERSONAL_REVIEW_WORKFLOW_20261023 -->
## Personal Unio workflow — 2026-10-23T09:55:29+02:00

This owner's standing workflow applies whenever acting as a Unio lead on ANY
project, not only Unio development. It supersedes the older October16 default
of two external worker reviews plus the lead, and any older copied Unio guide
that repeats that count. Default: TWO REVIEWERS TOTAL — one independent worker
reviewer plus the existing lead's final assessment. The lead already reviews;
do not spawn another worker to duplicate that role.

- Codex/OpenAI leads: use Claude subscription / Claude Code / requested
  `claude-opus-5-5` / `xhigh` as the independent final reviewer when eligible.
- Claude/Anthropic leads: use ChatGPT subscription / Codex CLI / requested
  `gpt-6.1-sol` as the independent final reviewer. Use supported high effort,
  escalating to xhigh for demonstrated review complexity; never max/ultra.
- Other known AI labs lead: prefer eligible Opus5.5xhigh or another strong
  reviewer from a different AI lab than the lead. CLI/subscription names do
  not by themselves establish an AI lab; preserve effective Unknowns.

The implementation worker builds and runs meaningful checks. The independent
reviewer inspects the exact current code, then the existing lead checks the diff,
tests and findings, reproduces material issues and accepts or returns corrections.
One external review does not mean only one assessment. Add another external
reviewer only for a concrete unresolved disagreement/coverage gap or owner request.
A stricter current project/CI/human-approval requirement is not waived.

Respect actual shared accounts, the registered lead, owner holds, STOP and low-tier
one-workflow limits. An Opus reviewer sharing a fully reserved Claude lead budget
is not eligible: choose an independent other-lab route instead of faking a group
or spawning another lead-account session. Keep Codex implementation/shared-budget
worker LOW defaults and their narrow consent rules separate from reviewer effort.
Do not alter auth/billing, spend paidAPI fallback tokens, silently downgrade or
retry blindly. Unknown quota is not positive capacity or proof of exhaustion.
Record each requested route/model/effort, CLI/version, real exits, checks and
acceptance separately. Failed calls and acknowledgments are not delivered reviews.
Never transfer an old approval to changed code or average votes over a real defect.

This is lead guidance, not an automatic runtime reviewer selector. Workers finish
only their frozen assignments and do not start recursive reviews or other agents.
Before leading an Unio project, read the current owner policy at
`~/.config/unio/OWNER-WORKFLOW.md`, even if project coordination copies are older.
Apply this workflow at startup/instruction refresh; editing a guide does not
inject instructions into already running foreign sessions.
<!-- /UNIO_PERSONAL_REVIEW_WORKFLOW_20261023 -->
