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
    with tempfile.TemporaryDirectory(prefix="unio-remote-guard-") as tmp:
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


if __name__ == "__main__":
    main()
