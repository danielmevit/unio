# Human native-run phases

Native run diagnostics use `unio: phase` on the run command's stderr. They
identify baseline, periodic, final and final-failure checkpoint attempt starts
and ends, including the existing selected capture budget. Invalid capture
configuration reports a skipped attempt; unavailable run identity skips saves.
An ended attempt does not establish that a checkpoint was saved: consult save
inspection and existing failure diagnostics for that evidence.

Provider launch starting precedes the spawn call; launched means that call
returned. The `exit` field means provider-command exit only on command completed. On
launch skipped or supervisor finalization it may instead be cancellation or run
status. Command completed reports the observed command exit before cancellation
can override the run result. Periodic capture does not imply provider completion.
Launch failure, refusal and cancellation before startup do not claim a launch.
Owned cleanup clear follows the existing owned-session sweep. Supervisor
finalization surrounds continuation bookkeeping and the final capture attempt;
it does not establish work validation, lead acceptance or release of the shell's
worker/account ownership. Existing STOP, timing and cleanup rules still apply.

Messages are fixed labels with bounded numeric fields, written best effort.
On Linux, ordinary pipes and TTYs use an independent nonblocking open through
`/proc/self/fd`; original and duplicate peer descriptor flags are never changed.
A full pipe drops the message, including when another writer fills it just before
the write. Regular files use the existing shared file position and append mode;
ordinary file writes can wait for filesystem I/O. There is no hard latency guarantee
for arbitrary filesystems, devices, descriptor races or OS operations. Unsupported
streams (including unavailable procfs reopening), failed writes and partial TTY
writes may lose diagnostics; no background writer or metadata scan is used. There is
no heartbeat and no phase persistence or machine protocol. Provider output stays
in the freshly truncated `coord/reports/<task>.log`; `unio tail` follows that
provider stream and does not contain all engine phases. With `-b`, the engine
stdout and stderr are discarded, so these phase diagnostics are discarded too. JSON commands, receipts
and provider-output parsing are unchanged.

Version 0.5.24 is an unreleased private candidate for the combined operational
batch; this slice does not authorize installation globally or publication.
