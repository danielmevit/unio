0532-ADAPTIVE-LEAD-EFFORT: add the experimental `unio lead-session` vertical
slice — an opt-in, owner-controlled managed lead session per workspace wiring
the managed lead core, the owned Codex bridge and a new adaptive effort policy
(`tools/lead-effort.py`) into a native CLI (start/run/status/effort/worker/
stop/output). AUTO requests low for routine coordination and the ceiling for
substantive planning/review on the same owned thread, with zero model calls
while waiting, one review wakeup per worker terminal event, manual override
that suspends auto, pending next-turn requests, immutable per-turn decisions
and STOP that blocks new turns without killing workers. Per the V2 owner
correction the first interface exposes only AUTO plus LOW and XHIGH: the
ceiling accepts only low or xhigh, manual/pending choices accept only low or
xhigh, medium/high refuse with an explicit interface message, and advertised
sets containing medium/high plus fixed legacy worker/core settings remain
compatible. The bridge gains opt-in per-turn effort, an explicit mapping
bound (1..64) and an explicit acknowledgement-proven handoff; legacy defaults
are preserved exactly. Contract V4 enforces real project policy admission
(`tools/lead-session-policy.py`): project STOP (`coord/STOP`), real installed
and project-level off holds with duration expiry checking, valid registered lead
matching `coord/work-policy.json`, and low-tier shared account group capacity
(counting the registered lead reservation exactly once) before any child process
is spawned or turn dispatched. Concurrency and races with lead/account setters
are prevented via non-blocking `coord/.locks/lead-session.lock` owned lease and
brief `coord/.locks/work-policy.lock` transactions. Read-only status and pending
controls remain allowed in STOP with zero provider calls. Installer embedding,
help and completion are registered; focused suites: tests/unio-lead-effort.py,
tests/unio-lead-session.py, tests/unio-lead-session-codex.py,
tests/unio-managed-lead.py, tests/unio-managed-lead-codex.py. Unreleased.
