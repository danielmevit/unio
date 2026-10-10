# Agent Readiness

This document describes the native agent authentication readiness CLI tool and its associated storage bridge (`bridge/readiness.py`).

## Limits
The observation tool explicitly tests non-generating readiness, verifying basic authentication status without modifying config, falling back to API calls, or making actual LLM queries. It only runs read-only commands and records the result safely under `coord/readiness/`.

## Checked Fields
The tool runs `claude auth status --json` and strictly accepts:
- `loggedIn`: Required boolean.
- `authMethod`: Optional string.
- `apiProvider`: Optional string.
- `subscriptionType`: Optional string.

Any other fields are silently dropped (privacy sentinel behavior) to ensure no credentials or excessive PII are exposed or saved to disk. Missing `loggedIn` or unexpectedly typed fields result in an observation failure.

## Exits
The `agent-readiness.py` CLI verifies:
- `claude --version`: Nonzero exit codes or unsupported versions are considered failures. (Only versions matching `2.1.295` or `2.1.296` are considered supported).
- `claude auth status --json`: 
  - Nonzero exit codes are logged as `nonzero exit: <code>`.
  - Empty output, timeouts (10s), and oversize outputs (>64KB) are considered failures.

Any malformed or duplicate JSON structures result in an immediate parsing error and a failed observation, to prevent JSON injection or parsing bugs.

## Pending Packaging
In the future, the lead will package the accepted module into the native command. Currently, `tools/agent-readiness.py` remains an isolated stdlib script and does not claim to replace or mimic a fully integrated sub-command of `agy`.
