# Unio 0.5.15 — review findings in one place

Read the actionable findings from independent reviews together, while keeping
who reported each issue and the evidence that still needs attention.

```bash
unio reviews WORKER TASK --expect REVIEWER_A,REVIEWER_B --findings
unio reviews WORKER TASK --findings --json
```

These commands browse local recorded evidence and work with STOP set. They
make no AI calls. Identical normalized findings group together with every
source citation retained; similar claims and recorded verdict disagreement
stay separate. Agreement is not proof of correctness or independent AI labs.
Human acceptance remains false.

New reviews request a bounded `unio-findings-v1` block within the hashed review
material. Exact historical protocol-1 receipts remain valid in the ordinary
review summary and explicitly unstructured/incomplete in the findings view.
Missing, malformed, failed, stale and overflowing evidence never means that
no issues were found. Paths and text are untrusted and never executed or opened.
Review excerpts may contain private information; check before sharing.

Exit 0 requires current recorded approvals with valid empty structured findings
and complete required evidence. Exit 1 means findings or recorded changes need
attention, retaining any incompleteness. Other incomplete/unsupported states
return 2. See the [complete workflow and bounds](REVIEW-FINDINGS.md).

## Validation and scope

Focused installed offline checks cover findings extraction, source attribution,
legacy compatibility, complete material hashes, strict schema/bounds, replacement
and revision races, STOP and read-only browsing: 19 findings methods, 9 receipt
methods and 6 concurrent-collection methods passed. Release delivery requires
one full frozen-source repository gate, exact artifacts, isolated upgrade/restore,
installation before publication, installed mock acceptance and official download
hash checks. Actual release results are recorded in the development handoff.

The [dated worker-readiness report](development/WORKER-READINESS-2026-10-13.md)
preserves 20 calls, 14 exact responses and the original failures without treating
tiny diagnostics as model rankings. The initial Mistral/Vibe GLM implementation
hit its per-run token cap; a dedicated ChatGPT/Codex Sol high worker completed
the preserved draft. Provider delivery and lead acceptance stay separate.

[Mid-run worker effort control](development/WORKER-EFFORT-CONTROL.md) is planned
for a later milestone. Dashboard, website and brand payloads are unchanged.
