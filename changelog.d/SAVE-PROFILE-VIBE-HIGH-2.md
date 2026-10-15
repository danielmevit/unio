### Populated-store saving cost measurement

- Investigate-only: measure installed-engine `save create` latency against
  a populated store (12 distinct saves across 4 workers) versus a small
  baseline on fresh synthetic fixtures; no product source, timeout or
  validation change.
- Record that retention's deep re-validation of every active save dominates
  the populated-store cost, and recommend one bounded follow-up scope in
  docs/development/SAVE-PERFORMANCE-NEXT.md.

AI-Assisted-By: GLM 5.3 / Mistral Vibe
