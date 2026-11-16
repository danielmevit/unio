# Validation matrix and quality-gate lanes

First 0.5.33 batch: developer tooling for Unio itself. `tools/quality-check.sh`
run without arguments is still the full offline gate — every original suite,
in the original order, with the original `UNIO_*` offline and auto bounds
(plus `PYTHONDONTWRITEBYTECODE=1` for every child, an intentional minor
addition — not a byte-identical environment), first-failure semantics and
success string. What this batch adds is measurement and selection, so a Fast
loop can run the relevant checks without hand-written command lists and
without pretending a partial run is a full pass.

## Commands

| Command | Behaviour |
| --- | --- |
| `bash tools/quality-check.sh` | Full offline gate: all 126 catalogue commands in canonical order. The first failing command stops the run and its exit code becomes the gate's. Only a complete full run prints `quality-check: all checks passed`. |
| `bash tools/quality-check.sh --list` | Dry listing of the selected (or full) command ids and commands. Runs nothing, installs nothing, creates no fixture, changes no configuration and never claims a pass. |
| `bash tools/quality-check.sh --lane NAME` | Runs the named lane; repeatable. The union of the selected lanes is deduplicated and kept in canonical order. A successful lane run prints a PARTIAL coverage summary and never the full-gate success string. |

Unknown flags, unknown lanes, duplicate lanes and missing values exit 2
before any check or fixture is started. The ordered catalogue lives in
`tools/quality-gate-commands.json`; the dispatcher is `tools/quality-gate.py`.
The catalogue contains the original 125 commands plus one explicitly added
runner self-test (`tests/unio-quality-gate.py`, static lane); the tracked
snapshot `tests/fixtures/quality-gate-baseline.json` pins the original list so
any coverage or order drift is caught by the self-test. A run made with
`UNIO_QUALITY_GATE_CATALOGUE` set is always labelled `FIXTURE`/noncanonical
and never prints the full-gate success string, so no override or fixture can
certify the production catalogue.

## Lanes

| Lane | Covers |
| --- | --- |
| `static` | `bash -n` on the installer, all 22 `embed-*.py --check` checks, both `node --check` checks, `check-docs.sh`, and the runner self-test. Pure-read. |
| `install-smoke` | The private installer fixture (fresh install into a temp directory, shellcheck on the installed engine), installer-safety, neutral-startup, thin-config, selftest, role-cards. |
| `safety-core` | startup-refusal, `unio-quality.sh`, run-identity, loop-brake, limit-wall, lead-budget, work-policy, work-policy-guard, admission-deadline, remote-guard, kill-pid, native-stop, `unio-probes.sh`. |
| `evidence-review` | required-delivery, handoff-incomplete, task-outcomes, tail, scope-annotations, task-preview, the review family, report-reviews. The heavy lane. |
| `managed-lead` | codex-worker, worker-effort, managed-session, managed-lead, managed-lead-codex, lead-effort, lead-session, lead-session-codex, lead-session-policy, lead-effort-display, lead-cooldown. |
| `adapters` | opencode, prompt-transport, command-audit, cli-updates, perplexity, vibe, copilot, antigravity, adapters-install, route-profiles, adapter-outcome, adapter-budget. |
| `observation` | watch, orphan-observation, capacity (bridge and unio), readiness, fleet, model-experience, provider-capacity (bridge and unio). |
| `bridge` | The bridge unit and API tests, both `node --check` checks, browser-launcher, dashboard. |
| `delegation` | task-plan, worktree-cache, task-dispatch, task-dispatch-install, continuous-delegation, readiness-install. |
| `admission-env` | disk-preflight, host-space, the `embed-host-space.py` check, project-root. |
| `save` | The save and work-saving family, run-phases, save-capture-budget, wip. |
| `docs` | branding, `check-docs.sh`. |

The union of all lanes equals the full catalogue; the runner self-test
enforces this, the baseline comparison and the lane invariants. The installer
fixture is created only when a selected command needs it, and it is removed on
normal exit, command failure and handled `SIGTERM`/`SIGHUP` termination: the
gate forwards the signal to the command it currently owns (only that direct
child; its grandchildren are not signalled automatically), reaps it within a
bounded wait, removes the fixture and exits 128+signal. A signal already
ignored when the gate starts (for example `SIGHUP` under `nohup`) stays
ignored, so the gate keeps running as the legacy shell gate did. `SIGKILL`
and other unhandled signals cannot trigger this cleanup.
Every child runs with `UNIO_AUTO_VERIFY=0`, `UNIO_AUTO_OFF=0`,
`UNIO_AUTO_SYNC=0`, `UNIO_CLI_UPDATES_OFFLINE=1` and
`PYTHONDONTWRITEBYTECODE=1`; provider and model calls stay zero.

## Timings

Set `QUALITY_TIMINGS` to a file path to record every executed command. The
format is TSV with a header row, then one row per executed command, written
and flushed incrementally:

```text
id	command	start_utc	end_utc	elapsed_seconds	exit_code
bash-n-unio-install	bash -n unio-install.sh	2026-11-16T10:00:00.000000+00:00	2026-11-16T10:00:00.012345+00:00	0.012345	0
```

- `id` — the catalogue command id.
- `command` — the canonical rendering: environment assignments, then the
  argument vector joined by single spaces, then `> path` when stdout is
  redirected, with the temporary fixture directory substituted.
- `start_utc` and `end_utc` — ISO 8601 UTC timestamps.
- `elapsed_seconds` — monotonic-clock difference, six decimals.
- `exit_code` — the command's actual exit code; 128 plus the signal number
  when a signal killed it.

Tabs and newlines inside a field are replaced by spaces. No environment
variables, credentials or provider logs are recorded. A timing failure never
masks a check failure: a failing command's exit code wins. If every check
passed but the requested timing output was unusable, the gate exits 1 and
does not print the success string. With `QUALITY_TIMINGS` unset, output is
unchanged. `QUALITY_TIMINGS` is not inherited by child commands, so a nested
gate run (for example the runner self-test as the last command of a timed
full gate) cannot truncate or corrupt the outer timing file; a fixture
command that wants nested timings must set its own path explicitly.

## Matrix

| Stage | Fast | Balanced | Thorough |
| --- | --- | --- | --- |
| Developer loop | The lane(s) touching the changed surface; the task's frozen Validate lines remain mandatory | Same | Touched lanes plus `safety-core` |
| Batch integration | Touched lanes plus `static` on the composed tree; add `install-smoke` when any installer or embedded byte changed; add `safety-core` when the engine or admission paths changed | Touched lanes plus `static`, `install-smoke` and `safety-core` | Full gate on each runtime-changing batch |
| Release | One exact-candidate full gate, unchanged policy | Same | Same |
| Docs-only change | `check-docs.sh` on the changed files | Same | Same plus one reviewer read |

Risk overrides, in every mode: an engine-section change, an admission, STOP
or refusal path change, or a change to `tools/quality-check.sh` itself means a
full gate before integration to main. Reasoning effort and coordination tier
are separate choices and are not affected by this matrix.

## Limitations and follow-ups

- Serial only. No `--jobs`, no `--changed`, no cache, no retry and no
  automatic skip in this batch; the default run is exactly as before.
- A lane run is PARTIAL coverage by definition. It never substitutes for the
  release gate and never prints the full-gate success string.
- Frozen task Validate lines keep their exact meaning; native `unio verify`
  re-runs them and remains the trust boundary.
- Docs-only evidence reuse must prove the installer, runtime and test bytes
  unchanged. Files under `docs/development/` are not intrinsically
  non-embedded: LEAD-ROUTING, MODEL-EFFORT and MODEL-SCOREBOARD are bundled
  into the installer.
- Known coverage gaps, deliberately deferred rather than silently claimed
  fixed: `tests/unio-route-contract.py` is invoked by no gate line
  (registration auditing is a later coherent batch), and `check-docs.sh`
  skips `docs/ai/` and `docs/development/` by default (recursive docs lint
  is deferred).
- The runner self-test uses the `UNIO_QUALITY_GATE_CATALOGUE` override to
  exercise fixture catalogues. It is test plumbing, not a lane selector: every
  override run is labelled `FIXTURE`/noncanonical, never prints the full-gate
  success string, and the variable is not inherited by child commands.
- No measured speedup or savings claim is made in this batch; per-command
  timings exist so the next optimization discussion is measured, not guessed.
