# Unio 0.5.32 — Managed lead first turn fixed; truthful completion under lock contention

Status: **validated 0.5.32 release source.** The full quality gate and private installation checks passed. Global installation must pass its configuration-preservation and smoke checks before official publication; the release assets and local receipts record the actual delivery state.

This patch fixes two problems in the experimental, opt-in `unio lead-session` Codex backend. It adds no new commands. It does not adopt an existing AI CLI or ordinary TUI session, and it is not an autonomous scheduler. You still drive each turn explicitly and choose the phase with `--kind` and worker events.

## Changes

- **The first managed lead turn now works with a real Codex app-server.** In 0.5.31, `unio lead-session start` created an empty thread and closed its process. Native Codex (observed with codex-cli 0.169.0) writes a thread's rollout only together with its first turn. So the first `run` refused with `thread/resume -32600 no rollout found` before any model turn. Now `start` checks admission, ownership, the subscription account and the model catalog, but creates no thread (`thread_lifecycle: deferred`). The first `run` creates the exact thread in its own process, right before its first `turn/start`. Later runs resume that same thread. There is no bootstrap or dummy model request, no resend and no replacement thread after a resume refusal. Older state stays readable as `legacy`. See [Managed lead](ADAPTIVE-LEAD-EFFORT.md#first-turn-and-the-owned-thread-lifecycle).

- **A genuinely completed turn stays completed under lock contention.** After a completed turn, `run` clears the stored `waiting` flag under the short control lock. In 0.5.31, if that lock was busy for more than 5 seconds, `run` returned 1 (`session state busy`) even though the turn had completed. Now `run` still exits 0 with `delivery: completed` JSON and adds a fixed `warning` that the housekeeping is uncertain. Failed, rejected, interrupted, unknown and uncertain turns keep their exit codes. See [Effort display](LEAD-EFFORT-DISPLAY.md).

The six embedded managed-lead helpers and the managed guide in the installer were regenerated from these sources.

## Validation

- **Author and native checks.** The authors' focused checks and native task verification exited 0 on each fix.
- **Combined offline checks** on candidate `f52396b54cc484b99c87ea1788830987d6c3e4cf`: `tests/unio-lead-session.py`, `tests/unio-lead-session-codex.py`, `tests/unio-lead-effort-display.py`, `tools/embed-managed-lead.py --check` and `bash -n unio-install.sh` each exited 0, with zero provider calls.
- **Independent current-code review.** Claude Pro / Claude Code 2.1.325 / requested `claude-opus-5-5` / XHIGH reviewed the exact candidate (review manifest SHA256 `f7527485549e89a74704ad5a1d6747a2d82ee9607b43924975cc6ba6360f84e9`). Verdict APPROVE, with 2 low and 4 informational findings and no critical, high or medium findings. The reviewer ran offline only. This reviewer is the same AI lab and model as the fix authors, under an owner-authorized higher-effort fallback, so it is **not cross-lab coverage**. The existing OpenAI lead also inspected both production diffs and the native cause evidence.
- **Owner-authorized live trial.** On the private candidate, through ChatGPT subscription / Codex CLI 0.169.0 / requested `gpt-6.1-sol`, three tiny real turns completed with requested efforts LOW, XHIGH and LOW. Zero bootstrap turns were sent. Native thread history shows three completed turns in total. Effective model and effort remain **Unknown**.

**Limitation of the live trial:** the three turns span **two** managed sessions, not one. The lead's own test harness searched serialized streamed chunks for a whole reply. After the first LOW turn completed correctly, the harness misread it and stopped that session. With the harness corrected (it now joins the ordered delta text), a new session ran XHIGH then LOW on one native thread. So the XHIGH→LOW transition is proven live on one thread, but a full LOW→XHIGH→LOW sequence on a single thread was not run live. The offline fixtures cover the full single-thread sequence. The original harness failure receipt is preserved. No further model calls were made to extend this coverage.

**Final release checks:** `bash tools/quality-check.sh` passed on frozen revision `5ebd9c5a8ada966fa8d943436d73477e67adce49`, with tracked source unchanged and zero provider calls. It finished 2026-11-16T12:59:39+01:00 after 3968.312 seconds. A private installation and all six offline smoke checks passed. The subsequent release commit changes only the changelog, these release notes and the development handoff; the runtime, installer and tests remain byte-identical to the gated revision. The package records exact source and validation provenance. Global installation and official publication have separate receipts; they are not inferred from these code checks.

## Upgrading, and rolling back safely

- An existing 0.5.31 session written before this fix is read as `legacy`. If its thread never ran a turn, `run` refuses with the native error and a hint to stop it and start a new session.
- **0.5.31 cannot read the newer control state.** On its next control write, 0.5.32 adds the lifecycle field to an older session. A 0.5.31 binary then refuses that state (fail closed) and refuses a new `start`. A safe rollback needs the matching 0.5.31 binary **and** a backup of `coord/lead-effort/` (owner and session files) taken **before** the upgrade. Restore only while the managed lead is idle and every turn is reconciled. First preserve a separate copy of the current newer directory, including its receipts, without deleting the records. Restore only the managed-lead state, not an unrelated project's files. If you lack a pre-upgrade backup, keeping 0.5.32 or running 0.5.31 in a separate isolated trial project is safer.
- Do not delete or casually move `coord/lead-effort/`, override STOP, or replace an owner whose ownership or pending turn is unresolved. Those records are your history and evidence. The forward field addition above is automatic on write; there is no automatic reverse migration, downgrade or retry. The shorter managed guide's statement about migration is imprecise; this paragraph describes the actual behavior.

## Known limits

- **Stored `waiting` can come back after contention (display only).** If the completion cleanup could not take the lock, the stored flag stays set. A later `worker register` without `worker wait` can then show `waiting` again although nothing is waiting. This affects only the display and never gates a call. It is recorded as backlog work, not fixed here.
- When native Codex persists a thread after an interrupted or killed first turn is **Unknown**; only completed first turns were observed live.
- The deferred-thread creator maps any exception during creation to a known non-delivery. That outcome is true, but it can hide an internal bug.
- The lock-contention regression test depends on a timing margin. A slow machine can make it fail spuriously; it cannot make it pass falsely.
- One stop/start hint can be slightly inaccurate for a `legacy` session whose only turn was never acknowledged (cosmetic).
- Live `turn/interrupt`, approval handling and stale-turn recovery against a real app-server remain unverified.
- Starting a new managed session gives it a new thread. Give it a goal file, your turn files and a short handoff; it does not adopt a whole earlier chat.

These fixes make two specific failures truthful and recoverable. They do not make the managed lead risk-free.

## Guides

[Managed lead](ADAPTIVE-LEAD-EFFORT.md), [Effort display](LEAD-EFFORT-DISPLAY.md), [New-user starters](ai/NEW-USER-STARTERS.md), [0.5.31 notes](RELEASE-0.5.31.md).
