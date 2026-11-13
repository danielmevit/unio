# Continue Unio development

Read repository AGENTS.md, the newest enclosing coord/AGENT-LOG.md when
available, and the current personal OWNER-WORKFLOW.md before planning. Inspect
actual Git state, installed version, native jobs and current account holds.
The official tag and its assets establish publication; a local version number
or this document does not.

## Current candidate: 0.5.28

Installation and startup safety follows the shipped 0.5.27 recovery/maintenance
release. See [scope and limits](../RELEASE-0.5.28.md) and the changelog.

- Refuse accidental installer sourcing before writes or caller-shell changes;
  print a quoted rerun command for paths with spaces.
- Stage and atomically replace the main runtime file. Preserve old open readers,
  pre-publication failure safety and owned-staging-only cleanup. Helpers and
  configuration still require idle maintenance; this is not whole-installation
  atomicity, zero-downtime upgrading or a security sandbox.
- Preserve live and Unknown Git index locks and refuse before provider/admission.
  The existing writer can finish; Unio never guesses that a lock is stale.
- Explain background Git-lock/Gitdir startup refusals in dated report/log
  fragments, keeping parent acknowledgement distinct from provider execution.
- Use portable test scratch selection and a stable README release link.

Independent scoped current-code reviews and the lead assessment completed.
The one full combined quality gate and isolated installation checks passed. Check
actual receipts and the official release before describing delivery as complete.
Preserve original failures, reviews of earlier code and any Unknown outcomes.
An approval on an earlier revision does not approve changed code.

## Fable's assessment role

The maintainer's current assignment for Fable is advisory product and
architecture assessment. First understand Unio: its purpose, users, workflow,
capabilities, limits and design. Then give scores with reasons, evidence and
confidence, and rank concrete improvements by value, urgency, effort and
relationships. Explain what to keep, simplify, defer or change. A score is
qualitative advice, not a benchmark or release certification.

Feature reproductions, failure injection, stress tests, regression tests and
implementation belong to other assigned workers. Do not resume the earlier
shutdown-test trajectory as Fable's next task. Preserve those partial results
as historical evidence and delegate validation of material claims. Save an
early substantive assessment and useful section checkpoints. The advisory
assessment does not hold up otherwise reviewed and gated app delivery.

## Next priorities

Make persistent Unknown cleanup holds understandable and provide safe operator
recovery, without releasing shared-account capacity while process ownership
remains Unknown. Independently validate natural failure paths before selecting
fixes; a protective quarantine is not automatically a defect.

Preview task scope against inherited branch changes before dispatch, without
silently expanding authority. Design append-only correction history for final
experience records, preserving the original evidence and assessments.

Managed lead lifecycle in the existing dashboard follows operational reliability,
then session-scoped phone pairing, native Windows and macOS. Reuse existing
foundations and inspect their actual state before assigning new work; no
replacement dashboard or speculative platform delivery is implied.

## Operating rules

Delegate source changes through Unio according to current owner routing; the
lead scopes, independently assesses, reviews and integrates. Use separate
worker checkouts, precise allowed paths, meaningful Validate lines and early
commits/artifacts. Follow actual shared-account slots, lead reservation, STOP
and owner holds. Requested startup model/effort, effective Unknown, real exits,
required delivery, tests, independent findings and acceptance are separate.

Respect spending/authentication restrictions and supported CLI/model controls;
check updates while idle and never update an active worker. No blind retries
or paid fallback. Preserve original failed attempts and partial work. Consult
[lead routing](LEAD-ROUTING.md), [model experience](../MODEL-EXPERIENCE.md) and
[work modes](../WORK-MODES.md); the latest owner workflow prevails over old copies.

Answer status questions with the practical goal and current concrete evidence,
then continue authorized useful work. Give estimates and proactive updates.
Do not imply the lead works after its turn ends; identify actual continuing jobs
and the exact next action in a handoff when capacity or runtime ends.
