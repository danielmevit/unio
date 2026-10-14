### Development

- Correct project-root discovery to resolve physical cwd once, preserving legitimate main-clone and worker entry through Bash logical symlinks. A copied `.unio-worker` outside the direct clone/`wt/` layout no longer bypasses refusal. Installed offline regressions exercise genuine Bash logical `cd` and freeze exact outer policy/STOP bytes for marked nested repositories under scratch and inside the main clone. Direct-child legacy topology remains allowed; this is an accidental-selection guard, not repository authentication or a sandbox.
