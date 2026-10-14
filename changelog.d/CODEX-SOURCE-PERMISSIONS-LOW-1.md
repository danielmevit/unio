# Explicit managed Codex startup permissions

Managed Codex Source `run` accepts optional fixed `--sandbox` and
`--approval-policy` choices from the installed 0.162.1 startup schema. Omission
preserves inherited CLI settings; explicit choices reach only `thread/start`.
Live worker-effort requests still cannot change permissions or startup settings.
The installed guide documents local and authorized trusted-host opt-ins, real
shared-group mapping, lead reservation and the limits of worktree isolation.
Offline installed tests cover omission, supported choices, invalid arguments,
effort refusal and existing native/channel/cancellation behavior. No model
probe or writable native acceptance is performed by this Source.
