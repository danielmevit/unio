# Human native-run phases

Native run diagnostics use `unio: phase` on the run command's stderr. They
identify baseline, periodic, final and final-failure checkpoint attempt starts
and ends, including the existing selected capture budget. Invalid capture
configuration reports a skipped attempt; unavailable run identity skips saves.
An ended attempt does not establish that a checkpoint was saved: consult save
inspection and existing failure diagnostics for that evidence.

Provider launch starting precedes the spawn call; launched means that call
returned. Command completed reports the observed command exit before cancellation
can override the run result. Periodic capture does not imply provider completion.
Launch failure, refusal and cancellation before startup do not claim a launch.
Owned cleanup clear follows the existing owned-session sweep. Supervisor
finalization surrounds continuation bookkeeping and the final capture attempt;
it does not establish work validation, lead acceptance or release of the shell's
worker/account ownership. Existing STOP, timing and cleanup rules still apply.

Messages are fixed labels with bounded numeric fields, written best effort without
waiting for a full diagnostic stream. A failed write drops the message. There is
no heartbeat and no phase persistence or machine protocol. Provider output stays
in the freshly truncated `coord/reports/<task>.log`; `unio tail` follows that
provider stream and does not contain all engine phases. JSON commands, receipts
and provider-output parsing are unchanged.

Version 0.5.24 is an unreleased private candidate for the combined operational
batch; this slice does not authorize installation globally or publication.
