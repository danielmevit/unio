0532-FIRST-TURN-PERSISTENCE: fix the confirmed live failure where the first
owned `unio lead-session run` refused with `thread/resume -32600 no rollout
found`. The Codex app-server writes a thread's rollout only with its first
turn. A zero-inference codex-cli 0.169.0 control showed no rollout after
`thread/start` or after a clean exit, and same-process resume also refused.
`start` no longer creates a thread. The first `run` creates the exact thread
in its own process immediately before its first `turn/start`, saves the id
first and never resumes it there. Later runs resume that same id. There is no
bootstrap or dummy turn and no replacement after a resume refusal.

Control state gains `thread_lifecycle`. Older state stays readable as
`legacy`, and a legacy thread that never ran a turn refuses with the native
error. Run payloads report `thread_created`, `thread_unavailable`,
`discarded_unused_thread_id` and the verbatim `not_sent_reason`. The offline
fixture now materializes threads lazily, and the old start reproduces the
live error. The embedded installer helpers have been regenerated.
