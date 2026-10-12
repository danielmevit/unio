# Build a new project using Unio

Use the installed Unio tool to coordinate AI workers building your own app,
website or other project. This starts a fresh project; it does not continue
development of Unio itself.

## Start from an empty folder

With Unio and your chosen AI CLI already installed, open a new Linux or WSL
terminal. Replace `my-new-project` with your project name:

```bash
mkdir -p "$HOME/code/my-new-project/repo"
cd "$HOME/code/my-new-project/repo"
claude
```

Use your preferred capable AI CLI instead of `claude`. The new lead will
initialize Git and Unio after reading your brief. No existing repository,
GitHub account setup or clone of Unio's source is needed. If the folder
already contains work, the lead must preserve it.

## Paste this into the new AI session

Fill in the project brief and accounts already occupied by other sessions:

```text
You are the lead for a brand-new project. Use the installed Unio CLI to
coordinate multiple AI workers building this project. Unio is the tool
we are using; we are not modifying Unio or continuing its development.

Project brief: [what I want to build, for whom, and any constraints]
Accounts already occupied by other sessions: [list them, or none]

Start in this folder. Inspect and preserve any existing files and local
instructions. Read Unio's installed lead guides under
~/.config/unio/templates/, starting with LEAD-ROUTING.md and its references.
Use the configuration location from unio version if it differs.
Do not import the Unio development repository's tasks or milestone handoff.

Give me an initial plan and time estimate. Initialize a local Git repository
if needed and make the first commit required by Unio. Set up this project's
own coord/ and wt/ beside repo/ using unio init with explicitly chosen,
configured workers. Preserve existing work; do not reclone it.

Use YOLO work mode and low tier: focused useful checks, concise lead review,
and one independent workflow per shared subscription, including the lead.
Register your configured lead alias and group aliases sharing one account.
Respect accounts occupied in other projects; native slots are workspace-local.
Check local worker facts without treating installed tools as spare quota.

Open this project's managed Unio dashboard and give me its actual URL.
Delegate implementation to available capable subscription workers through
Unio task files and native runs. Free models are routine support, not leads.
Start effort at high or the supported middle; xhigh is the ceiling.
No max/ultra, extra paid-token fallback, billing or authentication changes.

Resume before authorized worker runs and stop new runs after the cycle.
Verify actual changes and relevant behavior before claiming completion.
Give regular progress updates, commit coherent work early, and maintain
this project's own coordination log and handoff. Continue agreed work
through checkpoints; ask only for genuinely missing decisions or authority.
```

For example, when a Codex lead is already developing Unio in another session,
list the Codex account as occupied. A different project does not create a new
subscription allowance. Native Unio locks do not count other workspaces.

Use the new project's dashboard URL, not a development dashboard for Unio.
Existing sessions can stay open; their lead reservations and project files
are independent.

For an existing checkout or a remote repository, see
[separate project sessions](START_HERE.md#start-a-separate-project-session).
To continue work on Unio itself later, use the separate
[Unio development handoff prompt](../development/continue-with-ai-prompt.md#prompt-for-the-next-unio-development-lead).
