# CHECKPOINT-ARCHIVE-WORKER-20261111

Add `unio save archive-worker`, an explicit, operator-selected archival of one
confirmed-inactive worker's unclaimed active history (including its newest
save) that frees active slots without deleting bytes. Read-only
`[--plan]` previews selection, blocked/protected saves, native activity,
bounds and a deterministic plan hash (observation clocks and unrelated
workers' refused-attempt metadata excluded); `--apply PLAN_HASH
--confirm-inactive` is the only mutating form, refusing live/locked native
workers, stale plans, claim/activity races and unknown archive capacity under
the same locks/order as native saving, deep-validating exactly the selected
bodies and reusing the per-ID atomic archive move. Every ID/byte/attempt/claim
stays intact (archived saves inspect/restore at the archive path; last-good is
rechecked), partial interruptions report truthful nonzero/Unknown state with
moved/remaining IDs, each application writes a bounded versioned maintenance
receipt under `coord/reports/.checkpoint-archive/`, and `unio save
archive-worker` works while STOP is set like other owner-authorized local
maintenance. Help, completion, `docs/WORK-SAVING.md` and
`tests/unio-save-archive-worker.py` (registered once in
`tools/quality-check.sh`) cover the new command; existing semantics, schemas
and default newest protection are unchanged.
