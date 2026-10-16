# Failed-run WIP preservation

`unio wip on|off|status` controls an explicit project-local setting in private
`coord/wip.json` (schema 1). Default is off. This is separate from work-policy
schema 1, owner instructions and lead consent. Missing, malformed or unsafe
settings never enable WIP. No installed project setting changes automatically.

Enable it explicitly before dispatch, then inspect the current setting:

```bash
unio wip on
unio wip status
```

When enabled before a run, a nonzero Source exit can produce one scoped WIP
commit after the existing final-failure snapshot and exact owned-provider
quiescence, while the native worker lock and account reservation remain held.
The Source exit stays nonzero, the structured result stays failed, and work
remains unaccepted. There is no extra model call, retry, merge, push or acceptance.
Cleanup Unknown continues holding ownership; silence, heartbeats and timeout
text are not idle proof. No WIP is attempted before exact idle proof.

The first supported state is an ordinary `agent/<worker>` branch with a clean
initial worktree and index. Existing user edits, staging (including partial
staging), merge/rebase/cherry-pick/unmerged/sparse/shallow states, unsafe paths,
secret-looking names, links and special files refuse. Changed files must be
UTF-8 text without NUL bytes. Allowed deletions are supported. Scope must have
one `## Allowed scope` section containing literal relative file paths or
trailing-slash directories; globs currently refuse. Every changed path must be
explicitly covered, including changelog paths. Bounds and full-file safety
checks reuse safe-save observations; failed snapshots never waive WIP checks.

Two full observations and checked staged object IDs reject changing bytes and
Git filters that change content. Only explicit changed paths are staged into
an isolated index. A single normal Git commit runs configured hooks. The
original index is retained on hook/commit failure; edits remain available.
After success the checked index is installed only if the original is unchanged.
Hook/concurrent changes or uncertain completion report Unknown; inspect HEAD,
index and saved state manually. Hooks are trusted Git configuration and can
have their normal side effects. The native lock excludes other native workflows,
not arbitrary unrelated editors; avoid external writers during recovery.

Private dated receipts at `coord/reports/.wip/<native-run-id>.json` bind worker,
task, native attempt, owned session identity, original exit, outcome, revision
and safe relative paths. Outcomes are created, skipped, refused or unknown;
these are preservation outcomes, not adapter stop categories. The run report
shows the revision or actionable refusal plus snapshot and handoff guidance.
Success/clean runs and already committed work produce no duplicate WIP.

Baseline/periodic/final captures retain their existing order. SIGKILL or host
loss can recover only bytes already saved or committed; they cannot guarantee
a final snapshot or WIP commit. This feature is recovery assistance, not release
or lead acceptance.
