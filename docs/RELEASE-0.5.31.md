# Unio 0.5.31 — inspect scope before spending a worker run

This unreleased candidate makes current task scope easier to inspect, supports the current Antigravity and Vibe CLIs under the latest-CLI policy, renames the YOLO work mode to Fast and adds an experimental adaptive managed lead. The combined gate, installation and publication have not happened; check official release assets before treating a working-copy version as shipped.

## Task preview

Run `unio verify WORKER TASK --preview`, optionally with `--json`, to inspect the task's current scope, declared validation commands, required artifact names and classified changed paths. It observes the current worktree; it does not predict what a future worker will change or establish admission, delivery, verification PASS or owner acceptance.

Preview reuses native task, Git and scope helpers, takes the participating worker's nonblocking lock and checks for observed task/Git drift across parsing. It runs no Validate command or provider and leaves results, reports, recovery saves and the ledger unchanged. STOP remains readable. Busy, changing, incomplete or unsupported input returns 2; an observed scope mismatch returns 1. Report-only preview is deliberately unsupported in this first slice. Native lock metadata and disposable temporary files are operational details, not a claim of zero filesystem activity.

Bash completion offers `--json` only after `--preview`. Ordinary verification and its existing extra-argument behavior remain unchanged. Deterministic race regressions instrument only private disposable fixture engines; the production command contains no executable test hook. Snapshot checks detect observed drift; they do not exclude arbitrary unmanaged host writers or adversarial changes that return to the same state between observations.

See [task preview](TASK-PREVIEW.md).

## Antigravity compatibility

The optional canonical adapter was inspected against CLI 1.3.5 and 1.5.9. It records the observed version as provenance, or `Unknown` when the query fails, and does not refuse by version number. 1.3.5 keeps its legacy argument form; every other version passes the selected low, medium or high effort explicitly after the fixed Gemini selector. Process exit 0 plus a terminal stream ERROR remains a failure, and a CLI that rejects an argument, model or effort fails honestly, without fallback or retry. The earlier exact-version refusal in this batch's development notes is superseded by the latest-CLI policy; the Vibe adapter follows the same policy for 3.1.2 and newer.

This is CLI compatibility, not proof of account access, effective model, reasoning effort or remaining allowance. No additional model catalog entries are authorized and Unio does not exclude an external CLI auto-updater globally. The compatibility tests use offline fake CLIs. Real successful 1.5.9 reviews used the separately pinned experimental wrapper; they are route evidence, not a claim of a live trial through the new canonical adapter.

See [Antigravity adapter](integrations/ANTIGRAVITY.md).

## Fast mode name

`unio mode fast|balanced|thorough` replaces the YOLO name. `yolo` stays an accepted alias and remains the stored schema-1 value, so existing projects keep working. Modes still do not change permissions.

## Experimental adaptive managed lead

`unio lead-session` is an opt-in, owner-driven Codex lead. Each turn is one explicit `run`. AUTO effort requests LOW for coordination and XHIGH for planning (`--kind planning`) and for the review turn after an owner-recorded worker terminal event. No inference happens while it waits. A run keeps its owned app-server alive up to `--turn-wait` (default 3600 seconds); at the deadline it requests an exact `turn/interrupt` and records an outcome only from a terminal event or the provider's thread state, otherwise `unknown`. `recover` handles a stale turn on the same thread. Rejected attempts keep their pending effort and review wakeup. It requires a ChatGPT-subscription Codex login and the registered `codex` lead; close any other lead session on that account first. It has been tested offline against an executable fake app-server only; live Codex interrupt, approval and stale-turn behaviour remain Unknown. See [adaptive lead effort](ADAPTIVE-LEAD-EFFORT.md).

## Evidence

Grok subscription/Build 1.0.77/requested Grok 4.6 HIGH authored the initial preview. Mistral subscription/Vibe 3.1.1/client-selected GLM 5.3 with high catalog declaration completed its bounded corrections and authored the compatibility update. Effective server identity and effort remain Unknown. Final author Sources exited 0 and passed five native validation commands each. The final preview suite contains 22 tests; the adapter suite has 52 checks.

An independent Antigravity/agy 1.5.9 review requesting Gemini 3.8 Flash HIGH returned CLI/adapter/Source 0, terminal SUCCESS, four complete report artifacts, native verify PASS and APPROVE. It ran the 22 preview tests and 52 adapter checks. The existing lead assessed the composition and verified exact author-module bytes and both embeddings. The reviewed implementation remains frozen in its original worktree. Subsequent preparation incorporates the released 0.5.30 documentation and changes only release documentation and the literal version value, with a separate fidelity proof; it does not invent a fresh canonical approval.

Original failures remain separate: Grok's correction stopped on actual HTTP 402 allowance exhaustion with WIP preserved; an earlier GLM correction passed its checks but introduced a forbidden production test hook that the lead rejected; a later lead setup refusal happened before any model call. Passing process exits and earlier checks alone did not accept those revisions. No extra credit purchase, paid fallback, authentication change or model substitution was used.

The Fast rename, CLI-policy change and adaptive lead were added to this batch after the evidence above. They have their own focused checks and reviews; the final adaptive corrections still await an independent current-code review and the lead assessment.

## Remaining scope

The full combined release gate, isolated installation and official delivery have their own required receipts. This update does not add automatic preview at dispatch, report-only prediction, global account visibility, automatic CLI updates, managed-lead ownership or a new dashboard. Operational policy separation, measured recovery optimization, one-module extraction and onboarding work remain before the later phone and desktop milestones. No measured token saving or whole-app certification is claimed.
