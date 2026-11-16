# Unio 0.5.33 — focused checks and existing-session controls

Prepared for release on 2026-11-16. Current-code review, lead assessment, the full release gate and isolated installation checks passed. The official tag, assets and local installation receipts identify actual delivery.

## Faster development checks

`bash tools/quality-check.sh --list` shows the command catalogue without running it. Select relevant checks with `--lane NAME`; selected lanes remain partial coverage. Set `QUALITY_TIMINGS` to record command timings. The default command still runs the full catalogue. Nested tests cannot overwrite the parent timing record, and an overridden test catalogue cannot claim a canonical full-gate PASS. No speedup or subscription-saving estimate is claimed yet.

## Keep your conversation

The opt-in `unio lead-session attach` controls connect through the current Codex shared server, retaining the exact existing thread and native history. Initial attachment requires an idle thread. Explicit phase signals select requested LOW/XHIGH for future turns; a manual choice suspends automatic phase selection until explicitly re-enabled. Current/queued requests and provider-effective Unknown remain separate.

This is a first existing-session connection, not a complete autonomous scheduler. It does not classify chat text, continuously watch workers or change a running turn. Transport and read-only metadata access were observed live; actual native effort-setting acceptance has not yet been exercised. Follow the [command guide](ADAPTIVE-LEAD-EFFORT.md) for the exact interface and limits.

Setting attempts retain intent and acknowledged/rejected/Unknown outcomes in bounded local journals. Re-enabling control grants authority and does not turn an unknown outcome into successful delivery. Read commands preserve absent state; later control commands reuse saved transport selections. A saved executable name is not a server identity proof across installations.

## Review and validation

Mistral subscription / Vibe 3.1.2 / requested GLM 5.3 High implemented the connector. Antigravity subscription / agy 1.5.9 / requested Gemini 3.8 Flash High reviewed the final combined candidate, then the existing OpenAI lead independently assessed it. Requested model and effort do not prove provider-effective identity or effort. The owner explicitly authorized this review route while Claude was unavailable. Earlier change requests, additional lead findings, corrections and operational failures remain preserved separately. Copilot Free Auto Balance supplied two supplementary documentation findings; its selected model and lab remain Unknown. The free OpenCode trial returned no usable artifact and does not count as review evidence.

The one full `bash tools/quality-check.sh` gate passed on frozen `72ab8aff4b4b2b8f197ab8e2e7a618e9a05565af` with tracked source unchanged and no provider calls, finishing 2026-11-16T23:16:35+01:00 after 5229.505 seconds. All 127 catalogue commands passed and produced ordered timing records. Private installation and all six offline checks passed. Final release preparation changes only the changelog, release notes and handoff; runtime, installer and test bytes remain identical to the reviewed and gated candidate. Global installation and official assets have separate receipts.

## Known limits

- A shortened non-ASCII error can omit one extra complete character at its boundary. The receipt remains valid and keeps the rejection classification; this minor prefix-completeness issue is deferred.

- Existing-session controls currently require the supported Codex shared-server interface; other lead CLIs retain their own behaviour.
- Implicit executable/socket defaults can change outside Unio. Explicit saved selections and exact loaded-thread acknowledgements bound control; effective model/effort remain Unknown.
- Attempt journals are bounded and never silently truncated. Full journals require deliberate evidence-preserving maintenance.
- The stock Copilot adapter needs a separate update for newer CLI flags and disabled-plugin handling. A successful private Auto Balance documentation check is not proof that the stock adapter has been fixed.

[Managed lead guide](ADAPTIVE-LEAD-EFFORT.md) · [Validation matrix](development/VALIDATION-MATRIX.md) · [Previous release](RELEASE-0.5.32.md)
