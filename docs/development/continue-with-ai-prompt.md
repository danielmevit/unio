# Continue Unio 0.5.23 reliability work

Updated 2026-10-23T14:22:35+02:00. Read applicable AGENTS.md, the newest workspace
coord/AGENT-LOG.md and ~/.config/unio/OWNER-WORKFLOW.md before assigning work.

## Authority and current state

- No main push, publication or global candidate installation is authorized.
- Vecto supplies read-only evidence. Never modify that project or restart its workers.
- Official/global Unio remains 0.5.22. Version 0.5.23 is an unreleased candidate.
- Main/origin was last checked at 9fd18f7. Private integration branch:
  agent/vecto-reliability-20261021, staged runtime through b04aedc.
- The latest candidate checked independently is 68c7ff4 on
  agent/codex-delivery-compat-low-20261023. It has NOT passed final acceptance.

## Personal workflow on every project using Unio

Use one independent external current-code reviewer plus the existing lead's final
assessment: two reviewers total. This supersedes older copied instructions for two
external workers. Codex lead uses eligible Claude Code / Opus 5.5 XHIGH; Claude lead
uses eligible Codex. Add an external reviewer only for a concrete unresolved gap or
an owner request. Preserve stricter current project/CI/human approvals.

The lead scopes, delegates code corrections through native Unio, reviews and
integrates. Shared Codex implementation workers start LOW. Escalate one supported
step after demonstrated reasoning/integration gaps, never for infrastructure.
One focused companion beside the registered lead uses the actual shared account,
a task/config-bound grant, temporary coordination tier medium, STOP for unrelated
admissions and restoration to low when idle. Reasoning effort and tier are separate.
No paid API fallback, max/ultra, blind retries, invented identity or acceptance.

## Built and tested so far

A: a4ca22f adds bounded admission configuration (1–300 seconds, default 30), phase
errors and safety regressions. Source/native exits 0, native verification PASS.
Save/result/Git helper latency remains separate; no filesystem root cause claimed.

B: 54beed5 adds current review observation beside historical records. Original
Source/native failure at quota remains preserved; saved code passed separate
verification. Opus later found integration bugs. Dedicated LOW correction b04aedc
fixed unbound history veto, preparation leakage, effective config binding and
consumer handling; Source/native/native-verification all 0.

C: explicit required text delivery preserves Source/adapter/native exits separately
from required artifacts, checks and acceptance. Initial Mistral/Vibe GLM5.3 and
Medium3.5 infrastructure failures and AGY/Gemini terminal503 failure remain failures.
Dedicated Sol LOW corrected the saved draft at 3b56061. Compatibility a710c5b then
passed 11 commands, including 292 counted checks plus branding. Next compatibility
68c7ff4 fixed standalone helper import, legacy task readers, unset TMPDIR and
legitimate no-Source result readability; Source/native/8-command verification 0.

The earlier managed-session CLI slice is retained. Full multi-turn lead ownership,
phone access and native desktop support are separate later milestones.

## Actual latest acceptance evidence

First combined 7cb9b9b: full quality gate PASS (2687.18 seconds). Independent
Claude Code 2.1.303 / Opus5.5 XHIGH returned REQUEST-CHANGES; AGY1.4.6 /
Gemini3.8Flash HIGH approved. Lead probes confirmed seven Opus findings. These votes
were not averaged and the candidate was not accepted. Both original reports remain.

Next candidate 68c7ff4: full gate FAILED, exit 1 after 1182.43 seconds, at
unio-review-findings.py:410. That assertion still expects receipt-less history to
permanently veto current bound review evidence. Suites after it did not run.
Claude Code 2.1.309 / Opus5.5 XHIGH delivered a valid independent review,
REQUEST-CHANGES with eight findings. Three actionable integration defects were
reproduced by six installed mock observations (43.758 seconds, zero provider calls):
linked config prevents delivery hashes, legal native reviewer IDs fail decoding,
and invalid config erases an otherwise known projection revision. No false-ready
path was found by that review; this is not proof of universal correctness.

Actual evidence under workspace tmp/unio-next/vecto-reliability-20261021:
- machine-gate-final-20261023/full-gate.json and full-gate.log
- final-opus-review-20261023/claude/review.md and its receipts
- review2-triage-20261023/evidence.json and probe.py

## Latest correction complete; native finalization/verification still pending

Updated 2026-10-23T14:22:35+02:00. Task VECTO-CONFIG-OBSERVATION-SOL-MEDIUM-0523-20261023,
ChatGPT subscription / Codex CLI0.163.0 / gpt-6.1-sol MEDIUM, effective Unknown,
finished Source0 at14:19:09+02:00 with clean ae2521c. Its seven checks passed on
that exact revision:34 delivery,21 coherence,19 findings,65 bridge,9 receipts
(148 tests), syntax and embedding. Native finalization and separate verification
remain authoritative; inspect pipeline receipts rather than assuming success.
Automatic baseline/periodic/final saves exceeded60seconds; prior saves retained.
The source supervisor was observed waiting on Windows-mount p9 I/O, not active
model inference. No Source restart or failure rewrite.

## Newly measured latency concern; investigate before final acceptance

Lead privately installed68c7ff4 (no global install) and observed the same completed
own task on /mnt/d using both engines. Installed0.5.22 returned0 in18.982/13.758s;
candidate0.5.23 exceeded the45second observer twice. There were concurrent mock
checks. This is local evidence, not an isolated causal or universal benchmark.
The dashboard result deadline is15s. Actual Source outcomes remain separate from
observer timeouts. Evidence: owned-result-latency-20261023/receipt.json.

The waiting conditional final-gate/reviewer controller794587 was stopped BEFORE
launch; no active worker was interrupted. Its record preserves that decision and
a corrected local timestamp-recording error. No fresh review/gate has been run on
ae2521c. First7cb9 gatePASS and68c gateFAIL remain unchanged.

Prepared next bounded task: VECTO-RESULT-OBSERVATION-SOL-LOW-0523-20261023,
worker codex-result-observation-low-20261023. Preparer852746 waits for the previous
actual Source/native/native-verification0 and restored low tier before creating
its frozen task/worktree and admitting one LOW Source through native Unio. It
refreshes capacity and CLI/version first and keeps real group/lead/grant/STOP.
Pipeline result-observation-sol-low-20261023/preparation.json is authoritative.
Preparation is NOT a running provider call. Inspect before duplicating.

Scope: remove redundant result-observation material/snapshot work, first targeting
no-review evidence, without weakening current/stale review hashes, corruption
visibility, closing drift checks, Source/delivery state or acceptance. No broad
cache architecture or deadline inflation. Estimate30–60min plus final fullgate and
ONE Opus5.5 XHIGH review followed by the existing lead's assessment.

## Exact next actions

1. Observe actual MEDIUM native/verification receipts. Resolve any real failure;
   a successful Source and148 passing tests do not waive native verification.
2. Observe the already prepared LOW task, inspect its committed delta and relevant
   regressions; preserve all baselines. Repeat bounded private-engine observations
   against the same own finished /mnt/d task. Never touch Vecto or global install.
3. Freeze the clean verified candidate for a fresh full quality gate and ONE
   independent Opus5.5 XHIGH review. The full material exceeds the native300000-byte
   cap; retain the bounded hashed report-only Source audit, no clipping or claim
   of native Review approval. Do not reuse old approvals on changed code.
4. Perform the lead's assessment, integrate only accepted scoped commits privately,
   and update changelog/dispositions/scoreboard/handoff. No automatic acceptance,
   main push, publication, global candidate installation or blind retry.

## Deferred work and limits

P2: helper-specific measured result/Git/experience deadlines (4–8 hours), remaining
current-review status consumers (2–4 hours), effort capability reasons versus tier
(2–4 hours), explicit binary/ignored analysis artifacts (1–2 days), bounded enclosing
review context (4–8 hours), cross-workspace account visibility/model history (1–2 days).
Parser-heading ambiguity, Bash deadline granularity and raw-versus-observed stored
readiness are recorded limitations, not reasons to expand this correction.

Finish focused0.5.23; then full managed lead ownership0.5.24 (2–4 working days),
phone0.5.25, Windows0.5.26 with trial/localization/Eqho follow-ups, then macOS0.5.27.
No new UI, website, CodeGraph or competitor research in this round.

Answer status questions briefly and continue authorized work. Before a real limit,
preserve jobs, commits, actual exits and exact next step. Never imply coordination
continues after ending the turn. Final report: SUMMARY / ITEMS LANDED (test evidence)
/ ITEMS DEFERRED + WHY / FILES CHANGED / RISKS / NEEDS-REVIEW.
