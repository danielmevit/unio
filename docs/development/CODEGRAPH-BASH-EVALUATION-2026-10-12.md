# CodeGraph Bash evaluation — 2026-10-12

**Current result: the local grammar correction passes the bounded Unio CLI checks.**
The read/write redirect, negated `case` and coprocess defects described below
are repaired in local candidate `64e64f4`. The clean follow-up is now published
for upstream review as `01f8b3a`; no global CodeGraph install or working-project
index was made. Installed Unio remains **0.5.13**.

## Upstream review submission — 2026-10-13

The owner-authorized submission is posted on the original
[issue #1203](https://github.com/colbymchenry/codegraph/issues/1203#issuecomment-6135096972)
and [PR #1217](https://github.com/colbymchenry/codegraph/pull/1217#issuecomment-6135101790).
It explains the owner's use of CodeGraph over the past couple of months,
its efficiency, the Bash gap encountered while building Unio, and the
existing PR on which the experiment builds.

The [public follow-up branch](https://github.com/danielmevit/codegraph/tree/contrib/bash-unio-followup)
contains source, reduced regressions, the original MIT notice, a grammar-only
patch and a portable build recipe. It credits Omar-Elwazeery's original PR and
Adam0120's overlapping compatibility follow-up. It is available for review and
cherry-picking into the existing effort; upstream has not merged it.

On upstream base `4f3eaf3`, the clean contribution passed **38 selected
engine/preload checks** (1,011 unrelated tests skipped), TypeScript/build/asset
checks, shell syntax and whitespace checks. The preload helper now confirms
the actual shebang before selecting Bash for an unknown extensionless file,
addressing the existing review concern. A portable rebuild reproduced the
recorded WASM byte for byte, and 20 repeated parses passed. A fresh graph of
the same Unio CLI again matched all 8 selected function boundaries/parents
and 7 selected call links. The wider syntax and embedded-language limitations
below remain open; the full upstream repository matrix and agent A/B
acceptance remain unperformed.

The existing Codex lead prepared, checked and published this follow-up without
another provider invocation. The Mistral/Vibe GLM worker result and lead
correction below remain separate historical outcomes. Private run logs,
authentication data and local paths were excluded from the public branch.

## Grammar correction and double-check — 2026-10-12T21:54:21+02:00

The [official 0.25.1 grammar](https://github.com/tree-sitter/tree-sitter-bash/blob/v0.25.1/grammar.js)
omitted the `<>` redirect operator and did not
handle Unio's negated `case` condition. The correction adds those forms and an
explicit coprocess body. It preserves the original MIT notice and the Bash
parse-error guard; malformed Bash must still produce an error rather than an
invented graph. Source provenance and a locally rebuilt WASM are preserved.

Mistral subscription / Vibe 2.26.1 / GLM 5.3 (`zai-glm-5-3`) / high completed
`CG-BASH-REDIRECT-VIBE-1` in one invocation: Source/native/adapter 0, saved
`ca019ec`, and all 3 required validation commands passed. Native scope failed
because its project baseline included inherited integration paths; the exact
diff from frozen source base `67883ae` touched only the 6 allowed paths. That
native failure remains recorded, without being converted into a PASS.

The lead's separate check caught a real omission in the proposed patch:
`policy_admit_hold` ended at 4755 instead of 4839, although the parser reported
no errors and all 7 selected call links were present. A stronger regression
reproduced the shortened function. The existing lead added explicit coprocess
syntax, including named/unnamed brace and subshell bodies and simple commands.
An intermediate simple-command failure was retained and corrected. No extra
AI reviewer, model replacement or invocation retry was used.

Final checks on the frozen candidate:

- **32/32 selected checks pass:** 27 focused regressions plus 5 existing Bash/Bats
  extraction, import-resolution and extensionless-script sync checks.
- **100/100 upstream Bash grammar corpus cases pass.** The official 0.25.1 tag's
  grammar, scanner and license match the inputs pinned from npm.
- The unchanged 367,490-byte Unio CLI indexes without file errors. All 8 selected
  function start/end pairs and their top-level parents match independently
  inspected source. All 7 selected call links resolve.
- Small-fixture Bash calls and the Python control still pass. Ordinary text,
  inert heredoc contents and dynamic source paths are not invented as code.
  Execution markers stay absent; inspected scripts were never run or sourced.
- The reduced shell fixture passes `bash -n`; source and WASM hashes and the
  unchanged MIT notice match the saved build record.

The candidate WASM is built with tree-sitter 0.25.10 (ABI 15) and local
Emscripten 4.0.10. Docker was not needed. SHA256:
`b23e6f7672672bc52d76ca2a7ff8a6019e495fca19272fb84b5232605b437cf5`.

This is bounded acceptance of the measured CLI cases, not proof of universal
Bash coverage. `examples/demo.sh` remains a reported parse error in the wider
source copy, the oversized installer is still skipped at the default 1 MiB
limit, and its quoted runtime payload needs an explicit indexing strategy.
Embedded Python remains opaque to the Bash extractor; runtime-derived commands
still cannot always have a proven target. No agent-productivity A/B comparison
or cross-repository language acceptance was performed.

Reported worker usage was 3,337,680 cumulative tokens with estimated $4.765512
within the existing Mistral subscription. This is not an additional-charge or
remaining-allowance reading. Effective model/effort and allowance remain
Unknown. Native automatic saves refused an oversized unchanged Dart parser;
the implementation is preserved in Git, not claimed as a successful save.

The earlier failures and measurements follow as retained history. Reproducible
patches, build inputs, dated receipts and final checks are in the private
`tmp/codegraph-bash-evaluation/` workspace. They contain no published credentials.

## Initial evaluation — retained history

**Initial decision: retain the experimental patch; defer default use on Unio.**
The local candidate can navigate simple Bash functions and calls, but the real
Unio CLI exposed incorrect function boundaries and missing call edges. Passing
small fixtures or returning a successful index is insufficient evidence of
accurate navigation. No global CodeGraph upgrade, index of the working Unio
repository, or upstream publication was performed.

This is an optional development-tool experiment, not a new Unio runtime feature
or a released CodeGraph capability. Installed Unio remains **0.5.13**.

### Source and contribution

- CodeGraph upstream baseline: `7ba8eee4a78920e9f637624d351e042f0fc98772`.
- Existing [Bash PR #1217](https://github.com/colbymchenry/codegraph/pull/1217):
  `c8a48a20e511aea59a8d0f77cd5593411c6e6e41`.
- Unio input: `29ae7e04c62f1e02eb819da6b4564c92b447560c`, copied into disposable
  datasets. Subsequent reporting-guide changes do not alter the CLI payload.

The experiment builds on the existing PR; it does not claim its original
authorship. The inherited grammar crashed on five of eight fixture files with
`resolved is not a function`. The integration now selects the official
`tree-sitter-bash` 0.25.1 WASM explicitly and includes its MIT notice in copied
assets. Merely adding the new WASM was insufficient: the loader initially still
selected the old dependency. The failed check and correction are preserved.

Two additional corrections prevent misleading results:

- Recognize the interpreter in a shebang, rather than any later argument named
  `bash` or `sh`. For example, a Python script with `/tmp/bash` as an argument
  must not become a Bash file.
- Preserve literal shell source references without guessing target files.
  `source ./lib.sh` depends on the current working directory; bare names may
  depend on `PATH`. Bash does not invent `.sh` or `.bats` extensions. This
  candidate therefore does not resolve Bash file-import targets automatically.

### What the measurements establish

The repaired candidate passed all **16 focused checks** before the real-file
evaluation. Fixtures cover local calls, case dispatch, shebangs, inert heredoc
contents, unresolved dynamic source paths, a Python control and a marker proving
that indexing did not execute the fixture scripts.

| Input | Baseline | Repaired candidate before the parse-error guard |
| --- | --- | --- |
| Small fixtures | Python control only | Eight files indexed, no file errors; expected simple Bash calls found |
| Unio source copy, default 1 MiB limit | 104 files indexed; no Bash | 113 indexed, one oversized installer skipped; nine shell files added |
| Extracted Unio CLI | Extensionless Bash file unsupported | 106 functions; all seven selected function start lines correct; five of seven selected call edges found |

These are single local observations, not a throughput benchmark. The index
times were approximately 7.03/3.69 seconds for baseline/candidate fixtures,
35.60/28.34 seconds for the source copy, and 2.58/3.78 seconds for the extracted
CLI. The baseline does less work and host/cache conditions differ; these numbers
do **not** establish a speedup, token saving or agent productivity improvement.

The extracted CLI is 367,490 bytes and exactly matches installed 0.5.13
(SHA256 `134355b369c96d76d416e38e81e9ed9d077362e8b934095b1d461832551880c8`).
It was obtained by reading the installer's quoted `UNIO_BIN_EOF` payload, without
running the installer. Its line offset inside the installer is 17,433.

The installer itself is 1,382,888 bytes, above the default limit. Raising that
limit alone would not expose the embedded CLI as executable Bash: a correct
outer Bash parser treats a quoted heredoc as data. No default limit was raised.

### Why adoption is deferred

The real CLI produced parser recovery errors around read/write redirects such
as `exec {FD}<>"$fifo"`. The reduced `exec 3<>"$fifo"` form also reproduces a
grammar error. Recovery incorrectly made later top-level functions appear
nested inside `policy_refuse_report`, and omitted the selected
`cmd_run`/`cmd_review` calls to `policy_admit_hold`. The original index still
reported zero errored files because symbols survived the parse.

This is a grammar correctness problem, distinct from these inherent scope limits:

- A dynamic command derived from configuration cannot always have a proven
  concrete target without runtime information.
- Quoted Python/JavaScript payloads need explicit embedded-language extraction
  and source mapping before cross-language navigation can be claimed.
- A cross-file function-name match does not prove that a shell sourced that file.
- The three runtime query responses were roughly 13.3 KB each; finding symbol
  rows is not proof that those responses explain the complete execution flow.

The final defensive change refuses to emit a Bash graph when the parse tree
contains recovery errors. It does not repair unsupported grammar. All **18 Bash
regression checks plus one extensionless-script sync check pass**. The reduced
redirect fixture also passes `bash -n`, confirming that it is valid shell syntax
without executing it. A file that the parser cannot understand now produces an
explicit error rather than misleading function nesting.

Fresh post-guard measurements confirm: all eight small fixtures still index
without file errors; the extracted CLI fails explicitly with zero graph nodes
or edges. The full source copy indexes 112 files, rejects `examples/demo.sh`
with a Bash parse error, and still skips the oversized installer. Its existing
Astro warning is also retained. Mixed-project indexing can report overall
success while individual files fail, so always inspect `filesErrored` and
per-file diagnostics.

The existing extraction/resolution suites initially passed 950 of 955 checks.
Five failed because they opened a hard-coded project-local database location;
rerunning only those five with `CODEGRAPH_DIR=.codegraph` passed all five.
The original log remains preserved. This was a fixture-location adjustment,
not a source change or a second complete suite run. Documentation packaging
checks passed three of three; only scoreboard prose changed in Unio's embedded
installer templates, with executable payload equality checked separately.

The follow-up must fix the reduced grammar failure, retain correct function
boundaries and reproduce all seven chosen edges before reconsidering Unio
adoption. It must separately decide how generated/embedded source is indexed.
The full upstream language evaluation across repositories and a measured agent
A/B comparison were outside this bounded experiment and remain undone.

### Worker evidence and fresh availability

| Route, CLI, requested model and effort | Task and observed result |
| --- | --- |
| Mistral subscription / Vibe 2.26.1 / GLM 5.3 (`zai-glm-5-3`) / high | Integrated the existing PR in local commit `3e7932d`; Source 2, infrastructure failure. Native verification passed two of three checks; required regression test was missing. |
| GitHub Copilot Free / Copilot 1.0.95 / Auto Balance / effort not exposed | Returned a supporting checklist. Its source-relative path assumption was rejected by the lead; this was not a final review. |
| Grok subscription / Grok CLI 1.0.46 / `grok-4.7` / high | One replacement implementation call returned HTTP 402, exhausted usage balance, with no edits. |
| Existing Codex lead / owner-selected Astra / xhigh | Completed the bounded local corrections and inspected the measured graphs. Exact serving identity is not independently verified; no additional Codex worker was started. |

At the owner's request, separate small checks on the evening of October 12
confirmed that **Mistral/Vibe GLM 5.3 / high and Copilot Auto Balance responded**.
OpenCode Go / OpenCode 1.18.35 / `opencode-go/glm-5.3` / high also returned model
text, but an overly tight local one-step cap produced a maximum-steps response.
That proves connectivity, not clean diagnostic-task completion; do not reuse
that cap for real implementation. Perplexity was not needed or freshly tested.
None of these checks establishes remaining allowance or guarantees a long run.
Original failures remain in the record; no paid fallback or automatic retry ran.

### Evidence location and next work

Private reproducible inputs, date-derived run receipts, test logs, query outputs
and local Git history live under `tmp/codegraph-bash-evaluation/` in the Unio
workspace. That directory is not part of the public repository. No credentials,
native authentication stores or raw provider sessions are published here.

The current result should inform a bounded upstream grammar contribution if the
owner chooses to continue it. It should not delay Unio's next functional priority:
[matched automatic-save reliability diagnosis](ROADMAP.md#next-useful-slices).
