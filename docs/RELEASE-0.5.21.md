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
temporary medium coordination tier and one-use lead-budget consent. Initial scheduler `35f1260` finished Source 0 in 29m17s and passed all five
native checks. Lead inspection then reproduced an ownership-ordering defect in
bounded observer cleanup. A separate LOW correction is preserving the original
candidate and addressing that concrete gap; final acceptance remains pending.
Requested settings do not prove serving identity or available allowance.

Antigravity / agy 1.4.0 / Gemini 3.8 Flash HIGH returned a committed contract
assessment. Perplexity Pro / pinned web adapter 0.16.1 / Kimi 3 Thinking returned
a supporting critique. Neither is an independent review of implemented code.
Claims are checked separately by the lead, including asynchronous native
admission and cross-inventory scope limits. A Copilot Free / CLI 1.0.95 /
Auto Balance docs attempt stopped at a private version-pin check before any
model call; the lead handled the small prose correction without a retry.

The first Gemini implementation review wrote APPROVE with adapter exit 0,
but a lead diagnostic generated an untracked Python cache while the candidate
was frozen: native review returned 2, and the subsequent OpenCode Go review
refused before any model call. The cache is preserved privately, source bytes
are unchanged, and neither native result is rewritten as success. The Gemini
review also had inaccurate source anchors and missed the cleanup gap.

The corrected candidate must pass fresh native checks and two independent
blind current-code reviews from different AI labs, followed by lead assessment.
A new parallel review set is prepared for Antigravity / Gemini HIGH and
OpenCode Go / OpenCode 1.18.35 / GLM 5.3 HIGH; it has not yet been invoked.
Final evidence will record actual code revisions, the complete gate,
installation and official download hashes.
