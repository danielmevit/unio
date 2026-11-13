# Installer publication correction (2026-11-13)

Independent fault injection against the accident-safety state of
`unio-install.sh` (commit 5708aaa) found three gaps not covered by the
2026-11-13 accident-safety change. All three are corrected here with
minimal, surgical edits.

## Changes

- Publication is now target-directory strict: the staged runtime is
  published with `mv -f --no-target-directory` instead of
  `mv -f`. If `BIN_DIR/unio` is swapped to a directory between the
  destination preflight and the publication (race or sabotage), the rename
  now fails — nonzero status, no success message, this run's own staging
  directory still cleaned, the directory's foreign contents untouched and
  the runtime never nested inside it — instead of GNU mv silently moving
  the file into the directory and the installer printing success. A symlink
  destination is replaced as its own entry, never followed into another
  directory.
- The sourced-refusal rerun hint is printed with `printf %q` instead of an
  unquoted variable expansion, so a script path containing spaces stays a
  single argument; the printed command re-tokenizes to exactly
  `bash <script path>` and is directly actionable.
- The sourced-refusal guard writes no shell variables at all: it no longer
  assigns `unio_source_hint`, so a caller's pre-existing `unio_source_hint`
  keeps its value (and the guard no longer breaks under
  `readonly unio_source_hint`).
- New regressions in `tests/unio-installer-safety.py` (all offline, private
  fixtures, explicit `UNIO_BIN_DIR`/`UNIO_CONF_DIR`/`UNIO_COMPLETION_DIR`
  on every invocation): a private PATH-shim fault injection swapping the
  publication destination to a directory immediately before the rename; a
  path-with-spaces tokenization test that also runs the printed hint
  verbatim end to end; and a caller-variable sentinel proving the refusal
  clobbers nothing.

NOT changed by this correction: the runtime engine body (the
`UNIO_BIN_EOF` heredoc), the embedded browser/lead-cooldown helpers,
templates, completion and legal content; all `UNIO_*` override paths; and
the earlier accident-safety guarantees, with all 6 of its regressions
kept green and behavior-identical in `tests/unio-installer-safety.py`.
