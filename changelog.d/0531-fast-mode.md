### Changed
- Renamed the public work mode YOLO to Fast across the CLI input, help, shell completion, dashboard, human fleet surfaces, README, and documentation guides (docs/development/contracts/FAST-MODE-NAME-V1.md).
- Added `fast` as the canonical public command (`unio mode fast`), while retaining `yolo` as an accepted legacy alias alongside existing `medium` and `safe` aliases.
- Preserved schema-1 stored and machine `.mode` values (`yolo`, `medium`, `safe`) for full backward compatibility, while reporting public `protocol` (`fast`, `balanced`, `thorough`) in `unio policy --json`.
- Explained Fast as quick delivery with essential checks and accepted follow-up work, without waiving required checks, STOP, or account budget rules.
- Updated dashboard and fleet status human surfaces to display Fast while maintaining legacy internal validator compatibility.
- Added comprehensive regression evidence across canonical `fast` input, `yolo` alias, old stored schema-1 policies, public protocol reporting, help, completion, and human/browser surfaces.
