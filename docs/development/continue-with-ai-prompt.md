# Continue Unio after the 0.5.23 reliability round

Updated 2026-10-23T19:50:02+02:00. Read applicable AGENTS.md, newest coord/AGENT-LOG.md and
~/.config/unio/OWNER-WORKFLOW.md before acting.

## Active private development — 2026-10-24T13:12:49+02:00

Public/main/installed: official0.5.23 cd0b3a2. No0.5.24 main push, release or
global install authority. Own private integration branch is
agent/reliability-integration-20261024. Read newest coordination log and
~/.config/unio/OWNER-WORKFLOW.md. Source work is in dedicated worker branches,
not yet accepted or integrated here. Do not duplicate healthy active jobs.

### Active bounded corrections

- Claude subscription / Claude Code2.1.309 / claude-opus-5-5 LOW:
  SELFTEST-LIFECYCLE-OPUS-LOW-0524-20261024, worker
  claude-selftest-lifecycle-low-20261024, base88fe824. Source started12:55:03+02
  and is active at this checkpoint. Conditional reviewer takeover addresses the
  OpusXHIGH findings that Sol's selftest patch lost public run -b coverage and
  left cleanup/PID-reuse/timeout/timing-test gaps. LOW first; escalate only after
  a demonstrated reasoning miss, not filesystem/auth/quota failure. Pipeline
  tmp/unio-next/selftest-lifecycle-opus-low-20261024. Selected public-source WIP
  was copied read-only to lead-context-rescue-20261024T131010+0200 there because
  native capture deadlines still fail: this is unverified context, not a native
  save, commit, complete snapshot or restore proof. Never modify the active WT.
- ChatGPT subscription / Codex CLI0.163.0 / gpt-6.1-sol LOW:
  MANAGED-LEAD-CODEX-CORRECTIONS-SOL-LOW-0524-20261024, worker
  codex-managed-lead-transport-low-20261024, basea07ddee. ActualSource0 finished
  13:02:39+02, latest saved24a5c24fd57a8ac635f162b38fbd688c244f1dbe. Native
  finalization/verification pending: inspect controller.json. Lead repeated all
  three original fake probes and confirmed they now pass, zero provider calls,
  clean unchanged worktree. Pipeline managed-lead-codex-correction-low-20261024,
  lead-correction-positive-controls.json. Do not relabel this as accepted code.
  One shared-budget companion, actualcodexgroup/lead, task/config-bound grant,
  temporary native medium tier and STOP; controller restores low when idle.

Both requested models/efforts remain effective Unknown. Other routes are idle;
no new Mercury benchmarking. Source scripts pin CLI versions/configs and retain
all old failures. Before another shared-budget Source, inspect actual jobs and
fresh capacity; last preparation12:42 showed22% primary/56%weekly, not a current
allowance or per-task savings claim. No extra Codex companion while this one runs.

### Prepared independent reviews and one combined gate

Opus-authored selftest correction gets Mistral subscription / Vibe2.26.1 /
mistral-medium-3-5 / thinkingHIGH, under its independent-mistral-review.
Sol-authored bridge correction gets Claude subscription / ClaudeCode2.1.309 /
Opus5.5XHIGH, under its independent-opus-review. Both wait actualSource/native/
verify0, exact clean revision and available real account slots. They provide
full enclosing source snapshots/hashes, stay blind to peer verdicts and never
accept code. One external worker plus existing lead per change; no duplicate
lead reviewer or recursive worker delegation. Requested/effective remain separate.

Bounded batch observer: tmp/unio-next/managed-lead-batch-gate-20261024.
Only after BOTH current reviews approve0 and Source/native/verify0 does it prepare
wt/managed-lead-reviewed-batch-20261024 on its own agent branch, require disjoint
changed paths and exact reviewed-content identity, and run ONE full
bash tools/quality-check.sh on the frozen combined candidate in private tmpfs.
New quality registration covers both backend suites, so it does not repeat a
separate direct core run. Any failure/conflict/Unknown stops that preparation;
no Source retries, auto acceptance, main push, global install or publication.
Read controller.json, frozen-source.json, full-gate.json/log. The final existing
lead must inspect actual findings, checks, byte proofs and remaining limitations.

### Preserved evidence, not current approvals

- Review-history correction755cb060 has its own OpusAPPROVE; generatorb5a1b0e
  passed4nativechecks and outside-guide identity proof. Core/test9758f42 received
  MistralMedium3.5HIGH nativeAPPROVE0; lead six negative controls catch two faults
  old tests missed. Its exact full gate FAILED1 at11:58 after872.995s:
  managed-lead core0, selftest38/40 pidfile/kill checks failed. No fullPASS.
- Sol selftest88fe824 Source0/native0, mountedverify1 at300s; same declared
  checks on private tmpfs native4/4PASS0 in292.649s, no source change. Fresh
  Claude/Opus5.5XHIGH CLI0/adapter0/native1 REQUEST-CHANGES, six findings at
  selftest-background-readiness-low-20261024/independent-opus-review-tmpfs-verified.
  The corresponding full-gate observer correctly did not launch. Moving fixtures
  is not proof of mounted reliability or a replacement for lost coverage.
- Mistral subscription/Vibe2.26.1/GLM5.3HIGH bridgea07ddee Source0/native0.
  Nativeverify3/4: bridge/core suites and diff0, fourth scope/AST command failed
  because LEAD used Python single-quote repr inside shell singlequotes. Original
  task/verdict unchanged; corrected standalone scope/AST0 is separate in
  lead-validation-contract-erratum.json. Independently, lead confirmed three REAL
  code gaps: omitted model, early events discarded before rejection, reused
  provider turn ID rebinding. See lead-contract-reproductions.json. New Sol task
  addresses these; initial inference exit remains0, code was not accepted.
- A prep-only validation quoting/type error in the new Sol task was fixed and
  shell/Python-parsed BEFORE task/config freeze; no extra model invocation.
- Older quota Source1, stale reviews, setup refusals and interrupted gates-15
  remain unchanged. Every Python probe/import must use -B or no-bytecode env:
  earlier lead-generated pyc staled one native review; exact files preserved.

Helper diagnosiscabb1db is retained with separate
[lead corrections](HELPER-LATENCY-LEAD-ASSESSMENT-2026-10-24.md). Repeated store
scans are measured expensive; full-save105–125s is a model, under-load result
contention remains unproven, worktree byte counts differ and publish unlocks
before write_attempt. No timeout increase/performance patch/real-store cleanup.
The save optimization was deferred before any Source for the actual gate failure.
Native saves still time out60s; Git commits and selected context are distinct.

After current corrections/reviews/gate, existing lead assesses and integrates
privately. Then complete the owned native lead claim and persistent process;
this bridge/core alone does not provide a usable installed lead command.
[Integration decisions](MANAGED-LEAD-INTEGRATION-DECISIONS.md) reject fake account
aliases, publication dependencies and unproven provider/human identity. First
supported route estimate remains2–4working days total; phone afterward, Windows
before macOS. Keep Vecto read-only, UI/site separate, private research in the
private hub and Mercury trials closed. Do not publish an unfinished24.

## Release delivery complete

Owner-authorized v0.5.23 is published, installed and verified against all six
freshly downloaded official assets. Exact release source:
cd0b3a213f0bf52e4349af89e7b4ed94a3b95e0f. Main and the immutable v0.5.23 tag
contain it. The installed dashboard is http://127.0.0.1:33417/ on this machine.

[Official release](https://github.com/danielmevit/unio/releases/tag/v0.5.23).
Local delivery receipt:
workspace tmp/unio-next/reliability-release-0523-20261023/delivery.json,
state published_installed_official_download_verified, all delivery exits0.
Installation/offline smoke preceded publication; official downloaded hashes were
verified afterward. Existing operator configuration/templates and older release
tags were preserved. Never rerun completed shipping controllers or retag v0.5.23.

Runtime integration checkpoint8362d1f plus documentation1b0700d and cd0b3a2.
Read [the release report](../RELEASE-0.5.23.md),
[the candidate evidence](RELIABILITY-0.5.23-CANDIDATE.md) and
[field dispositions](VECTO-RELIABILITY-2026-10-21.md). Historical candidate reports
keep their original acceptance/publication status; this section records delivery.

Vecto remains read-only evidence; do not modify it or restart its workers.
Its reporting window spans multiple versions. The owner authorized continuing
milestone work; that does not authorize unrelated future releases automatically.

## Accepted evidence and exact revisions

- Final gate: a936848a9f0f01585e0c32b006bacd446d2fe2e8, tree3f27103c61f0170812010df867df7f3bbccbf49b.
  bash tools/quality-check.sh PASS0,2975.855s, finished16:18:03+02 Oct23;
  clean isolated clone, tracked unchanged/untracked[], zero real provider calls.
  Receipt machine-gate-guides-corrected-20261023/full-gate.json and full-gate.log.
- Independent Claude subscription / Claude Code2.1.309 / requested Opus5.5 XHIGH
  APPROVE12nonblocking observations on exact runtime2fa351b. Native CLI/Source/
  runner/artifactverify all0. Effective model/effort/capacity Unknown. Complete
 576920byte material SHA7ca0543db7afe849627d8ce648ed367bb530a6e60d105eeb8a4a8283d3504c87.
  Pipeline final-opus-result-corrected-20261023; raw review remains exact2fa.
  This is a report-only Source audit, NOT a native review receipt; native300K
  material cap was not raised or clipped.
- a936848 updates only34bundled guide lines plus fragment. Each guide body was
  already canonical at2fa; guide-regeneration-final-checks-20261023/receipt.json
  proves every other installer byte identical. Never rewrite old approval hashes.
- Existing lead inspected diffs, regressions, proof and observations; accepts the
  private prepared candidate with explicit limits. lead-final-assessment-20261023.json
  records integration8362d1f versus gated source; only release/handoff docs differ.
- Own/mnt/d timing: corrected engine8.322/7.811s, same-pass installed22baseline
 11.875/7.934s; previous candidate45s observer deadlines twice. Concurrent load
  differed, no speed ratio or universal performance claim. See
  owned-result-latency-corrected-20261023/receipt.json.

All receipt paths above are below workspace tmp/unio-next/vecto-reliability-20261021.

## Work and original failures

A a4ca22f bounded admission1..300/default30 + phase diagnostics; native checks0.
B review coherence54beed5 original Source1quota preserved; separate saved-code
verification0, later b04aedc/ae2521c correct actual integration bugs.
C delivery initial Mistral/Vibe2.26.1 GLM5.3HIGH andMedium3.5HIGH infrastructure2,
AGY1.4.4/Gemini3.8FlashHIGH CLI0/adapter2/native1 terminal503, all retained.
Dedicated SolLOW3b56061, compatibilitya710c5b/68c7ff4 andMEDIUMae2521c Source0.
MEDIUMae seven selectedcommands0/148tests; separate nativeverify0.
LOW result correction2fa351b Source0/native0/native3checks0; final80tests0.
Its introduced explicit-diagnostic hash regression was corrected and preserved;
two test-development mistakes and failed baselines remain distinct.
LOW guide regenerationa936848 Source0/native0/native4checks0/6contracttests0.
No failed call, stale review or saved partial is relabeled as a successful Source.

Earlier7cb gate0 but OpusREQUESTCHANGES/GemAPPROVE were not averaged; genuine
Opus bugs were reproduced/fixed. Later68c gate1 at obsolete history assertion,
and2fa gate1 at stale bundled guides, remain unchanged. They do not replace the
final a936 gate. Native experience records retain requested route/model/effort,
acceptance and correction counts; effective settings remain Unknown. Token usage
profiles are different tasks, not an effort benchmark or shared-limit attribution.

## Personal workflow on every project using Unio

One independent current-code external reviewer + existing lead assessment, two
reviewers total. Codex lead -> eligible Claude/Opus5.5 XHIGH; Claude lead -> eligible
Codex. Extra external reviewer only an unresolved gap/owner request; preserve
stricter current CI/project/human approvals. This supersedes older copied two-worker
review defaults. Root-local OWNER-WORKFLOW and Codex/Claude startup pointers were
updated; other projects' source and running sessions were not modified.

Delegate code corrections through native Unio. Shared Codex implementation workers
start LOW; advance one supported step only for demonstrated reasoning/integration
gaps, never infrastructure. One focused companion beside the registered lead,
real account mappings and task/config-bound grant, narrow temporary coordination
medium, STOP closing unrelated admissions, restore low when idle. No paid fallback,
max/ultra, blind retries, fake groups, automatic acceptance or recursive reviewers.
Record route/subscription, CLI/version, requested/effective settings, actual exits,
checks, correction count and elapsed. Status questions do not cancel work.

## Current authorized work checkpoint

The reliability follow-up is active in a dedicated worker worktree; consult the
newest local coord/AGENT-LOG.md for its exact branch, receipts and current checks.
The Codex shared-budget companion is a LOW implementation worker. Do not start a
second Codex companion or interrupt a healthy assignment. Existing lead remains
responsible for scope, independent current-code review and final assessment.

Owner-authorized independent private research is delivered and reconciled in its
separate private hub, alongside the verified0.5.23 backup. No classified findings,
raw sessions or credentials belong in public source. Mercury3 is registered only
as an experimental worker with measured trials; the owner explicitly deprioritized
further testing. Prioritize the core reliability fix and managed lead-session
continuity. Do not turn a testing-model exercise into the main milestone.

## Remaining priorities

1. Fix the exact9758f42 selftest failure, then rerun the corrected candidate gate
   and existing-lead acceptance. The narrow
   pre-provider-refusal eligibility correction is implemented/reviewed and included
   in this candidate; do not reimplement it. Legacy contextless history still blocks
   conservatively; no deletion, fake commits or automatic retry. Then complete the
   owned transport/native lead claim, and a separately scoped save-cost correction
   if the measured diagnosis survives the locking/correctness assessment.
2. Remaining current-review consumers and useful stale/unsafe/background reasons.
3. Effort startup/live/pending/effective capability reasons separate from tier;
   unified reviewer grammar, explicit binary/ignored analysis contracts, bounded
   enclosing review context, cross-workspace visibility/model-history normalization.
4. Full managed lead-session ownership; then phone, Windows/trials/localization/
   Eqho logic and macOS. Keep UI/site/CodeGraph work separately scoped.

Private research runs, studies and backups belong only in the owner-authorized
private workspace, never this public source tree or public release artifacts.
Consult the newest local coordination log for active processes and account slots.
Do not dispatch another shared-budget worker until the current companion is idle.

The reliability release is delivered. Next public implementation work needs a
new focused task/worktree and fresh capacity/CLI evidence. Keep original failures,
reviews and receipts; do not rerun completed Sources or gates. No new runtime
change is made by this handoff update. The full gate above remains the exact
release gate, not evidence for future implementation. Answer status questions
and continue authorized work; never imply lead work continues after its turn ends.
