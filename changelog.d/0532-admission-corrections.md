0532-ADMISSION-CORRECTIONS: address independent current-code review findings
(contract 0532-ADAPTIVE-ADMISSION-CORRECTIONS-V5) for native lead session policy
admission (`tools/lead-session-policy.py`). Default installed off hold discovery
falls back to `~/.config/unio/off/<agent>` when neither `UNIO_CONF_DIR` nor
`CONF_DIR` is set in the environment, and the production `unio lead-session`
dispatch exports `UNIO_CONF_DIR="$CONF_DIR"`, ensuring `unio off <lead>` blocks
owned lead sessions under standard default installations. Project-level
`coord/off/<agent>` is clarified as a read-only compatibility observation without
adding a new project-scoped off command. Slot metadata bounds are aligned with the
native contract at 4096 bytes (`MAX_SLOT_META = 4096`), so valid locked slots over
2048 bytes (e.g. 2500 bytes) correctly count as active native workflows. Slot
counting fails closed on unreadable or unsafe slot state (unreadable directory
permissions, open/read I/O or permission errors, oversized or non-regular files,
symlinks, malformed JSON, and invalid schema/labels/timestamps) matching native
`count_active` and `read_slot_meta`, while missing directories legitimately return
zero active workflows. Policy labels (`lead_agent`, account mappings, and budget
labels) strictly enforce native `check_label` rules, refusing whitespace, slashes,
leading dashes, and traversal. Safe locks directory creation ensures `coord`
exists before `.locks` is created. Added focused regression tests in
`tests/unio-lead-session-policy.py` and registered it in `tools/quality-check.sh`,
verifying default entrypoint environment, genuine permission faults without
assuming root is denied by chmod 000, and slot bounds. Unreleased.
