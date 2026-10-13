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

## Sibling ignore batching — 2026-10-11 source candidate

The existing lead implemented a narrower change after rejecting the earlier
GLM partial: batch ignore queries for sibling directories while retaining
depth-first traversal. Preflight closes each directory immediately; reopening
checks device/inode identity and the prepared listing. Query batches have
bounded metadata. Retention, both observations, full save validation and
production deadlines remain unchanged.

Six focused real-Git tests passed, including a 96-sibling tree under a 64-file
descriptor limit, retained ignored HEAD paths, exclusion before body reads,
query bounds, directory replacement/listing races and existing refusals.

A private generated fixture on the Windows-mounted `v9fs` filesystem had
324 tracked files, 325 captured paths, one carried commit and two existing
validated saves. Each measured call restored exactly that same starting
history and used the same worker bytes:

| Full save attempt | Elapsed seconds | Ignore queries | Result |
| --- | ---: | ---: | --- |
| Initial baseline | Not retained by the first harness | Not retained | Refused at the existing 30-second bound. |
| Sibling-batched candidate 1 | 26.35 | 6 | Complete save, deep validation passed. |
| Sibling-batched candidate 2 | 26.18 | 6 | Complete save, deep validation passed. |
| Final baseline | 31.66 | 66 | Refused at the existing 30-second bound. |

The candidate fingerprints matched the earlier successful baseline saves
used to seed the fixture. The two successful candidate manifests matched
except for identity/timestamps, and prior-history bytes stayed unchanged.
Full save calls include both observations, history/retention handling,
publication and deep validation; these are not traversal-only timings.

The first comparison harness stopped on the baseline refusal before storing
its timing. That failure is preserved; a corrected continuation recorded only
the remaining three planned calls. No production timeout was increased.
Another save suite was generating disk I/O during the comparison. This small
sample demonstrates reduced query overhead and successful captures on this
fixture, not a general speed percentage or proof that every real-workspace
automatic save now finishes within its deadline. Profile history-sized real
workloads before choosing the next optimization.

## Descriptor-bound deep reading — 2026-10-13 source candidate

`SAVE-PERFORMANCE-SOL-LOW-1` uses the existing ChatGPT subscription through
Codex CLI 0.162.1, requesting `gpt-6.1-sol` with LOW effort. Effective model,
effort and remaining allowance are Unknown. Worker completion is separate
from lead acceptance and release.

Deep loading previously checked each stored task/body/bundle through a
pathname stat, then opened it without following links and obtained descriptor
metadata again for its bounded read. The candidate opens each such file once,
checks its owner, 0600 mode, single link, regular type and size on that exact
descriptor, and supplies that descriptor stat to the bounded reader. It still
reads and hashes every body, validates index Git object IDs, task content and
bundle bytes/header, and checks the complete manifest and directory layout.
Metadata-only inspection retains its separate pathname checks.

Both worktree observations and all existing retention scans still run. No
metadata-only result becomes content-valid, and no file, manifest or body
result is reused between loads. Retention pins, newest/corrupt protection,
archive accounting, publication verification and capture budgets are unchanged.
The installed regression suite also changes privacy metadata at file-open time
to confirm that validation follows the descriptor actually supplying bytes.

The private comparison installs frozen source `9989ed34` and the candidate
separately. It loads the helper from each installed engine and times its real
manual-create path, including worker/store locks, both Git/worktree observations,
retention, publication and attempt bookkeeping. Shell-wrapper startup,
installation and fixture preparation are outside these timings. Calls and
cumulative function time are instrumented; overlapping times must not be added.
The regression smoke checks also invoke the installed CLI directly.

The task-generated `v9fs` fixture has 400 worktree paths, 4,901,321 worktree
bytes, 400 unique content bodies and no carried commits. Its small-history
case has one prior save; the populated case has 32 content-valid prior saves,
two per old worker. All starting saves contain the same verified snapshot
content, with distinct identities, workers and publication times. Later resets
move those same generated directories back from active/archive storage. The
source Git/worktree input is identical. Original diagnostic stores are untouched.
Both installations explicitly select a 300-second capture budget and use private
configuration with offline shell mocks (explicit Bash for subsequent runs);
no provider run is part of the fixture.

| History | Engine observation | Elapsed seconds | Result |
| --- | --- | ---: | --- |
| 1 save | Baseline | 24.29 | Complete |
| 1 save | Candidate | 23.95 | Complete |
| 32 saves | Baseline 1 | 320.43 | Refused at the 300-second capture bound; prior saves retained |
| 32 saves | Candidate 1 | 244.28 | Complete; one eligible old save archived |
| 32 saves | Baseline 2 | 304.93 | Complete; one eligible old save archived |
| 32 saves | Candidate 2 | 249.01 | Complete; one eligible old save archived |

The four populated observations alternate baseline/candidate. Total elapsed
includes attempt bookkeeping outside the helper's capture checks; this explains
why a successful manual helper can report more than the configured 300 seconds.
These measurements do not exercise the automatic controller's wall-clock stop.
The refused first baseline is preserved separately and is not a completed-save
latency sample.

For the completed second pair, both engines made 98 save-validation calls,
20 Git calls, two observations and **14,141 byte-reader calls**. Pathname privacy
checks fell from **39,593 to 26,360** (13,233 fewer). Their cumulative time fell
from 45.27 to 32.45 seconds. The small-history case similarly fell from 2,020
to 1,218 checks while retaining 1,617 byte-reader calls. Candidate reader counts
include both ordinary `read_at` and descriptor-bound `read_stored_at` calls.
This is measured code-level reduction in metadata work, with every deep body
read retained.

Storage/cache variation remains substantial. The first populated baseline
followed a bulk-copy reset; subsequent resets used directory renames. In the
second pair, the observation phases alone took 20.25 versus 10.44 seconds,
although their code and inputs are unchanged. Body reading remains the largest
profiled cost. Instrumentation, host I/O and cache state are uncontrolled;
there are only two observations per populated engine and one per small-history
engine. The elapsed differences therefore support this fixture's observed
outcomes, not a universal speed percentage or proof that automatic captures
fit the unchanged default thirty-second deadline. No native-Linux/tmpfs
comparison or model-effort performance attribution is claimed.

| Installed input | SHA-256 |
| --- | --- |
| Frozen installer source | `9ffd7a5c8e218a5257700824a6d84800cf85c484321f32f4307321a4f619cc6a` |
| Baseline installed engine | `8e4e6f58c70a716812224b8bc96f4205274b09054801c8bc5ff5d58f4f86f4ab` |
| Candidate installer source | `5b5c5fa3439839996f4a1e8a58319d2a9920ec3f1038636bf5789f332d5a889f` |
| Candidate installed engine | `91f24e17313ffe0b5aa6a7e73eb8276ae4c39abc9b7cb88870f46d5b577a5a4f` |

Private scripts, dated receipts, profiles, the original refusal and an initial
baseline source-label erratum remain in task scratch. The baseline installed
helper was independently matched byte-for-byte to frozen source; the erratum
changes neither engine/helper hashes nor measurements. All installer bytes
outside the saving payload match the frozen source.

`tests/unio-save-performance.py` exercises the installed helper and real CLI,
exact staged/worktree/binary/commit restoration, archival with claim pins and
newest protection, corrupt bodies/manifests/bundles, symlinks, hardlinks, modes,
owner checks, FIFO refusal, privacy changes at open and fresh changing-worktree
observations. Its repeated-pathname-I/O assertion fails against the frozen
installed baseline. The suite is registered once in the quality gate; full
release validation and acceptance remain with the lead.
