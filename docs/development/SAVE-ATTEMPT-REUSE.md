# Successful save-attempt metadata reuse

Retention optionally collects ephemeral metadata candidates while deep-loading every
active save. A deep failure gets a metadata-only fallback solely for last-good
eligibility; retention still treats it as protected corrupt evidence. Valid archive
metadata is included only after the existing corruption, duplicate, pin and cap
checks pass. Moving saves into the archive preserves their IDs and ordering.

After validated atomic publication, publish adds the new manifest and chooses by
(publication time, ID), never assuming the new save is newest. Successful attempt
writing happens before the same saves lock is released. There is no persistent
cache. Refusals and publication faults use the original fresh lookup. Attempt I/O
failure remains nonfatal. Both observations and all deep validation remain.

Installed regression instrumentation asserts one deep load and zero metadata-only
loads for ordinary valid history, no successful last_good traversal, and equivalent
metadata identity for future/tied timestamps and body-corrupt history. The existing
performance, retention and work-saving suites cover exact restore, descriptors,
pins, caps, stable bytes and interrupted archival. No timing threshold or global
speedup claim is made; this does not establish a cure for all 60-second timeouts.

## Validation receipt — 2026-10-24

Implementation checkpoint `c3d0843` passed the installed reuse (27 checks),
performance (31) and retention (29) suites. Final four-suite wrapper results,
revision and exact exits are recorded in the task delivery summary. Shell syntax,
diff whitespace and frozen scope checker passed. Tests run sequentially through
the supplied private-tmpfs wrapper; fixtures are not the real project save store.
Existing regression files remain unchanged; quality-check adds one registration.

The initial new test incorrectly called the real SIGSTOP fault in-process. That
run was explicitly terminated (test exit -9, wrapper exit 247), preserved, and the
harness corrected to use catchable refusal injection. Existing suites separately
exercise real publication/archival process faults. No provider retry occurred.
Source completion awaits independent Opus XHIGH review and existing lead acceptance;
these checks do not confer acceptance. No full quality gate or live probe was run.

## Test-only coverage correction — 2026-10-24

The installed-helper regression now checks each normal successful capture against
its newly published ID, complete attempt status, exactly one known_good write, and
a fresh installed last_good(False) result. Successful retention cases assert that
active IDs actually move to archive with identical bytes, while source worktree,
index, HEAD and claim pins remain intact. Already archived future history and a
deterministic equal-timestamp tie won by existing fff… over new 111… are covered.
A negative control silently skips the current attempt write with an unchanged
last_good_id and must fail the current-attempt identity assertion. The deliberate
nonfatal attempt-I/O case instead checks the one attempted complete write and new
publication: persistent complete metadata cannot be required when I/O fails.

Installer and quality registration remain byte-identical to e2f0afa. The original
Claude Code 2.1.309 / requested Opus5.5 XHIGH runtime APPROVE remains historical
evidence for that revision, not approval of this test delta. Fresh current-code
Opus review and lead assessment are still required. Frozen sequential four-suite
check logs and exact revision/exits are recorded in the delivery summary. The
in-process fault cases remain catchable bookkeeping injections, distinct from
the existing suites' real process-exit faults.

## Tie-break coverage restoration — 2026-10-24

Review of 94c1d43 found its existing-wins tie (fff… vs new 111…) passes even
when publish ignores the ID, because max() keeps the first tied candidate. The
existing-wins case is kept and a new-wins fixed tie (existing 222… vs new eee…
at one pinned stamp) is added; both compare against a fresh installed
last_good(False). A behavioral mutation control binds an in-memory publish with
only its ID tie-break removed to the installed globals and must fail exactly at
the new-wins metadata identity assertion; the oracle last_good stays unmodified.
The os.urandom pin now returns the fixed ID only for the first 16-byte request
and delegates every other call (including atomic_private's 8-byte nonce) to the
real function. Installer and quality registration remain byte-identical to e2f0afa.
