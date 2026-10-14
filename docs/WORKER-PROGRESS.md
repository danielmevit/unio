# Worker progress and console — browser feature contract

Owner request, 2026-10-06. Planned addition to browser v0.5.3; this document
does not claim implementation. Keep the running UI design task unchanged and
assign this work as a separate bounded native Unio slice against its verified
dependency base. See the [version plan](VERSION-PLAN.md).

## Implemented native adapter progress

One bounded slice is implemented at the adapter level: the optional
[Vibe worker](integrations/MISTRAL-VIBE.md#live-progress-during-a-run) now
prints fixed allowlisted operational labels and a liveness-only heartbeat to
its own stdout before the native process exits, derived from the CLI's
documented streaming route. Because the underlying stream delivers completed
history entries, records may be emitted after an action completes; labels
describe observed history, not certified currently-running tool state. It
emits no raw assistant or reasoning text, prompts, commands, file paths, tool
payloads (arguments or results), authentication or provider error text, invents
no completion state, and drives no policy decision. The browser console contract
below remains the fuller design; its observation layers can consume these labels
as already-public worker output.

## What the owner sees

Each worker has its actual task and lifecycle state, the latest short
excerpt from its emitted output, and the time that output was observed.
Clicking the excerpt opens that worker's console: actual CLI messages,
commands and results as the CLI emits them, with access to earlier output.
Files, the worktree path and changes belong in a separate tab or view.

The console follows the existing run. Opening it, refreshing it or
reconnecting must not start another worker or spend an AI request. The first
slice is an output viewer; terminal input or interactive process attachment
requires a separately specified control contract. It does not promise every
keystroke, buffered message or internal reasoning step is observable.

## Truthful progress

- Derive state from native run/process evidence and preserve the distinction
  between execution, verification, review and acceptance. A worker saying
  "done" is output, not proof of successful execution or readiness.
- Display an actual bounded excerpt or an explicitly labelled deterministic
  event description. Do not invoke an AI to summarize status or invent a
  completion percentage. Keep the underlying output available for context.
- Show update age, waiting for first output, stale output, missing logs,
  connection failures and actual process completion distinctly. A quiet
  process is not automatically failed or finished.
- Keep worker, task and run identity attached to output. Handle concurrent
  workers, log growth, partial records, reconnects and rotation without
  combining different runs or duplicating execution.
- Provide follow/pause controls, a stable view while reading earlier output,
  keyboard access and readable state announcements. Never trap scrolling or
  announce every output character to assistive technology.

## Console and files boundaries

Use existing local bridge authorization and opaque project-owned worker/run
identifiers. Serve bounded literal text, strip terminal control sequences,
and render emitted markup and links as untrusted data. Apply documented
sensitive-output exclusions; raw logs can contain secrets, so do not expose
unrestricted raw log files or promise perfect automatic redaction.

The file view reads only allowed files in the selected project-owned
worktree and fixed, safe status/diff information. Resolve paths and reject
traversal, escaping symlinks, credential files, Git internals, unsupported
binary files and excessive reads. Do not turn paths or emitted commands into
shell instructions. Preserve reviewer isolation; owner-visible progress is
not permission to inject another reviewer's findings into a blind review.

Show a useful local worktree path. A native terminal/editor/folder launcher
is optional future work requiring a fixed, reviewed launch mechanism;
browser console access does not claim to launch or control the native CLI.

## Acceptance checks

Use offline CLI-output fixtures and browser tests for running, quiet,
completed and failed workers, multiple runs, long output, partial records,
rotation, reconnects and stale state. Verify zero provider calls and zero
dispatches from all observation actions. Test literal rendering, terminal
escape handling, sensitive-output exclusions, path traversal and escaping
symlinks. Verify accessible desktop/mobile console navigation and the
separate files view. Preserve existing approval, verification, review and
acceptance behavior, followed by independent AI-lab reviews and the full
merged-tree quality gate.
