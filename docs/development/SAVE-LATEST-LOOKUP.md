# Latest checkpoint lookup

`last_good(store, worker, deep)` discovers bounded manifest hints before visiting
body pools. The original private prototype was **not accepted** after review.
The corrected implementation at `095b0d6` passed fresh independent Claude Code
2.1.310 / Opus 5.5 XHIGH review and the lead's assessment on 2026-10-25; it is
accepted on the private 0.5.25 integration branch. Public delivery and the full
combined gate remain separate steps. No full-save timeout cure or universal
speedup is established.

## Selection and error behavior

Discovery retains every active/archive name using the original exclusions.
Intersecting names refuse globally, including corrupt, foreign and unknown
copies. Global name bounds and private archive-root checks remain unchanged.
Each snapshot directory and manifest uses existing private ownership/mode and
no-follow checks. Discovery never visits context or body pools.

Safely read raw manifest bytes are untrusted hints. Strict JSON parsing happens
once per readable hint; only matching worker and parseable publication time are
necessary conditions for candidate ordering, never proof of eligibility. Every
eligible old-validator save meets those conditions. Candidates are ordered by
`(published_at, ID)` descending, including future dates and ties. The unchanged
`load_save(..., False)` validates candidates until one qualifies. Deep lookups
also use unchanged `load_save(..., True)`; ordinary invalid-save refusals skip
that candidate. Shallow lookup still permits metadata-valid same-size body
corruption and returns the original complete item, including `stored_bytes`.

Malformed/unsafe manifests and invalid archive reservations cannot qualify under
the old validator. They are recorded locally, with their names retained for
duplicate checks, rather than forcing partial discovery and a permanent full
scan. A second bounded discovery checks names, directory/wrapper validity,
readability and raw bytes; it repeats neither JSON parsing nor schema/fingerprint
validation. An invalid entry becoming readable changes the view. Arbitrary
wrapper/lstat I/O errors retain the legacy full-scan error behavior.

Full candidate validation must agree with its initial parsed hint, and deep
validation must agree with shallow validation. A disagreement or changed recheck
discards the hints and invokes the preserved original full scan at most once.
**No fallback invocation is inside the candidate-invalid or recheck exception
handler.** A genuine fallback refusal propagates exactly, even if a later view
would have returned to its initial state. There is no retry, persistent cache or
atomic filesystem snapshot; existing locking and concurrent-mutation limits remain.

## Original prototype evidence, retained

The original 13-save fixture (seven active, six archived, 12 foreign saves,
four pool bodies per save) reported full metadata loads 13 → 1 and pool metadata
checks 52 → 4, but manifest reads 13 → 27. Those original receipts and the early
commits remain. Review correctly found this insufficient total-work accounting:
the prototype also ran full manifest/schema/fingerprint validation 13 → 27.
Its shallow/deep mismatch fallback could swallow a genuine refusal and return
an older save. Original green suites did not establish acceptance. Reviewer-only
platform timings are not reused as reproduced measurements here.

## Shallow lookup work accounting, 2026-10-25

All work-count and timing tables below measure `deep=False` (shallow lookup).
For stable inputs, both implementations add the same existing deep validation
of the selected save when `deep=True`; deep counts and wall/CPU performance
have not been measured. These figures do not establish a periodic-checkpoint or
`save inspect --worker` speedup.

The installed suite instruments Python file-operation API calls, not kernel
syscalls or hardware I/O. It reports every instrumented category, including zero
categories. Matched 13-save/four-body valid fixtures give these complete counts:

| Work category | Preserved full scan | Original prototype | Correction |
| --- | ---: | ---: | ---: |
| `open` | 52 | 56 | 56 |
| `close` | 52 | 56 | 56 |
| `stat` | 117 | 9 | 9 |
| `lstat` | 32 | 65 | 65 |
| `fstat` | 13 | 27 | 27 |
| `scandir` | 8 | 16 | 16 |
| `listdir` | 39 | 3 | 3 |
| `read` | 26 | 54 | 54 |
| `readlink` / `access` | 0 / 0 | 0 / 0 | 0 / 0 |
| Sum of instrumented file-operation calls | 339 | 286 | 286 |
| Manifest reads | 13 | 27 | 27 |
| Strict JSON parses | 13 | 27 | 14 |
| Full manifest/schema/fingerprint validations | 13 | 27 | 1 |
| Full shallow save validations | 13 | 1 | 1 |

Directory enumeration calls (`scandir` plus `listdir`) fall 47 → 19, but directory
rechecks and raw reads still cost work. Total instrumented API calls decrease for
this 13-save fixture, despite increased directory rechecks and raw reads. For 41/401 bodies, baseline `stat` calls are 598/5278
versus corrected 46/406; all other file-operation counts in this table stay the
same. Corresponding complete call sums are 820/5500 versus 323/683. The one-save case below demonstrates a
work-count crossover; operation categories have different costs.

Deterministic bounds cover one-save active, two-save active/archive and populated
13-save fixtures, requested/missing workers, own history and malformed/unsafe
foreign history with empty archive reservations. They assert manifest reads,
parses, validations, every file-operation category and the actual fast/fallback
path. Corrupt-history cases deliberately avoid permanent global fallback, though
invalid requested-worker candidates may require several full validations.

## Bounded shallow timings and reproducibility

Timing is optional measurement, never a regression threshold. Set
`UNIO_LOOKUP_MEASURE` to a project-owned JSON output path and run
`python3 -B tests/unio-save-latest-lookup.py`; set `TMPDIR` to the project fixture
root. The supplied private tmpfs wrapper supplies the separate memory reference.
The optional measurement reads the preserved prototype from commit `74b1e22`,
compares it and the corrected helper against the byte-identical full-scan
baseline, and asserts seven active/six archived eligible saves before timing.
Fixtures have 4/41/401 distinct pool bodies per save and manifests of
1698/7766/66806 bytes. Every implementation must return the same complete item.

Each implementation gets an explicit warmup, then nine samples in recorded,
rotating/reversed interleaved order. No cache flush is attempted. Raw wall/process
CPU samples, operation counts, order, fixture sizes and dated command/hash
receipts are retained under the continuation's project-owned scratch directory:
`tmp/unio-next/save-latest-lookup-continuation-low-20261025/`.
Earlier correction receipts remain untouched in the sibling
`save-latest-lookup-correction-low-20261025/` directory. The retained final memory
run matches the current installer and suite SHA256 hashes; the earlier explicitly
invalid-fixture memory run is excluded. The continuation reruns both environments
rather than filling the unfinished D: receipt from assumptions.
`run-measurements.py`, `measurement-receipts.json`, `measure-final-memory.json`,
`measure-final-d.json` and corresponding logs are the reproducible evidence.
The delivery summary gives absolute paths and actual exits. Tmpfs is a memory
reference, **not ext4**. D: is the existing Windows-mounted project fixture root;
these measurements do not establish behavior on other filesystems or cold caches.

The continuation rerun (2026-10-25 UTC) produced these medians in milliseconds.
Each cell lists preserved full scan / original prototype / correction.

| Fixture location | Bodies/save | Wall ms | Process CPU ms |
| --- | ---: | --- | --- |
| Private tmpfs | 4 | 4.20 / 6.89 / 2.20 | 4.32 / 7.08 / 2.27 |
| Private tmpfs | 41 | 14.29 / 22.30 / 4.60 | 14.67 / 22.89 / 4.73 |
| Private tmpfs | 401 | 107.23 / 153.04 / 24.29 | 110.00 / 157.00 / 24.92 |
| D: project mount | 4 | 604.30 / 681.54 / 648.98 | 69.38 / 80.07 / 70.00 |
| D: project mount | 41 | 1397.96 / 755.28 / 746.11 | 151.48 / 97.95 / 78.65 |
| D: project mount | 401 | 9880.64 / 1637.90 / 1465.26 | 984.82 / 323.96 / 179.91 |

Both bounded measurement commands exited 0. The measured small-pool D: result
is a regression relative to the full scan; larger-pool improvements do not erase
that cost. These samples are local observations with uncontrolled OS caches and
scheduling, not a universal platform speedup or full-save measurement.

Small stores can pay more recheck overhead even when CPU work falls; one-save
requested-worker lookup uses 44 instrumented calls versus baseline 26. At 13
saves/four bodies the correction uses fewer total calls, yet its D: wall time
regresses; larger pools avoid substantially more body metadata checks. Timing and CPU
tradeoffs depend on fixture size, storage APIs, caches and scheduling; no
unsupported platform assumption is used to choose eligibility or fallback.

## Regression and operation

Run `python3 -B tests/unio-save-latest-lookup.py`. Existing semantic/restore,
reuse, performance, retention and work-saving coverage remains. Added tests prove
ordinary corrupt evidence stays on the fast path, deep validation and races
actually execute, and shallow/deep/changed-then-restored fallback refusals cannot
return an older save. Retained negative-control runs fail each refusal regression
against the original prototype. Arbitrary wrapper I/O propagation is also checked.

For the correction task itself, the quality registration remained byte-identical
to its frozen base, and validation covered the five focused suites plus
syntax/whitespace/scope checks. The full-scan function body remains byte-identical.
That task did not perform a broad gate, provider probe, real-store repair, global
installation, version change or release. Independent current-code review and
lead acceptance subsequently passed; the separate assembled-candidate gate and
release preparation are tracked in [the release guide](../RELEASE-0.5.25.md).
