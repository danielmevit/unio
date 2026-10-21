# Admission handshake deadlines

`UNIO_ADMISSION_TIMEOUT` bounds the Source, review and review-set admission
holder reply. It accepts ASCII whole seconds 1..300 (up to three digits),
default 30. Set it to `5` for the former five-second deadline. It does not
change provider run, review or verification timeouts. The handshake clock starts
after private IPC setup and covers holder startup plus its five-line reply;
cleanup and report writes are separate operations. Invalid values refuse
before opening admission IPC or consuming an owner grant.

Deadline, EOF, partial reply and holder refusal diagnostics include the configured
seconds and observed phase. Storage errors retain their storage marker. These
observations do not establish a filesystem root cause or exhausted capacity.
Only an actual capacity refusal suggests inspecting occupied slots/reservations.
No failed handshake starts a provider, queues or retries. Uncertain grant
consumption is never restored. Reports remain append-only; stderr remains the
failure channel if report storage fails.

Related helper deadlines (deliberately unchanged; installer symbols are stable
search anchors):

| Helper / source | Bound | Configurable? |
| --- | --- | --- |
| `unio-install.sh`: `capture_seconds`, `capture_child`, `create_locked` | Save capture 30 seconds, monotonic budget | `UNIO_SAVE_CAPTURE_TIMEOUT`, 1..300 |
| `unio-install.sh`: `CAPTURE_SECONDS`, `Budget`, `observe`, `RESTORE_SECONDS` | Other save observations 30 seconds; restore 120 seconds | Fixed constants; capture override does not globally change these |
| `unio-install.sh`: `spawn_owned_provider`, `_await_byte` | Provider session readiness 2 seconds; owned supervisor acknowledgement 15 seconds | Fixed |
| `unio-install.sh`: `quality` Python `git`, `snapshot`, `cmd_evidence`, `handoff` | Native result/handoff and result-start snapshot have no enclosing wall deadline; Git subprocess has no timeout | No native result deadline option |
| `tools/model-experience.py`: `RECORD_DEADLINE_SECONDS`, record's `fleet.observe` | Native result observation for recording: 30 seconds | Fixed |
| `tools/model-experience.py`: `LOCK_WAIT_SECONDS` | Experience store lock wait: 5 seconds | Fixed |
| `tools/model-experience.py`: `SUGGEST_TIMEOUT_DEFAULT`, suggest's `fleet.collect` | Suggest observation: default 10 seconds | `experience suggest --timeout`, 1..60 |

A separate follow-up should measure result-start/result snapshot cost on owned
slow-storage fixtures, then consider bounding native result/Git work and aligning
experience's 30-second observation with that contract. Extending admission alone
does not fix or diagnose an unrelated result helper delay. No expensive Git or
status operation was added to the admission handshake.

Regression coverage installs into project-local scratch, exercises the installed
Bash and embedded Python functions before CLI dispatch, and uses a marker at the
provider boundary. Fault injection is confined to that installed test copy; no
new production bypass or delay switch is added. Native CLI STOP and the existing
lead-budget regression additionally exercise public entry points and single-use
concurrency. The historical `budget-refused` receipt heading remains compatible;
the phase/reason determines whether a failure actually concerns capacity.
