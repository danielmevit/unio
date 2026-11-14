# Unio 0.5.30 — review evidence and archive maintenance

This candidate continues operational reliability improvements before lead ownership, desktop and phone work. Review, the combined release gate and installation are pending; the latest published release remains the source of truth.

## What changes

Separately assigned report-only reviews can receive a bounded exact code packet before dispatch, declare its identity in their frozen task, and later attach their verified reports to that packet. `unio review-packet`, `unio reviews-bind` and `unio reviews --reports` expose this evidence separately from canonical native review status. They never promote native readiness or owner acceptance. Old reviews do not become fresh merely through attachment.

The first slice requires a current successful report-only Source, native verify PASS and complete immutable summary, verdict and typed-findings artifacts. Nonzero, missing, malformed or stale evidence is refused. Coverage stays explicit, including scoped paths. Multiple partial opinions do not become whole-task approval. Ordinary review, findings and result interfaces retain their semantics.

Native participating-worker locks, STOP/currentness rechecks and complete pending-directory publication protect managed writers. Pending evidence belonging to other or interrupted writers is preserved. These are trusted-host filesystem controls, not protection from arbitrary unmanaged host mutation. A frozen genuine 0.5.29 reader fixture proves namespace compatibility without a maintainer-only path or download.

Explicit `save archive-worker --apply` accepts optional `UNIO_SAVE_ARCHIVE_TIMEOUT` (ASCII positive whole seconds 1..900, default60). One monotonic deadline covers selected validation, movement and rechecks. The read-only plan keeps30seconds. Existing pins, corruption handling, plan confirmation, save limits and Unknown partial outcomes remain; no automatic archive, purge, force or retry is added.

Lead guidance distinguishes misleading authentication status from actual route failure and preserves owner confirmation before another login request. The reusable Fable research prompt asks the lead to inspect current status and roadmap, select the authorized model and let the research worker choose its approach. Guidance is not an automatic authentication manager, worker selector or perpetual lead service.

## Evidence and remaining work

Implementation: Mistral subscription/Vibe3.1.1/client-selected GLM5.3 with high catalog declaration, followed by Grok subscription/Build1.0.77/requested Grok4.6/high corrections for report reviews; the archive fix was separately authored by the same Mistral route. Effective server identity and effort remain Unknown. Source cap failures, generated-bytecode scope failure and an incomplete Gemini network-stream review remain preserved; process exit0 is not accepted delivery.

The archive Source passed four native checks (54archive and70capture checks); the corrected report-review Source passed its four native checks (12focused tests). The lead independently confirmed that the old-reader fixture equals the official0.5.29 quality runtime. These are component checks, not the combined release gate or a whole-app certification. Independent current-candidate review, lead assessment and combined gate are the next prerequisites.

Deferred: attaching failed reviewer Sources, automatic lab eligibility, managed-lead ownership and phone/desktop interfaces, automatic route-profile dispatch, other adapters, broad engine extraction and measured save-performance optimization. Fable's earlier assessment is advisory; this release does not complete all of its recommendations or establish measured token savings.
