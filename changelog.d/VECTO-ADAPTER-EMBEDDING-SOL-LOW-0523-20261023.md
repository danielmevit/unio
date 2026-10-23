# Canonical adapter embedding refresh

- Regenerate the installer with `python3 -B tools/embed-adapters.py` to synchronize the embedded REVIEW-STATUS and REQUIRED-DELIVERY guides with their canonical sources.
- Restore the adapter embedding consistency gate; adapter Python payloads and canonical helper, engine, review, delivery and test logic are unchanged.
- Preserve the earlier full-gate failure separately; this mechanical refresh does not transfer prior review approval or establish full-gate success.
