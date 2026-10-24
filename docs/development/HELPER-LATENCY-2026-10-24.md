# Helper latency on Windows/WSL — diagnosis 2026-10-24

`HELPER-LATENCY-PROFILE-VIBE-GLM-HIGH-0524-20261024` is a bounded,
read-only diagnosis of the automatic-save and observation timeouts reported
by real Unio 0.5.23 development on the Windows-mounted workspace. It changes
no production code, no timeout, no policy and no save. All measurements ran
on 2026-10-24 between 10:42 and 11:05 local time on the development host
(WSL2, 16 CPUs, load average 0.9–1.9, workspace on `v9fs`/9p under
`/mnt/d`), while this task's own run kept producing real periodic save
timeouts. Raw receipts stay in task scratch under
`tmp/unio-next/helper-latency-profile-vibe-20261024/`.

## Confirmed phases and their deadlines

Installed engine: Unio 0.5.23, single-file installer
`/home/devmvt39/.local/bin/unio` (11,866 lines), matching this repository at
`cd0b3a2` (tag `v0.5.23`). Function references below are line numbers in
that installed engine.

| Phase | Code path | Deadline | Configurable |
| --- | --- | ---: | --- |
| Admission handshake | `policy_validate_admission_timeout` (7159) | 30 s default | `UNIO_ADMISSION_TIMEOUT`, 1..300 |
| Automatic save capture | `capture_seconds` (3491), `capture_child` (5650), `create_locked` (4918) | 30 s default; this workspace's launch wrappers set 60 s | `UNIO_SAVE_CAPTURE_TIMEOUT`, 1..300 |
| Save live-state observation | `cmd_inspect_worker` (5886) wraps one `observe` (4294) in `Budget(CAPTURE_SECONDS)` (3456, 3504) | 30 s fixed | No |
| Result observation | `observed_result` (686), `snapshot` (530), `changed` (846); no internal bound on its Git subprocesses | none | No |
| Experience record | `tools/model-experience.py` `RECORD_DEADLINE_SECONDS` (34), record's `fleet.observe` (709); `tools/fleet-status.py` `observe` (166) kills the group on expiry | 30 s fixed | No |
| Restore | `RESTORE_SECONDS` (3456) | 120 s fixed | No |

The save capture deadline covers the entire `create_locked` pipeline: two
full worktree observations (`capture` 4728, `observe` 4294, `walk_worktree`
4158, `tree_paths` 4125, `read_blobs` 4262, `ignored_names` 4150), the
carried-commit secret scan (`scan_history`), retention validation
(`retention_plan` 4742, `scan_store` 4655, `load_save` 4516), publication
(`publish` 4805), and attempt bookkeeping (`write_attempt` 4870 through
`last_good` 4706). The supervisor (`supervise_run` 5736,
`automatic_capture` 5716) forks the helper, waits synchronously for it,
sends SIGTERM at the deadline and SIGKILL one second later; a deadline stop
is reported as `helper exit -9; capture deadline exceeded (N seconds)`.

## Real evidence from 2026-10-24 runs

All five native runs that day used `UNIO_SAVE_CAPTURE_TIMEOUT=60`. Every
baseline and final save exceeded the 60-second capture deadline; the
provider runs themselves completed normally, so this is not a provider,
reasoning or admission failure.

| Run (worker) | Save outcomes in `native.log` | Run exit, duration |
| --- | --- | --- |
| `vibeglm-managed-lead-core-20261024` | baseline and final-failure timed out at 60 s | 2, 173 s |
| `codex-managed-lead-review-medium-20261024` | baseline, three periodic and final timed out at 60 s; one further periodic killed without the deadline note (cancellation/obsolete path in `capture_child`) | 0, 719 s |
| `codex-managed-lead-output-low-20261024` | baseline timed out at 60 s; one real refusal `the worktree changed between two observations`; one periodic `helper exit 1` (the helper's own refusal); final-failure timed out at 60 s | 1, 287 s |
| `codex-managed-lead-output-recovery-low-20261024` | baseline, one periodic and final timed out at 60 s; one further periodic killed without the deadline note | 0, 444 s |
| `vibeglm-helper-latency-20261024` (this task) | baseline and five periodic saves timed out at 60 s during the task window | running |

Each killed helper is recorded in `coord/saves/attempts/<worker>.json` as
`status: failed, reason: io_error` with `last_good_id: null` — the designed
bookkeeping for a helper that could not record its own refusal
(`capture_child` writes it when the exit status is neither 1 nor 2).

## Local measurements

Fixture scale (excluding `.git`): this worker's worktree 566 files,
7.6 MB, 32 directories; the idle `vibeglm-native-lead-plan-20261024`
worktree 568 files, 7.6 MB. The save store holds 32 active saves — exactly
the `CAP_PROJECT` cap of 32 — with 11,597 stored body files totalling
154 MB, plus 49 archived saves totalling 254 MB (`unio save usage`:
23.4 s, exit 0). Per-save deep-load cost on `v9fs` is 0.7–1.7 s.

Components measured on this worker's own worktree (`v9fs`), each with an
absolute supervisor deadline and its exit code recorded (all exited 0):

| Component | Seconds |
| --- | ---: |
| Full walk + read + sha256 of all 563 regular files (7.6 MB) | 2.54 |
| `git status --porcelain` | 1.01 |
| `git check-ignore --no-index --stdin`, all 566 paths in one batch | 1.01 |
| `git diff` unstaged name-only | 0.76 |
| `git rev-list HEAD ^main` | 0.63 |
| `git rev-parse HEAD`, `ls-files --stage`, three `diff`/`ls-files` variants, `ls-tree -r HEAD` | 0.05–0.16 each |
| `python3 -I -S` startup (5 reps) | 0.009–0.010 |
| `git --version` startup (5 reps) | 0.002 |
| `flock` acquire/release, 200 reps | 0.209 ms per op |

The same content copied into a private tmpfs (existing project wrapper:
`unshare` user and mount namespace, private 512 MB tmpfs, no Docker)
shows the cost is filesystem metadata overhead, not the work itself:

| Measurement (identical bytes) | `v9fs` seconds | tmpfs seconds |
| --- | ---: | ---: |
| Walk + read + hash 566 files, 7.6 MB | 2.54 | 0.017 |
| Read + hash all 11,597 stored bodies, 154 MB | 37.70 | 0.25 |
| `flock`, 200 reps | 0.042 | ~0.0 |
| Copy the store out of `v9fs` (11,597 files, 154 MB) | 93.76 | — |

Installed-helper call paths on the real workspace, read-only, supervisor
deadline 120 s each:

| Command | Seconds | Exit | Result |
| --- | ---: | ---: | --- |
| `unio save usage --json` | 23.38 | 0 | store at cap: 32 active, 49 archived |
| `unio save inspect --worker vibeglm-native-lead-plan-20261024 --json` | 32.68 | 0 | no valid save; latest attempt `failed io_error`; metadata scans only |
| `unio result vibeglm-native-lead-plan-20261024 MANAGED-LEAD-PROPOSAL-LOCAL-VALIDATION-0524-20261024` (the one permitted real result observation, idle worker, its fixed-command config) | 19.42 | 0 | fresh result JSON, 6.7 KB |

## Cost model of one automatic save on this workspace

Adding the measured components to the `create_locked` pipeline (cumulative
component costs; staging writes are the only unmeasured step):

1. Two worktree observations: about 5–6 s each, 10–12 s total.
2. Periodic early-exit check `last_good(deep=True)`: full metadata scan of
   active and archive stores (23–33 s measured through the installed
   helper) plus a deep load of the newest save (1.5 s).
3. `scan_history`: one `ls-tree` per carried commit, 0.15 s each.
4. `retention_plan` deep-loads every active save: 37.7 s measured as pure
   read + hash; the real deep load also stats every body and reads each
   manifest, task and bundle, so this is a lower bound.
5. Publication staging: writes about 7.6 MB of bodies plus the bundle to
   `v9fs` with fsyncs (unmeasured; the 93.8 s store copy suggests roughly
   8 ms per file).
6. `write_attempt` re-scans the whole store through `last_good`: another
   23–25 s.

Total: roughly 105–125 s against the configured 60-second deadline. The
deadline cannot be met by any margin, and because the baseline save never
succeeds, no save exists for the run's `run_id`, so the periodic
"state unchanged" early exit never applies and every periodic capture
repeats the full publish path. The two `helper exit -9` lines without the
deadline note are the cancellation and obsolete-provider kill paths in
`capture_child`, not a different failure.

## Root cause versus hypotheses

Confirmed: the automatic-save deadline is exhausted by save-store
validation on `v9fs`, not by worktree observation. The store is at its
project cap (32 active saves, 11,597 bodies, 154 MB), and every publish
deep-loads all of it plus two more full metadata scans, at roughly 8 ms of
per-file `v9fs` overhead per body. The worktree observation itself costs
2.5 s and every Git component stays under 1.1 s.

Ruled out by measurement: provider or reasoning involvement (separate
phase; all five runs completed with their own exits), admission (bounded at
30 s, no admission failures in any 2026-10-24 log), Git subprocess cost
(0.05–1.01 s each), hashing (0.01 s per 7.6 MB), locking (0.209 ms per
`flock` cycle), process startup (2–10 ms), and the worktree walk alone
(2.5 s).

The 30-second experience/result observation timeouts are the same
filesystem cost at a different scale: a real `unio result` on the idle
568-file worktree costs 19.4 s, leaving about 10 s of margin under the
fixed 30-second `RECORD_DEADLINE_SECONDS`. During active runs a capture
child is almost always walking the worktree twice and deep-loading the
32-save store, saturating `v9fs`; result observations then cross 30 s and
`fleet.observe` kills the group. This is a load-induced deadline failure of
the observation wrapper, not a provider, reasoning or admission bug.

## Smallest justified correction

1. Configuration, immediate: raise `UNIO_SAVE_CAPTURE_TIMEOUT` from 60 to
   150–180 in this workspace's launch wrappers. The measured full path is
   105–125 s, so 60 s can never succeed; 150–180 keeps the bound well under
   the supported 300 s maximum without weakening any validation. The
   supervisor waits synchronously for each capture, so the final save can
   delay run completion by up to the deadline; that trade-off is the
   owner's call.
2. Code, focused: remove the third full-store metadata scan by letting
   `write_attempt` reuse the last-good identity established under the same
   publish lock instead of calling `last_good` (saves 23–25 s per save),
   and let the periodic early-exit read the newest-save identity without
   scanning the active and archive stores (saves another 23–33 s whenever
   the periodic path runs). Both keep every stored byte validated once per
   publish, both worktree observations, retention caps, pins, newest and
   corrupt-evidence protection, and atomic publication unchanged. The
   estimated full path drops to roughly 55–75 s, fitting a 90–120 s
   capture deadline with margin.

Explicitly not justified by this evidence: loosening all limits, bypassing
policy or STOP, removing checks, globally capturing ignored files,
weakening the stable-byte/double-observation safety, or skipping deep
validation of active saves. The store being at its cap is deliberate
retention policy; shrinking `CAP_PROJECT` would cut per-publish cost but
is an owner policy decision, not a helper fix.

For the experience/result deadline: keep the 30-second bound and reduce
the concurrent `v9fs` saturation through the corrections above. Raising
`RECORD_DEADLINE_SECONDS` would need its own under-load measurement first;
none exists yet.

Meaningful regressions for the code change: `tests/unio-save-performance.py`
(the folded single-deep-load retention property and repeated-pathname I/O
assertions), `tests/unio-save-retention.py` (caps, pins, newest
protection, corrupt evidence, interruption), an A/B timing on an
equivalent populated fixture using the `SAVE-PERFORMANCE-NEXT.md` method,
and one real-workspace automatic-save observation (baseline, periodic,
final) after the change.

## Elapsed-time estimate for a future focused fix

The configuration change is minutes of work plus an owner decision. The
code change is about 2–4 hours of implementation plus 1–2 hours of
regression suites and A/B timing — roughly half a day for one
implementation worker, comparable in size to the 0.5.16 descriptor-bound
change.

## Limitations

- One host, one day, load 0.9–1.9, cache state uncontrolled; single
  repetitions for the installed-helper timings.
- The 37.7 s deep-load sample reads and hashes pool bodies only; the real
  deep load also stats every body and reads manifests, tasks and bundles,
  so retention cost is higher than measured.
- Publication staging writes were not measured directly.
- Only one real result observation was permitted; it measured the idle
  state, not the under-load condition that produces the 30 s timeouts.
- The tmpfs comparison used identical bytes but a different filesystem and
  namespace; it attributes cost, it does not propose moving the store
  (store location is policy).
- No speed ratio is claimed across different fixture sizes; every
  comparison above used identical file and byte counts.
- If the under-load result-observation question must be closed, the single
  next useful measurement is one bounded `unio result` on an idle worker
  while a real run's periodic captures are active.

## Raw local evidence

- Run logs: `tmp/unio-next/managed-lead-core-20261024/native-corrected.log`,
  `tmp/unio-next/managed-lead-review-corrections-medium-20261024/native.log`,
  `tmp/unio-next/managed-lead-output-correction-low-20261024/native.log`,
  `tmp/unio-next/managed-lead-output-recovery-low-20261024/native.log`,
  `tmp/unio-next/helper-latency-profile-vibe-20261024/native.log`.
- Attempt records: `coord/saves/attempts/<worker>.json` for the five workers.
- Measurements: `tmp/unio-next/helper-latency-profile-vibe-20261024/fixtures/`
  — `component-measurements.jsonl`, `tmpfs-comparison.json`,
  `result-observation-{start,stdout,stderr,exit}.txt`,
  `save-usage-{stdout,stderr}.json`, `save-inspect-{stdout,stderr}.json`,
  `harness-run.log`, `tmpfs-run.log`, and the two harness scripts.
- Store and worktree scale: `unio save usage --json` receipt and the
  inventory phases recorded in `component-measurements.jsonl`.
