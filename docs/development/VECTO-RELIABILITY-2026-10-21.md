Recorded 2026-10-21T19:44:10+02:00

# Vecto field dispositions — Unio 0.5.23 candidate

Evidence window: Oct19–21, multiple versions. Raw Vecto files stay private and read-only. No provider failures are silently attributed to0.5.22. This is an initial disposition, not a completed fix or review.

| Finding | Disposition before implementation | Evidence and intended treatment |
| --- | --- | --- |
| Five-second admission deadline | Confirmed in installed/main0.5.22 source | policy_admit_hold hardcodes5s. VEC67 shows failure before provider launch. Filesystem causal root not isolated; configurable bounded deadline and phase diagnostics, no retry. |
| /mnt/d helper slowness | Confirmed symptoms; causal explanation uncertain | Prior Unio automatic saves also exceeded60s. Inventory each helper, preserve bounded failure and original work. No blanket timeout inflation. |
| Canonical result versus review-set receipts | Reproduced in a new owned0.5.22 fixture | Two current mock approvals, zero stale receipts, reviews decision all_recorded_approved; canonical review not_run. This is new synthetic evidence, not replayed Vecto approval. |
| Missing structured findings versus valid verdict | Confirmed distinct states | Historical VEC69 had2current verdict approvals but one missing findings block. Keep verdict, freshness, extraction completeness, expected reviewers and lead/human acceptance separate. |
| Old Vecto approvals currentlystale | Confirmed current evidence | All4 currentlystale after base advance. Never promote historical approvals to fresh evidence. |
| Exit0 acknowledgement without required report | Confirmed field failure; declaration enhancement needed | GPTOSS report absent despite Source0; not accepted. Current report-only captures nonempty stdout but cannot infer narrative semantic delivery. Add explicit bounded required-artifact validation; preserve actual Source/adapter/timeout/limit independently. |
| Legacyexec medium startup | Not a defect | Explicit command construction selectedmedium. Live worker-effort unsupported is a route capability, not evidence startup selection failed. |
| Effort/tier/live/effective ambiguity | Enhancement | Requested startup, supported live controls, pending next turn and effectiveUnknown must remain distinct. Tier controls slots, not reasoning. |
| Ignored analysis/asset work versus empty_work | Expected implementation behavior; enhancement | Native implementation gate correctly refused no committed change. Explicit analysis/asset contract + bounded opt-in preservation needed; never blanket ignored-file capture. |
| Review omitted enclosing code | Confirmed historical context gap; enhancement |3-line diff caused a false finding; context200 changed material and fresh blind batch approved unchanged product. Add explicit bounded context with exact hash; no silent clipping. |
| Cross-workspace account visibility | Known limitation; enhancement | Native slots are project-local; retain truthful visibility, no invented global enforcement. |
| Model history names | Enhancement | Preserve exact strings and normalize family separately; AutoBalance does not identify lab/model. |
| Streaming/quota/CADquality | Separate operational/product evidence | Effort escalation is not infrastructure repair. Source0 not quality or acceptance; no universal model ranking. |
| Historical tail/scope/report-only issues | Already addressed in0.5.22; no fresh regression established | Reuse current tests and reproduce before changing; do not redo shipped fixes from old events. |

## Prioritized work

P1A bounded admission configuration and diagnostic phases, safety regressions. P1B consistent revision/material-bound review observation, with historical verdicts retained and separate extraction/acceptance. P1C explicit required-delivery evidence and missing report classification. Separate focused tasks/commits; two independent current-code lab reviews then lead assessment and full coherent quality gate. No push-main/release authority.

Follow-up after P1: helper-specific measured deadline improvements; explicit analysis/asset contract and bounded artifact preservation; explicit review context; effort capability clarity; account visibility and model family normalization. Windows/macOS/phone and new UI stay later.

Private baseline-review.json records new exact-revision mock reproduction. No real provider calls were made by the reproducer.

## Current local startup observation

2026-10-21T19:49:11+02:00: native workflow admitted, result-start helper spent time in Windows-mount I/O; automatic baseline save then exceeded configured60s and retained previous save. Actual provider receipt absent at observation. The five-second handshake is not the whole startup path. A larger handshake budget alone is not claimed to fix save/result/helper latency or prove a filesystem root cause.

## Checked admission candidate

P1A implementation at a4ca22f is staged on the private integration branch, pending the final current-code lab reviews and combined gate. Source0/native0; native scopeOK and3/3checks passed. Installed admission36cases, existing lead-budget52cases and policy-guard36cases passed. Earlier test failures and automatic-save failures are retained privately. Exact new delta is five assigned files; no main push/global install/release.

The helper inventory in [admission deadlines](ADMISSION-DEADLINES.md) identifies a separate high-priority follow-up: native result/snapshot Git work has no enclosing deadline, and experience recording observes native result for a fixed30seconds. Save capture already has a1..300-second option. The admission fix does not promise to resolve these other latency paths or establish their filesystem root cause.

## Prioritized follow-up backlog

These are estimates for separate scoped work with regression checks and reviews, not new healthy-worker time limits. Refresh estimates from actual implementation evidence. No deferred feature is claimed shipped.

1. Native result/Git/metadata deadlines and experience observation configuration:4–8hours for a first bounded slice. Measure the real Windows-drive path; preserve atomic results, original exits and Unknown on incomplete observation. The current review projection adds metadata reads, so slow-storage cost needs an explicit check rather than a constant-runtime claim.
2. Adopt the additive current-review observation in remaining status/dashboard consumers:2–4hours. Preserve the legacy record for readers that need history; this is functional status plumbing, not visual redesign.
3. Effort capability reason codes and startup/live/pending/effective separation:2–4hours. Retain successful legacyexec medium construction and keep coordination tier separate.
4. Explicit analysis/asset types and bounded opt-in binary/ignored artifact preservation:1–2working days. The P1 text-delivery contract is a foundation only; retain strict implementation commits/no-op gate and never globally include ignored folders.
5. Explicit bounded review context/enclosing code with exact material hashes:4–8hours. Never silently truncate or treat old review material as current.
6. Cross-workspace visibility and model-history family normalization:1–2working days for an honest first slice. Keep exact requested strings/CLI/revision/task/effort and model-family keys separate; no automatic global-account visibility claim.

After the reliability foundation: full managed lead-session ownership/continuity, session-scoped phone access, nativeWindows, then macOS. Version numbers in [the version plan](../VERSION-PLAN.md) are provisional: reliability now occupies0.5.23, so full session ownership is planned before phone access rather than silently skipped. Windows retains app-managed trial expiry, localization and selected Eqho logic as later bounded requirements. CodeGraph extension, competitor strategy and decorative UI work are outside this round.

## Checked review-coherence checkpoint

The committed review change54beed5 passed a fresh native verification on
2026-10-22: scopeOK, five required checks passed (syntax, coherence, collections,
receipts and findings). This validates saved code, not the original provider run.
The CodexCLI0.163.0 / GPT6.1SolLOW Source exited1 at its usage limit after committing
the change; the original Source/native failure is retained. Current requests for
changes remain blocking even when a collection is incomplete. Result/handoff add
`review_current` while preserving the legacy review record and stale history.
Configuration currentness, verdicts, findings completeness, readiness and acceptance
remain distinct; complete readiness requires current configuration evidence.

The required-delivery enhancement is still in progress. Its first
Mistral/Vibe2.26.1/GLM5.3HIGH invocation exited2 infrastructure_failure after8975
reported tokens, below its12M cap, without edits. A bounded Medium3.5HIGH
replacement is a separate invocation, not a rewritten success or effort escalation.
Final current-code independent reviews and the full candidate gate are pending.

## Required-delivery draft validation, Oct22

The AGY1.4.4 / Gemini3.8FlashHIGH continuation saved23bb459 before a terminal503ERROR. Native CLI0, strict adapter/Source2 and enclosing runner1 remain separate original facts. No completed feature or accepted provider result is claimed. Independent installed zero-provider probes reproduced an engine-generated prompt counting as delivery, ignored binding/prompt tampering and a nested ancestor-symlink read beyond the artifact directory. Missing declared output also retained validationPASS while delivery was incomplete. A focused CodexCLI0.163.0 / SolLOW correction is now separately scoped/admitted, pending actual Source/checks, final independent current-code reviews and combined full gate. The lead has not repaired product source inline.

## Required-delivery correction checkpoint, Oct23

A dedicated existing ChatGPT subscription / CodexCLI0.163.0 / GPT6.1SolLOW
worker completed and committed3b56061, Source0 and enclosing native0. It corrected
reserved engine artifact names, immutable run/task/command metadata, ancestor
symlink handling, changed evidence, validation preflight and safe bounded handoff
copies. Effective identity/effort remains Unknown; these requested settings are
not provider attestation. Earlier Mistral and Gemini failures remain failures.

Fresh native verification passed all eight declared commands and scope38patterns,
but overall exited2 INCOMPLETE because a sanitized child test environment
generated Python bytecode in the checkout. That receipt remains unchanged. A
separate dedicated LOW compatibility correction now covers the fixture environment,
the confirmed legacy manual-verification regression and complete readiness mocks.
Verdict-only approvals remain visible without conferring review completeness.
No final current-code lab approval, complete candidate gate, main push, global
installation or publication is claimed at this checkpoint.
