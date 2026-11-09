Cache inventory now requires exact lowercase cache directory entries and refuses
case-insensitive tracked-path aliases on every platform. Malformed worker Git
registration paths exclude only that worker instead of aborting JSON inventory.
The command remains read-only with no delete/apply mode.
