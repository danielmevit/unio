# Unio 0.5.18 — worker reliability

Unio makes worker activity and results easier to assess while preserving your
existing agent commands and shared-account policy.

- **Live Vibe progress:** fixed operational labels show observed activity, with
  a separate heartbeat when the adapter is alive without a new provider event.
  Raw reasoning, answers, commands and tool payloads stay private.
- **Clear Antigravity outcomes:** the optional agy1.3.5 connector checks both
  the process exit and the structured final result. Exit0 with terminalERROR
  fails the adapter. Oversized tasks are refused before a model call; tasks
  are never clipped to fit.
- **Exact Copilot proposals:** the optional Copilot1.0.95 Auto Balance connector
  extracts assistant text from native JSONL without rich wrapping or manual
  JSON repair. Malformed input, missing completion and conflicting chunk groups
  fail with a fixed outcome; raw output stays private.

All four optional adapters are packaged and discoverable with
`unio integrations --json`. Existing aliases remain intact; enabling an optional
connector is explicit. See [Vibe setup](integrations/MISTRAL-VIBE.md),
[Antigravity setup](integrations/ANTIGRAVITY.md) and
[Copilot setup](integrations/GITHUB-COPILOT.md).

## Evidence and limits

A real Mistral subscription / Vibe2.26.1 / requested GLM5.3 high task delivered
safe progress labels and a liveness heartbeat while running. A later real
Antigravity / agy1.3.5 / requested Gemini3.8Flash high correction used the new
connector and finished with native0, terminalSUCCESS and adapter0.
Copilot JSONL delivery has installed-source and offline fake-CLI evidence;
no live Copilot call through this changed transport is claimed.

Grok subscription / Build1.0.52 / requested Grok4.7 high implemented Copilot
framing and prepared release files. Antigravity/Gemini high corrected three
lead-found decoder cases; six native checks and four independent cases passed.
The AGY component passed seven native checks and three independent cases.
Code acceptance is separate from provider completion and remaining capacity.
Effective model/effort and subscription allowances remain Unknown.

Earlier failures and replacements remain recorded. The separate Mistral/Vibe
save investigation failed with native2/infrastructure_failure; its OpenCode Go
GLM5.3 high replacement timed out with exit124 without a committed report.
Neither establishes quota exhaustion or a performance improvement. That
investigation adds no runtime change to this release.

There were no additional Codex workers or AI review fleet in this batch.
UI, website and brand source are preserved. Final gate, artifacts, upgrade,
installation and official-download results are recorded in the
[development handoff](development/continue-with-ai-prompt.md).
