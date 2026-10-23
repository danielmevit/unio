# Bounded unreviewed result observation

Defer review-only material/configuration work until a valid own receipt or
collection needs freshness verification. Keep unbound/corrupt history visible,
malformed bound evidence unresolved, and unreviewed results not ready. Reviewed
evidence retains fresh per-call hashes and closing mutation checks. No consumer
deadline, policy, admission or helper timeout changes.

Installed deterministic regression fails on ae2521c (four subcases) and passes
on the correction: no folders, unbound history, malformed receipt and collection.
Full focused checks and actual receipts are recorded outside the source checkout
in result-observation-sol-low-20261023; lead acceptance and real /mnt/d comparison
remain pending. This is no general performance or token-savings claim.

Additional installed coverage checks busy unreviewed workers, fresh material
observation on each reviewed call, and actual Source exits 0/7 with complete or
incomplete delivery. Test-development failures (an overbroad sentinel and an
incorrect complete-delivery expectation for failed Source) are preserved in the
external receipts; neither was a production-code correction.

The first full findings run exposed a compatibility regression: explicit
`reviews --findings` needs material hashes even before a receipt exists for
protocol-size diagnostics. Deferred work is now limited to result projection;
explicit review browsing retains eager material/hash observation. The original
19-test run (one failure) is preserved, with final checks recorded separately.
