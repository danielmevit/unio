# Required delivery — explicit artifact contract (0.5.23 unreleased)

This opt-in P1 contract observes explicit text artifacts. It does not establish
provider identity, effective reasoning effort, lead acceptance, or human approval.
Tasks without a declaration retain their existing behavior and gates.

## Declaration

Use exactly one section with one plain portable relative path per line:

```markdown
## Required artifacts
report.txt
summary.md
data/results.json
```

Blank lines and comment lines beginning with `#` are ignored; fenced examples
are ignored. Empty, duplicate, malformed and unsafe declarations refuse before
Source invocation. There are at most 32 names, each at most 128 characters.
Components begin with an ASCII alphanumeric character and otherwise contain only
ASCII alphanumerics, dots, underscores and hyphens. Traversal, hidden components,
Windows device names and trailing dots are refused. Names must be distinct even
without case, and no name may be another name's directory prefix.
`binding.json` and `prompt.md` at the delivery root, including their directory
prefixes and case variants, are reserved for engine metadata. Metadata never
satisfies required output.

## Dispatch and environment

The engine exclusively creates a fresh private per-run directory. Precreated
or populated delivery destinations are refused. Only declared artifacts in that
directory are observed; ignored repository files are not globally captured.

Source and a later, separate `verify` receive:

- `UNIO_DELIVERY_DIR`: the current run's delivery directory.
- `UNIO_DELIVERY_BINDING`: its immutable `binding.json` path.

Both values are cleared for undeclared tasks, including inherited values.
Validation commands may read the current artifacts; changing observed output
invalidates it. Source must create nested artifact directories itself.

The engine writes a read-only dispatch binding and prompt using exclusive,
non-following opens. It never rewrites them at finalization. The binding records
task, worker, run, command and prompt hashes, declared paths, dispatch revision,
and directory identity. The dispatch revision includes the original task hash.
The result additionally records binding hash, metadata identities, artifact
hashes and identities, counts and missing paths. Optional delivery evidence
extends result schema 1; undeclared legacy documents need no delivery field.
Incomplete or malformed declared evidence cannot establish completeness.

## Observation and freshness

Artifacts must be nonempty UTF-8 text without NUL, regular files owned by the
current UID with exactly one hard link. Every path component is walked with
non-following directory descriptors. Symlinks (including ancestor symlinks),
FIFOs, devices, sockets, directories and hardlinks cannot become delivered files.
Reads are nonblocking and bounded to 262144 bytes per artifact; 32 artifacts
bound the total artifact content to 8 MiB. Prompt reads are bounded to 1 MiB.
The contract does not require worker file mode 0600.

The engine detects inode/path replacement and size/time changes during reads.
It records file identity and hashes at Source completion, then rechecks current
bytes and identity on result, verify, review material and handoff. It also
rechecks immutable metadata, task declaration/hash, current Source command,
dispatch binding, Source revision, and any declared outcome's run, binding,
prompt and available report provenance. Evidence is never upgraded by dropping
a hash or by writing a missing artifact after Source completion.

Malformed delivery fields/types, counts, paths, hashes or identities refuse
before evidence paths are used. Observational failures are reported in
`delivery_current`; delivery readiness remains false. These observations do not
write through artifact paths or convert arbitrary metadata into coordination
paths.

## States and exits

- `complete`: successful Source with every declared artifact safely observed.
- `incomplete`: missing/unsafe output or a nonzero/timeout Source. Bounded partial
  output is retained with exact observed hashes and count.
- `stale`: previously observed evidence changed, disappeared, or no longer binds
  the current task/run/command/revision. A new dispatch is required.
- Undeclared: delivery evidence is absent; legacy behavior applies.

A missing artifact does not change the actual Source exit. Source 0 remains 0
in process evidence and the native run exit; `verify` fails the required contract
independently and reports the delivery reason. Nonzero and timeout Source exits
remain their original exits. Delivery failure is not a provider failure.
Adapter outcomes and provider-limit observations remain separate; facts not
exported by a route remain Unknown.

## Review and handoff

Review material contains complete artifact bytes, saved dispatch binding/prompt
bytes and delivery provenance, with repeated freshness checks. The existing
300000-byte complete review payload limit refuses oversized material before a
reviewer invocation; content is never clipped. Handoff copies bounded observed
artifacts plus metadata and result state, or refuses. Report-only handoffs also
retain the existing complete report bound and can refuse incomplete delivery.
An incomplete partial packet must retain its incomplete state.

Report-only tasks still require their existing nonempty native report and no
repository changes. Implementation tasks retain commit, no-op and empty-work
gates. Current review projection and reviewer configuration freshness remain
required. Delivery adds no semantic prose checking, retries, automatic approval
or acceptance. Lead acceptance remains Unknown/not recorded and human pending
until separately recorded by their authorities.

## Validation

`tests/unio-required-delivery.py` installs only private mock engines and is
included in `tools/quality-check.sh`. Fixtures use supplied `TMPDIR` or project
`tmp`; subprocess calls have parent time bounds. No inference calls are needed.
Regressions cover reserved metadata, nested symlinks and unsafe types, immutable
binding/prompt and schema drift, complete/missing/partial output, timeout exits,
post-run mutation/disappearance, fresh-run isolation, separate verify environments,
and complete reviewer/handoff bytes or bounded refusal. Check the correction
receipt for actual executed checks and remaining limitations.
