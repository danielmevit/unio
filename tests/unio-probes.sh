#!/usr/bin/env bash
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
# =====================================================================
# tests/unio-probes.sh — adversarial probes against unio ITSELF
# (SABAT-1: saboteur seat; target = the orchestration machinery, not an app).
#
# Every probe builds a complete unio project inside a throwaway
# `mktemp -d` sandbox: the tool is installed fresh with UNIO_BIN_DIR /
# UNIO_CONF_DIR / UNIO_COMPLETION_DIR all pointed inside the
# sandbox, git repos live under it, and all `unio` calls run with cwd
# inside it. Nothing touches the operator's real ~/.config/unio, real
# projects, or any path outside the sandbox. Sandboxes are removed on exit
# (UNIO_PROBE_KEEP=1 keeps them for inspection).
#
# Mock agents are plain shell lines in agents.conf — the selftest technique;
# zero AI quota is spent.
#
# Verdicts:
#   HELD   — unio withstood the probe (the guarantee held)
#   BROKEN — a genuine defect was demonstrated; the broken promise is cited
#
# Exit status: 0 = everything HELD, 1 = at least one BROKEN, 2 = harness error.
#
# Usage:
#   bash tests/unio-probes.sh            run all probes
#   bash tests/unio-probes.sh --list     print probe names, run nothing
#   bash tests/unio-probes.sh --only <substring>   run matching probes
# =====================================================================
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
INSTALLER="$HERE/../unio-install.sh"
[ -f "$INSTALLER" ] || { echo "harness: $INSTALLER not found" >&2; exit 2; }

# Deterministic git identity inside sandboxes; short timeouts so no probe
# can hang the suite.
export GIT_AUTHOR_NAME=unio-probe GIT_AUTHOR_EMAIL=probe@unio.local
export GIT_COMMITTER_NAME=unio-probe GIT_COMMITTER_EMAIL=probe@unio.local
export UNIO_TIMEOUT=120 UNIO_VERIFY_TIMEOUT=60 UNIO_REVIEW_TIMEOUT=60

KEEP=${UNIO_PROBE_KEEP:-0}
HELD_N=0 BROKEN_N=0
SB="" AT="" REPO="" ROOT=""
NOTE="" PROMISE=""
SANDBOXES=()

cleanup() {
  [ "$KEEP" = "1" ] && return 0
  local s
  for s in ${SANDBOXES[@]+"${SANDBOXES[@]}"}; do
    [ -n "$s" ] && [ -d "$s" ] && rm -rf "$s"
  done
}
trap cleanup EXIT

# ---------------------------------------------------------------- harness
sb_boot() { # fresh sandbox + the tool installed entirely inside it
  SB=$(mktemp -d); SANDBOXES+=("$SB")
  UNIO_BIN_DIR="$SB/bin" UNIO_CONF_DIR="$SB/conf" \
    UNIO_COMPLETION_DIR="$SB/comp" bash "$INSTALLER" >/dev/null 2>&1 \
    || { echo "harness: installer failed inside sandbox" >&2; exit 2; }
  export UNIO_CONF_DIR="$SB/conf"
  AT="$SB/bin/unio"
}

sb_repo() { # $1 = path of the "repo clone" to create (base branch: dev)
  REPO="$1"; ROOT=$(dirname "$REPO")
  git init -q -b dev "$REPO" || exit 2
  git -C "$REPO" commit -qm "initial commit" --allow-empty || exit 2
}

sb_init() { ( cd "$REPO" && "$AT" init "$@" >/dev/null 2>&1 ); }

sb_conf() { cat > "$UNIO_CONF_DIR/agents.conf"; }

sb_task() { # $1=task id  $2=Allowed-scope body  $3=Validate body
  printf '# Task %s — worker: mock\n\n## Goal\nprobe\n\n## Context\nprobe\n\n## Allowed scope\n%s\n\n## Constraints\nnone\n\n## Validate\n%s\n\n## Done means\ncommitted\n\n## Report\nSUMMARY\n' \
    "$1" "$2" "$3" > "$ROOT/coord/tasks/$1.md"
}

at() { ( cd "$REPO" && "$AT" "$@" ); }

# ------------------------------------------------------------- framework
declare -a PROBE_NAMES=()
declare -A PROBE_FN=()
declare -A PROBE_ABOUT=()
probe() { PROBE_NAMES+=("$1"); PROBE_FN["$1"]="$2"; PROBE_ABOUT["$1"]="$3"; }

run_probe() {
  local name="$1" rc
  NOTE="" PROMISE=""
  "${PROBE_FN[$name]}"; rc=$?
  case "$rc" in
    0) HELD_N=$((HELD_N+1))
       printf 'HELD   %-40s %s\n' "$name" "$NOTE";;
    1) BROKEN_N=$((BROKEN_N+1))
       printf 'BROKEN %-40s %s\n' "$name" "$NOTE"
       [ -n "$PROMISE" ] && printf '       promise: %s\n' "$PROMISE";;
    *) echo "ERROR  $name — probe malfunctioned" >&2; exit 2;;
  esac
}

# =====================================================================
# CONTROLS — sanity that the harness can also confirm what works.
# =====================================================================

p_control_basic_loop() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo line >> hello.txt; git add hello.txt; git commit -qm "T: hello"; echo done'
EOF
  sb_task T-basic "- hello.txt" '$ test -f hello.txt'
  at run mock T-basic >/dev/null 2>&1 \
    || { NOTE="HARNESS SUSPECT: plain in-scope run failed"; return 1; }
  at verify mock T-basic >/dev/null 2>&1 \
    || { NOTE="HARNESS SUSPECT: plain in-scope verify failed"; return 1; }
  NOTE="run + verify PASS for an ordinary in-scope task"
  return 0
}

p_control_worker_lock() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo line >> hello.txt; git add hello.txt; git commit -qm x'
EOF
  sb_task T-lock "- hello.txt" ''
  ( exec 9>>"$ROOT/coord/.locks/mock.lock"; flock 9; sleep 3 ) &
  local holder=$!
  sleep 1
  local out rc=0
  out=$(at run mock T-lock 2>&1) || rc=$?
  wait "$holder" 2>/dev/null || true
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'already running'; then
    NOTE="per-worker flock refuses a concurrent run"
    return 0
  fi
  NOTE="concurrent run was NOT refused (rc=$rc)"; return 1
}

p_control_id_escape() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'echo hi'
EOF
  sb_task T-id "- hello.txt" ''
  local r1=0 r2=0
  at run mock ../reports/T-id >/dev/null 2>&1 || r1=$?
  at diff ../repo           >/dev/null 2>&1 || r2=$?
  if [ "$r1" -ne 0 ] && [ "$r2" -ne 0 ]; then
    NOTE="check_id refuses ../-style escapes for task and worker ids"
    return 0
  fi
  NOTE="path escape NOT refused (run rc=$r1, diff rc=$r2)"; return 1
}

# =====================================================================
# FINDING PROBES
# =====================================================================

# --- F1: not every "$ " Validate line is machine-run ------------------
# cmd_verify's read-loop feeds Validate lines on stdin, and the command it
# runs inherits that same stdin. A command that reads stdin (cat, codex-style
# agents, ...) swallows the remaining lines; they are never read, never run,
# never counted. cmd_smoke has an explicit </dev/null guard with a comment
# describing exactly this failure — cmd_verify lacks it.
p_verify_validate_stdin_swallow() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo line >> hello.txt; git add hello.txt; git commit -qm "T: hello"; echo done'
EOF
  sb_task T-stdin "- hello.txt" '$ cat >/dev/null
$ false'
  at run mock T-stdin >/dev/null 2>&1
  local out rc=0
  out=$(at verify mock T-stdin 2>&1) || rc=$?
  if [ "$rc" -eq 0 ] && printf '%s' "$out" | grep -q 'validate : 1/1 passed'; then
    NOTE="verify ran 1 of 2 '\$ ' lines and PASSed: '\$ cat' ate the '\$ false' line through the loop's stdin"
    PROMISE="PROTOCOL §3 — 'Validate: every \$ command line is machine-run by verify and must exit 0'"
    return 1
  fi
  NOTE="all Validate lines were executed (rc=$rc)"; return 0
}

# --- F2: committed rename out-of-scope -> in-scope passes the gate ----
# verify's changed-path list comes from `git diff --name-only` (shows only
# the rename DESTINATION) and porcelain output filtered through
# sed 's/.* -> //' (also keeps only the destination). The deletion of the
# out-of-scope source path is never scope-checked.
p_verify_scope_rename_source_blind() {
  sb_boot; sb_repo "$SB/proj/repo"
  mkdir -p "$REPO/src"; echo v1 > "$REPO/src/tracked.txt"
  git -C "$REPO" add src/tracked.txt
  git -C "$REPO" commit -qm "add src/tracked.txt"
  git -C "$REPO" config diff.renames true   # default; spelled out for determinism
  sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; mkdir -p tests; git mv src/tracked.txt tests/tracked.txt; git commit -qm "T: move"; echo done'
EOF
  sb_task T-ren "- tests/" '$ test -f tests/tracked.txt'
  at run mock T-ren >/dev/null 2>&1
  local out rc=0 gone=1
  out=$(at verify mock T-ren 2>&1) || rc=$?
  git -C "$ROOT/wt/mock" diff --name-status dev...HEAD 2>/dev/null \
    | grep -q '^R100.*src/tracked.txt' || gone=0
  if [ "$rc" -eq 0 ] && [ "$gone" = 1 ]; then
    NOTE="verify PASS (scope OK) while the diff DELETES out-of-scope src/tracked.txt via rename — only the destination is checked"
    PROMISE="PROTOCOL I1 + §4 — verify enforces the '- path' scope lines on the diff; FAILURE PROTOCOL: a violating diff is never merged as-is"
    return 1
  fi
  NOTE="verify caught the rename's source side (rc=$rc)"; return 0
}

# --- F3: dangling coord/base makes the gate blind, yet it PASSes ------
# verify suppresses the diff/rev-list errors (`2>/dev/null || true`,
# `|| echo 0`). With a base branch name that no longer exists, the committed
# diff vanishes from the evidence: scope is checked against uncommitted
# files only, commits=0, and any in-scope untracked file yields a PASS while
# out-of-scope commits sit on the branch unexamined.
p_verify_passes_on_vanished_base() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo x > forbidden.txt; git add forbidden.txt; git commit -qm "T: rogue"; mkdir -p tests; echo y > tests/ok.txt; echo done'
EOF
  sb_task T-ghost "- tests/" '$ test -f tests/ok.txt'
  at run mock T-ghost >/dev/null 2>&1
  echo ghost-branch > "$ROOT/coord/base"   # the name the OWNER file points at no longer exists
  local out rc=0 bad=1
  out=$(at verify mock T-ghost 2>&1) || rc=$?
  git -C "$ROOT/wt/mock" ls-tree -r --name-only HEAD | grep -qx 'forbidden.txt' || bad=0
  if [ "$rc" -eq 0 ] && [ "$bad" = 1 ]; then
    NOTE="base 'ghost-branch' does not exist: verify could diff nothing, yet PASSed with out-of-scope forbidden.txt committed on the branch"
    PROMISE="PROTOCOL §4 — verify is the 'machine gate': diff vs the scope lines; I10 — verification is evidence-based, and here there was no evidence"
    return 1
  fi
  NOTE="verify refuses to PASS on a dangling base (rc=$rc)"; return 0
}

# --- F4: off/on agent names are never validated -> path traversal -----
# check_id guards worker/task ids "so they cannot escape those directories",
# and the selftest even proves that for run/diff. cmd_off/cmd_on take an
# agent name that addresses files under $CONF_DIR/off/ — with no check_id.
p_off_on_path_traversal() {
  sb_boot   # no project needed: off/on touch only the conf dir
  ( cd "$SB" && "$AT" off '../escaped-marker' >/dev/null 2>&1 )
  local wrote=0 deleted=0
  [ -f "$SB/conf/escaped-marker" ] && wrote=1        # outside off/ — traversal
  : > "$SB/victim"
  ( cd "$SB" && "$AT" on '../../victim' >/dev/null 2>&1 )
  [ ! -e "$SB/victim" ] && deleted=1                 # unrelated file deleted
  if [ "$wrote" = 1 ] || [ "$deleted" = 1 ]; then
    NOTE="'off ../x' wrote a marker outside off/ (wrote=$wrote); 'on ../../x' deleted an unrelated file (deleted=$deleted)"
    PROMISE="install.sh check_id contract — names that address files 'cannot escape those directories'; off/on skip the check entirely"
    return 1
  fi
  NOTE="off/on refuse path-traversal agent names"; return 0
}

# --- F5: task ids allow '\n' and '"' -> ledger forgery -----------------
# check_id blocks slash/backslash/../ but not control characters or quotes.
# A newline inside a task id splits its ledger line in two; the tail can be
# a fully-formed forged event that `unio score` then counts as truth.
# (A '"' in an id likewise breaks the 'one JSON object per line' format.)
p_ledger_forgery_via_task_id_newline() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo line >> hello.txt; git add hello.txt; git commit -qm "T: hello"; echo done'
EOF
  local evil
  evil=$(printf 'FRG\n{"event":"merge","ts":"2026-07-26T00:00:00+00:00","worker":"forged","subject":"forged merge"}')
  sb_task "$evil" "- hello.txt" ''
  local rc=0
  at run mock "$evil" >/dev/null 2>&1 || rc=$?
  # Refusing the crafted id outright is the correct outcome, not a harness
  # fault: check_id rejects whitespace/control characters in ids, so the
  # forgery never gets a chance to reach the ledger.
  [ "$rc" -eq 0 ] || { NOTE="crafted task id refused before it could reach the ledger (rc=$rc)"; return 0; }
  # NB: no `score | grep -q` pipeline here — under pipefail, grep -q's early
  # exit SIGPIPEs the producer and flips the result.
  local srow
  srow=$(at score 2>/dev/null)
  if case "$srow" in *forged*) true;; *) false;; esac; then
    NOTE="a newline in the task id injected a fake 'merge' event — 'unio score' credits a worker 'forged' that never existed"
    PROMISE="PROTOCOL §3 — ledger.jsonl is 'one JSON object per event', the append-only machine history; status() even comments ids have 'no newlines/globs'"
    return 1
  fi
  NOTE="crafted task id could not inject ledger events"; return 0
}

# --- F6: non-ASCII in-scope paths get a false VIOLATION ----------------
# git C-quotes such paths (core.quotePath, default on): porcelain and
# diff --name-only yield "t\303\244st.txt". verify compares that quoted
# form against the raw scope pattern and rejects a worker that stayed in
# scope — the gate lies in the fail-closed direction.
p_verify_unicode_false_violation() {
  sb_boot; sb_repo "$SB/proj/repo"
  git -C "$REPO" config core.quotepath true   # default; spelled out for determinism
  sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo x > täst.txt; git add täst.txt; git commit -qm "T: uni"; echo done'
EOF
  sb_task T-uni "- täst.txt" '$ test -f täst.txt'
  at run mock T-uni >/dev/null 2>&1
  local out rc=0
  out=$(at verify mock T-uni 2>&1) || rc=$?
  if [ "$rc" -ne 0 ] && printf '%s' "$out" | grep -q 'VIOLATION'; then
    NOTE="in-scope non-ASCII path flagged as scope VIOLATION — git C-quotes it and the matcher compares the quoted form"
    PROMISE="PROTOCOL §4/I10 — the gate judges the worker's actual changed paths; a conforming worker must not be rejected"
    return 1
  fi
  NOTE="unicode paths are scope-checked correctly (rc=$rc)"; return 0
}

# --- F7: guard hooks misfire when repo/ is itself a linked worktree ----
# The hooks key on the git-dir path matching */worktrees/*. When the project
# clone is itself a linked worktree (a common layout), repo/'s git-dir lives
# under .git/worktrees/ too: the owner's own commits are refused and the
# post-merge hook skips ledger-logging (it exits 0 on the same match).
p_guard_hooks_misfire_linked_worktree_repo() {
  sb_boot
  git init -q -b main "$SB/main" || exit 2
  git -C "$SB/main" commit -qm "initial" --allow-empty
  mkdir -p "$SB/proj"
  git -C "$SB/main" worktree add "$SB/proj/repo" -b dev >/dev/null 2>&1 \
    || { NOTE="HARNESS SUSPECT: cannot create linked worktree"; return 2; }
  REPO="$SB/proj/repo"; ROOT="$SB/proj"
  sb_init mock || return 2
  grep -q 'unio guard' "$SB/main/.git/hooks/pre-commit" \
    || { NOTE="HARNESS SUSPECT: hooks not installed"; return 2; }
  echo owner-doc > "$REPO/owner.txt"; git -C "$REPO" add owner.txt
  local cout crc=0 blocked=0 logged=0 mrc=0
  cout=$(git -C "$REPO" commit -qm "owner: doc" 2>&1) || crc=$?
  [ "$crc" -ne 0 ] && printf '%s' "$cout" | grep -q 'unio guard' && blocked=1
  # and is a merge into the base still ledger-logged from repo/?
  git -C "$ROOT/wt/mock" commit -qm "mock work" --allow-empty
  git -C "$REPO" merge --no-ff agent/mock -m "merge T" >/dev/null 2>&1 || mrc=$?
  [ -f "$ROOT/coord/reports/ledger.jsonl" ] \
    && grep -q '"event":"merge"' "$ROOT/coord/reports/ledger.jsonl" && logged=1
  if [ "$blocked" = 1 ] || { [ "$mrc" -eq 0 ] && [ "$logged" = 0 ]; }; then
    NOTE="repo/ is a linked worktree: owner's own commit blocked=$blocked by the 'worker guard'; merge into base ledger-logged=$logged"
    PROMISE="PROTOCOL §2 — hooks guard 'a worker worktree' (repo/ is the OWNER's), and 'every merge into the base branch is recorded' by the post-merge hook"
    return 1
  fi
  NOTE="guard hooks tell a linked-worktree repo/ apart from a worker worktree"; return 0
}

# --- F8: a worker can rewrite the BASE branch; nothing notices ---------
# Hooks wrap commit/push/merge — not plumbing. From its own worktree a
# worker can `git update-ref refs/heads/dev HEAD`: the human gate is
# bypassed with no merge, no ledger event, and doctor still reports clear.
p_worker_can_rewrite_base_branch() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo unaudited > payload.txt; git add payload.txt; git commit -qm "T: payload"; git update-ref refs/heads/dev HEAD; echo done'
EOF
  sb_task T-base "- payload.txt" ''
  at run mock T-base >/dev/null 2>&1
  local moved=0 logged=0 docrc=0
  [ "$(git -C "$REPO" rev-parse dev)" = "$(git -C "$ROOT/wt/mock" rev-parse HEAD)" ] && moved=1
  grep -q '"event":"merge"' "$ROOT/coord/reports/ledger.jsonl" 2>/dev/null && logged=1
  at doctor >/dev/null 2>&1 || docrc=$?
  if [ "$moved" = 1 ] && [ "$logged" = 0 ]; then
    NOTE="worker advanced the BASE branch from its worktree via git update-ref; no hook fired, ledger has no merge event, doctor rc=$docrc (clear)"
    PROMISE="PROTOCOL I5 — 'workers never touch the base branch (enforced by guard hooks)' / GUIDEBOOK ch17 — 'the hooks enforce this physically'; I3 — only OWNER merges"
    return 1
  fi
  NOTE="base branch cannot be moved from a worker worktree"; return 0
}

# --- F9: kill trusts the pidfile blindly (pid-reuse friendly fire) -----
# A background run that dies by SIGKILL leaves its pidfile; status/doctor
# prune only DEAD pids. Once the OS recycles the pid, `kill <task>` signals
# whatever session now owns it. Simulated here by recording a live,
# innocent setsid session in the pidfile — exactly the post-reuse state.
p_kill_trusts_pidfile_blindly() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  setsid sleep 300 &
  local innocent=$!
  sleep 1
  pgrep -s "$innocent" >/dev/null 2>&1 \
    || { kill "$innocent" 2>/dev/null; NOTE="HARNESS SUSPECT: no session established"; return 2; }
  echo "$innocent" > "$ROOT/coord/reports/T-innocent.pid"
  local out dead=0
  out=$(at kill T-innocent 2>&1)
  kill -0 "$innocent" 2>/dev/null || dead=1
  kill -KILL "$innocent" 2>/dev/null || true
  if [ "$dead" = 1 ]; then
    NOTE="kill terminated an innocent session that merely held the recorded pid — the pid's identity (an unio run) is never verified"
    PROMISE="PROTOCOL §4 — 'kill <task> terminate a background run'; after a SIGKILLed run + OS pid reuse this becomes friendly fire"
    return 1
  fi
  NOTE="kill verifies the pid belongs to an unio run"; return 0
}

# --- F10: run is not refused while a verify is in flight ---------------
# cmd_verify refuses to run while the worker is mid-run ('verify when it
# finishes'), but it holds no lock itself — so `run` happily starts while a
# verify is mid-Validate, and the gate's evidence is gathered against a
# worktree another agent is actively mutating.
p_run_not_refused_during_verify() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; mkdir -p tests; echo a >> tests/a.txt; git add tests/a.txt; git commit -qm "T: work"; echo done'
EOF
  sb_task T-v "- tests/" '$ sleep 5
$ test -f tests/a.txt'
  sb_task T-r "- tests/" ''
  at run mock T-v >/dev/null 2>&1    # seed committed, in-scope work
  at verify mock T-v >/dev/null 2>&1 &
  local vpid=$!
  sleep 1                            # verify is now inside '$ sleep 5'
  local out rc=0
  out=$(at run mock T-r 2>&1) || rc=$?
  wait "$vpid" 2>/dev/null || true
  if [ "$rc" -eq 0 ]; then
    NOTE="a full agent run executed while verify was mid-Validate on the same worker — the mutual exclusion is one-sided"
    PROMISE="cmd_verify's own contract — 'worker is mid-run — verify when it finishes'; I10 — a verdict must reflect a stable worktree"
    return 1
  fi
  NOTE="run refuses to start while a verify is in flight"; return 0
}

# --- F11: the gate's yardstick is writable by the gated party ---------
# verify scope-checks the diff against the task file's "- path" lines —
# but coord/ is not a git repo and nothing protects the task file, so a
# worker that commits out-of-scope work can edit its own task file to
# widen the scope retroactively. verify then launders the violation into
# a PASS, and the edit leaves no trace anywhere.
p_verify_launders_worker_scope_rewrite() {
  sb_boot; sb_repo "$SB/proj/repo"; sb_init mock || return 2
  sb_conf <<'EOF'
mock=bash -c 'set -e; echo rogue > forbidden.txt; git add forbidden.txt; git commit -qm "T: rogue"; sed -i "s/^- tests\/$/- tests\/\n- forbidden.txt/" "$TASKFILE"; echo done'
EOF
  sb_task T-launder "- tests/" '$ true'
  at run mock T-launder >/dev/null 2>&1
  local out rc=0 committed=1
  out=$(at verify mock T-launder 2>&1) || rc=$?
  git -C "$ROOT/wt/mock" ls-tree -r --name-only HEAD | grep -qx 'forbidden.txt' || committed=0
  if [ "$rc" -eq 0 ] && [ "$committed" = 1 ]; then
    NOTE="worker committed out-of-scope forbidden.txt, then appended '- forbidden.txt' to its own task file — verify PASSes the doctored scope"
    PROMISE="PROTOCOL §2 — coord/tasks write access is 'LEAD only'; GUIDEBOOK §7.4 — verdict is PASS 'only if scope is not violated': the gate's yardstick is writable by the gated party, undetectably"
    return 1
  fi
  NOTE="verify does not trust a worker-edited task file (rc=$rc)"; return 0
}

# --- R-02 / next0.5.28: unio run must never delete an existing index.lock
p_run_preserves_existing_index_lock() {
  local out rc=0
  out=$(python3 -B "$HERE/unio-index-lock.py" 2>&1) || rc=$?
  if [ "$rc" -ne 0 ]; then
    NOTE="unio run does not safely preserve existing index.lock: $out"
    PROMISE="R-02 / next0.5.28 — unio run must never delete an existing index.lock; startup must refuse nonzero before provider execution"
    return 1
  fi
  NOTE="run refuses startup when index.lock exists and preserves live writer"
  return 0
}

# =====================================================================
probe control-basic-loop                 p_control_basic_loop                 "control: ordinary run + verify works"
probe verify-validate-stdin-swallow      p_verify_validate_stdin_swallow      "a '\$ ' line reading stdin swallows the remaining Validate lines"
probe verify-scope-rename-source-blind   p_verify_scope_rename_source_blind   "rename out-of-scope -> in-scope passes the scope gate"
probe verify-passes-on-vanished-base     p_verify_passes_on_vanished_base     "dangling coord/base: committed diff invisible, verify still PASSes"
probe off-on-path-traversal              p_off_on_path_traversal              "off/on agent names escape the conf dir (write/delete anywhere)"
probe ledger-forgery-via-task-id-newline p_ledger_forgery_via_task_id_newline "newline in a task id injects forged ledger events"
probe verify-unicode-false-violation     p_verify_unicode_false_violation     "in-scope non-ASCII paths get a false scope VIOLATION"
probe guard-hooks-misfire-linked-worktree-repo p_guard_hooks_misfire_linked_worktree_repo "hooks misfire when repo/ is itself a linked worktree"
probe worker-can-rewrite-base-branch     p_worker_can_rewrite_base_branch     "git update-ref from a worktree moves the base; nothing notices"
probe kill-trusts-pidfile-blindly        p_kill_trusts_pidfile_blindly        "kill signals whatever session holds the recorded pid"
probe run-during-verify-not-refused      p_run_not_refused_during_verify      "run starts while a verify is mid-Validate on the same worker"
probe verify-launders-worker-scope-rewrite p_verify_launders_worker_scope_rewrite "worker widens its own task scope post-run; verify PASSes the doctored scope"
probe control-worker-lock                p_control_worker_lock                "control: per-worker lock refuses a concurrent run"
probe control-id-escape                  p_control_id_escape                  "control: ../-style task/worker ids are refused"
probe run-preserves-existing-index-lock   p_run_preserves_existing_index_lock   "unio run preserves live and Unknown Git index locks"

# ------------------------------------------------------------------ main
ONLY=""
case "${1:-}" in
  --list)
    for n in "${PROBE_NAMES[@]}"; do printf '%-42s %s\n' "$n" "${PROBE_ABOUT[$n]}"; done
    exit 0;;
  --only)
    ONLY="${2:-}";;
  ""|-h|--help)
    :;;
  *) echo "usage: $0 [--list] [--only <substring>]" >&2; exit 2;;
esac

echo "== unio adversarial probes (SABAT-1) =="
for n in "${PROBE_NAMES[@]}"; do
  if [ -n "$ONLY" ]; then case "$n" in *"$ONLY"*) ;; *) continue;; esac; fi
  run_probe "$n"
done
echo
echo "probes: $HELD_N HELD, $BROKEN_N BROKEN"
[ "$BROKEN_N" -eq 0 ]
