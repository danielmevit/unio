# PROTOCOL-NAMES-VIBE-1 — public protocol command names

Unio development source: `unio mode` now speaks the public protocol names
`yolo`/`balanced`/`thorough` everywhere it is displayed (mode command,
human policy, status/init output, worker prompt headers, help and
completion) while the stored schema-1 enum stays `yolo`/`medium`/`safe`
for older runners; `medium`/`safe` remain accepted input aliases,
`unio policy --json` keeps `mode` and adds `protocol` with the public
name, and `tests/unio-work-policy.py` covers every name, alias,
persistence, axis independence, frozen old-policy acceptance and
invalid/no-write refusals.
