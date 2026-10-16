# Unio 0.5.20 — protect budgets, work and publication

Code and independent review accepted; complete release gate and delivery pending.
This candidate combines four field improvements and persistent lead guidance.

## Changes

- **Protect the lead's subscription.** One-use owner consent is required before
  native workers or reviewers spend the registered lead's declared shared
  account. Grants expire after15 minutes and bind the exact task and route.
  They do not create allowance or raise concurrency. [Usage and limits](development/LEAD-BUDGET-CONSENT.md).
- **Preserve eligible failed work.** Opt-in WIP commits run after confirmed
  provider cleanup, with normal Git hooks and literal task scope. Source remains
  failed and the work remains unaccepted. Dirty initial states, unsafe files
  and unsupported Git states refuse. Power loss cannot guarantee a final
  commit. [Work preservation](WORK-WIP.md).
- **Explain supported worker stops.** Canonical adapters provide bounded, typed
  plain outcome observations. Missing, stale, malformed or generic-wrapper
  evidence stays Unknown; real exits, budgets and acceptance are unchanged.
  [Outcome boundaries](WORKER-OUTCOMES.md).
- **Separate development and release pushes.** Opt-in remote policy pins
  destinations and validates release refs, source aliases and tag ancestry
  before ordinary Git publication. main is the default independently of the
  development work base; explicit owner rules remain. Canonical embedded guard
  code supports standalone engines and thin configuration overrides, forwards
  Git ref input and preserves owner hooks/worker guards. [Remote policy](REMOTE-POLICY.md).
- **Keep leads economical and moving.** Answer status questions and continue
  authorized work in the same turn. Workers sharing the lead's model or
  subscription start at the lowest supported effort; escalate gradually from
  results. The existing experience store and updated scoreboard distinguish
  route, model, effort and task type. [Lead guidance](development/LEAD-ROUTING.md),
  [effort-specific results](development/MODEL-SCOREBOARD.md).

## Evidence and limits

ChatGPT/CodexCLI0.162.1/GPT-6.1 Sol low completed consent02bfcac, WIP9c4dba0
and outcomes0977d38. Each passed six native checks, a separate Antigravity/
agy1.4.0/Gemini3.8Flash high APPROVE/adapter0 and lead inspection. Mistral/
Vibe2.26.1 GLM5.3 high and MistralMedium3.5 high reviews failed infrastructure
without verdicts; their collection remains incomplete.

Original Gemini remote3cda4ad finished Source0/native6PASS, but lead inspection
reproduced credential, conflicting-role and typed-policy failures. That original
code is not accepted. Sol high stopped at a real usage limit, with test edits
preserved. Authorized Sol low98d6c61 corrected guard behavior; its native6/7
result retains an invalid operator-supplied test path as failure, while the
actual35-case guard suite passed separately. It also introduced the external
helper dependency that subsequent integration checks exposed.

Sol lowc48c5f0 repaired selftest,0f4ee4f corrected the development-base-derived
release default and6e06dcd registered tests. A first full gate failed at selftest;
a second failed in the unchanged review-receipts suite on thin profiles. Neither
is relabeled as passed. Sol medium6740e0d corrected initialization generally,
finished Source0 and passed six native commands, including the unchanged9-case
review-receipts suite, new installed/standalone thin-profile cases,48 remote
functional cases and60 regressions. It preserves the40 selftest assertions.

Fresh Antigravity/agy1.4.0/Gemini3.8Flash high review of6740e0d returned
APPROVE/adapter0/native0. The private review mirror has Source not_run; its
identity checks reuse the actual original Source/native evidence without
claiming repeated functional tests. The lead inspected code and assessment.
PerplexityPro/pinnedadapter0.16.1/Kimi3Thinking supplied two selected-context
critiques; corroborated findings, unsupported claims and future suggestions
are qualified separately. They are not formal native approvals. CopilotFree/
CLI1.0.95/AutoBalance supplied a docs proposal and genuine live compatibility
follow-up for0.5.19; serving model and AI lab remain Unknown.

Windows-mounted selftest timing failures (38/40) remain preserved alongside
unchanged private-tmpfs40/40 passes. Controlled fixtures do not establish a
latency guarantee on every host. Requested model/effort are not verified serving
identity or per-task quota; no general token savings or model ranking is claimed.
Hooks and local state are trusted-host controls, not a sandbox or authentication
against hostile same-user rewriting. Removing markers/hooks or --no-verify
can bypass host controls. core.hooksPath and automatic remote import remain
unsupported; import and configurable Vibe caps are follow-up work.

Release provenance records the exact final source, complete-gate identity,
reproducible artifacts, installation/upgrade checks and official download hashes.
The candidate must pass its final full gate and install before publication.
