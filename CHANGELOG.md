# Changelog

Release notes for Unio. Between releases, each task writes a short
fragment in `changelog.d/`; the fragments are rolled into this file when a
version is released.

## 0.5.13 — matching protocols and clearer effort — unreleased

See [release scope and usage](docs/RELEASE-0.5.13.md).

- Use matching `unio mode yolo`, `balanced` and `thorough` commands. Keep
  `medium`/`safe` aliases and stored schema-1 compatibility values.
- Show public protocol names in human output and new worker instructions;
  add `protocol` to policy JSON while preserving machine-readable `mode`.
- Give each new-project prompt separate Low / Medium / Max reasoning and
  coordination-tier fields. Explain independent changes during a project,
  verified model controls, fixed routes and frozen running tasks.
- Put a dedicated effort section in the README and package the canonical
  reasoning guide. Effort profiles remain lead instructions, not an
  automatic native effort controller or a new `unio effort` command.
- Preserve account limits, configuration, owner templates and frontend work.

## 0.5.12 — choose workers from experience — 2026-10-12

See [release scope and usage](docs/RELEASE-0.5.12.md).

- Record a final operator assessment of an exact native task revision with
  `unio experience record`; preserve Source/check facts separately from
  reported acceptance, code issues, operational failures and unaccepted work.
- Inspect local task-specific profiles with `unio experience show`, retaining
  sample counts, age, correction burden and unknown metadata.
- Get conditional worker options with `unio experience suggest`, respecting
  STOP, shared slots including the lead, bench/binary facts and fresh cached
  sign-in/allowance. Sparse samples receive no recommendation; free/proposal
  routes remain eligible for routine advice only.
- Package the dependency-free helper, strict immutable storage, command help
  and completion, operator/lead guidance and focused offline regression cases.
- Preserve the shipped dashboard, website, brand assets and prior releases.

## 0.5.11 — plan, dispatch and review together — 2026-10-12

See [release scope and usage](docs/RELEASE-0.5.11.md).

- Batch sibling Git ignore queries during recovery capture. Matched fixtures
  improved from timed-out baseline attempts to roughly 26-second saves; broad
  real-workspace timeout elimination remains unproven. Include an offline probe.
- Explain local fleet blocks, cached readiness and shared-account slots with
  `unio fleet`; inspect dependencies, task material and write conflicts with
  `unio plan` without launching agents.
- Prepare, explicitly approve and start one saved task with `unio dispatch`.
  Bind grants and reservations to exact material; preserve replay and Unknown.
- Preserve immutable individual review receipts and inspect same-revision
  evidence with read-only `unio reviews`. Explicit `unio review-set` launches
  two to eight reviewers concurrently on identical frozen common material.
- Preserve refusal, interruption and request-changes evidence without automatic
  retries, substitutions, merging or human acceptance.
- Include the latest owner dashboard refinements and mandatory lead estimates,
  proactive progress summaries and continuity through authorized delivery.

## 0.5.10 — safer recovery and daily-use improvements — 2026-10-12

See [release scope and usage](docs/RELEASE-0.5.10.md).

- Archive eligible older recovery saves instead of deleting history, including
  under project-wide pressure. Protect each worker's newest valid save, claims
  and corrupt evidence; refuse new saves when bounded archival cannot proceed.
- Inspect, restore and separately authorize continuation from archived save IDs.
  Add read-only `unio save usage [--json]` for counts, limits and actual file bytes;
  unavailable or unsafe observations remain Unknown.
- Add explicit `unio readiness refresh claude` and local-only `show`, with private
  cached observations and bounded native metadata commands for Claude Code 2.1.296.
  The dashboard displays the cache without signing in or refreshing a provider;
  authentication does not establish allowance or permission to start work.
- Remember task search, worker, lifecycle and category filters across reloads of
  the same dashboard URL. Reconcile vanished restored choices after live data
  arrives; reset retains theme and list/map preferences.
- Add a practical daily-use guide and record real worker outcomes separately
  from connection failures and model-quality claims.

## 0.5.9 — clearer dashboard and agent fleet — 2026-10-10

See [release scope and usage](docs/RELEASE-0.5.9.md).

- Bring the website's interface language into the installed dashboard: dot-U
  branding, clear task rows, muted agent tones and responsive layouts.
- Start with a readable task list, remember the selected list/map view and
  show Run, Checks and Review separately, with safely quoted next-step commands.
- Show one allowance card per agent and separate cards for genuinely shared
  budgets; keep missing or stale readings Unknown.
- Replace raw activity output with a readable timeline, retain expandable
  technical evidence and simplify work-map connections and phone filters.
- Package the optional Copilot Auto Balance proposal adapter and persistent
  fleet guide. Local/BYOK models stay excluded; proposals require inspection.
- Keep packaged model-role and task-fit guides synchronized with their source,
  and include lead-routing and effort instructions without replacing owner copies.

## 0.5.8 — optional subscription adapters — 2026-10-10

See [release scope and setup](docs/RELEASE-0.5.8.md).

- Package the exact Mistral Vibe and Perplexity adapter scripts in the standalone
  installer, with generator checks preventing source/payload drift.
- Add read-only `unio integrations [--json]` with adapter paths, roles and setup
  guides; authentication and capacity remain Unknown.
- Support explicitly pinned Vibe implementation workers and Perplexity research
  or selected-context code proposals, with bounded calls and private receipts.
- Request proposed code and tests inline, preserve real failures and incomplete
  answers, and require implementation review and actual validation before use.
- Preserve existing configuration and custom templates; include offline checks
  for copied installers, JSON escaping and unsafe adapter targets.
- Record genuine model-task outcomes and the separate recovery-save retention
  follow-up. Preserve the owner-built project website.

## 0.5.7 — dashboard and AI allowance overview — 2026-10-09

See [release scope and usage](docs/RELEASE-0.5.7.md).

- Start, reuse, inspect and stop one managed local dashboard per workspace.
- Show AI routes, shared budgets, lead reservation, mode/tier and allowance
  windows with source, age, reset and truthful Unknown handling.
- Add explicit read-only Codex metadata refresh; browser polling reads only
  cached local snapshots. Preserve manual readings and failed refresh history.
- Share task search, lifecycle, worker and category filters across map and list;
  correct detail-pane layout, pagination and whole-token category detection.
- Reject malformed nested limits metadata, extreme percentages and timestamps
  without crashing. Synchronize standalone installer payloads and lead guidance.
- Document future temporary lead handover separately from current instructions.

## 0.5.6 — manual allowance tracking — 2026-10-09

[Release and downloads](https://github.com/danielmevit/unio/releases/tag/v0.5.6).
See the [usage and release scope](docs/RELEASE-0.5.6.md).

- Add installed `unio capacity record` and `show`, with explicit project selection,
  shared-budget groups, multiple windows, JSON output, age and optional reset time.
- Keep missing, invalid, stale and expired readings unusable; a passed reset
  does not imply refill. All readings are manual, with zero provider calls.
- Preserve malformed state, bound and validate every loaded field, refuse
  storage symlinks and merge concurrent writes under a lock. Handle extreme
  integer and UTC timestamp inputs without crashing.
- Package the store and CLI independently, verify exact installer payload bytes,
  and preserve readings and agent configuration on reinstall.
- Add bounded CLI-auth readiness research and a local documentation-link audit;
  update task-fit evidence without equating Source success with acceptance.

## 0.5.5 — browser launcher and clearer work map — 2026-10-09

[Official release](https://github.com/danielmevit/unio/releases/tag/v0.5.5).
The complete automated gate passed. Final publication edits preserve every
runtime, asset and test byte from the tested candidate.

- Packaged the installed browser launcher, available natively via `unio browser` with its own explicit configuration and startup options.
- Delivered the left-to-right interactive work map featuring an active-first presentation and a neutral hub.
- Redesigned cards to include quarter-width local AI logos/names, clear task titles, and muted outcome strips.


## 0.5.4 — recoverable work and live work map — 2026-10-09

[Official release](https://github.com/danielmevit/unio/releases/tag/v0.5.4).
The complete automated gate and installer upgrade/restore checks passed.
Lead cooldown restart is experimental and requires explicit enablement: its
genuine subscription-limit-to-restart cycle remains unverified. The owner
approved publication with that limitation disclosed.

- Save exact committed, staged and unstaged work with manual create, inspect
  and restore commands. Refuse unsupported or unsafe state and preserve the
  original worker, receipts and last good save.
- Capture baseline, changed periodic and final recovery saves around native
  runs, including failure and interruption. Keep real provider exits and
  bounded cleanup of the actual owned processes.
- Continue one explicitly restored save under a separately authorized task.
  Freeze task and effective prompt authority, retain current account admission
  and prevent replay after completion, refusal or an unknown launch.
- Add an experimental, owner-enabled lead cooldown supervisor for Codex CLI 0.161.0 on
  Linux with Python 3.11+ and an individual first-party ChatGPT subscription.
  Wait on authoritative allowance evidence; use five hours and one minute
  for a confirmed five-hour limit with no useful reset. Every launch requires
  fresh ordinary-usage permission. Stop, pause and completion remain explicit.
- Add Light/Dark themes, responsive radial work-map navigation with zoom and
  pan, every-node details, semantic status strips and repository/license links.
- Give browser observation a configurable 30-second default budget, bounded
  from 1 through 120 seconds. This fixes scan availability, not scan speed.
- Keep installed model guidance synchronized with checked task outcomes and
  document worker escalation, effort defaults and truthful agent attribution.
- Correct completion expectations, continuation test deadlines and interruption
  fixture startup budgets. Preserve
  all default release assertions and clearly label partial diagnostic modes.

## 0.5.3 — browser workspace and work policies — 2026-10-08

[Official release](https://github.com/danielmevit/unio/releases/tag/v0.5.3). Published from exact source `ae61bf3d11ff` after the full release gate, packaged installer checks and upgrade/rollback checks.

- Observe actual native launch attempts across timeout/replay tests. Keep real
  deadlines and Unknown/no-retry behavior when a Python mock is killed before
  it can write its entry log. Production launch deadlines remain unchanged.
- Measure provider timeout from the mock's own monotonic start; require live
  parent and child identity/session observations and bounded termination. Keep
  startup/final bookkeeping separate from the provider limit, bound the whole
  test harness and prove the next same-budget run can obtain its released slot.
- Document the owner preference for Grok on nuanced reasoning, observed Gemini
  review gaps and native AGY Opus's supported model default without an effort flag.
- Upgrade cleanup recognizes the exact markerless v0.4.0 completion and removes
  aliases only when their target is an owned legacy install. Preserve unrelated
  targets, their aliases and modified completion files.
- Run a real task from the local browser: save a draft, preview its frozen scope
  and checks, approve spending, start once, verify, review and accept the current
  revision. Immutable ownership, action intents and revision binding prevent a
  refresh from silently repeating a spending action.
- Follow short worker updates, open protected Source output and browse tracked
  worktree text files. Output and files require explicit startup grants and never
  dispatch another worker. Git observation has bounded output and deadlines,
  with cleanup of the exact owned process group and a confirmed worktree root.
- Add `unio mode yolo|medium|safe`, `unio tier low|medium|high`, `unio lead`,
  `unio account` and `unio policy`. Persist strict atomic state, group aliases
  sharing a budget, include the declared lead and enforce native capacities
  of one, two or four independent workflows per group. Frozen checks and owner
  permissions remain unchanged; reported subscription capacity stays Unknown.
- Admission requires a complete bounded reply before any provider starts.
  Slots remain visible and locked while the provider runs, then release and reap
  the actual holder. Run and review stop their owned provider on interruption;
  quality-start failures retain their original status. Bounded mock regressions
  cover the shared budgets, partial replies, failure, timeout and signal cleanup.
- Preserve caller stderr after closing control descriptors and keep EXIT cleanup
  roots/pidfiles as quoted data after their function locals expire. Generated
  runtime ShellCheck passes; a new check proves fd closure and stderr visibility.
- Preserve the loop-brake overlap scenario with explicit two-slot mock capacity,
  then restore low tier. The real low-tier contract remains enforced.
- Transport large UTF-8 tasks and review material without placing the entire
  file in one command argument. Claude and Codex use stdin, Grok uses
  `--prompt-file`, OpenCode uses `--file`, and Antigravity receives a short file
  pointer. Existing custom agent configuration is preserved; doctor reports
  legacy substitutions without changing or running them.
- Keep whole-file transport regressions current with the effective policy header:
  compare delivered bytes and the unchanged original separately for all five
  source/reviewer routes, preserving bounds and no-shell-execution checks.
- Validate and bound browser storage documents before recording ownership;
  store request/scope/check companions as UTF-8 JSON. HTTP errors use fixed public
  mappings and browser recovery reads state without automatic POST retries.
- Clarify main implementation and routine free-worker roles, correct Gemini Pro
  to its native High/Low variants, document 90–120-minute implementation budgets,
  and use the new tagline across README, installed help, version and attribution.
  Document a ready queue so independent tasks continue across available accounts
  while other workers are busy; low tier remains one workflow per shared account.

The browser remains a local source preview. See [the release overview](docs/RELEASE-0.5.3.md)
and [startup guide](bridge/README.md). Automatic recovery saves and lead cooldown
restart are planned for v0.5.4.

## 0.5.2 — durable queue approval — 2026-10-06

[Official release](https://github.com/danielmevit/unio/releases/tag/v0.5.2). Published from the original gated milestone; tag and source history are preserved.

- Added schema-2 queue job store with durable approve, reserve, unknown and cancel states.

- Fixed the queue job store: it now refuses unknown or under-constrained schema-1 and schema-2 layouts and corrupt legacy records without changing the database, and identical approve/reserve replays recheck the current draft.

Reject impossible queue state metadata and unknown CHECK/generated layouts unchanged; preserve recognized migrations and valid replays with exhaustive corruption regressions.

## 0.5.1 — truthful limit observations — 2026-10-06

[Official release](https://github.com/danielmevit/unio/releases/tag/v0.5.1). Published from the original gated milestone; tag and source history are preserved.

Unio 0.5.1: a run now counts as failed for the limit helper
only on a nonzero actual exit or the empty-work rule (zero commits against
the base and zero uncommitted files), preserving the real exit in every
receipt, and one normalized final 60-line window (ANSI/control escapes and
carriage returns stripped, never executing log text) drives both the
report display and matching while the raw log is kept. The warning and
ledger wall=1 mean suspected limit language, never a confirmed quota, and
a successful run with work stays wall=0. Worker text never benches an
agent or writes availability/configuration state: UNIO_AUTO_OFF is
accepted for compatibility and has no effect, while explicit unio off/on
remains the operator's control. Help, docs/PROTOCOL.md with its embedded
copy and docs/QUALITY-USAGE.md are updated, and tests/unio-limit-wall.py
replaces the automatic-bench expectations with regressions for genuine
phrases, printed repository text, exit-zero empty work, successful and
failed committed work, ANSI/carriage returns, a phrase 50 lines from the
end, and AUTO_OFF=1 with unchanged availability/config files.

Unio 0.5.1: guarantee 5 checks the failed mock's real exit and suspected-limit warning, unchanged availability with UNIO_AUTO_OFF=1, and explicit off/refusal/on behavior.
The adversarial demo honors UNIO_BIN_DIR and the incoming UNIO_CONF_DIR for its engine and template source while retaining isolated mock configuration and existing defaults.

## 0.5.0 — Unio rename — 2026-10-06

[Official release](https://github.com/danielmevit/unio/releases/tag/v0.5.0). Published from the original gated milestone; tag and source history are preserved.

- The project is renamed to Unio.
- The command is `unio` (all old aliases like `frugal-flock` and `agentteam` are removed).
- Configuration folder is now `~/.config/unio`. Environment variables are prefixed with `UNIO_`.
- Updated installer to `unio-install.sh`.
- The installer copies existing default configuration into `~/.config/unio`, preserving the original. The development workspace migrated to Unio 0.5.0 with owner approval on 2026-10-05; the completed milestone was published on 2026-10-06.

## 0.4.0 — 2026-10-04 — trustworthy results (M1)

The first published release under the Frugal Flock name. It completes M1,
the quality milestone, which the owner accepted on 2026-10-04. Frozen
contract: [QUALITY-M1-CONTRACT.md](docs/QUALITY-M1-CONTRACT.md); evidence
per clause: [M1-ACCEPTANCE-AUDIT.md](docs/M1-ACCEPTANCE-AUDIT.md).

### Upgrade notes

- **Stricter verification.** `verify` passes only with at least one
  `- path` line under `## Allowed scope` and at least one `$ command` line
  under `## Validate`. A task missing either now ends INCOMPLETE (exit 2)
  instead of PASS. Real failures exit 1.
- **Review is gated.** `review` needs a current passing `verify` and clean,
  committed, text-only work of at most 300000 bytes, and accepts exactly one
  standalone `VERDICT:` line from the reviewer's stdout. Exits 0/1/2.
- **Python 3 is required** (standard library only, nothing downloaded) for
  run, verify, review, smoke, agents, result and handoff.
- Existing commands, `agentteam`, `AGENTTEAM_*` variables, config paths and
  the Linux `flock` dependency all keep working.

### Name and commands

- The product is now Frugal Flock: "Small plans. Big ideas." New commands
  `frugal-flock` and the short `frgl-flc`, with completion; `agentteam`
  remains as a compatible alias. The GitHub repository is now
  `danielmevit/frugal-flock`, with a plain-language README.

### Reliability (M1)

- `verify` fails closed: missing scope or checks are INCOMPLETE, never PASS;
  a missing base branch is a failure. With `AGENTTEAM_AUTO_VERIFY`, a worker
  failure keeps its own exit and failed or incomplete checks make a
  successful run nonzero.
- Structured results: each worker/task gets a schema-versioned JSON result in
  `coord/results/`, read with `result`. Process, validation and review
  states are separate and bound to a revision of the commit, base, task file
  and worktree contents, so any change marks old evidence stale.
  `ready_for_human_review` is never human acceptance.
- `review` parses the verdict conservatively and records it per revision.
- `agents --json` reports local availability without running agents or
  probing sign-in or quota; programs are resolved past quoted shell syntax.
  `doctor` checks for Python 3 and handles environment-prefixed agent lines.
- `handoff` writes a same-checkout context packet for the next AI. It is
  context, not a backup.
- Live commands state the `trusted_host` boundary: worktrees are not OS
  sandboxes.
- Unsupported worktree states fail closed: assume-unchanged/skip-worktree
  index flags (they hid edits from scope and review), FIFOs, devices,
  sockets, nested repositories and submodules. If the snapshot fails right
  after a run, `run` still records the worker's real exit, report and
  ledger line (`snapshot_failed`).
- Scratch left by an interrupted handoff or a killed result write is
  removed by the next locked operation.

### Engine fixes and tests

- `init` no longer blocks on CodeGraph indexing; it is detached and
  time-boxed (CG-1).
- A sandboxed adversarial probe suite (`tests/agentteam-probes.sh`, 14
  probes) demonstrated 11 defects, all closed (SABAT-1).
- `tools/quality-check.sh` runs every check in temporary directories:
  40 selftests, 120 mock-only quality checks, the probes, branding,
  ShellCheck and docs lint. Timing-dependent tests and a selftest cleanup
  race no longer fail on slow drives.

### Documentation

- Help, completion and the operational protocol cover the new commands and
  exits. `docs/QUALITY-USAGE.md` is the complete M1 reference; SETUP,
  HANDBOOK, GUIDEBOOK (and its Word file) and the README match the release.
- A single living continuation prompt (`continue-with-ai-prompt.md`), the
  one-folder workspace rules, the agent-log rule, research findings and the
  UX direction preserve context across AI tools and usage limits.
