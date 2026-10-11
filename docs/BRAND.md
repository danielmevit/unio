# Unio

Your AIs, in sync.

## Name and promise

The owner selected Unio as the product name and approved the
tagline above. Unio connects AI agents from different AI labs
into one workspace through their coding tools: one AI leads, the others work as its
subagents in separate copies of the project, and a person approves what is
merged. Unio means union or oneness: a team of AI agents from different AI labs, run
frugally on the plans people already have.

Independent reviews support security and code quality; bounded tasks,
checks and durable handoffs support efficient work. These benefits depend
on the chosen workflow and evidence, rather than the number of agents.

The promise is to reduce the interruption and coordination work caused by
limited plans. Provider limits still apply. More agents do not guarantee
better code, and using a different provider does not transfer the first
provider's quota or conversation memory.

## Naming contract

| Surface | Name |
|---------|------|
| Product and window title | Unio |
| Tagline | Your AIs, in sync. |
| One-sentence description | Connect AI agents from different AI labs into one workspace |
| Canonical terminal command | `unio` |
| Installer entrypoint | `unio-install.sh` |

Tagline approved by the owner on 2026-10-08. Description selected on 2026-10-06. Keep the README and the following
intended GitHub description consistent; changing this document alone does
not update repository metadata. The topics below were set on 2026-10-04:

- Description: "Bring AI agents from different AI labs into one team. A lead
  delegates parallel work, independent reviews help improve code and security,
  and shared tasks, checks and handoffs keep the project moving."
- Topics: 10 precise tags, not the maximum of 20. Each must describe what
  Unio does; generic filler (llm, ai-workflow) and jargon
  (human-in-the-loop) dilute it: ai-orchestration, agent-orchestration,
  multi-agent, subagents, ai-agents, coding-agents, agentic-coding,
  multi-llm, claude-code, codex.

Do not use `flock` as an executable name. It is the Linux locking utility
used by the orchestration engine.

Unio 0.5.0 uses only the `unio` command and `UNIO_*` environment variables.
The default configuration is `~/.config/unio`. When that folder is absent
and no config override is supplied, installation copies the legacy
`~/.config/agentteam` folder once, leaving the old folder untouched.
Old command aliases and environment names are removed; update automation.
Project coordination layouts and evidence schemas stay the same. The canonical repository is now
[danielmevit/unio](https://github.com/danielmevit/unio),
renamed in place from the historical `agentteam-docs` and `frugal-flock` repositories with its history retained. Existing
local directories need not be renamed; keeping them avoids breaking
worktree paths (for example, the legacy local path `/mnt/d/Vibe Coding/_vm/frugal-flock` stays intact). Point their Git remote at the new URL.

## Voice

Friendly, resourceful, clear. Use the bird theme in identity and small
illustrations, while keeping task actions literal: Start, Pause, Review,
Request changes, and Apply changes. People should not need to learn bird
metaphors to understand what a button does.

Show the real provider beside every agent. A role such as Reviewer must
still say whether Claude, Codex, or another provider is doing the work.

Useful product copy:

- What would you like to build?
- Review the plan before your flock starts.
- This agent reached its limit. Your work is saved.
- Continue with another available agent.
- The agent finished. Checks are still running.
- Ready for your review.

Only claim work is saved after a durable checkpoint exists. When usage
information is unavailable, say Unknown instead of inventing a percentage.

## Visual identity

The rules behind the website (<https://danielmevit.github.io/unio/>) and the
dashboard's look; the logo and pattern files are in the
[brand kit](brand/README.md). The source of
truth for every value is the code named in each part; update this section
when that code changes.

### Logo

The logo is the word **UNIO** set in Doto, drawn in dots. The dot-matrix
lettering is the mark: many dots (tasks done by AIs from different labs)
forming one word. Every dot is an even rounded square at 80 % of the dot
spacing. On the website header it stands alone, with no pill or separate
symbol, and animates like the titles.

The logo files, the dot line and the story of what the dots mean are in the
[brand kit](brand/README.md): the logo with one-dot and two-dot strokes, each
in one ink, the agent tones and animated, for light and dark backgrounds,
plus the animated dot line for breaking up long pages, all drawn from Doto
by `tools/make-brand-assets.py`. The
earlier dot-matrix U (`brand/legacy/`) is still the dashboard's loading
screen. The website's tab icon is Doto's U in the agent tones, shifting
colors in the tab, and its link preview is the toned logo.

### Typography

All fonts are open source and self-hosted (Fontsource packages in
`site/package.json`); no font is loaded from a third party.

| Role | Font | Where (website: `site/src/pages/index.astro`) |
| --- | --- | --- |
| **Titles** | **Doto** (variable, weight **800**), uppercase | Hero title and every section title; token `--section-title` |
| Body, labels, readouts | IBM Plex Mono 400 / 500 / 600 | Token `--mono` |
| Wordmark "UNIO" in the header | Doto, weight 900 | `.wordmark` |
| Buttons, tabs, card titles | Archivo (variable width, 125 %) | Token `--wide` |

- **Doto** is the title face because it is a dot-matrix font, the same idea as
  the U mark. Keep it at weight 800 so the dots read as dots at every size;
  lighter weights look faint, 900 merges the dots.
- Titles light up dot by dot like the U mark: they start dim (`--title-dim`),
  then each dot grows in as a ring from the top-left (hero on load, section
  titles when first reached). Then the agent tones flow through the word
  endlessly as a wave from one end to the other: the different AIs moving
  in and out, together always forming the whole word. The color moves in
  small clusters of neighboring dots inside one letter, each cluster a
  little ahead or behind, so it is alive but never scattered. Titles pause
  while out of view. With reduced motion they show still in the soft
  off-white `--title` (`#d4d4d4`, never pure white).
- Doto is monospaced at 0.6 em per character. The hero title "YOUR AIs, /
  IN SYNC." is sized from its column (`font-size: 18.4cqi`) so its first line
  fills the column exactly; change that value if the title text changes.
- Licenses: Doto and IBM Plex Mono are SIL OFL 1.1, Archivo is SIL OFL 1.1.
- The dashboard (`bridge/`) uses system fonts (see [UX direction](UX-DIRECTION.md)).

### Color

Dark charcoal grays, no accent color. Website tokens (`:root` in
`index.astro`); the dashboard's dark theme in `bridge/activity.css` matches.

| Token | Value | Use |
| --- | --- | --- |
| `--bg` | `#1c1c1c` | Page |
| `--deep` | `#171717` | Bars, footer band |
| `--paper` | `#252525` | Cards and panels |
| `--line` | `#3d3d3d` | Borders and dividers |
| `--text` | `#e8e8e8` | Main text |
| `--muted` | `#a6a6a6` | Secondary text |
| `--label` | `#c4c4c4` | Labels |
| `--ghost` | `#363636` | Readouts: present, but almost part of the background |
| `--on` / `--on-text` | `#d2d2d2` / `#1c1c1c` | Selected / primary (inverted) |

Status colors are green for finished and the Cradle rust and mustard for
failed and needs attention, at one intensity and one perceived brightness so
that none of the three stands out, and always paired with text: finished
`#7acb7d`, failed `#f86b60`, needs attention `#e1aa40` on dark;
`#357039`, `#9e2d26`, `#7e5908` on light. Green and mustard share OKLCH
lightness 0.77 (dark) and 0.49 (light); the red sits a little lower (0.70 and
0.47) with more chroma, because a saturated red already looks brighter.

**Agent tones** (muted, from the owner's game-UI reference "The Cradle"), one
per agent: its tile, its dots in the animated U, the sync-bus nodes.

| Tone | On dark | On light (dashboard light theme) |
| --- | --- | --- |
| rust | `#cb7f72` | `#8b3b2d` |
| mustard | `#caaa72` | `#8a682e` |
| sea | `#74b4a5` | `#2e6b5d` |
| steel | `#91a2b6` | `#455a73` |
| periwinkle | `#8795c9` | `#344483` |
| lavender | `#a094d1` | `#433285` |

### Shape and layout

- Nothing is perfectly square: `--r-xs` 2px, `--r-sm` 4px, `--r-md` 6px,
  `--r-out` 9px. Groups (segmented buttons, card grids) round only their
  **outer** corners with `--r-out`; inner corners stay tight. On the website a
  page script marks the outer corners from the live layout, so it holds at
  every column count.
- Full width and responsive at every size; never a fixed-width page, never
  horizontal scrolling. Gaps between cards: `--gap` 6px (8px at 1920px+,
  10px at 2560px+). Every section is separated by the same gap.
- The work map is a recessed board: a step darker than the page in both
  themes, with a barely visible dot grid that pans and zooms with the map.

### UI rules

- UX first: no decorative text without real meaning. Readouts (the small
  terminal lines closing each website section) must be true facts.
- No colored left-edge bars on cards, rows or pills. Status is a small
  colored square.
- No frames or plates around floating controls. Close is a plain X.
- Follow the game-UI reference's logic (HUD bars, readouts, inverted
  selections) but never its accent colors, fonts, imagery or assets.
- Support reduced motion everywhere: animations stop, content stays.

## Product direction

See [UX direction](UX-DIRECTION.md) for the proposed interface and delivery
sequence. The product name is decided; the interface described there is a
design proposal, not a claim that a graphical app already ships.
