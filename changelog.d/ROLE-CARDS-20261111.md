# Package compact role startup cards

- Package canonical worker and reviewer startup cards under `docs/ai/WORKER-STARTUP-CARD.md`
  and `docs/ai/REVIEWER-STARTUP-CARD.md` into installed templates via deterministic
  `tools/embed-role-cards.py` with destination safety preflight checks.
- Extend `unio init` to copy role startup cards into project `coord/docs/` when absent while
  preserving existing custom project cards.
- Add static role-card guidance pointer line to policy header literal strings in both
  admission snapshot paths, directing workers to matching frozen task roles with project and
  template fallback.
- Update installer WORKER and REVIEW template compact entry points and `docs/ai/START_HERE.md`.
