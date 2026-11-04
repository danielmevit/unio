# Refuse deeply nested save JSON as invalid evidence

- Convert the decoder's `RecursionError` in the save helper's `strict_json` into the existing `invalid_save` refusal with the message "nested too deeply". A single deeply nested manifest no longer aborts `unio save inspect --worker`, `save inspect ID` or `save usage` with a traceback; it is skipped and counted as corrupt evidence like any other malformed manifest.
- Treat a deeply nested frozen task record in `coord/results/` like any other unreadable record during `unio save create`, falling back to the native `coord/base`.
- Size bounds, duplicate-key, non-finite and ordinary malformed-JSON refusals, selection, retention and STOP behavior are unchanged. Malformed bytes are preserved; nothing is cleaned up. Add `tests/unio-save-json-depth.py`, including the original 400001-byte reproduction.
