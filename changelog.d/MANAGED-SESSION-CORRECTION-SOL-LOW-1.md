# Managed-session bounded correction

- Retain app-server leader ownership through process-group cleanup, including
  provider EOF, natural failure, cancellation and leader-first exit; reap only
  after the last intended signal.
- Bound transcript records, archive bytes and output pages; report corruption,
  torn tails, unsupported records and archive truncation without silently
  skipping output or changing the provider's successful outcome.
- Cache and archive steering intent before RPC, validate the acknowledged turn,
  distinguish rejection from uncertain delivery, and preserve acceptance after
  post-ack archive errors. Duplicate IDs never silently replay an RPC.
- Validate archive/latest/native identity consistently, retain Unknown stale
  outcomes, read input through checked descriptors, support full 8 KiB UTF-8
  wire framing, and delay archive mutation until startup authorization and the
  exclusive native claim succeed.
- Add zero-provider fake-server/native and boundary regressions. The original
  Gemini implementation remains preserved. Focused checks and baseline failures
  are recorded privately; independent reviews, integrated fullgate and lead
  acceptance remain separate and pending.
