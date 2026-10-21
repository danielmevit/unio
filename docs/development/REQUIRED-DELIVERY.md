# Required delivery — explicit artifact contract (Unio 0.5.23)

Status: P1 candidate for Unio 0.5.23; additive opt-in contract, no change to legacy behavior.

## Overview

An optional `## Required artifacts` section in a task file declares an explicit
delivery contract: a bounded set of text artifacts that must be present for the
delivery to be considered complete. This is an opt-in enhancement that preserves
existing behavior for tasks without this declaration.

The contract is strictly additive: it does not modify Source exit semantics,
provider outcomes, or acceptance authority. A Source that exits zero without
declared artifacts yields an incomplete delivery, clearly visible in result and
report, never accepted or ready. Required-artifact validation and human acceptance
remain separate facts.

## Declaration

A `## Required artifacts` section contains a list of portable relative logical
names, one per line. Each name must be a valid identifier (alphanumeric, hyphen,
underscore, dot; 1–128 characters). Empty lines and lines starting with `#` are
ignored. Duplicate names are refused before any provider call.

Example:

```markdown
## Required artifacts
report.txt
summary.md
data/results.json
```

## Contract

- **Opt-in only**: Tasks without a `## Required artifacts` section retain exact
  legacy behavior with Unknown/undeclared delivery.
- **Bounded metadata**: Artifact names are validated before any provider call;
  malformed, duplicate, or unsafe metadata refuses early.
- **Engine-owned directory**: A fresh per-run private delivery directory is created
  and exposed to authorized Source via the `UNIO_DELIVERY_DIR` environment variable.
  This directory is bound to the exact task/worker/run/dispatch command and revision.
- **Text artifacts only**: For this P1, only regular UTF-8 text files are supported.
  Binary assets are deferred to follow-up.
- **Strict bounds**: Each artifact is validated as a regular file with:
  - Maximum size: 262144 bytes (256 KiB)
  - No symlinks, FIFOs, hardlinks, or path traversal
  - UTF-8 encoding
  - Single linkage (nlink == 1)
  - Owned by current UID with mode 0600
- **Count bounds**: Maximum 32 declared artifacts per task.
- **No fabrication**: Missing data is never fabricated; incomplete delivery is
  explicitly visible.

## Lifecycle

1. **Prepare**: Before Source invocation, the engine creates a fresh private
   delivery directory and validates the declared artifact metadata. Any
   validation failure refuses before the provider call.
2. **Source execution**: The Source receives `UNIO_DELIVERY_DIR` and may write
   artifacts to this directory. The Source must create files directly; the engine
   does not interpret stdout or arbitrary paths.
3. **Observation**: After Source exit, the engine validates that all declared
   artifacts exist in the delivery directory with correct bounds. Partial
   artifacts are preserved; nonzero/timeout exits retain original failure evidence.
4. **Verification**: The `verify` command checks artifact presence, bounds, and
   hash consistency against the binding. Artifact mutation/disappearance makes
   delivery stale/incomplete.
5. **Review/Handoff**: Complete bounded artifacts and provenance are included in
   reviewer material or the handoff refuses bounds. No clipping occurs.

## Environment

- `UNIO_DELIVERY_DIR`: Engine-created current run directory for artifacts.
  Exposed to Source and validation. Read-only for observation/validation.
- `UNIO_DELIVERY_BINDING`: Path to the binding.json for the current run.
  Contains task/worker/run/command/revision hashes for verification.

## Validation rules

- **Binding validation**: Artifacts are bound to exact task/worker/run/dispatch
  command and revision. Hash drift or tampering makes delivery stale.
- **Source exit preservation**: Actual Source exit is preserved; nonzero exits
  retain original reason with partial artifacts counted but not complete.
- **Adapter evidence separation**: Source/adapter/timeout/provider-limit evidence
  must be distinct. Unknown for unexported/custom routes.
- **No provider calls from validation**: Observation and validation perform no
  provider calls; they only inspect the engine-owned delivery directory.
- **No shell evaluation**: Declarations are parsed as structured metadata; no
  arbitrary shell evaluation is performed.

## Outcomes

- **Complete**: All declared artifacts present with valid bounds and matching
  hashes. Delivery state is "complete" but not automatically "ready" or "accepted".
- **Incomplete**: Any declared artifact missing, oversized, or invalid. Delivery
  state is "incomplete". Source exit zero with incomplete delivery is not ready.
- **Stale**: Artifact mutation, disappearance, or binding drift after verification.
  Delivery state becomes "stale".
- **Unknown**: No declaration (legacy), malformed metadata, or validation failure.
  Delivery state is "Unknown/undeclared".

## Compatibility

- **Legacy tasks**: Tasks without `## Required artifacts` have delivery state
  "Unknown/undeclared" and retain exact existing behavior.
- **Report-only tasks**: A report-only task with required artifacts must still
  supply a nonempty bounded UTF-8 report via the engine channel. Required artifacts
  are additional; the report channel is separate.
- **Implementation tasks**: Implementation tasks may declare required artifacts
  in addition to code changes. The repository must remain unchanged for report-only
  verification; implementation tasks follow their existing commit gates.
- **Empty work refusal**: The existing empty_work refusal remains correct and
  unchanged. Nonempty acknowledgement stdout is not proof of required artifacts.

## Security

- **No path traversal**: Artifact names are validated as safe relative paths;
  absolute paths, `..`, and symlinks are refused.
- **No arbitrary writes**: The delivery directory is created fresh with mode 0700;
  only the Source (running as the same UID) may write to it.
- **No privilege escalation**: All operations use current UID with no effective
  capabilities. Ordinary UID/no effective caps.
- **No global state**: The delivery directory is per-run and private; it does
  not affect repository contents or global ignored-file capture.

## Testing

Tests cover:
- Installed fake Source0 acknowledgement with missing file => process succeeded
  and delivery incomplete, not ready
- Real complete artifact + explicit validation
- Source nonzero/timeout retains original reason with partial artifacts
- Legacy/report-only/implementation no-op unchanged
- Invalid metadata refuses before call
- Artifact/task/revision/command drift and tamper
- Path/type/bounds validation
- Separate verify exposes current artifact env
- Review/handoff complete/hash-bound or refuse

## Implementation notes

- The smallest compatible design is chosen: explicit per-run text artifact
  directory with strict metadata validation.
- No general binary asset backups or globally captured ignored files.
- Validation can inspect the delivery directory by the documented
  `UNIO_DELIVERY_DIR` variable bound to current run.
- A strict structured observer in canonical `tools/adapter-outcome.py` is within
  scope for exposing existing actual adapter evidence.
- Optional budget telemetry and old schemas are preserved.
