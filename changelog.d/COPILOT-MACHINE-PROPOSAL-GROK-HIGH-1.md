### Fixed

- Copilot routine proposals now use the installed CLI 1.0.95
  `--output-format json` JSONL transport. Private `native-stdout.jsonl`
  keeps every raw byte. `proposal.md` is only the exact root
  `assistant.message` content, so rich-text wrapping no longer inserts
  physical newlines into JSON patch strings.
- A completion is recorded only when the native process exits 0 and the
  stream has one final `result` with integer exit code 0 plus one
  unambiguous root text completion. Malformed, truncated, duplicate,
  nonfinite, missing or wrong-typed terminal records fail closed.
  Nonzero native exits stay native failures. Auto Balance, stdin prompts,
  provider isolation and Unknown model, effort and allowance are unchanged.
  This transport is in the unreleased 0.5.18 candidate. Evidence here is
  offline only. Three lead-found input/group defects are a separate
  correction and are not accepted.
