# Unio 0.5.14 — configurable recovery-save budgets

Give slow recovery captures a deliberate, bounded allowance while retaining the
30-second default and every existing save-integrity check.

## Choose a capture budget

`UNIO_SAVE_CAPTURE_TIMEOUT` accepts positive whole seconds from **1 through 300**.
Unset means **30 seconds**. It applies to manual captures and automatic baseline,
periodic and final captures:

```bash
UNIO_SAVE_CAPTURE_TIMEOUT=300 unio save create WORKER TASK
UNIO_SAVE_CAPTURE_TIMEOUT=300 unio run WORKER TASK
```

A larger value allows longer waits before worker startup and after worker exit.
It does not make capture faster. Invalid settings refuse capture before save-store
effects; the worker's execution and real exit remain independent. Read-only
inspection/usage and restoration remain usable. Agent execution, observation and
restore timeouts retain their separate bounds. Cancellation retains the original
30-second final-cleanup ceiling and one-second helper escalation grace.

Automatic-save failures identify `capture deadline exceeded (N seconds)` only
when the controller actually initiates a deadline stop. The real helper exit,
previous good snapshot, existing result schemas and all stable-byte, secret,
retention, archive and integrity checks are preserved.

## Measured result

On one matched Windows-mounted fixture with 400 worktree paths and 32 retained
saves, the default controller killed the helper after its 30-second deadline;
controller/failure bookkeeping took 40.36 seconds. An explicitly configured
300-second capture succeeded in **217.33 seconds**, preserving source HEAD/index,
the prior good save and the original diagnostic evidence. These instrumented
single-run observations do not establish a general speedup or the causes of
older historical kills. See the [diagnosis and measured limits](development/AUTOSAVE-HELPER-2026-10-13.md#configured-budget-measurement)
and [saving guide](WORK-SAVING.md#capture-time-budget).

## Validation and scope

The implementation's 70 focused offline runtime checks cover actual configured
capture outcomes, invalid input before effects, deadline versus external kills,
real worker exits, last-good retention, periodic saves and bounded cancellation.
Native scoped verification passed all three required commands. Release delivery
also requires the full repository gate, exact artifacts, an isolated upgrade and
restore, installation before publication, an installed offline smoke check and
official-download hash verification.

This release includes updated owner guidance for dedicated Sol corrections and
honest worker-route reporting. Those remain lead instructions, not automatic
model delegation. Dashboard, website and brand payloads are preserved.
