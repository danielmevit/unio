# CLI-UPDATES — AI CLI version facts; installs manual-only (2026-11-10)

Multi-day Unio work runs on subscribed AI CLIs that release frequently.
This slice makes staleness visible and updates explicit — it never updates
silently, never interrupts a frozen or active task, and NEVER installs at
all: every update request is refused with a truthful per-route reason and
a manual plan (see Update below).

Surface:

- `unio update clis --check [--json] [agents...]` — facts only.
- `unio update clis [--json] [agents...]` — the explicit update request;
  it refuses to install for every present target with a truthful
  per-route reason — `maintenance_not_implemented` for installable
  routes (no run/review maintenance lease exists yet),
  `check-only-route` for claude/codex, `manual-unverified-install` for a
  vibe outside the verified uv layout — plus a frozen manual plan.
- One awareness line at the human entry points: plain `unio` (help is the
  default entry), `unio doctor` and `unio resume` — cached facts or
  Unknown only. The bounded background refresh runs only at genuine
  interactive owner entry (stdin AND stdout are a TTY); scripted, piped
  and fixture invocations never touch the network and never spawn
  detached writers. `UNIO_CLI_UPDATES_OFF=1` disables the awareness
  entirely (tests, offline or batch hosts).

## Check (`--check`)

For every recognized route — antigravity (`agy`), vibe, grok, copilot,
opencode, claude, codex; aliases deduplicate onto one route report — the
check records, per route: installed version, latest version, cache age,
install method, present/absent, update support, update state, busy
observations (STOP, held worker locks, native process identity), the
exact native identities checked, and compatibility `unknown`. Nothing
else: no model, auth, plan, billing or default reads, no route dispatch,
no write outside the cache. Latest-version metadata is NEVER fetched for
an absent binary: a route with nothing installed reports latest Unknown
honestly.

- Installed version: the CLI's own read-only `--version`, run as a fixed
  argv array from a bounded subprocess (output and time bounds enforced
  during capture; only the probe's own child session is ever cleaned).
  grok's documented read-only `update --check --json` provides its latest
  version. Where a CLI documents one (claude's `DISABLE_AUTOUPDATER`,
  vibe's `VIBE_ENABLE_UPDATE_CHECKS`/`VIBE_ENABLE_AUTO_UPDATE` — the same
  flags this project's worker uses), native auto-update flags are set for
  the read-only probe. The uv-tool label is bound to the binary actually
  on PATH: it requires the resolved executable's real path to sit inside
  the validated uv tools layout; `uv tool list` output carries no path, so
  it is never used to guess the method of a different install.
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
  Reads are bounded, nonblocking, no-follow and refusal-safe: the state
  directory is pinned by a no-follow directory fd (a symlinked state
  directory or a symlinked/nonregular/FIFO cache — which can never block
  startup — is quiet `Unknown`), the byte cap is checked before any read
  and again during it, and a deep, duplicate-keyed, nonfinite, malformed,
  oversized or wrong-typed-field (string fields are validated, bounded
  and control-character-clean) cache is quiet `Unknown` — never a
  traceback, never trusted, never authorization to run anything. A
  `checked_at` timestamp in the future beyond a 300 s clock-skew
  tolerance is Unknown, never fresh-forever (WSL clock skew is real).
  Writes go through a fresh private temp file created, written, replaced
  and cleaned up relative to that pinned directory fd (never reopening
  the pathname or following a swapped directory), so independent
  concurrent checks cannot collide on or overwrite unrelated files;
  writing through a symlink (state
  dir, cache or `refresh.lock`) is refused. Facts older than the
  freshness bound (default 24 h) are refetched.
- Exit: 0 for facts, 1 if any present tool's version probe failed, 2 for
  usage errors. `UNIO_CLI_UPDATES_OFFLINE=1` forbids all network metadata
  fetches (statuses become `network-disabled`) without failing the check.

## Busy facts are observations — never permission, never idle proof

Detection covers this project (worker locks, STOP) and same-uid native
processes with exact validated executable identity: `/proc/<pid>/exe` or
an exact cmdline element equals one of the route's exact identities. For
a verified uv-managed vibe the launcher `.../uv/tools/mistral-vibe/bin/vibe`
and its native `.../site-packages/vibe/_bin/vibe-rs` are both covered
(validated live on 2026-11-10 — a live session matched the native, not the
launcher). No process names are ever guessed, and no other layout adds a
second identity. A NONZERO number of unidentifiable same-uid processes
means the busy fact is `Unknown` (`busy-identity-unknown`) — it is never
reported as confirmed idle. Other users, other hosts, cross-workspace
unmanaged sessions and same-uid daemons are invisible; an unavailable
identity scan is also `Unknown`. Known blind spot, stated honestly:
candidates are real paths, so a node/python session started through a
PATH symlink (its `/proc exe` is the interpreter, its cmdline element is
the symlink) is not counted as native-process-active; identity is never
inferred to bridge that gap. Since installs are refused anyway, no
claim of full native visibility is made — these are observed facts only.

## Update (`unio update clis [agents...]`) — manual-only apply policy

Until a shared native maintenance/admission lease between `unio
run`/`review` and any updater exists, the update command REFUSES to
install for EVERY present target:

- Every present route is refused with a truthful per-route reason plus
  that route's frozen manual plan: `maintenance_not_implemented` (the
  lease is genuinely missing) for the installable routes — agy →
  `agy update`; vibe → `uv tool upgrade mistral-vibe` (only when the
  resolved vibe binary sits in the verified uv tools layout); grok →
  `grok update --stable`; copilot → `copilot update stable`; opencode →
  `opencode upgrade` (never `--major`); `check-only-route` for claude/
  codex (check-only by policy, codex lead-only), which never implies a
  future lease would install them; `manual-unverified-install` for a
  vibe outside the verified uv layout (its update stays manual).
- Absent routes are skipped truthfully. No updater or installing probe is
  ever constructed or executed by unio — regardless of STOP, worker
  locks, process state, cache content, flags or environment. There is
  deliberately no bypass: these commands exist only as the fixed, safe
  manual plans above, printed with the refusal.
- Missing tools and check-only routes are reported truthfully; nothing is
  guessed and no installation-method switch ever happens through unio.
- Any refusal makes the command exit nonzero; every route is always
  reported. Compatibility always stays `unknown`: updating (manually) does
  not prove route/adapter compatibility; version guards and adapter pins
  are untouched, and after a real manual update `unio smoke` per agent
  remains the project rule.

The automatic installation path is DEFERRED, not abandoned: the plan is a
shared/exclusive `coord/.locks/cli-update.lock` pair — `run`/`review` take
it shared, the updater path takes it exclusively — introduced together
with a native maintenance lease in a separate task. Until that exists,
`unio update clis` claims nothing about installing; only `--check` and
the awareness line are working features of this slice.

## Daily startup awareness (interactive refresher, offline otherwise)

Plain `unio`, `doctor` and `resume` print exactly one line — cached
freshness only (`never checked` / `fresh` / `stale` / `unknown`, with the
command hint). Noninteractive invocations — scripts, pipes, cron, IDE
integrations, test fixtures — stay fully offline by default: no network
metadata fetch and no detached writer is ever spawned; they show the
cached facts or Unknown. A genuinely interactive owner entry (stdin AND
stdout are a TTY) with a stale (default 24 h, `UNIO_CLI_UPDATES_MAX_AGE`)
or absent/Unknown cache spawns at most one bounded background refresh
(owned lock opened nonblocking and no-follow, so a FIFO or symlinked
`refresh.lock` is refused, never written through; hard deadline enforced
twice: SIGALRM stops the refresh and, for a process hung where the alarm
cannot run — e.g. a pathological DNS lookup — an exactly-owned watchdog
child SIGKILLs it 15 s past the deadline, by exact pid and boot start
time, so no detached child outlives its bound). The background refresh
never executes a CLI binary or updater, never fetches latest for an
absent binary — only filesystem metadata and the official metadata URLs
above — and it never writes to stdout or JSON, so `doctor --commands
--json` and every machine surface stay untouched. A future-dated
`checked_at` (beyond the 300 s clock-skew tolerance) is Unknown, never
fresh, so the daily recheck cannot be silently disabled. The first
interactive checkpoint each day either has fresh facts or starts a
bounded refresh; the recheck happens at the next invocation — there is
no daemon and no background writer while an automation works. Explicit
`unio update clis --check` remains the bounded metadata opt-in for any
noninteractive caller that wants fresh facts.

## Deferred or refuted (explicit non-goals of this slice)

- Automatic installation deferred: see Update above. `unio update clis`
  is not an install manager and does not claim to be one.
- Full latest-version metadata for native (non-npm) opencode and
  standalone copilot: no read-only official endpoint was verifiable on
  2026-11-10, so latest stays Unknown (manual) for those installs.
- Claude/Codex remain check-only: their natives also cover other accounts
  (claude) and lead-only usage (codex), so unio never runs their
  updaters.
- Cross-user, cross-host and unmanaged-session visibility: impossible and
  never claimed; unio observes and refuses, it does not control what it
  does not own.

Env: `UNIO_CLI_UPDATES_MAX_AGE` (seconds; default 86400 = daily; the
explicit `--max-age-seconds` flag overrides it), `UNIO_CLI_UPDATES_TIMEOUT`
(metadata seconds per request; default 10; the explicit `--timeout` flag
overrides it for `check`), `UNIO_CLI_UPDATES_DEADLINE` (refresh total;
default 45),
`UNIO_CLI_UPDATES_OFF=1` (awareness off), `UNIO_CLI_UPDATES_OFFLINE=1`
(no network metadata fetches).

Implementations: `tools/cli-updates.py` (canonical, standard library),
embedded byte-identically by `tools/embed-cli-updates.py` as
`$UNIO_CONF_DIR/lib/cli-updates.py`. Tests:
`tests/unio-cli-updates.py` (offline fixtures only; never the real CLIs).
