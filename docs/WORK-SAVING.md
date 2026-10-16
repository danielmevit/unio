# Work saving — saves and authorized continuation

Owner requirement recorded 2026-10-06 after a worker reached its allowance
limit with useful edits but no final commit. See the
[version plan](VERSION-PLAN.md), the frozen
[implementation contract](development/WORK-SAVING-CONTRACT.md) and the
[roadmap](development/ROADMAP.md#approved-delivery-priorities).

Validation update, 2026-10-09: the complete versioned quality gate passed,
including all 65 default continuation assertions. See [completed checks,
preserved failures and live cooldown limitation](development/RECOVERY-ACCEPTANCE-2026-10-08.md).

## Status

| Part | State |
| --- | --- |
| Manual `unio save create`, `inspect` and `restore` | Available in v0.5.4 |
| Automatic baseline, periodic and final saves during runs | Available in v0.5.4 |
| One authorized continuation from a save (`unio save continue`) | Available in v0.5.4 |
| Save retention with archival (`unio save usage`) | Included in the v0.5.10 release candidate; not included in v0.5.9 |
| [Lead cooldown supervisor](LEAD-COOLDOWN.md) | Experimental, explicitly enabled in v0.5.4; genuine lead-limit-to-restart cycle unverified |

Install the [official v0.5.9 release](https://github.com/danielmevit/unio/releases/tag/v0.5.9)
to use the existing saving commands. The archival and usage additions below
require the next release. Check the installed version with `unio version`.

## Manual saving

```text
unio save create WORKER TASK
unio save inspect SAVE_ID [--json]
unio save inspect --worker WORKER [--json]
unio save restore SAVE_ID DESTINATION
unio save continue SAVE_ID DESTINATION NEW_TASK
unio save usage [--json]
```

`create`, `inspect`, `restore` and `usage` make no provider call and work while
STOP is set. `continue` starts one separately authorized worker run and respects
STOP and account limits. Exit 0 means success, 1 a known refusal or failure,
and 2 bad arguments, unavailable observations or an Unknown restore outcome;
`continue` preserves the worker run's exit code.

`create` acquires the source worker's native lock exactly once (a validated, regular, owned file in a safe parent directory, without following symlinks or blocking) and observes the worktree twice. It saves only when both observations match: committed history after the base (as a verified Git bundle carrying HEAD over the base), the full index and the working files, each with its own bytes and modes. Staged, unstaged, untracked, deleted, binary, empty, executable and retained deleted-from-index content is kept exactly. Ignored caches and the native ignored role cards are omitted before any of their bytes are read; however, required paths like HEAD-tracked files inside ignored directories are still saved. The base is the frozen task base that `unio run` recorded, otherwise the commit named by `coord/base`.

A save is refused, not partially written, for changing bytes, secret-looking
names (including ignored `.env` files and secrets in carried commits, even
when later deleted), symbolic links, hard links, FIFOs, nested repositories,
unmerged, sparse, assume-unchanged, skip-worktree or intent-to-add index
states, an operation in progress, unsafe or case-colliding path names and
anything over the bounds: 4000 paths, 100 commits, 4 MiB per file, 32 MiB
stored, 1 MiB task text, 30 seconds by default for capture. The source HEAD, index and files are
never written.

### Capture time budget

`UNIO_SAVE_CAPTURE_TIMEOUT` optionally sets the capture budget in positive whole
seconds from **1 through 300**. Unset means **30 seconds**. For example:

```bash
UNIO_SAVE_CAPTURE_TIMEOUT=120 unio save create WORKER TASK
UNIO_SAVE_CAPTURE_TIMEOUT=120 unio run WORKER TASK
```

The same value bounds manual capture and the native automatic baseline,
periodic and final capture helpers, including their controller's stop/reap
deadline. An invalid value (including empty, zero, fractions or values above
300) refuses capture before observing the worktree or creating save-store,
lock or attempt evidence. Automatic saving reports the refusal while provider
execution and its real exit remain independent. Read-only `inspect` and
`usage`, and restoration, remain usable with invalid capture configuration.

A larger budget allows slow storage and retained-history validation more time;
it also allows a longer wait before provider startup and after provider exit.
Periodic capture runs while the provider continues. All existing integrity,
stable-byte, secret, retention and immutable-save checks still apply, including
validation of older saves. This setting changes neither the agent task timeout
nor the 120-second restore budget or read-only live-observation bounds. After
cancellation, final capture retains the original maximum 30 seconds of cleanup
and one-second helper escalation grace even with a larger capture budget.
`unio kill` retains its sixty-second orderly-shutdown limit.

When the controller stops a helper for its capture deadline, the existing
automatic-save failure message includes `capture deadline exceeded (N seconds)`
alongside the real helper exit and last-good retention notice. Arbitrary
SIGKILL, external termination and provider exit codes receive no deadline
label without a controller-initiated deadline stop. Attempt/result schemas
and the last successful snapshot are unchanged.

See the [measured Windows-mounted-store example](development/AUTOSAVE-HELPER-2026-10-13.md#configured-budget-measurement)
for the latency tradeoff on a populated store. The setting is also listed in
`unio help`.

Saves live under the private `coord/saves/` directory: one directory per
save with `manifest.json`, the literal task text, a content pool named by
SHA-256 and the optional bundle. A save becomes visible only after it is
complete and verified; an interrupted save leaves the previous good save in
place. Each worker keeps its latest five unclaimed saves; restore claims pin
the saves they used. A separate latest-attempt record per worker shows a
newer refused or failed attempt without hiding the last good save.

When retention caps are reached (5 ordinary unclaimed saves per worker, 8
total per worker, 32 project-wide), older eligible saves are atomically archived
to `coord/saves/archive/SAVE_ID/snapshot/` instead of being deleted. A private
wrapper reserves each ID exclusively before the existing save directory moves
inside it; an existing ID is never replaced. Archived saves remain
accessible for inspect and restore, and count toward a separate archive bound
(128 saves, 512 MiB). Each worker's newest valid save and every claim-pinned or
corrupt/unsupported item is preserved. If no eligible history can move, the
archive is full or evidence is unsafe, the new save is refused without deleting
history. There is no automatic archive purge. `unio save usage` reports active
and archived counts, bounds and evidence.

`inspect` validates every stored byte and reports the save, or a worker's
last good save, latest attempt and live state. Live state is Unknown while
the worker is busy, its native lock or coordination parents are unsafe, or it
cannot be observed. Unsafe lock admission refuses before changing saved or
claim evidence. Existing owned, single-link 0644 native locks are supported;
new native locks are 0600, and save-store privacy remains 0700/0600.

`usage` reports read-only metadata observations: active and archived save counts,
actual stored file bytes, retention caps (5 per worker unclaimed, 8 per worker, 32
project-wide), archive bounds (128 saves, 512 MiB), valid claim pins, corrupt
evidence and claim counts. It works while STOP is set and makes no provider
calls, creates no missing store or lock and changes no existing files. Busy or
unsafe storage, unreadable claims and corrupt or ambiguous entries report
Unknown with exit 2. Counts do not establish content integrity; `inspect`
validates content hashes. The JSON output labels this `metadata_only`.

`restore` writes into a different worker that is idle, clean and at the
saved base in the same repository. Everything is validated first: manifest,
content, task text, bundle (in a private quarantine), paths and collisions
with ignored destination files. It then records a claim, fast-forwards only
the destination branch, rebuilds the exact index and working files, and
compares the result with the saved fingerprint. On failure it restores the
destination's exact earlier state, or records the outcome as Unknown and
never restores into that destination again automatically. It never commits,
resets the source, cleans ignored files or moves another branch.

## Automatic saving

Native `unio run` saves local file state before starting its provider, checks
for changed state every sixty seconds, and captures final state after success,
failure, timeout or graceful TERM/INT interruption. Unchanged periodic state
creates no duplicate save. Saving needs no AI request or final answer. Each
save records its worker, task, native attempt ID, revisions, file hashes and
observation time; final saves also record the actual process exit.

The same validated, bounded format and retention rules apply as for manual
saves. The native shell keeps its existing worker and shared-account ownership;
providers and capture children inherit neither lock nor account-control pipes.
Capture children use the capture budget (thirty seconds by default) and are stopped and reaped.
Provider execution continues if saving fails. Its real exit and native quality
receipts remain separate from saving; a refused or failed final capture keeps
the previous good save visible through `unio save inspect --worker WORKER`.
No allowance telemetry is required, and no worker is benched or restarted by a
save failure. Forced process termination (SIGKILL), host loss or disk failure
can prevent the final save; already published checkpoints remain available.
`unio kill TASK` requests orderly shutdown and allows up to sixty seconds for
provider cleanup, final capture and receipts before forcing owned processes to
stop. It retains process identity checks and makes no new provider call.

Workers receive guidance to commit coherent, scoped changes regularly. A
finish reserve leaves time to validate and commit before the run deadline
or a known allowance boundary. Use supported readings and timestamped manual
input where available; missing quota information remains Unknown. This
cannot predict every provider cutoff, so saving works independently of the
AI answering a final request.

Use `inspect` for the last successful save, observation time, latest attempt
and live saved/changed/Unknown state. Concurrent edits can prevent an exact
latest capture; those changing bytes are never reported as successfully saved.

## Continue restored work

First inspect a save and restore it into a different, idle worker at the saved
base. Write a separate new task under `coord/tasks/` with explicit `Allowed
scope` paths and `Validate` commands, then authorize its one run:

```text
unio save inspect SAVE_ID
unio save restore SAVE_ID DESTINATION
unio resume
unio save continue SAVE_ID DESTINATION NEW_TASK
unio stop
```

`continue` requires the destination's HEAD, full index and working bytes/modes
to match the save exactly. It never silently restores or overwrites changed
work. The saved task is literal context; its instructions and checks cannot
authorize this run. The new task must exist separately, differ from the saved
task and retain its complete SHA-256 through dispatch. The original worker,
branch and failed result stay intact.

Unio reserves one durable continuation claim per save, bound to the destination,
new task and saved fingerprint. It holds validated worker ownership once and
enters the native run body, retaining current account/tier admission, STOP,
retry limits, process receipts, automatic saving and optional automatic
verification. Auto-sync is skipped for this continuation so a newer main
cannot replace recovered commits or edits. Ordinary runs retain auto-sync.

The claim becomes `calling` immediately before provider startup, then `called`
with the actual exit after known completion. A launch refusal records `failed`;
uncertain launch or lost completion remains `unknown` (or unresolved `calling`
after a crash). **Every continuation claim blocks replay**, including failed,
calling and Unknown claims, even with another task or destination. Releasing an
account slot or editing a task does not grant a retry. Claimed saves stay pinned.
There is no automatic queue, restart or extra provider invocation.

The command returns the native run's exit: a failed provider keeps its real
exit; when the provider succeeds, optional verification can still return a
failure. TERM/INT is forwarded through the frontend and native supervisor,
which reap owned processes, attempt a final save and release worker/account
ownership. Forced termination or host loss can leave an unresolved claim; it
is evidence to inspect, never permission to replay.

Recovery grants no earlier checks, review or readiness. Run fresh checks and
the selected review policy for the continued candidate before acceptance.

Saving never commits arbitrary dirty files or accepts code. A coherent
source commit is still subject to checks and reviews. A recovery save is
explicitly unverified. Restore and inspection make no provider calls.

Filename exclusions cannot guarantee arbitrary source or task text is
secret-free. Worktrees are trusted-host coordination, and a private local
save is not an off-device backup.

## Required checks

Slice 1 is covered by `tests/unio-work-saving.py`: actual restored HEAD,
full index and bytes/modes, source immutability, zero provider calls,
corruption, unsupported states, concurrent edits, interrupted publication,
retention, pinning, caps, destination refusals, rollback and Unknown.

`tests/unio-work-saving-auto.py` uses offline native providers to exercise failed
exits without a final answer, exact restore, timeout, termination, periodic
change capture and deduplication, capture failure, last-good retention and
released worker/account ownership without allowance telemetry.

`tests/unio-save-capture-budget.py` exercises actual manual and native automatic
captures with the default and configured budgets, invalid input before effects,
controller deadlines versus external kills, real exits, last-good retention and
bounded cancellation. It uses private installations and deliberate offline
mocks; one case waits for the real sixty-second periodic interval and one
checks the thirty-second final-cancellation ceiling. The quality gate includes
this suite.

`tests/unio-work-saving-continue.py` drives real offline native runs: exact
restored state and separately authorized task text, real exits, replay and
Unknown refusal, STOP and occupied accounts, changed/incomplete orders,
single ownership through auto-verification, signal cleanup, pinned evidence,
source immutability and preserved commits with auto-sync enabled and newer main.
These focused checks make no AI request; the full gate runs before release.

`tests/unio-save-retention.py` exercises cross-worker pressure, archived inspect,
restore and authorized continuation, byte preservation, protected claims and
newest saves, archive count/byte bounds, collisions, read-only usage and an
interrupted archive move using isolated native workflows.

Failed-run commits are separately opt-in with `unio wip on|off|status` (default
off). See [WIP preservation](WORK-WIP.md) for text-only scope, safety refusals,
private receipts and recovery limits. Existing snapshot ordering is unchanged.
