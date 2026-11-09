# Build-cache hygiene

`unio cache` is a read-only inventory of likely generated .NET build output in
this workspace's inactive worker worktrees. It works while STOP is set, calls no
provider, and reads metadata only. It has no delete, apply, compact or retention
mode. `--dry-run` is accepted and is always the behavior.

```
unio cache [--dry-run] [--json] [--project PATH]
```

## What is a candidate

A candidate is an immediate `bin` or `obj` directory of a project whose `.csproj`,
`.fsproj` or `.vbproj` is tracked, either in a top-level directory of the worker
or at its root. Arbitrary directories with those names are not discovered. Being
ignored by Git is not treated as evidence that something is disposable.

## What is excluded

Excluded entries appear in the `excluded` list with a reason. The scan does not
enter `_bench`, `benchmarks`, BenchmarkDotNet artifacts, `reports`, `coord`, `.git`,
credential or private artifact names, or VHD/VHDX files.

- **Worker identity:** the worker needs a matching `.unio-worker` marker, an
  `agent/WORKER` branch, and a two-way Git registration in the selected project's
  common Git directory. Unregistered, foreign, locked or copied worktrees are
  excluded. Malformed registration paths (including embedded NUL bytes) exclude
  that worker as `unregistered_worktree`; other workers are still inventoried.
  So is a Git operation in progress.
- **Activity:** a held worker or task lock, a work-policy slot, a native session
  manifest, or a `running` result excludes the worker. A stale `running` result
  with no process is reported as `running_orphan_uncertain`, never as inactive.
  A missing lock, missing result, unreadable record or unknown state is reported
  as `activity_unknown_*`.
- **Cache names:** only exact lowercase `bin`/`obj` directory entries qualify.
  Case aliases such as `Bin`/`Obj` are refused as `case_mismatch`, including on
  Windows/WSL storage. Tracked-path checks use case-insensitive literal matching
  on every platform, regardless of `core.ignorecase`; conservative exclusions
  of distinct case aliases on case-sensitive storage are intentional.
- **Cache contents:** tracked files, symlinks, hardlinked files, mount crossings,
  FIFOs and other special files, protected names, or entries that differ between
  two metadata observations refuse the whole candidate.

Activity and directory identity are checked again just before output.

## Native and unmanaged activity

`inactive_observed` means only that Unio's own records show no activity. A build,
editor, antivirus scan or shell that Unio did not start leaves no such record, so
unmanaged writers are not proven absent. The label is an observation, not deletion
permission.

The lock probe holds a nonblocking lock for an instant, as native status does. A
worker starting at that exact instant could report that it is busy.

## Reading the sizes

`logical_bytes` and `allocated_bytes` describe probable generated regular files.
They are not reclaimable capacity. `allocated_bytes` is null where the filesystem
does not report allocation. A candidate that could not be fully measured has the
status `partial` and null sizes; it is never reported as zero or complete.

## Bounds and partial results

Each run is limited to 1024 worktrees, 4096 candidates, 100000 distinct entries
and 30 seconds. Git calls are bounded in time and output. The confirming second
observation revisits only entries already counted. When a bound runs out, `partial`
is true and the unscanned work is listed as excluded.

A partial inventory exits 0, but it does not establish safety or completeness. A
blocking filesystem call on a hung mount cannot be interrupted by these checks.
On slow WSL `/mnt` paths with hundreds of workers, the time limit can be reached.

Exit codes: 0 for an inventory, including a partial one; 2 for invalid input or an
unsafe or unidentifiable workspace.

## JSON

`schema_version` is 1. The document has `observed_at`, `dry_run` (always true),
`partial`, `partial_reasons`, `stop_active`, `totals`, `candidates` and `excluded`.
Each candidate has a project-relative `path`, `worker`, `kind`, `logical_bytes`,
`allocated_bytes` and `status`. Each excluded entry has `path`, `worker` and `reason`.

## WSL and the host disk

Deleting files inside WSL frees blocks in the ext4 filesystem. It does not by itself
shrink a non-sparse VHDX on the Windows host, so the host drive may show no more free
space. Linux `df` does not report host free space either. Unio does not shut down WSL
or compact a disk. See Microsoft's
[WSL disk space](https://learn.microsoft.com/en-us/windows/wsl/disk-space) guide.
