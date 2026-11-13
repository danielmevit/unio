Introduce neutral fresh-start lead instructions and align coordination tier terminology:
- Rewrite the embedded MASTER template in `unio-install.sh` into a concise, neutral starting instruction for new users instead of personal maintainer account and permission rules.
- Use neutral human-owner terminology in lead operational guidance; preserve legal author credit intact elsewhere.
- Replace unsupported myapp scorecard references in MASTER with supported `unio score` and `unio experience` guidance; navigate code with CodeGraph only when indexed (`.codegraph/`).
- Fix the coordination tier table in `docs/WORK-MODES.md` (and generated installer template) to designate the two-workflow tier as `medium` rather than `balanced`, keeping balanced work mode and medium tier distinct.
- Add conservative keep-if-existing template guard and unsafe-target check for `templates/MASTER.md` to preserve custom templates and project role cards across repeat installs.
- Add test suite `tests/unio-neutral-startup.py` covering fresh install, tier table accuracy, unsafe target refusal, repeat install preservation, and custom router preservation.
- Broad fleet notes and historical model scoreboard cleanup are deferred.
