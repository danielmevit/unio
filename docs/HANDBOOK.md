# The Unio Handbook

One document, everything you need: what Unio is, every command, a real
worked example from your own history, and the maintenance recipes. Written
to be readable without a programming background.

---

## 1. What Unio is

Unio turns five separate AI coding subscriptions — Claude, Codex
(ChatGPT), Antigravity (Google), Grok Build (X), and OpenCode — into one
coordinated software team on your Ubuntu machine. One AI acts as the
**foreman** (plans work, writes task orders, inspects results); the others
act as **workers** (each builds its assigned piece in its own isolated
copy of the project); and **you** are the owner — the only one who can
accept work into the real codebase.

What it is NOT: it isn't an AI itself, and it doesn't contain the AI
tools. It's coordination machinery — about a thousand lines of scripting
that handles workshops, work orders, reports, receipts, and safety
switches. The
intelligence is rented from your five subscriptions; Unio is the
office they work in.

Three principles it's built on:

**Isolation.** Every worker gets its own complete copy of the project (a
"git worktree") pinned to its own branch. This separates ordinary edits
and review receipts; it is not an OS sandbox. Configured commands retain
host access and can reach other worktrees or files.

**Receipts over reports.** Every run produces a report (the agent's own
claim) and a diff (the exact line-by-line truth). Rule one of operating
this system: reports can lie, diffs can't.

**One human gate.** Nothing enters the real codebase without you merging
it. The foreman recommends; you decide. This is not a formality — it is
the entire safety model.

## 2. The loop

Every piece of work follows the same cycle:

```text
 YOU: "I want X"  (two sentences, plain English)
   ↓
 FOREMAN: studies project → proposes task breakdown → waits for your "go"
   ↓ (you read the task files, then: "go")
 FOREMAN: dispatches workers, in parallel, each in its own workshop
   ↓
 WORKERS: build, test, commit on their own branch, report
   ↓
 FOREMAN: machine-checks first (unio verify), reads the diffs, recommends
   ↓
 YOU: read the diff yourself → merge what passes → reject what doesn't
```

Rejection is normal and healthy. A long streak with zero rejections means
your gate has gone soft, not that the team has become perfect.

## 3. Project anatomy

`unio init` builds this next to any repo clone:

```text
<project>/
├── repo/            The real project, on the base branch (normally dev).
│   │                YOU and the FOREMAN work here. Nobody else.
│   ├── MASTER.md    Foreman's standing orders — symlinked as CLAUDE.md,
│   │                AGENTS.md, GEMINI.md so any AI brand reads its role.
│   └── changelog.d/ Changelog fragments, one file per task. Workers never
│                    edit CHANGELOG.md itself — the one shared file that
│                    used to guarantee merge conflicts.
├── wt/              The workshops.
│   ├── codex/       Full project copy, branch agent/codex, WORKER.md orders.
│   ├── antigravity/ Same pattern per worker. Workers never leave their
│   ├── grok/        own folder and never touch the base branch.
│   ├── opencode/
│   └── claude/      (a Claude WORKER — distinct from the foreman)
└── coord/           The office. Deliberately OUTSIDE git.
    ├── base         One word: the integration branch (dev).
    ├── docs/        Your playbooks — foreman must read before planning.
    ├── board.md     Task board. Foreman-only writes.
    ├── tasks/       Work orders, one .md per task (TEMPLATE.md included).
    ├── reports/     Auto-written run reports (.md) + full raw logs (.log)
    │                + ledger.jsonl: one JSON line per run/verify/review.
    ├── results/     One JSON result per worker and task: process, checks
    │                and review, each bound to an exact revision.
    ├── handoffs/    Context packets for the next AI (unio handoff).
    ├── blockers.md  "I'm stuck" notes, append-only.
    └── STOP         If this file exists, all new runs are refused.
```

Key facts about the data: report `.md` files are append-only (every run
adds a block — this is the historical record); `.log` files hold only the
latest run (overwritten each time). `ledger.jsonl` is the machine twin of
the reports — append-only JSON, one line per run/verify/review/merge with
durations and diffstats; `unio score` reads it directly, no markdown
parsing anywhere.

## 4. Complete command reference

### Unio (the machinery)

| Command | What it does |
|---|---|
| `unio new <repo-url> [name] [workers...]` | The whole project bootstrap in one command: clone → dev branch → init → your playbooks copied in from `~/.config/unio/playbooks/`. Run it where you keep projects (e.g. `~/code`). |
| `unio init [w1 w2 ...]` | Build workshops + office next to your clone. Run once per project, from inside the repo. Default workers: codex antigravity opencode grok. Add more anytime: `unio init claude`. |
| `unio agents [--json]` | Roll call: each agent — program installed (yes / no / unknown when the conf line uses shell syntax)? switched on/off? Local only: it never runs the agent and never checks login or quota. `--json` prints the same as machine-readable JSON. |
| `unio run <w> <task>` | Execute `coord/tasks/<task>.md` with worker `<w>` in its workshop. Blocks until done; prints exit code + report path. Resets the task's stored result; the worker's real exit code is kept even if the post-run snapshot fails. |
| `unio run -b <w> <task>` | Same, in the background — dispatch several at once, poll with `status`. |
| `unio tail [task]` | Watch a run's log live (default: the newest). Ctrl-C stops watching, not the run. |
| `unio kill <task>` | Stop a background run cleanly — kills its whole session, including the agent under `timeout`; any partial work stays uncommitted in the workshop. |
| `unio report <task> [lines]` | Read a task's report without typing paths (default: last 60 lines of the append-only history). |
| `unio verify <w> <task>` | The mechanical gate assist: checks the diff against the task's "- path" scope lines, re-runs its "$ " Validate commands inside the workshop, and flags empty "success" diffs. Verdict lands in the report and the stored result. Exit 0 = PASS, 1 = FAIL, 2 = INCOMPLETE (no scope lines, no Validate lines, or the worktree changed during the checks). Run it BEFORE reading any diff. |
| `unio diff <w> [--stat]` | The receipts: exact changes on that worker's branch vs the base branch, committed and uncommitted separately. `--stat` = file list only (your scope check). |
| `unio review <w> <task> [agent]` | Second opinion from a DIFFERENT vendor, only after a current verify PASS: it gets the task order + the full committed diff (clean worktree, text only, at most 300000 bytes) and must end with exactly one `VERDICT: APPROVE` or `VERDICT: REQUEST-CHANGES` line. Exit 0 = approved, 1 = changes requested or the reviewer failed, 2 = unknown verdict or incomplete material. Your gate, with a rival's eyes attached. |
| `unio result <w> <task>` | The stored evidence as JSON: process, validation and review states, each bound to a revision, plus `stale` and `ready_for_human_review`. Read-only, no provider call. Exit 2 when the result is missing or malformed. |
| `unio handoff <w> <task>` | Writes a context packet for the next AI under `coord/handoffs/` (task, result, revision, changed paths, HANDOFF.md) and prints its path. Not a backup: uncommitted work stays in the workshop. Refused while the worker runs. |
| `unio sync [w]` | After your merges: brings the base branch into worker branches (fast-forward when fully merged, merge otherwise) so workshops build on current reality instead of drifting stale. Skips dirty or running workers; reports conflicts instead of forcing them. |
| `unio status` | Morning briefing: benched agents, open tasks, recent reports,each workshop's branch state, anything still running. |
| `unio off <agent> [30m\|5h\|7d]` | Quota switch: bench an agent. `5h` for a burned session window, `7d` for a weekly cap — auto-returns when the time expires. No duration = benched until `on`. |
| `unio on <agent>` | Un-bench immediately. |
| `unio smoke` | One tiny live call per agent, from a neutral folder. Run after any CLI update or after days away — catches renamed flags and expired logins in 30 seconds. Rows read OK / WARN (replied, but not "ok") / FAIL. |
| `unio selftest` | The whole loop — init, run, verify, bench, lock, background + kill, sync, review — rehearsed in a throwaway sandbox with mock agents. Zero quota, ~15 seconds. Run after updating Unio itself. |
| `unio doctor` | Preflight a project before you dispatch: base branch present, each agent's binary and config line, worktree health (right branch, behind base, uncommitted), stale pidfiles, guard hooks, disk headroom. Catches the misconfigurations that would otherwise waste a run. Exits nonzero on an error. |
| `unio race <task> <w1> <w2> …` | Bake-off: the same task dispatched to several workers in parallel (isolation makes it free). Compare the diffs, merge exactly ONE winner — head-to-head data for the scorecard. |
| `unio sabotage [w]` | The saboteur seat: syncs the worker, then sends it hunting for real bugs in freshly merged work by writing failing tests. With no worker named, the seat rotates round-robin through your vendors — a different pair of eyes each time. |
| `unio sabotage --all` | Every available vendor attacks the same code in turn, one after another. For a finished feature or a release: different models find different defects, and a finding two vendors agree on is almost certainly real. |
| `unio score [project-root]` | The fleet scorecard, straight from the ledger: runs, ok/fail, walls, verify pass-rate, merges, average duration — per worker, sorted by merges. Your "who earns their seat" view; `myapp` remains the full product with pre-ledger history. |
| `unio version` | Installed version + config path — check it after every `bash unio-install.sh`. |
| `unio stop` / `resume` | Project-wide red button: refuse ALL new runs / release. |

Tab-completion ships with the installer (commands, then workers / task ids
/ agent names in context) — it lands in
`~/.local/share/bash-completion/completions/unio` and just works in
any new shell on a normal Ubuntu.

Worker naming: the part before a dash picks the engine — worker `codex-2`
runs the codex CLI, so you can have two codex workshops.

### Settings (environment variables and files)

| Thing | Meaning |
|---|---|
| `~/.config/unio/agents.conf` | One line per agent: how to invoke its CLI headless. THE lego file — add/retune agents here. |
| `<project>/coord/agents.conf` | Optional per-project override of the above. |
| `<project>/coord/base` | The integration branch name (auto-detected: dev). |
| `UNIO_TIMEOUT=7200 unio run ...` | Per-run time limit in seconds (default 3600). |
| `UNIO_VERIFY_TIMEOUT=900` | Per-command time limit for verify's Validate re-runs. |
| `UNIO_REVIEW_TIMEOUT=900` | Time limit for a cross-vendor review call. |
| `UNIO_AUTO_OFF` | Accepted for compatibility with no effect. A failed run can warn about suspected limit language; check the provider and use `unio off` explicitly. Worker output never changes availability. |
| `UNIO_AUTO_VERIFY=1` | Append verification after the run. A successful worker plus failed/incomplete checks returns the check's nonzero exit; worker failures keep their own exit. This is not approval. |
| `UNIO_AUTO_SYNC=1` | Fast-forward a stale worker onto the base branch before a run (when its worktree is clean), so it never builds against outdated code. Without it, `run` just warns. |
| `UNIO_ALLOW_SECRETS=1` | Override init's refusal when secret-looking files are tracked. Know exactly why before using it. |

### myapp (the scorecard — the team's first product)

| Command | What it does |
|---|---|
| `myapp <project-root>` | Per-agent performance table for any Unio project: Runs, OK, Fail, Walls (runs that hit auth/quota walls), Merges (branches you accepted), Last run. Sorted by merges — earners on top. |

Run it weekly per active project. Merges are the column that matters:
effort is Runs, results are Merges.

### Your commands (the human gate — plain git)

| Command | When |
|---|---|
| `git merge --no-ff agent/<w> -m "merge T1: ..."` | Accept a worker's branch into dev. Only after reading the diff. From `repo/`. (The post-merge hook logs it to the ledger — that's where `score`'s merges column comes from.) |
| `python3 -m unittest discover tests -v` | Your own test run — acceptance evidence you produced yourself. |
| `git push` | End of every work session. This IS your backup strategy. |
| `git checkout main && git merge dev -m "release vX.Y.Z" && git tag vX.Y.Z && git checkout dev && git push origin dev main --tags` | Release, per your model: main only moves when you say "release". First have the foreman roll `changelog.d/` into CHANGELOG.md. Order matters: merge fix → verify → THEN tag. |

---

## 5. The session rhythm: start, work, save, resume

The single most important fact for continuity: **the project's memory
lives in files, not in any chat.** Worker branches, reports, the board,
CHANGELOG, git history — all survive every shutdown automatically. The
foreman's chat is a convenience you can resume, but the files are the
truth. You could fire the foreman every night and hire a fresh one every
morning without losing anything that matters — that is exactly why task
files are self-contained and the board exists.

### Starting a session (2 minutes)

```bash
cd ~/code/<project>/repo
unio status          # where did I leave off? benched agents? open tasks?
unio smoke           # after CLI updates or days away: everyone alive?
claude                    # hire the foreman
```

Then EITHER continue the previous conversation:

```bash
claude -c                 # instead of plain claude: resumes last chat, full memory
```

— use `-c` when returning the same day. After days away, prefer a FRESH
session with this resume prompt (old chats degrade; files don't):

```text
Read MASTER.md, ../coord/docs/*, ../coord/board.md, and CHANGELOG.md.
We are resuming. Summarize current state — merged, in flight, blocked —
then propose the next step. Wait for my go.
```

### Working efficiently

- Dispatch long tasks with `-b`, poll with `unio status` (or watch
  live with `unio tail`), and review results in batches — two or
  three diffs in one sitting beats context-switching per task.
- `unio verify` before you read any diff — let the machine flag
  scope breaks, failing Validate commands, and empty "success" diffs
  first, then read with its verdict in hand. Big or risky diff? Add
  `unio review` for a rival vendor's second opinion.
  `unio result` then shows whether the run, verify and review
  evidence all still match the current code.
- After your merges: `unio sync` — one command and every workshop
  rebuilds on the new base instead of drifting stale.
- Two terminals: foreman in one, YOUR gate commands (diff, tests, merge)
  in the other. Never gate inside the foreman's window.
- Reject early. A sharp re-brief costs minutes; polishing a wrong diff
  costs an evening.
- Quota-aware ordering: hard tasks early in your 5-hour windows, chores
  late. Bench (`unio off`) the moment limits bite; never wait on a
  dead agent.
- One cycle at a time: don't dispatch new work while merged-pending diffs
  are waiting on you — your review is the bottleneck, protect it.

### Ending a session (3 minutes — the save ritual)

```bash
unio status          # 1. "running: (none)" — never leave -b runs going;
                          #    Windows sleep/reboot kills them mid-write
                          #    (stragglers: unio kill <task>)
```

Then tell the foreman to close the books:

```text
End of session. Update ../coord/board.md to the exact current state, add a
CHANGELOG entry for anything merged today that lacks one, and write a
short "NEXT SESSION" note at the top of the board: in flight, blocked,
and the next 1-3 actions. Then stop.
```

```bash
git push                  # 2. the actual save button — code leaves the VM
exit                      # 3. close terminals freely; everything durable is on disk
```

Unfinished worker branches are safe to leave — they're committed in their
worktrees and will still be there next week. The only things that die with
the session are running processes and un-pushed work, which is what steps
1 and 2 exist for.

### What survives what

| Thing | Survives shutdown? |
|---|---|
| Worker branches, commits, reports, board, CHANGELOG | Yes, automatically |
| Foreman chat | Yes via `claude -c`, but degrades — files are canonical |
| Running `-b` tasks | NO — finish or kill before leaving |
| Un-pushed commits | Only on this VM until `git push` |
| Benched/off timers | Yes (global, in ~/.config/unio/off) |

---

## 6. A real example: how the scorecard got built

Historical account: this build used the legacy Frugal Flock command names
before the Unio rename. The quoted brief and commands below preserve that
record; current instructions elsewhere use `unio`.


This is not hypothetical — it's the compressed true story of myapp v0.1.1,
your first shipped product. Every mechanism in this handbook appears in it.

**The brief.** You gave the foreman two sentences: "a command-line tool
that reads a Frugal Flock project's reports and git history and prints a
per-agent scorecard. It exists so I can see which AI worker earns its
seat." Plus a pointer to real reference data: the sandbox project's
reports from the fleet certification.

**The plan.** The foreman studied the reference files, discovered on its
own that `.log` files get overwritten while `.md` reports append (so only
`.md` is a valid history source), hand-computed the correct answers into
an "oracle" table BEFORE any code existed, froze a contract (the shared
data structures nobody but it may edit), and proposed a task split. It
also asked you one genuine decision question — should auth errors count as
"walls"? — instead of guessing. You adjusted two things (count runs not
lines; keep the foreman out of feature code) and said go.

**The build.** Five tasks across five workers, four in parallel:

```text
S1 codex        reports.py   parse the run history
S2 grok         logs.py      count wall-hitting runs
S3 antigravity  gitmerges.py count accepted merges from git
S4 opencode     render.py    print the table
S5 claude       aggregate + cli — wired together AFTER S1–S4 merged
```

While they built, `frugal-flock status` showed four different AI companies
working simultaneously on four modules of one program.

**The failures — all real, all caught.** Codex's first run died with an
expired login; the log said exactly that; `codex logout && codex login`
fixed it. Codex then couldn't commit because its own sandbox blocked git's
worktree metadata — a genuine infrastructure incompatibility, diagnosed
from its honest NEEDS-REVIEW note, fixed with one config line. The foreman
confessed its own contract gap (a missing test file) — two workers
correctly flagged it and waited; one fixed it slightly beyond scope, which
you accepted once and recorded as precedent: flagging beats fixing.

**The gate.** For every branch: `frugal-flock diff <w> --stat` (files match
the assignment?), then the tests run by your own hands, then
`git merge --no-ff`. Five branches in, zero conflicts — because scopes
were disjoint by design.

**The proof.** `./myapp ~/code/sandbox` printed the table, and every
number matched the oracle computed before the code existed. Then you found
a real bug the twelve passing tests missed — the launcher only worked from
inside its own folder — because tests check what was predicted and users
find what wasn't. One pre-approved fix task (S7), one new test, v0.1.1.

**Total human input:** a two-sentence spec, a handful of decisions, diff
reading, and merge commands. Everything else — plan, code, tests, docs,
fixes — was machine work under your gate.

---

## 7. Onboarding an EXISTING project (including production)

New projects start empty; established projects have history, users, and
things that must not break. The recipe differs in three ways: fresh clone,
an onboarding-only first cycle, and stricter safety rules.

**Step 1 — clone fresh into the layout** (never move your working copy):

```bash
cd ~/code && mkdir <proj> && cd <proj>
git clone <repo-url> repo && cd repo
git checkout dev 2>/dev/null || git checkout -b dev   # create dev off main if missing
git push -u origin dev                                # dev must exist on the remote too
unio init codex antigravity                      # start with two workers, always
cp ~/path/to/ai-*.md ../coord/docs/
```

**Step 2 — the onboarding cycle: study only, build nothing.** Open
`claude` in `repo/` and give it this instead of a feature request:

```text
Read MASTER.md and the playbooks in ../coord/docs/. This is an EXISTING
production project. Do not plan any feature work yet. First: run codegraph
init if needed, study the codebase, and produce/refresh the docs/ai/ set
per the setup playbook — START_HERE.md (purpose, how to run, current
state), DECISIONS.md for architecture choices you can infer, GOTCHAS.md
for build/run traps you find. Commit that to dev, then give me a one-page
summary of what this project is, its risk areas, and what kinds of tasks
are SAFE to delegate first. Wait for my go on everything else.
```

This costs one cycle and pays forever: every future worker inherits an
accurate map instead of guessing about a codebase it's never seen.

**Step 3 — safety rules for production work:**

- **Secrets stay out.** Check that `.env` / credential files are
  gitignored BEFORE init — worktrees copy tracked files, and workers run
  with auto-approve. If secrets are tracked in the repo, fix that first.
  `unio init` enforces this: it refuses to scaffold while
  secret-looking files are tracked.
- **First tasks are small and reversible:** a bug fix, missing tests, doc
  updates. Never "refactor the core" on cycle one — you're calibrating
  how well the agents understand this codebase.
- **No deploy automation.** Agents build on branches; you merge to dev;
  what reaches production stays a purely human action, same as today.
- **The gate tightens, not loosens.** On the toy project a soft gate cost
  nothing. Here a bad merge has users. Reject freely.

**Step 4 — then normal operation.** After one or two calibration cycles,
it's the standard loop, and the project's git history + reports start
feeding `myapp <project-root>` like any other.

---

## 8. Maintenance

### Updating the AI CLIs

Unio has no bundled AI — it calls whatever binaries are on your
PATH, so updating a CLI updates the fleet instantly. Update commands:

```bash
claude update
curl -fsSL https://chatgpt.com/codex/install.sh | sh     # codex: rerun installer
agy update
opencode upgrade
curl -fsSL https://x.ai/cli/install.sh | bash            # grok: rerun installer
```

**The post-update ritual (do not skip):** flags move between versions —
it has already happened three times in this system's short life (agy,
opencode, codex). After updating, run:

```bash
unio smoke        # one live call per agent; prints OK / FAIL per row
```

Equivalent manual form, if you want to see the raw output:

```bash
claude -p "say ok"; codex exec "say ok"; agy -p "say ok" --dangerously-skip-permissions
opencode run "say ok" --auto; grok -p "say ok" --always-approve
```

If one fails with a usage/flag dump: `<binary> --help`, find the renamed
flag, fix that agent's line in `~/.config/unio/agents.conf`. One
line, two minutes — the drill you already know. Sensible cadence: monthly,
or when a worker starts behaving oddly.

### Updating Unio itself

Re-run `bash unio-install.sh` anytime: it overwrites the `unio`
command and templates with the newest versions but NEVER touches your
`agents.conf` (your tuned flags survive). Existing projects keep their
old MASTER.md/WORKER.md copies; new projects get the new templates. After
big template changes, paste the new sections into important existing
projects' MASTER.md by hand if you want them (re-running
`unio init <worker>` in a project refreshes that worker's card).

After any Unio update, run `unio selftest`: the entire loop —
init, run, verify, bench, lock, background + kill, sync, review —
rehearsed with mock agents in a throwaway sandbox. Zero quota, about
fifteen seconds, and it exits red if the machinery broke.

### Updating myapp (the scorecard)

It's a normal project of yours: new features = new task cycles through
its foreman (backlog: multi-project scan, HTML output, bench watching);
code updates on another machine = `git clone`/`git pull` from
github.com/danielmevit/myapp. No dependencies to maintain — standard
library only, by design.

### Backups, standing policy

Code: `git push` at session end — that's everything that matters.
Config: `tar czf /mnt/c/Users/dmite/unio-conf.tgz -C ~ .config/unio`
after conf changes (a few KB). Full VM export: optional, only when disk
allows; the rebuild path (installer + five logins, under an hour) is
documented and acceptable.

---

## 9. Troubleshooting, condensed

| Symptom | Cause → fix |
|---|---|
| `not inside a Unio project` | Wrong folder — cd into the project (it searches upward for coord/ + wt/). |
| Worker fails instantly, log shows a flag/usage dump | CLI updated, flag renamed → `--help`, fix agents.conf line. |
| Worker fails, log says token/login expired | `<cli> logout && <cli> login`, rerun. |
| Worker hangs | Waiting on a prompt auto-approve didn't cover, or agy's 5-minute default print timeout → check the .log. |
| Log mentions rate/usage limit | `unio off <agent> 5h` (weekly: 7d), foreman reroutes. |
| Report says done, diff shows uncommitted work | Worker forgot to commit → commit it yourself in `wt/<w>`, or rerun with sharper Done-means. |
| Report says done, diff looks wrong | Normal. Reject; foreman re-briefs. The system working. |
| `worker … is already running a task` | The per-worker lock: one run per workshop at a time → `unio status` to see what; stray background run: `unio kill <task>`. |
| verify says SCOPE VIOLATION | The worker left its lane → reject the branch, re-brief with corrected scope. Never merge a violating diff as-is. |
| verify FAIL while the report claims success | Working as designed — the report lied, the machine caught it. Trust verify. |
| verify says INCOMPLETE (exit 2) | The task has no "- path" scope lines or no "$ " Validate lines, or the worktree changed while the checks ran → fix the task through the foreman, or rerun verify. It is never a PASS. |
| review: "requires current passed validation" | Run verify first; any edit, commit or task change since the last PASS makes it stale. |
| review: "incomplete review material" | Commit all staged, unstaged and untracked work; binary or oversized diffs need your own manual inspection. |
| "unsupported assume-unchanged/skip-worktree index flags" | Those git flags hide edits from scope and review → `git update-index --no-assume-unchanged --no-skip-worktree <path>` or `git sparse-checkout disable`. |
| run: "post-run snapshot failed" | The worker left a FIFO, socket, device, nested repo or submodule. Its exit is recorded but the result stays not ready → remove the file, run again. |
| "Python 3 is required before run/review/smoke" | Install `python3` (standard library only, nothing else is downloaded). |
| git complains about `index.lock` | Existing lock detected at startup → `unio run` refuses startup to protect active Git processes; inspect manually and ensure no Git writer is active before removing `<gitdir>/index.lock`. |
| "name must not contain a path separator / `..`" | Safety guard on worker/task ids (they build paths under `wt/` and `coord/tasks/`) → use the bare id, e.g. `T7-codex`. |
| init: "this repo has no commits yet" | Worktrees branch from a commit → `git commit --allow-empty -m init`, then `unio init`. |
| Two workers touched the same file | Scope overlap — accept one, reject the other, tell the foreman to fix disjointness. (Exception: a deliberate `race`, where only one branch merges anyway.) |
| Everything on fire | `unio stop`, read status + reports, `resume` when understood. |

---

## 10. The document map

Everything lives in [Unio](https://github.com/danielmevit/unio),
the repository historically called Frugal Flock and `agentteam-docs`. Clone it, run
`bash unio-install.sh`, and sign in to the coding CLIs you choose
to use. You can start with one; all five are not required.

- **docs/GUIDEBOOK.md** — the complete manual: every feature explained
  from scratch, step-by-step usage, exhaustive troubleshooting, command
  and settings references, glossary, cheat sheet. Start there if you (or
  anyone else) need the long form; this handbook is the terse twin.
- **This handbook** (docs/HANDBOOK.md) — daily operations, all commands,
  session rhythm, the worked example.
- **docs/EXAMPLE.md** — the replayable tour of every command against a
  toy project with stand-in agents; rerun it anytime with
  `bash examples/demo.sh /tmp/unio-demo` (zero quota).
- **docs/SETUP.md** — the compact install/setup reference.
- **docs/MASTER-PLAN.md** — the deep explanation for a beginner + the
  phased roadmap; dictionary of every technical term.
- **unio-install.sh** — the installer; run it, don't read it.
- **Your playbooks** (`ai-project-setup-playbook.md`,
  `ai-full-build-recipe.md`) — the working standard every foreman follows.
- **multi-agent-claude-review.md** — the original research: why this
  architecture, terms-of-service analysis, alternatives, sources.
