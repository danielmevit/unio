MANAGED-LEAD-CORE-0524: add `tools/managed-lead.py`, an importable lead-session
state/controller backend with injected transport/authority/ownership, idempotent
no-replay request IDs, a bounded output journal and fake-transport tests; the
native caller contract is documented in `docs/development/MANAGED-LEAD-CORE.md`.
Backend component only — not installed lead continuity.
Correction: bind persisted identity/turn relationships, report journal/metadata
mismatches without repair, and replace state using exclusive private temp files;
add controlled corruption, unsafe-file and persistence-failure regressions.
Independent-review correction: validate complete state before replacement, preserve conflicting observations as uncertain, distinguish journal failures from archive caps, reserve closing-marker space, and bound external lifecycle integers; add direct/fault-injection regressions and document unrepaired crash windows.
Focused correction: preserve matching pending output activity across contradictory rejection and journal/save failures; test all output kinds, reopen and no-replay, clarify Refusal effects and deferred recovery/I/O limits.
Retention-order correction: save valid exact active pending activity before archive-closed/oversized refusal; cover retention boundaries, separate observers, old/wrong turns and late-after-rejection limits.
