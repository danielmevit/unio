# Cloud session handoff: 0.5.26 source candidates

Written 2026-11-05 by a Claude Code cloud session (Anthropic) at the owner's
request to work through the next milestones. Branch `claude/unio-0.5.26`,
based on main `0c9827f`. Nothing was merged to main, installed, versioned or
published. The local workspace, coordination state, accounts and STOP were not
touched; this session had no access to them.

## Process note for the lead

The [continuation prompt](development/continue-with-ai-prompt.md) planned the
first item as a delegated Sol LOW worker task through installed Unio, with no
inline lead fix. The owner instead asked this session to implement directly.
All three commits are therefore authored by an Anthropic model. Under the
current review rule, independent final reviewers must come from other labs
than the author: Claude/Opus cannot review these. The owner's requested blind
GPT-6 Astra XHIGH opinion for 0.5.26 fits here, plus one more non-Anthropic
lab, then the lead's own assessment. Treat each commit as a separate component.

## Components

| Commit | Scope | Focused evidence |
| --- | --- | --- |
| `8824f5a` | Save helper refuses deeply nested JSON as `invalid_save` instead of a `RecursionError` traceback; `resolve_base` falls back on a deeply nested task record | `tests/unio-save-json-depth.py` 19 checks. Before the fix, `save create`, `save inspect --worker`, `save inspect ID` and `save usage` all crashed through the real CLI on one planted 400001-byte manifest or record |
| `acc1baa` | Review material protocol 3: bounded, hash-bound enclosing source context; readers, review-set and the browser bridge accept it; protocol 1/2 receipts stay current | `tests/unio-review-context.py` 7 cases including exact region hashes, configuration-independent bytes, protocol-2 fallback, review-set and bridge readiness. Existing review tests updated only where they pinned protocol 2 as the default |
| `0a24dd0` | Effort audit runs in its own session; the whole process group is killed before reaping on completion, timeout or oversized output; `requested_model` privacy wording | `tests/unio-effort-audit-cleanup.py` 9 real-process checks; all three scenarios left survivors before the change |

Design details for protocol 3 are in the
[receipt contract extension](REVIEW-RECEIPTS-CONTRACT.md). Changelog fragments
are under `changelog.d/` with the `-0526` suffix.

## Full gate in this container

Every command in `tools/quality-check.sh` was run once on `0a24dd0` with a
private `TMPDIR`, continuing past failures (2996 seconds). 86 of 94 passed. The
8 failures below fail identically on unmodified main `0c9827f` in the same
container, so they are environment results, not evidence about these changes.
Re-run the real gate on the owner's machine before any acceptance.

| Suite | Failure on main and branch | Likely cause |
| --- | --- | --- |
| `unio-copilot.py`, `unio-antigravity.py`, `bridge/tests/worker_files_test.py` | Killed orphan processes still observed | PID 1 is a sandbox init, not a normal reaper |
| `unio-worker-effort.py` | Replaced manifest assertion at the managed-session cleanup step | Unknown; container runs as root |
| `unio-managed-lead-codex.py` | `lost['action'] == 'refused'` | Unknown |
| `unio-admission-deadline.py` | Assertion at line 136 | Unknown |
| `unio-remote-guard.py` | Fixture `git push` refused | Container Git configuration forces commit signing |
| `unio-capacity.py` | Abbreviated `--proj` not refused | Python 3.13 here versus 3.12.3 on the owner's machine |

`bridge/tests/execution_service_test.py` passed in the gate run but is flaky
here on both main and branch (a killed process briefly still running).

## Also observed

Running `tests/unio-selftest.py` with `TMPDIR` unset puts its sandbox inside
the checkout. In one run its teardown failed and two fixture commits landed on
the current branch; they were removed before any push. Set `TMPDIR` outside the
repository until that is fixed.

## Next

1. Lead assessment and two non-Anthropic reviews of the three components.
2. Full gate on the owner's machine, then normal 0.5.26 release preparation if
   accepted.
3. Remaining operational items need owner input or hardware: mounted-drive
   result/save deadlines need real measurements, `review_current` display in
   the browser job view is a UX choice (backend acceptance gating already uses
   it), and model-family normalization and cross-workspace visibility need
   design decisions.
