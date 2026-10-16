#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Test suite for remote role and ref policy guard."""
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import importlib.util
from pathlib import Path

SOURCE = Path(__file__).resolve().parent.parent
passed = 0


def check(label, condition, detail=""):
    global passed
    if not condition:
        msg = f"FAIL {label}"
        if detail:
            msg += f"\nDetail: {detail}"
        print(msg, file=sys.stderr)
        sys.exit(1)
    passed += 1
    print(f"  ok {label}", flush=True)


def main():
    global passed
    # Installed fixtures use project-owned private tmpfs paths, never shared /dev/shm files.
    with tempfile.TemporaryDirectory(prefix=".unio-remote-guard-", dir=os.environ.get("TMPDIR", str(SOURCE))) as tmp:
        base = Path(tmp)
        env = dict(
            os.environ,
            UNIO_BIN_DIR=str(base / "bin"),
            UNIO_CONF_DIR=str(base / "conf"),
            UNIO_COMPLETION_DIR=str(base / "completion"),
            UNIO_AUTO_VERIFY="0",
            UNIO_AUTO_SYNC="0",
            UNIO_TIMEOUT="30",
            GIT_AUTHOR_NAME="offline",
            GIT_COMMITTER_NAME="offline",
            GIT_AUTHOR_EMAIL="offline@example.invalid",
            GIT_COMMITTER_EMAIL="offline@example.invalid",
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_NOSYSTEM="1",
        )
        for key in ("UNIO_SAVE_TEST_FAULT", "UNIO_TEST_FAULT_DIR", "BASH_ENV"):
            env.pop(key, None)

        # Install Unio
        subprocess.run(["bash", str(SOURCE / "unio-install.sh")], env=env, check=True, capture_output=True)
        unio_bin = str(base / "bin" / "unio")

        # Project root with spaces in path
        proj_root = base / "project with spaces"
        repo = proj_root / "repo"
        repo.mkdir(parents=True)

        def run(args, cwd=repo, codes=(0,), extra=None):
            cp = subprocess.run(
                args,
                cwd=cwd,
                env=dict(env, **(extra or {})),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=60,
            )
            if cp.returncode not in codes:
                raise AssertionError(f"Command {args} failed with exit {cp.returncode}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}")
            return cp

        def git(*args, cwd=repo, codes=(0,)):
            return run(["git", *args], cwd=cwd, codes=codes)

        # Initialize repository and base commit
        git("init", "-q", "-b", "main")
        (repo / "tracked.txt").write_text("initial main content\n", encoding="utf-8")
        git("add", "tracked.txt")
        git("commit", "-qm", "initial main commit")
        c_main_initial = git("rev-parse", "HEAD").stdout.strip()

        # Initialize Unio project with worker mock
        run([unio_bin, "init", "mock"], cwd=repo)
        wt_mock = proj_root / "wt" / "mock"

        # Local bare fixture remotes (with spaces in path)
        remotes_dir = base / "bare remotes with spaces"
        remotes_dir.mkdir(parents=True)
        bare_dev = remotes_dir / "dev remote.git"
        bare_pub = remotes_dir / "public release.git"
        bare_same = remotes_dir / "same repo.git"
        bare_unpinned = remotes_dir / "unpinned remote.git"

        for b in (bare_dev, bare_pub, bare_same, bare_unpinned):
            subprocess.run(["git", "init", "--bare", "-q", str(b)], check=True)

        git("remote", "add", "origin", str(bare_dev))
        git("remote", "add", "public", str(bare_pub))
        git("remote", "add", "same", str(bare_same))
        git("remote", "add", "unapproved", str(bare_unpinned))

        # -------------------------------------------------------------
        # 1. Unconfigured policy: preserves simple existing projects
        # -------------------------------------------------------------
        cp = git("push", "origin", "main")
        check("unconfigured policy allows push to origin", cp.returncode == 0)

        # Worker guard: workers inside wt/mock never push
        cp = git("push", "origin", "main", cwd=wt_mock, codes=(1,))
        check("worker guard blocks worker worktree from pushing", cp.returncode == 1 and "workers do not push" in cp.stderr)

        # -------------------------------------------------------------
        # 2. CLI commands: show, set, install-guard
        # -------------------------------------------------------------
        cp = run([unio_bin, "remote-policy", "show"])
        check("show reports no policy configured initially", "none configured" in cp.stdout)

        # Set development role for origin
        cp = run([unio_bin, "remote-policy", "set", "origin", "development"])
        check("set development remote succeeded", "pinned remote 'origin' as development" in cp.stdout)

        # Set release role for public
        cp = run([unio_bin, "remote-policy", "set", "public", "release", "--branch", "main", "--tag-pattern", "refs/tags/v*"])
        check("set release remote succeeded", "pinned remote 'public' as release" in cp.stdout)

        # Set same-remote for same
        cp = run([unio_bin, "remote-policy", "set", "same", "same-remote", "--branch", "main"])
        check("set same-remote succeeded", "pinned remote 'same' as same-remote" in cp.stdout)

        # Install pre-push guard
        cp = run([unio_bin, "remote-policy", "install-guard"])
        check("install-guard command reports success", "pre-push guard installed" in cp.stdout)

        # Verify show command output
        cp = run([unio_bin, "remote-policy", "show", "--json"])
        data = json.loads(cp.stdout)
        check("show --json reports valid schema and remotes", data.get("configured") is True and len(data["policy"]["remotes"]) == 3)

        # Verify coord/remote-policy.json file permissions (must be private 0600)
        pol_path = proj_root / "coord" / "remote-policy.json"
        check("policy file exists and is owned with private mode 0600", pol_path.is_file() and (pol_path.stat().st_mode & 0o077 == 0))

        # -------------------------------------------------------------
        # 3. Development role: allowed dev push
        # -------------------------------------------------------------
        git("checkout", "-b", "dev")
        (repo / "dev_work.txt").write_text("private dev work\n", encoding="utf-8")
        git("add", "dev_work.txt")
        git("commit", "-qm", "dev feature commit")
        c_dev = git("rev-parse", "HEAD").stdout.strip()

        cp = git("push", "origin", "dev")
        check("allowed dev push to development remote", cp.returncode == 0)

        # -------------------------------------------------------------
        # 4. Release role: rejected dev branch push to public
        # -------------------------------------------------------------
        cp = git("push", "public", "dev", codes=(1,))
        check("rejected dev push to public release destination", cp.returncode == 1 and "refusing to push non-release branch" in cp.stderr)

        # -------------------------------------------------------------
        # 5. Prevent bypass attempts to release remote
        # -------------------------------------------------------------
        # 5a. dev:main
        cp = git("push", "public", "dev:main", codes=(1,))
        check("refused dev:main bypass to release destination", cp.returncode == 1 and "cannot target release branch" in cp.stderr)

        # 5b. HEAD:main
        cp = git("push", "public", "HEAD:main", codes=(1,))
        check("refused HEAD:main bypass to release destination", cp.returncode == 1 and "ambiguous or non-canonical source ref 'HEAD'" in cp.stderr)

        # 5c. raw object sha:main
        cp = git("push", "public", f"{c_dev}:refs/heads/main", codes=(1,))
        check("refused raw-object source bypass to release destination", cp.returncode == 1 and "raw object or non-branch source" in cp.stderr)

        # -------------------------------------------------------------
        # 6. Release role: allowed main branch push
        # -------------------------------------------------------------
        git("checkout", "main")
        (repo / "tracked.txt").write_text("clean release content\n", encoding="utf-8")
        git("commit", "-aqm", "clean release commit on main")
        c_main_clean = git("rev-parse", "HEAD").stdout.strip()

        cp = git("push", "public", "main")
        check("allowed main branch push to release destination", cp.returncode == 0)

        # -------------------------------------------------------------
        # 7. Release tag reachability validation
        # -------------------------------------------------------------
        # Create a release-named tag pointing to private dev commit
        git("tag", "v1.0.0-dev", c_dev)
        cp = git("push", "public", "v1.0.0-dev", codes=(1,))
        check(
            "refused release tag pointing to unmerged dev commit",
            cp.returncode == 1 and "not reachable from release branch" in cp.stderr,
        )

        # Create a valid release tag pointing to main commit
        git("tag", "v1.0.0", c_main_clean)
        cp = git("push", "public", "v1.0.0")
        check("allowed release tag pointing to release branch commit", cp.returncode == 0)

        # Tag not matching tag_pattern is rejected
        git("tag", "internal-test-tag", c_main_clean)
        cp = git("push", "public", "internal-test-tag", codes=(1,))
        check("refused tag not matching tag_pattern on release", cp.returncode == 1 and "does not match allowed release tag pattern" in cp.stderr)

        # -------------------------------------------------------------
        # 8. Mixed multi-ref forbidden updates
        # -------------------------------------------------------------
        (repo / "tracked.txt").write_text("another release update\n", encoding="utf-8")
        git("commit", "-aqm", "another release update on main")
        # Attempt to push both main (valid) and dev (forbidden) in one command
        cp = git("push", "public", "main", "dev", codes=(1,))
        check("rejected mixed multi-ref push containing forbidden dev ref", cp.returncode == 1 and "refusing to push non-release branch" in cp.stderr)

        # Verify that bare_pub main was NOT updated to the latest commit
        pub_head = subprocess.check_output(["git", "-C", str(bare_pub), "rev-parse", "refs/heads/main"]).decode().strip()
        check("mixed multi-ref rejection prevented publication of valid refs in batch", pub_head == c_main_clean)

        # -------------------------------------------------------------
        # 9. Explicit deletion policy on release destination
        # -------------------------------------------------------------
        cp = git("push", "public", ":refs/heads/main", codes=(1,))
        check("refused deletion of release branch on release remote", cp.returncode == 1 and "ref deletion 'refs/heads/main' on release destination" in cp.stderr)

        cp = git("push", "public", ":refs/tags/v1.0.0", codes=(1,))
        check("refused deletion of release tag on release remote", cp.returncode == 1 and "ref deletion 'refs/tags/v1.0.0' on release destination" in cp.stderr)

        # -------------------------------------------------------------
        # 10. Same-remote configuration
        # -------------------------------------------------------------
        # Allowed: push dev branch to dev branch on same
        cp = git("push", "same", "dev")
        check("same-remote: allowed pushing dev branch", cp.returncode == 0)

        # Allowed: push main branch to main branch on same
        cp = git("push", "same", "main")
        check("same-remote: allowed pushing main branch", cp.returncode == 0)

        # Rejected: pushing dev:main on same (fast-forward candidate rejected by policy)
        git("checkout", "dev")
        git("merge", "-q", "-m", "sync main into dev", "main")
        cp = git("push", "same", "dev:main", codes=(1,))
        check("same-remote: refused dev:main bypass", cp.returncode == 1 and "cannot target release branch" in cp.stderr)

        # Rejected: pushing HEAD:main on same
        cp = git("push", "same", "HEAD:main", codes=(1,))
        check("same-remote: refused HEAD:main bypass", cp.returncode == 1 and "ambiguous or non-canonical source ref 'HEAD'" in cp.stderr)

        # Rejected: pushing dev-pointing release tag on same
        cp = git("push", "same", "v1.0.0-dev", codes=(1,))
        check("same-remote: refused release tag pointing to unmerged dev commit", cp.returncode == 1 and "not reachable from release branch" in cp.stderr)

        # Allowed: pushing valid release tag on same
        cp = git("push", "same", "v1.0.0")
        check("same-remote: allowed release tag on main commit", cp.returncode == 0)

        # Rejected: deleting release branch on same
        cp = git("push", "same", ":refs/heads/main", codes=(1,))
        check("same-remote: refused deletion of release branch", cp.returncode == 1 and "ref deletion of release branch" in cp.stderr)

        # -------------------------------------------------------------
        # 11. URL rewriting (pushInsteadOf) and pushurl safety
        # -------------------------------------------------------------
        # Configure a dummy remote name that rewrites to public release
        dummy_url = "dummy://internal.invalid/repo.git"
        git("remote", "add", "rewritten", dummy_url)
        # Owner pinned dummy_url as development
        run([unio_bin, "remote-policy", "set", "rewritten", "development"])
        # Malicious or accidental git config redirects push to public release
        git("config", f"url.{bare_pub.as_uri()}/.pushInsteadOf", dummy_url)

        # Attempt to push dev branch to 'rewritten'
        cp = git("push", "rewritten", "dev", codes=(1, 0))
        check(
            "URL rewriting: detected resolved destination and refused dev push",
            cp.returncode == 1 and "refusing to push non-release branch" in cp.stderr,
            detail=f"rc={cp.returncode} stdout={cp.stdout} stderr={cp.stderr}",
        )

        # Multiple push URLs for a remote: dev + release
        git("remote", "add", "multipush", str(bare_dev))
        git("remote", "set-url", "--add", "--push", "multipush", str(bare_dev))
        git("remote", "set-url", "--add", "--push", "multipush", str(bare_pub))
        cp = git("push", "multipush", "dev", codes=(1,))
        check(
            "multiple push destinations: refused pushing dev refs when release is among targets",
            cp.returncode == 1 and ("multiple push destinations" in cp.stderr or "refusing to push non-release branch" in cp.stderr),
        )

        # -------------------------------------------------------------
        # 12. Unpinned destination rejected
        # -------------------------------------------------------------
        cp = git("push", "unapproved", "main", codes=(1,))
        check(
            "refused push to unpinned destination",
            cp.returncode == 1 and "refusing push to unpinned destination" in cp.stderr,
        )

        # -------------------------------------------------------------
        # 13. Existing owner hook preservation and chaining
        # -------------------------------------------------------------
        # Create a new test repo with pre-existing owner hook
        repo_chained = proj_root / "repo_chained"
        run(["git", "clone", "-q", str(bare_dev), str(repo_chained)])
        (repo_chained / "f.txt").write_text("test commit in chained repo\n", encoding="utf-8")
        git("add", "f.txt", cwd=repo_chained)
        git("commit", "-qm", "chained repo commit", cwd=repo_chained)

        hooks_chained = repo_chained / ".git" / "hooks"
        hooks_chained.mkdir(parents=True, exist_ok=True)
        owner_marker = repo_chained / "owner_hook_ran.log"
        owner_hook = hooks_chained / "pre-push"
        owner_hook.write_text(f"#!/bin/sh\necho \"owner hook ran with args: $@\" > {shlex.quote(str(owner_marker))}\nexit 0\n", encoding="utf-8")
        os.chmod(str(owner_hook), 0o755)

        # Run install-guard on the project
        run([unio_bin, "remote-policy", "install-guard"], cwd=repo_chained)

        # Verify pre-push.owner was created
        owner_backup = hooks_chained / "pre-push.owner"
        check("install-guard backed up existing owner hook to pre-push.owner", owner_backup.is_file())

        # Push to origin from repo_chained: verify owner hook still executed!
        cp = git("push", "origin", "main", cwd=repo_chained)
        check("push succeeded with chained owner hook", cp.returncode == 0)
        check("existing owner hook executed during push", owner_marker.is_file() and "owner hook ran" in owner_marker.read_text(encoding="utf-8"))

        # If owner hook exits non-zero, push must fail
        owner_backup.write_text("#!/bin/sh\necho 'owner hook deliberate failure' >&2\nexit 42\n", encoding="utf-8")
        (repo_chained / "f.txt").write_text("another\n", encoding="utf-8")
        git("commit", "-aqm", "another", cwd=repo_chained)
        cp = git("push", "origin", "main", cwd=repo_chained, codes=(42, 1))
        check("chained owner hook failure aborts push", cp.returncode in (42, 1) and "owner hook deliberate failure" in cp.stderr)

        # -------------------------------------------------------------
        # 14. Credential redaction: tokens never logged or printed
        # -------------------------------------------------------------
        secret_token = "SUPER_SECRET_PAT_TOKEN_999"
        cred_url = f"https://myuser:{secret_token}@github.example.invalid/org/secret-repo.git"
        run([unio_bin, "remote-policy", "set", cred_url, "development"])

        # Check show output
        cp = run([unio_bin, "remote-policy", "show"])
        check("credential token is redacted in show output", secret_token not in cp.stdout and secret_token not in cp.stderr)

        # Check policy file content
        pol_raw = pol_path.read_text(encoding="utf-8")
        check("credential token is not stored in remote-policy.json", secret_token not in pol_raw)

        # -------------------------------------------------------------
        # All checks passed
        # -------------------------------------------------------------
        print(f"\nPASS: all {passed} remote guard checks passed successfully.")


def regressions():
    """Collect independent old-fail/new-pass evidence without contacting a network."""
    spec = importlib.util.spec_from_file_location("guard", SOURCE / "tools/remote-guard.py")
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    results = []

    def case(name, fn):
        try:
            ok = bool(fn())
        except Exception as exc:
            # Never include exception text: malformed URLs can contain secrets.
            results.append({"case": name, "pass": False, "exception_type": type(exc).__name__})
            return
        results.append({"case": name, "pass": ok})

    def refused(fn):
        try:
            fn()
        except guard.PolicyError:
            return True
        return False

    with tempfile.TemporaryDirectory(prefix=".remote-regression-", dir=os.environ.get("TMPDIR", str(SOURCE))) as tmp:
        base = Path(tmp)
        env = dict(os.environ, UNIO_BIN_DIR=str(base / "bin"), UNIO_CONF_DIR=str(base / "conf"),
                   UNIO_COMPLETION_DIR=str(base / "completion"), UNIO_AUTO_VERIFY="0", UNIO_AUTO_SYNC="0",
                   GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1", GIT_AUTHOR_NAME="offline",
                   GIT_COMMITTER_NAME="offline", GIT_AUTHOR_EMAIL="offline@example.invalid",
                   GIT_COMMITTER_EMAIL="offline@example.invalid")
        for key in ("BASH_ENV", "UNIO_SAVE_TEST_FAULT", "UNIO_TEST_FAULT_DIR"):
            env.pop(key, None)

        def run(args, cwd=None, input=None, override=None):
            return subprocess.run(args, cwd=cwd, env=dict(env, **(override or {})), input=input,
                                  text=True, capture_output=True, timeout=60)

        def git(*args):
            cp = run(["git", "-C", str(repo), *args])
            assert cp.returncode == 0
            return cp.stdout.strip()

        root = base / "project with spaces"
        repo = root / "repo"
        repo.mkdir(parents=True)
        coord = root / "coord"
        coord.mkdir(mode=0o700)
        policy_path = coord / "remote-policy.json"
        git("init", "-q", "-b", "main")
        git("commit", "--allow-empty", "-qm", "fixture")
        git("branch", "dev")
        oid = git("rev-parse", "HEAD")
        refs = [("refs/heads/dev", oid, "refs/heads/main", "0" * 40)]
        dest = base / "bare destination with spaces.git"
        other = base / "other bare.git"
        unknown = base / "unknown bare.git"
        for path in (dest, other, unknown):
            assert run(["git", "init", "--bare", "-q", str(path)]).returncode == 0
        git("remote", "add", "origin", str(dest))
        git("remote", "add", "release", str(other))

        def cfg(role, url):
            return dict(role=role, url_hashes=[guard.hash_url(str(url))], redacted_urls=[guard.redact_url(str(url))],
                        release_branch="main", tag_pattern="refs/tags/v*", allow_deletions=False)

        def policy(remotes=None):
            return dict(schema_version=1, enabled=True, release_branch="main", tag_pattern="refs/tags/v*",
                        allow_deletions=False, remotes=remotes or {"origin": cfg("development", dest), "release": cfg("release", other)})

        def raw(doc):
            policy_path.write_text(doc if isinstance(doc, str) else json.dumps(doc))
            policy_path.chmod(0o600)

        raw(policy({"dev": cfg("development", dest), "pub": cfg("release", dest)}))
        case("conflicting roles rejected while checking dev:main", lambda: refused(lambda: guard.verify_push(root, repo, "origin", str(dest), refs)))
        raw(policy())
        case("conflicting roles rejected before configuration write", lambda: refused(lambda: guard.cli_set(root, str(dest), "release")))
        raw(policy())
        git("remote", "set-url", "--add", "--push", "origin", str(dest))
        git("remote", "set-url", "--add", "--push", "origin", str(other))
        case("all push destinations apply release source rule", lambda: refused(lambda: guard.verify_push(root, repo, "origin", str(dest), refs)))
        git("remote", "set-url", "--delete", "--push", "origin", ".*")
        git("remote", "set-url", "--add", "--push", "origin", str(dest))
        git("remote", "set-url", "--add", "--push", "origin", str(unknown))
        case("unpinned second push destination refused before refs", lambda: refused(lambda: guard.verify_push(root, repo, "origin", str(dest), [])))
        git("remote", "set-url", "--delete", "--push", "origin", ".*")
        git("remote", "add", "rewrite", "test-remote://fixture/repo")
        git("config", f"url.{other.as_uri()}/.pushInsteadOf", "test-remote://fixture/repo")
        case("rewrite configuration detects existing release pin", lambda: refused(lambda: guard.cli_set(root, "rewrite", "development")))

        sentinel = "SYNTHETIC_CREDENTIAL_SENTINEL"
        urls = [f"https://{sentinel}@example.invalid/repo", f"https://u:{sentinel}@example.invalid/repo",
                f"https://example.invalid/repo?token={sentinel}", f"https://example.invalid/repo#{sentinel}",
                f"ssh://{sentinel}@example.invalid/repo", f"{sentinel}@example.invalid:repo"]
        # Usernames must never become regex replacement templates.
        urls.extend([f"https://u\\g<3>:{sentinel}@example.invalid/repo",
                     f"https://u\\3:{sentinel}@example.invalid/repo"])
        for index, url in enumerate(urls):
            case(f"safe redaction and normalization form {index}", lambda url=url: sentinel not in guard.redact_url(url) + guard.normalize_url(url))
            raw(policy())
            cp = run([sys.executable, "-B", str(SOURCE / "tools/remote-guard.py"), "set", url, "development"], cwd=repo)
            case(f"no credential persistence or CLI output form {index}", lambda cp=cp: cp.returncode == 0 and sentinel not in cp.stdout + cp.stderr + policy_path.read_text())
        raw(policy())
        cp = run([sys.executable, "-B", str(SOURCE / "tools/remote-guard.py"), "set", f"https://[{sentinel}/bad", "development"], cwd=repo)
        case("malformed URL errors contain no credential", lambda: cp.returncode != 0 and sentinel not in cp.stdout + cp.stderr)
        case("query destinations remain distinct", lambda: guard.hash_url(urls[2]) != guard.hash_url("https://example.invalid/repo?token=different"))
        case("SSH users remain distinct", lambda: guard.hash_url("ssh://a@example.invalid/repo") != guard.hash_url("ssh://b@example.invalid/repo"))

        for label, mutate in [
            ("enabled string", lambda d: d.update(enabled="")),
            ("schema boolean", lambda d: d.update(schema_version=True)),
            ("unknown key", lambda d: d.update(unexpected=True)),
            ("invalid role", lambda d: d["remotes"]["origin"].update(role="private")),
            ("invalid hash", lambda d: d["remotes"]["origin"].update(url_hashes=["bad"])),
            ("nonboolean deletion flag", lambda d: d.update(allow_deletions=0)),
            ("invalid branch", lambda d: d.update(release_branch="bad..branch")),
            ("invalid tag namespace", lambda d: d.update(tag_pattern="refs/heads/*")),
            ("unbounded remotes", lambda d: d.update(remotes={str(i): cfg("development", dest) for i in range(257)})),
        ]:
            doc = policy()
            mutate(doc)
            raw(doc)
            case(f"strict schema refuses {label}", lambda: refused(lambda: guard.load_policy(root)))
        raw('{"schema_version":1,"enabled":true,"enabled":false,"remotes":{}}')
        case("duplicate JSON keys refused", lambda: refused(lambda: guard.load_policy(root)))
        policy_path.unlink()
        target = base / "policy-target"
        target.write_text(json.dumps(policy()))
        target.chmod(0o600)
        policy_path.symlink_to(target)
        case("policy symlink refused", lambda: refused(lambda: guard.load_policy(root)))
        policy_path.unlink()
        policy_path.symlink_to(base / "absent")
        case("dangling configured policy refused", lambda: refused(lambda: guard.load_policy(root)))
        policy_path.unlink()
        os.mkfifo(policy_path, 0o600)
        case("FIFO refused without blocking", lambda: refused(lambda: guard.load_policy(root)))
        policy_path.unlink()
        coord.rename(root / "real-coord")
        coord.symlink_to(root / "real-coord", target_is_directory=True)
        case("coord symlink refused", lambda: refused(lambda: guard.load_policy(root)))
        coord.unlink()
        (root / "real-coord").rename(coord)
        case("clean unconfigured default allowed", lambda: guard.verify_push(root, repo, "origin", str(dest), refs) is None)
        raw(policy())
        for opts in [["--unknown"], ["--branch"], ["--branch", "bad..branch"], ["--tag-pattern", "refs/heads/*"], ["--branch", ""], ["--branch", "main", "--branch", "dev"]]:
            before = policy_path.read_bytes()
            cp = run([sys.executable, "-B", str(SOURCE / "tools/remote-guard.py"), "set", "origin", "development", *opts], cwd=repo)
            case("invalid CLI arguments refused " + repr(opts), lambda cp=cp, before=before: cp.returncode != 0 and policy_path.read_bytes() == before)

        # Install and exercise both hook creation routes only in private fixtures.
        assert run(["bash", str(SOURCE / "unio-install.sh")]).returncode == 0
        unio = str(base / "bin/unio")
        case("installed helper byte-identical", lambda: (base / "conf/lib/remote-guard.py").read_bytes() == (SOURCE / "tools/remote-guard.py").read_bytes())
        hooks = repo / ".git/hooks"
        hook = hooks / "pre-push"
        backup = hooks / "pre-push.owner"
        owner = '#!/bin/sh\ncat > "$PWD/owner-input"\nprintf "%s\\n" "$@" > "$PWD/owner-args"\nexit 0\n'
        hook.write_text(owner)
        hook.chmod(0o755)
        guard.cli_install_guard(root, repo)
        python_hook = hook.read_bytes()
        cp = run(["git", "push", "origin", "main"], cwd=repo)
        case("installed owner hook receives refs and spaced destination", lambda: cp.returncode == 0 and (repo / "owner-input").is_file() and "refs/heads/main" in (repo / "owner-input").read_text() and str(dest) in (repo / "owner-args").read_text())
        hook.write_text("#!/bin/sh\nexit 37\n")
        current, saved = hook.read_bytes(), backup.read_bytes()
        case("existing owner backup collision refuses without clobber", lambda: refused(lambda: guard.cli_install_guard(root, repo)) and hook.read_bytes() == current and backup.read_bytes() == saved)
        hook.unlink()
        hook.symlink_to(base / "hook-victim")
        (base / "hook-victim").write_text("preserve")
        case("hook symlink refused", lambda: refused(lambda: guard.cli_install_guard(root, repo)) and (base / "hook-victim").read_text() == "preserve")
        hook.unlink()
        hook.write_bytes(python_hook)
        hook.chmod(0o755)
        git("config", "core.hooksPath", str(base / "custom hooks"))
        case("custom hooksPath explicitly refused", lambda: refused(lambda: guard.cli_install_guard(root, repo)))
        git("config", "--unset", "core.hooksPath")
        hooks.rename(repo / ".git/real-hooks")
        hooks.symlink_to(repo / ".git/real-hooks", target_is_directory=True)
        case("hook directory symlink refused", lambda: refused(lambda: guard.cli_install_guard(root, repo)))
        hooks.unlink()
        (repo / ".git/real-hooks").rename(hooks)

        # Shell init writes the other hook implementation. Separate project avoids
        # initialization mutating any operator checkout or its hooks.
        shell_root = base / "shell project with spaces"
        shell_repo = shell_root / "repo"
        shell_repo.mkdir(parents=True)
        assert run(["git", "init", "-q", "-b", "main"], cwd=shell_repo).returncode == 0
        assert run(["git", "commit", "--allow-empty", "-qm", "fixture"], cwd=shell_repo).returncode == 0
        cp = run([unio, "init", "mock"], cwd=shell_repo)
        case("shell init succeeds", lambda: cp.returncode == 0)
        shell_hook = shell_repo / ".git/hooks/pre-push"
        case("both hook generators byte-identical", lambda: shell_hook.read_bytes() == python_hook)
        shell_backup = shell_hook.with_name("pre-push.owner")
        shell_hook.write_text("#!/bin/sh\nexit 36\n")
        shell_backup.write_text("#!/bin/sh\nexit 35\n")
        shell_hook.chmod(0o755)
        shell_backup.chmod(0o755)
        cp = run([unio, "init", "mock"], cwd=shell_repo)
        case("shell init preserves colliding owner hooks", lambda: cp.returncode != 0 and shell_hook.read_text() == "#!/bin/sh\nexit 36\n" and shell_backup.read_text() == "#!/bin/sh\nexit 35\n")

        # Remove all available helpers and hide unio, leaving system git/python.
        (base / "conf/lib/remote-guard.py").rename(base / "hidden-helper")
        safe_path = str(base / "hook-bin")
        Path(safe_path).mkdir()
        for executable in ("git", "python3", "cat", "dirname"):
            (Path(safe_path) / executable).symlink_to(shutil.which(executable))
        hook.write_bytes(python_hook)
        hook.chmod(0o755)
        data = f"refs/heads/main {oid} refs/heads/main {'0' * 40}\n"
        cp = run([str(hook), "origin", str(dest)], cwd=repo, input=data, override={"PATH": safe_path})
        case("configured missing helper refuses", lambda: cp.returncode != 0)
        cp = run([str(hook), "origin", str(dest)], cwd=repo, input="", override={"PATH": safe_path})
        case("configured missing helper refuses empty ref batch", lambda: cp.returncode != 0)
        policy_path.unlink()
        cp = run([str(hook), "origin", str(dest)], cwd=repo, input=data, override={"PATH": safe_path})
        case("unconfigured missing helper preserves owner hook", lambda: cp.returncode == 0)
        (repo / ".unio-worker").write_text("mock\n")
        cp = run([str(hook), "origin", str(dest)], cwd=repo, input=data, override={"PATH": safe_path})
        case("missing helper still blocks workers", lambda: cp.returncode != 0 and "workers do not push" in cp.stderr)

    print(json.dumps({"regressions": results, "passed": sum(r["pass"] for r in results), "total": len(results)}, indent=2))
    return all(r["pass"] for r in results)


if __name__ == "__main__":
    if sys.argv[1:] != ["--regressions"]:
        main()
    sys.exit(0 if regressions() else 1)
