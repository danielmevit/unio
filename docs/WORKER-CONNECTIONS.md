# Static worker command audit

Run `unio doctor --commands` before a provider invocation. Add `--json` for
schema version 1 and `source: local_static`. It reads `coord/agents.conf` in a
Unio project when present, otherwise the ordinary configured `agents.conf`
(`UNIO_CONF_DIR` or `~/.config/unio`). It works outside projects and under STOP.
The no-argument project doctor retains its existing behavior, including project
metadata/hook migrations; the command audit returns before that path.

The audit does not run configured commands, wrappers, provider binaries or
help/version probes. It does not inspect authentication stores or PATH, change
settings, migrate hooks, bench agents, retry, select models or alter billing.
Authentication, capacity, effective model and effective effort are **Unknown**.
Exit 0 means the bounded audit completed, even with warnings or Unknown facts.
Exit 2 means invalid arguments or unreadable, malformed or over-bound input.
Only `--commands [--json]` is accepted; duplicate/surplus arguments are rejected.
This is not readiness or compatibility proof.

## What the facts mean

Each alias has a recognized tool basename or Unknown, requested selector facts,
transport and controlled issues/remedies. Quoted executable paths and simple
argv are supported. Recognized basenames (`codex`, `claude`, `opencode`, `grok`,
`agy`, `vibe`, `copilot`) do not prove that a file contains that native CLI.
Compound shell commands, assignments, substitutions and custom wrappers remain
Unknown. Literal `$TASKFILE`/`${TASKFILE}` references are inspected, never expanded.
A file pointer is only a pointer, not proof that the provider reads the file.

Only conservative, nonsensitive structural model forms and explicit effort
values are shown. These are not a current model catalog or evidence that a
flag/selector combination is supported by your installed version. Other model
text remains Unknown with a `selector_unknown` hint. Duplicate selectors,
conflicting/unrecognized effort controls, unrecognized options, profiles and
additional config overrides remain
Unknown. No implicit effort is inferred from a model name. Copilot Auto Balance
is reported as a requested policy, not a fixed underlying model or lab.

Issue codes include `command_unknown`, `selector_unknown`, `effort_ambiguous`,
`transport_unknown`, `whole_taskfile_argv`, `legacy_opencode_permission` and
`auto_balance`. The whole-TASKFILE hint is a static text observation: large
material may exceed the OS argv limit; prefer stdin or a native file flag.
The OpenCode flag hint is dated 2026-10-13. Neither a text match nor a historical
observation proves a current provider failure. Inspect native help yourself
when a combination cannot be established safely. The audit never fetches help.
The [dated readiness observations](development/WORKER-READINESS-2026-10-13.md)
are separate evidence, not live allowance or audit results.

## Bounds and privacy

Input must be UTF-8 regular configuration, with no final-file symlink: at most
65,536 bytes, 512 lines, 128 unique aliases and 4,096 bytes per command. Aliases
must match `[a-z][a-z0-9_-]{0,31}` and cannot contain
secret/token/password/account/credential/API-key markers. Blank lines and comments are allowed; other lines require `alias=command`.
Empty commands, malformed quoting, control characters and duplicate aliases are
rejected with a controlled diagnostic. The canonical JSON facts and each
output are capped at 131,072 bytes in both views.

Raw commands, arbitrary executable/wrapper paths, environment values, account
identifiers and unvalidated selector text are never printed. Human and JSON
views use the same bounded facts. Existing `unio agents --json`, defaults and
configured commands are preserved. Static parsing is deliberately conservative;
inspect custom wrappers separately without treating an Unknown as a failed run.
