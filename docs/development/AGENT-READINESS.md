# Authentication observations

This feature distinguishes **signed in** from **able to take work**.
It observes Claude Code authentication without asking a model. Allowance and
combined dispatch readiness remain Unknown, including after a signed-in result.

## Use the command

The v0.5.10 release candidate adds the native command below. It is not included in
the published v0.5.9 installer.

```bash
unio readiness refresh claude
unio readiness show --agent claude --json
unio readiness --project '/path/to/workspace' show --json
```

The development source tool provides the same operations:

```bash
python3 -B 'tools/agent-readiness.py' --project '/path/to/workspace' refresh claude
python3 -B 'tools/agent-readiness.py' --project '/path/to/workspace' show --agent claude --json
```

The project path names the workspace containing `coord`, rather than its `repo`
subfolder. `show` reads only local cached data, creates no missing store and
executes no command. Refresh is explicit and works while STOP is set; it does
not permit a worker run or change the project's policy or off/on settings.

Only the checked Claude Code **2.1.296** is supported. Refresh runs exactly
`claude --version`, then `claude auth status --json` if the version matches.
Other versions and agents do not trigger a generating command or fallback.
The browser's **AI agents & limits** section reads the same cached observation.
It never refreshes authentication or starts an additional CLI call. Other agents
remain Unknown. A signed-in label establishes neither remaining allowance nor
permission to start work.

## What is recorded

The required `loggedIn` field must be a JSON boolean. Optional strings must
match these allowlists:

| Field | Accepted labels |
| --- | --- |
| `authMethod` | `claude.ai`, `api_key`, `oauth`, `none` |
| `apiProvider` | `firstParty`, `bedrock`, `vertex`, `foundry` |
| `subscriptionType` | `pro`, `max`, `team`, `enterprise`, `free` |

Unknown additional native fields are discarded in memory. Email, organization,
account names, identifiers, tokens and raw native diagnostics are never printed
or saved. An unexpected optional label or type produces a failed observation,
not a signed-in claim. Duplicate or malformed JSON is refused.

Fresh observations expose `authentication=signed_in` or `signed_out` alongside
source, time and age. A reading older than 15 minutes or ahead of the local clock
has Unknown current authentication. A failed refresh also makes current
authentication Unknown, retaining a separately labelled historical last-good
observation. Historical sign-in never establishes present capacity.

## Bounds and failure behavior

Version output has a 256-byte aggregate stdout/stderr bound and five-second
deadline. Status has a 64 KiB aggregate bound and ten-second deadline. Output is
bounded while reading; owned process groups are cleaned up on timeout, overflow
and completion. These controls operate on a trusted host, not in an OS sandbox.

The private `coord/readiness` store uses owned, single-link regular files,
no-follow directory/file opens, a bounded lock and atomic replacement. Unsafe,
busy or failed storage never establishes a fresh persisted reading. Existing
malformed evidence is preserved rather than silently repaired.

Refresh exits 0 after persisting a valid observation, 1 after persisting an
allowlisted native-failure reason, and 2 for unsafe or unavailable storage.
Reasons are fixed labels such as `timeout`, `unsupported_version` and
`invalid_status`; they contain no native output. Show exits 2 for invalid stored
state and 0 for readable or missing state. A missing reading is Unknown.

Focused checks cover exact argv, signed-in/out, private-field rejection,
historical/stale/skew handling, storage permissions and links, bounded locking,
output overflow and descendant cleanup. The original Gemini candidate and its
six failed personal-review probes remain recorded separately; passing its
initial tests did not establish acceptance. Installed-command checks exercise
the real installer with a fake Claude executable. Browser and API checks verify
that rendering the cached observation adds no CLI calls or cache writes.
