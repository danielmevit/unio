# Quick onboarding — design proposal, next slice

Not implemented or shipped. Finish the current automatic-effort/CLI-policy batch first; onboarding is the next functional slice. Owner wants a short guided setup instead of making a beginner understand every policy first.

Question order and wording:
1. Which AI subscriptions or tools will you use?
2. Which AI should lead? Offer a choice or a recommendation after the goal is known.
3. What do you want to build or improve?
4. How would you prefer to work?

Question4 descriptions come before mode labels:
- Build quickly — Fast: test the essentials and accept more follow-up fixes; good for prototypes/early experiments.
- Keep a balance — Balanced: steady progress, check important interactions and review meaningful changes.
- Check thoroughly — Thorough: smaller steps, broader tests and careful risk review; good for sensitive changes.

All modes retain meaningful checks, required project approvals and account controls. This changes pace/verification scope, not model reasoning effort or coordination tier. Preserve an existing project's choices; new projects may default Balanced/conservative budget. This owner's ongoing development retains its existing Fast/low preferences.

The result should preview a sensible workflow: real detected/declared CLI routes and shared subscription groups, chosen capable lead, one workflow per actual account by default (including lead), suitable workers, one independent external review plus existing lead, supported lead-effort controls and a copyable starter prompt. A subscription count does not prove AI lab diversity or independent budgets. Free worker-only routes cannot become lead. Preserve Unknown capacity/auth/effective identity; no credential collection, paid API fallback, invented quota, silent account remapping or automatic provider probes.

For one subscription, default one workflow/sequential handoff; a lead plus one shared-budget worker is an explicit optional exception with real mapping, native grant and narrow temporary tier, never extra allowance. Ask that follow-up only if relevant. Let the user inspect/edit the derived setup instead of asking everyone a long form. Advanced effort/concurrency choices can be adjusted later.

The first managed AUTO LOW/XHIGH backend is Codex app-server. Other leads retain supported fixed effort; onboarding cannot adopt or reconfigure an existing unmanaged TUI by prose. Explicit owner transition/handoff remains necessary. Use latest installed CLI and record version; react to actual operation failures, not an arbitrary version allowlist.

Proposed first surface is a CLI guided command, name not yet frozen, whose answers can also be supplied noninteractively for an AI lead. Start with a read-only plan/starter prompt and an explicit reviewed apply to existing native settings. Applying must preserve busy-state locks, owner holds/STOP/account mapping and fail honestly without partial misleading setup. No new dashboard or separate orchestrator. Reuse the resulting configuration later in desktop onboarding.

Opus review must assess brevity, defaults, conditional questions, real native feasibility and gaps, separately from runtime code acceptance. This proposal is not a release blocker for the already-implemented reliability batch; design findings inform the next scoped implementation.
