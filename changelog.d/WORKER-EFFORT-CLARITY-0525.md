# Read-only configuration clarity and absent-channel explanation for worker-effort

- Surface truthful read-only configuration facts under `current_configuration`
  for `unio worker-effort WORKER [--json]` when a worker lacks an active supported
  control channel (such as legacy exec or other routes), explaining channel absence.
- Tag discovered configuration provenance as `static_agents_conf` and scope as
  `future_launch` so newly edited configuration is never attributed as proof of an
  already-running worker's startup settings.
- Missing, ambiguous, compound, wrapped or unknown routes fail safely to Unknown
  with actionable reasons; malicious shell tokens and secret values are never
  executed or reflected in output.
- Distinguish model reasoning effort from coordination tier and review pace.
- Preserve existing authoritative active-channel views, exact schema validation,
  nonzero exit on unsupported workers, and fail-closed live-set requests.
