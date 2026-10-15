# Native stop ownership contract

Source note for the installed public native run and kill path. Product version
stays 0.5.18. This note does not claim a live provider was validated; the
offline fixtures are generic local processes.

## Ownership boundary

Before the provider command is executed, the native shell writes
`coord/reports/TASK.own`. The file is private JSON. It records schema version
1, the current boot id, the worker, the task, and the shell pid, start ticks,
and session. Provider fields stay null until the supervisor has created the
provider session.

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
| Recorded shell start ticks do not match the live pid | No signal. Pidfile retained. Exit 2. |
| Provider session still live, reused, or unproved after the deadline | Shell is not killed. Pidfile retained. Unknown. Exit 2. |
| `pidfd` is unavailable, or a protected pid shares the provider session | No `kill` fallback. Unknown. Ownership stays held. |
