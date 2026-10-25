# C: versus D: checkpoint-file comparison

Recorded 2026-10-25T12:20:59+01:00. Installed engine: Unio 0.5.24. This is a local filesystem
diagnostic, not a full Unio run, a hardware health assessment or a code change.
No model/worker invocation was used for these measurements.

## Finding

Moving this workspace from D: to C: did not improve the tested small-file
workload. Windows reports both letters as partitions on the same physical
NVMe SSD and reports that device Healthy. Both WSL mounts use 9p/DrvFS.

The results support prioritizing the file-access path and repeated per-file
work. They do not establish a slow physical D: device or prove that one
specific Unio function accounts for all elapsed time. Keep actual saves and
worker exits separate from this component diagnostic.

## Matched sample and method

- Exactly 2048 checkpoint body files, 24748179 bytes (about 25 MB):
  the first 64 name-sorted pool files from each of 32 active checkpoints.
- One stable, read-only source snapshot; identical relative paths, byte sizes
  and SHA-256 values copied to temporary C:, project-local D: and private tmpfs
  fixtures. Each timed read verified the complete selected content manifest.
- Three sequential repeats, with target order rotated C/D/RAM, D/RAM/C,
  RAM/C/D. No concurrent worker or provider run was launched for the experiment.
- Warm/uncontrolled caches and one host; no host cache flushing. Host and
  external workloads were not controlled. Ranges and all raw samples remain
  in the local receipts. These samples are not a universal performance claim.
- Metadata walk/stat, small-file open/read/hash and a same-sized synthetic
  single-file read/hash were measured separately. The synthetic bulk file
  contains identical bytes on all three targets; it is not concatenated
  checkpoint content. Setup/copy times are excluded from read medians.
- Python 3.12.3 through WSL performed the matched comparison.
  File reads were bounded at 32 MiB plus one byte and included guard checks;
  this is not a byte-for-byte implementation of the Unio save validator.

## Median elapsed seconds (three samples)

| Operation | C: through WSL | D: through WSL |
| --- | ---: | ---: |
| Metadata for 2,048 files | 24.421 | 13.008 |
| Read and SHA-256 all 2,048 files | 72.634 | 70.488 |
| Read and SHA-256 one same-sized bulk file | 0.104 | 0.209 |

The small-file read samples were C: 93.462 / 72.634 / 53.985 seconds and
D: 70.488 / 70.793 / 43.995 seconds. The changing timings show why a single
pass should not be treated as a stable ratio. C: was never faster in the
paired small-file read samples in this experiment.

The memory-backed Linux reference median was
0.433 seconds for small-file reads and
0.170 seconds for metadata. This was RAM tmpfs, **not an
ext4 disk measurement**, and it does not predict the result of moving the
workspace into WSL's on-disk filesystem.

## Native Windows control

After the WSL samples completed, Windows PowerShell 5.1.26100.9711 / .NET read and verified
the same retained D: fixture. All file paths, byte totals and individual hashes
matched. Three medians: metadata 0.261 seconds;
small-file read/hash 0.387 seconds.

This control uses different runtime/I/O methods and ran later with uncontrolled
caches. It is useful evidence that these bytes can be handled quickly on the
same device, but it cannot isolate a pure language/bridge multiplier or predict
a native Windows Unio speedup. No full save, provider run, retention operation
or application-level end-to-end comparison was performed.

## Original failed attempt and preservation

The initial full-store snapshot reached its 300-second diagnostic preparation
bound before producing C:/D: timings. Its actual supervisor exit was 1 with a
TimeoutError. It is preserved separately; it is not counted as a completed
benchmark or a failed provider call. The completed experiment uses the smaller,
explicitly defined sample above; it is not a silent retry of identical work.

The sample diagnostic and native control both exited 0. Sampled source metadata
was unchanged. Real saves, Git worktrees, authentication and policy were not
modified. The exact newly created C: fixture was removed after verification;
D: evidence stays local. The private RAM mount ended with its namespace.
No workspace relocation, product source change or global configuration change
was made by this test.

## Next operational work

Keep Unio 0.5.24 installed. Investigate avoidable latest-checkpoint lookup and
periodic-save metadata work on the current helper before changing code. Prove
semantic equivalence for corrupt history, duplicate IDs, archive handling,
ordering/ties and refusals. Full publication/retention byte validation and both
worktree observations remain required. Do not raise deadlines or relocate a
real store based only on this component benchmark.

A separately authorized on-disk Linux fixture would be the useful next storage
comparison. Microsoft recommends keeping projects in WSL's Linux filesystem
when using Linux tools; its guidance supports that direction but does not
replace a local matched measurement: [WSL filesystem guidance](https://learn.microsoft.com/en-us/windows/wsl/filesystems).

## Local evidence

- `tmp/unio-next/drive-comparison-sample-20261025T120407+0100/`: comparison.json,
  observations.jsonl, source-manifest.json, benchmark.py, benchmark-sha256.txt,
  windows-storage.json and windows-native-control.json/script/output.
- Content manifest SHA-256: `8c8d0451b729da77525761be02c40f108714757bc016dfec0f9248173a4aaf12`.
- Original preparation failure:
  `tmp/unio-next/drive-comparison-20261025T115758+0100/`.

Raw bodies, storage identifiers, private paths and logs are not part of the
published Git documentation. These results remain bounded observations.
