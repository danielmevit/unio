# Native stop ownership contract

Source contract for the 0.5.19 native run and kill path. This note does not
claim a live provider was validated; the
offline fixtures are generic local processes.

## Ownership boundary

After account and retry admission, before the provider command is executed,
the native shell writes `coord/reports/.owners/WORKER/TASK.own`. The file is private JSON. It records schema version
1, the current boot id, the worker, the task, and the shell pid, start ticks,
and session. Provider fields stay null until the supervisor has created the
provider session. `schema_version` must be the exact integer 1; a JSON `true`
is refused, because Python compares `True == 1`. Pid and start-tick fields
must be JSON integers, not strings or floats.

The supervisor starts that session with `setsid`, reads the new process from
`/proc`, and requires its session id to be its own pid and to differ from the
shell session. It stores the provider pid, session, and start ticks, and only
then lets `timeout` exec. Ownership therefore exists before the provider runs.

Runtime cleanup reads only that worker's record. Parallel workers may share a
task and its retry grant without sharing runtime ownership. Refused admissions
publish no ownership controls. Background runs also publish the compatible
`coord/reports/TASK.own` and `TASK.pid` public controls; when the same task has
several admitted background runs, these select the latest published run.
Short task-control locks serialize publication and removal, never provider
execution. Provider publication and EXIT cleanup change those public controls
only while they still name that exact shell. Cleanup cannot remove another
worker's selection. Public kill reaping is bound to the selected shell pid and,
after validated signaling, its start ticks, so replacement controls cannot
redirect cleanup to another run. Missing or foreign runtime evidence remains
Unknown and retains the existing cleanup holds.

An owned process is a live process in that recorded session, running as the
same user, and not a zombie. It may leave the original process group. It may
be reparented when an intermediate launcher exits. It stays owned while its
session id is the recorded provider session.

The sweep does not use `pgrep` or `pkill`, and it does not match command text.
The owned-session sweep signals through `pidfd` only after the open pid still
has the recorded start ticks and session. The shell, the supervisor, and the supervisor's parent
are never treated as members of the provider session. If one of those protected
pids is inside that session, or the leader pid is now a different process, the
result is Unknown and nothing is signaled.

`/proc/PID/stat` is split at the last `)`, not the first one, on both the
shell and the Python side. A comm that itself contains `)` therefore cannot
shift the stat fields and forge a start-tick or session match. Observation
preserves normal process disappearance (ENOENT/ESRCH) as gone, but distinguishes
unproved identity (unreadable stat, malformed fields) from gone. A same-user
member whose identity cannot be verified keeps cleanup Unknown rather than
silently assuming it disappeared, while restricted /proc entries of unrelated
other-user processes are ignored and do not fail the run.

A recorded identity cannot redirect a signal to another run under supported
operation. Before anything is signaled, the live target must match the ownership
record's boot id, shell pid, start ticks and session, must run as the same user,
and must have the exact `bash unio run WORKER TASK` command line of that record.
Another run has a different shell pid, start and session; a reused pid has different
start ticks; a helper or Source identity from one run never matches another run's
record. The provider session must additionally be led by the recorded pid
with the recorded start ticks and must differ from the shell session.

This foreign-session validation relies on a private same-user ownership record
as trusted local state; it is not cryptographic proof against arbitrary same-user
record rewriting. The mechanism does not provide container containment or
authentication against a hostile process running as the same UID. Supported
validation strictly requires private file permissions, exact schema version 1
integer typing, boot id match, matching ancestry and start ticks, and session
separation, preserving meaningful refusal for malformed or cross-task identity
evidence.

These cases are outside the boundary. Cleanup is not claimed for them:

- A helper that calls `setsid` and leaves the provider session.
- The shell session itself, including a foreground terminal, the lead, another
  worker, or an unrelated sibling.
- An external `SIGKILL` of the runner. The kernel drops the worker lock when
  that process dies. No daemon is installed to reclaim it.

## Stop, cancellation, and normal exit

On cancellation and on a normal provider exit, the supervisor reaps the
provider session before it starts the final save. Cooperative children receive
`SIGTERM`. Children that ignore `SIGTERM` are then `SIGKILL`ed. Owned provider
cleanup must be proved clear before any final capture is attempted. If cleanup
returns Unknown, worker and account reservations stay held, and no final
checkpoint or Source success is invented. If cleanup later becomes provably
clear, the real provider exit or cancellation code is preserved and the existing
bounded final capture proceeds. The shell waits until that reap reports the
session clear, and only then releases the worker lock and the native account slot.

When the shell itself receives `TERM` or `INT` while the supervisor runs, it
forwards that signal to the supervisor through `pidfd` only. The shell records
the supervisor's start ticks and session while it is still an un-reaped direct
child, and the dispatcher revalidates both against the open pidfd before
signaling. A `/proc` check followed by a numeric `kill` is not used, because
the pid could be reused between the two. If the supervisor's identity cannot
be established, the signal is refused, the shell keeps waiting, and cleanup
stays Unknown; there is no numeric fallback.

Public `unio kill TASK` accepts a background `run` whose pidfile, boot id,
start ticks, session, worker, and task all match the ownership record. It
sends `SIGTERM` to that shell and waits up to the existing 60 second cleanup
budget, comparing start ticks. It does not use `kill -0`. If the recorded
shell is still the same process when the deadline expires, kill reaps the
provider session first. Only a clear session may then pidfd-kill that shell's
current child tree, which is capped at depth 32 and 256 processes.

After validated signaling, the runner may complete its EXIT trap before kill
can reload the ownership record. Kill also accepts that terminal cleanup state:
the exact recorded shell is gone (or dead), and both the pidfile and ownership
entry are genuinely absent from the existing reports directory. The runner
removes these controls only on exit, after the normal owned-cleanup and final
capture path. An unreadable parent identity, a remaining file of any type,
including a dangling symlink, or an unavailable reports directory is not this
terminal evidence. This check does not authorize signaling without ownership
and does not change Source cancellation status or the cleanup deadline.

The worker and the account do not become free while a known owned live
provider remains. If the session cannot be proven clear, the command reports
Unknown, keeps the pidfile and the ownership file, and does not exit
successfully. A later clear reap preserves the provider's own exit code.
Exit 0 is available only when the provider exited 0 and cleanup was
established. Unknown is not reported as Source success.

## Final save

Baseline, periodic, and final saves keep their existing capture path. The
final save runs only after the provider-session sweep. It uses its own
session, so the sweep does not kill it. A cancelled `final-failure` save still
receives the existing capture budget: 30 seconds, or the legal
`UNIO_SAVE_CAPTURE_TIMEOUT` value from 1 to 300 seconds. Public kill does not
force the shell down before the 60 second deadline, so that bounded attempt
is not cut short.

No automatic worker retry, resubmission, quota inference, provider-output
policy change, or credential change is part of this cleanup.

The Unknown regression proof synchronizes on the supervisor's own cleanup
verdict, not on provider readiness: while the owned session is unproved, no
final save attempt for the task and no run completion may be observable, and
recovery must precede the final capture. Test-only fault injection through
the fault directory is scoped to `proc-stat` identity faults, so a marker for
one unreadable pid can never fail an unrelated save operation.

The recorded before/after proof uses an isolated installed copy with only the
supervisor's old if-and-log cleanup guard restored. The current proc-identity
fault fixture is retained in both copies. The mutation attempts a final save
while cleanup is Unknown and fails the regression; the corrected guard passes.
This does not claim the entire old revision was tested with a later fault hook.

## Failures

| Situation | Result |
| --- | --- |
| Pidfile text is empty, zero, negative, or not a decimal pid | No signal. Pidfile retained. Exit 1. |
| Live pid is not a Unio background run | No signal. Stale pidfile removed. Exit 1. |
| Ownership file is missing, malformed, or from another boot | No signal. Pidfile retained. Exit 2. |
| Ownership file has a boolean, string or otherwise non-integer identity field | No signal. Pidfile retained. Exit 2. |
| Recorded shell start ticks do not match the live pid | No signal. Pidfile retained. Exit 2. |
| Provider session still live, reused, or unproved after the deadline | Shell is not killed. Pidfile retained. Unknown. Exit 2. |
| Unproved same-user member identity in `/proc` | Treated as unproved rather than gone; session cleanup stays Unknown. |
| Owned provider cleanup returns Unknown at run termination | Final capture withheld; worker and account reservations stay held without Source success. |
| Supervisor identity cannot be revalidated at the `pidfd` | No signal to the supervisor. Cleanup stays Unknown. |
| `pidfd` is unavailable, or a protected pid shares the provider session | No `kill` fallback. Unknown. Ownership stays held. |

## Unverified boundaries

The offline fixtures are generic local processes; no live provider was
validated. The pidfd guarantee above applies to recorded identity dispatch and
the owned-session sweep. Existing provider timeout and capture paths also use
numeric process-group signals; this document does not claim that every signal
in the engine uses a pidfd. Two defenses are structural rather than reproduced: a pid reused
between observation and `pidfd` signaling is refused by the start-tick and
session revalidation, but that race is not deterministically reproducible in
the fixtures; and the early numeric `TERM` on a supervisor whose `/proc`
identity could not be read is exact only because an un-reaped direct child
cannot have its pid reused by the kernel.
