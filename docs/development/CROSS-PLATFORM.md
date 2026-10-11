# Run Unio on macOS and Windows

Owner-requested milestone, 2026-10-11. This is a delivery plan, not a claim
that the current release runs natively on every platform. Release numbers
remain unassigned; continue the existing 0.5.x sequence.

| Host | Current support | Target |
| --- | --- | --- |
| Linux | Current CLI/runtime baseline | Preserve the working installation and recovery workflow. |
| Windows through WSL | Uses the Linux runtime | Make WSL2 setup, paths and browser startup reproducible. |
| macOS | Not supported yet | Native runtime on Apple Silicon and Intel, with actual host checks. |
| Windows without WSL | Not supported yet | Native installation and execution from PowerShell, after a backend feasibility checkpoint. |

One engine should serve the CLI and the existing dashboard. A desktop window
can eventually host the same interface. Native platform support does not
require replacing the dashboard or building a second orchestration system.
The separate [interactive session workspace](SESSION-WORKSPACE.md) covers live
AI terminals and a possible desktop shell.

## 1. Audit the runtime and define platform contracts

Map platform assumptions to their callers before replacing commands. The
[installer/runtime](../../unio-install.sh) uses Linux utilities and process
facilities; simply adding Windows or macOS to a CI matrix is insufficient.

| Area | Current examples to audit | Required behavior |
| --- | --- | --- |
| Shell and installation | Bash features, GNU `stat -c`, `readlink -f`, `timeout`, completion locations | Detect prerequisites and preserve configured paths and owner files. |
| Ownership and locking | Shell `flock`, Python `fcntl`, inherited worker locks | Exactly one admitted workflow per shared-account slot; no concurrent save writers. |
| Processes and recovery | `setsid`, POSIX groups, signals, `/proc` identity/boot observations | Stop only owned children; detect stale processes; preserve cooldown ownership. |
| Worktree and queue access | Descriptor-relative paths, `/proc/self/fd` access in some readers | Read the intended object without following an unsafe replacement. |
| Snapshots and storage | `dir_fd`, `O_NOFOLLOW`, atomic renames, permissions and Git modes | Refuse unsupported states and retain the last good save on failure. |
| Agent integrations | Host-installed CLIs, command quoting and native authentication | Discover actual host capabilities; never copy another machine's credentials. |

These examples identify audit targets, not a claim that every helper uses
every facility. Keep platform-specific code behind a small, explicit host
interface where practical. Native Windows may require substantial changes
to the Bash-led engine; record that feasibility decision before promising a
thin compatibility wrapper.

Finish this stage with a file/function inventory, supported-host checks and
shared offline contracts. Missing capabilities must explain what cannot run;
they must not silently disable locking, ownership checks or recovery validation.

## 2. Make Windows through WSL easy to set up

Document a clean WSL2 installation, Linux prerequisites, where commands run
and how Windows users open the returned loopback dashboard URL. Test paths
with spaces and Unicode. Compare the Linux filesystem with Windows-mounted
project paths before recommending a performance-sensitive storage location.
Do not label WSL execution as native Windows execution.

Finish when the documented setup can initialize a project, run an offline
mock task, stop its owned children, and save/restore its work. Record browser
startup and any filesystem limitations from the actual machine.

## 3. Port and verify native macOS

Implement the audited host operations on macOS. Decide and document actual
shell/tool prerequisites; installing one missing Linux utility alone does
not establish compatibility. Exercise both Apple Silicon and Intel using
actual hosts or suitable CI runners.

Finish when installation, shared-account admission, interrupted runs, child
cleanup, saves/restores and local dashboard startup pass on each declared
architecture. Unverified architectures and versions stay explicitly unverified.

## 4. Implement native Windows after the feasibility checkpoint

The user should be able to install Unio, open PowerShell and launch workers
using their Windows-installed AI CLIs without WSL. Preserve the same task,
review, work-mode and subscription-tier semantics.

Choose intentional Windows equivalents for file locking, atomic writes,
process ownership, permissions and safe restore. Windows Job Objects are a
candidate for owned process-tree management; interactive terminals would
also need a host-appropriate terminal backend. Validate the chosen behavior
rather than translating Bash flags mechanically. The feasibility checkpoint
must identify any required engine refactor and deliverable sub-slices.

Finish with actual Windows installation and execution evidence. A browser
opening successfully or a Linux test suite passing is not native support.

## Acceptance shared by supported hosts

- Run installation and mock workflows without AI accounts or paid calls.
- Verify paths with spaces and Unicode, case collisions and executable modes.
- Race concurrent admissions/locks and refuse an occupied shared budget.
- Interrupt a worker and confirm only its owned process tree is terminated.
- Save and restore committed, staged, unstaged, untracked and deleted work.
- Preserve corrupt history, claims and previous good saves; keep secret-name
  and unsupported-state refusals. Document unsupported host filesystem cases.
- Start/reuse/stop the loopback dashboard without exposing a general terminal
  or binding a public interface by default.
- Verify release installation and upgrade behavior on every declared host.

Run these contracts in appropriate cross-platform CI and retain per-host
release smoke evidence. Genuine provider calls are a separate, explicitly
authorized check against an available account. A model's availability,
authentication and allowance on one host do not establish them on another.

## References and scope

[Microsoft's WSL setup](https://learn.microsoft.com/en-us/windows/wsl/install)
describes the existing Windows compatibility route.
[Windows Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects)
describe a possible native process-management primitive.
[GitHub runner availability](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
and [workflow shells](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax)
help choose actual test environments. These sources do not certify Unio support.

This milestone adds host compatibility. Packaging, an interactive session UI
and phone access have their own contracts. Existing dashboard/site work remains
with the owner's separate Opus session; this plan introduces no visual changes.
