# Test scratch portability correction (2026-11-13)

Remove machine-specific author profile scratch directory preference from `tests/unio-index-lock.py`.

### Background
In `tests/unio-index-lock.py`, `get_scratch_base()` hardcoded an author-machine directory (`/mnt/d/.../index-lock-gemini-medium-20261113/fixtures`) and prioritized it before `UNIO_TEST_SCRATCH` and `TMPDIR`. When running across different environments, worker profiles, or on systems where that path did not exist or belonged to a previous run, scratch fixtures either leaked into foreign directories or failed to honor caller-configured isolation.

### Changes
- Removed the hardcoded owner-machine absolute path completely from `tests/unio-index-lock.py` `get_scratch_base()`.
- Preserved existing `UNIO_TEST_SCRATCH` environment variable preference when set to a valid directory.
- Preserved standard `tempfile` `TMPDIR` and system default placement when `UNIO_TEST_SCRATCH` is unset or invalid.
- Added offline regression test covering explicit `UNIO_TEST_SCRATCH` selection, rejection of foreign directories, standard `TMPDIR` placement, and deliberate invalid-input fallback.
- Kept all six live-writer, lock-type, and control tests untouched and green.
