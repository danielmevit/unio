# Interactive AI session workspace

Design direction discussed with the owner on 2026-10-11; implementation is
planned. The owner is independently finishing dashboard and website details
with Opus. This document does not authorize replacing that delivered design.

Unio should let an owner move from an agent's task card to its actual live
CLI session, send input and return to its files, checks and reviews. Keep the
current dashboard as the shared interface, with a future Sessions view and
an optional desktop window around it.

## One engine, several entry points

The CLI, local browser and any future desktop app should use the same task
identities, account slots, saves and authority. A desktop app is an entry point
to Unio, not a second scheduler with conflicting state. Keep the visual work
map as the overview and the session view as a place to inspect and interact.

Native macOS/Windows execution is the separate
[cross-platform milestone](CROSS-PLATFORM.md). A native desktop window does
not itself port Linux worker execution. Conversely, native worker execution
does not require a new desktop design.

## Build in stages

1. **Managed interactive sessions:** launch an eligible AI CLI through Unio
   with an owned pseudoterminal, stable session identity and explicit lifecycle.
   Record worker/task ownership and shared-account admission. Headless task
   runs remain available. Do not claim arbitrary already-open terminals are
   automatically captured or attached.
2. **A session view in the existing dashboard:** select a session, follow its
   output, resize its terminal and send deliberately authorized input. Link to
   the same task, worktree, files, checks and reviews. Keep output observation
   separate from permission to type, approve, stop or launch work.
3. **Cross-platform terminal backends:** use appropriate POSIX/macOS and native
   Windows terminal/process facilities. Test input, resizing, Unicode, process
   exit, reconnect and owned-child cleanup on actual supported hosts.
4. **Optional desktop packaging:** reuse the established web interface and
   engine. Choose a desktop shell only after the managed-session contract
   works; do not commit to Electron or Tauri merely to obtain an app window.
5. **Scoped remote access:** build on session ownership and the
   [phone-pairing plan](MOBILE-SESSION-COMPANION.md). Pair with one selected
   session using revocable grants, rather than exposing the entire machine.

## Acceptance

An owner can launch a managed session, see which task and account it belongs
to, interact with that exact session and reconnect without starting a second
worker. Session termination releases its slot once and preserves available
work/saves. STOP continues to block new work under its existing meaning.

Browser authentication, origin checks and explicit input grants must protect
the terminal endpoint. Read-only dashboard access must not become shell access.
The local server remains loopback by default. Reconnecting does not authorize
a new task, an automatic retry or an extra low-tier account session.

The [Pane project](https://github.com/greenfield-inc/Pane) is an experience
reference for managing live CLI agents across sessions. This is a product
direction comparison, not a decision to copy its code or adopt its architecture.
Unio's implementation should connect those sessions to its existing recovery,
shared-account limits, delegation and independent review workflow.
