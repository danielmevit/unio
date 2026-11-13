# Startup test scratch portability correction (2026-11-13)

Remove machine-specific author profile scratch directory preference from `tests/unio-startup-refusal.py`.

### Background
In `tests/unio-startup-refusal.py`, `get_scratch_base()` hardcoded an author-profile fixture path (`/mnt/d/.../startup-refusal-mistral-glm-high-20261113/fixtures`) and called `mkdir(parents=True, exist_ok=True)` on it before checking `UNIO_TEST_SCRATCH` or `TMPDIR`. When running across different environments, worker profiles, or gate runners, scratch fixtures either leaked into foreign directories, bypassed caller-isolated fixture directories, or failed to honor caller-configured isolation.

### Changes
- Removed the hardcoded owner-machine absolute path and directory creation entirely from `tests/unio-startup-refusal.py` `get_scratch_base()`.
- Preserved existing `UNIO_TEST_SCRATCH` environment variable preference when set to a valid directory.
- Preserved standard `tempfile` `TMPDIR` and system default placement when `UNIO_TEST_SCRATCH` is unset or invalid.
- Added standard copyright/SPDX header to `tests/unio-startup-refusal.py`.
- Added offline regression test covering explicit `UNIO_TEST_SCRATCH` selection, rejection of unconfigured/foreign paths, standard `TMPDIR` placement, invalid-input fallback, and source checks ensuring no machine-specific paths or directory creation remain in `get_scratch_base()`.
- Kept all five foreground, background, normal control, and Gitdir assertions completely unchanged and green.
