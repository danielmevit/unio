# Proposed releases after v0.5.18

Planning checkpoint, 2026-10-14. These are recommended scopes and rough active
engineering estimates, not shipped capabilities or fixed release commitments.
Owner update, 2026-10-14: native Windows precedes native macOS.
v0.5.18 is delivered. The v0.5.19 candidate is being completed; see its
[release evidence and limits](../RELEASE-0.5.19.md). No new provider assignment is authorized
merely by a row here; use existing owner authorization, current availability and
the selected work policy when freezing each implementation task.

Estimates include focused implementation, personal review and ordinary release
checks. Provider cooldowns, unavailable test machines and a substantial redesign
can add elapsed time. Re-estimate after each bounded technical assessment.

| Proposed release | Outcome | Rough effort |
| --- | --- | --- |
| 0.5.19 | Owned stopping, measured save validation and Copilot compatibility | 2–4 hours for a focused slice; 4–8 hours if deeper changes are needed |
| 0.5.20 | Optional continuous delegation within explicit owner-approved bounds | 1–3 working days |
| 0.5.21 | Managed live CLI sessions and reliable lead continuity | 2–4 working days for the first supported route |
| 0.5.22 | Phone access paired to a selected Unio session | 2–4 working days after session ownership works |
| 0.5.23 | Native Windows execution and a Microsoft Store desktop-app track | Runtime estimate: 1–3 working weeks after feasibility; desktop onboarding, packaging and certification estimated separately |
| 0.5.24 | Native macOS support | 3–6 working days, subject to host checks |

## 0.5.19 — Owned stopping and measured saving

Update, 2026-10-15: populated-store profiling isolated duplicate metadata and
deep validation passes. The checked implementation folds these into one deep
retention traversal without skipping stored-content validation. On one host,
the isolated retention phase averaged 16.14 seconds before and 9.91 seconds after;
two complete captures per engine did not establish an overall wall-time gain.
See the [measurement method and limits](SAVE-PERFORMANCE.md). The earlier
failed profiling attempts remain failures rather than successful measurements.

Bundle this with native stopping of explicitly recorded Linux provider sessions
and the real Copilot filename-array compatibility fix. Stopping must prove owned
cleanup before final saving; processes that leave that session remain unmanaged.
The final stopping proof and combined release checks are still pending at this
planning update. A higher timeout alone is not a performance improvement.

## 0.5.20 — Continuous delegation within a clear work plan

Build on the shipped task planner, explicit dispatch, shared-account slots and
task-specific experience. An opt-in scheduler can advance ready dependencies
under a bounded owner grant, assign distinct eligible accounts concurrently and
explain why other tasks are waiting. Completed work can advance through the
selected review protocol without the lead rebuilding every command manually.

Recheck admission at launch, persist task identity and reservations, preserve
STOP and never replay an uncertain or failed attempt automatically. Unknown
allowance is not available quota. Keep review policy, reasoning effort and
coordination tier independent. Test restart, dependency failures and occupied
shared accounts with offline workers before a bounded real workflow.

## 0.5.21 — Managed live sessions and lead continuity

Launch the first supported interactive CLI through Unio with owned terminal
and process identities. Connect its session to the existing task, worktree,
logs, checks and saves. The existing dashboard gains access to the same
session; it does not become a second orchestrator.

Start with durable observation, reconnect and authorized input. Then connect
handoffs and the existing cooldown supervisor so a replacement session reads
current work without duplicating it. A capable acting lead can be a later
sub-slice after explicit ownership transfer is verified. Existing cooldown
restart is already experimental runtime, not a feature to rebuild from zero.
Do not claim an arbitrary already-open AI conversation is automatically linked.

## 0.5.22 — Session-scoped phone access

Use a mobile browser rather than requiring an Android application. Pair the
phone to one selected Unio session using an expiring invitation and revocable
grants. Begin with status and output, then add deliberately permitted messages
and commands for that session. Show the current permissions and connection state.

Reuse managed session ownership from 0.5.21. Test expired invitations,
revocation, reconnect, wrong-session access and duplicate message delivery.
Choose an authenticated transport explicitly; keep local loopback defaults and
do not expose a general PC terminal or automatically open a public port.
Remote control of arbitrary desktop applications is outside this milestone.

## 0.5.23 — Native Windows

Begin with a 4–8-hour feasibility assessment of the Bash-led engine and shared
host interface. Then implement PowerShell-facing installation, native agent
discovery, Windows locking and owned process trees, safe paths/permissions,
recovery and an appropriate terminal backend. Windows Job Objects and ConPTY
are candidates to evaluate, not an adopted design.

Exercise actual Windows-host installation, independent account admission,
Unicode/space paths, interruptions, exact restore and dashboard startup.
Reuse the existing dashboard instead of making a second orchestration product.
WSL is the working fallback while this port is unfinished. If the audit requires
a broad engine change, split delivery across further 0.5.x releases and update
the estimate before committing to full native support.

### Windows desktop and Microsoft Store direction

Owner clarification, 2026-10-14: the Windows goal is a desktop application
intended for Microsoft Store distribution, not only native command execution.
Keep Windows ahead of macOS. Reuse the existing dashboard and orchestration
engine in a desktop window; choose the desktop framework after a small proof
of concept. Native execution and Store packaging are separate acceptance steps.
A web-based desktop interface does not itself require rewriting every screen in
Windows-native widgets, but native execution requires the host backend port.

First-run UX should help a new user select a project, discover supported AI
CLIs, complete provider-supported sign-in, choose a lead and workers, and start
a small task. Explain missing prerequisites and required subscriptions in plain
language. Keep current agent authentication stores out of project files. Offer
an offline demo project without requiring a paid AI account. Show task progress,
limits/Unknowns, review changes, recovery and explicit stop/continue actions with
clear effects. Preserve CLI access for advanced workflows and the owner's brand.

Evaluate MSIX first for Store distribution, signing and managed updates, while
keeping EXE/MSI as an alternative when actual installer/backend requirements
justify it. Verify real worker launch, Git/worktree access and packaged filesystem
behavior in the prototype before choosing packaging. Test clean Windows install,
upgrade, restart, graceful shutdown and uninstall. Provide accurate Store listing,
privacy information, dependencies and usable certification instructions. Store
approval is Microsoft's decision; the current runtime estimate is not an estimate
for all desktop UX work or certification elapsed time.

Store and GitHub distribution can have different optional integration sets.
For the first Store build, prefer verified permitted integration routes and
leave unofficial web-session connectors outside the package while permission
is unresolved. Open-source publication does not itself authorize access to an
external service. This planning recommendation does not remove an existing
GitHub feature, change account settings or establish that any connector has
legal approval. No provider call or Store submission is part of this document.

Relevant Store requirements include disclosure of external software/service
dependencies (10.2.4), a testable product and certification instructions (10.3),
responsive supported-host behavior (10.4), and a privacy policy describing
accessed/transmitted data and recipients (10.5). Appropriate user consent and
secure handling of project data/credentials belong in the desktop flow.
The policy review found a plausible submission path for a developer tool; it
is not certification or a legal opinion covering every provider agreement.

Checked official sources on 2026-10-14:

- [Microsoft desktop distribution options](https://learn.microsoft.com/en-us/windows/apps/distribute-through-store/how-to-distribute-your-win32-app-through-microsoft-store): MSIX or traditional EXE/MSI distribution.
- [MSIX package requirements](https://learn.microsoft.com/en-us/windows/apps/publish/publish-your-app/msix/app-package-requirements): packaging choices and MSIX benefits.
- [Store policy 7.19](https://learn.microsoft.com/en-us/windows/apps/publish/store-policy-archive/store-policy-7-19): current effective policy at this checkpoint; disclose non-integrated dependencies and provide a testable, responsive product.
- [Published policy 7.20](https://learn.microsoft.com/en-us/windows/apps/publish/store-policies): effective 2026-10-22, so recheck the version in force when submitting.

### Optional Eqho transcription and history logic

Owner direction, 2026-10-15: adapt selected logic from the owner's Eqho
project for the Windows app. Start with editable transcript drafts and local
searchable history, then optional dictation with partial/final updates.
Use the existing Unio interface, task authority and Windows process ownership;
the first flow is app-scoped voice input with an explicit send action.
See the [source assessment, adaptation work and estimates](EQHO-VOICE-INTEGRATION.md).
This is planned work after the native desktop foundation; a bounded 0.5.x
follow-up can carry it without delaying that foundation.

## 0.5.24 — Native macOS

Complete the host-operation inventory and implement macOS equivalents for
locking, process identity/cleanup, safe filesystem access and installer tools.
Keep the same CLI, task semantics and dashboard. Decide actual shell/tool
prerequisites from the audit rather than assuming a GNU utility fixes the port.

Use actual supported macOS hosts or available CI for installation, admission,
interruption, save/restore and dashboard checks. Verify Apple Silicon and Intel
separately; any untested architecture remains unverified. Continue to support
Linux and the existing Windows-through-WSL route.

## Delivery approach

Delegate coherent independent tasks to eligible subscription routes; the lead
coordinates, reviews and integrates. Identify route, CLI version, requested
model/effort and actual outcome in receipts and progress reports. Account
aliases sharing a subscription remain one budget group. Free routine workers
remain support workers, not the lead or final acceptance authority.

Use focused checks during implementation and one combined frozen-source gate
for a useful release bundle. Install and test the candidate before publication,
then verify official download bytes. Keep version status truthful. Do not add
unrelated visual redesign or deferred CodeGraph work to these bundles.

Related plans: [roadmap](ROADMAP.md), [version plan](../VERSION-PLAN.md),
[saving measurements](SAVE-PERFORMANCE.md), [interactive sessions](SESSION-WORKSPACE.md),
[phone pairing](MOBILE-SESSION-COMPANION.md) and [platform stages](CROSS-PLATFORM.md).
