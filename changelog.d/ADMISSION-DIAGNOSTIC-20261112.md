# ADMISSION-DIAGNOSTIC-20261112

Give content-focused admission regression tests a bounded ten-second window,
while preserving explicit one- and five-second timeout tests and adding cases
that hold partial output open past a deadline. Production admission code,
its thirty-second default, complete-handshake requirements, cleanup and refusal
behavior remain unchanged.

The first combined gate observed `phase=deadline` where the unterminated-EOF
case expected `phase=partial`, under its three-second fixture bound. The run
used private POSIX tmpfs fixtures; it was not instrumented to establish why the
reply did not complete in time. Scheduling or startup variability is a plausible
explanation, not a reproduced historical root cause or demonstrated production
regression. A passing focused rerun alone does not prove the cause.

The added tests assert the deadline phase and preserve the no-provider and
cleanup assertions. They do not assert that partial bytes arrived before the
deadline or verify exact partial-line counts; those stronger coverage checks
remain separate potential improvements.
