# Admission handshake deadlines

`UNIO_ADMISSION_TIMEOUT` bounds the Source, review and review-set admission
holder reply. It accepts ASCII whole seconds 1..300 (up to three digits),
default 30. Set it to `5` for the former five-second deadline. It does not
change provider run, review or verification timeouts. Invalid values refuse
before opening admission IPC or consuming an owner grant.

Deadline, EOF, partial reply and holder refusal diagnostics include the configured
seconds and observed phase. Storage errors retain their storage marker. These
observations do not establish a filesystem root cause or exhausted capacity.
Only an actual capacity refusal suggests inspecting occupied slots/reservations.
No failed handshake starts a provider, queues or retries. Uncertain grant
consumption is never restored. Reports remain append-only; stderr remains the
failure channel if report storage fails.

Related helper deadlines (installer source, deliberately unchanged):

- `capture_seconds` / `UNIO_SAVE_CAPTURE_TIMEOUT`: configurable 1..300, default
  30, for save capture. `Budget`, `CAPTURE_SECONDS` and `RESTORE_SECONDS` also
  bound observations (30 seconds) and restore (120 seconds).
- `_await_byte` / `spawn_owned_provider`: separate provider startup acknowledgement
  deadline, independent of policy admission.
- Result and experience helpers are inventoried in the task handoff after focused
  checks. Their deadlines should be evaluated separately with owned timing
  evidence; this change does not extend unrelated operations.
