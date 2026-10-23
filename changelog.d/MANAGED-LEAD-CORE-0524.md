MANAGED-LEAD-CORE-0524: add `tools/managed-lead.py`, an importable lead-session
state/controller backend with injected transport/authority/ownership, idempotent
no-replay request IDs, a bounded output journal and fake-transport tests; the
native caller contract is documented in `docs/development/MANAGED-LEAD-CORE.md`.
Backend component only — not installed lead continuity.
