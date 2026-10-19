# Windows app trial enforcement

Owner requirement recorded 2026-10-19T21:26:05+02:00. This belongs to the native Windows/Store
milestone; no trial restriction is implemented in the current Linux/WSL tool.

## Problem and intended behavior

The owner observed a Store-configured one-day trial remaining usable after
24 hours. This is a reported integration failure, not a verified claim that
all Microsoft Store trials are broken. Build Unio-managed trial state and
expiry enforcement; a Store trial flag alone must not keep access enabled.
The initial target is24 hours from first valid activation, with an explicit
expiry timestamp and remaining-time display.

After expiry, refuse new trial-restricted actions at the Windows backend
boundary as well as the UI. Closing/reopening the app must not restart the
trial. Restore normal access when a valid entitlement is established. Define
which Windows-app capabilities are trial-restricted before implementation;
this plan does not change the existing open-source CLI or its license terms.

## Preserve the user's work

Expiry must preserve projects, files, logs and provider sessions. Block new
work and new instructions while keeping read/export, stop, save and handoff
available. Do not kill active writers to enforce a sales restriction. State
clearly whether an already-started run may finish and show the expired state;
continued unrestricted use after the deadline is not acceptable.

## Design and acceptance

- Record activation and expiry independently of UI state and the Store's
  displayed trial status; make all privileged actions check the same decision.
- Define trusted time, clock rollback, offline access and unavailable licensing
  service behavior. Local timestamps alone cannot guarantee tamper resistance.
  Evaluate a verifiable activation/entitlement record; do not silently add a
  paid service, device fingerprinting or undisclosed network dependency.
- Persist the decision across restart, upgrade and repair. Explicitly test
  uninstall/reinstall and user-data deletion under the chosen identity model;
  do not claim those cases are solved by a per-install local file alone.
- Test just before, exactly at and after24 hours; sleep/resume, daylight saving
  and timezone changes, clock rollback/forward, offline use, corrupted/missing
  trial state, interrupted activation, Store entitlement refresh, purchase and
  cancellation/expiry. Unknown state must have a documented, visible policy.
- Use an injectable clock and synthetic entitlements for automated tests, plus
  an actual Store test installation. No real24-hour wait is required for each
  regression check. Keep any development bypass out of distribution builds.
- Explain activation, expiry, upgrade and recovery in the app. Keep licensing
  identifiers and secrets out of public logs and source control.

Start with the entitlement/state contract and one local expiry prototype.
Rough estimate:2–4 working days for design, prototype and expiry/restart/upgrade
checks; a hosted activation service, certification and purchase flows need a
separate estimate after their requirements are selected. This is a Windows
milestone requirement, not extra functionality for the0.5.22 reliability release.
