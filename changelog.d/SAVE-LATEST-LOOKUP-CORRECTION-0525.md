Correct latest-lookup fallback refusal propagation and use untrusted raw manifest hints with full selected-save validation. Complete file-operation counters expose the one-save overhead (26 → 44 calls), 13-save reduction (339 → 286 calls) and measured small-pool D: slowdown; retained interleaved D:/private-tmpfs measurements, fast-path/race regressions and limitations are documented in the guide. Original prototype evidence and provider-limit failure remain preserved; independent review and lead acceptance are pending.

Performance counts and timings describe shallow lookup (`deep=False`) only. Deep production-path performance remains unmeasured; the documented small-pool mounted-drive regression remains.

Current disposition, 2026-10-26T00:54:14+01:00: final component review by Claude Code 2.1.310 /
Opus 5.5 XHIGH and the existing lead assessment passed; privately accepted.
Earlier pending wording records task-delivery state. The assembled gate and
public delivery remain separate; see docs/RELEASE-0.5.25.md.
