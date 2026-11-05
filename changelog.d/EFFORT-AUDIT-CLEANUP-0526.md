# Leave no process behind after the read-only effort audit

- Run the `worker-effort` native command audit in its own process session. On completion, timeout or oversized output, kill its whole process group while the leader is still unreaped, then read the result. Previously a timed-out audit killed only the direct child, so its descendants could keep running, and a completed audit could leave background descendants.
- Stop an audit as soon as its output exceeds the existing 128 KiB bound instead of letting it write until the 15-second timeout. The result is still the existing `invalid_agents_conf` Unknown outcome.
- Clarify in the effort guide that `requested_model` privacy relies on the trusted native audit parser's fixed model-name patterns; the helper validates structure and bounds but does not re-check model names.
- Add `tests/unio-effort-audit-cleanup.py` with real processes: hung, completed-with-background and flooding audits. Move the existing validator test's mock to the new runner boundary.
