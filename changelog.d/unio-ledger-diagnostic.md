UNIO-LEDGER-DIAGNOSTIC: actionable, fail-closed diagnostics when a damaged
Source ledger journal blocks verification. An operator-driven verification of
an exact previously committed change had no new Source; `unio verify` failed
with the opaque `unio quality: Expecting value: line 1 column 1 (char 0)`
because the `dispatch_sha` helper stopped while reading the older
`coord/reports/ledger.jsonl`, which contains one invalid JSON line at physical
row 241. That was a real runtime error surfaced with no location, no journal
name and no safe next step.

The ledger scan in `dispatch_sha` (unio-install.sh, QUALITY_PY) now reports a
read-only diagnostic before failing closed. Each ledger row is numbered by
physical position; a row that is not decodable text, is not valid JSON, or is
valid JSON but not an object record fails with the project-relative journal
(`coord/reports/ledger.jsonl`), the exact physical row number, a short
inspection hint, and the standing rule that ledger history is never skipped,
repaired or rewritten. The row's contents are never echoed into the error, so
no task, worker, run id or payload leaks into logs. The check remains
fail-closed: a damaged ledger still refuses to fabricate a dispatch binding,
and nothing about the ledger is skipped, repaired, rotated, deleted or
rewritten.

Semantics are unchanged everywhere else. A healthy journal (including run
records for other tasks) still yields no binding under no-provider semantics;
a valid record that proves a Source existed still refuses legacy manual
verification without bound dispatch evidence; retained retry state, foreign
results and legacy run reports keep their existing refusals; a persisted
result with a bound dispatch revision still returns its task SHA without
reading the ledger at all.

Offline regression coverage lives in `tests/unio-ledger-diagnostic.py`: a
selected-function harness against the actual installed engine text plus one
end-to-end replay of the exact `quality dispatch-sha` invocation. It
demonstrates valid history, invalid syntax midfile, valid JSON non-object,
undecodable bytes and actual Source evidence, and asserts for every case that
the error names the journal and exact physical row with safe actionable
wording, that the row's contents stay hidden, that the fixture ledger is
byte-identical afterwards (zero mutation), and that zero provider launches
occur (any subprocess use inside the harness aborts the test). All fixture
rows are synthetic; no real ledger row content is used.
