# Installer accident containment (2026-11-13)

Sourcing `unio-install.sh` from a measurement command (2026-11-12 incident)
overwrote the global runtime in place: the inherited `UNIO_CONF_DIR` was
isolated, but `UNIO_BIN_DIR`/`UNIO_COMPLETION_DIR` defaulted to the global
tool and the sourced install ran to completion inside the caller's shell.

## Changes

- `unio-install.sh` refuses accidental sourcing (`source`, `.`, from a
  function or `bash -c`) before any filesystem write and before
  `set -euo pipefail` is applied to the caller. Refused callers get a
  nonzero status, an actionable "run it instead" message, and keep their
  shell. Executed installs, piped-stdin installs and strict callers with
  unset `BASH_SOURCE` are unaffected; detection relies on `return`
  legality, not on script-path heuristics.
- The main runtime publishes through a private same-directory staging file
  plus one atomic rename. Open readers and in-flight CLIs keep a complete
  old inode across replacement; new invocations only ever see a complete
  file. Failure before publication leaves the existing runtime
  byte-identical and mode-identical with no success message; only this
  invocation's own staging path is cleaned, never foreign files. A
  non-regular destination (symlink/directory) is refused up front.
- Runtime engine body, embedded helpers, templates, legal content,
  configuration rules and every `UNIO_*` override path are untouched;
  generated markers (`UNIO_BIN_EOF` and embeds) are unchanged.
- New regressions: `tests/unio-installer-safety.py` (offline private
  fixtures; every invocation, including refused sourcing, gets explicit
  `UNIO_BIN_DIR`/`UNIO_CONF_DIR`/`UNIO_COMPLETION_DIR`), registered once in
  `tools/quality-check.sh`.
- Docs: `docs/development/INSTALLER-SAFETY.md` records the semantics and
  the deliberate limits (accident containment, not a same-UID sandbox; no
  zero-downtime claim; generated helpers/config keep in-place semantics).

Old-baseline evidence: the new suite fails safely against the pre-change
installer in a private fixture (8 failures + 1 error: fullscreen sourced
install with caller shell-state change, in-flight reader breakage,
mid-write failure truncating the live runtime), and passes 6/6 against the
new installer.
