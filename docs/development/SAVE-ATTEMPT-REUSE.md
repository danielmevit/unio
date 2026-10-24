# Successful save-attempt metadata reuse

Retention optionally collects ephemeral metadata candidates while deep-loading every
active save. A deep failure gets a metadata-only fallback solely for last-good
eligibility; retention still treats it as protected corrupt evidence. Valid archive
metadata is included only after the existing corruption, duplicate, pin and cap
checks pass. Moving saves into the archive preserves their IDs and ordering.

After validated atomic publication, publish adds the new manifest and chooses by
(publication time, ID), never assuming the new save is newest. Successful attempt
writing happens before the same saves lock is released. There is no persistent
cache. Refusals and publication faults use the original fresh lookup. Attempt I/O
failure remains nonfatal. Both observations and all deep validation remain.

Installed regression instrumentation asserts one deep load and zero metadata-only
loads for ordinary valid history, no successful last_good traversal, and equivalent
metadata identity for future/tied timestamps and body-corrupt history. The existing
performance, retention and work-saving suites cover exact restore, descriptors,
pins, caps, stable bytes and interrupted archival. No timing threshold or global
speedup claim is made; this does not establish a cure for all 60-second timeouts.
