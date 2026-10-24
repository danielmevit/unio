# Lead assessment of the helper-latency diagnosis

Recorded 2026-10-24T11:58:23+02:00. Supporting diagnosis: Mistral subscription / Vibe2.26.1 /
GLM5.3 / thinkingHIGH, commitcabb1db, Source0/native0/nativeverify2checksPASS0.
Requested model/effort do not establish effective identity. Original diagnosis
and raw receipts remain unchanged. This assessment accepts the measurements as
bounded local evidence, with the corrections below; it does not accept a runtime
patch, alter timeouts or claim the automatic save problem is fixed.

## What the evidence establishes

- Installed0.5.23 on this Windows-mounted v9fs workspace repeatedly reached
  the configured60second capture limit. These are save-helper outcomes, separate
  from provider exits and code quality. Existing work is committed in Git.
- Raw component measurements show active-store body reads/hashing11597files /
 154328717bytes taking37.701seconds on v9fs; the same file/byte count took0.25s
  in the private tmpfs fixture. This supports a filesystem cost hypothesis on
  this host; one uncontrolled sample is not a general performance guarantee.
- Read-only helper observations: save usage23.38s, worker inspect32.68s and one
  idle result19.421s, all exit0. These are actual complete command timings.
- Source inspection confirms complete store scans in last_good, deep active
  validation in retention_plan, and a fresh last_good scan in write_attempt.
  Ordinary successful create currently calls write_attempt after publish returns.

## Corrections to the diagnosis

1. Estimated105–125seconds is a cost model assembled from components, not a
   completed automatic-save measurement. The components have different cache/load
   conditions and possible overlapping work. It does not prove a precise bound,
   that60seconds can never work, or that150–180seconds is sufficient. Publication
   writes were not timed. No timeout increase is applied on that basis.
2. Result/experience contention under concurrent captures is a plausible cause,
   not confirmed. Only one idle result was measured; no under-load comparison
   establishes the proposed causal chain. Preserve30second failures separately.
3. Original Sources did not all succeed. The selected table includes local setup2
   and an actual Codex quota1. A save timeout neither explains nor erases those
   exits. Lack of an admission failure in selected logs is not proof none exists
   in all runs or that provider infrastructure is always healthy.
4. The worktree copies are not an exact matched-byte comparison: raw v9fs walk
   reports563regular files /7626234bytes while tmpfs walk reports566files /
   7634022bytes. Do not use that pair for an identical-byte claim or speed ratio.
   The active-store comparison above does match file/byte totals, with unchanged
   original inputs and uncontrolled caches still a limitation.
5. publish acquires saves_lock and releases it in its finally block BEFORE the
   current successful write_attempt call. Reusing an identity after that unlock
   needs a correctness argument; the proposal cannot assume a still-held lock.
   Retention's deep-valid set also differs from last_good(deep=False) semantics
   for a body-corrupt yet metadata-valid save. Preserve that distinction, duplicate
   active/archive refusals, ordering/ties/future timestamps and failure evidence.

## Next bounded correction

Prioritize eliminating redundant post-publication metadata work only where the
same outcome can be proven under the real lock lifetime. Keep both worktree
observations, all existing deep validation, pins/newest protection, active/archive
caps, atomic publication, descriptor checks and refusal bookkeeping. No persistent
cache across captures, ignored-file expansion, cap reduction, timeout change,
policy change or real-store cleanup is part of that slice. Leave periodic newest
lookup and result/experience deadlines to separate evidence-backed work.

Regression evidence must use the installed helper, prove fewer redundant scans
without weakening checks, and exercise corrupt/future/duplicate storage,
publication faults, stable-byte refusal and exact restoration. Timing alone is
not a gate. A proposed implementation still needs native verification, independent
current-code review and existing-lead assessment before private integration.
The owned lead transport/claim remains the next continuity feature; this focused
save correction protects useful work while that separate dependency gate runs.
