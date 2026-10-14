# Unio — your 5-CLI team on one Ubuntu VM

One master CLI session (default: Claude Code) delegates coding tasks to
worker CLI agents (Codex, Antigravity, OpenCode, Grok Build), each
running headless in its own git worktree under its own subscription login.
No API keys, no browser automation.

Built around Daniel's operating standard (`ai-project-setup-playbook.md` +
`ai-full-build-recipe.md`): dev/main branch model, AGENTS.md router +
docs/ai/, CodeGraph for structure, verified milestones, strict commit
hygiene. v2 tested end-to-end 2026-07-10 (init on a dev-branch repo →
delegate → run → report → diff → off/on quota switch → limit auto-detect →
stop/resume). Headless syntax per CLI verified against official docs the
same day — sources at the bottom.

## Lego principles

- **One agent = one line** in `agents.conf`. Add, remove, or re-tune agents
  without touching anything else.
- **One switch per agent**: `unio off codex 5h` when it burns its
  5-hour window, `off codex 7d` for a weekly cap, `on codex` to re-enable.
  Expiries clear themselves; the master reroutes around OFF agents.
- **Master is whoever you launch** in the repo dir — the role card is
  symlinked as CLAUDE.md, AGENTS.md, and GEMINI.md, so any CLI picks it up.
- **Per-project overrides**: `coord/agents.conf` beats the global config;
  `coord/base` sets the integration branch.

## 1. Install (once, on the VM)

```bash
bash unio-install.sh
# ~/.local/bin must be on PATH (Ubuntu default; otherwise:)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc && source ~/.bashrc
unio selftest       # rehearse the whole loop with mock agents — no quota
unio version        # confirm what's installed
```

Tab-completion (commands, workers, tasks, agents) installs automatically;
open a new shell to pick it up.

Requirements besides the AI CLIs: `git`, `flock` (util-linux, preinstalled
on Ubuntu) and Python 3. Python is used only through its standard library,
for the revision-bound evidence; nothing is downloaded or pip-installed.
`run`, `verify`, `review`, `result`, `handoff`, `agents` and `smoke` look
for `python3` first and stop with "Python 3 is required before
run/review/smoke" before any provider starts. Check with
`python3 --version`; on a minimal image, `sudo apt install python3`.

## 2. Log in each CLI once (interactive, one time)

Headless runs reuse cached credentials. On a GUI-less VM most logins print
a URL + code you open in the browser on your Windows host.

| Agent | Install | Login | Verify |
|---|---|---|---|
| Claude Code | `npm i -g @anthropic-ai/claude-code` | `claude` | `claude -p "say ok"` |
| Codex | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh` | `codex` → ChatGPT account | `codex exec "say ok"` |
| Antigravity | install per antigravity.google (`agy` binary) | `agy` → Google account (prints URL + code over SSH) | `agy -p "say ok"` |
| OpenCode | `curl -fsSL https://opencode.ai/install \| bash` | `opencode auth login` (Go) or `/connect` (Copilot) | `opencode run "say ok"` |
| Grok Build | `curl -fsSL https://x.ai/cli/install.sh \| bash` | `grok` → xAI/X sign-in | `grok -p "say ok"` |

Antigravity note: Google shut down Gemini CLI on 2026-06-18; Antigravity CLI
(`agy`) is its replacement and fills the Google seat. Unattended syntax,
verified on a live install 2026-07-17:
`agy -p "..." --dangerously-skip-permissions --print-timeout 55m` — the
print-mode timeout defaults to just 5 minutes, hence the override. The tool
is young; recheck `agy --help` after updates. If background runs act odd,
read the task .log first.

CodeGraph (your standard): wire agents once per the playbook —
`codegraph install -t claude,codex,opencode,antigravity`. Grok has no
CodeGraph target; it uses shell `codegraph explore "..."` (the worker card
says so). `unio init` indexes a new worktree only when your clone is
itself indexed (there is a `.codegraph/` in `repo/`), and it does that in the
background, time-boxed by `UNIO_CG_INDEX_TIMEOUT` (default 600s). An
unindexed repo stays unindexed — that is your call, not the tool's.

## 3. Set up a project

One command does the whole recipe below (clone → dev → init → playbooks
from `~/.config/unio/playbooks/`):

```bash
cd ~/code && unio new <repo-url> myproj
```

Or step by step:

```bash
cd ~/code && mkdir myproj && cd myproj
git clone <your-repo-url> repo && cd repo
git checkout dev                       # your model: dev = work, main = releases
unio init codex antigravity opencode grok
unio agents                       # every row: OK + on
cp ~/path/to/ai-*.md ../coord/docs/    # your playbooks -> master's reading ritual
```

Layout created next to the clone:

```text
myproj/
├── repo/          # your clone on dev — master session runs HERE
│   └── MASTER.md  #   symlinked as CLAUDE.md / AGENTS.md / GEMINI.md
├── wt/
│   ├── codex/     # worktree, branch agent/codex (forked from dev), WORKER.md
│   ├── antigravity/ # ... same per worker; bg-indexed if repo/ is indexed
│   ├── opencode/
│   └── grok/
└── coord/
    ├── base       # integration branch (auto-detected: dev)
    ├── docs/      # YOUR playbooks — master reads these first
    ├── board.md   # master-owned task board
    ├── tasks/     # task specs (TEMPLATE.md included)
    ├── reports/   # auto-generated run reports + full logs
    └── blockers.md
```

Role cards and `.codegraph/` are excluded via `.git/info/exclude` — the repo
stays clean. If the repo already has its own AGENTS.md router (your standard
setup), init does NOT overwrite it; it tells you to add one line: "Also read
and follow MASTER.md." Workers are likewise told to follow the repo's
AGENTS.md reading ritual, with Unio boundaries taking precedence.

### Project-root boundary

Commands that act on a project (mode/tier/lead/account, stop/resume, run,
verify, ...) select it by walking up from your physical current directory
(including after a logical shell `cd` through a symlink) to the
nearest `coord/` + `wt/` pair. On the way up they remember the first Git
boundary (a `.git` — a full repository, a fresh `git init` with no commits
yet, or a linked worktree's `.git` file). That boundary must belong to the
project found: its main clone (any name, directly under the project root)
or a direct child worktree under `wt/`, including pre-marker worktrees.
A `.unio-worker` file elsewhere does not authorize selecting the enclosing
project. Anything else is an unrelated nested Git repository — for example
something you cloned into the
workspace scratch or into a vendor directory — and Unio refuses to act on
the enclosing project from inside it, before touching any policy, lock or
provider:

```text
unio: refusing to act on the enclosing project from inside an unrelated Git repository
```

The refusal tells you the two ways out: `cd` into the enclosing project
(or any non-Git directory inside it, such as `coord/` or the scratch), or
`cd` to the nested repository's own root and run `unio init` there to give
it its own workspace. Unio never initializes, resets policy or fabricates
identity for you. An initialized nested workspace is selected normally
from inside it, and commands that take an explicit project path (e.g.
`unio score <project-root>`) are unaffected.

This is an accidental-selection layout guard, not a sandbox or repository
authentication. An independent clone directly under the project root or
`wt/` still fits the supported legacy topology and is allowed.

## 4. Run a cycle

```bash
cd ~/code/myproj/repo
claude        # or codex / agy / grok — whatever opens here IS the master
```

First time with an AI as the master? Set up its permissions once (§9), or
its own safety system may stop it from running `unio` commands.

First prompt to the master:

```text
Read MASTER.md and the playbooks in ../coord/docs/. I want: <feature/fix>.
Check unio agents, propose a task breakdown, and wait for my "go"
before delegating. Then run the cycle and end with a merge recommendation.
```

The master (or you, in a second terminal) drives everything with:

```bash
unio run codex T1-codex        # run a task (foreground)
unio run -b grok T2-grok       # long task in background
unio tail T2-grok              # watch a background run live
unio kill T2-grok              # stop a background run
unio status                    # off-agents, tasks, review queue, jobs
unio verify codex T1-codex     # machine gate: scope + Validate + commits (exit 0/1/2)
unio diff codex                # the REAL diff vs dev — reports can lie
unio review codex T1-codex     # a rival vendor reviews the committed diff (exit 0/1/2)
unio result codex T1-codex     # stored evidence as JSON: ready_for_human_review?
unio handoff codex T1-codex    # context packet for the next AI, same checkout
unio sync                      # after merges: refresh all workshops
unio race T5 codex grok        # bake-off: two vendors, one task, one winner
unio sabotage opencode         # saboteur seat: failing tests vs fresh merges
unio off antigravity 5h        # it hit its window -> bench it
unio stop                      # kill switch for the whole project
```

### Work modes and coordination budget

Read the [work modes guide](WORK-MODES.md) and run `unio policy`
before planning. `unio mode [yolo|medium|safe]` sets the pace (default
`medium`); `unio tier [low|medium|high]` sets the coordination budget
(default `low`: one independent workflow per shared budget, lead
included; `medium` 2, `high` 4). Register the lead with
`unio lead <agent>` and group aliases sharing one budget with
`unio account <agent> <group>`. These settings provide guidance and enforce concurrency natively via strict budget slots. The installed copy lives at
`coord/docs/WORK-MODES.md` after `unio init`.

You merge, nobody else — into dev, per your model:

```bash
cd ~/code/myproj/repo
git merge --no-ff agent/codex       # after the milestone gate passes
```

Acceptance gate (from your recipe, enforced by MASTER.md): `unio
verify` PASS + clean build (0 warnings where the repo enforces it) +
tests green + smoke run + changelog fragment (`changelog.d/<ID>.md` —
workers never edit CHANGELOG.md itself) — only then is a branch
merge-ready. main is touched only on an explicit release.

Exit codes: `verify` returns 0 for PASS, 1 for a real failure and 2 for
INCOMPLETE evidence (no `- path` scope lines, no `$ ` Validate lines, or the
worktree changed during the checks). `review` runs only after a current
passed verify and returns 0 for approval, 1 for requested changes or a
failed reviewer process, and 2 for an unknown verdict or incomplete
material. `result` prints the stored evidence; `ready_for_human_review`
is never your acceptance. Details: [QUALITY-USAGE.md](QUALITY-USAGE.md).

If Claude Code asks approval for every Unio call, allow once in
`repo/.claude/settings.json`:

```json
{ "permissions": { "allow": ["Bash(unio *)"] } }
```

## 5. The quota switch (5-hour and weekly limits)

When an agent exhausts its plan window, bench it — everything else keeps
running:

```bash
unio off codex 5h    # 5-hour window burned; auto-ON when it resets
unio off grok 7d     # weekly cap burned
unio off opencode    # off until you say otherwise
unio on codex        # manual re-enable anytime
unio agents          # shows on/OFF + auto-on countdown per agent
```

Mechanics: `run` refuses OFF agents with a clear message, expired timers
clear themselves, `status` lists benched agents first. A failed run's
normalized final 60 log lines can trigger a suspected-limit warning and
an `off` suggestion. A nonzero exit or empty work qualifies for this
helper; the real exit remains in receipts. Check actual provider state
before benching explicitly. `UNIO_AUTO_OFF` has no effect: worker output
never changes availability, and the warning is not confirmed quota data.
MASTER.md tells the master to check availability before delegating and
reroute by the fallback policy (codex→claude/grok, antigravity→codex,
grok→codex, opencode→any idle) — work never queues on a dead agent.

## 6. Tuning agents

`~/.config/unio/agents.conf` (or per-project `coord/agents.conf`):
one line per agent, `$TASKFILE` holds the task path, command runs inside
the worker's worktree.

```text
opencode=opencode run --auto -m opencode-go/glm-5.3 "Your complete task is the attached UTF-8 file. Before acting, read the ENTIRE file, every chunk through its last line; never act on a partial read. Then do exactly what that file asks. File: $TASKFILE" --file "$TASKFILE"
```

Pass the task by stdin or by file, never as one argument. Linux limits a
single argument to about 128 KiB, and a large task or review material
fails with `Argument list too long` before the agent starts. Fresh
installs ship these lines (each flag checked against the installed
`--help` on 2026-10-06):

```text
claude=claude -p --dangerously-skip-permissions < "$TASKFILE"
codex=codex exec --sandbox danger-full-access --skip-git-repo-check - < "$TASKFILE"
grok=grok --prompt-file "$TASKFILE" --always-approve
opencode=opencode run --auto "<pointer message>" --file "$TASKFILE"
antigravity=agy -p "<pointer message> File: $TASKFILE" --dangerously-skip-permissions --print-timeout 55m
```

Claude and Codex read the whole file on stdin, and Grok reads it with
`--prompt-file`. OpenCode attaches the file with `--file`. `agy` has no
prompt-file flag, so its short prompt names the file and tells the agent
to read ALL of it, every chunk, before acting. The pointer message in
`agents.conf` asks for that full read; keep it if you edit the line.

Before spending a provider run, use `unio doctor --commands` or
`unio doctor --commands --json` for a local static command audit. It works
outside projects and under STOP, reads the project override when present,
and executes no configured command. See [usage and limits](WORKER-CONNECTIONS.md).

Reinstalling never rewrites an existing `agents.conf`. Older lines that
contain `"$(cat "$TASKFILE")"` keep working for small tasks, but
`unio doctor` warns about each one and shows the replacement. It only
reads the file: it runs nothing and changes nothing. Edit those lines
yourself. Your own wrapper commands are yours to maintain. This change
does not raise a provider's own context limit.

Current installed OpenCode help (checked 2026-10-04) advertises `--auto`;
the older permission flag is absent. GLM 5.3 and Kimi K3 canaries used it.
Fresh source installs use `--auto`; reinstalls keep existing profiles and
model choices. Check `opencode run --help` and edit only your OpenCode
entries if needed. Doctor flags direct entries with the legacy option
without executing commands; shell wrappers may need manual inspection.
The Unio installer copies the legacy config folder once when the new default
folder is absent and no config override is supplied. It preserves configured
provider commands; it does not rewrite custom shell wrappers or provider flags.

Two workers on one engine: `unio init codex-2` (prefix before the dash
picks the agent). Timeout: `UNIO_TIMEOUT=7200 unio run ...`.

## 7. Read this before you scale up

- **Workers run with auto-approve flags** (`--dangerously-skip-permissions`,
  `--yolo`, `--always-approve`, `workspace-write`). Acceptable *because*
  this is an isolated VM — keep it that way: push branches to the remote
  often, snapshot the VM, no production credentials on it.
- **Basic plans are small.** Every delegation burns that vendor's quota and
  the master burns Claude quota planning and reviewing. Start with master +
  codex, count accepted diffs, then add agents. A worker whose diffs keep
  getting rejected costs more than it produces — bench it permanently.
- **Task files are the whole interface.** Workers have no memory of the
  master's chat. Vague task file = garbage diff. TEMPLATE.md's sections are
  the minimum, not bureaucracy.
- **Commit hygiene is enforced by prompt, verified by you**: workers are
  told to stage only their own files (no blind `git add -A`) and to add a
  CHANGELOG entry. The diff shows whether they obeyed.
- **Grok Build is a beta** (2026-05-25). If a run fails instantly, check
  `grok --help` and fix the conf line.
- **Always read the diff.** The report's output tail is the agent's claim;
  `unio diff <worker>` is the truth.

## 8. Troubleshooting

- `not inside a Unio project` — run from the clone or any project
  subdir (it searches upward for `coord/` + `wt/`).
- Worker hangs → an approval prompt its auto-approve flag didn't cover, or
  expired login. Check `coord/reports/<task>.log`, re-login that CLI, verify
  with the §2 one-liner.
- Nonzero exit + near-empty log → not logged in or wrong flag;
  `unio agents` + §2 verify commands isolate it fast.
- Codex edits files but can't commit ("index.lock" / .git not writable) →
  its workspace-write sandbox keeps .git read-only, and a worktree's git
  metadata lives in the main repo's .git/worktrees/. The conf uses
  `--sandbox danger-full-access` for exactly this reason — don't "harden"
  it back to workspace-write, it breaks worktree commits.
- Wrong integration branch → edit `coord/base`.
- "Python 3 is required before run/review/smoke" → install `python3`
  (standard library only); see §1.
- `agents` shows `installed=unknown` → normal for conf lines whose program
  is hidden by shell syntax: pipes, `;`, output redirects, or wrappers such
  as `bash -c`. A plain `< "$TASKFILE"` input redirect and quoted
  arguments keep the program known. It never runs them to find out.
  `unio doctor` checks that each worker's program is on PATH.
- WSL `/mnt` quirks from your GOTCHAS don't apply on the native-ext4 VM;
  if you ever move this workflow to WSL-on-Windows-drive, re-add
  `codegraph sync` after edits and `git config core.filemode false`.
- The master AI asks before every `unio` command, or its tool
  refuses to run one → that is the tool's own permission system; set up
  §9. A refusal printed by Unio itself (`STOP is active`, an agent
  that is `OFF`, a worker `already running a task`) says why; check
  `unio status`.

## 9. Lead AI permissions

The master (lead) is the AI session you open in `repo/`. It plans, writes
task files in `coord/tasks/`, and runs `unio` commands;
`unio run` then starts the worker AIs with their own approval flags
(§2). AI coding tools guard the commands their own session runs, and some
treat "start another AI" or "push to GitHub" as risky. What you meet
depends on how the lead runs:

| How the lead runs | What happens |
|---|---|
| You type the `unio` commands yourself | Nothing to set up; the AI only plans and reviews. |
| Claude Code, default mode | It asks before each new kind of command. "Don't ask again" saves a rule. |
| Claude Code, auto mode | A safety check decides each command. Some are refused until you add a rule. |
| Claude Code with `--dangerously-skip-permissions` | No checks at all inside the lead session. |
| Codex, Antigravity or Grok as the lead | Their own approval or sandbox settings decide; see each tool's docs. |

Whatever the tool, the lead needs to write in `repo/` and `coord/` and run
`unio`. It does not need to push or merge.

### The lasting fix for Claude Code: allow the flock commands

Create `repo/.claude/settings.local.json` once, with the full path to your
project's `coord/` folder:

```json
{
  "permissions": {
    "allow": [
      "Bash(unio *)"
    ],
    "additionalDirectories": ["/home/you/code/myproj/coord"]
  }
}
```

Keep this personal file out of Git without editing `.gitignore`, then
restart the lead, because settings are read when a session starts:

```bash
cd ~/code/myproj/repo
echo ".claude/settings.local.json" >> .git/info/exclude
```

What these settings do and do not do:

- The lead may run any `unio` subcommand, including `run`, `sync`
  and `kill`, without asking. Every worker starts through `unio
  run`, so the lead never needs to call `codex`, `grok` or the others
  directly.
- `additionalDirectories` lets it work with the task files in `coord/`,
  which sits next to `repo/`, as part of the project.
- It is not a sandbox. Workers still run commands with your rights. The
  lead writes each task's Validate lines, and `unio verify` runs
  them without a separate prompt, so read those lines when you approve the
  lead's plan, before any work starts.
- `git push`, merges and the lead's own settings are not covered. In
  default mode they keep asking; approve them one at a time, never with
  "don't ask again". In auto mode the safety check decides. Add rules
  yourself: auto mode refuses a lead's attempt to edit its own permissions.
- A rule matches how a command starts. Put per-project agent commands in
  `coord/agents.conf`, which overrides `~/.config/unio/agents.conf`,
  instead of starting commands with a variable such as
  `UNIO_CONF_DIR=...`.

### Why not skip permissions?

`--dangerously-skip-permissions` turns off every check in the lead
session: it can then run any command, push or delete without asking. Use
it only on a disposable VM that holds this project and nothing else, never
on an everyday machine with other projects, Git credentials and keys. The
worker AIs are unaffected either way; they always run with their own
approval flags (§2).

## Sources (verified 2026-07-10)

- Claude Code CLI: https://code.claude.com/docs/en/cli-reference
- Codex non-interactive (`codex exec`, `--sandbox workspace-write`): https://developers.openai.com/codex/noninteractive
- Codex CLI + plans: https://developers.openai.com/codex/cli
- Gemini CLI shutdown / Antigravity transition: https://developers.googleblog.com/an-important-update-transitioning-gemini-cli-to-antigravity-cli/
- Antigravity CLI hands-on (`agy -p`, headless): https://dev.to/arindam_1729/antigravity-cli-a-hands-on-guide-to-googles-terminal-coding-agent-5bc7
- agy headless/CI quirks: https://antigravitylab.net/en/articles/integrations/antigravity-cli-headless-non-interactive-ci-design
- OpenCode CLI (`run`, `--auto`, `-m`): https://opencode.ai/docs/cli/
- OpenCode Go plan: https://opencode.ai/go
- Grok Build (`grok -p`, `--always-approve`): https://x.ai/news/grok-build-cli and https://mer.vin/2026/05/grok-build-cli-xai-terminal-coding-agent-with-plan-mode-subagents-and-headless-ci/
- Antigravity official docs: https://antigravity.google/docs/cli-using

## Optional managed Codex Source

For one-turn app-server execution and truthful future-turn effort requests, see
[managed Codex Source](WORKER-EFFORT.md). Existing Codex exec defaults stay unchanged.
The standalone installer packages the helper and guide in its lib directory.
