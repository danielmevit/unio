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

Item 1 continuation commit: `e31b965` (preserved WIP remains its ancestor).
Item 2 continues the existing actual-parser `safe_integer_bounds` metadata;
the safe dispatcher renders both numeric endpoints and the agents.conf remedy,
without reading rejected user strings. Existing standalone parsing and accepted
syntax/ranges are unchanged. Tests obtain native-dispatch bounds from that same
parser metadata, avoiding duplicate range values, and cover below/above bounds,
`nan`, `inf`, nonintegers and secret-like input. Native refusal is asserted before
background start, provider marker, retry, policy and outcome artifacts. Adapter
embeds were regenerated, including the standalone bundled contract.

Preserved failed check: the first route-contract run returned 1 (7 tests,
5.534 seconds): the WIP's new Perplexity fixture had not initialized a Perplexity
worktree, so native dispatch correctly stopped with “no worktree” before parser
validation. The fixture now configures and initializes that route; no production
worktree or dispatch guard was changed. Corrected rerun: exit 0, 7 tests,
24.144 seconds.

Focused final checks (this continuation only):

| Command | Result |
| --- | --- |
| `bash -n "unio-install.sh"` | passed |
| `python3 -B "tools/embed-adapters.py" --check` | passed, byte-identical |
| `python3 -B "tests/unio-copilot.py"` | exit 0, 16 tests, 146.650 seconds |
| `python3 -B "tests/unio-perplexity.py"` | exit 0, 11 tests, 36.099 seconds |
| `python3 -B "tests/unio-route-contract.py"` | corrected exit 0, 7 tests, 24.144 seconds |
| `python3 -B "tests/unio-adapter-budget.py"` | exit 0, 7 tests |
| `python3 -B "tests/unio-adapter-outcome.py"` | exit 0, 9 tests, 31.143 seconds |
| `git diff --check` | passed |

No full gate, live model canary, push, release, global install or other provider
invocation. Local fake-CLI receipts assert native 0/adapter 0 for successful
proposals with invalid usage; these are fixture observations, not the outer
worker's Source/native exit. The latter remain Unknown inside this invocation.
Both corrections are implementation plus focused validation, not lead acceptance.
Three independent current-code reviews follow outside this task, per assignment.

End receipt: `2026-10-19T10:59:56+02:00`; requested route remains ChatGPT subscription / Codex CLI 0.163.0 / `gpt-6.1-sol` LOW, effective settings Unknown.

## Items 5–6 implementation worker receipt — 2026-10-19

Start receipt: integrated base `2216704408395109c9427301e6b7c43e9200d562`,
clean worktree at entry. Exact initial wall-clock time was not captured (Unknown).
ChatGPT subscription / Codex CLI `0.163.0` (observed with `codex --version`) /
requested `gpt-6.1-sol` / LOW. Effective model, effort and remaining allowance
are Unknown. This is the dedicated implementation worker, not lead acceptance;
no AI/subagent, live provider, paid fallback, push, release, global installation
or owner auth/config/policy change was made. All installation/configuration and
mock Source activity used disposable machine-test fixtures.

Item 5 checkpoint: `44ddef5c34904cef74fd0d3a571ba6d24cff55c0`,
`2026-10-19T11:23:48+02:00`. Corrected the preserved parser header comparison,
validated exact optional metadata outside fences, and blocked recognized canonical
Copilot/Perplexity implementation routes before admission/background start/Source.
Wrapped adapters also refuse declared implementation. No Source success or exit
is invented for those pre-dispatch refusals. Unknown custom commands stay
unvalidated; absence retains legacy behavior. Five initial focused tests passed.

Item 6 adds immutable, exclusive run evidence under
`coord/results/<worker>/<task>.outcomes/<run-id>/`: actual bounded UTF-8 report,
effective prompt and dispatch binding, with hashes in additive schema1 outcome
provenance. Native output is captured completely; canonical proposal adapters
publish the actual answer through `UNIO_TASK_REPORT`, never receipt pointers.
Verification requires Source0, matching task/run/prompt/command/revision, unchanged
repository since dispatch, scope and executable passing checks. Prior feature
commits, including binary changes, do not become new report-only work or invalidate
a diagnostic. Legacy empty-work still fails. Current result, review/review-set,
review material and handoff recheck the report. Complete report/provenance enter
bounded review material and `report.md` handoffs; size refusal never clips it.
Strict revision keys and legacy result/review behavior are preserved. Copied
standalone engines and thin configs use frozen embedded metadata code. Task
examples are optional fenced metadata, so default tasks remain legacy.

Preserved failed checks and corrections in this worker:

- The first item 5 native suite exposed a missing Perplexity blocked-state entry
  (`KeyError`); fixed, then the five-test suite passed before the item 5 commit.
- A quoting typo in the newly added oversize-report fixture prevented test
  collection during development; corrected before successful native runs.
- Adapter-install tests initially found the preserved outcome helper preflight
  emitted a different unsafe-directory diagnostic before the adapter preflight.
  The directory refusal now preserves the adapter diagnostic; all three pass.
- The added copied-engine fixture initially used a filename other than `unio`.
  The existing ownership guard correctly refused before a provider. The fixture
  now copies to a directory containing `unio`; its focused rerun passed. No
  production ownership guard was changed.

Focused validation uses the owner's machine-only fixture accelerator (normal
uid1000, zero effective capabilities, disposable private tmpfs fixtures) for native
machine suites. No real provider/authentication call ran inside those fixtures.
The outer worker Source/native exit remains Unknown until its parent records this
invocation's completion. Mock Source0/7 and adapter outcomes below are test
observations, not worker acceptance or a new model-quality measurement.

| Check | Result |
| --- | --- |
| `bash -n unio-install.sh` | passed |
| `python3 -B tools/embed-adapters.py --check` | passed, byte-identical |
| `python3 -B tools/embed-task-plan.py --check` | passed, byte-identical |
| `python3 -B tools/embed-task-outcomes.py --check` | passed, byte-identical |
| `python3 -B tests/unio-task-outcomes.py` | passed, 11 tests (198.142 seconds) |
| `python3 -B tests/unio-route-contract.py` | passed, 7 tests |
| `python3 -B tests/unio-adapter-outcome.py` | passed, 9 tests |
| `python3 -B tests/unio-copilot.py` | passed, 16 tests |
| `python3 -B tests/unio-perplexity.py` | passed, 11 tests |
| `python3 -B tests/unio-adapters-install.py` | passed, 3 tests |
| `python3 -B tests/unio-thin-config.py` | passed, 1 test |
| `bash tests/unio-quality.sh` | passed: 16 shell + 80 contract + 26 coverage checks |
| `git diff --check` | passed |

The report suite covers no-provider canonical/background refusals, malformed and
fenced metadata, actual report success without an implementation commit, Source
failure, empty/missing/invalid/oversize reports, code changes, missing Validate or
scope, altered/disappeared report, stale task/prompt/run binding, receipt-pointer
rejection, result/review-set/handoff integrity, prior binary feature commits,
standalone/thin execution, material bounds and legacy empty-work compatibility.
A final targeted metadata run also passed all three parser tests after tightening
the refusal for a malformed heading without a space (`##Outcome`).

No functional item 5–6 deferral. The full gate and independent current-code lab
reviews remain the lead's integration/acceptance work per this frozen assignment.
Unsigned local evidence retains the established same-user trust model; unknown
custom wrapper capabilities remain unvalidated. Earlier metrics, tail, scope,
disk and route/thinking bounds were retained. No version/UI/brand change.

End receipt: `2026-10-19T11:39:58+02:00`. Requested route remains ChatGPT subscription /
Codex CLI 0.163.0 / `gpt-6.1-sol` LOW; effective model/effort/allowance Unknown.
Implementation plus focused machine checks returned for lead review, not acceptance.
