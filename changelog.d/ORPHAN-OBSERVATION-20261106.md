### Fixed

- Native runs orphaned by a host or WSL crash now show one read-only `runtime_observation` in `result`, `report`, `status`, `watch` and handoff, with `completion_unknown` and Source exit Unknown. Original evidence is unchanged and nothing is retried or signalled.
- `unio report TASK` is useful when a crash left no report file, and fabricates none.
- `unio status` no longer trusts a raw PID or process-name match as running and no longer deletes `.pid` evidence. See `docs/INTERRUPTED-RUNS.md`.
