# Lead handoff — Unio 0.5.20, 2026-10-16

Read the newest project `coord/AGENT-LOG.md`, this guide and
[the release notes](../RELEASE-0.5.20.md). Check GitHub's actual latest release
and `unio version`; a version heading alone does not prove publication.

## Current checkpoint

The field bundle implements shared-lead budget consent, opt-in failed-worker
WIP commits, plain supported adapter outcomes and development/release push
guards. It also documents continued work after status questions, shared-budget
LOW defaults and effort-specific experience tracking. The existing dashboard,
website, brand and the owner's separate projects were preserved.

Runtime and tests `658cbf042063d4508d1bb506d3507f16dc2e43d7` passed the complete
`bash tools/quality-check.sh`: exit 0, 1,542.096s, 2026-10-16 17:00:04–17:26:23
UTC+02:00. Three earlier gates remain recorded as failures. The final LOW
consent-fixture correction changed two tests only; runtime remains identical to
`6740e0d`, independently reviewed by Antigravity / agy 1.4.0 / requested Gemini
3.8 Flash HIGH (APPROVE, adapter 0, native 0). First consent, WIP and outcome
components each have their own independent Google approval and lead inspection.
Perplexity Pro / pinned web adapter 0.16.1 / Kimi 3 Thinking provided supporting
critiques, not formal approval. Failed Mistral/Vibe reviews retain no verdict.

Delivery confirmed on 2026-10-16 at 19:55:48 UTC+02:00: official
[v0.5.20](https://github.com/danielmevit/unio/releases/tag/v0.5.20) is published,
latest and installed from `20e203cdba5692bfe246a8621eb8e207a22d6c49`. The exact
source reached main before publication. Reproducible artifacts, all 40 isolated
selftests, 0.5.19 upgrade/rollback, preserved operator configuration/templates,
installed helper/dashboard identity and all six official download hashes passed.
Earlier tags are unchanged. Installation occurred before publication. The local
save-usage inspection retained exit 2/Unknown for the existing store; installation
did not repair it. Use `unio dashboard ensure --open-browser` for the current URL.

Documentation finalization preserves executable installer bytes outside the
canonical scoreboard guide. Do not repeat the passing broad gate for prose-only
updates. Public delivery confirmation is a later docs commit, not a changed
release tag or rebuilt artifact. Record any new failure separately.

## Owner rules for every continuation

- Use Unio for implementation and review. The lead scopes, coordinates, reviews
  and integrates; delegate code corrections to a dedicated Codex CLI /
  `gpt-6.1-sol` worker through Unio.
- Workers sharing the lead model or subscription start at the lowest supported
  effort (Sol: LOW). The owner gives standing permission for LOW Sol workers
  and necessary continuations; do not ask about their count. Preserve every
  attempt, partial commit and failure. Avoid blind retry loops.
- Raise effort one supported step only after a demonstrated reasoning or
  integration gap. Quota, network and authentication failures do not justify
  higher effort. Frozen calls keep their settings. Max/ultra and paid API
  fallback are not authorized by this default.
- Keep one focused shared-budget worker beside the registered lead. Preserve
  actual account mappings; use a narrow temporary native medium coordination
  tier when needed and restore the prior tier when idle. Coordination tier and
  reasoning effort are separate. Resume for authorized admission, then STOP
  unrelated new work; active jobs finish.
- Answer status questions briefly, then continue authorized work in the same
  turn. Give estimates and proactive progress updates. A progress update is
  not a reason to stop. Preserve jobs, receipts and the exact next step before
  any genuine runtime, capacity, access or information block. Never imply the
  lead keeps working after its turn ends.
- Name subscription route, CLI/version, requested model/effort, task and actual
  state in assignments and results. Status covers the full fleet. Requested
  identity and effort do not prove effective identity or remaining allowance;
  report Unknown when unverified. Record model/effort/task-specific results in
  native `unio experience record/show` and the
  [scoreboard](MODEL-SCOREBOARD.md).
- Opus is reserved for the owner's other projects until explicitly released.
  Grok last reported balance exhaustion; OpenCode Go last reported a usage
  limit. These are dated observations, not current quota readings. Vibe GLM
  and Medium review infrastructure failures are distinct from model quality.
  Copilot Auto Balance does not identify a fixed model or AI lab. Free Zen
  models are workers for routine tasks only and need current free-price proof.
- Keep classified competitor research local. Do not alter owner field reports,
  reveal credentials, overwrite other sessions, or change UI/site/brand scope.

## Next functional work

Delivery is complete. Do not rerun release checks without a new relevant change
or failure. The next functional milestone is continuous delegation; scope a
bounded first implementation before assigning work. Initial estimate: 4–8 hours,
including focused checks and independent review; revise from the scoped contract.
Proceed in bounded bundles:

1. **Continuous delegation:** eligible accounts take separate ready tasks while
   others run; preserve dependencies, admission, consent and review evidence.
2. **Managed interactive sessions:** attach to owned lead/worker CLIs with clear
   live state; support effort changes only at proven supported boundaries.
3. **Lead continuity and phone access:** explicit session handoffs, then scoped
   pairing and messaging to Unio rather than general PC access.
4. **Native Windows, then macOS:** audit host backends and actual host acceptance;
   reuse the existing dashboard. Windows localization follows the
   [language plan](WINDOWS-LOCALIZATION.md): Serbian Latin only, no Montenegrin.

See [the roadmap](ROADMAP.md) and
[release outlook](RELEASE-OUTLOOK-0.5.19-0.5.24.md). Further CodeGraph development
is deferred. Do not expand this release with additional visual redesign or
unrelated features.
