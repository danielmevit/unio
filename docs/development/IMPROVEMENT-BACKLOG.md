# Unio Improvement Backlog

This backlog consolidates pending, accepted, and shipped functional improvements for Unio, organized by priority. It acts as a detailed inventory supporting the [ROADMAP.md](ROADMAP.md) without assigning fixed deadlines or version numbers for unreleased work.

## Current delivery and owner priority — 2026-10-24T22:52:32+02:00

- **Shipped and installed:**0.5.23, following the seven operator fixes in0.5.22.
  See [the release evidence](../RELEASE-0.5.23.md). Older entries below retain
  their dated context; shipped20/21/22 work is not an unfinished next batch.
- **Privately accepted:** review-history/dispatch corrections and tested internal
  lead core/RPC foundations. The complete foundation gate passed; these do not
  provide installed native lead ownership.
- **Privately accepted checkpoint fix:** metadata reuse preserves validation,
  retention and restoration. Focused checks, independent reviews and exact94d29082
  combined gate passed. This does not claim all capture deadlines are repaired.
- **Current task:** finish preserved experience-record timeout implementation and
  obtain actual native validation plus independent Opus review. See the
  [current batch](OPERATIONAL-QUALITY-2026-10-25.md).
- **Next:** operational improvements before ownership or interface work. Preserve
  the failed ownership invocation (infrastructure exit2, no edits), without retry.

### Operational queue

1. Finish the assessment-observation timeout continuation and existing-lead assessment; checkpoint gate/assessment are complete.
2. Validate remaining helper delays: mounted-workspace automatic captures still
   hit60s; result/experience observations may exceed caller deadlines. Diagnose
   the exact call/phase, reduce redundant work or add bounded configurable
   observation deadlines where justified. Preserve freshness and failed exits;
   no arbitrary timeout increase, data deletion or unproven speedup claim.
3. Improve operating clarity where evidence is missing: supported stop reasons,
   receipt provenance, requested startup effort/live-control capability/pending
   configuration/effective Unknown, separate from coordination tier. A custom
   wrapper's Unknown is not proof the provider exported nothing; distinguish
   route setup limitations from product defects before fixing them.
4. Provide bounded enclosing review context with exact material hashes; keep
   individual opinions, current change requests, stale evidence and lead
   acceptance separate. Preserve material caps; never silently clip.
5. Follow with explicit analysis/asset delivery and honest cross-workspace
   shared-account visibility when scoped. Do not weaken implementation no-op
   gates or claim global account enforcement that does not exist.

Ownership/lifecycle and UX work resume after the operational batch: existing
dashboard integration, session phone pairing and native Windows before macOS.
No extra feature is added to an already running gate. Bundle coherent completed
operational changes; run the required final combined gate on the frozen scope.

## Functional Priorities

### 1. Allowance, Reset, and Worker Readiness

- **Shipped**: Native shared-budget workflow admission, including the lead in low tier.
- **Added in 0.5.6**: Manual readings with `unio capacity record`/`show`, grouped by shared budget, with observation age, optional reset time, and fresh/stale/expired/Unknown handling. This packages the reviewed store independently of the browser. See [capacity readings](CAPACITY-READINGS.md).
- **Implementation evidence**: Gemini's first candidate passed 3 native checks but had four reproduced defects. Opus corrected those and packaged the command; the lead then corrected two inherited extreme-input crashes before the release gate. The scoreboard preserves each result rather than treating process success as acceptance.
- **Shipped in 0.5.7**: Explicit `unio capacity refresh codex` reads Codex account/rate-limit metadata once (no model turn) and caches 5h/weekly windows; `show --provider codex` is local only. The browser's Designated AI agents & limits section shows routes, shared groups, the registered lead and every window with remaining, reset countdown, age and source through a cached read-only `/api/limits`. Stored-state validation was hardened after the lead reproduced an accepted 100.000001% value and a year-9999 overflow.
- **Planned**: Supported readings for other providers and integration of allowance with worker readiness and scheduling. No extra per-token spending or promotion of free workers to lead. A cached reading is not a live meter.
- **Evidence**: [PROVIDER-QUOTA-MONITORING.md](../PROVIDER-QUOTA-MONITORING.md), [TASK-TIME-BUDGETS.md](TASK-TIME-BUDGETS.md)

### 2. Ready-Task Scheduling and Parallel Execution

- **Next Slice**: Automated dependency handling, conflict ownership, and ready-task dispatch.
- **Available now**: The lead can run independent tasks concurrently through native workflows on separate budgets.
- **Planned**: Automatic ready-queue scheduling and explainable idle/dependency decisions.
- **Evidence**: [PARALLEL-WORK.md](PARALLEL-WORK.md)

### 3. Connection, Auth, and Transport Reliability

- **Documented now**: A [help-only readiness inventory](AUTH-READINESS-INVENTORY.md), with local sign-in, remote authentication, allowance and workflow readiness kept distinct. Claude JSON status is the smallest documented first adapter; actual exit and safe-field behavior still need checking.
- **Shipped in 0.5.8**: Optional Vibe workers, Perplexity proposals and standalone adapter packaging/discovery. Corrected Vibe made a real GLM run, saved work and reported a connection failure; Opus completed packaging with four native checks. The first genuine Perplexity GLM request returned a plan but missing code attachments. Kimi returned two complete inline files after the prompt correction; six proposed test methods exposed one incorrect fixture. These outcomes do not establish model rankings or remaining allowance.
- **Planned**: Implement supported read-only readiness adapters and improve prompt/connection reliability without blind retries.

### 4. Review Aggregation and Security

- **Shipped**: Native independent review collection and structured findings preserve each attempt and disagreement. The owner selects review depth through the active protocol; the lead assesses current evidence. Reviews never grant human acceptance or merge code. Further security improvements remain planned.

### 5. Context Efficiency and Measurement

- **Planned**: Measured scan performance optimizations, including automatic-save scan overhead on mounted file systems, and context/token efficiency improvements. Do not invent missing benchmark scores or claim a requested tool was actually used without evidence.

### 6. Work Saving and Recoverable Handoffs

- **Shipped**: Manual and automatic native-run saves and separately authorized restored-worker continuation shipped in 0.5.4.
- **Available now**: Early commits are worker policy and context handoffs already exist. Snapshots are not commits or off-device backups.
- **Planned**: Better enforcement of early checkpoints and clearer recovery/handoff status.
- **Observed follow-up, 2026-10-09/10**: This workspace reached the 32-save project retention cap across historical workers; new workers' saves were refused, and some mounted-filesystem scans exceeded their deadlines. The refusal text mentions pinned/corrupt evidence even though no continuation claim files were present. Preserve existing saves; implement explainable bounded retention/archiving and measure scan cost. Early commits preserved the current implementation, but automatic saving must not be described as working for these runs.
- **Evidence**: [WORK-SAVING-CONTRACT.md](WORK-SAVING-CONTRACT.md)

### 7. Lead Cooldown and Identity Controls

- **Shipped**: Lead cooldown shipped experimentally, opt-in in 0.5.4; genuine limit restart is still unobserved.
- **Current lead instruction**: Delegate more implementation as trustworthy allowance falls (suggested 20% delegate-first, 10% prepare handover; not native thresholds).
- **Planned**: Extended supported adapters/identity and the automatic [temporary acting-lead handover](LEAD-CAPACITY-HANDOVER.md), documented but not implemented; deterministic fake capacity/handoff tests come first.
- **Evidence**: [LEAD-COOLDOWN-CONTRACT.md](LEAD-COOLDOWN-CONTRACT.md), [LEAD-COOLDOWN-RESTART.md](LEAD-COOLDOWN-RESTART.md), [LEAD-CAPACITY-HANDOVER.md](LEAD-CAPACITY-HANDOVER.md)

### 8. Work Modes and Model Roles

- **Shipped**: CLI mode/tier switches and shared-budget workflow admission shipped in 0.5.3.
- **Documented now**: Supported model effort controls, main implementation roles, free routine-only workers and a curated task-fit scoreboard.
- **Planned**: Browser policy selectors, automatic task-fit recommendations and richer model/outcome measurements. See [model experience](MODEL-EXPERIENCE.md).
- **Evidence**: [MODEL-EFFORT.md](MODEL-EFFORT.md), [MODEL-EXPERIENCE.md](MODEL-EXPERIENCE.md)

### 9. Browser Appearance and Live Overview

- **Shipped**: Worker updates/output/tracked worktree files shipped in 0.5.3. Themes/basic map shipped in 0.5.4.
- **Shipped in 0.5.5**: Installed launcher, left-to-right layout and task-logo cards with muted outcome strips. Early commits are policy; snapshots do not guarantee a commit or off-device backup.
- **Shipped in 0.5.7**: Background `unio dashboard ensure|status|stop`, shared map/list filters (Current work default, All states, direct Finished, worker, token-based category, search) and the Designated AI agents & limits section. The imported filter candidate failed 2 of 4 native browser checks; the completion restored the map/details nesting and the original lifecycle assertions.
- **Planned**: Live lead messages and phone pairing are different, planned capabilities. UI polish comes after functional work.
- **Evidence**: [LIVE-WORKSPACE-VIEW.md](LIVE-WORKSPACE-VIEW.md)

### 10. Mobile Session Companion

- **Planned**: Scoped mobile session pairing, revocable QR invitations, and live lead messaging within an active session. Not a general remote desktop.
- **Evidence**: [MOBILE-SESSION-COMPANION.md](MOBILE-SESSION-COMPANION.md)

### 11. Essential Settings and Front-Facing Org

- **Shipped**: AGPL-3.0-only license, lawful attribution, and contribution records. Current README/tagline, repo organization, release/install/provenance and effort/role guides already exist.
- **Planned**: Essential settings/access controls UI.

## Parallel Work

Checkpoint, 2026-10-10: v0.5.8 is published and installed, and its managed read-only dashboard passed real HTTP checks. Both initial Perplexity trials and the owner-requested [matched four-scenario comparison](PERPLEXITY-FIELD-TRIALS-2026-10-10.md) completed. Both planners passed independent checks; their generated tests required corrections. No trial worker remains active and no planner was merged. Check the local coordination log for later work; the entries below record earlier work, not active jobs.

- **Opus**: The initial release-preparation attempt failed OAuth without edits on 2026-10-09. After sign-in, the owner-authorized capacity correction was approved by the lead at `528e214`. Because Grok is unavailable, the owner then authorized further Opus feature work: Opus packaged the native capacity command for 0.5.6; the lead made bounded extreme-input corrections before release validation.
- **Grok**: Capacity Source ended 402 without edits on 2026-10-09; no active Grok run is claimed.
- **Gemini**: Completed the bounded help-only readiness inventory; lead editorial correction tightened three evidence claims. No credentials or model probes were run by the inventory.
- **Verified-free LongCat**: Ran the predefined local link audit: 405 targets checked, 125 skipped, 0 missing. The lead corrected document classification wording. This was routine support, not implementation or security acceptance.
