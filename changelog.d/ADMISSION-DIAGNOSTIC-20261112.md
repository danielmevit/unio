# ADMISSION-DIAGNOSTIC-20261112

Resolve timing-sensitive fixture failure in installed admission deadline regression and preserve honest runtime diagnostic phase classification.

The full gate failure at `tests/unio-admission-deadline.py:87` (`partial unterminated line`: expected `phase=partial`, observed `phase=deadline deadline=3s complete_lines=0/5` after 2846s) was diagnosed through timing and payload analysis as a fixture timing sensitivity under heavy host/test load, not a runtime defect in `policy_admit_hold`. Production runtime behavior in `unio-install.sh` defaults to 30 seconds (`UNIO_ADMISSION_TIMEOUT=30`) and correctly distinguishes between stream termination at EOF (which diagnoses `phase=partial` or `phase=eof` immediately upon process exit) and deadline expiration before completion (which diagnoses `phase=deadline`).

In the test harness, `attempt()` defaulted `bound` to 3 seconds for non-deadline tests. Under prolonged gate load on virtualized/NTFS storage, shell sourcing of the 33,600-line installed functions file combined with Python 3 startup and Bash integer-second truncation in `SECONDS` allowed the 3-second window to expire before the child process wrote data and closed the pipe, triggering a false-positive deadline failure.

Resolution:
1. `tests/unio-admission-deadline.py`: Updated the harness default bound for non-deadline content and refusal tests to a justified 10 seconds. Because holder processes in these tests exit immediately upon writing partial output or encountering simulated faults, successful runs complete in under 0.5 seconds while providing sufficient margin against host scheduling delays.
2. Preserved dedicated 1s and 5s deadline tests (`old five second bound reproduction`, `deadline`, and `deadline after grant consumption`).
3. Added regression coverage verifying that delayed complete lines (`deadline after partial line`) and delayed unterminated lines (`deadline after partial unterminated line`) under an explicit 1-second deadline truthfully report `phase=deadline` with accurate line counts (`complete_lines=1/5` and `complete_lines=0/5`), proving that deadline timeouts and EOF stream truncations are not conflated.
4. Documented the distinction between deadline enforcement and diagnostic content test bounds in `docs/development/ADMISSION-DEADLINES.md`.
5. Retained `unio-install.sh` byte-identical to baseline, avoiding invented production patches or inflated production defaults.
