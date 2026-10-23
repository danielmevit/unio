# Focused 0.5.23 compatibility correction

- Restore manual verification without a Source result when no required artifacts
  are declared. The temporary document remains `not_run`; declared contracts
  still refuse missing bound delivery evidence before validation.
- Readiness fixtures emit complete structured findings. Keep verdict-only
  approval coverage visibly approved but extraction-incomplete and unready.
- Preserve bytecode suppression through sanitized task-outcome child environments;
  use the private TMPDIR for adapter-outcome fixtures instead of /dev/shm.

Worker: existing ChatGPT subscription / Codex CLI 0.163.0 / requested
`gpt-6.1-sol`, low; effective settings Unknown. Base `3b5606157a499c8c1349676af8ea41a8c5417998`.
Fresh baseline quality, prompt-transport and run-identity each exited 1.
Dated command receipts and original failures are retained outside source in
`/mnt/d/Vibe Coding/_vm/unio/tmp/unio-next/compat-sol-low-20261023/`.
Implementation checkpoint `6e07e03d3c1af48243dfb8acf68b18e5dff58b82` passed
all 11 requested commands (actual exit 0 each):

| Command | Result |
| --- | --- |
| `bash -n unio-install.sh` | pass |
| `python3 -B tools/embed-task-outcomes.py --check` | byte-identical |
| `python3 -B tools/embed-adapters.py --check` | byte-identical |
| `bash tests/unio-quality.sh` | 16 shell + 81 contract + 26 coverage |
| `python3 -B tests/unio-prompt-transport.py` | 73 checks |
| `python3 -B tests/unio-run-identity.py` | 36 checks |
| `python3 -B tests/unio-task-outcomes.py` | 15 tests |
| `python3 -B tests/unio-adapter-outcome.py` | 10 tests |
| `python3 -B tests/unio-required-delivery.py` | 30 tests |
| `python3 -B tests/unio-review-coherence.py` | 5 tests |
| `bash tests/unio-branding.sh` | pass |

Mock commands ran through the supplied private tmpfs harness with UID1000 and
zero effective capabilities, bounded to 900 seconds each. No actual provider ran
inside it. Original baseline command exits remain 1/1/1; no candidate check
failed. Syntax/embedded checks ran on the ordinary host. No embedded regeneration
was needed. Bytecode scan found no `.pyc`/`.pyo`; scope and whitespace checks pass.

Confirmed and fixed: manual no-Source delivery loading, verdict-only readiness
fixtures, sanitized child bytecode setting, adapter fixture temp location.
Coverage readiness was corrected using the same complete structured fixture and
passed its 26 checks; the baseline quality suite stopped earlier in cases.
Other preceding required-delivery defects were not presumed to remain and were
not rewritten; the current delivery suite passed, including actual bound-artifact
and tamper checks. No claims are made about unexecuted older reproductions.

Lead reviews, full hour gate and acceptance remain separate. No additional
provider invocation, Source0 acceptance, main push, release or global install.
Final commit adds this check record only; executable code is the checked checkpoint.
