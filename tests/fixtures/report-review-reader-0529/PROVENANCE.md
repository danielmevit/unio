# Frozen 0.5.29 report-review reader fixture

Genuine pre-change 0.5.29 quality runtime used to prove that
`<task>.report-review.<id>/` is ignored by the official 0.5.29
`reviews` / `reviews --findings` / `reviews --json` / `result`
commands. This is not the current engine and is not a substitute
0.5.29 distribution.

## Source

- Official 0.5.29 installer read locally (prepare-time input only, never a
  runtime test dependency):
  `/mnt/d/Vibe Coding/_vm/unio/tmp/unio-next/fable-implementation-0529-20261113/assets/unio-install.sh`
- Version: 0.5.29
- Source commit: `65d2a2975d71adb16362f33ac0f6e06027d378fd`
- Source tree: `a3c884cc3020e5d8745f23f23e7fbb79e4c5529b`
- Installer bytes: 2327389
- Installer SHA-256: `2543b26a84235d4c5b8057d3106d0f3f3a84cdf9f398a4b036fb3d695ad01cb3`
- License: AGPL-3.0-only; additional terms in NOTICE. Same license as
  the repository LICENSE / NOTICE files. 0.5.29 LICENSE SHA-256:
  `0d96a4ff68ad6d4b6f1f30f713b18d5184912ba8dd389f86aa7710db079abcb0`
- Provenance JSON from that asset set recorded
  `publication_state_at_assembly: not yet published` with later
  documentation-only commit `65d2a297` after gated
  `c4f79698d1212c7359122feb291432ea84d38eb3`. Runtime installer bytes
  were recorded byte-identical after that docs-only step.

## What was extracted

`quality.py` is the verbatim `QUALITY_PY` heredoc from that installer
(the embedded quality runtime that implements `quality reviews` and
`quality result`), plus a terminating newline so the file is POSIX
text. Body SHA-256 before the terminating newline:
`c231a12ebd2535ddc0c012caf9e7058d65f165d655888b9e376f6e72ad116bec`.

The 0.5.29 reviews directory match is the literal regex
`re.escape(task)+r'\.review\.[A-Za-z0-9]{8}'`. That pattern does not
match `<task>.report-review.<16hex>`. `quality.py` contains no
`report-review` or `review-packet` writer.

`unio-reader` is a thin launcher. `check_id`, `find_root` and
`cmd_reviews` argument handling are copied from the same 0.5.29
installer. `result` follows the 0.5.29 `cmd_evidence` result path
(`quality paths` then `quality result`). Other 0.5.29 commands are
absent on purpose.

## Fidelity and limits

- This fixture proves namespace ignore and unchanged 0.5.29
  reviews/findings/result/readiness output against evidence produced
  by the current engine. It is the actual 0.5.29 quality reader, not
  a reimplementation of those commands.
- It is not a full 0.5.29 `unio` binary. It does not install, run,
  verify, review, bind, update CLIs, or contact network services.
- The whole 0.5.29 installer (2.3 MiB) and source archive are not
  committed. Host-space, delivery and other quality helpers remain
  inside `quality.py` because `reviews`/`result` load that runtime as
  a whole; they are not a claim that this task re-audited those
  helpers.
- Runtime tests must not open the owner-workspace installer path.
