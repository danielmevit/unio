# Eqho logic for Unio's Windows app

Owner direction, 2026-10-15: reuse selected transcription and history logic
from [Eqho](https://github.com/danielmevit/eqho) in the planned Windows app.
This is a future Windows milestone design, not an implemented Unio feature.
The assessment used Eqho revision
`e81c4af29efe179b85692b4510cc90ca574a0f78`; selected modules were read
statically. No Eqho code, model or dependency was installed or executed.

The owner is improving Eqho in a separate session. This snapshot is an
assessment reference, not the version selected for integration. Before the
Windows implementation, inspect the owner's latest approved Eqho revision,
reassess its module boundaries and pin the version actually used. Refresh
the source references and compatibility checks then; preserve that session's
independent work.

## Useful building blocks

| Eqho source | Useful logic | Unio adaptation |
| --- | --- | --- |
| [history.py](https://github.com/danielmevit/eqho/blob/e81c4af29efe179b85692b4510cc90ca574a0f78/src/history.py) | Local JSONL entries, a 1,000-entry default, search, delete, clear and text export | Private transcript drafts associated with a project/session and optionally a task; stable entry IDs and explicit storage outcomes |
| [textproc.py](https://github.com/danielmevit/eqho/blob/e81c4af29efe179b85692b4510cc90ca574a0f78/src/textproc.py) | Segment joining, punctuation commands and optional replacements/cleanup | Preserve the original transcript; preview optional transformations and keep case-sensitive code and commands intact |
| [transcriber.py](https://github.com/danielmevit/eqho/blob/e81c4af29efe179b85692b4510cc90ca574a0f78/src/transcriber.py) | Separate partial/final callbacks, microphone lifecycle and filtering of likely non-speech | Replace provisional text in one draft; commit a final utterance once and expose recording/transcribing/error states |
| [model_host.py](https://github.com/danielmevit/eqho/blob/e81c4af29efe179b85692b4510cc90ca574a0f78/src/model_host.py) | A spawned model process and serialized inference requests | An optional speech backend with owned shutdown, bounded requests and verified cleanup, separate from AI worker coordination |
| [history view](https://github.com/danielmevit/eqho/blob/e81c4af29efe179b85692b4510cc90ca574a0f78/src/ui/tabs/history.py) | Search by text/date, period filters and pagination | Apply those interactions to Unio's existing interface |

## Proposed experience

Record an instruction, watch its partial transcript, then edit the completed
draft. Choose the intended project/task and use the normal explicit send
action. A transcript never becomes an executed shell command or an approved
task by itself. App-scoped input is the first target; system-wide typing,
clipboard injection and Eqho's desktop shell are not required for that flow.

History should let the owner search, reopen, edit, delete and export drafts.
Keep the voice transcript separate from worker output and the task ledger:
reopening history must not replay a task. Preserve an original transcription
alongside any edited draft. Bind an optional task reference only after the
normal task creation/send step.

## Adaptation work identified in the source

Eqho's history lock protects threads in one process. Unio must coordinate
multiple local processes, use private bounded storage and unique temporary
files, validate entries and distinguish an unreadable store from an empty
one. Its float timestamp should remain display metadata rather than the
identity used to delete or replay an entry. Use Unio's existing storage
patterns rather than making transcript history a second task database.

Eqho's cleanup can capitalize text and apply word replacements. Those
transformations need an opt-in preview for coding instructions. Raw transcript
bodies currently appear in some Eqho logging calls; Unio's operational logs
should report state without copying spoken content into ordinary worker logs.

Model-process and transcription-thread joins have time limits in Eqho.
Unio must verify that its owned speech process actually stopped before
claiming cleanup or starting a replacement. Reuse the lifecycle design with
the Windows host's ownership mechanism; do not treat a timed join as proof.

Speech remains optional. Keep its audio/model dependencies out of the base
CLI install, request microphone access visibly, and offer model downloads
explicitly. Audio is temporary by default; text history is private and
owner-controlled, with a history-off option. Only selected submitted text
enters an AI task. Actual source reuse retains Eqho attribution/notices.

## Delivery and estimates

1. **Draft/history prototype:** typed and recorded-text fixtures, search,
   editing, deletion/export and explicit send, about **6–12 hours** once the
   Windows desktop's draft/session interface exists. Check persistence across
   restart, concurrent access and that reopening an entry makes no agent call.
2. **Optional local dictation:** microphone input, partial/final events,
   backend selection and owned cancellation, about **1–3 working days** after
   that prototype. Exercise real Windows audio, permission refusal, model
   failure and stop/restart without duplicate submission.
3. **Packaging:** measure dependency/download size, model loading, CPU/GPU
   impact and the selected Windows package's permissions before inclusion.
   Estimate this after the native desktop feasibility proof; it is outside
   the current Windows runtime estimate.

These are planning ranges, not measured reuse savings. Keep the native host
and desktop foundation first, then ship voice in a bounded 0.5.x follow-up if
it would otherwise delay that foundation. See the
[Windows release track](RELEASE-OUTLOOK-0.5.19-0.5.24.md#0523--native-windows).
