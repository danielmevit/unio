# Read actionable review findings locally

`unio reviews --findings` collects structured findings from recorded reviews of
the exact current work. It makes no provider calls or coordination writes and
works while STOP is set. Human acceptance is always false; the command does
not retry, execute a suggestion, fix code or authorize integration.

**Introduced in Unio 0.5.15.**

## Workflow

After committing and validating a worker's work, run authorized reviews with
`unio review` or `unio review-set`. Those commands use reviewer allowance.
Then browse their already recorded evidence:

```bash
unio reviews worker-a task-a --expect reviewer-a,reviewer-b --findings
unio reviews worker-a task-a --expect reviewer-a,reviewer-b --findings --json
```

Replace these illustrative aliases with the actual worker and reviewers.
`--expect` declares required aliases; it never launches or discovers agents.
Omitting `--findings` preserves the ordinary verdict summary and JSON fields,
which exclude private reviewer prose.

New single and concurrent review material requests exactly one block followed
by the existing single standalone verdict marker:

```unio-findings-v1
{"schema_version":1,"findings":[{"severity":"high","path":"relative/file.py","line":12,"summary":"A concrete issue","detail":"Why it matters and the evidence"}]}
```

```text
VERDICT: REQUEST-CHANGES
```

An explicit `{"schema_version":1,"findings":[]}` block means no structured
findings. Missing, malformed, multiple and oversized blocks are incomplete
evidence. A valid block cannot repair an unknown verdict, failed Source call,
incomplete material or stale review.

## Evidence and grouping

Only successful, fully bound, current receipts with a known recorded verdict
can supply actionable findings. The reader reuses native receipt, path, stream
digest and revision checks. It parses the same stdout bytes it verified and
reobserves stream identities, worker lock and revision after extraction.
Drift or a busy worker makes actionable findings unavailable and `current=false`.

Failed, stale, invalid, unbound and unknown evidence remains visible with its
state and reasons; missing expected aliases remain listed. Historical stale
reviews do not invalidate a complete current set. A current request for changes
survives later approvals. `verdict_disagreement=true` means current recorded
approvals and requests for changes coexist. It does not establish semantic
contradictions, reviewer competence or truth by vote.

Findings group only when all fields are identical after Unicode NFC and text
trimming, including the path. Distinct claims remain separate. Ordering is
deterministic: critical, high, medium, low, info, then path, line and text.
Every source retains its receipt ID, reviewer alias, actual policy group, raw
directory leaf name, stdout SHA-256, block start line and zero-based finding
index. Alias counts and shared-account groups do not prove independent labs;
every view reports `ai_lab_independence="unknown"`.

## Legacy and material compatibility

Old exact schema-1 receipts keep their implicit material protocol 1. Its
generator and hash preserve the original bytes, including the VERDICT footer
and original 300000-byte pre-footer limit. Ordinary `reviews` still recognizes
valid current legacy reviews. The findings view marks them
`unstructured_legacy` with `incomplete=true`, even when old prose resembles a
structured block. It never rewrites the old receipt or raw streams.

New reviews use receipt schema 2 and explicit `material_protocol=2`. Structured
instructions and the unchanged verdict footer are included in the hashed
common material, all within a whole-payload 300000-byte UTF-8 bound. Single
and concurrent reviews use identical complete material. Unknown schema/protocol
combinations are invalid. Currentness uses each receipt's own protocol hash;
a new-protocol size refusal does not invalidate otherwise current legacy
evidence. The findings JSON exposes both hashes in `material_protocols`.

## Limits and privacy

Reviewer prose is untrusted and may contain private information or secrets.
The opt-in findings view shows local excerpts, including summaries and detail.
Check them before sharing. Finding paths, commands and URLs are never opened,
followed or executed. Existing evidence is local unsigned data, not an audit
log protected against a hostile owner.

The reader accepts only exact keys and strict UTF-8 JSON. Duplicate keys,
nonfinite values, unknown keys, excessive nesting (over 16 container levels),
booleans in integer fields and control characters are invalid. Severity must
be one of the five values above. Path and line may be null; otherwise the path
must be a lexical relative POSIX path and line an integer from 1 to 1000000.
Absolute paths, drive-prefixed paths, backslashes, empty components and dot or
parent traversal components are rejected.

Bounds are 16 MiB per raw stream, 64 KiB per receipt, 256 matching folders,
1 MiB per structured block, 32 findings per block and 256 extracted findings
before grouping. Summary, detail and path limits are respectively 1000, 4000
and 512 UTF-8 bytes, checked before and after normalization. Findings text and
JSON output are bounded to 2 MiB, including the final newline.

Any extraction or aggregation overflow is explicit and incomplete. If JSON
serialization exceeds the output bound, finding prose is omitted with
`findings_omitted=true`, `output_overflow` and `incomplete=true`; all evidence
rows, failures, missing aliases and reasons remain. This cannot look like a
complete finding-free review. A failed output write reports `output_failed`
on stderr and exits 2.

## Exit semantics

| Exit | Meaning |
| --- | --- |
| 0 | The existing recorded-review decision is `all_recorded_approved`, every required current review has a valid structured empty array, and no evidence is incomplete; findings decision is `no_structured_findings` |
| 1 | Current structured findings or a current request for changes needs attention; decision is `findings_attention` |
| 2 | Every other incomplete, not-run, invalid, legacy or unsupported state, or output failure |

At exit 1, incompleteness can coexist with attention. Always inspect
`incomplete`, `reasons`, `missing_reviewers` and individual `evidence` rows.
No exit grants human acceptance or permission to execute reviewer suggestions.

See [recorded review receipts](REVIEW-RECEIPTS.md) and
[parallel collection](REVIEW-COLLECTION.md) for review invocation and admission.
