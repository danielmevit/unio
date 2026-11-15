0532-TRANSPORT-CORRECTIONS: close the six REQUEST-CHANGES findings of the
independent owned-transport review (contract
0532-ADAPTIVE-TRANSPORT-CORRECTIONS-V6) on the native `unio lead-session`
slice. High: the run command's stale pre-turn snapshot can no longer
overwrite concurrent control state — control-state changes are now short
per-session locked transactions (coord/lead-effort/<session_id>.lock,
never held across a model/RPC turn) and `run` merge-persists its own
effects (proven provider mappings, immutable decisions, at-most-one
pending-effort and wakeup consumption) into the freshly re-read control
state, so a pending effort request, worker terminal wakeup or STOP
arriving during an active turn survives and a pending effort applies
only from the next turn on. Medium: `ProviderRejected` is now a `Refusal`
subclass preserving the rejected method, provider code and bounded
reason, so RPC rejections on initialize/account/model/thread operations
exit as controlled refusals instead of raw tracebacks (typed turn/start
rejection in the bridge is unchanged and stays distinct from uncertain
acknowledgements); a child EOF during the turn wait is flagged, the final
buffered terminal events and stderr diagnostics are drained, and the wait
stops promptly instead of busy-polling until the deadline with no
inferred success. Low: run payloads now separate submission
acknowledgement (`status`), actual turn outcome (`turn_status`,
`delivery`) and observed native exit (`provider_exited` plus a bounded
private `stderr_tail`) with truthful exit codes (0 only for an observed
completed turn or an explicit `--turn-wait 0` async acknowledgement;
2 rejected, 3 uncertain, 4 failed, 5 interrupted, 6 pending/timed-out);
native stderr is captured bounded instead of discarded; and mutating
controls require the current workspace owner even with an explicit
`--session` while read-only views of a retired session are labelled
`historical`. Tests overlap real CLI processes against a delayed fake
turn/start RPC and cover typed initialize rejection, crash and
wait-loop-death diagnostics and the exit-code matrix; original typed
failures, STOP semantics, zero-call guarantees and the frozen
worker/core/bridge contracts are preserved unchanged. Unreleased.
