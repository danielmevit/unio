- Switch the pinned Vibe worker's provider invocation to the installed CLI's
  documented `--output streaming` NDJSON route; keep every raw byte in the
  existing bounded private native stdout log and flush public progress promptly.
- Print only fixed allowlisted operational labels from recognized message
  roles and tool events (assistant response/reasoning observed, reading,
  editing or writing file, running shell command, searching files, updating
  task list, tool call/tool failure observed). Unknown events are counted,
  never invented progress; no raw text, prompts, tool arguments/results,
  paths, commands, exports, auth or error text is emitted.
- Add a modest liveness-only heartbeat (about 30 seconds of silence), clearly
  distinct from observed provider/tool events; it claims no reasoning, task
  success, readiness, quota or token savings.
- Bound incremental NDJSON parsing: split UTF-8/records reassembled, multiple
  records per chunk, malformed/oversized/deeply nested records counted and
  dropped, 256 KiB record cap, 10,000 public line cap; overall output bounds
  and owned group/time/cancellation handling unchanged.
- Keep preflight quiet and final receipt/export semantics backward compatible
  with nonzero native exits intact; receipt and final line add bounded progress
  counts and last-observed metadata while requested/effective Unknowns remain.
- Add offline fake-CLI regressions: public progress before child exit,
  heartbeats distinct from actual events, partial/malformed/hostile stream
  safety, no sensitive payload leaks, failure exits with export validation and
  cleanup intact; existing adapter tests keep asserting original behaviors.
- Update the integration and progress docs with the exact supported route and
  limitations; refresh the embedded installer payload (adapter bytes only, no
  version bump, permissions or unrelated sections).
