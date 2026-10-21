Admission startup now accepts UNIO_ADMISSION_TIMEOUT (whole seconds 1..300,
default 30; explicit 5 preserves the old deadline). Failed handshakes distinguish
deadline, EOF, partial reply, startup/refusal and storage errors without suggesting
capacity cleanup for transport failures. Atomic policy/grant handling is unchanged.

Implementation receipt: existing ChatGPT subscription / Codex CLI 0.163.0 /
requested gpt-6.1-sol LOW, dedicated worker; effective settings Unknown.
Base 2b0e4e5. No real provider calls, pushes, releases or global installation.
Focused checks and final revision are recorded in the delivery handoff.

Worker handoff, 2026-10-21T20:01+02:00:

- Early implementation commit `bae5c62` at 19:51:46+02:00; functional candidate
  `cabe388`. Base delta contains only the five assigned paths. Managed-session
  files and canonical worker embeds are unchanged. No additional provider
  invocations, global installation, Vecto mutations, pushes or releases.
- Actual checks: `bash -n unio-install.sh` exit 0;
  `python3 -B tests/unio-admission-deadline.py` exit 0 (36 installed checks);
  `python3 -B tools/embed-codex-worker.py --check` exit 0 (byte-identical);
  `TMPDIR="$PWD/tmp/admission" python3 -B tests/unio-lead-budget.py` exit 0
  (52 checks); same TMPDIR with `tests/unio-work-policy-guard.py` exit 0
  (36 checks); `git diff --check` exit 0.
- Baseline: installed unchanged `2b0e4e5` into owned scratch, inserted a
  six-second fake holder delay in the installed test copy, observed refusal at
  5.30 seconds with the old mixed timeout/EOF/partial diagnostic. The candidate
  admits a six-second delay under an explicit 20-second deadline. This proves
  the admission bound, not a filesystem root cause.
- New coverage also checks invalid public Source/background/review/review-set
  configuration, pre-holder rejection without grant changes, post-consumption
  timeout leaving the grant used, distinct EOF/partial/death/refusal/storage
  reasons, IPC/slot cleanup, stderr despite failed report writes, defaults and
  bounds, STOP, lead capacity and owner-budget refusal. Faults use only owned
  installed mock copies; the provider boundary is a marker. Existing consent
  tests preserve the real fake-provider exit 7 and concurrent single use.
- Preserved failure: first regression exit 1 exposed Bash's killed-process
  diagnostic masking the holder-exit marker and echoing embedded source. The
  corrected path replaces signal output with status-only diagnostics. Original
  `tmp/admission/tests-first.log` remains; later runs passed. No owned timing,
  authentication, quota or other operational failure was observed.
- Owned `/mnt/d` installed smoke passed as ordinary UID 1000 with effective
  capabilities zero; no tmpfs harness was needed. Logs and dated receipt are
  in untracked `tmp/admission/`, retained for the lead, not committed as product
  files. Exact native Source start/exit and effective model/effort remain
  Unknown to this worker; the coordinating lead owns those receipts. Start
  evidence is the workspace log's 19:47:02+02:00 admission observation; this
  handoff completed about 15 minutes later, within the 45–90 minute estimate.
- Helper inventory and follow-up: see `docs/development/ADMISSION-DEADLINES.md`.
  Source anchors: save constants/capture validation at `unio-install.sh:25444`
  and `:25479`; capture child `:27638`; provider readiness `:27445` (2 seconds)
  and acknowledgement `:27364` (15 seconds); result Git helper `:22436` and
  snapshot `:22734` have no enclosing native deadline. Experience has fixed
  record 30 seconds and lock wait 5 seconds (`tools/model-experience.py:34`,
  `:41`), configurable suggest 1..60 (`:1062`). These were inventoried only.
  A separate owned result/Git timing and deadline task is justified before
  changing those unrelated helpers.
- No check establishes lead acceptance. Native verification, two independent
  current-code worker reviews from different labs, the final gate and the
  lead's assessment remain next. No background checks remain active.
