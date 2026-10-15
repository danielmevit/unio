# Populated-store saving cost — 2026-10-15 measurement

`SAVE-PROFILE-VIBE-HIGH-2` is a bounded, read-only runtime investigation of
how existing save history slows `save create` on the installed engine. It
changes no product source, no timeout and no validation rule. A separate
worker owns native stopping; nothing here touches that work.

## Method

A new private harness (modeled on `tools/save-benchmark.py` and the
2026-10-14 harness whose summary print crashed before any usable report)
built four fresh isolated fixture projects on the Windows-mounted `v9fs`
filesystem, two per case, each with:

- four local workers and one known task, hooks and template injection
  disabled, STOP set, and a provider stub that records any invocation;
- a generated worktree of 305 tracked paths (300 small distinct bodies of
  about 100 bytes plus the base files), 307 worktree files, about 35 KiB;
- an explicit 300-second capture budget, private Git and Unio configuration,
  and bounded subprocess deadlines (330 seconds per step, 2700 per case).

The baseline case seeded one prior save for the measured worker. The
populated case seeded 12 distinct saves, three per worker, each with a
distinct worktree state so every save has its own full per-save body pool.
The measured call was one manual `save create` for the same worker on the
same worktree shape; only the store population differs between cases. Every
save was confirmed against its published manifest. Two repeats per case were
recorded. No restore was performed; manifest confirmation does not prove
one.

Engine: installed Unio 0.5.18, SHA-256
`180c5e09ac74c51c92a1322546b2625783832cb21f25e6673ba8b46128c5a7e2`, at
source commit `e66b4844b69374b3ff19078fc72a7c89320b99dd`. The embedded save
helper extracted from the installed engine is byte-identical to the source
checkout (helper SHA-256
`0f5eb3ef6375d9a1234bbdbff256e57878bbfdf1550b8fb4a8fba7a6c0a0559c`).

## Observed create latency

All four measured creates exited 0 with a matching published manifest. The
provider stub was never called and STOP stayed set in every fixture.

| Case | Repeat | Prior active saves | Create seconds | Inspect seconds | Usage seconds |
| --- | ---: | ---: | ---: | ---: | ---: |
| Baseline | 1 | 1 | 11.19 | 5.01 | 0.86 |
| Baseline | 2 | 1 | 8.23 | 3.79 | 0.57 |
| Populated | 1 | 12 | 23.52 | 11.50 | 3.72 |
| Populated | 2 | 12 | 17.98 | 8.47 | 3.07 |

The populated store held 13 active saves after the measured create (12 seeds
plus the measured save), 3,978 stored body files and about 1.98 MiB; the
baseline store held 2 saves and 612 body files. Per-save seeding latency grew
with the store: from 7.9–8.9 seconds at an empty store to 18.2–21.4 seconds
at 11 prior saves, roughly 1.0–1.2 seconds per additional active save at this
worktree shape. `save usage`, which is metadata-only, cost about 0.24–0.29
seconds per active save; worker `save inspect` deep-loads only the
worker's newest valid save and roughly doubled from baseline to populated.

These are synthetic-fixture timings on one filesystem with two repeats per
case and uncontrolled host I/O. They are not real-workspace latency, not a
general model, and not a filesystem ranking. No ext4 or tmpfs comparison was
run, so no claim is made about how `v9fs` per-file metadata costs compare
with other filesystems; only this filesystem's timings are recorded.
Extrapolating the roughly linear per-save cost on this fixture shape, a
manual create would cross the default 30-second automatic capture deadline
somewhere around 18–22 active saves; that extrapolation is a hypothesis for
a future measurement, not a claim about any real workspace.

## Function attribution

One additional create in the populated fixture ran the extracted,
byte-identical installed helper under cProfile (wall 35.5 seconds versus
23.5 seconds unprofiled; only relative attribution is used). Cumulative
times overlap and must not be added:

| Profiled work | Calls | Cumulative seconds |
| --- | ---: | ---: |
| `publish` (one full save attempt) | 1 | 24.05 |
| `retention_plan` (existing-store validation) | 1 | 21.90 |
| `load_save`, all deep and metadata passes | 41 | 26.23 |
| `read_stored_at` (deep body reads) | 4,298 | 17.32 |
| `scan_store` (metadata passes over all saves) | 2 | 8.43 |
| `private_at` (metadata privacy checks) | 8,412 | 7.68 |
| `observe` (both worktree observations) | 2 | 7.58 |
| `walk_worktree` | 2 | 4.08 |
| `write_attempt` via `last_good` (third store scan) | 1 | 3.79 |
| `sha` (all hashing) | 5,565 | 0.06 |

The populated-store cost is dominated by `retention_plan`: on every publish
it first metadata-validates every active save through `scan_store`, then
deep-loads every active save again, opening, reading and hashing every
stored body. `write_attempt` then performs a third, metadata-only store
scan through `last_good`. Hashing itself is negligible; the cost is
per-file open, stat and read metadata work, which `v9fs` amplifies. The
0.5.16 descriptor-bound optimization is preserved in this engine and its
effect is included in these numbers.

## Recommended bounded follow-up

One concrete change, preserving every existing guarantee — full byte
validation, both worktree observations, retention correctness, atomic
publication, last-good-save preservation, secret refusals, capture
deadlines and exact restoration:

Fold `retention_plan`'s separate metadata-only `scan_store` pass into its
deep-validation loop. Today each active save is opened twice per publish:
once by the metadata pass (manifest read, directory listings, one
`private_at` stat per stored body) and again by the deep pass (every body
re-opened, read and hashed). A deep `load_save` already performs every
check the metadata pass performs, so the retention path can classify,
order and deep-validate each save from one load, keeping corrupt-evidence
handling, pins, newest protection, caps and archive accounting unchanged.
Every stored body would still be opened, read and hashed exactly once per
publish — no validation is weakened and no result is reused between
separate saves.

- Scope: `retention_plan`, `scan_store`, `load_save`, `publish` in the
  embedded save helper; no timeout, retention policy or store layout
  change.
- Regressions: the installed save-performance suite, corrupt
  body/manifest/bundle and duplicate-ID cases, and an A/B timing on an
  equivalent populated fixture (12 saves across 4 workers) to confirm the
  reduction rather than assume it.
- Estimate: half a day for one implementation worker, comparable in size
  to the 0.5.16 descriptor-bound change.

The third traversal (`write_attempt` re-scanning the store for the last
good ID) is a separate, smaller measured cost and is deliberately outside
this recommendation; folding it in would need its own correctness argument
about post-publication state.

The single recommended fold above was implemented as
`SAVE-RETENTION-GO-GLM-HIGH-1` (see the "Folded retention validation"
section in `SAVE-PERFORMANCE.md` for the regression coverage and its A/B
measurements). This document preserves the original diagnosis unchanged.

## Limitations

- Synthetic fixtures only; no real project, task payload, credential or
  save was read. Raw receipts, the harness, the extracted helper and the
  pstats dump stay in the task's private directory.
- Two repeats per case on one host; storage and cache state uncontrolled.
- cProfile inflates wall time; only relative function attribution is used.
- Small bodies and no carried commits: bundle validation and large-body
  read costs are not exercised.
- The explicit 300-second capture budget was used; the automatic
  controller's wall-clock stop was not exercised, and no tmpfs or ext4
  comparison was run to separate filesystem metadata cost from process
  cost.
