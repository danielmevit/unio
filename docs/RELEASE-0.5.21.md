# Unio 0.5.21 — bounded continuous delegation

Unreleased candidate. Implementation, checks, independent current-code review,
installation and publication are not complete. Unio 0.5.20 remains stable.

## Scoped first outcome

An opt-in finite batch can keep existing approved, disjoint jobs moving as
account slots free up. This uses the existing planner and dispatcher; task
approval, shared-lead consent and native slot limits stay in effect. Durable
attempt recording prevents automatic replay after interruption or uncertain
startup. Pause and stop close new attempts without killing active workers.

The first contract intentionally binds a fixed inventory and base. Integration,
new instructions and dependent approvals remain explicit. It is not a hands-off
pipeline across changing main revisions. See the
[frozen contract](CONTINUOUS-DELEGATION-CONTRACT.md).

The existing planner/dispatcher availability docs are corrected to describe
shipped functionality. No UI, website or brand redesign is part of this bundle.

## Evidence so far

Mistral subscription / Vibe 2.26.1 / requested GLM 5.3 HIGH returned Source 2
with an infrastructure_failure export after one minute, without implementation
changes. Usage was below its frozen local bounds; this is not a model-quality
or monthly-allowance finding. The original attempt remains preserved.

The replacement is ChatGPT subscription / Codex CLI 0.162.1 / requested
GPT-6.1 Sol LOW, through native Unio with real shared account mapping, a narrow
temporary medium coordination tier and one-use lead-budget consent. Its work
is still unaccepted while running; requested settings do not prove serving
identity or available allowance.

Antigravity / agy 1.4.0 / Gemini 3.8 Flash HIGH returned a committed contract
assessment. Perplexity Pro / pinned web adapter 0.16.1 / Kimi 3 Thinking returned
a supporting critique. Neither is an independent review of implemented code.
Claims are checked separately by the lead, including asynchronous native
admission and cross-inventory scope limits. A Copilot Free / CLI 1.0.95 /
Auto Balance docs attempt stopped at a private version-pin check before any
model call; the lead handled the small prose correction without a retry.

Final release evidence will record actual code revisions, meaningful checks,
review findings, the complete gate, installation and official download hashes.
