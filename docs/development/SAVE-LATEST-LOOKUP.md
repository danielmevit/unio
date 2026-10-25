# Latest checkpoint lookup

`last_good(store, worker, deep)` now discovers bounded manifest hints before
visiting body pools. This targets metadata work for unrelated workers and older
history when looking up one worker. It does not change save eligibility, storage
layout, retention, publication, locks, deadlines or version 0.5.24.

## Selection and conservative fallback

Discovery records active/archive names with the same exclusions as `scan_store`.
Their intersection refuses globally duplicated IDs, even when a copy is malformed,
foreign or an unknown entry. Archive root/wrapper checks, private directories,
no-follow opens, private manifest descriptors and existing manifest/name bounds
remain in use. Discovery never opens a pool or context directory.

A manifest is only a selection hint. Matching worker hints are ordered by
`(published_at, ID)` descending, including future dates and timestamp ties.
Candidates take the unchanged `load_save(..., False)` validator until one qualifies.
For `deep=True`, that candidate must also pass unchanged byte validation; a failure
tries older history. Metadata-valid same-size byte corruption remains eligible
for `deep=False`. The complete original item shape, including metadata-derived
`stored_bytes`, is returned.

For stable storage, every possible eligible save has a valid manifest hint. A
higher-ranked requested-worker hint either passes full validation and wins, or
fails the same validator used by the old lookup. Foreign hints cannot qualify.
Malformed/unreadable/unsafe manifest discovery takes the preserved original full
scan instead of deciding eligibility from incomplete evidence. Unknown non-ID
names cannot qualify, but still participate in duplicate detection.

Full validation must agree with the selection manifest. A second bounded discovery
rechecks all manifests and names, including foreign/older hints. A disagreement,
missing entry or uncertain discovery takes one original full scan. There is no
retry loop or persistent cache. This detects changes between the observed views;
it does not create an atomic filesystem snapshot or remove the original lookup's
concurrent-mutation limits. Existing callers' locking remains unchanged.

## Observed work, 2026-10-25

Installed isolated fixtures use real Git worktrees and an actual published save,
then copies with valid identity/timestamp changes. Each save has four pool files.
The initial frozen-baseline Windows-mounted fixture had 13 active saves, 12 for
another worker: 13 full metadata loads, 12 foreign loads and 52 pool-file metadata
checks for one shallow latest lookup.

A matched populated fixture has seven active and six archived saves, again 12
foreign saves. Instrumentation through the installed helper reports:

| Shallow latest lookup | Frozen baseline | Candidate lookup |
| --- | ---: | ---: |
| Full metadata loads | 13 | 1 |
| Foreign-worker metadata loads | 12 | 0 |
| Pool-file `private_at` checks | 52 | 4 |
| Manifest reads | 13 | 27 |

The candidate Windows-mounted run observed the right-hand counts. The private
baseline negative control installed the frozen installer and failed precisely at
`lookup avoids unrelated full metadata loads`, with the left-hand counts. That
negative control ran under the private tmpfs wrapper; committed tests do not
require a Git object. Counts, rather than elapsed-time thresholds, are the
regression contract. Extra bounded manifest reads deliberately pay for change
checks. A store with invalid manifests conservatively retains full-scan costs;
invalid newest candidates may also require validation of multiple older saves.

This is component evidence, not a full-save speedup, a timeout cure or a hardware
diagnosis. The lead’s separate `DRIVE-COMPARISON-2026-10-25.md` diagnostic measured
matched small-file medians C: 72.634 / D: 70.488 seconds and a later native Windows
control of 0.387 seconds with different APIs/caches. Both letters share one NVMe.
Its original full-snapshot preparation failed before measurements. Those retained
observations motivate examining access patterns; they do not quantify this change.

## Regression and operation

Run `python3 -B tests/unio-save-latest-lookup.py`. It installs into an isolated
fixture and extracts the installed helper like the neighboring suites. It checks
complete returned items against the original scan/validator semantics, active and
archived ordering, empty/foreign history, corrupt metadata and bytes, missing and
unsafe files, duplicate IDs, archive roots/reservations, unknown entries, claims,
bounds, injected races, real periodic skip and refusal attempt bookkeeping. A
behavioral negative control makes an invalid newest hint appear validated and
requires the winner assertion to fail.

The quality gate registers this suite immediately after the reuse suite. Existing
reuse, performance, retention and work-saving suites remain unchanged. The frozen
five-suite check wrapper and final syntax/whitespace/scope checks are recorded with
exact exits and revision in the worker delivery summary. No broad quality gate,
provider probe, real-store cleanup or global installation is part of this task.
Independent current-code review and lead acceptance remain required.
