# Capacity observation and admission

`unio disk [--json]` observes storage without a provider, including while STOP
is set. JSON schema version 1 contains `observed_at`, `measurements`,
`thresholds` and `overall`. Each measurement has status `known`/`unknown`, kind,
volume, available_bytes (null for Unknown), and reason. Output omits registry,
account and profile identifiers. Linux volumes use filesystem device IDs.
Exit 0 means the observation is usable (including Unknown); exit 2 means known
critical capacity or invalid input. Unknown is not evidence of adequate space.

Source (foreground/background), review and review-set check capacity before
provider admission, retry consumption or shared-lead consent consumption. The
existing Source no-follow write/fsync/permission probe remains in place.
Default critical threshold is strictly below 2 GiB; warning is below 10 GiB.
`UNIO_DISK_MIN_FREE_BYTES` and `UNIO_DISK_WARN_FREE_BYTES` accept only decimal
integers from 1 MiB through 1 PiB inclusive, with warning >= minimum. Invalid
settings refuse dispatch. Known critical dominates Unknown; warning takes
precedence over Unknown when both are observed. No cleanup or retry is implied.

Project/worktree, coordination and temporary filesystem observations use bytes
available to the invoking user. In WSL, Linux free space is never presented as
Windows host capacity. A fixed read-only PowerShell observer matches the current
WSL distro name exactly against Lxss metadata, requires one WSL2 entry, verifies
its VHDX file, and normalizes extended DOS paths before path resolution. It rejects reparse
files/ancestors (including folder mount points), then reads the verified fixed
drive root through System.IO.DriveInfo. Unsupported paths remain Unknown.
Registry values are data, never executable script. Only a verified drive root
and available bytes are returned. Missing interop, unsupported mappings,
ambiguous metadata, probe failure, oversized output or timeout yield Unknown.
The Windows probe bounds output at 4096 bytes and uses a 4.5-second wall
deadline, plus at most 0.1 seconds for child reaping after group cleanup. The
leader stays unreaped until that cleanup to prevent process-group reuse. Each
filesystem syscall probe (including temp-path selection) runs in a read-only
child with a 0.5-second deadline; a stalled filesystem yields Unknown.
Deadlines bound supported subprocess execution and pipe reads, not synchronous
OS process creation, executable lookup or an uninterruptible kernel operation.
A child stuck in such an operation may remain pending after bounded cleanup.
The retained writable-path/fsync probes also retain their synchronous syscall
limits. No universal wall-time or crash-prevention guarantee is made.
Native Windows metadata validation is unit tested; this does not add native
Windows CLI support. No user-disk scan or credential read is performed.

This is a point-in-time observation, not a reservation or universal crash
prevention guarantee. Storage can fill after admission; existing ENOSPC/EIO
failures retain their operational meaning. No historical receipts are rewritten
and no new receipt schema or sidecar is introduced. The incident's exact free
bytes at failure were not captured.
