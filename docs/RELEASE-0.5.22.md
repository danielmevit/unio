# Unio 0.5.22 — clearer runs and route contracts

The seven reliability changes passed independent current-code reviews and the
complete quality gate. Artifact checks, upgrade/rollback, installation before
publication and official download verification are separate delivery evidence.
Consult the GitHub release for publication status.

This reliability round addresses seven problems observed in a heavy Vecto
session: operators could not see why runs stopped, route bounds disagreed,
and report-only or blocked work looked like ordinary implementation work.

## Changes

- Add per-run tokens, turns and USD used/cap/provenance to receipts and bound
  reports. Prefer underlying CLI usage; label estimates and Unknown explicitly.
  A generic exit3 does not identify which cap ended a run.
- Validate recognized canonical adapter routes against their actual parsers and
  bounds before admission or provider metadata calls. Custom/wrapped routes
  remain explicitly unvalidated. Vibe keeps its thinking flag and16M guard;
  the12M route is valid.
- Make tail nonblocking by default: last40 lines, `--lines N`, explicit `-f`.
- Parse supported scope annotations with a warning, retaining literal paths,
  spaces and parentheses and agreement with the task planner.
- Refuse explicit implementation tasks on known proposal-only Copilot/Perplexity
  routes before provider invocation with `blocked_no_repo_access`.
- Support explicit report-only tasks with a real bounded UTF-8 artifact bound
  to the current successful Source, task and unchanged dispatch state. Scope,
  Validate, stale/tamper checks, review and handoff remain enforced.
- Probe run-record write/fsync storage before admission so disk/permission
  failures receive accurate diagnostics rather than busy-budget advice.

Legacy tasks without exact `## Outcome` metadata preserve their behavior.
Receipt/report schema changes are additive. Raw configured commands are not
published in report provenance; command hashes provide the binding.

## Validation and review

Mistral subscription/Vibe2.26.1/Mistral Medium3.5 HIGH supplied a clean independent
full-code baseline review. ChatGPT subscription/CodexCLI0.163.0/GPT-6.1 Sol LOW
then found three genuine gaps; dedicated LOW corrections passed six focused
suites and all six native Validate commands. Google/Antigravity Gemini3.8Flash HIGH and OpenAI/Codex Sol LOW independently approved
the current correction delta81a3f40, with Source0/native0/report verification0.
The lead inspected their reports and actual changes. Effective serving identity,
effort and remaining allowance remain Unknown.

The complete `bash tools/quality-check.sh` passed0 at81a3f40 on2026-10-19
from17:31:25 to18:08:56UTC+02 in2225.171seconds. Final prose retains identical
runtime and test bytes. Delivery checks follow this code acceptance.
The [round report](development/OPERATOR-LEGIBILITY-2026-10-19.md)
records actual attempts, focused checks and review capture failures. Prior failed
runs are retained rather than recast as successful validation.

## Limits

Usage estimates are approximate and are not account-allowance readings. Not all
CLIs expose usage; Unknown is intentional. Custom route contracts cannot be
validated by guessing their command semantics. Report-only mode does not grant
repository access to proposal adapters or waive validation. The runtime remains
Linux/WSL; managed live sessions, phone access, native Windows and macOS are
later milestones. Dashboard, website and brand code are unchanged in this round.
