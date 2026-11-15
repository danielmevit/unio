### Changed
- Implemented latest-CLI operation policy across worker adapters (`tools/vibe-worker.py` and `tools/antigravity-worker.py`), removing version-number-only refusals in favor of judging actual operations.
- Vibe adapter retains the known 2.26.1 legacy overlay while attempting the modern explicit `--model`/json contract for newer releases without a version-only refusal. Preserved requested-model gating and catalog effort limitations.
- Antigravity adapter keeps the 1.3.5 legacy argv form without generic effort, while modern releases pass explicit selected `--effort`.
- Version query metadata is recorded as provenance; failure of `--version` alone records `Unknown` without blocking an otherwise working operation. Actual unsupported arguments, models, schemas, timeouts, and native failures remain truthful failures with no retry or silent fallback.
- Added regressions covering future versions with modern contracts, unavailable version metadata recording `Unknown`, preserved legacy behavior, and honest error handling. Updated affected tests and documentation, and regenerated embedded adapters in `unio-install.sh`.
