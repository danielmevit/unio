Add explicit opt-in owner remote roles and ref policy for Git pre-push validation
before publication. Protect against leaking private development branches or commits
to public release remotes via direct pushes, refspec aliases (dev:main, HEAD:main,
raw OIDs), unmerged release tags, or pushurl/rewrite redirection. Support same-remote
and multi-remote workflows with pinned destination hashing, credential redaction,
and non-clobbering owner hook chaining while preserving existing worker guards.
