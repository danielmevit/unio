0533-VALIDATION-LANES: measurable, selectable quality gate — developer tooling
for Unio itself; no runtime, installer, engine, adapter or receipt changes.
`bash tools/quality-check.sh` with no arguments remains the exact full offline
gate: the original 125 commands, order, environment bounds, installer fixture,
cleanup and first-failure semantics, and only a complete full run prints
`quality-check: all checks passed`.

Added `--lane NAME` (repeatable; twelve lanes: static, install-smoke,
safety-core, evidence-review, managed-lead, adapters, observation, bridge,
delegation, admission-env, save, docs) and a dry `--list`. Lane unions
deduplicate and keep canonical order; a lane run reports PARTIAL coverage and
never the full-pass string; unknown flags, unknown lanes, duplicate lanes and
missing values exit 2 before any check or fixture starts. The ordered
catalogue is `tools/quality-gate-commands.json`, dispatched by the
standard-library `tools/quality-gate.py`; the only addition to the original
list is the explicitly marked runner self-test `tests/unio-quality-gate.py`
(static lane), pinned against the tracked snapshot
`tests/fixtures/quality-gate-baseline.json` so coverage and order drift is
caught. The installer fixture is created only when a selected command needs
it and is always removed; children run with the existing `UNIO_*` offline and
auto bounds plus `PYTHONDONTWRITEBYTECODE=1`; provider and model calls stay
zero.

Optional `QUALITY_TIMINGS` writes an incremental TSV (id, command, start and
end UTC, monotonic elapsed seconds, actual exit code) per executed command; a
timing failure never masks a check failure, and an unusable timing output
cannot produce a false full pass. New
`docs/development/VALIDATION-MATRIX.md` documents the lanes, the TSV format,
the Fast/Balanced/Thorough developer, batch and release matrix and the
limitations. Deliberately deferred, documented as follow-ups rather than
silently claimed fixed: the unregistered `tests/unio-route-contract.py`
suite (registration auditing is a later batch), recursive docs lint
(`check-docs.sh` still skips `docs/ai/` and `docs/development/`), and all
automatic path selection, caching, parallelism and fixture-setup work. No
measured speedup or savings claim; one full release gate is still required
and frozen Validate lines keep their exact meaning.
