# Effort presentation V8

## Current effort is primary; adaptive policy is secondary

Owner instruction: show concrete current requested LOW/XHIGH prominently in Unio lead status/CLI/UI. AUTO/adaptive describes how the next request is selected; it must never replace the effort value or become the main effort label. Show a queued next-turn choice separately, without changing the running turn's display. When idle/waiting show no active turn, optionally the last requested effort, not an invented active level. If no current level is known, say Unknown/not started. Retain requested versus provider-effective Unknown honestly; settings are not proof of actual reasoning. An unmanaged AI CLI remains outside Unio control, and Unio must not claim it changed that CLI's own effort header. Preserve low/xhigh selection/manual override and backwards-compatible machine fields.

## Implementation and review acceptance

Display derives from the durable decision for the exact current turn, never the ceiling, baseline or a pending next choice. Current rejected/uncertain/successful attempted requests remain distinct from effective effort and from last completed activity. Main status and effort show/run acknowledgement/manual/request feedback put requested LOW/XHIGH (or truthful inactive/Unknown state) before secondary adaptive/manual policy. Keep legacy JSON fields; additive structured display fields are allowed. No inference, writes or provider calls for read-only display.

Apply the same hierarchy in first-time guides, starter prompts and onboarding plan: a plan has no active level, so say current effort not started/Unknown, with adaptive policy optional and secondary. Never claim a plan is a live managed lead. Basic mode/pace names remain Fast/Balanced/Thorough, coordination tier separate. No redesign or takeover of the existing Codex TUI.

Regression tests: active LOW/XHIGH matches exact turn, a queued opposite level stays next-only, idle/waiting displays no active request and last appropriately, pre-first-turn Unknown/not started, manual-versus-adaptive secondary, accepted/rejected/uncertain freshness, historical view labelled, zero provider calls and existing JSON compatibility. Human copy gets Opus5.5 MEDIUM plus existing lead assessment. Do not alter an active frozen task to add requirements; finish it normally, then scope this bounded correction on its committed result.
