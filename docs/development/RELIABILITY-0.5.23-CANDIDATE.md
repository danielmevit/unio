# Unio 0.5.23 reliability candidate

## Summary

Prepared and integrated on the private `agent/vecto-reliability-20261021` branch.
The runtime integration checkpoint is `8362d1f`; subsequent report/handoff changes
are documentation only. Main and the installed official engine remain 0.5.22.
No main push, release or global candidate installation was performed.

The update addresses three field-derived boundaries: admission before provider
launch, current review observation, and actual delivery versus a successful
process exit. Vecto's reporting window spans several versions; historical failures
are not all attributed to 0.5.22. Its three evidence inputs were read only.

## Items landed and test evidence

| Change | Relevant commits | Evidence |
| --- | --- | --- |
| Bounded admission and useful failure phases | `a4ca22f` | Configurable 1–300 seconds, default30; admission36, lead-budget52 and policy-guard36 focused cases passed. Atomic slots, STOP, grants and no-call refusal remain intact. |
| Current review status separated from history and acceptance | `54beed5`, `b04aedc`, `ae2521c` | Current revision/material/configuration, opinions and findings completeness are distinct. Native task checks passed; original quota failure and stale history remain preserved. |
| Explicit required text delivery | `3b56061`, `a710c5b`, `68c7ff4`, `ae2521c` | Source/run/task/command/revision-bound artifacts, strict paths and identity checks, partial preservation and missing-delivery refusal. The final delivery suite passed34 tests. |
| Compatibility for configuration and native results | `ae2521c` | Linked config layouts, collection reviewer IDs, invalid-config Source visibility and unbound history covered. Seven selected commands passed,148 counted tests; separate native verification0. |
| Less unnecessary work in unreviewed result observation | `06b12ea`, `4b6f97e`, `2fa351b` | Final coherence27, findings19 and delivery34 tests passed. An introduced explicit-diagnostic hash regression was corrected; original failed evidence remains. Separate native verification0. |
| Canonical bundled operating guides | `a936848` | Four commands and six contract tests passed. Only34 guide lines and a changelog fragment changed; executable installer bytes outside those guide bodies are identical. |
| Personal review workflow on every project using Unio | `2f2276e` | One independent external reviewer plus the existing lead; Codex leads prefer eligible Opus5.5 XHIGH. Canonical/bundled guidance and owner-local startup instructions updated. Guidance does not claim an automatic reviewer selector. |

The retained managed-session CLI slice provides bounded status/output and
idempotent steering of an already authorized active turn. Full lead-session
ownership and automatic takeover are later milestones.

The exact candidate `a936848a9f0f01585e0c32b006bacd446d2fe2e8` passed
`bash tools/quality-check.sh`, exit0, in2975.855seconds. The gate finished on
2026-10-23 at16:18:03+02:00 in a clean isolated clone, with tracked files unchanged
and no untracked files. It made no real provider calls. Earlier failed gates
remain unchanged; their failures are not counted as passes.

On one completed own task on `/mnt/d`, the corrected private engine returned
results in8.322 and7.811seconds; the same-pass installed0.5.22 baseline took11.875
and7.934seconds. The earlier candidate exceeded a45second observer twice.
Concurrent load changed, so these are local observations, not a speedup ratio,
guarantee for every history, or attribution of a filesystem root cause.

## Review and lead assessment

The independent reviewer used the Claude subscription, Claude Code2.1.309,
requested `claude-opus-5-5` at XHIGH. Native CLI, wrapper Source, enclosing runner
and artifact verification all exited0. Effective model, effort and allowance
remain Unknown without independent attestation.

It returned **APPROVE**, with12 explicitly nonblocking observations, on exact
runtime revision `2fa351b`. The full uncut material was576920bytes,
SHA256 `7ca0543db7afe849627d8ce648ed367bb530a6e60d105eeb8a4a8283d3504c87`.
This was a validated report-only Source audit; it is not a native review receipt
or a native readiness approval. The larger material was never clipped to bypass
the native300000-byte review limit.

The later `a936848` only refreshes two bundled guide bodies from canonical text
already present at the reviewed revision and adds a changelog fragment. Exact
comparison proves all other installer bytes identical. The external receipt
remains bound to its original revision. Lead assessment accepts the prepared
private candidate using that unchanged-code evidence, the generated-guide proof,
current whole gate, actual diffs and regression evidence. This does not grant
human acceptance or publication authority.

Latest implementation routes were ChatGPT subscription / Codex CLI0.163.0 /
requested `gpt-6.1-sol`: MEDIUM for demonstrated integration gaps, LOW for result
observation and guide generation. Each Source and enclosing native run exited0;
each separate native verification exited0. Real shared-account mappings and the
lead reservation remained intact, temporary medium coordination tier was restored
to low, and unrelated admissions were closed afterward. Reasoning effort and
coordination tier are different settings.

The lead also reproduced two conservative history/recovery limits using installed
mocks and zero real provider calls. Full dispositions for every field finding and
all12 review observations are in [the field dispositions](VECTO-RELIABILITY-2026-10-21.md).

## Items deferred and why

1. **Review-history recovery and bounded observations, highest follow-up.** A
   pre-provider refusal or context-less legacy receipt can keep the same revision
   nonready after a later approval. Reviewed histories and large projections can
   exceed consumer time/size budgets. Keep the conservative behavior disclosed;
   define explicit supersession and bounded summaries without deleting evidence,
   hiding genuine change requests, automatic retries or silent truncation.
   Estimate4–8hours for a first scoped slice.
2. **Remaining review consumers and diagnostics.** Some execution UI stages still
   use legacy fields; stale/unsafe artifact messages and background declaration
   refusals need clearer reasons. These remain functional follow-ups, rather than
   being hidden by new visual work.
3. **Broader contracts.** Startup/live/pending/effective effort capability reasons,
   unified single-review/collection alias grammar, analysis/binary/ignored artifact
   preservation, bounded enclosing review context, cross-workspace visibility and
   model-family normalization need separate validated contracts.
4. **Full managed lead ownership.** Duplicate completion events and lifecycle
   ownership belong to that next feature milestone. Phone, native Windows,
   app-managed trials/localization/Eqho integration and macOS remain later.

## Files changed

Core work is in `unio-install.sh`, `tools/required-delivery.py`,
`bridge/execution_service.py`, retained `tools/codex-worker.py`, the relevant
embedding helpers, regression tests, operating guides and changelog fragments.
See [admission](ADMISSION-DEADLINES.md), [review status](REVIEW-STATUS.md),
[required delivery](REQUIRED-DELIVERY.md) and [the handoff](continue-with-ai-prompt.md).
The repository root was not expanded with operational scratch files.

## Risks and needs-review

This is a tested candidate with known nonblocking limits, not a guarantee that
every slow-storage or recovery case is resolved. Required artifacts are opt-in
UTF-8 text and need the exact documented heading and a route able to write
`UNIO_DELIVERY_DIR`. Original failures, partial work and historical reviews stay
preserved. Global/shared quota outside this workspace remains incompletely visible.

Owner authorization is still required before pushing main, publishing0.5.23 or
globally installing an unpublished candidate. No Vecto workers were restarted.
Private dated receipts, full gate logs, raw review, timing observations, experience
records and code-identity proofs remain under the enclosing workspace's
`tmp/unio-next/vecto-reliability-20261021/`; they are not bundled into GitHub.
