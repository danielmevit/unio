# Final edges of interrupted-run observation

- Run observation accepts exactly the worker and task IDs the native `ident` check accepts, with no extra 200-character or DEL limit. A 201-character task keeps its recorded terminal exit (for example 124) instead of becoming `Unknown`. A name the filesystem cannot hold fails on the actual read and gives `Unknown`.
- Strict JSON parsing now also rejects numbers that overflow to positive or negative infinity (such as `1e999`). Such records and owner files give `Unknown` without tracebacks. Finite floats, large integers, UTF-8, duplicate-key and depth handling are unchanged.
