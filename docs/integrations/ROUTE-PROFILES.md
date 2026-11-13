# Optional route profiles (`unio routes`)

A route profile is a reusable, typed launch **recipe declaration**. It removes
the repeated manual construction of the canonical adapter command: you
declare the requested settings once, and `unio routes compile NAME` prints
exactly one safely quoted `agents.conf` line for the tested packaged
**Vibe 3.1.1 / glm-5-3** path. V1 is local and offline only.

What a profile is **not**:

- It does not replace `agents.conf`, dispatch/admission, receipts,
  validation, review or owner consent. You review the compiled line and add
  it to your existing `agents.conf` yourself; nothing is applied
  automatically and nothing is executed.
- Requested model/effort/version are declarations. Effective model, effort
  and remaining allowance stay **Unknown**; a profile label never
  manufactures identity, consent or allowance.
- Account mappings and budget slots remain current native policy
  (`unio account`, `unio policy`); a profile can never widen them.
- No sign-in, credential access, quota probing, CLI installation or
  version subprocess ever runs. `unio routes` works outside a project and
  while STOP is set, and saves no authentication anywhere.

## The registry file

Optional file: `$UNIO_CONF_DIR/route-profiles.json`
(default `~/.config/unio/route-profiles.json`). A missing file means an
empty inventory. There is **no project override** in V1. The schema is
closed: unknown fields, duplicate keys, nonfinite numbers, NUL/control
characters, oversized or non-regular files are refused with bounded
diagnostics that never echo rejected secret-like values. A refused
`show`/`compile` name is never echoed either: the requested value is
untrusted free-form input, so every name refusal is a fixed actionable
error.

```json
{
  "schema_version": 1,
  "routes": {
    "vibeglm": {
      "adapter": "vibe",
      "requested_cli_version": "3.1.1",
      "model": "glm-5-3",
      "thinking": "high",
      "receipt_dir": "/home/you/unio-receipts",
      "max_tokens": 2000000,
      "max_price": null,
      "time_limit": 5400,
      "max_turns": null
    }
  }
}
```

Field rules (closed schema, `schema_version` must be the integer 1):

- Compiled V1 route names are usable native agent **prefixes**: a
  lowercase letter, then letters/digits/`_`, at most 64 characters, **no
  hyphen** (for example `vibeglm` or `vibeglm_high`). Native `unio run`
  selects the `agents.conf` alias as `${worker%%-*}` — the text before
  the first hyphen in the worker name — so a compiled key `vibe-high`
  would be selected as `vibe`. Hyphenated and secret-shaped names are
  refused with a fixed diagnostic that never echoes the rejected value.
- `adapter` must be `vibe`; `requested_cli_version` must be `3.1.1`;
  `model` must be `glm-5-3` — the frozen V1 contract covers the tested
  GLM 5.3 path only. Other adapter-pinned models (such as
  `mistral-large-4-0-3`) stay legacy `agents.conf` routes, not V1 profile
  targets; `thinking` must be `high` (Vibe 3.1.1 has no
  per-run thinking control, so only the observed catalog level may be
  declared and the effective effort stays Unknown). Other providers,
  versions and wrapped commands remain legacy `agents.conf` routes, not
  falsely supported profile targets.
- `receipt_dir` is an absolute path declaration, not a command: the
  existing private parent the adapter expects. **Create it explicitly
  yourself**, for example `mkdir -m 700 /home/you/unio-receipts`.
  `compile` checks it read-only and never creates it, never writes into
  it and never claims startup success.
- Caps (`max_tokens`, `max_price`, `time_limit`, `max_turns`) are optional
  and may be a finite number or `null`. Nonfinite and non-representable
  magnitudes (for example `1e400` or a `10**400` integer) are refused with
  a bounded diagnostic before any adapter is loaded. On 3.1.1, an omitted
  or `null` cap
  compiles to the adapter's explicit `none` choice (the native flag is
  omitted; the CLI default then applies and stays Unknown). Numeric caps
  are validated against the **installed trusted adapter's** current
  parser and bounds — never duplicated limits — so a compiled line is
  exactly what the adapter accepts.

## Commands

```bash
unio routes                 # list declared profiles (requested settings only)
unio routes --json          # same, as closed schema-1 JSON
unio routes show NAME       # display one declared profile
unio routes show NAME --json
unio routes compile NAME    # print one safely quoted agents.conf line
```

`compile` output looks like:

```text
vibeglm=python3 -I -S -B '/home/you/.config/unio/lib/adapters/vibe-worker.py' --model glm-5-3 --thinking high --receipt-dir '/home/you/unio-receipts' --max-price none --max-tokens 2000000 --time-limit none --max-turns none
```

- The line always refers to the actual configured trusted adapter path
  (`$UNIO_CONF_DIR/lib/adapters/vibe-worker.py`); compile requires the
  packaged adapter and refuses with a clear diagnostic when it is absent.
- Compile prints exactly one physical line. A configuration directory or
  packaged adapter path that contains a newline or other control
  character is refused (exit 2) with a bounded diagnostic that does not
  echo the path; the filesystem location is not rewritten into a
  different path. Spaces, quotes and shell metacharacters in ordinary
  paths stay quoted as before. Inventory JSON remains valid: JSON string
  escaping is a representation, not a filesystem rename. Text list/show
  never emit raw control fragments from a configuration path.
- Paths with spaces and shell punctuation are quoted safely; hostile
  values are refused, never silently normalized.
- Copy the line into your existing `agents.conf` yourself (the file uses
  `alias=command` lines). Then map the alias to its shared budget and run
  it through the normal flow:

```bash
unio account vibeglm mistral
unio run vibeglm-feature TASK-ID
```

- The declared CLI pin is not proof of the installed version: the adapter
  detects `vibe --version` at launch and refuses unknown versions before
  any provider call, exactly as for hand-written routes.

## Read-only behavior

`unio routes` performs no provider, CLI, version or quota subprocess, no
configuration or receipt-directory writes, and no execution of any
configured value. All output is declared requested settings plus explicit
`Unknown` effective values. The real work policy, admission and review
remain authoritative in every case.
