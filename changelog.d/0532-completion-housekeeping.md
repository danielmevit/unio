Keep an observed completed lead-session turn truthful when post-completion
waiting-flag housekeeping cannot take the per-session control lock (busy for
more than 5 seconds) or read the control state. `run` now still exits 0 with
`delivery: completed` JSON and adds a fixed `warning`. The stored flag is left
unchanged, and views keep computing truthful waiting. Only controlled refusals
are absorbed. Non-completed outcomes, replay idempotency and lock, owner, STOP
and admission controls are unchanged. New regressions cover this: an external
process holds the exact session lock across a genuine fake app-server
completion for 8 seconds, and registering a worker after the completed final
review, without `worker wait`, shows waiting False.
