# Operator legibility improvement round — 2026-10-19

The seven improvements below come from a heavy Vecto session led through
Mistral/Vibe. Its operator found the core worktree, verification and independent
review loop useful, but could not reliably tell why runs ended or which kinds
of work each route could perform. The external report remains unchanged.

## Current acceptance

All seven items have implementation commits on the isolated integration branch.
They are not yet accepted, pushed, released or installed globally. The final frozen-candidate gate and clean second independent review are running;
lead assessment and delivery follow their actual results.
New receipt fields are additive; legacy tasks and route command shapes remain.

| Item | Implemented behavior | Evidence and remaining acceptance |
| --- | --- | --- |
| 1. Per-run budget telemetry | Tokens, turns and USD used versus configured caps, with reported, estimated or Unknown provenance; supported stop reasons in report verdicts. | Adapter suites and native focused checks passed. Generic exit3 alone does not identify a particular cap. |
| 2. Dispatch-time contract checks | Known adapter routes use their actual parser and bounds before provider/version calls or admission. Diagnostics identify the flag, bound and configuration remedy. | Native route tests passed, including standalone/thin configurations, custom routes and12M within the Vibe16M bound. |
| 3. Nonblocking tail | Last40 lines and exit by default; explicit-f follows, configurable line count. | Focused tail checks passed; the initially unbounded regression subprocess was corrected. |
| 4. Annotated task scope | Warn about supported annotations without including them in the path; preserve literal spaces and parentheses; planner and verification agree. | Focused scope/planner checks passed; literal-parenthesis broadening was corrected. |
| 5. Distinct blocked outcome | An explicit implementation task on a known proposal-only Copilot/Perplexity route refuses before dispatch with blocked_no_repo_access. | Outcome and adapter checks passed. Absent declarations retain legacy behavior; only exact `## Outcome` declares metadata. |
| 6. Report-only tasks | An explicit report-only task verifies a real bounded report bound to the successful current Source and unchanged dispatch state, retaining normal scope and Validate checks. | Artifact, tamper, stale, review/handoff and legacy-empty-work checks passed. Public provenance keeps command hashes rather than raw configured command arguments. |
| 7. Storage preflight | Probe actual run-record storage before admission and distinguish storage/permission failures from busy-budget refusals. |193 focused checks passed; original missing-Python and read-only exit contracts were restored. |

Focused checks are component evidence, not final candidate acceptance. The
13-command native outcome verification passed all Validate commands but returned
INCOMPLETE because a test created an untracked Python cache in its source checkout.
The earlier18-command verification passed17 commands; the broad quality command
exceeded its900-second limit. Both original results remain recorded. The final
full gate uses an isolated exact Git checkout and project-owned fast disposable
fixtures, retaining source identity and real test exits without provider calls.

## Attempts and corrections

Mistral subscription / Vibe2.26.1 / requested GLM5.3 HIGH (AI lab Z.ai) produced
preserved partial work. Its first installed helper incorrectly labelled generic
exit3 as a turn cap; the actual specific cap is Unknown. Two later canonical
adapter runs returned backend connectivity failures below their16M caps: name
resolution failed, then all connection attempts failed. Those failures do not
establish a token-cap failure or a model-quality ranking.

Antigravity / agy1.4.2 / requested Gemini3.8Flash MEDIUM supplied items3–4.
ChatGPT subscription / CodexCLI0.163.0 / requested gpt-6.1-sol LOW completed
items1–2 and5–7, with dedicated integration and compatibility corrections.
Quota interruptions and partial commits remain separately preserved. The final
correction committed ea9a4d7 and362c932 and passed14 outcome tests plus focused
route/thin/embedding checks before Source/native1 at the genuine usage limit;
its committed work is available, but the failed call is not reported as Source0.
Effective model/effort and remaining allowance stay Unknown unless evidenced.

## Independent review

The complete diff exceeds native review-set's300000-byte material bound. That
preparation was retired before any reviewer call. Reviewers inspect the
complete frozen local checkout through separate native report-only Source tasks;
no patch is clipped, bound raised or native review APPROVE fabricated. Preserve
separate blind verdicts, actual Source exits, artifact verification and the lead
assessment. At least two current-code reviewers from different AI labs are
required. Catalog availability does not prove current capacity.

## Earlier milestone and delivery order

Continuous delegation shipped in v0.5.21. The first managed live CLI-session
candidate remains preserved at04c51ee6902d6a56dd709e58baaaeeddb1834a0b, with
Source0 and six native checks passed, but no completed independent review or
integration. This operator round took priority over that work; it does not
replace or restart it. Finish these reliability fixes, then resume that saved
managed-session candidate and lead-continuity scope. Phone access follows;
native Windows remains before macOS. Further CodeGraph work stays deferred.

The existing website, dashboard, brand and owner projects are outside this round.
The planned delivery is one v0.5.22 reliability release, using focused checks and
the real full gate, followed by isolated artifact/upgrade checks, installation
before publication and official-download verification. These are planned steps,
not a claim that publication or installation has already happened.
