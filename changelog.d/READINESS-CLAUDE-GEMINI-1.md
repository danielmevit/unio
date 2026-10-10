### Added

- Add `unio readiness refresh claude` and `unio readiness show` for explicit,
  bounded Claude Code sign-in observations, without asking a model. Only
  allowlisted fields enter the private cache; stale or failed readings are
  Unknown, and sign-in never establishes allowance or permission to run.
- Show cached sign-in observations in the dashboard without refreshing a
  provider or adding CLI calls. Other agents remain Unknown.
- Cover storage safety, subprocess bounds, installed commands and browser/API
  reads with isolated checks. Codex corrected and integrated Gemini's initial
  candidate after personal review identified gaps.
