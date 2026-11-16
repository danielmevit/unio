0532-RELEASE-PREP: prepare the 0.5.32 candidate (metadata and notes only;
no runtime algorithm changes). `UNIO_VERSION` is 0.5.32. The six embedded
managed-lead helpers are byte-identical to base f52396b; only the embedded
managed guide changed. New `docs/RELEASE-0.5.32.md` covers the two fixes
(deferred first-turn thread creation; completed turn stays exit 0 with a
`warning` when waiting cleanup hits lock contention).

Evidence for the lead: combined offline checks 5/5 exit 0 on f52396b; fresh
Opus 5.5 XHIGH current-code review APPROVE (2 low, 4 info, same lab as the
authors, not cross-lab); three owner-authorized live turns LOW, XHIGH, LOW
completed via codex-cli 0.169.0 / requested gpt-6.1-sol with zero bootstrap,
across TWO managed sessions because of a lead harness error (XHIGH→LOW on one
thread). Effective model and effort are Unknown.

Guides: the managed-lead guide drops its stale "no real Codex turn" claim and
adds safe rollback (0.5.31 cannot read newer state; needs matching binary plus
pre-upgrade backup while idle; never delete `coord/lead-effort/`). The display
guide documents the display-only stale `waiting` limitation as backlog. The
starter guide points to 0.5.32 for the managed trial.

Pending, lead only: full quality gate on the final reviewed candidate, private
install and smoke checks, CHANGELOG.md heading, publication, global install.
