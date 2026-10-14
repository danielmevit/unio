Added an opt-in managed Codex app-server Source and `unio worker-effort`.
The Source uses native admission, owns one assigned turn, streams worker text,
and preserves native failure/cancellation/timeout receipts. Effort requests are
serialized over a bounded private Unix channel and acknowledged by notification
or readback, with pending-next-turn semantics and effective effort Unknown.
Legacy exec defaults and optional adapter discovery remain unchanged. Packaged
helper/usage guide and deterministic installed offline tests make zero AI calls.
