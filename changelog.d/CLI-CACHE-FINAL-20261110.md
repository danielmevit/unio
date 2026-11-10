# CLI-CACHE-FINAL-20261110 — pinned-fd temporary file lifecycle: elimination of parent-swap write/cleanup race

Bounded correction to the safe CLI-version check and awareness slice
(following external lead review on base 9e6f8b31).

`save_cache` now implements a consistent pinned-fd temporary-file lifecycle
confined to the already-validated directory fd (`_open_state_dir`):
- Chooses an unpredictable safe relative basename (`.cache-<16 hex chars>.tmp`)
  via `secrets.token_hex(8)` with a bounded collision loop.
- Creates and opens the temporary file using
  `os.open(basename, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600, dir_fd=directory_fd)`.
- Writes and fsyncs the JSON payload directly through the opened descriptor.
- Atomically replaces the file into `cache.json` using
  `os.replace(basename, 'cache.json', src_dir_fd=directory_fd, dst_dir_fd=directory_fd)`
  against that same pinned directory descriptor.
- Cleans up incomplete temporary files in `finally:` exclusively by
  relative basename and `dir_fd=directory_fd` (`os.unlink(tmp_name, dir_fd=directory_fd)`).

This resolves the confirmed defect where `save_cache` pinned the state
directory fd but called `tempfile.mkstemp(dir=str(directory))` and
subsequent `os.unlink(tmp_name)` by pathname: under a race swapping the
state directory for a symlink pointing to an outside directory after fd
pinning, `mkstemp` followed the path and wrote a temporary file outside the
pinned state directory (even though the final rename failed), and path-based
cleanup unlinked outside the pinned state. With the pinned-fd lifecycle,
the directory pathname is never reopened or resolved for temporary file
creation, write, or unlink; outside directories and sentinels remain
completely untouched.

Offline regressions in `tests/unio-cli-updates.py` prove:
1. Swapping the state directory after fd pin before temp creation creates
   and replaces the cache file within the pinned directory while leaving
   outside directories and sentinels untouched.
2. Swapping the state directory after fd pin before temp creation and
   before cleanup cleanly unlinks the temporary file from the pinned
   directory via `dir_fd` without touching outside directories or sentinels.
3. Swapping the state directory after temp creation before cleanup unlinks
   from the pinned directory via `dir_fd` without touching outside directories.

All earlier safety contracts, refusals (`maintenance_not_implemented`),
honest Unknown facts, strict shape/bytes/depth/fifo checks, and no updater
execution policies are strictly preserved.
