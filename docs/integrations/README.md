# Optional subscription adapters

Vibe and Perplexity ship with Unio 0.5.8 and later. Copilot Free / Auto Balance
joins them in 0.5.9. The Antigravity worker is the fourth optional adapter in
the unreleased 0.5.18 candidate. The published installer remains 0.5.17 and
does not yet install that fourth helper. All four run from a source checkout.
Install and sign in to the
external tool manually; the adapter does not purchase credits, change billing or
fall back to another paid service.

## Where the adapters live

| Adapter | Source checkout | Installed copy |
| --- | --- | --- |
| Vibe worker | `tools/vibe-worker.py` | `~/.config/unio/lib/adapters/vibe-worker.py` |
| Perplexity worker | `tools/perplexity-worker.py` | `~/.config/unio/lib/adapters/perplexity-worker.py` |
| Copilot worker (0.5.9+) | `tools/copilot-worker.py` | `~/.config/unio/lib/adapters/copilot-worker.py` |
| Antigravity worker (0.5.18 candidate) | `tools/antigravity-worker.py` | `~/.config/unio/lib/adapters/antigravity-worker.py` |

The standalone installer copies the exact reviewed adapter bytes to
the installed path above (or under `$UNIO_CONF_DIR/lib/adapters`). With 0.5.7 or
earlier, use the source-checkout path or upgrade; Copilot needs 0.5.9 or its
source-checkout helper. Installing Unio installs no
Vibe, Perplexity connector or other external
dependency, and starts no model.

To see what is present, run:

```bash
unio integrations          # human-readable
unio integrations --json   # schema_version 1
```

It reports each adapter's role, installed path, whether that file is present
and its setup guide. It only reads local file metadata: it loads no adapter or
dependency, reads no token or config contents, makes no network or model
request and writes nothing. It works outside a project and while STOP is set.
`installed: true` means only that the file exists; authentication and capacity
remain `unknown`. `--json` needs Python 3, run isolated with the standard
library `json` module only. The command never launches an adapter: you still
add an explicit `agents.conf` alias, map it to its budget with `unio account`
and start it with `unio run`, so native per-budget slots stay in force.

| Route | Use it for | Guide |
| --- | --- | --- |
| Mistral Vibe 2.26.1 | Implementation tasks using GLM 5.3 or Mistral Medium 3.5, explicitly pinned at high effort | [Vibe worker setup](MISTRAL-VIBE.md) |
| Copilot Free / Auto Balance | Routine documentation and small mechanical proposals; local/BYOK models excluded | [Copilot setup](GITHUB-COPILOT.md) |
| Perplexity Pro web | Research and draft code proposals using GLM 5.3, Kimi K3 or the connector's GPT-6 Sol Thinking route | [Perplexity setup and proposal workflow](PERPLEXITY-WEB.md) |
| Antigravity / agy 1.3.5 | Implementation tasks on the fixed Gemini 3.8 Flash high/medium/low selectors, with the CLI process exit kept separate from the structured terminal verdict | [Antigravity setup](ANTIGRAVITY.md) |

Perplexity supplies research, citations and proposed code from selected context.
A capable implementation agent checks that proposal, applies suitable changes
in its own Unio worktree and runs the assigned validation. The lead reviews
the actual diff and evidence. Generating a proposal does not accept a change.
The adapter never executes suggested commands or applies a patch automatically.

Keep aliases on the same subscription in one shared budget group. Perplexity,
Mistral Vibe and OpenCode are separate account routes even when they offer the
same underlying model. In low tier, each shared budget permits one independent
native workflow, including a lead when that account hosts it. For example,
after adding the aliases from each guide:

```bash
unio account vibeglm mistral
unio account vibe35 mistral
unio account perplexityglm perplexity
unio resume
UNIO_TIMEOUT=5460 unio run vibeglm-feature TASK-ID
unio stop
```

Both adapters passed focused offline tests. The corrected Vibe wrapper also
made a real GLM 5.3 implementation run: it saved an early commit, then reported
a connection failure with native exit 2. Opus completed that saved packaging
work and passed four native checks. This is not a model-quality ranking.

A genuine Perplexity request on the GLM 5.3 Thinking route succeeded for one
owner's Pro account. Its readiness proposal referenced missing code attachments,
so it is incomplete and its claimed tests are unverified. Proposal prompts now
request code inline; the adapter does not download generated attachments.
A separate Kimi K3 request returned both code files inline. Local inspection
and its proposed tests found one incorrect fixture, so that draft remains
unmerged. Text delivery does not establish implementation correctness.
Remaining allowance and effective model identity stay Unknown. The pinned
connector names GPT-6 Sol, not GPT-6.1 Sol; do not silently equate the two.

Use the [agent fleet guide](../development/AGENT-FLEET.md) to assign all
approved accounts without duplicating their shared-budget workflows.
