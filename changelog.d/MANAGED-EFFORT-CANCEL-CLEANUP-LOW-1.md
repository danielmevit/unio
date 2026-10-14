### Fixed
- Make managed Codex Source cancellation idempotent: repeated native/timeout signals cannot raise again during entry into owned channel and provider cleanup; retain the first signal exit code and exact native slot accounting.
- Add an installed-helper regression that delivers repeated TERM/INT at cleanup entry, retaining native cancellation, timeout and replacement-refusal smoke checks.
- Correct the worker-effort guide: local initialization ensures workspace discovery before account mapping; initialization was not shown to reset mappings. Re-embed helper and guide.
