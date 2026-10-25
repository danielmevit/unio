Latest-checkpoint lookup validates requested-worker candidates before visiting unrelated body pools, with bounded manifest rechecks and conservative original-scan fallback. An installed 13-save fixture reduces shallow pool metadata checks from 52 to 4 (manifest reads 13 to 27); no full-save timing claim or version change.

Correction note: these original pool/read counts described an unaccepted prototype, not reduced total work; see SAVE-LATEST-LOOKUP-CORRECTION-0525.md and the guide for complete counters, retained failures and new measurements.

Performance counts and timings describe shallow lookup (`deep=False`) only. Deep production-path performance remains unmeasured; the documented small-pool mounted-drive regression remains.
