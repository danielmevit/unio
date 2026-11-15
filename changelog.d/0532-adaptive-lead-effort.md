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
are preserved exactly. The real owned app-server connection seam stays an
explicit refusal (fake test transport only); effective provider effort stays
Unknown. Installer embedding, help and completion are registered; focused
suites: tests/unio-lead-effort.py, tests/unio-lead-session.py,
tests/unio-managed-lead.py, tests/unio-managed-lead-codex.py. Unreleased.
