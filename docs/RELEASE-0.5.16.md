# Unio 0.5.16 — measured recovery saving

Recovery saves do less repeated filesystem metadata work when validating
stored task text, content bodies and commit bundles. The loader checks private
metadata on the exact no-follow descriptor used for the bounded read, then
retains the existing size, content-hash and Git-object checks.

Both worktree observations, complete old-save validation, retention pins,
newest/corrupt protection, archive accounting and capture budgets remain in
place. No persistent validity cache or reduced-validation mode is introduced.

## Measured outcome

An isolated generated Windows-mounted fixture contained 400 paths, about
4.9 MB of worktree content and 32 valid prior saves. A completed baseline
capture took 304.93 seconds; the subsequent candidate took 249.01 seconds.
Both read the same stored content. Pathname privacy checks fell from 39,593
to 26,360. A first baseline refused at its configured 300-second capture
bound; both candidate observations completed. The small-history difference
was minor: 24.29 versus 23.95 seconds.

These are instrumented installed-helper timings, excluding installation,
fixture preparation and shell-wrapper startup. Total bookkeeping can extend
beyond the helper's capture checks. Host I/O and cache effects are uncontrolled,
and the first baseline followed a bulk-copy reset. The default budget remains
30 seconds; this populated fixture still exceeds it. No universal speed
percentage, automatic-controller deadline success or reasoning-effort quota
savings is claimed. See the [full measurement record](development/SAVE-PERFORMANCE.md#descriptor-bound-deep-reading--2026-10-13-source-candidate).

## Validation and delivery

Focused installed tests exercise exact committed/index/worktree restoration,
binary data, claim/newest pins, actual archival, corrupt evidence, unsafe
stored files, descriptor metadata changes and fresh worktree observations.
The final release additionally requires the full frozen-source quality gate,
exact artifacts, isolated upgrade/restore, installation before publication,
actual installed saving checks and official download hashes. The latest
[development handoff](development/continue-with-ai-prompt.md) records completed
delivery separately from this scope description.

Implementation route: existing ChatGPT subscription / Codex CLI 0.162.1 /
requested GPT-6.1 Sol low, under the owner's bounded experiment. Effective
serving identity and effort remain Unknown. Worker output, machine checks and
personal lead acceptance are separate evidence. No additional AI reviewers
were invoked under the current YOLO policy.
