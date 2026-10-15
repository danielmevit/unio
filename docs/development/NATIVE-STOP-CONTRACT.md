# Native stop ownership contract

Source note for the installed public native run and kill path. Product version
stays 0.5.18. This note does not claim a live provider was validated; the
offline fixtures are generic local processes.

## Ownership boundary

Before the provider command is executed, the native shell writes
`coord/reports/TASK.own`. The file is private JSON. It records schema version
1, the current boot id, the worker, the task, and the shell pid, start ticks,
and session. Provider fields stay null until the supervisor has created the
provider session. `schema_version` must be the exact integer 1; a JSON `true`
is refused, because Python compares `True == 1`. Pid and start-tick fields
must be JSON integers, not strings or floats.

The supervisor starts that session with `setsid`, reads the new process from
`/proc`, and requires its session id to be its own pid and to differ from the
shell session. It stores the provider pid, session, and start ticks, and only
then lets `timeout` exec. Ownership therefore exists before the provider runs.

An owned process is a live process in that recorded session, running as the
same user, and not a zombie. It may leave the original process group. It may
be reparented when an intermediate launcher exits. It stays owned while its
session id is the recorded provider session.

The sweep does not use `pgrep` or `pkill`, and it does not match command text.
A signal is sent with `pidfd` only after the open pid still has the recorded
start ticks and session. The shell, the supervisor, and the supervisor's parent
are never treated as members of the provider session. If one of those protected
pids is inside that session, or the leader pid is now a different process, the
result is Unknown and nothing is signaled.

`/proc/PID/stat` is split at the last `)`, not the first one, on both the
shell and the Python side. A comm that itself contains `)` therefore cannot
shift the stat fields and forge a start-tick or session match.

A recorded identity cannot redirect a signal to another run. Before anything
is signaled, the live target must match the ownership record's boot id, shell
pid, start ticks and session, must run as the same user, and must have the
exact `bash unio run WORKER TASK` command line of that record. Another run has
a different shell pid, start and session; a reused pid has different start
ticks; a helper or Source identity from one run never matches another run's
record. The provider session must additionally be led by the recorded pid
with the recorded start ticks and must differ from the shell session, so a
foreign session cannot be swept by presenting this run's identity.

These cases are outside the boundary. Cleanup is not claimed for them:

- A helper that calls `setsid` and leaves the provider session.
- The shell session itself, including a foreground terminal, the lead, another
  worker, or an unrelated sibling.
- An external `SIGKILL` of the runner. The kernel drops the worker lock when
  that process dies. No daemon is installed to reclaim it.

## Stop, cancellation, and normal exit

On cancellation and on a normal provider exit, the supervisor reaps the
provider session before it starts the final save. Cooperative children receive
`SIGTERM`. Children that ignore `SIGTERM` are then `SIGKILL`ed. The shell waits
until that reap reports the session clear, and only then releases the worker
lock and the native account slot.

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

## Failures

| Situation | Result |
| --- | --- |
| Pidfile text is empty, zero, negative, or not a decimal pid | No signal. Pidfile retained. Exit 1. |
| Live pid is not a Unio background run | No signal. Stale pidfile removed. Exit 1. |
| Ownership file is missing, malformed, or from another boot | No signal. Pidfile retained. Exit 2. |
| Ownership file has a boolean, string or otherwise non-integer identity field | No signal. Pidfile retained. Exit 2. |
| Recorded shell start ticks do not match the live pid | No signal. Pidfile retained. Exit 2. |
| Provider session still live, reused, or unproved after the deadline | Shell is not killed. Pidfile retained. Unknown. Exit 2. |
| Supervisor identity cannot be revalidated at the `pidfd` | No signal to the supervisor. Cleanup stays Unknown. |
| `pidfd` is unavailable, or a protected pid shares the provider session | No `kill` fallback. Unknown. Ownership stays held. |

## Unverified boundaries

The offline fixtures are generic local processes; no live provider was
validated. Two defenses are structural rather than reproduced: a pid reused
between observation and `pidfd` signaling is refused by the start-tick and
session revalidation, but that race is not deterministically reproducible in
the fixtures; and the early numeric `TERM` on a supervisor whose `/proc`
identity could not be read is exact only because an un-reaped direct child
cannot have its pid reused by the kernel.
