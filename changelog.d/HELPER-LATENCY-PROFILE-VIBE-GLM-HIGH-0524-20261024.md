HELPER-LATENCY-PROFILE-VIBE-GLM-HIGH-0524-20261024: diagnose Windows/WSL
helper latency. Measured real 2026-10-24 runs: every automatic save exceeded
the 60 s capture deadline because each publish deep-loads the capped 32-save
store (11,597 bodies, 154 MB) on v9fs (37.7 s) plus two more full metadata
scans (23-33 s each), while worktree observation costs 2.5 s; a real result
observation costs 19.4 s against the fixed 30 s experience deadline.
Documented the smallest justified correction (capture timeout 150-180 s plus
removing the redundant store re-scans) with regressions and a half-day
estimate. No code, timeout, policy or save changed.
