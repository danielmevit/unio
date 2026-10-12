# Local worker experience and selection advice

`unio experience` provides local worker experience records and conditional
selection advice. It records explicit operator assessments of native task
revisions, presents aggregated evidence grouped by worker profile, and combines
that evidence with bounded fleet observations to offer conditional advice for
task assignment.

```bash
unio experience record WORKER TASK --model MODEL --route ROUTE --effort EFFORT --task-type TYPE --outcome OUTCOME [--corrections N] [--project PATH]
unio experience show [--task-type TYPE] [--json] [--project PATH]
unio experience suggest --task-type TYPE [--work-kind implementation|routine] [--json] [--timeout SECONDS] [--project PATH]
```

All commands support `--project PATH` and `--help`; help is usable outside any
workspace. Arguments are strictly validated: duplicate, unknown, or surplus
arguments are rejected with exit code 2 even when `--help` is present.

## Commands

### `record`

Records one final operator assessment of a completed native task revision.
Reads only the fixed `result WORKER TASK` command without running a shell,
provider calls, or configured agents. Running, not-run, stale, failed-snapshot,
mismatched, or unsupported evidence is refused without recording.

- **Outcomes**:
  - `accepted`: Operator reports accepting the candidate. Requires native Source
    exit code 0 and validation state `passed`. Does NOT grant human acceptance,
    merge, review, or publication.
  - `quality_issue`: Operator reports a demonstrated code-quality problem.
  - `operational_failure`: Operator reports transport, authentication, quota,
    or infrastructure failure. Requires a nonzero Source exit.
  - `unaccepted`: Work delivered without reported acceptance. Exit 0 alone is
    never accepted work.
- **Corrections**: Optional operator-reported integer `0..10000`. Missing means
  unknown, not zero.
- **Model**: Operator-reported requested model identifier (bounded ASCII token,
  up to 128 characters; slashes permitted for exact provider model IDs).
- **Route**: One of `codex`, `claude`, `grok`, `antigravity`, `mistral-vibe`,
  `opencode-go`, `opencode-zen-free`, `perplexity-web`, `copilot-auto`, or `unknown`.
- **Effort**: One of `unknown`, `none`, `low`, `medium`, `high`, `xhigh`, `thinking`.

### `show`

Displays stored experience evidence grouped by profile (account alias, requested
model, route, requested effort, and task type). Shows attempt counts, unique
tasks, reported accepted tasks, quality issues, operational failures, unaccepted
attempts, correction burden, and sample age. No universal model score is produced.

### `suggest`

Combines stored evidence with a bounded fleet observation (1..60s deadline, default
10s) into conditional worker selection advice for a given task type.

- **Evidence Threshold**: At least 3 distinct reported accepted tasks in the
  last 90 days are required for an eligible profile to qualify. Older observations
  remain visible but do not count toward this threshold.
- **Route Eligibility**:
  - `implementation` (default): `codex`, `claude`, `grok`, `antigravity`,
    `mistral-vibe`, `opencode-go`.
  - `routine`: Implementation routes plus `opencode-zen-free`, `perplexity-web`,
    `copilot-auto`.
  - `unknown` routes are never eligible.
- **Ordering**: Qualifying profiles are ranked by:
  1. Recent distinct reported accepted tasks (descending)
  2. Observed quality-issue count (ascending)
  3. Complete known correction burden (lower wins; a profile with unknown
     correction counts cannot outrank a fully known zero)
  4. Stable profile identifiers (account alias, model, route, effort)
- **Honest Admission**: Blocked, occupied, off, signed-out, or exhausted agents
  are reported honestly and are never marked recommendable. Unavailable or stale
  authentication remains `unknown` rather than reporting expired signed-in states.

## Storage and Schema Limits

- **Storage Location**: `coord/experience/records/<32hex-id>.json`
- **Lock File**: `coord/experience/lock` (serialized via nonblocking bounded wait)
- **Max Record Bytes**: 65,536 bytes (64 KiB) per record file
- **Max Store Records**: 512 records per workspace
- **Enumeration Bound**: At most 513 entries, allowing one bounded regular
  writer scratch file. Unrecognized hidden files and special files are refused.
- **Max Accepted Examples**: 8 examples displayed per profile
- **Recent Window**: 90 days
- **Record ID**: First 32 hexadecimal characters of SHA-256 over
  `(worker + '\0' + task + '\0' + canonical_json(revision))`
- **Idempotence & Conflicts**: Re-recording an identical revision with the same
  assessment succeeds idempotently. A conflicting assessment for an existing
  revision is refused unchanged with exit code 2.
- **Safety**: Symlink, hardlink, FIFO, and corrupt store paths are strictly
  refused without writing. Reads never create directories or locks.

### Record Schema (schema_version 1)

```json
{
  "schema_version": 1,
  "id": "0123456789abcdef0123456789abcdef",
  "worker": "codex",
  "task": "TASK-1",
  "recorded_at": "2026-10-12T10:00:00.000000+00:00",
  "observed_at": "2026-10-12T09:45:00.000000+00:00",
  "revision": {
    "base_commit": "0123456789abcdef0123456789abcdef01234567",
    "candidate_commit": "89abcdef0123456789abcdef0123456789abcdef",
    "task_sha256": "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789",
    "worktree_sha256": "fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"
  },
  "process": {
    "state": "succeeded",
    "exit_code": 0
  },
  "validation": {
    "state": "passed",
    "scope": "OK",
    "checks_run": 3,
    "checks_failed": 0
  },
  "profile": {
    "model": "openai/gpt-4o",
    "route": "codex",
    "effort": "high",
    "task_type": "implementation"
  },
  "outcome": "accepted",
  "corrections": 0,
  "provenance": {
    "source": "operator_report",
    "effective_model": "unknown",
    "effective_effort": "unknown",
    "human_acceptance": false,
    "independent_review": false
  }
}
```
