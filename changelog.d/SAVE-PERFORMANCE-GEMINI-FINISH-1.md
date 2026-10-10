### Finished save-performance probe implementation

Completed the offline `save-benchmark.py` probe for measuring Unio engine save performance safely. 

- Fixed subprocess boundaries by properly executing in process groups (`start_new_session=True`), killing the group via `os.killpg()`, and preventing resource leaks by closing standard file descriptors after process completion.
- Ensured total probe deadlines properly clamp descendant execution step timeouts (`min(step_timeout, ...)`).
- Upgraded the test fake-engine initialization to utilize parallel background `git clone` executions instead of creating empty directories, maintaining strict isolation without triggering probe timeouts.
- Adjusted result-recording paths so probes do not attempt to construct a receipt inside a fully-cleaned workspace.
- Authored initial `SAVE-PERFORMANCE.md` documentation covering how to execute the probe on local tmpfs and standard scratch disks, accompanied by baseline 0.5.9 engine measurements.

AI-Assisted-By: Gemini/Antigravity
