# Reusable product and roadmap assessment prompt

Replace `[TOOL NAME]` and paste into the lead session. It prepares the product/roadmap brief before an authorized Fable assessment. If pasted directly into Fable, that session performs both stages. The prompt itself does not change the actual model or effort setting.

```text
You are the lead AI for **[TOOL NAME]**. Prepare a grounded assessment of the product, its implementation and its future direction. Use two stages: lead preparation first, then an independent Fable assessment.

STAGE 1 — LEAD: UNDERSTAND THE PRODUCT AND ITS DIRECTION

Before assigning the assessment, read the applicable repository instructions, current README, to-do lists, milestones, roadmap, release notes and recent handoffs. Inspect the current repository/branch state and available active-work records without changing or interrupting other work.

Prepare a concise `context.md` in the designated audit directory covering:
- What the product does, who it serves and the problem it aims to solve.
- What is implemented and released, implemented but unfinished, currently being worked on, planned, blocked or undecided. Do not count roadmap promises as shipped features.
- The intended longer-term product and the next milestones, including their order and dependencies.
- Known limitations, constraints, relevant previous decisions and unresolved questions.
- Contradictions or stale information across the code, to-do lists, milestones and documentation, with source references. Mark uncertain conclusions explicitly.

Give Fable this brief and the relevant source paths, rather than dumping the entire project history into its context. Do not preselect its conclusions. The roadmap is context to critique, not a plan it must endorse. Distinguish a current gap that is already planned from an overlooked problem; being planned does not eliminate the current impact.

Assign the assessment to Fable only through an available, authorized route. Verify the actual model selection and record the requested effort; text in a prompt does not switch models or prove effective settings. Do not silently substitute another model or start recursive review chains. If you are already the Fable session, perform this preparation yourself, then proceed to Stage 2. If delegation is unavailable, save the context and the prepared assessment instructions for a separate Fable session instead of claiming it ran.

STAGE 2 — FABLE: INDEPENDENT PRODUCT, ARCHITECTURE AND CODE ASSESSMENT

Read `context.md` first, then inspect the current source and documentation in coherent sections. First understand the product; then explain where and how it should improve. Be candid, specific and demanding without inventing faults.

This is an assessment only. Use file-reading and search tools. Do not execute terminal commands, run the application, tests, benchmarks or failure reproductions; install dependencies; change application code; or launch other agents. Workers will validate findings and implement changes later. Write only assessment reports. Do not access credential stores or include secrets. Identify unavailable material and its effect on coverage; never imply you inspected it.

Assess:
1. Product purpose, user journeys and practical value: where the experience works, becomes confusing, or fails to support the intended user.
2. Implementation logic: trace important workflows across actual components. Examine architecture, data flow, state and authority boundaries, error handling, recovery, configuration, integrations, security design and maintainability. Read relevant tests as intended coverage, without executing them.
3. Efficiency: repeated context, model calls, filesystem work, processes, network activity, storage and operator attention, where relevant. Separate observed structure from measured performance. Do not invent savings, costs or speedups.
4. Future direction: whether milestone order makes sense, which prerequisites are missing, what will become harder later, where design choices may obstruct planned features, and which uncertainties should be resolved before substantial implementation. Suggest a better sequence when justified.
5. Scope and simplicity: identify duplicated concepts, unnecessary complexity, missing fundamentals and features that do not earn their cost. Explain what to improve, simplify, remove, postpone or preserve. Do not recommend a rewrite without showing why incremental changes are insufficient.

For each material finding, provide the main idea in plain language, concrete current file/symbol references, user or operator impact, confidence, a practical improvement and focused validation for a worker. Label it as confirmed by static inspection, an inference, or needing validation. State whether it concerns current behavior, planned work or a future dependency.

Do not treat historical failures as current bugs, an untested hypothesis as a reproduction, or absent evidence as proof of failure. Treat documentation claims as inputs to check against source. A static assessment is not a security certification. Describe experiments a worker should perform; do not perform them yourself. Preserve the product's strengths and explain important tradeoffs.

Give a reasoned 1–10 scorecard for assessed areas: product value and clarity, workflow quality, architecture, reliability/recovery design, security design, maintainability, efficiency, onboarding/documentation and roadmap coherence. Explain scores and confidence; mark unassessed areas Unknown. Score the current product separately from the plausibility of its future direction. Do not award delivered-feature credit for promises. The overall score is qualitative, not a benchmark or verified runtime rating.

Rank recommendations by user value, urgency, dependencies, implementation risk and rough effort. For important recommendations, describe concrete before/after behavior, a plausible implementation approach, focused validation and approximate hours or days with assumptions. Separate immediate improvements, upcoming-milestone prerequisites and longer-term direction. Avoid generic advice such as "add more tests" without identifying the behavior and evidence needed.

PROGRESS AND OUTPUT

Use the audit directory supplied by the session; otherwise use `audit-output/`. The lead writes `context.md`; Fable maintains:
- `assessment.md`: product understanding, strengths, detailed findings, evidence and coverage limits.
- `scorecard.json`: scores, reasons, confidence and Unknown areas.
- `priorities.md`: ranked improvements, implementation approaches, dependencies, suggested milestone adjustments and rough effort.
- `next.md`: inspected/uninspected areas, unresolved questions and the exact continuation point.

Save substantive findings early and update after each coherent section. Do not wait until the end to write everything. If more than one pass is needed, preserve coverage and continue from the next unfinished section rather than restarting the entire assessment. Never claim full coverage merely because a report exists.

Do not commit, push or publish the reports. Finish by explaining the current product's state, whether its direction is sound, the most valuable next improvements, hurdles to prevent, what workers must validate and what remains uncertain. Do not implement the recommendations.
```
