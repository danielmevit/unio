# CLI-UPDATES — AI CLI version facts and held-safe updates (2026-11-10)

Multi-day Unio work runs on subscribed AI CLIs that release frequently.
This feature makes staleness visible and updates explicit — it never
updates silently and never interrupts a frozen or active task.

Surface:

- `unio update clis --check [--json] [agents...]` — facts only.
- `unio update clis [--json] [agents...]` — the explicit update request.
- One awareness line at the human entry points `unio doctor` and
  `unio resume` (the chosen existing startup points; plain `unio` prints
  help and is not a session entry). `UNIO_CLI_UPDATES_OFF=1` disables the
  awareness and its refresh entirely (tests, offline or batch hosts).

## Check (`--check`)

For every recognized route — antigravity (`agy`), vibe, grok, copilot,
opencode, claude, codex; aliases deduplicate onto one route report — the
check records, per route: installed version, latest version, cache age,
install method, present/absent, update support, update state, busy/lead
holds, and compatibility `unknown`. Nothing else: no model, auth, plan,
billing or default reads, no route dispatch, no write outside the cache.

- Installed version: the CLI's own read-only `--version`, run as a fixed
  argv array from a bounded subprocess. `uv tool list` (read-only) is used
  to verify a uv-managed vibe; grok's documented read-only
  `update --check --json` provides its latest version.
- Latest version: official metadata only — the GitHub release of
  `google-antigravity/antigravity-cli`, PyPI `mistral-vibe` (only for a
  verified uv-managed vibe), the npm registry (only for npm-installed
  copilot/claude/codex/opencode). A source that is not authoritative for
  the detected install method is honestly `Unknown` — never guessed. No
  credential scraping; no endpoint content is ever executed or evaluated.
- A check NEVER calls an installing updater. Default routes are the
  recognized installed ones; unknown agent names refuse with usage exit 2.
- `--json` prints strict, versioned, additive JSON (`schema_version` 1).
- The last result cache lives in `$UNIO_CONF_DIR/cli-updates/cache.json`
  (observations only — never commands, never secrets or account ids).
  Fresh cache (default 24 h) means no network and no grok call. A corrupt,
  missing or unsafe (symlink/nonregular) cache is `Unknown`; it is never
  authorization to run anything. Facts older than the bound are refetched.
- Exit: 0 for facts, 1 if any present tool's version probe failed, 2 for
  usage errors. `UNIO_CLI_UPDATES_OFFLINE=1` forbids all network metadata
  fetches (statuses become `network-disabled`) without failing the check.

## Update (`unio update clis [agents...]`)

Runs, per route, only that CLI's official updater, with the exact argv:

| route | command (frozen) | condition |
|---|---|---|
| antigravity | `agy update` | installed |
| vibe | `uv tool upgrade mistral-vibe` | install verified uv-managed |
| grok | `grok update --stable` | installed (stays natively benched otherwise) |
| copilot | `copilot update stable` | installed |
| opencode | `opencode upgrade` | installed, never `--major` |
| claude, codex | no updater | check-only (codex stays lead-only); manual plan printed |

- Missing tools are skipped; unknown/custom installs and unsupported
  methods are reported and refused, never guessed. No major-version
  switches and no installation-method switches ever happen through unio.
- Refusal BEFORE any updater call: STOP owner hold, any held project
  worker lock, a native process with the exact executable identity
  (`/proc/<pid>/exe` or an exact cmdline element equals the resolved CLI
  path — never process-name guessing), or an unavailable identity scan.
  Ambiguity means manual/refusal, not permission. One update lock
  (cli-updates/update.lock) also prevents duplicate updater batches.
  Refusals carry an actionable manual plan; unio never signals, kills or
  restarts any job, and never touches an existing external Claude process.
- Each result reports the actual updater exit code, the before/after
  installed versions (truthful; a standalone copilot download applies at
  its next launch), and a bounded tail of updater output where relevant.
  A partial batch is reported truthfully and exits nonzero if any route
  failed or was refused; one failed tool never hides other results.
- Updating does NOT prove compatibility: compatibility stays `unknown`,
  route version guards and adapter pins are untouched (`--check` states
  this), and the bounded offline re-probe after an update is the only
  automatic ceremony. Run `unio smoke` per agent after a real update
  (that has always been the project rule for CLI updates).

## Daily startup awareness

`doctor` and `resume` print exactly one line — cached freshness only
(`never checked` / `fresh` / `stale`, with the command hint). A stale
cache (default 24 h, `UNIO_CLI_UPDATES_MAX_AGE`) spawns at most one
bounded background refresh (hard deadline, default
`UNIO_CLI_UPDATES_DEADLINE`=45 s; owned non-blocking lock, so no
duplicate or orphaned jobs can accumulate beyond the deadline). The
background refresh never executes a CLI binary or updater — only
filesystem metadata and the official metadata URLs above — and it never
writes to stdout or JSON. So during multi-day work, the first checkpoint
each day either has fresh facts or starts a bounded refresh; the next
`unio doctor` / `unio update clis --check` shows them.

Stated visibility limits: busy detection covers this machine's own
processes by exact executable identity and the current project's locks
and STOP. Other users, other hosts, and cross-workspace/unmanaged
sessions are invisible; same-uid processes whose identity cannot be read
(non-dumpable daemons) are counted as unidentifiable in the JSON facts.
An update is refused when identity cannot be scanned at all. There is
no OS-sandbox or global-account enforcement and no daemon: unio observes
and refuses; it does not control what it does not own.

## Deferred (explicit non-goals of this slice)

- Admission coordination inside native run/review start (an update-vs-
  launch shared/exclusive lock pair) is not yet wired into `unio run`:
  the race is bounded only by the refusal gate above. The safe path until
  then: freeze with STOP or update when no run is dispatched. The
  deferred plan: `run`/`review` take a shared flock on
  `coord/.locks/cli-update.lock`; `update clis` takes it exclusively, so
  an updater waits for launches to finish and launches wait for the
  updater — no behavior change on success, one new lock file.
- Full latest-version metadata for native (non-npm) opencode and
  standalone copilot: no read-only official endpoint was verifiable on
  2026-11-10, so latest stays Unknown (manual) for those installs.
- Claude/Codex remain check-only: their natives also cover other
  accounts (claude) and lead-only usage (codex), so unio never runs
  their updaters in this slice.

Env: `UNIO_CLI_UPDATES_MAX_AGE` (seconds; default 86400 = daily),
`UNIO_CLI_UPDATES_TIMEOUT` (metadata seconds per request; default 10),
`UNIO_CLI_UPDATES_DEADLINE` (refresh total; default 45),
`UNIO_CLI_UPDATES_INSTALL_TIMEOUT` (updater bound; default 1800),
`UNIO_CLI_UPDATES_OFF=1` (awareness off), `UNIO_CLI_UPDATES_OFFLINE=1`
(no network metadata fetches).

Implementations: `tools/cli-updates.py` (canonical, standard library),
embedded byte-identically by `tools/embed-cli-updates.py` as
`$UNIO_CONF_DIR/lib/cli-updates.py`. Tests:
`tests/unio-cli-updates.py` (offline fixtures only; never the real CLIs).
