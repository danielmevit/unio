Fixed the installed command-audit fixture's `dirname` shim to recognize its
isolation boundary with or without an optional `--`, while preserving the
original arguments when forwarding to `/usr/bin/dirname`. Added direct
regression coverage for both boundary forms and literal-path argument
forwarding. Product runtime and offline provider poison assertions are unchanged.
