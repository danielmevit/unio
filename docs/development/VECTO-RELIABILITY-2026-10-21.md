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
