# Save-store recovery — 2026-10-14

On Unio 0.5.16, a local workspace store refused new captures because an active and archived save
shared an ID and an archive reservation was corrupt or unsupported. These were storage-state
refusals, not model-quality failures.

With STOP set and all native workers idle, the lead used the installed save helper, shared saves
lock, and bounded metadata and content validators. A private inventory with path metadata and SHA256
hashes was recorded first. All 32 active and 2 complete archived snapshots passed deep validation.
One additional archive wrapper was empty and duplicated an active ID; that active snapshot also
passed deep validation. There were no claims or pins.

Archival reserves a private ID wrapper before moving a snapshot. An interruption between those steps
is consistent with the empty wrapper, but the historical cause was not proven. Under the exclusive
saves lock and STOP, ownership, mode, the unchanged empty wrapper, active snapshot validity, and
original manifest hash were rechecked. Only that empty wrapper was atomically renamed out of the
saves catalog into a private, project-owned recovery folder. Its inode and empty directory were
kept, along with the inventory and rollback instructions. No snapshot content was deleted, edited,
restored, accepted, or retried.

Afterward, `unio save usage --json` returned exit 0 and reported 32 active, 2 archived, 0 corrupt, and
0 claims. Active content remained 107,217,821 bytes. This was a metadata-only check, not fresh deep
validation or proof of provider readiness. A later native run created a baseline save of 439 paths
and archived one eligible old snapshot with `UNIO_SAVE_CAPTURE_TIMEOUT=300`; this does not show that
the default 30-second budget is sufficient. The worker later disappeared before edits, a separate
operational interruption.

If a similar refusal returns, keep STOP set and workers idle; preserve evidence and inspect
ownership, metadata, claims or pins, and snapshots under the saves lock before considering one
specific reversible action. Do not assume an empty reservation if files or snapshot content exist,
populated copies conflict, claims or pins are unreadable, or ownership or types are unsupported.
Keep private receipts and logs private. This checked manual recovery is not an automatic repair
feature and does not guarantee future failures preserve all work.

