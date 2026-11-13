# Installer accident containment (source refusal + atomic runtime publish)

Scope: the standalone `unio-install.sh` only. This document explains two
deliberate installer behaviors added after sourcing the installer from a
measurement command accidentally overwrote the global runtime
(2026-11-12 incident): inherited `UNIO_CONF_DIR` was isolated but
`UNIO_BIN_DIR`/`UNIO_COMPLETION_DIR` defaulted to the global tool, so a
sourced install ran to completion inside the caller's shell.

## 1. Accidental sourcing is refused before anything happens

`source unio-install.sh` (or `. unio-install.sh`, likewise from a function
or `bash -c`) exits the sourced file with status 1 after printing an
actionable message to stderr. The refusal runs before `set -euo pipefail`
and before any destination variable is used, so:

- No file is created, written or deleted anywhere, including all
  `UNIO_BIN_DIR`/`UNIO_CONF_DIR`/`UNIO_COMPLETION_DIR` destinations,
  which is what an accidental sourced install would have replaced.
- The caller's shell options (`$-`, `set +o` state) are unchanged. Under the
  old installer, sourcing silently applied `set -euo pipefail`, redirects
  and working assumptions to the *caller's* shell.
- The caller keeps running: the sourced file returns 1 and control resumes
  after the `source` command. The installer never calls `exit` on the
  caller's behalf. If the caller itself runs `set -e`, its own errexit
  policy may still abort the caller — that choice belongs to the caller.

Detection relies on `return` being legal only while a file is sourced
(`if (return 0 2>/dev/null); then ... return 1; fi`), not on
`BASH_SOURCE` heuristics, so supported executed installs keep working:

- `bash unio-install.sh` and `./unio-install.sh` (also under `bash -c`),
- a pipe feeding bash's standard input (`curl ... | bash` style), where no
  script path needs to exist,
- any caller strictness: the guard uses `${BASH_SOURCE:-}` defaults and
  never assumes the array is set (an unset or empty `BASH_SOURCE` only
  shortens the "run it instead" hint).

Deliberate limits of the guard:

- It is accident containment, not a same-UID anti-abuse sandbox. A caller
  that `eval "$(cat unio-install.sh)"` pastes the installer into its own
  shell command stream; that is indistinguishable from a piped executed
  install and is out of scope.
- Sourcing under a shell other than bash is unsupported, exactly as before
  (the installer is a bash script; the shebang is authoritative).
- The refusal is not a version check: any `bash unio-install.sh` still
  installs exactly as before, with identical semantics and messages.

## 2. The runtime publishes through one atomic rename

The old writer did `cat > "$BIN_DIR/unio"`, truncating the live runtime in
place. Readers that had the file open (a CLI currently starting up) then
saw a truncated or mixed file, and any mid-write failure left the tool
half-written with a success message already queued.

The runtime is now written into a private staging file inside `BIN_DIR`
(`mktemp -d "$BIN_DIR/.unio-install-stage.XXXXXX"`), chmod'ed, then
published with a single `mv` rename. Consequences, all covered by
`tests/unio-installer-safety.py`:

- An interpreter that already opened the previous runtime keeps reading
  its own complete inode; concurrent or new invocations see either the old
  or the new complete file, never a truncated mix (open-reader and
  in-flight CLI checked across a real replacement).
- A failure before the rename leaves any existing runtime byte-identical
  and mode-identical, prints no `Unio installed` message, and preserves
  the real failure status (checked by bounding the write with `ulimit -f`
  so the failure happens mid-runtime; on the old behavior the same bound
  truncates the live runtime).
- Cleanup is strict: only this invocation's own staging directory is
  removed — by an `EXIT` trap disarmed right after publication. Foreign
  leftover files (a crashed invocation's staging, any unrelated temp) are
  never globbed away.
- A non-regular existing destination (symlink, directory) at
  `BIN_DIR/unio` is refused up front, consistent with the installer's
  existing unsafe-destination preflights. The previous behavior wrote
  *through* a symlinked runtime; if you intentionally manage the runtime
  path with a symlink, remove it first — the installer owns that path as
  a regular file.
- An upgraded runtime keeps its existing mode (`chmod --reference`); a
  fresh install keeps the umask-following mode `cat` + `chmod +x` always
  produced.

What is deliberately *not* claimed:

- No zero-downtime or cross-host update-safety claim of any kind.
- Generated helpers, templates, completion and config installs keep their
  existing in-place `cat >` semantics: they still require idle
  maintenance windows; only the main `unio` runtime publishes atomically.
- The `EXIT` trap covers `set -e` failure paths. A `kill -9` crash can
  still strand one private `.unio-install-stage.*` directory; it is
  invisible to the CLI, harmless to remove, and never cleaned by any
  later install run (no glob cleanup, by contract).
- Runtime command implementation, version, embedded helpers, templates,
  legal content and configuration rules are untouched; all existing
  `UNIO_*` override paths behave as before.

Regression entry point: `python3 -B tests/unio-installer-safety.py`
(registered in `tools/quality-check.sh`).
