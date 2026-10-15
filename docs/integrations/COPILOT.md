# GitHub Copilot Free / Balanced Integration

This document records the exact machine-readable delivery contract and terminal
usage validation for the optional Copilot routine-proposal adapter
(`tools/copilot-worker.py`), updated for the verified native `filesModified`
collection in GitHub Copilot CLI 1.0.95.

For setup and operating limits, see the [Copilot integration guide](GITHUB-COPILOT.md).

## Delivery contract and terminal usage shape

The adapter invokes GitHub Copilot CLI 1.0.95 in non-interactive prompt mode with
`--output-format json` (which emits line-delimited JSONL), `--stream off`, and
`--silent`. Standard output is captured privately to `native-stdout.jsonl`.
The adapter parses each line as a bounded JSON object without rewriting decoded
character contents.

Prompt mode concludes with a single terminal `result` event. The accepted
shape for this terminal record is:

```json
{
  "type": "result",
  "timestamp": "2026-10-15T13:03:25Z",
  "sessionId": "fixture-session",
  "exitCode": 0,
  "usage": {
    "premiumRequests": 1,
    "totalApiDurationMs": 31994,
    "sessionDurationMs": 37936,
    "codeChanges": {
      "linesAdded": 0,
      "linesRemoved": 0,
      "filesModified": []
    }
  }
}
```

### Usage and code changes validation

`require_result` strictly validates the terminal `result` event:
- Top-level keys must equal `{"type", "timestamp", "sessionId", "exitCode", "usage"}`.
- `type` must be `"result"`.
- `timestamp` and `sessionId` must be non-empty identifiers up to 512 characters.
- `exitCode` must be integer `0` for success (a result-level `1` is refused as `empty_or_invalid_response`, adapter exit 2; a nonzero CLI process exit is recorded separately as `native_failed`).
- `usage` must contain exactly `{"premiumRequests", "totalApiDurationMs", "sessionDurationMs", "codeChanges"}`.
- Numeric usage metrics (`premiumRequests`, `totalApiDurationMs`, `sessionDurationMs`) must be finite numbers; these checks do not impose a non-negative range on those three fields.
- `codeChanges` must contain exactly `{"linesAdded", "linesRemoved", "filesModified"}`.
- `linesAdded` and `linesRemoved` must be finite whole numbers (integers `>= 0`).
- `filesModified` must be either:
  1. A JSON array (list) of non-empty strings (`0 < len(entry) <= 512`), including the empty collection `[]` when no files are modified. Only type and length are checked; whitespace and control characters are not path-validated. Values are discarded rather than used as paths. Filesystem existence and authenticity are not checked.
  2. A whole number count (`integer >= 0` and finite), retained for compatibility with earlier adapter fixtures. The inspected native schema uses an array; its separate `filesModifiedCount` key is not accepted by this exact-key contract.

Malformed or wrong-typed values (e.g. `None`, boolean, dictionary, nested non-string array entries or empty strings), non-finite numbers (`NaN`, `Infinity` or exponent overflow), and negative line/count fields fail closed as an `empty_or_invalid_response` (adapter exit 2).

## Inspected native source anchors

The collection contract was statically verified from the locally installed
Copilot CLI package (`@github/copilot` 1.0.95, build `f5ba5057`):

1. **Terminal result generator (`cli-main.js`)**:
   Function `Gan(e, t, n, r, o)` formats the final stream result record:
   `usage` contains `codeChanges: {linesAdded: r.codeChanges.linesAdded, linesRemoved: r.codeChanges.linesRemoved, filesModified: r.codeChanges.filesModified}`.
   `r` is provided by `be.usage.getMetrics()`.
2. **Schema definitions (`schemas/session-events.schema.json`)**:
   - `ShutdownCodeChanges` (lines 19629–19645):
     `linesAdded`: integer `>= 0`.
     `linesRemoved`: integer `>= 0`.
     `filesModified`: `type: "array"`, `items: {"type": "string"}` ("List of file paths that were modified during the session").
   - `UsageMetricsCodeChanges` (lines 24610–24621):
     `filesModifiedCount`: integer `>= 0`.
     `filesModified`: `type: "array"`, `items: {"type": "string"}` ("Distinct file paths modified during the session").
3. **TypeScript declarations (`copilot-sdk/generated/session-events.d.ts`)**:
   Lines 3273 and 3433 explicitly type `filesModified: string[]`.

## Proposal extraction and boundaries

Root assistant proposals are extracted strictly from `assistant.message` events:
- Intermediate root assistant events with empty content (such as preliminary thinking or turnaround notices) are skipped.
- Exactly one non-empty root completion without `toolRequests` must be present on the plain-message path. This path does not enforce a shared `turnId` across other empty messages. Multiple eligible non-empty completions without chunking are rejected as ambiguous; messages carrying tool requests are excluded.
- Chunked messages must have matching group identifiers (`turnId`, `originatingMessageId`) and contiguous chunk indexes (`0..chunkCount-1`).
- Subagent messages (`agentId` or non-empty `parentToolCallId`), user message echoes, deltas (`assistant.message_delta`), and tool outputs are not proposals and are never used as fallbacks.
- Reasoning fields are excluded from `proposal.md` and public adapter output. The verbatim native stream may contain them and remains in the private raw capture (mode 0600); do not publish that capture or credentials.

## Truthful trial status and field evidence

- **Concrete observed failure (2026-10-15)**: Copilot CLI 1.0.95 returned native exit 0, one final result event, and a non-empty assistant proposal, but the previous parser rejected the terminal usage metadata because `codeChanges.filesModified` was `[]` instead of an integer. The adapter exited with code 2 (`empty_or_invalid_response`).
- **No live re-execution or quota claims**: The original failed run was not claimed successful and was not replayed against the live provider. No quota failure is established.
- **Offline verification**: The fix was validated offline against the sanitized actual terminal stream, verified populated collection shapes (`["file.py"]`), invalid entries and types, metadata-only streams, and existing test fixtures.
- **Base commit**: `e66b4844b69374b3ff19078fc72a7c89320b99dd` (Unio 0.5.18 delivery, pending 0.5.19).
- **Execution bounds**: Text proposals only under Balanced routing (`--model auto --auto-tier balance`); the native `view` tool may read local files, while read/write/shell/url/memory tools are denied. The adapter does not execute proposed commands or apply patches. This is trusted-host execution, not an OS sandbox; no automatic paid fallback.
