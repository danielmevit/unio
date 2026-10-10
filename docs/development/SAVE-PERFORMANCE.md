# Measure recovery-save performance

`tools/save-benchmark.py` measures the installed Unio CLI using a tiny,
isolated project. Use it to compare save latency on different filesystems or
engine versions before choosing an optimization. This is a source-checkout
utility; it does not add an installed `unio` subcommand.

## Run it

From the repository root, choose an existing directory owned by you. In the
Unio workspace layout, `repo/` and `tmp/` are siblings:

```bash
mkdir -p "../tmp/save-benchmarks"
python3 -B "tools/save-benchmark.py" \
  --engine "$HOME/.local/bin/unio" \
  --scratch "../tmp/save-benchmarks" \
  --workspace "baseline-disk"
```

Every run requires a new workspace name. The probe refuses to reuse an
existing child and leaves its generated project and private `receipt.json`
there for inspection. `--cleanup` explicitly removes only that newly created
child; capture stdout if you need the receipt after cleanup.

For a filesystem comparison, use a second, already mounted, owner-created
tmpfs directory **inside the workspace** as `--scratch`, with a new workspace
name and the same engine, save count and limits. Creating or mounting tmpfs
is a separate operator action. The probe never mounts storage, installs
software, clones external repositories or makes a provider call.

## What is measured

The fixture has two local workers and a small mixed workload: a staged text
change and deletion, an unstaged edit, and untracked text and binary files.
It runs at most three `save create` calls, worker `save inspect`, `save usage`
and `watch --once --json`. STOP stays set. It preserves HOME, isolates Unio
and Git configuration, disables Git hooks and uses a local provider stub to
detect accidental invocation.

Schema-1 JSON includes the exact engine version and SHA-256, observed
filesystem, monotonic command durations, exits, timeout/output flags and
workload counts. `save_attempt_count` counts calls; `save_count` counts unique
IDs with matching published manifest identities. That manifest check does
not prove a restore or replace native verification. A refused save remains a
failed observation. Unsupported usage, supported-but-Unknown usage, and
unrecognized output remain distinct.

Defaults are 60 seconds per subprocess, 300 seconds for the probe and 256 KiB
per output stream. Git and filesystem-observation commands share the total
deadline. Owned process groups are stopped on a bound or interruption, with
up to one extra second to reap the child. Exit 0 means the planned
measurements were recorded; inspect each measurement for engine failures.
Exit 1 means the fixture or whole-probe deadline prevented completion.

## Observed baseline

A corrected probe against Unio 0.5.9 on 2026-10-10 observed `v9fs` / `9p` on
the workspace-mounted Windows drive:

| Operation | Elapsed seconds | Result |
| --- | ---: | --- |
| Save 1 | 7.19 | exit 0, matching published manifest |
| Save 2 | 7.52 | exit 0, matching published manifest |
| Save 3 | 7.24 | exit 0, matching published manifest |
| Inspect worker | 3.36 | exit 0, JSON object |
| Watch once | 0.25 | exit 0, JSON object |
| Usage | 0.07 | exit 2, command unsupported in 0.5.9 |

The generated workload contained six non-control files totaling 2,377 bytes.
Three distinct saves were recorded; no provider-stub call occurred. The
installed engine and operator configuration hashes were unchanged afterward.
Private receipts stay outside the repository.

These are observations from one small fixture, not a general model or
filesystem ranking. Repeating the same workload on tmpfs can help separate
storage costs from process and Git costs. No comparative tmpfs measurement
or save-engine speedup is claimed here.
