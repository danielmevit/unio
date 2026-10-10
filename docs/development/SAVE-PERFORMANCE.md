# Save Performance Benchmark

## Running the Probe

The `save-benchmark.py` probe builds a private Git fixture to measure `unio save create` performance without modifying any real project state or saves. It measures isolated worker performance, bounds execution times, and reports results in schema-1 JSON.

### On ordinary workspace-mounted scratch

To run the probe on a standard disk-backed scratch directory (e.g., inside the workspace `tmp/`):

```sh
python3 -B tools/save-benchmark.py \
    --engine /path/to/bin/unio \
    --scratch tmp \
    --workspace save-benchmark-disk
```

### On workspace-local tmpfs

To measure performance without disk I/O overhead, create a user-owned tmpfs and use it as the scratch directory:

```sh
# Create a local mount point
mkdir -p tmp/ramdisk

# Mount a user-owned tmpfs (requires appropriate permissions or sudo)
sudo mount -t tmpfs -o size=256M,uid=$(id -u),gid=$(id -g) tmpfs tmp/ramdisk

# Run the benchmark
python3 -B tools/save-benchmark.py \
    --engine /path/to/bin/unio \
    --scratch tmp/ramdisk \
    --workspace save-benchmark-tmpfs
```

## Observations (0.5.9)

### Facts
- A probe ran on `Unio 0.5.9` using a `v9fs` (9p) workspace-mounted scratch directory.
- `unio save create` duration over three attempts was observed at `~8.19s`, `~8.21s`, and `~6.27s`.
- `unio save inspect --worker <w> --json` executed in `~3.10s`.
- `unio watch --once --json` executed in `~0.18s`.
- `unio save usage` is officially unsupported on `0.5.9` (exits with code 2).

### Interpretations
- The save creation process on 0.5.9 is heavily influenced by filesystem I/O performance. The `v9fs` file system used during observation might amplify the time taken to clone worker states and write save manifests compared to a native local filesystem.
- Running the same probe on a `tmpfs` RAM disk would likely drastically decrease the save creation time by eliminating storage subsystem latency.
- Future engine enhancements could optimize the storage layer or parallelize worker snapshotting to reduce save times.
