Optional pinned Antigravity adapter: `tools/antigravity-worker.py` supports
agy 1.3.5 with the fixed Gemini 3.8 Flash high/medium/low selectors (no
generic effort flag), passes the bounded task as the single `-p` argv string
and refuses tasks above 64 KiB before any provider call, and parses the
native NDJSON stream strictly so a process exit 0 plus a terminal ERROR
result — even with a nonempty response body — can no longer look like a
successful completed agent call. Real native exits are preserved, raw
streams stay private, and the helper ships as the fourth packaged adapter
with a read-only `unio integrations` entry. Legacy raw agents.conf command
lines are untouched. This is an unreleased 0.5.18 candidate; the published
installer remains 0.5.17. No live AGY validation is claimed for this first
draft. The lead accepted only the later checked correction.
