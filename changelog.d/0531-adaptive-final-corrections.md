### Fixed (final adaptive-lead review corrections, contract 0531-ADAPTIVE-REVIEW-CORRECTIONS-V7)

- `unio lead-session run` on the owned transport no longer kills an in-flight turn at a short wait and labels it
  `pending`. It keeps the owned app-server alive until the turn's terminal event or `--turn-wait` (default now
  3600 seconds). At the deadline it sends `turn/interrupt` for the exact proven thread and turn, drains terminal
  events (`--interrupt-drain`, default 30 seconds) and reads the provider's own thread state. An interrupt
  acknowledgement is not terminal proof: without a terminal event the delivery is `unknown` (exit 6), the turn
  stays active and nothing is resent. `--turn-wait 0` is refused before launch. This supersedes the
  `--turn-wait 0` exit-0 and `pending` wording in `0532-transport-corrections.md`.
- New `unio lead-session recover [--interrupt] [--drain N]` reconciles a proven stale turn on the SAME thread
  from the provider's thread state and, when asked, requests an exact `turn/interrupt`. It never starts or resends
  a turn, never fabricates a terminal and never resets the thread; an unacknowledged turn refuses.
- A provably rejected or never-sent turn no longer uses up the pending effort request or the worker review wakeup.
  Newer concurrent controls are kept, the attempted decision stays visible with outcome `rejected`, and uncertain
  attempts are never restored. Reaching the local provider-turn mapping bound is now a known non-delivery
  (`rejected`, no RPC) instead of `uncertain`, so it no longer blocks the session.
- The lead-session policy reader accepts the native 65536-byte work-policy bound; malformed, unreadable and
  oversized files still fail closed. The embedded lead role card says Fast instead of YOLO, matching its source.
- Docs: the starter guide keeps its fixed-effort prompts and tells the pasted-into AI not to start a nested managed
  lead; the optional managed trial is a separate owner-driven terminal sequence. The adaptive guide documents
  replay as "no new turn starts", session lifetime limits, approval rejection and inherited sandbox settings.
  Antigravity docs and release notes now match the latest-CLI policy (versions are provenance, not a gate).
- Offline only: the executable fake app-server progresses a turn only while its own process lives. No real Codex
  model call was made; live interrupt and stale-turn behaviour remain Unknown.
