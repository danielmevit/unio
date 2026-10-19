# Operator legibility improvement round — 2026-10-19

The seven improvements below come from a heavy Vecto session led through
Mistral/Vibe. Its operator found the core worktree, verification and independent
review loop useful, but could not reliably tell why runs ended or which kinds
of work each route could perform. The external report remains unchanged.

## Current acceptance

All seven items and the three subsequent review corrections are committed.
Two independent blind correction-delta reviews approved81a3f40: Antigravity/agy1.4.2/
Gemini3.8Flash HIGH and ChatGPT/Codex GPT-6.1 Sol LOW, each with Source0, native0
and artifact verification0. The lead inspected the actual corrections and
findings. The versioned full gate81a3f40 passed0 on2026-10-19,18:08:56UTC+02,
in2225.171seconds. The complete batch shipped in [v0.5.22](https://github.com/danielmevit/unio/releases/tag/v0.5.22)
on2026-10-19. Artifact and upgrade/rollback checks passed, installation preceded
publication, and all six official downloads matched their hashes.
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

## Independent review and correction

The complete diff exceeds native review-set's300000-byte material bound. That
preparation was retired before any reviewer call. Actual reviews used complete
local current checkouts through native report-only Source tasks; no clipping,
limit increase or native `unio review` approval was fabricated.

Mistral subscription/Vibe2.26.1/requested Mistral Medium3.5 HIGH independently
approved the full baseline and its six-line test correction, with actual
Source0/native0/report verification0. Antigravity/agy1.4.2/Opus4.6 fixed Thinking
and Gemini3.8Flash HIGH returned genuine CLI0 full-code reports but private
capture errors; they remain supporting content, not clean native approvals.
GPT-OSS120B Medium claimed a missing output file and was unaccepted. A later
Opus delta hit a real quota response; a Gemini delta ended in stream ERROR.
Original calls, failures, report bytes and partial work remain separately saved.

A subsequent Mistral Medium3.5 HIGH correction-delta call ended with an
infrastructure failure, Source2, below its12M token and estimated USD10 caps.
Its draft is preserved but is not a completed review. Original failures remain
separate from code-quality assessments; no cap exhaustion or provider fault
is inferred.

A separate ChatGPT/CodexCLI0.163.0/requested GPT-6.1 Sol LOW full-code review
finished Source0/native0/report verification0 with REQUEST-CHANGES. It found
three reachable gaps: uncertain Perplexity asks labelled reported1; safely
quoted literal paths losing outcome telemetry; and unbounded follow-test reads.
The lead confirmed them from source. Dedicated Sol LOW corrections47516ff,
c398dc7 and9b0f273 plus regenerated embeds81a3f40 passed six focused suites and
all six native Validate commands. Source0 took131 seconds. Uncertain ask counts
now stay Unknown, safe quoted argv retains binding, and silent/missing-appended
follow output hits a deadline and reaps its child.

Two fresh, blind current-delta reviews from Antigravity Gemini3.8Flash HIGH and
Codex Sol LOW each returned APPROVE with no findings, Source0/native0/artifact checks0.
Requested settings do not prove effective identity, effort or allowance. These
are separate content reviews, followed by lead assessment; acceptance of a
review artifact is not product or human acceptance.

Two earlier full gates remain failures: the first exposed an outdated guard-test
stdout expectation; the second completed runtime/probe checks but found stale
canonical PROTOCOL tail help. The dedicated test correction and one-line guide
correction retain all guarantees; focused branding and complete docs checks
passed. The final complete gate passed0 at81a3f40 from17:31:25 to18:08:56UTC+02
(2225.171seconds), using a clean isolated Git checkout and zero provider calls.
Tracked source remained unchanged; generated bytecode stayed in the disposable
clone. Final prose updates retain identical runtime/test bytes.

## Earlier milestone and delivery order

Continuous delegation shipped in v0.5.21. The first managed live CLI-session
candidate remains preserved at04c51ee6902d6a56dd709e58baaaeeddb1834a0b, with
Source0 and six native checks passed, but no completed independent review or
integration. This operator round took priority over that work; it does not
replace or restart it. Finish these reliability fixes, then resume that saved
managed-session candidate and lead-continuity scope. Phone access follows;
native Windows remains before macOS. Further CodeGraph work stays deferred.

The existing website, dashboard, brand and owner projects are outside this round.
All seven items were delivered together in v0.5.22 after focused checks, the
complete gate, independent reviews and lead assessment. Artifact/upgrade checks,
installation before publication and official-download verification passed.
The Windows trial requirement is documented for its later milestone; no Windows
runtime or trial restriction was added to this release.
