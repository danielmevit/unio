# Unio version plan

Owner direction, 2026-10-05: close the rename at 0.5.0, then keep the next
changes in separate versions with their implementation and changelog entries.

The [2026-10-08 milestone review](development/FUNCTIONALITY-FIRST-PLAN.md)
separates shipped features from source additions and recommends a functional
delivery order. Recovery shipped in v0.5.4, followed by the browser launcher and
map improvements in v0.5.5, manual capacity readings in v0.5.6 and the managed
dashboard/explicit Codex readings in v0.5.7. Optional subscription adapters and
standalone discovery shipped in v0.5.8. Version v0.5.9 integrates the saved
dashboard redesign and Copilot/fleet packaging; published
assets stay immutable.

Validation update, 2026-10-08: see [completed checks, preserved failures and
remaining release work](development/RECOVERY-ACCEPTANCE-2026-10-08.md). The complete candidate gate passed; final documentation-only publication retains identical runtime and test bytes.

| Version | Included work | State |
| --- | --- | --- |
| 0.5.18 | Worker reliability: Vibe live progress and liveness heartbeat, fourth packaged Antigravity adapter with process exit separated from structured outcome, Copilot exact JSONL proposal text | Candidate, unreleased. Public and installed release remains [0.5.17](https://github.com/danielmevit/unio/releases/tag/v0.5.17). Full gate, artifacts, upgrade, install and publication are prepared and not run. A separate Copilot input/group correction is not accepted. |
| 0.5.17 | Safer project selection and experimental managed Codex workers | [Released and installed2026-10-14](https://github.com/danielmevit/unio/releases/tag/v0.5.17); full gate, exact artifacts, upgrade/restore, installed acceptance, dashboard identity and six official download hashes passed. Current-inference effort changes remain unproven. |
| 0.5.16 | Recovery performance and static worker diagnostics | [Released and installed 2026-10-14](https://github.com/danielmevit/unio/releases/tag/v0.5.16); source9ee2a20, combined gate9b4dfc4, artifacts, upgrade/restore, installed saving/audit acceptance and six official download hashes passed |
| 0.5.15 | Local structured review findings, protocol-aware compatibility and dated worker readiness | [Released and installed 2026-10-13](https://github.com/danielmevit/unio/releases/tag/v0.5.15); source 6894b20, full gate on af19d35, exact artifacts, 0.5.14 upgrade/restore, installed findings acceptance and six official download hashes passed |
| 0.5.13 | Matching YOLO/Balanced/Thorough commands and explicit interchangeable Low/Medium/Max reasoning instructions | [Released and installed 2026-10-12](https://github.com/danielmevit/unio/releases/tag/v0.5.13); source f9997dc, full gate, copied-guide packaging, exact artifacts, upgrade/restore, installed command acceptance and six official download hashes passed |
| 0.5.14 | Bounded configurable recovery-save capture budgets and honest deadline diagnostics | [Released and installed 2026-10-13](https://github.com/danielmevit/unio/releases/tag/v0.5.14); source d0abc60, full gate, exact artifacts, upgrade/restore, installed smoke and six official download hashes passed |
| 0.5.12 | Explicit native-revision experience assessments, task-specific profiles and conditional worker-selection advice | [Released and installed 2026-10-12](https://github.com/danielmevit/unio/releases/tag/v0.5.12); source 81e21e7, complete gate on 3ff333c, exact assets, upgrade/rollback and six official download checks passed |
| 0.5.11 | Recovery-save performance probe and measured sibling-ignore batching, local fleet overview, checked planner/explicit dispatch, independent review receipts and concurrent explicit reviewer collection | [Released and installed 2026-10-12](https://github.com/danielmevit/unio/releases/tag/v0.5.11); source e0dd00b, complete gate, exact artifacts, upgrade/rollback and official download checks passed |
| 0.5.10 | Bounded recovery-save archival and usage, explicit cached Claude sign-in, remembered task filters and daily-use guide | [Released and installed 2026-10-12](https://github.com/danielmevit/unio/releases/tag/v0.5.10); source db78932, complete gate, exact assets, upgrade/rollback and official download checks passed |
| 0.5.9 | Saved dashboard redesign: readable task list, agent allowance cards, activity timeline and map readability; packaged Copilot Auto Balance and fleet guide | [Released and installed 2026-10-10](https://github.com/danielmevit/unio/releases/tag/v0.5.9); source0c2def4, complete gate, six browser suites, artifacts, upgrade/restore and official download/install checks passed |
| 0.5.0 | Completed A/B/C/D rename; installer, commands, config, docs and prototypes | [Published 2026-10-06](https://github.com/danielmevit/unio/releases/tag/v0.5.0); source aebe23c; installed with owner approval |
| 0.5.1 | Limit-policy hardening and regression coverage | [Published 2026-10-06](https://github.com/danielmevit/unio/releases/tag/v0.5.1); source af437b1 |
| 0.5.2 | Queue approval, reservation and recovery library | [Published 2026-10-06](https://github.com/danielmevit/unio/releases/tag/v0.5.2); source 1bddeab |
| 0.5.3 | One real browser-to-worker workflow alongside browser output/files; owner-approved work modes yolo/medium/safe and subscription tiers low/medium/high with native shared-budget workflow accounting | [Published 2026-10-08](https://github.com/danielmevit/unio/releases/tag/v0.5.3); exact source ae61bf3d11ff; full gate, artifact and upgrade checks passed; installed with owner approval |
| 0.5.4 | Automatic recovery saves, checkpoint continuation and lead CLI cooldown restart; browser themes and live work map | [Released 2026-10-09](https://github.com/danielmevit/unio/releases/tag/v0.5.4): complete automated gate and upgrade/restore checks passed; lead cooldown is experimental and explicitly enabled, genuine lead-limit-to-restart cycle unverified; owner approved release with that limitation |
| 0.5.5 | Installed browser launcher (`unio browser`), interactive work map with active-first layout, task-logo cards, and muted outcome strips | [Released 2026-10-09](https://github.com/danielmevit/unio/releases/tag/v0.5.5); complete automated gate passed; phone pairing, allowance meter and live lead attachment remain planned |
| 0.5.6 | Installed manual capacity readings with age, optional reset and Unknown handling; supporting readiness inventory and local documentation-link audit | [Release and downloads](https://github.com/danielmevit/unio/releases/tag/v0.5.6); automatic readings, browser meters and dispatch integration remain planned |
| 0.5.7 | Managed background dashboard, shared task filters, visible AI agents and allowance windows, explicit Codex metadata refresh and cached observations | [Released and installed 2026-10-09](https://github.com/danielmevit/unio/releases/tag/v0.5.7); exact source30842abea68c, complete gate and official asset/install checks passed |
| 0.5.8 | Packaged Vibe implementation and Perplexity research/code-proposal adapters; local integration discovery and documented setup | [Released and installed 2026-10-10](https://github.com/danielmevit/unio/releases/tag/v0.5.8); source bc8625837ae8, complete gate passed in 710.043 seconds; artifact, upgrade/restore, official download and installed-command checks passed |

The owner approved the [delivery priorities](development/ROADMAP.md#approved-delivery-priorities)
on 2026-10-06: finish 0.5.3, deliver 0.5.4, then allowance monitoring, agent
connection reliability, smarter delegation, a built-in parallel review
pipeline, reasoning/context efficiency and measured performance. The owner additionally requires
[automatic work saving](WORK-SAVING.md) during runs and on failures in v0.5.4.
On 2026-10-11 the owner added [macOS and Windows host support](development/CROSS-PLATFORM.md).
An [interactive session workspace](development/SESSION-WORKSPACE.md) is a separate
planned feature using the existing dashboard and engine. Neither has an assigned
release number or implies current native support. The current delivery freezes
the checked CLI slices, including [concurrent review collection](REVIEW-COLLECTION.md),
for release checks while owner UI/site work proceeds separately. Finding
aggregation and routing automation are later work, not additions to this gate.
On 2026-10-07 the owner added [lead cooldown restart](development/LEAD-COOLDOWN-RESTART.md):
an owner-enabled supervisor waits outside the lead CLI and restarts it from
the saved handoff after its allowance resets. The five-hour fallback is five
hours and one minute. Repeated lead limits create new waits; existing worker
limit handling stays unchanged. Implement work saving before this restart slice.
Continue with patch releases in 0.5.x: 0.5.11 follows 0.5.10. Further release
numbers and dates are not assigned yet. See the
[save-performance probe](development/SAVE-PERFORMANCE.md) for measured baselines;
its measurements do not imply a save-engine speedup. The
[worker progress contract](WORKER-PROGRESS.md) covers browser output and files;
its implementation has passed native checks and the real funded browser journey.
[Task time budgets](development/TASK-TIME-BUDGETS.md) give substantial work
90 minutes or up to two hours, with bounded individual checks and early saves.
The lead configures the native limit, wrapper and supported CLI deadline for each
assignment. This guidance does not automatically change installed defaults.

Shipping preparation follows these changes. It does not automatically create
a new version or publish a release. The published v0.4.0 title is now
**Unio 0.4.0 — trustworthy results (M1)**; its existing tag and files are kept.
New public release headings use Unio without a former-name suffix.

For each version, its worker updates the installer version and existing
branding assertion as part of the scoped implementation. The lead rolls its
changelog fragment into the matching unreleased section before the full
merged-tree quality gate. Focused validation and lead review permit integration
and pushes under the current delivery policy; publication requires that full gate.
The website reads release headings from the changelog at build time. Keep
`unreleased` on main's candidate heading until its tag and assets are published;
then push the final heading so the website advertises an available download.
Final README/changelog labels may reuse a complete gate only after confirming
that every other tracked byte is identical and checking the changed Markdown.
Record both the full-gate revision and final release revision in provenance.

Publication requires owner authorization. On 2026-10-06 the owner authorized
completed 0.5.x releases, unattended sequential browser 0.5.3 and checkpoint
0.5.4 work, and installation of the latest verified release on this machine.
The current sequence under the newest owner YOLO+low policy uses one independent
workflow per shared provider/account including lead, focused native validation and
personal lead review without extra model reviewer jobs for this session, with a
full required release gate before publication. This supersedes the earlier
current-session requirement for two AI-lab reviews on every slice. Independent
reviews remain available under other owner-selected policies. Frozen checks and
owner authority remain in force. Exact pushes remain required. It does
not authorize billing changes or publication of unfinished milestones.

The approved 0.5.0 installation preserved agent settings, left the original
config intact for rollback, and migrated worker markers and shared guards.
Private receipts and rollback live under the enclosing workspace's
`artifacts/migration-unio/` and `tmp/unio-next/receipts/`. Installed authentication
stores and billing settings were not changed. The existing workspace path
remains intact so worktree links and historical receipts continue to resolve.

The historical 0.5.0, 0.5.1 and 0.5.2 tags retain their original gated source
snapshots, including their earlier development notes. Each public release
includes an exact-source installer, source archive, legal files, checksums and
provenance. Isolated install, version, help, legal and offline workflow checks
passed, and all six downloaded assets matched their prepared hashes.
