# Continue Unio after the 0.5.23 reliability round

Updated 2026-10-23T19:50:02+02:00. Read applicable AGENTS.md, newest coord/AGENT-LOG.md and
~/.config/unio/OWNER-WORKFLOW.md before acting.

## Active private development — 2026-10-24T11:54:21+02:00

Published/main/installed stable0.5.23 cd0b3a2. No0.5.24 main push, release or
global installation is authorized. Lead integration branch retains staged8190057
plus guidance commits. Latest separately reviewed candidate is
9758f4224a73d8ee49dd3a85cfbefd8830e8f2a4 in
wt/claude-managed-lead-tests-low-20261024. Do not duplicate its completed Source.

The managed-lead prototype now retains uncertainty when matching output arrives
before a rejected acknowledgement, including closed-archive and oversized-output
paths. SolLOW b89aa67 fixed the runtime ordering; OpusXHIGH confirmed that fix
and found a test assertion swallowed by the fake transport's exception handler.
Conditional owner takeover used Claude subscription/ClaudeCode2.1.309/
claude-opus-5-5 LOW. Source0/native0/native4checksPASS0, commit9758f42 changes
only tests/unio-managed-lead.py. Runtime is byte-identical to b89aa67. LOW was
sufficient, no escalation. Preserve original Sol quota failures and prior reviews.

Independent final other-lab review: Mistral subscription/Vibe2.26.1/
mistral-medium-3-5/HIGH via --thinking high, CLI0/adapter0/native review0,
APPROVE with valid empty findings. Full frozen source116244bytes accompanied
native diff material, separately hashed. Requested settings remain effective
Unknown. One external reviewer plus existing lead; Opus authored the last fix,
so this final external reviewer appropriately uses another AI lab.

Pipeline tmp/unio-next/managed-lead-test-takeover-opus-low-20261024 contains
source/controller/verification proof, independent-mistral-review and machine-gate.
Lead-negative-controls.json confirms six deterministic old/corrected tests:
unchanged runtime passes both; injected wrong-turn activity and callback assertion
are missed by old tests and caught by corrected tests. No provider calls or source
changes. An initial operator fault-injection placement error is preserved separately.

Full quality gate is RUNNING from11:42:35+02 on exact9758f42/tree76fb311c.
It uses an isolated exact Git clone/private project tmpfs, zero AI calls, direct
backend suite then bash tools/quality-check.sh; estimate45–60minutes. Read actual
machine-gate/full-gate.json and log. Never infer PASS from an active process.
Final existing-lead acceptance/private integration waits actual gate completion.
No worker is still invoking a provider at this checkpoint; reallead/account/lowtier
and STOP retained. Failed/stale reviews and original failures remain unchanged.

Current personal workflow also contains conditional Opus takeover after repeated
unresolved Sol corrections; read [the rule](../ai/REVIEWER-LED-CORRECTIONS.md).
Sol remains ordinary correction defaultLOW. This is guidance, not native routing.

Helper diagnosis: Mistral subscription/Vibe2.26.1/GLM5.3/HIGH Source/native/verify0,
commitcabb1db in wt/vibeglm-helper-latency-20261024. Read
HELPER-LATENCY-2026-10-24.md there plus raw receipts under
helper-latency-profile-vibe-20261024. Repeated save-store traversal on v9fs is
measured expensive; full-save105–125seconds is a MODEL, not completed timing.
Under-load result/experience contention is a hypothesis from one idle19.42s
sample. Some original Sources failed quota/setup: do not call them all successful.
Lead must inspect exact lock lifetime before accepting cached-identity proposal:
publish releases its store lock before current write_attempt runs. Do not blindly
raise limits or change save protections. No performance code correction dispatched.

Separate review-history755cb060 has its own OpusAPPROVE; bundled-guideb5a1b0e
passed4nativechecks and outside-guide identity proof; current full gate includes
both. Old packaging failure1 and deliberate gate stops-15 remain unchanged.
Native-plan7280cad Source/native0 but verify1 was a lead report-only/commit contract
contradiction; separate local fixed artifact validation0 made no AI call.
[Integration decisions](MANAGED-LEAD-INTEGRATION-DECISIONS.md) correct account-alias,
private dependency, provider-ID and strict-schema assumptions. Native owned
transport/lead claim remain to implement; this backend alone is not usable full
lead continuity. Research/privatehub e5be535 and stable23 backup complete; Mercury
trials closed. Vecto read-only. Do not publish or install an unfinished24.

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

1. Finish the running exact9758f42 gate and existing-lead acceptance. The narrow
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
