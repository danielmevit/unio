### Fixed
- The test-only fault directory hook is scoped to proc-stat identity faults only, so an unreadable-pid marker can no longer fire unrelated faults such as capture launch, and the unused global trigger is gone. The Unknown regression now synchronizes on the supervisor's own cleanup verdict and proves no final save attempt or run completion before recovery. Product version stays 0.5.18.
