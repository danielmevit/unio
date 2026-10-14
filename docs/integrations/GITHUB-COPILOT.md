# GitHub Copilot Free / Balanced

Unio 0.5.9 packages `tools/copilot-worker.py` as a bounded routine
proposal worker alongside Vibe and Perplexity, without installing or authenticating
any external tool. Follow [the fleet guide](../development/AGENT-FLEET.md)
for assignments and shared budget groups.

## What Balanced selects

On the inspected Copilot CLI 1.0.95, Balanced maps to `--model auto
--auto-tier balance`. It is an automatic routing profile, not a fixed model,
AI lab or reasoning-effort level. GitHub selects eligible models under the
account's plan and policies. This exact Auto route rejects explicit reasoning-effort flags, so the
adapter omits them and records effective effort as Unknown. Balance does
not mean medium or high reasoning. No max/ultra request is made. An unsupported version or setting fails rather
than silently changing routes.

The owner reports Copilot Free. Its included allowance is the only authorized
funding; no purchase, upgrade, billing change, paid API or local fallback is
permitted. Remaining allowance stays Unknown until a supported account
reading supplies it. The adapter does not establish the account's plan or
turn a paid account into a Free one.

## Manual setup

Install the official [GitHub Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/install-copilot-cli)
if needed. This adapter supports the inspected 1.0.95 executable and opts out
of automatic updates for each call. Sign in directly in your terminal if
needed; do not paste tokens or login output into tasks, chat or Git:

```bash
copilot login
```

Existing native authentication stays in Copilot's own store. Unio does not
copy or print it. A CLI installation or successful login is not evidence of
remaining Free allowance.

From an initialized Unio project, create a private receipt parent and add
an alias to your existing `agents.conf` without replacing its other entries.
Use the installed 0.5.9 helper, or the reviewed source-checkout helper:

```text
copilot=python3 '/absolute/path/to/unio/tools/copilot-worker.py' --receipt-dir '/absolute/private/copilot-proposals'
```

With 0.5.9, the installed helper path is
`~/.config/unio/lib/adapters/copilot-worker.py` (or under `UNIO_CONF_DIR`).
Keep the receipt parent outside the Git checkout, owned by you and mode 0700.
The adapter requires it to exist; it never creates an account or dependency.
Then assign a concrete task using an explicitly prepared worker worktree:

```bash
unio account copilot copilot
unio resume
UNIO_TIMEOUT=960 unio run copilot-docs TASK-ID
unio stop
```

The worker name's prefix selects the `copilot` alias. Its task must contain
the public context needed for the proposal. Prepare the registered worktree
using normal Unio project setup first. All aliases on this GitHub account
share one budget; low tier permits one independent workflow in that group.
Known unmanaged owner sessions also consume allowance even though native
slot counts cannot see them.

## Proposal boundaries

Use Copilot for small documentation drafts, inventories and mechanical
patch proposals initially. A capable implementation agent or the existing
lead checks and applies suitable output in its own worktree, then runs the
assigned checks. Delivery is not acceptance, and generated tests are not
independent proof. This adapter does not execute suggested commands or
apply patches. It cannot establish cross-lab review independence because
Auto does not pin the underlying AI lab.

The wrapper feeds task text through stdin, avoiding large argument limits.
It selects GitHub Auto Balance explicitly, clears inherited local/BYOK route
overrides and supplies an empty provider registry for this invocation.
Native credentials remain in place; local model definitions are not edited.
There is no local model, paid API, alternate account, fleet or automatic
continuation fallback.

Each call uses a new neutral private directory, explicit tool restrictions,
disabled hooks and MCP servers, no remote export/control, custom instructions,
BASH_ENV or experimental mode. Configured plugins or extensions that the
wrapper cannot safely exclude cause refusal. These are execution controls
on a trusted host, not an operating-system sandbox or a guarantee about
upstream GitHub behavior. Review any update before widening compatibility.

## Machine-readable delivery

Installed Copilot CLI 1.0.95 help describes `--output-format json` as JSONL,
one JSON object per line. The wrapper keeps `--stream off` and `--silent`,
and adds that format. It does not use rendered text. This source slice stays
on 0.5.17 until a combined bundle is released; it does not assign a new
version.

The contract was read from the installed 1.0.95 executable
(`@github/copilot` 1.0.95, build `f5ba5057`), not from a live model call.
`Han` writes `JSON.stringify(sessionEvent)` plus a line feed. It omits
internal model-log events and a fixed exclusion set that includes
`session.idle`, `assistant.streaming_delta`, `assistant.usage`, permission
events, `system.message` and skill events. After a prompt-mode session,
`Gan` appends one terminal record with `type` `result`, `timestamp`,
`sessionId`, integer `exitCode`, and `usage` (`premiumRequests`,
`totalApiDurationMs`, `sessionDurationMs`, and `codeChanges` of
`linesAdded`, `linesRemoved`, `filesModified`). A blocked run also adds
`outcome` and `blocker`; that shape is not success.

`assistant.message` `data.content` is the full assistant text in the
session-event schema. `assistant.message_delta` is incremental and is not
the completion. User messages, tool results, and subagent events (an
`agentId` or a non-empty `parentToolCallId`) are not the proposal. When a
response is split, `chunkIndex` and `chunkCount` identify the parts; the
adapter concatenates one complete group in index order and inserts nothing
between parts. One other root text message, or more than one such group,
is ambiguous and fails closed.

The raw JSONL stays in the private `native-stdout.jsonl`. `proposal.md` is
written only after the native process exits 0 and the stream proves one
final `result` with `exitCode` 0 plus one unambiguous root completion.
Decoded JSON strings are kept as the model wrote them: escaped newlines,
quotes, backslashes and Unicode become the original characters, with no
rich wrap, markdown strip or JSON repair. Duplicate keys, duplicate event
ids, nonfinite numbers, truncated or CRLF frames, a missing or repeated
result, and a result that is not last all fail as an empty or invalid
response. A nonzero native exit stays `native_failed` and does not become
a proposal. Effective model, AI lab, effort and remaining allowance stay
Unknown; a model name inside an event is not treated as proof.

Native secret redaction still runs inside the CLI before a line is written.
The adapter does not undo it. Visible `parentId` values can point at events
`Han` omitted, so the adapter does not require an unbroken parent chain.

## Limits and receipts

Default task deadline is 15 minutes; up to 2 hours can be selected for a justified
task. Keep the outer Unio deadline above the adapter's deadline plus shutdown
margin. `--max-ai-credits` defaults to 30, the native minimum. This is a soft
session limit, observed after a model response and capable of overshoot;
it neither measures remaining account allowance nor enforces a billing cap.
It does not authorize extra charges. A failed run never starts another route.

Each invocation writes a new private receipt, the raw JSONL transcript,
and, only for a proved completion, `proposal.md`, plus native usage output.
Preserve the actual exit, configured route, task hash and elapsed time.
Effective model, AI lab, effort and remaining allowance stay Unknown
unless separately supported evidence establishes them. Raw answers, usage and
diagnostics may contain task/session data: keep them private. A native usage
file measures that session's consumption, not the account's remaining quota.
The adapter's stdout contains operational metadata, not raw account settings
or proposal text.

## Trial status

On 2026-10-10 the corrected adapter passed seven focused offline checks and
three shipping/discovery checks. A real native Unio corrective task returned a
useful routing/budget documentation draft: Source 0, native 0, adapter 0,
10.958seconds. Native usage reported one user request and model metric label
`gpt-6-luna`. This verifies one text-delivery workflow, not coding quality,
server-proven identity or remaining Free allowance.

Two earlier frozen tasks remain failed and were not replayed. The first caught
incorrect object-valued provider/model lists; the exact native parser requires
arrays. The second caught an explicit medium effort flag unsupported by Auto;
its native usage reported zero user requests, API duration and AI credits.
The lead fixed both compatibility defects before the corrective invocation.
Private original task/config/output receipts remain local. No local model,
authentication or billing change was used to resolve them.

## References checked 2026-10-10

- [GitHub Auto selection and Balance profile](https://docs.github.com/en/copilot/concepts/models/auto-model-selection).
- [Official plans and CLI programmatic availability](https://github.com/features/copilot/plans).
- [Native CLI command reference and tool controls](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference).
- [Provider registry and settings precedence](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-config-dir-reference).
- Installed `copilot --help`, `copilot help config`, `copilot help providers`,
  `copilot help billing` and `copilot help limits` for 1.0.95. Native help says
  the minimum credit limit is 30 and session-wide, with possible overshoot;
  online reference wording differs, so keep the supported version explicit.
