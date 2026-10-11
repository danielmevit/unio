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

## Larger generated workload and optimization target

A separate 2026-10-10 probe added 300 generated text files and a 1 MiB binary
block to the same small fixture. It contained 307 non-control files totaling
1,348,553 bytes. The installed 0.5.9 CLI created one manifest-confirmed save in
17.52 seconds and inspected the worker in 9.82 seconds. No provider was called.
This fixture did not reproduce the real workspace's automatic-helper timeout.

A subsequent profile used the unchanged installed save-helper source on that
private fixture, with one existing save. It completed in 23.41 seconds,
excluding shell-wrapper startup. Profiling and existing history differ from
the first probe, so the elapsed difference is not an isolated history-cost
measurement. Cumulative times overlap and must not be added:

| Profiled work | Calls | Cumulative seconds |
| --- | ---: | ---: |
| Git commands | 32 | 10.53 |
| Worktree traversal | 2 | 7.77 |
| Save validation | 4 | 4.31 |
| Ignore checks, included in Git/traversal costs | 10 | 3.55 |

The next bounded optimization should measure reducing repeated Git/ignore
queries and redundant save reads. It must preserve ignored-file exclusion
before body reads, secret-name refusal, no-follow traversal, both matching
observations and complete published-save validation. Compare equivalent
fixtures and history sizes before claiming a speedup. A larger timeout alone
is not an optimization; do not weaken recovery validation to meet a deadline.

## Real workspace timeout — 2026-10-11

Two new native runs using the unchanged installed 0.5.9 engine reproduced
`automatic baseline save unavailable (helper exit -9)` in the real workspace.
The worker checkout had 344 tracked files; the active save directory had
34 direct entries, including control entries. These counts are not equivalent
to the generated fixture above or a count of fully validated saves.

The automatic capture has a 30-second helper deadline. The provider invocation
continued independently after its baseline save failed. Read-only inspection
of the first worker reported no valid save, no corrupt evidence, and an
`io_error` save attempt. This is recovery evidence, not a provider connection,
allowance or model-quality result. Earlier successful saves remain preserved.

Investigate validation of existing save history as well as worktree traversal.
The current retention path scans the store and deeply validates existing
entries before deciding what to archive. The observed timeout does not isolate
which phase exhausted the deadline. Compare equivalent history sizes and file
contents before attributing cost or claiming an optimization. Keep failed-save
reporting separate from worker completion and preserve complete save validation.
