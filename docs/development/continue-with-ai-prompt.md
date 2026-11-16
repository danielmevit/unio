# Unio release checkpoint — 2026-11-16

The public installed release is 0.5.32. Candidate 0.5.33 combines focused validation lanes/timings and experimental existing-conversation lead controls. Functional implementation: `729734befb30df5bcfa59564766fdaee76b8eede`. This release layer changes the version declaration and release Markdown only. Preserve the same native conversation; restarting alone does not activate adaptive control.

Current implementation checks: focused connector checks and native verification passed, plus the validation runner's 71 assertions. The existing lead independently reproduced seven repaired behaviours with fake transports. The final cumulative independent review is pending, followed by lead assessment, one exact-candidate full gate and private/global installation checks. No candidate publication is implied. The installer embeds the managed lead modules; run `python3 -B tools/embed-managed-lead.py --check` after relevant changes.

The first existing-session slice selects future-turn effort from explicit phase signals. Live setting acceptance, mid-turn effort changes, autonomous phase classification and worker watching remain separate follow-ups. Keep requested/effective Unknowns, original failures, actual provider routes and exact review material. Older private launch failures are operational evidence, not adverse model-quality results. Copilot's current stock adapter compatibility is a known follow-up; per-run trials do not repair the public adapter.

Earlier checkpoint follows unchanged.

# Continue Unio development

Read AGENTS.md, the newest enclosing coord/AGENT-LOG.md when available, and the current personal OWNER-WORKFLOW.md before planning. Check actual local/remote Git state, installed version, active runs, account mappings, owner holds and fresh capacity observations. This handoff or a version string never proves publication, installation or remaining allowance.

## Delivered scope

The 0.5.32 patch fixes the first real turn in the opt-in managed Codex lead and preserves a genuinely completed outcome when post-completion waiting cleanup cannot obtain its lock. It adds no new commands. See [release evidence, upgrade instructions and limits](../RELEASE-0.5.32.md). The 0.5.31 foundations remain: task-scope preview, current CLI operation policy, Fast/Balanced/Thorough, effort-first status, explicit LOW/XHIGH turn controls, safer recovery and durable review defaults.

The managed lead is an experimental, explicit per-turn controller. It neither adopts the current unmanaged TUI nor provides an autonomous project scheduler. Current requested effort, next-turn choices, selection policy, coordination tier, actual delivery and effective Unknowns stay separate. A new managed thread needs its own goal, turn files and a short handoff.

## How to continue

Use the shipped [review defaults](../ai/LEAD-REVIEW-POLICY.md), [lead routing](LEAD-ROUTING.md), model-effort and experience guides, plus current project/owner overrides. Delegate focused source changes through Unio in isolated worker worktrees. Preserve original attempts and required artifacts; record route/subscription, CLI/version, requested model/effort, actual exits, checks, corrections and acceptance. Task/model/effort evidence guides selection; it is not a universal ranking. Record final experience before advancing the task's base. Keep actual account mappings, lead reservation, STOP and owner holds. Reasoning effort and coordination tier are different settings. No paid fallback or authentication/billing changes.

When no .codegraph directory exists, use normal project search and do not index automatically. Keep source and scratch in the enclosing workspace, quote paths, use host date timestamps, update coordination records and preserve checkpoints. Explain the practical feature goal and concrete current work in status answers, then continue authorized work. A completed version is a checkpoint when further milestones are authorized.

## Next functional work

1. Finish review and integration of the separate read-only onboarding planner. It covers tools/subscriptions, lead, goal and preferred pace; preserves existing settings; shows a plan before changes; and distinguishes account budgets from AI labs. It must not invent active effort or capabilities. This planner is not shipped by 0.5.32.
2. Correct the remaining display-only stale waiting flag after completion-cleanup contention followed by worker registration. Preserve completed outcomes and idempotency. Improve the shorter managed guide's legacy-state upgrade/rollback wording: the next control write adds the lifecycle field; there is no automatic reverse migration. Preserve newer records before any idle, reconciled restoration of a pre-upgrade managed-state backup.
3. Design explicit evidence-preserving retirement of an unrecoverable managed session, pending-effort generation/ABA handling and measured operating costs. Interrupted native first-turn persistence, approval handling and stale recovery remain unverified. Ownership/dashboard control, native Windows and later macOS/phone follow functional reliability priorities. Preserve the existing version plan and private research boundary.

Keep original failed gates, stale reviews and operational mistakes distinct from code quality. The release-prep author's original scope verification failed because the lead omitted inherited paths; four Validate checks passed, and a separately tracked local verifier provided the corrected scope/delta gate. The original failure was not rewritten. A preexisting malformed ledger row remains preserved; do not delete it or weaken freshness checks to force another task through.

## Validation checkpoint

Fresh-context Claude Pro / Claude Code 2.1.325 / requested Opus 5.5 XHIGH reviewed the functional and release-only deltas, then the existing OpenAI lead assessed them. Both worker reviews used the authors' AI lab under the owner-authorized higher-effort fallback; they do not provide cross-lab worker coverage. No blocking findings remained; known minor limits are in the release notes.

Three actual ChatGPT-subscription / Codex CLI 0.169.0 / requested gpt-6.1-sol requests completed LOW/XHIGH/LOW across two managed sessions. The lead harness misread the first correctly completed streamed reply and stopped that session. The remaining XHIGH and LOW ran on one thread. There were exactly three completed native turns and no bootstrap; a full single-thread LOW/XHIGH/LOW is only fixture-tested. Effective identity/effort remain Unknown.

The one full `bash tools/quality-check.sh` gate passed on frozen `5ebd9c5a8ada966fa8d943436d73477e67adce49` with tracked source unchanged and no provider calls, finishing 2026-11-16T12:59:39+01:00 after 3968.312 seconds. Private installation and all six offline checks passed. Later release preparation changes only this handoff, the changelog and release notes; runtime/installer/tests stay byte-identical. Official assets and the actual installed binary remain the authority for delivery identity.
