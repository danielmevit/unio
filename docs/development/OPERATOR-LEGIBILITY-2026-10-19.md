# Operator legibility improvement round — 2026-10-19

## Scope and acceptance

An external heavy-session report found the core worktree / verify / independent-review loop sound, with recoverable interruptions, but run limits and route capabilities difficult to diagnose. This round prioritizes additive per-run budget telemetry, then dispatch-time adapter/route consistency checks. Existing receipts and routes remain compatible; observations do not grant acceptance, change account availability or imply remaining subscription allowance.

## Work in progress

- Items 1–2: Mistral subscription, Vibe CLI 2.26.1, requested GLM 5.3 HIGH ended Source/native 3 after 379.579 seconds. The installed helper synthesized `turn_limit` from generic exit 3, so the specific cap remains Unknown. Partial work is preserved in unaccepted checkpoint 26ffd7d. A dedicated GPT-6.1 Sol LOW completion is prepared and waits for the disk worker to finish; no overlapping Codex worker is admitted.
- Items 3–4: Antigravity, agy CLI 1.4.2, requested Gemini 3.8 Flash MEDIUM. Separate nonblocking-tail and scope-annotation commits requested.
- Item 7: ChatGPT subscription, Codex CLI 0.163.0, requested GPT-6.1 Sol LOW. Early disk/write preflight and accurate storage refusals, one focused worker beside the registered lead.
- Items 5–6: not yet assigned. A proposal-only route is intentionally useful for research; it must not be mistaken for an implementation route. Report-only verification needs an explicit artifact/evidence contract, not a blanket empty-work waiver. Reassess after priorities 1–2 pass.

Requested settings are recorded, not proof of effective model identity or allowance. Implementations are unaccepted until focused checks, two blind current-code worker reviews from different AI labs, and the lead assessment are recorded. No push before review. No release or global install is part of this round.

## Preserved work

The earlier managed-session CLI candidate stays on its isolated branch. Its Sol LOW correction ended Source 0 and passed six native checks at 04c51ee6902d6a56dd709e58baaaeeddb1834a0b. That evidence does not make it merged or reviewed. It is excluded from this round.

## Results

Pending. Replace this section with actual item commits, test exits, review revisions, deferred reasons and remaining risks before delivery.

## Outcome-mode design boundary

Items 5 and 6 are coupled. Proposal-only routes intentionally produce useful research without repository tools. A successful proposal is not a successful implementation, but arbitrary answer text cannot reliably decide which artifact the owner authorized. Existing task files also have no explicit declaration separating these outcomes.

A future explicit task contract should distinguish implementation from report-only work and declare required capabilities. Dispatch can then refuse a known missing repository capability with a typed nonzero blocked outcome, while a declared diagnostic task can pass checks against its own current, run-bound report artifact. It must retain Source failure, scope checks, task identity, stale-evidence checks and independent review. Merely ignoring `empty_work`, or searching the model's prose for “blocked,” would weaken those guarantees. Preserve legacy task interpretation and proposal routes while adding this declaration. This is a deferred design dependency, not a claim that the requested functionality conflicts with Unio's purpose.

## Standalone preflight continuation receipt — 2026-10-19

Dedicated implementation worker: ChatGPT subscription / Codex CLI (locally verified
`codex-cli 0.163.0`) / requested `gpt-6.1-sol` LOW. Effective model identity,
effort and remaining allowance are Unknown. This worker used no other AI calls,
subagents or paid fallback. This is implementation and local validation evidence;
it is not an independent review or lead acceptance. The outer Source exit is
Unknown from inside this invocation.

Base revision: `472aadb253cb89c0cd1f3c170269cd8db1912c0e`, including the preserved
standalone WIP and previous corrections. Prior invocation termination 143 and
its stale/reconciled receipts remain preserved; no causal claim about its
termination or the removed namespace layer is made here. The referenced
`coord/tasks/OPERATOR-FINAL-COMPLETION-20261019.md` is absent in this worktree;
the explicit continuation assignment supplied the requirements and allowed scope.

Item 2 completion: `23a6737b8c866f731864b3eafbabd7ff38e41248`. The generated inline
checker retains the frozen canonical parser sources. Relocated recognition now
uses nonblocking/no-follow open, descriptor type/size checks and bounded exact
byte comparison. Unsafe or changed sources stay unvalidated; only packaged
sources are executed for parser discovery. Recognizable malformed quoting is
refused without inferring contracts from wrapper text or model names. The six
route-contract tests passed, including run/review/review-set refusals, thin
configs, copied standalone `unio`, no provider/version markers on refusal,
custom compatibility and bounded FIFO/symlink/directory/changed-source checks.

Separate item 7 test correction:
`0b1827263ab4a1bd3fd89a778d2f04b62d55473d`. The initial disk suite returned 1
after its behavioral checks passed because TemporaryDirectory teardown raced
background EXIT cleanup (`Directory not empty: coord`). The test now waits,
within its existing deadline, for native worker-lock release. Its focused rerun
returned 0 with 193 checks; no production disk behavior changed.

Preserved failed test attempts: the first route suite returned 1 because its
copied binary was named `copied-engine`, which the existing ownership guard
refuses; the fixture now copies to `standalone/unio` and still requires custom
exit 7. Added review assertions initially returned 1 at the prerequisite current
validation gate; the fixture now performs a real in-scope edit and successful
verify before testing invalid reviewer dispatch. The final route suite returned
0 (six tests, 24.982 seconds). No assertions were weakened.

Focused validation batch started at `2026-10-19T03:29:02Z`; final results follow.

| Focused command | Actual exit / evidence |
| --- | --- |
| `bash -n unio-install.sh` | 0 |
| `python3 -B tools/embed-adapters.py --check` | 0, regenerated canonical bytes match |
| `python3 -B tools/embed-task-plan.py --check` | 0 |
| `python3 -B tests/unio-vibe.py` | 0, 22 tests |
| `python3 -B tests/unio-antigravity.py` | 0, 41 checks |
| `python3 -B tests/unio-copilot.py` | 0, 14 tests |
| `python3 -B tests/unio-perplexity.py` | 0, 11 tests |
| `python3 -B tests/unio-adapter-budget.py` | 0, 7 tests |
| `python3 -B tests/unio-adapter-outcome.py` | 0, 9 tests |
| `python3 -B tests/unio-route-contract.py` | final 0, 6 tests; earlier failures described above |
| `python3 -B tests/unio-adapters-install.py` | 0, 3 tests |
| `python3 -B tests/unio-tail.py` | 0 |
| `python3 -B tests/unio-scope-annotations.py` | 0 |
| `python3 -B tests/unio-disk-preflight.py` | initial 1, corrected rerun 0, 193 checks |
| `python3 -B tests/unio-thin-config.py` | 0, 1 test |
| `python3 -B tests/unio-task-plan.py` | 0, 13 tests |

| `bash tests/unio-quality.sh` | 0, including contract cases and 26 coverage regressions |
| `git diff --check` | 0, also repeated after the handoff edit |

Validation end receipt: `2026-10-19T03:47:07.761104+00:00`.
The focused batch elapsed approximately 18 minutes; route/disk correction reruns
ran separately alongside the batch. Full quality gate and independent AI
reviews were not run by this worker, as instructed. Logs are retained locally
under `/tmp/unio-focused-20261019/`; the initial disk failure is `12.log`, the
corrected disk exit-0 run is `disk-correction.log`, and the final route exit-0
run is `route-contract.log`. The table above is the durable results receipt.

Remaining limits: custom/wrapped/unsafe/unrecognized sources remain callable
with validation Unknown; canonical validation proves syntax/bounds only, not
provider capacity or successful execution. A standalone native engine retains
the existing required `unio` basename. Items 5–6 remain deferred. No push,
global installation, release, policy/task/auth-store edits or Vecto changes
were performed. Next step belongs to the lead: focused native verify, the full
quality gate, two independent current-code lab reviews and lead acceptance;
record the outer Source exit separately when it becomes observable.


## Bounded telemetry/diagnostic continuation — 2026-10-19

Assignment/start receipt: `2026-10-19T10:56:41+02:00`, base
`f6567278639be5c6fe83823ad2e3c2b1a3d692af` (preserved WIP).
Dedicated correction worker: ChatGPT subscription / Codex CLI, locally verified
`codex-cli 0.163.0` / requested `gpt-6.1-sol` LOW; effective model and effort
Unknown. No other provider calls, subagents or paid fallback. Outer Source and
native invocation exits remain Unknown until observed by the controller.
The original missing-PID/no-receipt attempt and the prior interrupted LOW
Source 1/native 1 allowance-limit attempt remain historical failures; this
continuation does not replace their evidence. Reported reset allowance was
shared-group metadata, not an allocation to this worker.

Item 1 continues the existing overflow-safe `finite_number` check and single
bounded usage-file read. Notes exceeding the telemetry schema limit are omitted,
including finite enormous JSON integers; native/adapter exit and final receipt
must survive. Added fake-CLI cases cover `10**200`, `10**400`, negative enormous
integers, booleans, nonfinite values, malformed JSON and wrong shapes, and assert
unknown token/USD meters, bounded notes and absence of raw usage/secrets.
