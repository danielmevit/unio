0531-EFFORT-FIRST-DISPLAY: implement owner contract V8 / V8A effort-first
presentation in `unio lead-session`. Concrete requested reasoning effort
(LOW or XHIGH) is now primary in lead status, effort show, manual/request
controls, and startup acknowledgements; adaptive policy mode is secondary.
The active requested effort derives strictly from the durable decision for the
exact current running turn, reporting 'not started' prior to the first turn and
'no active turn' when idle or waiting with truthful last attempt and status.
A queued next-turn effort request is displayed separately without overwriting
the running turn. Provider rejections are disclosed honestly as undelivered
attempts without claiming effort was used. Read-only commands (`status`,
`effort show`) make zero provider calls. Backward compatibility for legacy JSON
fields (`effort.mode="auto"`) is preserved, supplemented with additive
`effort_display` and `current_request` structured views. Added documentation
`docs/LEAD-EFFORT-DISPLAY.md` and regression suite
`tests/unio-lead-effort-display.py` registered in `tools/quality-check.sh`.
