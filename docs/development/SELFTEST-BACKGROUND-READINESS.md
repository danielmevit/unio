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

## Opus LOW correction (SELFTEST-LIFECYCLE-OPUS-LOW-0524)

An independent Opus XHIGH review of `88fe824` (`unio-review-v1` findings,
REQUEST-CHANGES) found that the 88fe824 correction stopped exercising
`run -b`. It launched `UNIO_BG=1 unio run` as a direct child, so the lock
probe, the budget pre-check, the `setsid -f` detach, the started
acknowledgement and the frontend exit 0 were no longer covered. That earlier
correction is kept in history as it was.

**Frontend and identity.** T3 and T5 now invoke the public `unio run -b`
again and require exit 0 plus `started in background`. The detached runtime
is not a child of the selftest, so `kill -0` proves nothing about its
identity. Readiness instead requires all of the following:

- a nonempty `.own` record;
- a pidfile naming a session leader (proving the `setsid` detach) with an
  open description holding a WRITE lock on the worker's
  `coord/.locks/<worker>.lock`, read from `/proc/<pid>/fdinfo`;
- a fresh marker from the mock provider.

That pid and its `/proc` start time become the run's identity. The checks
use `fdinfo` because, on drvfs (`/mnt/d`), `/proc/locks` shows flock locks
as POSIX locks with pid 0.

**Natural completion.** Completion first needs the fresh marker. Only after
it appears does the selftest probe the worker lock, because probing earlier
could steal the lock from a runtime that has not taken it yet. Completion
then requires:

- the proved identity gone, or the lock free;
- both public controls removed;
- a new ledger `run` line for the task with `"exit":0` and
  `"snapshot_failed":0`.

A noop Source exits 0 without auto-verify. A post-run snapshot or record
failure is a nonzero runtime outcome and is not accepted.

**Cleanup.** `st_bg_cleanup` returns success only after it proves that the
exact run is gone and its controls are removed. It calls native kill only
while the published pid, lock holder and start time still match the
identity. If native kill fails, or the run outlives it, it sends one TERM
through a pidfd that rechecks the start time. The runtime's own TERM trap
then stops the provider session. Cleanup never signals a reaped, reused or
unproven pid, and never enumerates operator jobs. If it has no identity, or
the run or controls are still there at the deadline, it prints `cleanup
Unknown`, the sandbox is kept, and the result counts as a failure. Phase
bounds are `ST_BG_LIMIT` (default 40 s), polled every 100 ms.

**Slow mock.** The marker write is guarded, and the nap is 60 s, also capped
by `TIMEOUT`. `slow` is benched right after T3, so sabotage rotation cannot
detach it. Teardown waits up to 60 s for recorded pidfiles. If any remain,
it keeps the sandbox and fails.

**Regression.** `tests/unio-selftest.py` extracts the installed helper
block. It drives the block with a fake `unio` whose `run -b` detaches a
`setsid` runtime that holds the worker lock. Cases:

- delayed start;
- delayed completion;
- snapshot failure rejected;
- refused frontend;
- no start (exit 23) and never start, both bounded, with cleanup Unknown;
- native kill failure handled by the pidfd fallback;
- a crashed runtime whose stale pidfile then names an unrelated sentinel:
  not signaled, and the sentinel survives;
- outer timeout.

The two former-logic negative controls replace only the phase they model.
Readiness stays the real bounded helper, and the fixed 4 s sleep is gone.

**Outer bound.** The installed selftest and every harness run in their own
session through `run_bounded`. On timeout it TERMs and then KILLs that
still-unreaped session's group and prints the partial output. It then TERMs,
through a start-checked pidfd, each published runtime that holds a lock in
its own fixture `coord/.locks`. The fixture is removed only when no such
runtime is left. Otherwise it is kept and reported. The fixture again
defaults to a project-local directory when `TMPDIR` is unset.

**Mounted timeout: root cause and hypotheses.** The source of record is the
`r3i1m5tw` sandbox that remained after the 88fe824 mounted verification. It
shows that the installed selftest itself is slow on drvfs:

| Time | Event |
|------|-------|
| 12:06:27 | init |
| 12:07:42 | T2 rogue commit |
| 12:09:01 | T3 readiness marker |
| 12:09:15 | T3 kill (exit 143) |
| 12:11:45 | T5 ledger line |

T5 was not reached until about 318 s after init, so the 300 s outer timeout
expired in the normal checks rather than in a background wait. The T5
runtime then wrote `ledger.jsonl` and a directory after the timeout, while
`TemporaryDirectory` was being removed. That orphan write is the observed
`OSError(39)`.

Exact cleanup on timeout now fixes the orphan race. It does not make a
drvfs selftest fit within 300 s. Per-command filesystem latency (git, saves)
remains the leading hypothesis and has not been profiled per command. The
declared check runs on the private tmpfs fixture.

This focused validation does not replace the lead's fresh independent review
or combined gate. Previously passing backend evidence is reused unchanged.
