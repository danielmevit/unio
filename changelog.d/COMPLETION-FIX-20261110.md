# COMPLETION-FIX-20261110 — narrow correction to CLI update bash completion

Narrow correction to the CLI update completion handler in `unio-install.sh`.

## Problem
The `cmds` wordlist in the `_unio()` bash completion function erroneously included
`clis` alongside `update`. `clis` is not a top-level Unio command; the top-level
dispatch command is `update` (which dispatches `unio update clis ...`).
`tests/unio-branding.sh` validates that every command offered by top-level
completion matches a valid dispatch target in `unio`, and correctly failed on `clis`.

## Solution
1. Removed `clis` from the top-level `cmds` list in `_unio()` in `unio-install.sh`.
   Top-level completion offers `update` and all real existing commands, with no top-level `clis`.
2. Refined `update` completion in `_unio()` so that `unio update <TAB>` completes
   `clis` at `COMP_CWORD -eq 2`, and `unio update clis <TAB>` completes its flags
   (`--check`, `--json`) and recognized AI CLI route names (`antigravity`, `vibe`,
   `grok`, `copilot`, `opencode`, `claude`, `codex`).
3. Added regression assertions to `tests/unio-branding.sh` and `tests/unio-cli-updates.py`
   verifying that top-level completion includes `update` and excludes `clis`, and that
   nested `unio update clis` completion accurately resolves `clis`, flags, and route names.
4. Preserved byte-identical installer payloads outside the `COMPLETION_EOF` block,
   along with all existing cache, safe update, manual-only, and error-handling policies.
