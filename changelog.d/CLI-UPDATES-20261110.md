# CLI-UPDATES-20261110 — AI CLI update facts, awareness and manual-only updates (installs refused)

Unio development source (branched from 0.5.25 base 0c9827f5): native AI-CLI
update awareness without touching active work — check-only facts and daily
cached awareness; `update` refuses every install and prints frozen manual
plans. (Superseded same-day by CLI-UPDATES-SAFETY-20261110.md, which
records the refused-install policy and the review-driven safety fixes.)

New `unio update clis --check [--json] [agents...]` records read-only facts
per recognized route (antigravity/agy, vibe incl. mistral aliases, grok,
copilot, opencode, claude, codex): installed version (the CLI's own
`--version`, fixed argv), latest version from official metadata only
(GitHub release for antigravity; PyPI for a verified uv-managed vibe; npm
registry only for npm-installed copilot/claude/codex/opencode; grok's
documented read-only `update --check --json`), checked_at/age, install
method label, presence, support (native/uv-tool/check-only), busy
observations (STOP, worker locks, native process identity),
compatibility unknown. Missing tools are absent, unknown/custom
installs honestly Unknown, aliases deduplicate; a check never calls an
installing updater, never executes agents.conf/task/report/cache text and
never makes a model, auth, plan or billing call. Results cache in
$UNIO_CONF_DIR/cli-updates/cache.json (strict schema 1; observations only,
never commands or identifiers); corrupt, missing, symlinked or nonregular
cache is Unknown; a fresh cache (default 24 h) causes no network.

`unio update clis [agents...]` was planned as the explicit request to run
each route's official updater with frozen argv (agy update; uv tool
upgrade mistral-vibe only for a verified uv-managed vibe; grok update
--stable; copilot update stable; opencode upgrade without --major).
claude/codex stay check-only (codex lead-only). IMPORTANT: that update
execution was NEVER released — the same-day correction refuses every
present target (see CLI-UPDATES-SAFETY-20261110.md), so there is no
update lock, no batch and no before/after result: only the refusal plus
the frozen manual plan is real. Ambiguity is refusal with a manual plan,
never permission; compatibility stays unknown; route version guards and
adapter pins are untouched; no major-version or installation-method
switches ever happen through unio.

Human entry points plain `unio` (help), `unio doctor` and `unio resume`
print one read-only freshness line from the cache; only a genuinely
INTERACTIVE entry (stdin and stdout are a TTY) with a stale cache
(>24 h default) spawns one bounded background refresh (owned non-blocking
lock, hard double deadline — SIGALRM plus an exactly-owned watchdog —
no stdout, no CLI execution), so multi-day work sees daily rechecks
without a daemon and without blocking startup, while scripted/fixture
runs stay fully offline by default. UNIO_CLI_UPDATES_OFF=1 disables
awareness explicitly; UNIO_CLI_UPDATES_OFFLINE=1 forbids all network
metadata fetches. Stated limits: cross-user, cross-host, unmanaged and
non-dumpable same-uid processes are invisible and reported as such;
node/python sessions started through PATH symlinks are a known unmatched
blind spot (identity is never inferred); no OS-sandbox or global-account
enforcement; run/review admission coordination with the maintenance
lease is deferred with a documented plan instead of introducing a
launch-vs-update race.

Canonical `tools/cli-updates.py` (standard library), embedded
byte-identically by `tools/embed-cli-updates.py` as
$UNIO_CONF_DIR/lib/cli-updates.py with the installer's unsafe-path
preflight; engine dispatch/help/completion glue is minimal;
`docs/CLI-UPDATES.md` documents check vs update, daily behavior, frozen
holds, and the deferred application path. Focused offline suite
`tests/unio-cli-updates.py` proves check/update/refusal/startup/
consistency behaviors with fake CLI executables, metadata and caches
only — no real CLI, provider or network call, no real installation
mutated.

Supersession (same day, before release): the `update` section above is
superseded by CLI-UPDATES-SAFETY-20261110.md — `unio update clis` refuses
every present target with maintenance_not_implemented (no updater is ever
executed by unio) until a shared maintenance lease exists; busy facts are
observations that mean Unknown, never idle proof; cache reads/writes and
probes gained the strict bounds described there; plain `unio` also prints
the awareness line. --check and the daily awareness behave as described.
