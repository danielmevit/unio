# CLI-UPDATES-SAFETY-20261110 — slice corrections: installs refused, honest Unknown facts, bounded nonblocking reads/probes, interactive-only refresh

Correction to CLI-UPDATES-20261110 (same day, same base 3e5d38c9) after
live lead probes found real failures. ZERO real updates, providers,
accounts or auth were touched; the evidence used private-tmpfs fixtures
and read-only probes only.

`unio update clis` now REFUSES to install for EVERY present target with
the explicit reason `maintenance_not_implemented` plus the route's frozen
manual plan, until a shared native run/review maintenance/admission lease
exists (deferred, not attempted here). No updater or installing probe is
ever constructed or executed — regardless of STOP, worker locks, process
state, cache content, flags or environment; there is deliberately no
bypass. Unio does not claim to be an install manager; only `--check` and
the startup awareness are working features.

Busy facts are honest observations, never permission and never idle
proof: a NONZERO count of unidentifiable same-uid processes now reports
busy-identity-unknown (the frozen code only rejected a missing scan, so an
ambiguous machine looked confirmed idle — live probe found 2 obscured
processes while an update would have run). A verified uv-managed vibe now
checks both exact identities — the `bin/vibe` launcher and its
site-packages `vibe/_bin/vibe-rs` native (live 2026-11-10 evidence: a
real Source session matched only the native identity) — via that one
validated layout only; no process names are guessed and other layouts do
not gain identities. Rows state the identities checked and the
cross-user/host/workspace limits.

Cache reads are strictly bounded and no-follow: the byte cap is checked
BEFORE any read (fstat) and again during it; O_NOFOLLOW refuses symlinks;
deep (the noted 200000-byte RecursionError probe), duplicate-keyed,
nonfinite, malformed, oversized and nonregular caches are quiet Unknown
with no traceback and no startup block. Writes use a per-check private
temp file (no fixed cache.json.tmp name), so independent concurrent
checks cannot unlink or overwrite unrelated files; symlinked state dir
or cache is never written through.

probe/run_bounded is bounded DURING capture (output bytes and wall time),
no longer capture-all-then-slice; on truncation/timeout only the exactly
owned child session (own process group) is cleaned — no signals to other
sessions. Read-only version probes set documented native auto-update
flags where they exist (claude DISABLE_AUTOUPDATER) and can never install.

Plain `unio` (help) now prints the one read-only awareness line like
doctor/resume: cached freshness only (fresh <= 24 h: no refresh), one
bounded background refresh on staleness or absence (hard deadline, owned
non-blocking lock, no stdout, no CLI execution, no updater), rechecked at
the next invocation — no daemon. `doctor --commands --json` and machine
JSON stay untouched; UNIO_CLI_UPDATES_OFF=1 silences and disables
everything; UNIO_CLI_UPDATES_OFFLINE=1 forbids all metadata fetches.

Focused offline suite tests/unio-cli-updates.py rewritten accordingly:
every update case proves ZERO updater/probe calls across ordinary,
failure, STOP, worker-lock, native-session and malicious-cache fixtures;
deep/duplicate/nonfinite/oversized cache regressions (from 200000 bytes),
fresh-TTL reuse, concurrency and no-write-through-symlink; hanging and
flooded probe bounds with bystander sessions never signalled; obscured
Unknown and the vibe launcher/native pair; engine help/awareness/
payload-consistency checks. Compatibility stays Unknown; route guards and
adapter pins untouched; no model, provider, auth or account calls.

Same-day review correction (external REQUEST-CHANGES on the exact base,
reproduced with fake fixtures and a local canary proxy only): cache and
lock reads are now NONBLOCKING as well as no-follow — a FIFO or device
cache.json or worker lock can never block startup, and the state
directory is refused on read AND write through a pinned no-follow
directory fd (a symlinked state dir's hostile facts are Unknown, a
symlinked cache or refresh.lock is never written through; the refresh
lock itself is opened O_NOFOLLOW|O_NONBLOCK with a regular-file check
before any truncate). Cached route fields are validated field by field:
wrong-typed or oversized strings (status 5, version 7, control
characters) are quiet Unknown with no traceback, never reused or printed.
A `checked_at` timestamp in the future beyond a 300 s clock-skew
tolerance is Unknown — never fresh-forever (WSL clock skew). The refresh
deadline is now hard twice: Deadline is a BaseException that no per-route
`except Exception` can swallow, and an exactly-owned watchdog child
(SIGKILL by exact pid plus boot start time, 15 s past the deadline)
bounds the process through its actual lifetime — so DNS/slow-read hangs
cannot outlive their bound; a post-kill wait TimeoutExpired is handled
honestly (a D-state child may survive: exit stays None/Unknown, never a
false killed claim). The automatic startup refresh now runs ONLY for
genuine interactive owner invocations (stdin AND stdout are a TTY);
noninteractive plain unio/help/resume/doctor invocations stay fully
offline with no detached writers, latest is never fetched for an absent
binary, quality-check.sh sets UNIO_CLI_UPDATES_OFFLINE=1 explicitly for
the fixture gate, and explicit --check stays the bounded metadata opt-in.
UNIO_CLI_UPDATES_MAX_AGE and _TIMEOUT now really apply to startup and
check (explicit flags still override them; the argparse default no longer
masks the env). Read-only probes set vibe's documented auto-update flags
(VIBE_ENABLE_UPDATE_CHECKS/VIBE_ENABLE_AUTO_UPDATE=false — the worker's
own pair); the uv-tool label is bound to the resolved binary's real path
inside the validated uv tools layout only (uv tool list output carries no
path, so it can never mislabel another install). Update refusals carry
truthful per-route reasons — maintenance_not_implemented, check-only-route
(claude/codex), manual-unverified-install (vibe outside the verified uv
layout) — and docs/help/changelogs describe the actual manual-only policy,
computed observations and known limits (node/python sessions started
through PATH symlinks are a stated unmatched blind spot). New offline
regressions cover every reproduced defect: FIFO cache, symlinked state
dir on read, wrong-typed entries, refresh.lock symlink, hard deadline
against a hanging local proxy, noninteractive no-refresh/network-noise,
interactive pty refresh, future timestamps/WSL skew, env precedence and
uv-tool binding.
