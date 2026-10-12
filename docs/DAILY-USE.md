# Everyday use

Unio coordinates your AI coding tools. You start the lead AI separately and
use Unio to delegate tasks and follow their recorded progress.

## Open your project

In Linux or WSL, open a terminal in the `repo` folder of an initialized Unio
project. Its neighbouring `coord` and `wt` folders hold coordination records
and worker worktrees.

```bash
cd 'my-project/repo'
unio version
```

Replace `my-project/repo` with your project's path. `version` shows the
installed version and configuration location. Typing just `unio` displays
command help and exits; that is expected.

## Open the dashboard

```bash
unio dashboard ensure --open-browser
```

Open the exact local URL it prints. Unio chooses the port and reuses an
existing managed dashboard. If the browser does not open automatically,
paste that URL into your browser. To find it again:

```bash
unio dashboard status
```

The dashboard runs independently of your lead's conversation. It stays up
until stopped and shows recorded Unio activity; it does not capture an
arbitrary AI chat. The default connection is local and read-only. Phone
pairing is not included.

## Start the lead AI

Start your preferred AI coding CLI, such as `codex`, in the same repository.
Paste the [README startup prompt](../README.md#start-with-your-ai), followed
by the task you want done. The [AI startup guide](ai/START_HERE.md)
explains the local checks and how to register the lead's configured alias.
For another project, open a separate terminal in its own workspace and follow
[separate project sessions](ai/START_HERE.md#start-a-separate-project-session).
Your other sessions can stay open. When replacing the lead on this same
project, finish its handoff and end its coordinating session first, then follow the
[lead-switch steps](ai/START_HERE.md#switch-to-a-different-lead).

Unio does not start that conversation for you or attach an existing one
automatically. The lead reads your instructions and uses Unio's commands
to coordinate workers.

## Follow the work

Use the task list or work map to inspect tasks, worker output and files.
Both views share search and state, worker and category filters. Task details
show Run, Checks and Review separately: a successful run alone does not
prove a change is ready. Copy-command buttons copy text; they do not run it.

In the terminal, these commands observe existing work without starting an AI:

```bash
unio watch
unio tail TASK-ID
unio report TASK-ID
```

Replace `TASK-ID` with a real task name. Ctrl-C exits the watcher or log
viewer without stopping the worker.

The agents and limits section shows recorded allowance readings with their
source and age. Missing or stale data stays Unknown. `unio agents` reports
configured tools and on/off state; an installed tool is not proof of sign-in
or spare allowance. Browser polling does not refresh providers or make model
calls.

## Pause or finish

```bash
unio stop
```

This blocks new Source and review runs. Already-running tasks continue until
they finish or reach their existing timeout. Run `unio resume` when you want
to permit new work again; resuming does not start workers by itself.

To stop only the managed dashboard:

```bash
unio dashboard stop
```

This leaves workers running. For more detail, see [setup](SETUP.md),
[saving work](WORK-SAVING.md), [optional integrations](integrations/README.md)
and the [browser guide](../bridge/README.md).
