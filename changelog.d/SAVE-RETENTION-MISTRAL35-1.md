### Added

- Archive eligible older recovery saves under project or worker pressure,
  preserving their IDs and bytes, each worker's newest valid save, claim pins
  and corrupt evidence. Active limits remain 5 ordinary saves per worker,
  8 total per worker and 32 per project; the archive holds at most 128 saves
  or 512 MiB. A full or unsafe archive refuses a new save without deleting history.
- Add `unio save usage [--json]` for read-only metadata counts and storage bounds.
  Busy, corrupt or unsafe observations remain Unknown. Inspect, restore and
  separately authorized continuation resolve archived IDs without moving them back.
- Cover cross-worker pressure, byte preservation, claims, collisions and
  interruption in isolated native checks. Codex completed Mistral Medium's
  preserved partial implementation after its Vibe connection failed.
