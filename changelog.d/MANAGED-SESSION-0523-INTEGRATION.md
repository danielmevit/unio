Proposed/unreleased 0.5.23: integrate the preserved first managed-session CLI slice
onto the released 0.5.22 source, retaining current operator and admission protections.
Local status/output observation and idempotent steering apply only to an already
authorized single-turn managed Codex Source. This does not attach arbitrary lead
conversations, start new turns, complete lead takeover/cooldown, establish Windows
support, or change current-inference effort; effective inference remains Unknown.
UNIO_VERSION remains 0.5.22 pending lead-owned release work. Integration checks and
independent reviews/lead acceptance are separate; no acceptance is claimed here.
Detect a missing archived suffix even when the remaining transcript ends at a
valid record boundary; retain its validated cursor prefix and flag the gap.
