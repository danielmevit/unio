# Hardened observation of interrupted native runs

- Preserve native-safe worker and task identifiers: `_ident` now accepts canonical IDs containing colons (`T:1`), hyphens, dots, and safe Unicode without treating them as invalid or suppressing their terminal records and readiness.
- Bounded metadata enumeration: Enforce entry caps (`MAX_WORKERS` and `MAX_RECORDS`) during directory traversal before materializing, sorting, or filtering, returning incomplete (`Unknown`) observations when scan limits are reached.
- Precise shell PID verification: Require exact matching of boot ID, start ticks, UID, and session ID before labeling a background shell PID as live in status and doctor; surviving provider processes keep run state active without certifying unrelated or reused shell PIDs.
- Strict bounded JSON parsing: Reject duplicate keys, nonfinite constants (`NaN`, `Infinity`), deep recursion (exceeding depth 64 or 15000 nested arrays), and invalid schema/exit contradictions without tracebacks, consistently resolving to `Unknown` and `blocks_readiness=True`.
- Terminal exit invariants: Match native receipt rules; succeeded runs require exit code 0, failed runs require nonzero exit codes, and legacy failed runs with `exit_code: null` keep honest `Source exit: Unknown` without fabricating exit 0.
