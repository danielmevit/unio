# Unio 0.5.33 — focused checks and existing-session controls

Release candidate prepared 2026-11-16. Publication and installation are pending the current-code review, lead assessment and full release checks.

## Faster development checks

`bash tools/quality-check.sh --list` shows the command catalogue without running it. Select relevant checks with `--lane NAME`; selected lanes remain partial coverage. Set `QUALITY_TIMINGS` to record command timings. The default command still runs the full catalogue. Nested tests cannot overwrite the parent timing record, and an overridden test catalogue cannot claim a canonical full-gate PASS. No speedup or subscription-saving estimate is claimed yet.

## Keep your conversation

The opt-in `unio lead-session attach` controls connect through the current Codex shared server, retaining the exact existing thread and native history. Initial attachment requires an idle thread. Explicit phase signals select requested LOW/XHIGH for future turns; a manual choice suspends automatic phase selection until explicitly re-enabled. Current/queued requests and provider-effective Unknown remain separate.

This is a first existing-session connection, not a complete autonomous scheduler. It does not classify chat text, continuously watch workers or change a running turn. Transport and read-only metadata access were observed live; actual native effort-setting acceptance has not yet been exercised. Follow the [command guide](ADAPTIVE-LEAD-EFFORT.md) for the exact interface and limits.

Setting attempts retain intent and acknowledged/rejected/Unknown outcomes in bounded local journals. Re-enabling control grants authority and does not turn an unknown outcome into successful delivery. Read commands preserve absent state; later control commands reuse saved transport selections. A saved executable name is not a server identity proof across installations.

## Review and validation

The implementation is frozen at `28d855039200d486719f4273d5f92c3b5726dfae`. Its 62 connector checks, embedding parity, installer syntax and documentation checks passed native verification. The lead independently checked seven repaired behaviours using fake transports. The validation-runner suite has 71 passing assertions. The last delivered independent review requested changes; the final cumulative current-code review is in progress. Its eventual verdict, the full gate, installation and publication have separate receipts; none is inferred from a process exit.

The release layer changes only the version declaration and three release Markdown files. Full runtime/test checks remain pending at this checkpoint. The final notes will record actual results before publication.

## Known limits

- Existing-session controls currently require the supported Codex shared-server interface; other lead CLIs retain their own behaviour.
- Implicit executable/socket defaults can change outside Unio. Explicit saved selections and exact loaded-thread acknowledgements bound control; effective model/effort remain Unknown.
- Attempt journals are bounded and never silently truncated. Full journals require deliberate evidence-preserving maintenance.
- The stock Copilot adapter needs a separate update for newer CLI flags and disabled-plugin handling. A successful private Auto Balance documentation check is not proof that the stock adapter has been fixed.

[Managed lead guide](ADAPTIVE-LEAD-EFFORT.md) · [Validation matrix](development/VALIDATION-MATRIX.md) · [Previous release](RELEASE-0.5.32.md)
