# Unio 0.5.20 — protect budgets, work and publication

Four practical protections from field use, with clearer guidance for the lead.
The complete quality gate passed. Published and installed on 2026-10-16 from
`20e203cdba5692bfe246a8621eb8e207a22d6c49`; installation preceded publication.
Reproducible artifacts, all 40 isolated selftests, 0.5.19 upgrade/rollback,
configuration preservation and all six official download hashes passed.
Earlier release tags remain unchanged.

## Changes

- **Protect the lead's subscription.** Native workers and reviewers need one-use
  owner consent before spending the registered lead's shared account. Grants
  expire after 15 minutes and bind the exact task and route. They do not create
  allowance or increase concurrency. [Usage and limits](development/LEAD-BUDGET-CONSENT.md).
- **Preserve eligible failed work.** Optional WIP commits run after confirmed
  provider cleanup, using normal Git hooks and literal task scope. The original
  failure remains; a WIP commit is not acceptance. Unsafe files, initially dirty
  worktrees and unsupported Git states refuse. Power loss cannot guarantee a
  final commit. [Work preservation](WORK-WIP.md).
- **Explain supported worker stops.** Canonical adapters supply bounded, typed
  outcome observations. Missing, stale, malformed or generic-wrapper evidence
  stays Unknown. Observations do not change exits, budgets or acceptance.
  [Outcome boundaries](WORKER-OUTCOMES.md).
- **Separate development and release pushes.** Optional remote policy pins
  destinations and checks release refs, source aliases and tag ancestry.
  The release branch defaults to `main` independently of the development base;
  explicit owner rules remain. The guard is embedded in the engine, so standalone
  installations and thin configuration profiles retain enforcement and Git ref
  input. Existing owner hooks and worker guards are preserved.
  [Remote policy](REMOTE-POLICY.md).
- **Keep leads economical and moving.** Answer status questions and continue
  authorized work in the same turn. Workers sharing the lead's model or
  subscription start at the lowest supported effort; increase it gradually from
  demonstrated task gaps. Existing experience profiles and the scoreboard
  distinguish subscription route, model, effort and task type.
  [Lead guidance](development/LEAD-ROUTING.md),
  [effort-specific results](development/MODEL-SCOREBOARD.md).

## Validation and independent review

The final runtime and tests at `658cbf042063d4508d1bb506d3507f16dc2e43d7`
passed `bash tools/quality-check.sh` on 2026-10-16, from 17:00:04 to 17:26:23
UTC+02:00: exit 0 in 1,542.096 seconds. The source, global installation and
operator agent configuration remained unchanged. Tests used project-owned
fixtures in a private mount namespace. Documentation finalization changes no
executable installer bytes outside the canonical scoreboard guide; release
provenance records the exact gate and artifact revisions.

ChatGPT subscription / Codex CLI 0.162.1 / requested GPT-6.1 Sol LOW completed
consent `02bfcac`, WIP `9c4dba0` and outcomes `0977d38`. Each passed six native
checks, an independent Antigravity / agy 1.4.0 / Gemini 3.8 Flash HIGH review
(APPROVE, adapter exit 0), and lead inspection. Mistral / Vibe 2.26.1 / GLM 5.3
HIGH and Mistral Medium 3.5 HIGH reviews failed at infrastructure without a
verdict. Their collection remains incomplete.

The original Gemini remote implementation `3cda4ad` finished Source 0 and six
native checks, but lead inspection reproduced credential, conflicting-role and
typed-policy defects. That original implementation was not accepted. The Sol
HIGH correction stopped at a real usage limit; its partial test edits remain
preserved. Sol LOW `98d6c61` corrected guard behavior. Its native 6/7 result
retains an invalid operator-supplied test path as failure; the actual 35-case
guard suite passed separately. An external-helper dependency then required
further integration work.

Three earlier complete-gate attempts failed, and remain failures: selftest
initialization, thin-profile review-receipts initialization, and managed Codex
fixtures missing the newly required shared-lead consent. Sol LOW `c48c5f0`
repaired selftest, `0f4ee4f` corrected the release default and `6e06dcd`
registered coverage. After those demonstrated integration gaps, Sol MEDIUM
`6740e0d` embedded the canonical guard and passed six native checks, including
the unchanged nine-case review-receipts suite, installed/standalone thin-profile
cases and 48 remote functional cases plus 60 regressions. Sol LOW `658cbf0`
then corrected only two consent test fixtures: Source 0, three native checks,
11m12s. Runtime bytes remained identical to the reviewed `6740e0d`.

A fresh Antigravity / agy 1.4.0 / Gemini 3.8 Flash HIGH review of `6740e0d`
returned APPROVE, adapter 0 and native 0. The private review mirror did not run
Source; its identity checks refer to the original Source and validation evidence.
The lead inspected the runtime and final test-only changes. Perplexity Pro /
pinned web adapter 0.16.1 / Kimi 3 Thinking supplied two supporting critiques;
corroborated findings, unsupported claims and future suggestions were assessed
separately. These proposals are not formal native approval. Copilot Free /
CLI 1.0.95 / Auto Balance supplied documentation and a genuine compatibility
follow-up for 0.5.19; its serving model and AI lab remain Unknown.

## Limits and follow-up work

Windows-mounted selftest timing failures (38/40) remain alongside unchanged
private-tmpfs 40/40 passes. Controlled fixtures do not establish a latency
guarantee on every host. Requested model and effort are not verified serving
identity or per-task allowance; no general token savings or model ranking is
claimed. The existing dashboard, website and brand are unchanged.

Hooks and local state are trusted-host controls, not an OS sandbox or protection
against hostile rewriting by the same user. Removing hooks or markers, or using
`--no-verify`, can bypass local controls. `core.hooksPath` and automatic remote
import remain unsupported. Configurable Vibe caps, continuous delegation and
managed interactive sessions remain follow-up work.

Delivery completed at 19:55:48 UTC+02:00. The installed dashboard and internal
helpers match the released source. The existing local save-store usage check
remains exit 2/Unknown; installation did not repair that store. Delivery receipts
retain this limit separately from the passing release and installation checks.
