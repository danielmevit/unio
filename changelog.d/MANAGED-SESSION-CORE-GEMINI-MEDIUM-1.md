### Added
- Implement the frozen first managed-session CLI slice: `unio session status`, `output`, and `send` for the opt-in managed Codex Source (`tools/codex-worker.py`).
- Record session output and lifecycle facts under `coord/sessions/` (`<session_id>.output.jsonl` and `<session_id>.json`), supporting output reconnect and historical inspection of completed or failed runs without provider calls.
- Support current-turn steering via supported `turn/steer` RPC with 8 KiB UTF-8 file bounds, bounded request IDs, idempotent repeated requests, and non-replay of uncertain or failed transports.
- Add `docs/MANAGED-SESSIONS.md` documentation, embed it alongside `tools/codex-worker.py` and `docs/WORKER-EFFORT.md` in `unio-install.sh`, and register `tests/unio-managed-session.py` in `tools/quality-check.sh`.
