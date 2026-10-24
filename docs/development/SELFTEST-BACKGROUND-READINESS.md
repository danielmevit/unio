# Mock selftest background readiness

The exact `9758f4224a73d8ee49dd3a85cfbefd8830e8f2a4` combined gate exited 1
in 872.995 seconds. The managed-lead suite passed; selftest reported 38/40,
with the background pidfile and kill checks failing. This is preserved failed
evidence, not candidate acceptance. Startup/observation load remains a hypothesis
for that occurrence; no product run/kill defect was established by its log.

The former two-second pidfile observation can precede admission and ownership
publication. The former completion loop can accept an absent pidfile before the
child even starts. Deterministic delayed fake jobs reproduce both observation
gaps without a provider call.

The selftest now retains the background runtime as a directly launched child,
using the existing `UNIO_BG=1` runtime boundary that `run -b` launches. This gives
it an exact child to wait for and clean up even before ownership publication.
It does not exercise the detached `run -b` frontend in these two assertions;
that frontend and all run/kill/admission runtime code remain unchanged.
Readiness requires the public pidfile to match that child, a nonempty ownership
record, a live child and a fresh marker written by the mock provider. The existing
native kill validates ownership before signaling. Completion requires the child
to exit, a fresh provider marker, and removal of both public controls. The noop
provider intentionally produces no diff, so its runtime exit may be nonzero;
absence without its fresh marker is always failure.

Readiness and completion each poll at 100ms for at most 60 seconds. The slow
mock sleeps 120 seconds to remain available throughout the readiness window.
Cleanup uses native kill for an owned child, or TERM for the exact launched
pre-start child, then observes exit for at most 70 seconds. It does not enumerate
operator jobs or use unvalidated public pid values for raw signals. Failure
prints task, child, phase, control/marker listings and the last 20 launch-log
lines, keeping the failed sandbox. Cleanup failure is an additional failure,
never a green result. The normal selftest still has 40 assertions.

`python3 -B tests/unio-selftest.py` installs into an isolated TMPDIR fixture,
extracts these exact helper definitions from the installed runner, and exercises
fake delayed readiness, delayed completion, exit-23 no-start, 60-second readiness
timeout, and cleanup with an unrelated sentinel process. Negative controls
replace the observations with their former logic and must fail on those delayed
fixtures. The normal installed 40-check selftest and config/Git preservation
checks still run. All fake Python children disable bytecode through the fixture
environment. No actual AI command is invoked.

This focused validation does not replace the lead's fresh independent review
or combined gate. Previously passing backend evidence is reused unchanged.
