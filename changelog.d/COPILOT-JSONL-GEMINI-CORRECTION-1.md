### Fixed

- Hardened Copilot CLI 1.0.95 JSONL parser against three demonstrated decoder defects:
  - `require_assistant` verifies `isinstance(event["id"], str)` before regex matching,
    ensuring wrong-typed event IDs (null, int, list, dict) fail closed with
    the adapter's fixed `empty_or_invalid_response` refusal instead of an unhandled `TypeError`.
  - `finite_number` catches `OverflowError` from large integers exceeding floating-point
    range (e.g. `10**400`), ensuring out-of-range usage metadata fails closed as an
    invalid response while ordinary finite usage metadata and large integers in proposal
    content remain supported.
  - `completion_text` and `require_assistant` validate group identifiers (`turnId` and
    `originatingMessageId`) for valid identifier shape and reject explicit conflicting
    group identifiers across chunks, preserving exact byte concatenation for a coherent
    complete group while keeping absent optional fields compatible.
