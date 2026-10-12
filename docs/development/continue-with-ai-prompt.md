# Continue Unio

This handoff continues development of Unio itself. To use Unio to build a
different app or project from scratch, use the
[new-project prompt](../ai/NEW-PROJECT-PROMPT.md) instead.

## Prompt for the next Unio development lead

Paste this into a future session when the owner hands over Unio development.
The separate session building another project does not take over this lead.

```text
Continue developing Unio in /mnt/d/Vibe Coding/_vm/unio/repo.
Read applicable AGENTS.md instructions, docs/ai/START_HERE.md, the newest
../coord/AGENT-LOG.md entries, and this entire handoff:
docs/development/continue-with-ai-prompt.md.
Read docs/development/LEAD-ROUTING.md and its referenced guides.

Inspect current Git state, worker receipts and owner instructions before
planning. Preserve other agents' work and any active writers. Register your
actual lead alias only after the outgoing Unio lead has handed over.
Check installed capabilities and policy, then reuse the managed dashboard
and show its actual URL.

Official and installed Unio 0.5.12 is already delivered. Do not repeat its
release checks or publication for unchanged code. Recent work added README
startup instructions, independent project sessions and separate prompts;
those are documentation changes, not a new runtime release.
The new-project guide now has separate YOLO, Balanced and Thorough prompts.
Those options do not change this Unio development workspace's YOLO policy.
New-project reasoning profiles Economy/Adaptive/Maximum are documented as
separate owner choices. They are not native switches and do not raise this
Unio development workspace's xhigh ceiling or authorize max here.

The next planned functional task is matched diagnosis of real automatic-save
helper exit -9. Its cause is unknown, and preserved Git commits remain intact.
Read the latest log, receipts and docs/development/ROADMAP.md before starting.
Estimate 1–3 hours for diagnosis, then estimate a bounded fix from findings.
Do not rerun frozen AI tasks or erase their original failures.

Keep YOLO/low and shared-account limits, including sessions in other projects.
Delegate suitable implementation; free models remain routine workers only.
Default to high/supported middle, xhigh ceiling, no max/ultra or paid fallback.
Resume before authorized runs and stop new runs after the cycle.
Give task estimates and proactive progress summaries, preserve commits and
handoffs, and finish agreed work without unnecessary continue checkpoints.
Keep releases in 0.5.x and preserve owner dashboard, website and brand work.
```

Read the local project's newest coordination log and actual receipts before
starting work. They take precedence over dated examples in the repository.
Check the owner's latest instructions, `unio version`, and `unio policy`;
do not infer current availability from an earlier successful worker run.

The lead **must** follow [task estimates and progress summaries](LEAD-ROUTING.md#mandatory-task-estimates-and-progress-summaries):
give a rough time range before every task, proactively summarize progress at
least every 10 minutes during active work or waits, and revise estimates when
the plan changes. Include elapsed and remaining time, active workers, blockers
and the next step. Do not wait for the owner to request a status report.

Follow [mandatory continuity](LEAD-ROUTING.md#mandatory-continuity-until-the-authorized-work-is-complete):
keep progressing through the authorized deliverable after checkpoints and status
questions. Finish, honor an explicit owner pause, or explain a genuine blocker;
before an unavoidable stop, save work and leave a dated actionable handoff.
Report background activity only when an actual process is still running.

## Current delivery state — 2026-10-12

Official and installed stable are **[v0.5.12](https://github.com/danielmevit/unio/releases/tag/v0.5.12)**,
published from `81e21e7`. The complete gate passed on `3ff333c` in 954.14 seconds;
only checked README/changelog release labels differ, with every other tracked
byte identical. Exact installer/artifact checks, 0.5.11 upgrade/backup restoration,
installation and real-project experience commands before publication, and all
six official download hashes passed. Final native integration passed six commands
and ten focused journeys; independent copied-install acceptance passed 31 checks.
The managed dashboard serves the installed release's exact assets. Check
GitHub's latest stable and `unio version` before changing the operator's runner.

**[v0.5.11](https://github.com/danielmevit/unio/releases/tag/v0.5.11)** remains published
from `e0dd00b`. Its complete gate passed on `0e8636f` in 1528.528 seconds; only
the final README differs. Its separate artifacts, 0.5.10 upgrade/restore,
installation-before-publication and six official download checks passed.

**[v0.5.10](https://github.com/danielmevit/unio/releases/tag/v0.5.10)** is also published,
from `db78932`. Its complete gate passed in 1215.704 seconds and its separate
artifact, 0.5.9 upgrade/rollback, installation and six-download checks passed.
Prior tags, agent configuration and owner templates were preserved in both upgrades.

Delivered work includes bounded recovery archival/storage usage, cached Claude
sign-in observations, remembered task filters and the daily-use guide, followed
by measured sibling-ignore batching, fleet overview, task planning, explicit
approved dispatch, independent review receipts/concurrent collection and local
worker experience/conditional advice. Read [the release guide](../RELEASE-0.5.12.md)
and [version plan](../VERSION-PLAN.md).
Source worker failures remain failures; later lead checks do not convert them
into successful model deliveries. Preserve original receipts and partial work.

The **released 0.5.12** implements the bounded
[worker-experience CLI](../MODEL-EXPERIENCE.md): explicit revision assessments,
task-specific profiles and conditional advice using local fleet facts.
Gemini completed the saved GLM draft; its native checks and independent installed
journey passed. Personal lead review reproduced and corrected corrupt-store and
correction-ordering omissions. Original Source outcomes remain preserved.
The complete release gate, installation/tests and publication are finished;
do not restart them. Automatic capture/routing remain separate. The next useful
slice is diagnosing the remaining real-workspace automatic-save failures,
initially **1–3 hours** for matched reproduction before estimating a fix.
See [current priorities](ROADMAP.md#next-useful-slices).
Continue 0.5.x; do not shift this work to 0.6.0.

Use YOLO/low: focused meaningful checks, one workflow per shared subscription
including the lead, early commits and truthful handoffs. Capable subscription
workers implement features; routine/free agents support bounded chores and cannot
lead. After one worker and one suitable replacement fail, this existing lead
finishes the correction without a second Codex session. Current owner holds,
spending restrictions and actual availability override old examples.

Owner dashboard/site/branding work through `0d46dff` is preserved. The dashboard
uses plain X controls, small status squares and frameless map controls. Keep the
website demo's `activity.css` injection anchor; bridge changes require
`tools/embed-browser.py`, and canonical routing/effort/scoreboard changes require
`tools/embed-adapters.py`. Reuse unchanged release evidence for prose-only edits.
Get the actual local URL from `unio dashboard ensure --open-browser`.

Native [macOS/Windows support](CROSS-PLATFORM.md), the
[interactive session workspace](SESSION-WORKSPACE.md), phone pairing and acting-lead
handover remain planned. Windows currently uses WSL. Lead cooldown restart is
experimental/opt-in; its genuine subscription-limit restart remains unobserved.
Google/Bing account setup remains deferred.

## Earlier checked backend evidence

These are historical implementation facts, not new release claims:

- Sibling-only save ignore batching preserved capture/refusal behavior and
  passed 186 manual plus 61 automatic saving checks and six native validations.
  Two matched-history saves took 26.35/26.18 seconds against baseline attempts
  reaching the existing 30-second bound; ignore queries fell from 66 to 6.
  See the [measured limits](SAVE-PERFORMANCE.md#sibling-ignore-batching--2026-10-11-source-candidate).
  A general real-workspace timeout fix is not established.
- Corrected prepared-task planner `58dfe85`: 13 focused tests and native4/4.
  Explicit dispatch `9930263`: native7/7, eight CLI and five installed workflow
  tests; actual grants, scope reservations and dependency evidence stay required.
- Review receipt delivery `81ecc76`: native4/4/scope10, nine receipt methods,
  existing review compatibility and seven separate installed acceptance checks.
  It reads evidence without a provider call or human acceptance. The subsequent
  concurrent collector adds explicit reviewer calls; the local summary stays read-only.
- Scoreboard bundling and collection contract `b0e5889`: native4/4/scope3,
  including the previously failing branding test and canonical adapter check.

Original failed checks, partial worker work and source outcomes remain preserved
in the local workspace. Read the current receipts; do not replay old broad suites
for prose-only changes or treat self-review as another AI lab's verdict.

## Earlier source integration — 2026-10-10

The development checkout adds Copilot Free / Auto Balance as a bounded routine
proposal worker, its packaging/discovery entry and a persistent
[agent fleet guide](AGENT-FLEET.md). These source changes are not a new published
release; official/global 0.5.8 remains unchanged. Exact helper seven offline checks and
three shipping checks passed. One actual corrective Copilot task delivered a
reviewed documentation draft in 10.958s; usage labelled `gpt-6-luna`. Two earlier
setup failures remain preserved. Auto rejects explicit effort flags; empty provider
and model registry fields must be arrays. No local model or paid fallback.

Future leads read fleet, routing, effort and scoreboard guides. Current subscriptions
have distinct groups; aliases sharing each subscription serialize in low tier.
Perplexity remains proposal/research only, free Zen/Copilot initially routine
workers. Next functional priority remains save-retention reliability.

## Dashboard integration checkpoint — 2026-10-10

The owner authorized integrating Opus's saved dashboard work at `0aa9a8b`
and then continuing functional milestones. Its nine commits are preserved on
`agent/claude-dashboard-ui`; the release candidate is on
`agent/codex-dashboard-release`. Version 0.5.9 includes that interface work and
the already-reviewed Copilot/fleet packaging. Do not redo the owner website or
silently add the unfinished map-grouping proposal to this release. Read the
local coordination log for actual gate, publication and installation outcomes.
After delivery, prioritize save-retention reliability, then supported readiness
and scheduling. One native workflow per shared subscription still includes lead.

## Previous release checkpoint — 2026-10-10

[Unio v0.5.8](https://github.com/danielmevit/unio/releases/tag/v0.5.8)
is published and installed. Exact release source:
`bc8625837ae8574149bc87b8eefa069f7f1f8cbf`. The complete unchanged quality
gate passed in 710.043 seconds; five isolated artifact checks (including
40/40 selftest), upgrade/backup restore and official download checks passed.
The installed engine, capacity runtime, dashboard and browser files match
that release, with operator settings and custom lead templates preserved.
Later commits do not rewrite published tags or assets.

- v0.5.3: browser-to-worker workflow, output/files, work modes and native
  shared-budget workflow admission.
- v0.5.4: manual/automatic saves, separately authorized continuation and
  experimental owner-enabled lead cooldown restart.
- v0.5.5: installed browser launcher and interactive, task-first work map.
- v0.5.6: installed manual capacity readings, age/reset and Unknown handling.
- v0.5.7: managed background dashboard, shared task filters, visible AI agents
  and limits, plus explicit Codex metadata refresh with cached observations.
- v0.5.8: packaged Vibe implementation and Perplexity research/code-proposal
  adapters, with local integration discovery and explicit manual setup.

The browser reads local observations; it never queries a provider. Explicit
`unio capacity refresh codex --group codex` updates the supported Codex reading.
Other account readiness, fleet refresh and dispatch integration remain planned.
Missing, stale or expired readings stay Unknown; a passed reset is not proof
of refill. See [capacity usage](CAPACITY-READINGS.md).

The v0.5.8 release packages optional [subscription adapters](../integrations/README.md).
The standalone installer
copies both exact adapter files to `~/.config/unio/lib/adapters`
and adds read-only `unio integrations [--json]` (file metadata only; JSON via
isolated stdlib Python). Its offline test and generator check are wired into
the complete passing quality gate. External dependencies and sign-in remain
manual; installation does not activate these routes. Vibe 2.26.1 supports explicitly pinned
GLM 5.3 and Mistral Medium 3.5/high, with 2M/$5 default and 4M/$10 substantial
cumulative task bounds. Both pins were checked against the actual installed
CLI schema offline; nine functional tests passed. A real corrected-wrapper GLM
run saved an early packaging commit, then ended with a connection failure at
1,791,060 cumulative tokens/estimated $2.571018, below its local bounds.
Opus completed the saved implementation, passed four native checks and received
personal lead approval. Packaging is merged alongside the owner's website.
Effective model/effort and remaining monthly allowance stay Unknown.

Perplexity supports one research answer or a selected-file code-proposal packet,
then a separate capable implementation agent reviews, applies and validates.
GLM 5.3, Kimi K3 and the connector's GPT-6 Sol Thinking identifier are pinned;
GPT-6.1 Sol is not exposed in that pin and is not silently aliased. Eleven
offline tests passed. The owner completed manual setup; one account-backed GLM
Thinking trial succeeded in 121 seconds. It returned a plan referencing missing
attachments, so its proposed implementation and claimed tests remain unverified.
The prompt now requests code/tests inline; no attachment is downloaded. This is
one account observation, not proof of another account's access or effective identity.
A separate Kimi K3 Thinking parser trial completed in about 300 seconds with
two complete inline code files. Personal inspection and its six fake test methods
found one incorrect array fixture. Preserve the draft for a separate implementation
agent; it has not been merged or accepted as a readiness feature.
Use the [manual setup and native proposal workflow](../integrations/PERPLEXITY-WEB.md).
The disabled upstream text tool parser is not enabled as a command executor.

Genuine lead subscription-limit-to-restart acceptance remains unobserved.
The owner approved experimental opt-in publication without waiting hours to
manufacture that event. Do not revive that removed release hold.
See [cooldown usage](../LEAD-COOLDOWN.md).

Local workspace relocation completed 2026-10-09: use
`/mnt/d/Vibe Coding/_vm/unio` (`D:\Vibe Coding\_vm\unio`). All 149 Git
worktrees and refs were preserved and repaired. Historical evidence keeps its
old paths; resolve them through local `coord/WORKSPACE-PATHS.json`. See the
[completed relocation record](WORKSPACE-RENAME.md).

## Project website — 2026-10-10

A one-page Astro site lives in `site/` and publishes to
<https://danielmevit.github.io/unio/> through `.github/workflows/deploy.yml`
on every push to `main` that touches `site/`, `bridge/`, the workflow or
`CHANGELOG.md`. The workflow pins its actions to commit SHAs, and only the
deploy job may write to Pages. The page shows the version of the first
`## X.Y.Z` heading in `CHANGELOG.md` whose line does not say "unreleased":
keep "unreleased" in a work-in-progress heading and remove it at release.
Colors are the dashboard's dark theme in `bridge/activity.css`; the layout
follows the owner's game-UI reference (HUD bars, readouts, inverted
selections) without its accent colors. Titles use Doto (weight 800), body
IBM Plex Mono and buttons Archivo, all self-hosted through Fontsource; the
full brand rules are in [docs/BRAND.md](../BRAND.md#visual-identity). Lab logos in
`site/src/marks.ts` are copied from the dashboard's MIT-licensed Lobe Icons
paths. The work map panel is the real dashboard on a demo project:
`site/scripts/demo.mjs` copies `bridge/` into `public/demo` at every build and
`site/demo/shim.js` answers its API from `site/demo/fixtures.json` (re-capture
with `site/scripts/capture-demo.cjs` against a dashboard running the local demo
project from `tmp/site-demo/showcase2.sh`); no provider is called. Preview with
`cd site && npm install && npm run build && npx astro preview` (`npm run build`
runs the demo copy; a bare `astro build` does not).

## Next functional work

Read the [roadmap](ROADMAP.md), [consolidated backlog](IMPROVEMENT-BACKLOG.md)
and [version plan](../VERSION-PLAN.md). Finish one bounded feature at a time.

1. Diagnose remaining real-history save failures with a matched workload.
   Archival and measured sibling-ignore batching already shipped. Both recent
   implementation runs reported automatic-save helper exit -9; its cause is
   unknown. Preserve commits, failed receipts and any actual last-good save.
2. Then choose one scoped slice from review-finding aggregation, additional
   supported readiness adapters or the macOS/Windows platform audit. Fleet,
   planning and explicitly approved dispatch already shipped; automatic routing,
   live-lead attachment/transfer and phone pairing remain future work.
3. Preserve delivered 0.5.10/0.5.11/0.5.12 evidence and reuse unchanged checks.
   Do not restart completed implementation or add features to their frozen tags.

Both initial Perplexity trials and the owner-requested
[matched four-scenario comparison](PERPLEXITY-FIELD-TRIALS-2026-10-10.md) are
complete. Both Thinking routes received identical material sequentially on the
shared account. Both planners passed 16 independent checks; both authored two
faulty test fixtures, and their security findings were complementary. No planner
was merged. Preserve original responses; these observations are task-fit guidance,
not a universal ranking or implementation acceptance. Assign actual feature work
separately, without blind retries or separately billed fallback.

Phone/session pairing, live lead messaging and further UI polish remain
planned. The browser launcher is local by default; it does not provide a
paired remote session. See [mobile session companion](MOBILE-SESSION-COMPANION.md).

## Delegation and delivery

Read [lead routing](LEAD-ROUTING.md), [model effort](MODEL-EFFORT.md),
[task-fit evidence](MODEL-SCOREBOARD.md), [worker escalation](../ai/LEAD-ESCALATION.md)
and [work modes](../WORK-MODES.md).

- The current owner-selected cadence is YOLO/low: focused checks per coherent
  feature, personal lead assessment and the complete gate at release. Reuse
  unchanged passing evidence. Future owners can select another review policy.
- Low tier allows one independent workflow per shared budget, including the
  lead. Do not start an extra Codex worker beside a Codex lead. Independent
  budgets may advance disjoint ready tasks concurrently.
- Available Codex, Claude, Grok, Gemini and explicitly pinned Vibe workers
  are main implementation options.
  Choose by checked task fit and current owner availability. The latest batch
  used Opus for the Perplexity adapter and existing-lead concrete corrections
  after incomplete or invalid worker attempts. Original failures
  and lead corrections are recorded in the scoreboard; no model ranking or
  independent security acceptance follows from these small samples.
- Free OpenCode models remain routine supporting workers. Check current zero
  pricing and pin primary/helper routes before each assignment. No paid-token
  fallback, account creation, billing change or promotion to lead is allowed.
- Start at high or the supported middle; GLM stays high. Escalate supported
  effort only for a concrete difficulty, up to supported xhigh. Never request
  max or ultra; a high-only route stays high. A requested level does not
  prove the effective level.
- Use one Source invocation per task unless the owner explicitly authorizes
  another. Preserve a struggling worker, try one suitable replacement, then
  let the existing lead finish the remaining correction. Do not cycle through
  more sessions on the lead's limited budget.
- Substantial tasks normally get 90 minutes, or up to two hours for heavier
  work. Commit an early coherent checkpoint, preserve reports and inspect
  automatic saves. A snapshot is not a commit or an off-device backup.
- Resume Unio before Source/review and stop it afterward. Keep paths quoted,
  take log timestamps from `date`, and avoid self-matching process patterns.

Publish only completed, meaningfully tested versions under current owner
authorization. Keep published tags and assets immutable, install and exercise
the exact verified artifact, preserve operator configuration and retain a
rollback backup. Never merge or push a designated private lead branch.

Older dated findings and release notes are historical evidence. Start with
this checkpoint, the current backlog and local receipts rather than reviving
their completed work or superseded provider holds.
