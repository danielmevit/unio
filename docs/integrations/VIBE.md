# Mistral Vibe Integration and Terminal Contract

This document records the machine-readable delivery contract and terminal usage
validation for the optional Mistral Vibe adapter (`tools/vibe-worker.py`),
supporting legacy **2.26.1**, modern **3.1.1**, **3.1.2**, and future CLI releases under the latest-CLI policy.

For general worker setup, installation paths, and account budget configuration,
see the [Mistral Vibe setup guide](MISTRAL-VIBE.md).

## CLI operation policy and version contract

In accordance with Unio's latest-CLI operation policy, the adapter uses the
latest installed CLI and judges actual operations rather than enforcing exact
version allowlists:

- **2.26.1**: Process-local `VIBE_*` model overlays, `--output streaming` with
  NDJSON progress parsing, explicit numeric bounds, and thinking levels (`low`,
  `medium`, `high`). Supported models: `glm-5-3` and `mistral-medium-3-5`.
- **Modern releases (3.1.1, 3.1.2, and newer)**: Documented startup
  `--model <ALIAS>` flag, `--output json` message list history, bounded
  `session/meta.json` metadata verification, omittable native caps (`none`),
  and catalog-level thinking (`high` only; `low`/`medium` refuse before launch
  because modern CLIs have no per-run thinking control). Supported models:
  `glm-5-3` and `mistral-large-4-0-3`.
- **Provenance & Unknown metadata**: The detected CLI version is recorded as
  provenance. If `--version` query fails, the version metadata is recorded as
  `Unknown` without blocking an otherwise working operation.
- **Honest failure contract**: Actual unsupported arguments, model catalog
  errors, schema defects, timeouts, and native exits remain truthful failures;
  no retry, silent fallback, or parameter guessing is performed.

## Delivery contract and terminal usage shape

For Vibe 3.1.1 and 3.1.2, the adapter invokes the native CLI in headless mode:

```bash
vibe --model <ALIAS> --prompt-file <TASK> --workdir <CWD> --trust --agent auto-approve \
  --output-dir <DIR> --output json --enabled-tools bash --enabled-tools read_file \
  --enabled-tools write_file --enabled-tools edit --enabled-tools grep
```

When native caps are specified, flags `--max-price`, `--max-tokens`,
`--time-limit`, and `--max-turns` are appended. When set to `none`, the
corresponding flag is omitted from the CLI invocation, allowing native CLI
defaults to apply while retaining the adapter's owned-process supervisor bound
(maximum 7200 seconds + 20-second shutdown margin).

Standard output is captured privately to `native-stdout.log`. The adapter parses
the payload as a bounded JSON message list without printing raw message text to
receipts or public streams.

### Run export and outcome taxonomy

On exit, Vibe writes `export.json` to the specified `--output-dir`. The accepted
schema version is integer `1`. Process exit codes map strictly to native
outcomes:

| Exit code | Native outcomes | Adapter classification |
|---|---|---|
| `0` | `finished` | `completed` |
| `1` | `usage_error`, `config_error` | `setup` |
| `2` | `infrastructure_failure` | `infrastructure` |
| `3` | `turn_limit` | `turn_cap` |
| `3` | `token_limit` | `token_cap` |
| `3` | `price_limit` | `price_cap` |
| `3` | `deadline` | `time_cap` |
| `3` | `terminated`, `length`, `refusal` | `provider_limit` |
| `4` | `aborted` | `aborted` |

### Model selection and session verification

Session identity is verified from actual selected identity sources in strict
priority order:
1. `session/meta.json` written under the `--output-dir` session journal.
2. The export configuration's `session` block.
3. The export configuration's `active_model` setting.

The export's `routed_model_config` and `routed_default_model` represent the
account's default declaration. They are recorded as `routed_default_*`
telemetry and corroborate session selection only when they explicitly name the
selected alias. Contradictory declarations result in explicit `mismatch`
states. Both alias and wire model must be confirmed for `verified` status;
partial or default-only evidence remains `unknown`.

Effective model, effective effort, and remaining allowance remain `unknown` on
the receipt regardless of client-side validation.

### Final response provenance

In `--output json` mode, the final response is extracted from the last
assistant entry in the top-level message list. The adapter records:
- Content form: `"string"` or `"blocks"`.
- Final response state: `"present"` when non-zero text bytes are found, or
  `"final_without_text"` when trailing entries contain only tool calls or empty
  content.
- SHA-256 hash and byte length of the serialized final assistant entry.

Raw text remains exclusively in the private log (`native-stdout.log`).

## Inspected native source anchors

The contract was statically inspected from the locally installed Vibe 3.1.2
package (`mistral_vibe-3.1.2.dist-info`):

1. **Launcher and CLI (`vibe.cli.launcher`)**:
   Executes bundled Rust binary `vibe-rs`, launching `vibe-app-server` and
   dispatching headless runs with CLI arguments.
2. **Export structure (`vibe.app_server.run_export`)**:
   - `RunExport`: Defines `schema_version = 1`, `vibe_version`, `outcome`,
     `usage`, `limits`, `cost_usd`, `steps`, and computed `exit_code`.
   - `RunOutcome`: Defines the exhaustive outcome enum and exit code mapping.
   - `RunLimits`: Captures active numeric caps (`max_turns`, `max_price`,
     `max_tokens`, `time_limit_s`).
3. **Session journal index (`vibe.core.session.session_index`)**:
   `METADATA_FILENAME = "meta.json"` defines the session metadata file
   copied into the export output directory.

## Truthful trial status and field evidence

- **Live trial status**: A live model invocation on Vibe 3.1.2 was **not
  performed** during this task. Per project policy, shared Mistral provider
  budget is strictly reserved for the adaptive lead implementation, and no live
  model calls were authorized. The live 3.1.2 trial is therefore explicitly
  labelled **unrun**.
- **Offline validation**: The compatibility changes have been verified offline
  using deterministic subprocess fixtures in `tests/unio-vibe.py` and
  `tests/unio-adapter-outcome.py`. Tested paths include:
  1. Successful execution, `--output json` message list parsing, and verified
     selection with `mistral-large-4-0-3` and `glm-5-3`.
  2. Native cap omission (`none`) with enforcement of the adapter's 7220-second
     supervisor ceiling.
  3. Strict refusal of unsupported per-run thinking levels (`low`, `medium`)
     before provider launch.
  4. Immediate refusal of unsupported model aliases (e.g. `mistral-medium-3-5`
     on 3.1.2) before provider invocation.
  5. Latest-CLI operation: future versions (e.g. `3.1.3`, `3.2.0`) launch with
     the modern explicit `--model`/json contract; unavailable version metadata
     records `Unknown` without blocking an otherwise working operation.
  6. Additive outcome binding and classification in `adapter-outcome.py`.
- **Execution bounds**: Trusted-host execution only; no OS sandbox, no network
  fallback, and no modification of user credentials or global configuration.
