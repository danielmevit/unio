#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Remote role and ref policy guard for Git push operations.

Enforces OWNER-configured development, release and same-remote roles and ref policy
before publication via standard Git pre-push hooks.
"""
import fnmatch
import hashlib
import json
import os
import re
import shlex
import stat
import subprocess
import sys
import tempfile
import urllib.parse
from pathlib import Path

MAX_POLICY_BYTES = 65536
ZERO_OID_RE = re.compile(r'^0{40,64}$')
HEX_OID_RE = re.compile(r'^[0-9a-fA-F]{40,64}$')
CREDENTIAL_RE = re.compile(r'^(https?://|ssh://|git\+ssh://)([^:/@]+):([^@]+)@', re.IGNORECASE)


class PolicyError(Exception):
    """Raised when remote policy is violated or invalid."""


def redact_url(url):
    """Return URL with embedded passwords/tokens redacted."""
    if not url:
        return ""
    # Redact user:pass@ in standard schemes
    m = CREDENTIAL_RE.match(url)
    if m:
        scheme, user, _pass = m.groups()
        return CREDENTIAL_RE.sub(rf"{scheme}{user}:***@", url)
    # Check if there is an embedded token/password in userinfo
    if "://" in url:
        parts = urllib.parse.urlsplit(url)
        if parts.password:
            user = parts.username or ""
            netloc = f"{user}:***@{parts.hostname}"
            if parts.port:
                netloc += f":{parts.port}"
            return urllib.parse.urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    return url


def normalize_url(url):
    """Return canonical, lowercased, credential-stripped string for destination comparison."""
    if not url:
        return ""
    raw = url.strip()
    if raw.startswith("file://"):
        path = urllib.parse.unquote(raw[7:])
        if os.path.exists(path):
            path = os.path.realpath(path)
        return f"file://{path.rstrip('/')}"
    if os.path.isdir(raw) or raw.startswith("/") or raw.startswith("./") or raw.startswith("../"):
        path = os.path.realpath(raw)
        return f"file://{path.rstrip('/')}"
    if "://" in raw:
        p = urllib.parse.urlsplit(raw)
        scheme = p.scheme.lower()
        host = p.hostname.lower() if p.hostname else ""
        port = f":{p.port}" if p.port and not ((scheme == "http" and p.port == 80) or (scheme == "https" and p.port == 443)) else ""
        path = p.path.rstrip("/")
        return f"{scheme}://{host}{port}{path}"
    # SCP-style git@host:path/to/repo.git
    m = re.match(r'^([^@]+@)?([^:]+):(.+)$', raw)
    if m:
        _, host, path = m.groups()
        return f"ssh://{host.lower()}/{path.rstrip('/')}"
    return raw.rstrip("/")


def hash_url(url):
    """Return sha256 hex digest of normalized URL."""
    return hashlib.sha256(normalize_url(url).encode("utf-8")).hexdigest()


def find_project_root(start=None):
    """Traverse up to find the project root containing coord/."""
    curr = Path(start or os.getcwd()).resolve()
    for parent in [curr] + list(curr.parents):
        if (parent / "coord").is_dir():
            return parent
    return None


def get_base_branch(root):
    """Read coord/base or default to 'main'."""
    base_file = root / "coord" / "base"
    try:
        content = base_file.read_text(encoding="utf-8").strip()
        if content:
            return content
    except OSError:
        pass
    return "main"


def load_policy(root, require=False):
    """Load and validate coord/remote-policy.json."""
    coord_dir = root / "coord"
    if not coord_dir.is_dir():
        if require:
            raise PolicyError("missing coord directory in project root")
        return None

    # Verify coord directory ownership and permissions
    st_dir = coord_dir.stat()
    if st_dir.st_uid != os.getuid() or (st_dir.st_mode & 0o022):
        raise PolicyError("coord directory must be owned by current user and not group/world-writable")

    policy_file = coord_dir / "remote-policy.json"
    if not policy_file.exists():
        if require:
            raise PolicyError(f"no remote policy configured at {policy_file}")
        return None

    st = policy_file.stat()
    if not stat.S_ISREG(st.st_mode):
        raise PolicyError("remote-policy.json must be a regular file")
    if st.st_uid != os.getuid():
        raise PolicyError("remote-policy.json must be owned by current user")
    if st.st_nlink != 1:
        raise PolicyError("remote-policy.json must not have multiple hard links")
    if st.st_mode & 0o077:
        raise PolicyError("remote-policy.json must have private permissions (0600)")
    if st.st_size > MAX_POLICY_BYTES:
        raise PolicyError(f"remote-policy.json exceeds maximum size ({MAX_POLICY_BYTES} bytes)")

    try:
        raw = policy_file.read_bytes()
        doc = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise PolicyError(f"malformed remote-policy.json: {e}")

    if not isinstance(doc, dict):
        raise PolicyError("remote-policy.json must contain a JSON object")
    if doc.get("schema_version") != 1:
        raise PolicyError("unsupported remote-policy schema_version (expected 1)")
    if not isinstance(doc.get("remotes"), dict):
        raise PolicyError("remote-policy.json must contain 'remotes' map")

    return doc


def save_policy(root, doc):
    """Atomically write doc to coord/remote-policy.json with 0600 permissions."""
    coord_dir = root / "coord"
    coord_dir.mkdir(parents=True, exist_ok=True)
    st_dir = coord_dir.stat()
    if st_dir.st_uid != os.getuid() or (st_dir.st_mode & 0o022):
        raise PolicyError("coord directory must be owned by current user and not group/world-writable")

    policy_file = coord_dir / "remote-policy.json"
    encoded = (json.dumps(doc, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(encoded) > MAX_POLICY_BYTES:
        raise PolicyError(f"policy content exceeds maximum size ({MAX_POLICY_BYTES} bytes)")

    fd, tmp_path = tempfile.mkstemp(dir=str(coord_dir), prefix="remote-policy-", suffix=".tmp")
    try:
        os.chmod(tmp_path, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(encoded)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(policy_file))
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
        raise


def get_git_remote_push_urls(repo_dir, remote_name):
    """Return all resolved push URLs for the given remote alias in repo_dir."""
    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "remote", "get-url", "--all", "--push", str(remote_name)],
            capture_output=True, text=True, check=True
        )
        return [line.strip() for line in res.stdout.splitlines() if line.strip()]
    except subprocess.CalledProcessError:
        return []


def match_destination_to_role(policy, target_url):
    """Match target_url by hash against policy['remotes']. Return (remote_key, remote_cfg) or (None, None)."""
    target_hash = hash_url(target_url)
    remotes = policy.get("remotes", {})
    for key, cfg in remotes.items():
        hashes = cfg.get("url_hashes", [])
        if target_hash in hashes:
            return key, cfg
    return None, None


def check_tag_ancestor(repo_dir, commit_oid, release_branch):
    """Check if commit_oid is an ancestor of refs/heads/<release_branch>."""
    ref = f"refs/heads/{release_branch}"
    cp = subprocess.run(
        ["git", "-C", str(repo_dir), "merge-base", "--is-ancestor", str(commit_oid), ref],
        capture_output=True
    )
    return cp.returncode == 0


def verify_push(root, repo_dir, remote_name, remote_url, ref_lines):
    """Check every pre-push ref update and actual target destination against pinned policy.

    ref_lines is a list of tuples: (local_ref, local_oid, remote_ref, remote_oid).
    Raises PolicyError if any update violates policy.
    """
    policy = load_policy(root, require=False)
    if not policy or not policy.get("enabled", True):
        # No policy configured: preserve simple existing projects without guessing
        return

    default_base = get_base_branch(root)
    norm_target = normalize_url(remote_url)
    target_hash = hash_url(norm_target)

    # 1. Check resolved target push destination against pinned roles
    key, cfg = match_destination_to_role(policy, remote_url)
    if not cfg:
        raise PolicyError(
            f"refusing push to unpinned destination '{redact_url(remote_url)}' "
            f"(hash {target_hash[:12]} is not an owner-approved remote destination)"
        )

    role = cfg.get("role")
    if role not in ("development", "release", "same-remote"):
        raise PolicyError(f"invalid or unsupported remote role '{role}' for destination '{redact_url(remote_url)}'")

    # 2. Check if remote alias has multiple push destinations configured in git
    all_push_urls = get_git_remote_push_urls(repo_dir, remote_name)
    has_release_dest = False
    for u in all_push_urls:
        _k, other_cfg = match_destination_to_role(policy, u)
        if other_cfg and other_cfg.get("role") in ("release", "same-remote"):
            has_release_dest = True
            break

    # 3. Validate every ref update
    for local_ref, local_oid, remote_ref, remote_oid in ref_lines:
        is_delete = local_ref in ("(delete)", "") or ZERO_OID_RE.match(local_oid)
        release_branch = cfg.get("release_branch") or policy.get("release_branch") or default_base
        release_ref = f"refs/heads/{release_branch}"
        tag_pat = cfg.get("tag_pattern") or policy.get("tag_pattern") or "refs/tags/v*"
        allow_deletions = cfg.get("allow_deletions", policy.get("allow_deletions", False))

        if role == "release":
            # Deletion policy on release destination
            if is_delete:
                raise PolicyError(f"ref deletion '{remote_ref}' on release destination '{redact_url(remote_url)}' is forbidden")

            if remote_ref.startswith("refs/heads/"):
                if remote_ref != release_ref:
                    raise PolicyError(
                        f"refusing to push non-release branch '{remote_ref}' to release destination "
                        f"'{redact_url(remote_url)}'; only '{release_ref}' is allowed"
                    )
                # Prevent bypass by dev:main, HEAD:main, raw-object sha or ambiguous sources
                if local_ref == "HEAD":
                    raise PolicyError(
                        f"ambiguous or non-canonical source ref 'HEAD' targeting release destination; "
                        f"push explicit branch '{release_ref}'"
                    )
                if not local_ref.startswith("refs/heads/"):
                    raise PolicyError(
                        f"raw object or non-branch source '{local_ref}' targeting release destination; "
                        f"push explicit branch '{release_ref}'"
                    )
                if local_ref != release_ref:
                    raise PolicyError(
                        f"source ref '{local_ref}' cannot target release branch '{release_ref}'"
                    )

            elif remote_ref.startswith("refs/tags/"):
                if not fnmatch.fnmatch(remote_ref, tag_pat):
                    raise PolicyError(
                        f"tag '{remote_ref}' does not match allowed release tag pattern '{tag_pat}'"
                    )
                if not local_ref.startswith("refs/tags/"):
                    raise PolicyError(
                        f"tag update destination '{remote_ref}' requires explicit tag source (got '{local_ref}')"
                    )
                # Release tags must not publish a private development commit merely matching v*
                if not check_tag_ancestor(repo_dir, local_oid, release_branch):
                    raise PolicyError(
                        f"release tag '{remote_ref}' points to commit {local_oid[:8]} which is not reachable "
                        f"from release branch '{release_ref}'; refusing publication of unmerged development commit"
                    )
            else:
                raise PolicyError(f"refusing unsupported ref update '{remote_ref}' on release destination")

        elif role == "development":
            if is_delete and not allow_deletions:
                raise PolicyError(f"ref deletion '{remote_ref}' on development destination is disallowed by policy")

            # If the remote alias configured in Git also targets a release destination (multi-push):
            if has_release_dest and remote_ref != release_ref:
                raise PolicyError(
                    f"remote '{remote_name}' has multiple push destinations including release; "
                    f"cannot push development ref '{remote_ref}'"
                )

        elif role == "same-remote":
            # Same-remote dev/release project: destination ref distinguishes dev vs release
            if remote_ref == release_ref:
                # Treated as release publication
                if is_delete:
                    raise PolicyError(f"ref deletion of release branch '{release_ref}' on same-remote is forbidden")
                if local_ref == "HEAD":
                    raise PolicyError(
                        f"ambiguous or non-canonical source ref 'HEAD' targeting release branch; "
                        f"push explicit branch '{release_ref}'"
                    )
                if not local_ref.startswith("refs/heads/"):
                    raise PolicyError(
                        f"raw object or non-branch source '{local_ref}' targeting release branch; "
                        f"push explicit branch '{release_ref}'"
                    )
                if local_ref != release_ref:
                    raise PolicyError(
                        f"source ref '{local_ref}' cannot target release branch '{release_ref}'"
                    )

            elif remote_ref.startswith("refs/tags/"):
                # If tag matches release tag pattern:
                if fnmatch.fnmatch(remote_ref, tag_pat):
                    if is_delete:
                        raise PolicyError(f"ref deletion of release tag '{remote_ref}' on same-remote is forbidden")
                    if not local_ref.startswith("refs/tags/"):
                        raise PolicyError(f"tag destination '{remote_ref}' requires explicit tag source (got '{local_ref}')")
                    if not check_tag_ancestor(repo_dir, local_oid, release_branch):
                        raise PolicyError(
                            f"release tag '{remote_ref}' points to commit {local_oid[:8]} which is not reachable "
                            f"from release branch '{release_ref}'; refusing publication of unmerged development commit"
                        )
                else:
                    if is_delete and not allow_deletions:
                        raise PolicyError(f"ref deletion '{remote_ref}' disallowed by policy")

            elif remote_ref.startswith("refs/heads/"):
                # Development branch on same-remote
                if is_delete and not allow_deletions:
                    raise PolicyError(f"ref deletion '{remote_ref}' on same-remote is disallowed by policy")
                if not is_delete and local_ref != remote_ref:
                    raise PolicyError(
                        f"cross-branch source alias '{local_ref}:{remote_ref}' unsupported on same-remote"
                    )
            else:
                raise PolicyError(f"refusing unsupported ref update '{remote_ref}' on same-remote")


def cli_show(root, as_json=False):
    """Show configured remote policy and guard status."""
    policy = load_policy(root, require=False)
    repo_dir = root / "repo"
    hooks_dir = repo_dir / ".git" / "hooks"
    if not hooks_dir.exists():
        # Check worktree / common git dir
        try:
            res = subprocess.run(
                ["git", "-C", str(repo_dir), "rev-parse", "--path-format=absolute", "--git-common-dir"],
                capture_output=True, text=True, check=True
            )
            hooks_dir = Path(res.stdout.strip()) / "hooks"
        except Exception:
            pass

    guard_hook = hooks_dir / "pre-push"
    has_guard = False
    has_owner_chained = (hooks_dir / "pre-push.owner").is_file()

    if guard_hook.is_file():
        try:
            txt = guard_hook.read_text(encoding="utf-8", errors="replace")
            has_guard = "unio guard" in txt
        except OSError:
            pass

    status = {
        "configured": policy is not None,
        "enabled": bool(policy.get("enabled", True)) if policy else False,
        "guard_installed": has_guard,
        "owner_hook_chained": has_owner_chained,
        "policy": policy or {},
    }

    if as_json:
        print(json.dumps(status, indent=2))
        return 0

    if not policy:
        print("remote policy: none configured (simple unconfigured project preserved; pre-push worker guard only)")
        print(f"guard hook: {'installed' if has_guard else 'not installed'} (owner chained: {'yes' if has_owner_chained else 'no'})")
        return 0

    print(f"remote policy: {'enabled' if policy.get('enabled', True) else 'disabled'}")
    print(f"release branch: {policy.get('release_branch', get_base_branch(root))}")
    print(f"guard hook: {'installed' if has_guard else 'not installed'} (owner chained: {'yes' if has_owner_chained else 'no'})")
    remotes = policy.get("remotes", {})
    if not remotes:
        print("pinned remotes: none")
    else:
        print("pinned remotes:")
        for name, cfg in sorted(remotes.items()):
            role = cfg.get("role", "unknown")
            urls = cfg.get("redacted_urls", [])
            hashes = cfg.get("url_hashes", [])
            url_str = ", ".join(urls) if urls else "n/a"
            hash_str = ", ".join(h[:12] for h in hashes) if hashes else "n/a"
            print(f"  - {redact_url(name)}: role={role}")
            print(f"      destinations: {url_str}")
            print(f"      hash: {hash_str}")
            if role in ("release", "same-remote"):
                rel_b = cfg.get("release_branch") or policy.get("release_branch") or get_base_branch(root)
                tag_p = cfg.get("tag_pattern") or policy.get("tag_pattern") or "refs/tags/v*"
                print(f"      release ref: refs/heads/{rel_b}")
                print(f"      tag pattern: {tag_p} (commit must be ancestor of refs/heads/{rel_b})")
    return 0


def cli_set(root, target, role, branch=None, tag_pattern=None, allow_deletions=False):
    """Set role for a remote alias or explicit destination URL."""
    if role not in ("development", "dev", "release", "public", "same-remote"):
        raise PolicyError("role must be 'development', 'release', or 'same-remote'")
    if role == "dev":
        role = "development"
    if role == "public":
        role = "release"

    repo_dir = root / "repo"
    policy = load_policy(root, require=False) or {
        "schema_version": 1,
        "enabled": True,
        "release_branch": get_base_branch(root),
        "tag_pattern": "refs/tags/v*",
        "allow_deletions": False,
        "remotes": {},
    }

    if branch:
        policy["release_branch"] = branch
    if tag_pattern:
        policy["tag_pattern"] = tag_pattern

    # Determine whether target is an existing git remote alias or direct URL
    push_urls = []
    if repo_dir.is_dir():
        push_urls = get_git_remote_push_urls(repo_dir, target)

    if not push_urls:
        # Target may be a direct URL or path
        push_urls = [target]

    hashes = [hash_url(u) for u in push_urls]
    redacted = [redact_url(u) for u in push_urls]

    remote_cfg = {
        "role": role,
        "url_hashes": hashes,
        "redacted_urls": redacted,
        "release_branch": branch or policy.get("release_branch", get_base_branch(root)),
        "tag_pattern": tag_pattern or policy.get("tag_pattern", "refs/tags/v*"),
        "allow_deletions": allow_deletions,
    }

    target_key = redact_url(target)
    policy.setdefault("remotes", {})[target_key] = remote_cfg
    save_policy(root, policy)

    print(
        f"unio remote-policy: pinned remote '{target_key}' as {role}\n"
        f"  destination: {', '.join(redacted)}\n"
        f"  hash: {', '.join(h[:12] for h in hashes)}"
    )
    return 0


def cli_install_guard(root, repo_dir=None):
    """Safely install pre-push guard hook with owner hook backup and chaining."""
    if repo_dir is None:
        cwd = Path.cwd().resolve()
        if (cwd / ".git").exists() or (cwd / ".git").is_file():
            repo_dir = cwd
        elif (root / "repo").is_dir():
            repo_dir = root / "repo"
        else:
            repo_dir = cwd
    if not repo_dir.is_dir():
        raise PolicyError(f"no repository found at {repo_dir}")

    try:
        res = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True, text=True, check=True
        )
        hooks_dir = Path(res.stdout.strip()) / "hooks"
    except Exception:
        hooks_dir = repo_dir / ".git" / "hooks"

    hooks_dir.mkdir(parents=True, exist_ok=True)
    guard_hook = hooks_dir / "pre-push"
    owner_backup = hooks_dir / "pre-push.owner"

    if guard_hook.is_file():
        txt = guard_hook.read_text(encoding="utf-8", errors="replace")
        if "unio guard" not in txt and "agentteam guard" not in txt:
            # Existing owner hook: back up and chain
            if not owner_backup.exists():
                os.replace(str(guard_hook), str(owner_backup))
                os.chmod(str(owner_backup), 0o755)

    hook_script = """#!/bin/sh
# Unio — Copyright (C) 2026 Daniel Mitev
# Original project: https://github.com/danielmevit/unio
# unio guard — workers never push; owner pushes from repo/ with remote policy
top=$(git rev-parse --show-toplevel 2>/dev/null) || exit 0
if [ -f "$top/.unio-worker" ]; then
  echo "unio guard: workers do not push (owner pushes from repo/)" >&2
  exit 1
fi

STDIN_DATA=$(cat)

if [ -n "$STDIN_DATA" ]; then
  root=$(dirname "$top")
  guard_py=""
  if [ -n "${UNIO_CONF_DIR:-}" ] && [ -f "$UNIO_CONF_DIR/lib/remote-guard.py" ]; then
    guard_py="$UNIO_CONF_DIR/lib/remote-guard.py"
  elif [ -n "${CONF_DIR:-}" ] && [ -f "$CONF_DIR/lib/remote-guard.py" ]; then
    guard_py="$CONF_DIR/lib/remote-guard.py"
  elif [ -f "$root/tools/remote-guard.py" ]; then
    guard_py="$root/tools/remote-guard.py"
  fi

  if [ -n "$guard_py" ]; then
    printf "%s\\n" "$STDIN_DATA" | python3 -B "$guard_py" check "$top" "$1" "$2" || exit $?
  elif command -v unio >/dev/null 2>&1; then
    printf "%s\\n" "$STDIN_DATA" | unio _remote-guard check "$top" "$1" "$2" || exit $?
  fi
fi

hooks="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)/hooks"
if [ -x "$hooks/pre-push.owner" ]; then
  printf "%s\\n" "$STDIN_DATA" | "$hooks/pre-push.owner" "$@" || exit $?
fi
exit 0
"""
    guard_hook.write_text(hook_script, encoding="utf-8")
    os.chmod(str(guard_hook), 0o755)

    has_owner = owner_backup.is_file()
    print(f"unio remote-policy: pre-push guard installed in {guard_hook} (owner hook chained: {'yes' if has_owner else 'no'})")
    return 0


def cli_check(argv):
    """Run check called by pre-push hook.

    Usage: remote-guard.py check <repo_dir_or_project_root> <remote_name> <remote_url>
    Reads ref lines from stdin.
    """
    if len(argv) < 3:
        raise PolicyError("usage: remote-guard check <repo_or_root> <remote_name> <remote_url>")

    path_arg = argv[0]
    remote_name = argv[1]
    remote_url = argv[2]

    root = find_project_root(path_arg)
    if not root:
        # Not inside a unio project: allow
        return 0

    repo_dir = Path(path_arg).resolve()
    if not (repo_dir / ".git").exists() and (root / "repo").is_dir():
        repo_dir = root / "repo"

    lines = []
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) == 4:
            lines.append(tuple(parts))
        elif len(parts) >= 2:
            lines.append((parts[0], parts[1], parts[0], parts[1]))

    try:
        verify_push(root, repo_dir, remote_name, remote_url, lines)
        return 0
    except PolicyError as e:
        print(f"unio remote guard: {e}", file=sys.stderr)
        return 1


def main(argv=None):
    args = argv if argv is not None else sys.argv[1:]
    if not args or args[0] in ("-h", "--help", "help"):
        print(
            "usage: unio remote-policy show [--json]\n"
            "       unio remote-policy set <alias-or-url> <development|release|same-remote> [--branch <name>] [--tag-pattern <pat>]\n"
            "       unio remote-policy install-guard\n"
            "       unio remote-policy check <repo_dir> <remote_name> <remote_url>"
        )
        return 0

    cmd = args[0]
    rest = args[1:]
    root = find_project_root()

    try:
        if cmd == "check":
            return cli_check(rest)

        if not root:
            print("unio: not inside a Unio project", file=sys.stderr)
            return 1

        if cmd == "show":
            as_json = "--json" in rest
            return cli_show(root, as_json=as_json)

        if cmd == "set":
            if len(rest) < 2:
                print("usage: unio remote-policy set <alias-or-url> <development|release|same-remote> [--branch B] [--tag-pattern P]", file=sys.stderr)
                return 1
            target = rest[0]
            role = rest[1]
            branch, tag_pat = None, None
            idx = 2
            while idx < len(rest):
                if rest[idx] == "--branch" and idx + 1 < len(rest):
                    branch = rest[idx + 1]
                    idx += 2
                elif rest[idx] == "--tag-pattern" and idx + 1 < len(rest):
                    tag_pat = rest[idx + 1]
                    idx += 2
                else:
                    idx += 1
            return cli_set(root, target, role, branch=branch, tag_pattern=tag_pat)

        if cmd in ("install-guard", "install"):
            target_repo = Path(rest[0]).resolve() if rest else None
            return cli_install_guard(root, repo_dir=target_repo)

        print(f"unio remote-policy: unknown command '{cmd}'", file=sys.stderr)
        return 1
    except PolicyError as e:
        print(f"unio remote-policy: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
