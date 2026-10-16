# Remote Role and Ref Policy Guide

Unio v0.5.20 introduces an explicit, opt-in remote-role and ref-policy capability
to prevent accidental publication of private development branches to public release
destinations.

## 1. Problem and Objective

Field users occasionally push private development branches (e.g. `dev`, feature
branches, or work-in-progress experiments) directly to public release destinations
(e.g. public GitHub repositories) or accidentally target public refs using
refspec aliases (`dev:main`, `HEAD:main`, or raw commit IDs).

Remote policy provides explicit, OWNER-configured development and release remote
roles and ref validation, enforced before publication by normal Git pre-push hooks.

When no remote policy is configured, simple existing projects are completely
preserved: Unio never guesses public or private roles from an alias, host, or URL.

## 2. Minimal CLI Interface

Remote policy is managed through minimal, explicit CLI commands:

### `unio remote-policy show [--json]`
Displays the current remote policy, pinned destinations, URL fingerprints, ref
rules, and pre-push guard hook status.

```bash
$ unio remote-policy show
remote policy: enabled
release branch: main
guard hook: installed (owner chained: yes)
pinned remotes:
  - origin: role=development
      destinations: [destination]
      hash: e3b0c44298fc...
  - public: role=release
      destinations: [destination]
      hash: 4b227777d4dd...
      release ref: refs/heads/main
      tag pattern: refs/tags/v* (commit must be ancestor of refs/heads/main)
```

With `--json`, outputs structured schema 1 JSON.

### `unio remote-policy set <alias-or-url> <role> [--branch <name>] [--tag-pattern <pat>]`
Pins an approved remote destination and configures its role.
Omitting `--branch` uses the stored release branch, or `main` when none is stored,
independently of `coord/base`. Existing explicit rules are preserved. Owners may
explicitly select any valid branch, including `--branch dev`; names and URLs do
not establish privacy. This default also applies to `same-remote`.

Supported roles:
- `development` (or `dev`): Private development destination.
- `release` (or `public`): Public release destination.
- `same-remote`: Single remote hosting both development and release branches.

```bash
# Pin private development remote
unio remote-policy set origin development

# Pin public release remote with release branch 'main' and tag pattern 'refs/tags/v*'
unio remote-policy set public release --branch main --tag-pattern 'refs/tags/v*'

# Pin same-remote repository
unio remote-policy set origin same-remote --branch main
```

### `unio remote-policy install-guard`
Installs or upgrades the Git pre-push hook in the project's repository.
- Preserves and chains existing owner hooks: if a non-Unio `pre-push` hook exists,
  it is safely backed up to `.git/hooks/pre-push.owner` and executed after Unio checks.
- Preserves the worker worktree guard: workers inside `wt/<worker>` are never permitted
  to push.

## 3. Supported Roles and Ref Policies

### A. Development Role (`development`)
- Intended for internal, private development repositories.
- Ref updates follow the existing development policy; deletions require explicit
  policy permission. The development role does not establish destination privacy.
- Worker worktrees remain blocked by the worker guard.
- If multiple push URLs are configured for the remote alias and any destination is a
  release remote, pushing development branches is refused.

### B. Release Role (`release`)
- Intended for public publication destinations.
- Allowed refs:
  - Configured release branch only (`refs/heads/<release_branch>`, e.g. `refs/heads/main`).
    Source ref MUST match the release branch.
  - Release tags matching the configured pattern (`refs/tags/v*`).
- Strict ancestor validation:
  A release tag must point to a commit reachable from the configured release branch
  (`git merge-base --is-ancestor <tag_commit> refs/heads/<release_branch>`).
  Matching the name `v*` alone is insufficient; unmerged development commits tagged
  with release names are refused before publication.
- Prohibited on release destinations:
  - Pushing any development branch (e.g. `refs/heads/dev`, `refs/heads/feature/*`).
  - Refspec bypass attempts: `dev:main`, `HEAD:main`, or raw commit IDs (`<oid>:main`).
  - Ref deletions (`:refs/heads/main` or `:refs/tags/...`).
  - Mixed multi-ref updates containing any forbidden ref.

### C. Same-Remote Role (`same-remote`)
- Supported choice for projects using a single remote repository for both development
  and release.
- Ref rules are applied based on the destination ref:
  - Updates targeting `refs/heads/<release_branch>` must originate from the release branch
    and cannot be deleted.
  - Updates targeting release tags (`refs/tags/v*`) must point to commits reachable from
    the release branch and cannot be deleted.
  - Updates targeting development branches (`refs/heads/*`) must push matching branch
    names and cannot target the release branch.

## 4. Destination Pinning, Redaction, and Rewriting Safety

- Policy storage: Stored in project-local `coord/remote-policy.json` (schema 1, mode 0600,
  owned by current UID, maximum 64 KiB), strictly separate from schema 1 work policy.
- Identity: transport destinations use exact SHA-256 hashes including all URL
  components. Local paths/file URLs resolve filesystem aliases. Different transport
  spellings remain conservatively distinct and require explicit owner pinning.
- Credential protection: fixed `[destination]` displays and opaque hash-based keys
  for URL/path targets prevent credentials from reaching policy displays or errors.
  Credential changes require re-pinning. No URL component is printed.
- URL rewriting and push URLs:
  Git resolves `url.<base>.pushInsteadOf`, `url.<base>.insteadOf`, and `remote.<name>.pushurl`
  before passing the actual destination URL to `pre-push`. The guard checks the resolved
  destination hash against pinned roles, preventing silent redirection of development
  pushes to public endpoints.
- Unpinned destinations: Pushing to an unapproved, unpinned destination is refused.

## 5. Security Model and Operating Boundaries

- Standard Git pre-push hook: Validation occurs on normal Git pushes (`git push`).
- Not a sandbox: Git pre-push hooks execute in the user's environment. A pre-push hook
  cannot prevent direct remote API calls (e.g. GitHub REST/GraphQL API) or bypassing
  hooks via `--no-verify`.
- Remote contact: Git pre-push hooks run after remote connection and initial ref
  negotiation, but BEFORE Git uploads packfiles or updates remote references.
- No retroactive protection: The guard prevents future publications; it does not
  rewrite remote history or clean up prior leaks.
- Non-destructive: Does not force-push, alter remote URLs silently, or clobber hooks.

## 6. Follow-up: Safe Remote Import

Importing remotes from an explicitly supplied local clone (e.g. inspecting another
local working copy while preserving private configuration and without printing
credentials) is documented as a follow-up enhancement. Cloning a remote URL cannot
discover another clone's private remotes.

### Destination identity and failure handling

The guard checks every resolved push URL (including Git URL rewrites) before
accepting any ref. Conflicting roles or ref rules for one destination are invalid.
No privacy is inferred from a URL or remote name. Transport destinations are
pinned with exact SHA-256 identities, including userinfo, query and fragment;
only local paths/file URLs resolve filesystem aliases. Displays are fixed
`[destination]` strings. Credentials are never stored in displays or policy keys.
Changing credentials or transport spelling requires owner re-pinning; equivalent
transport spellings are conservatively distinct rather than silently merged.
Old policies containing URL displays or old normalized hashes require owner
migration: pause pushes, move the old policy to a private backup outside `coord/`,
then rebuild every pin with `set` and verify `show` before resuming. The loader
refuses unsafe legacy displays instead of printing or silently migrating them.

Policy JSON rejects duplicate keys, unknown fields, invalid types and ref rules,
and is read with bounded no-follow descriptors from owner-controlled paths.
A corrupt configured policy refuses pushes. An absent policy preserves the
unconfigured default. Installation explicitly refuses `core.hooksPath`, unsafe
hook paths and collisions between an owner hook and an existing owner backup.
Both installation routes use the same helper to generate the pre-push hook.
A configured project refuses when no guard helper can execute, including empty
ref batches; unconfigured projects retain the worker guard and owner hook.
These are normal-operation checks on a trusted host: a host owner can still
remove the worker marker, hook or policy. This does not establish remote privacy.

### Thin configurations and standalone engines

`UNIO_CONF_DIR` may contain only command overrides and templates. `init`,
`remote-policy` and `_remote-guard` use the engine's embedded guard core, generated
byte-for-byte from `tools/remote-guard.py` by `tools/embed-adapters.py`. The same
canonical source still installs at `lib/remote-guard.py`; it is an internal
core, and the AI adapter inventory remains four. `--check` verifies both copies.
Selftest uses the embedded core with an isolated thin profile as well.

New pre-push hooks pin the absolute engine that installed them; direct Python
helper installation pins that helper. They never search another profile,
source tree or `PATH` for a replacement Unio. Git ref records remain on stdin
through the Python dispatcher and reach the owner hook after policy approval.
Removing an external lib file therefore does not remove the engine's policy
implementation. Removing the pinned engine refuses configured pushes, including
empty ref batches, while workers remain unable to push. Moving an engine requires
explicit guard reinstallation with the intended engine.
