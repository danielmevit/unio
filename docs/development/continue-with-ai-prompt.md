# Continue Unio

Read the local project's newest coordination log and actual receipts before
starting work. They take precedence over dated examples in the repository.
Check the owner's latest instructions, `unio version`, and `unio policy`;
do not infer current availability from an earlier successful worker run.

## Current release — 2026-10-10

Continuation 2026-10-11: official and installed stable remain 0.5.9.
The owner completed the dashboard/site work and pushed it through `9f6a4f2`.
That work is integrated with the checked CLI candidates; the earlier parallel
UI writer hold has ended. Preserve its plain X controls, small status squares,
frameless floating map controls and monochrome board. The website embeds the
real dashboard map through a GET-only demo shim. Keep its `activity.css` injection
anchor, rebuild the demo after dashboard changes and regenerate the installer
with `tools/embed-browser.py` after every bridge edit.

The owner subsequently resumed small dashboard/site changes in a separate
Opus session. Those scopes are reserved again for that session. Advance the
functional CLI here and preserve any newer owner commits when integrating.

Source includes the 0.5.10 archival/authentication/daily-use candidate and the
0.5.11 performance probe, fleet overview and read-only task planner. These are
not new published releases. The planner passed 12 focused tests plus native
scope/validation and lead corrections; dispatch remains a separate future slice.
The combined-source validation retains one failed full-gate restore assertion:
the isolated case and subsequent full saving sequence passed, including all
186 recovery checks. Failure diagnostics and concurrent limits-test logging
were hardened without removing assertions. Read the newest local receipts for
remaining combined checks and exact publication state; do not infer a new release
from a source push. Current work mode is YOLO/low; continue 0.5.x, never 0.6.0
for this batch. Google/Bing account setup remains explicitly deferred.

Next functional priority is the reproduced 30-second automatic-save timeout.
GLM 5.3/high through Vibe 2.26.1 profiled the path, then stopped at its configured
4M cumulative-token cap (Source3). The lead committed its unvalidated partial
work separately; it is not merged. A representative baseline profile points to
repeated Git/ignore calls. A traversal-only comparison preserved the same file
map with fewer calls, but full capture, equivalent history and refusal behavior
still need validation. Preserve the partial work and evidence; never describe
it as an accepted optimization or a subscription outage.

The existing lead then implemented narrower sibling-only ignore batching,
keeping depth-first traversal and existing retention/deadline semantics.
Six focused real-Git tests passed. Two matched-history full saves completed
in 26.35/26.18 seconds; baseline attempts hit the existing 30-second bound.
Ignore queries fell from 66 to 6 on that fixture. Read
[the measured limits](SAVE-PERFORMANCE.md#sibling-ignore-batching--2026-10-11-source-candidate)
and the newest local receipts for full functional/native acceptance; no
general real-workspace timeout fix or release is implied.
The completed slice passed all 186 manual and 61 automatic saving checks,
plus native scope and six validation commands. The lead personally reviewed
the patch; no additional AI reviewer was launched. Final handoff changes are
documentation only, with runtime identity checked against the verified source.

The owner added [native macOS and Windows support](CROSS-PLATFORM.md), with
an initial file/function inventory and staged acceptance. Windows currently
uses WSL; native Windows and macOS remain planned. A Pane-like
[interactive session workspace](SESSION-WORKSPACE.md) is a separate proposed
milestone reusing the current dashboard and one engine. Desktop packaging
does not itself provide native worker support; architecture discussion with
the owner's Opus session is ongoing.

[Unio v0.5.9](https://github.com/danielmevit/unio/releases/tag/v0.5.9) is
published and installed from `0c2def4dfee307622b3d5959641a22d220d1576a`.
It preserves all nine Opus dashboard commits at `0aa9a8b` and packages the
completed Copilot/fleet integration. The complete gate passed in 740.945s;
all six browser suites, exact artifacts, upgrade/restore, official download
hashes and installed runtime/payload checks passed. Operator settings and
custom templates were preserved; earlier failed evidence and tags remain intact.

The next functional task is measured recovery-save optimization, followed by
explicit single-attempt dispatch. Retention, cached authentication and the
isolated performance probe are source candidates pending release. Check the local coordination log for actual worker state;
prepared tasks are not completed implementations. The latest managed dashboard
URL comes from `unio dashboard ensure --open-browser`. A separate design preview
may show demo data. Further map grouping and remote pairing remain follow-up work.

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

1. Correct project-wide save retention and measure mounted-filesystem saving
   and observation overhead. New workers encountered the 32-save project cap:
   current retention only evicts older saves belonging to the same worker.
   Preserve all history while designing explicit archive/retention behavior.
   A failed helper is not proof of lost commits or an existing last-good save.
2. Add supported, read-only allowance and readiness adapters with truthful
   Unknown, observation age and reset handling. Auth status and allowance
   are separate: the [help-only inventory](AUTH-READINESS-INVENTORY.md)
   recommends Claude's documented JSON auth command as the smallest auth
   adapter; it has not established safe output fields or exit semantics.
3. Connect checked capacity/readiness evidence to scheduling and explain
   why a worker is idle or a task waits. Existing per-budget admission stays
   authoritative; a manual reading grants no launch or retry permission.

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
