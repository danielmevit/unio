# COMPLETION-TEST-ISOLATION-20261110 — isolate CLI update bash completion test subprocess

Hermetic test isolation fix for the bash completion regression test in `tests/unio-cli-updates.py`.

## Problem
In `test_help_completion_and_payload_consistency`, the `subprocess.run(['bash', ...])` invocation
testing bash completion was invoked without explicit `cwd` and `env`. Consequently, bash inherited
the outer calling environment and working directory. Under an outer environment where `UNIO_CONF_DIR`
pointed to a nonexistent or hostile path, or when executed from within the workspace containing
`coord/` and `wt/`, the test attempted to traverse the workspace and read an outer `agents.conf`,
resulting in `subprocess.CalledProcessError` (exit status 2) instead of hermetic test execution.

## Solution
Configured the completion test `subprocess.run` to explicitly use:
1. `cwd=self.outside` to run outside any enclosing project workspace.
2. `env=self.env` to use the class fixture's isolated environment containing synthetic configuration and directories.
