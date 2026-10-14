# Unio 0.5.18 — worker reliability

Candidate only. The published and installed release remains
[Unio 0.5.17](https://github.com/danielmevit/unio/releases/tag/v0.5.17).
This note does not publish a tag, assets or a global install. One frozen
full quality gate is still required. Public README and changelog labels
can drop the unreleased mark only after that gate, and only when every
other tracked byte stays identical.

## Vibe live progress

The pinned Vibe 2.26.1 worker prints fixed operational labels and a
separate liveness heartbeat. The heartbeat says the adapter process is
alive. It does not claim reasoning, task success, readiness, quota or
token savings.

On 2026-10-14 a Mistral subscription run, Vibe 2.26.1, requested GLM 5.3
high, used frozen adapter
`4dd45a0e4d50190b15332b04c772afa12af7c4febb186d8b2f8e6f32cef2a85b`
for ANTIGRAVITY-OUTCOME-GLM-HIGH-1. The first safe event was at 12:09:17
+02:00 while the adapter was alive. The first liveness heartbeat was at
12:12:18 +02:00. Source exit was 0 and the export finished. The lead
accepted only the later checked correction. Effective model, effort and
remaining allowance stay Unknown.

Earlier Vibe evidence remains in force. A native exit 3 at the local 4M
cumulative token cap, and the 2026-10-09 save that ended native 2 with
`infrastructure_failure`, do not show monthly or weekly allowance and do
not rank models.

## Antigravity outcome

The optional agy 1.3.5 adapter is the fourth packaged helper. It pins
Gemini 3.8 Flash high, medium and low, refuses a task above 64 KiB before
any provider call, and keeps the real process exit separate from the
structured terminal verdict. A process exit 0 with terminal ERROR is not
a completed success. Legacy command lines, permissions, real accounts and
review authority stay as they are.

The checked correction `e52dfea` is the accepted source component. Frozen
adapter `fa9b964a678d0b2fd8a3e336535ad80432476f13db6ca807718af48702cee31e`
then ran COPILOT-JSONL-GEMINI-CORRECTION-1. Its operational receipt
finished at 13:47:58 +02:00 with native exit 0, structured terminal
SUCCESS and adapter exit 0. Effective model, effort and allowance stay
Unknown. That result does not accept the correction, and the correction
is outside this candidate. The earlier process 0 / terminal ERROR
observation stays preserved.

## Copilot JSONL proposals

Routine Copilot proposals take the exact root assistant message from
native JSONL. The adapter does not rich-wrap, strip or repair that text.
A completion still requires native exit 0 and one valid terminal result.
This evidence is offline native-source and fake-CLI only. There is no
live Copilot call for this transport in the candidate record. Effective
model, effort and allowance are Unknown.

Three lead-found input and group defects are being corrected separately
as COPILOT-JSONL-GEMINI-CORRECTION-1. That correction is not in this
candidate and is not accepted.

## What stays unchanged

Permissions, account mapping, human review, global command lines and
existing version tags stay intact. Accepting source is separate from a
provider finishing and from remaining capacity. UI, site and brand work
remain owner-reserved. No Codex worker and no extra review fleet were
used for this batch.

Provenance for the staged components: Mistral / Vibe GLM high produced
the initial Antigravity source; Antigravity / Gemini 3.8 Flash high made
the checked correction; Grok 4.7 high implemented the Copilot JSONL
transport; an earlier Copilot Free Auto Balance pass supplied a routine
proposal. An OpenCode Go save diagnosis remains unknown and is not a
capacity or ranking result.

## Delivery still required

Private scripts under the workspace `tmp/unio-next/` directory rehearse
the corrected 0.5.17 order: one gate, exact artifacts, upgrade from
0.5.17 and restore, idle native tasks, install, then publication. They
are staged and have not been run. The lead pushes explicit refs from
`repo/`. Worker checkouts do not push.
