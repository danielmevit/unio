### Fixed
- Native stop now records a provider session before exec and reaps that session on cancel, public kill, and normal provider exit, including descendants that change process group or are reparented.
- A malformed, stale, or reused pid is not signaled. The worker and account stay occupied while a known owned provider is still live or cleanup is Unknown. The final save keeps its existing bounded attempt. Product version stays 0.5.18.
