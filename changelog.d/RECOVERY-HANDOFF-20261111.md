# Recovery handoff for failed report-only runs (2026-11-11)

## Change

`unio handoff WORKER TASK` now remains useful after a failed or interrupted
report-only Source run. Previously `report_evidence`'s strict
"report-only requires a current successful Source" requirement blocked every
packet, even when the run had left a genuinely bound partial report and
declared partial artifacts. That strict default is unchanged for verify,
review and readiness.

Behavior, all inside the frozen QUALITY_PY contract
(`report_evidence`, `report_material`, `handoff`, new `recovery_*` helpers; no
schema, CLI or gate changes):

- Successful report-only handoffs are byte-identical to before.
- A terminal failed Source (recorded nonzero exit) at an unchanged snapshot
  publishes an explicitly incomplete recovery packet:
  - `report.md` records the original failure (`INCOMPLETE RECOVERY SOURCE`
    with the real `process` state and exit), the genuinely bound partial
    report (hash/length re-verified) under `INCOMPLETE SOURCE REPORT`, and
    delivery material mirroring `delivery_material` with strict
    `delivery_check` binding rechecks and `MISSING ARTIFACT` labels.
  - A missing/unavailable report is labeled `MISSING SOURCE REPORT` with the
    recorded `report_artifact_unavailable` reason; no text is fabricated and
    raw logs are never scraped.
  - `HANDOFF.md` and `result.json` keep the real failure, `stale`,
    `not ready_for_human_review`, and invalid `outcome_current` facts.
- Refusals preserved: running/locked workers, interrupted or unknown process
  states, changed snapshots or worktrees, changed task text, tampered or
  unbound report/binding/prompt/artifact evidence, symlinks, unsafe files,
  oversized material, and delivery command changes all still fail closed and
  publish nothing.
- The internal opt-in is handoff-only; `verify`, `review`, `outcome-check`,
  readiness gates and all other callers keep the exact strict behavior and
  messages.

## Tests

New regression suite `tests/unio-handoff-incomplete.py` (mock-only, no
providers; registered in `tools/quality-check.sh`):

- successful report-only handoff unchanged;
- failed Source with real partial report and partial declared artifacts gets a
  clearly incomplete packet with original failure, while
  verify/review still refuse;
- tampered bound report, tampered/symlinked delivery artifacts and changed
  snapshots refuse (and recovery works again after byte-identical
  restoration);
- missing report is labeled, not fabricated, and no artifact/log text is
  scraped;
- offline frozen-engine checks: running/succeeded/inconsistent states never
  become recovery provenance, unbound content next to a missing report
  refuses.

Existing suites `tests/unio-task-outcomes.py` and
`tests/unio-required-delivery.py` keep their strict expectations.

## Limits

- An interrupted (running) report-only run still cannot produce a packet; an
  explicit stop is needed first so its Unknown state stays truthful.
- The recovery packet reuses the existing 300000-byte bound; oversized
  material still refuses.
- No new CLI flag; legacy implementation-mode handoffs are unchanged and out
  of scope here.
