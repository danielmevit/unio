# Antigravity (agy) Gemini 3.8 Flash

Unio packages `tools/antigravity-worker.py` as an optional, explicitly
pinned Antigravity CLI worker. It exists to keep one failure mode honest:
the Antigravity CLI can exit its process with status 0 while its structured
result stream reports a terminal `ERROR`, sometimes alongside a nonempty
response body. A raw exit-0 check reads that as a successful completed agent
call. This adapter never does: the process exit and the structured terminal
status are evaluated separately, and both must be clean for exit 0.

## What the adapter pins

The adapter supports the inspected `agy` 1.3.5 only; any other `--version`
output is refused before a provider call. It selects one fixed Gemini 3.8
Flash variant advertised by that CLI:

| Selector | Requested model | Requested effort |
| --- | --- | --- |
| `high` (default) | `gemini-3.8-flash-high` | high |
| `medium` | `gemini-3.8-flash-medium` | medium |
| `low` | `gemini-3.8-flash-low` | low |

The generic `--effort` flag is never passed: these fixed variants embed the
effort level, and agy 1.3.4 rejected a matching high model plus a separate
effort flag before inference. Requested effort is derived from the selector
name only. The effective model, AI lab, effort and remaining allowance stay
`unknown`: the adapter does not verify what the account actually served.
There is no fallback model, no retry and no second invocation.

## Prompt transport and its bound

The task comes from `--prompt-file` or `$TASKFILE` as a bounded regular
UTF-8 file. `agy` has no prompt-file flag. Its help documents an NDJSON
stdin input mode, but the message schema of that mode is not established
from help or owned logs, so the adapter does not guess a stdin format and
never truncates a task to fit. The proven native transport is the print-mode
`-p` argument, so the whole task text travels as that single argv string.

Linux caps one argv string at 131072 bytes (`MAX_ARG_STRLEN`) — the exact
bound that made the legacy `$(cat "$TASKFILE")` line fail with
`Argument list too long`. The adapter refuses tasks larger than 65536
bytes (half the kernel bound) with outcome `task_exceeds_argv_bound`
before any provider call, including the version preflight. Split large
work into smaller tasks instead of raising the bound.

## Native versus adapter exit contract

The invocation is `agy -p <task> --mode accept-edits --model <selector>
--dangerously-skip-permissions --disable-slash-commands --print-timeout <limit>
--output-format stream-json`, run in the adapter's current working
directory. The raw NDJSON stream is preserved in a private
`native-stdout.log`; the adapter parses only the top-level
`event`/`result` envelope. Text inside assistant or tool content never
produces a verdict, and a forged result record inside streamed content is
ignored.

| Condition | Adapter exit | Receipt outcome |
| --- | --- | --- |
| Native 0 plus exactly one valid terminal `SUCCESS` with no error | 0 | `terminal_success` |
| Native 0 plus terminal `ERROR` (with or without a response body) | 2 | `terminal_error` |
| Native 0 plus missing, duplicate, unknown-status or wrong-typed terminal record | 2 | `missing_terminal_result`, `ambiguous_terminal_result`, `unknown_terminal_status`, `invalid_terminal_*` |
| Native 0 plus a `SUCCESS` that still carries an error | 2 | `success_with_error` |
| Native 0 plus malformed stream (split record, duplicate key, non-finite value, invalid UTF-8) | 2 | `invalid_stream_*` |
| Native nonzero exit 1..255 | the same code | `native_failed` |
| Native death by signal | 128 + signal | `native_signal` |
| Adapter deadline reached | 124 | `timeout` |
| Output above 8 MiB | 2 | `output_limit` |
| Cancelled (SIGTERM) | 130 | `interrupted` |

A response body alongside `ERROR` never repairs the verdict, but it is
preserved in the private raw log. A terminal `SUCCESS` is provider/CLI
evidence of a completed turn, not verified code acceptance, review or
remaining capacity. The native process exit is recorded separately in the
receipt (`native_exit`) from the adapter exit (`adapter_exit`).

## Trusted host and permissions

The adapter runs on the trusted host: the parent shell, the `agy`
installation and its native Google account credentials are all
`trusted_host`, and `sandbox` is false. `--dangerously-skip-permissions`
matches the owner's proven invocation (the stream reports
`permission_mode: always-proceed`); it is an execution control, not an
operating-system sandbox. `--mode accept-edits` and
`--disable-slash-commands` preserve established print-mode flags without
interactive edit prompts or slash command expansion. The adapter reads
no credential, changes no plugin, MCP, auth or billing setting, and performs
no network request itself. Each invocation owns one new process group with
bounded stdout, stderr, time and cleanup; only that group is signalled.

## Manual setup

Install the official Antigravity CLI yourself and sign in with `agy` in
your terminal; Unio installs nothing and authenticates nothing. Then add an
explicit alias to your existing `agents.conf` without touching its other
entries, create a private receipt parent (mode 0700, outside the checkout),
and map the budget:

```text
antigravity=python3 '/absolute/path/to/unio/tools/antigravity-worker.py' --receipt-dir '/absolute/private/antigravity-runs'
```

With the packaged installer the helper path is
`~/.config/unio/lib/adapters/antigravity-worker.py` (or under
`UNIO_CONF_DIR`). Then:

```bash
unio account antigravity antigravity
unio resume
UNIO_TIMEOUT=3900 unio run antigravity-feature TASK-ID
unio stop
```

Keep the outer Unio deadline above the adapter deadline plus shutdown
margin. All aliases on the Antigravity subscription share one budget
group; low tier permits one independent workflow in that group.

## Receipts and privacy

Each run creates a new 0700 directory under the receipt parent holding a
0600 frozen task copy, the raw native stdout/stderr logs and a receipt
with the pinned selectors, task hash, bounds, native and adapter exits and
the terminal verdict. Public stdout carries only finite operational
metadata: receipt path, exits, outcome and terminal status. Terminal status
is allowlisted to `SUCCESS`, `ERROR`, or `null` when missing or unrecognised,
so provider-supplied status strings never leak outside the private raw log.
Prompts, answers, provider error text and conversation IDs never appear
publicly; keep the raw logs private. Legacy raw `agents.conf` command lines
are left untouched: the adapter is opt-in, and a legacy line keeps its own
native behavior.

## Trial status

The adapter passed focused offline fake-CLI regressions only. No live
Antigravity call was made through this adapter, and no fake fixture
demonstrates provider behavior, code security acceptance or remaining
allowance. Owned logs that motivated the verdict logic recorded one
process-0/terminal-`ERROR` run with a nonempty response and one clean
process-0/terminal-`SUCCESS` probe on agy 1.3.5 with
`gemini-3.8-flash-high`; both stay private. The adapter is in the
unreleased 0.5.18 candidate. Tags, the public download and the global
installation remain 0.5.17. A bounded Copilot correction was still running
on frozen adapter `fa9b964` when this candidate was prepared, so that live
outcome is pending. The earlier process-0/terminal-ERROR observation stays
a failure, not a completed provider call.
