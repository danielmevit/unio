#!/usr/bin/env bash
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
# Unio rename contract: entirely isolated, no providers or credentials.
set -euo pipefail
REPO_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
EXPECTED_VERSION=$(sed -n 's/^UNIO_VERSION="\([^"]*\)"$/\1/p' "$REPO_DIR/unio-install.sh")
[ -n "$EXPECTED_VERSION" ] || { echo 'FAIL: missing declared release version' >&2; exit 1; }
BRAND_SANDBOX=$(mktemp -d)
trap 'rm -rf "$BRAND_SANDBOX"' EXIT
fail() { echo "FAIL: $*" >&2; exit 1; }

export UNIO_BIN_DIR="$BRAND_SANDBOX/bin with spaces"
export UNIO_CONF_DIR="$BRAND_SANDBOX/conf with spaces"
export UNIO_COMPLETION_DIR="$BRAND_SANDBOX/completion with spaces"
FLOCK_PATH=$(command -v flock)
FLOCK_HASH=$(sha256sum "$FLOCK_PATH")
FLOCK_INODE=$(stat -Lc '%d:%i' "$FLOCK_PATH")
legacy_commands=(frugal-flock frgl-flc agentteam)
legacy_link_target=agentteam
legacy_version_marker='AGENTTEAM_VERSION='
legacy_conf_name=agentteam
legacy_worker_marker='.agentteam-worker'
legacy_guard='agentteam guard'
legacy_bin_override=AGENTTEAM_BIN_DIR
legacy_conf_override=AGENTTEAM_CONF_DIR
legacy_completion_override=AGENTTEAM_COMPLETION_DIR

install() {
  (cd "$BRAND_SANDBOX" && bash "$REPO_DIR/unio-install.sh") > "$BRAND_SANDBOX/install.log"
  grep -Fq 'Unio installed. Your AIs, in sync.' "$BRAND_SANDBOX/install.log"
}
only_unio() {
  local dir entry
  for dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
    local entries=("$dir"/*)
    [ "${#entries[@]}" -eq 1 ] && [ "${entries[0]}" = "$dir/unio" ] \
      || fail "install contains entries other than unio: $dir"
    [ -f "$dir/unio" ] && [ ! -L "$dir/unio" ] || fail "unio must be a regular file: $dir"
    for entry in "${legacy_commands[@]}"; do
      [ ! -e "$dir/$entry" ] && [ ! -L "$dir/$entry" ] || fail "legacy command remains: $dir/$entry"
    done
  done
  [ -x "$UNIO_BIN_DIR/unio" ] || fail 'unio is not executable'
}

# A standalone installer carries byte-identical legal files and lead guides.
mkdir -p "$BRAND_SANDBOX/standalone"
cp "$REPO_DIR/unio-install.sh" "$BRAND_SANDBOX/standalone/unio-install.sh"
bash "$BRAND_SANDBOX/standalone/unio-install.sh" > "$BRAND_SANDBOX/install.log"
only_unio
cmp "$REPO_DIR/LICENSE" "$UNIO_CONF_DIR/legal/LICENSE"
cmp "$REPO_DIR/NOTICE" "$UNIO_CONF_DIR/legal/NOTICE"
cmp "$REPO_DIR/docs/PROTOCOL.md" "$UNIO_CONF_DIR/templates/PROTOCOL.md"
cmp "$REPO_DIR/docs/ai/LEAD-ESCALATION.md" "$UNIO_CONF_DIR/templates/LEAD-ESCALATION.md"
cmp "$REPO_DIR/docs/development/MODEL-SCOREBOARD.md" "$UNIO_CONF_DIR/templates/MODEL-SCOREBOARD.md"

# Reinstalling preserves user configuration, bench state and playbooks.
printf '# existing user config\nmock=bash -c "exit 0"\n' > "$UNIO_CONF_DIR/agents.conf"
cp "$UNIO_CONF_DIR/agents.conf" "$BRAND_SANDBOX/expected.conf"
mkdir -p "$UNIO_CONF_DIR/off" "$UNIO_CONF_DIR/playbooks"
printf 'keep quota state\n' > "$UNIO_CONF_DIR/off/existing"
printf 'keep playbooks\n' > "$UNIO_CONF_DIR/playbooks/existing.md"
install
cmp "$BRAND_SANDBOX/expected.conf" "$UNIO_CONF_DIR/agents.conf"
grep -Fxq 'keep quota state' "$UNIO_CONF_DIR/off/existing"
grep -Fxq 'keep playbooks' "$UNIO_CONF_DIR/playbooks/existing.md"

# Every legacy name in both directories is removed only by the frozen rules.
# Test 1: all regular files with marker
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  for legacy_command in "${legacy_commands[@]}"; do
    printf '#!/bin/bash\n%s"0.4.0"\n' "$legacy_version_marker" > "$legacy_dir/$legacy_command"
  done
done
install
only_unio
[ "$(grep -c '^Removed legacy install: ' "$BRAND_SANDBOX/install.log")" -eq 6 ] \
  || fail 'not every legacy removal was reported (regular files)'

# Test 2: aliases to an owned target
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  printf '#!/bin/bash\n%s"0.4.0"\n' "$legacy_version_marker" > "$legacy_dir/$legacy_link_target"
  for legacy_command in "${legacy_commands[@]:0:2}"; do
    ln -s "$legacy_link_target" "$legacy_dir/$legacy_command"
  done
done
install
only_unio
[ "$(grep -c '^Removed legacy install: ' "$BRAND_SANDBOX/install.log")" -eq 6 ] \
  || fail 'not every legacy removal was reported (owned links)'

# Actual v0.4.0 completion fixture cleanup.
fixture="$REPO_DIR/tests/fixtures/legacy-v0.4.0-completion"
[ -f "$fixture" ] || fail "Missing fixture"
[ "$(wc -c < "$fixture")" -eq 2326 ] || fail "Fixture length mismatch"
[ "$(sha256sum "$fixture" | cut -d' ' -f1)" = "c8d65ea3f3b696760ebdfe7e03f7f8fee646f9f99b85abee8e38197569cb7c29" ] || fail "Fixture SHA256 mismatch"

cp "$fixture" "$UNIO_COMPLETION_DIR/$legacy_link_target"
for legacy_command in "${legacy_commands[@]:0:2}"; do
  ln -s "$legacy_link_target" "$UNIO_COMPLETION_DIR/$legacy_command"
done
install
only_unio
[ "$(grep -c '^Removed legacy install: ' "$BRAND_SANDBOX/install.log")" -eq 3 ] \
  || fail 'fixture cleanup failed'

# Modified completion is preserved.
cp "$fixture" "$UNIO_COMPLETION_DIR/$legacy_link_target"
echo "# modified" >> "$UNIO_COMPLETION_DIR/$legacy_link_target"
for legacy_command in "${legacy_commands[@]:0:2}"; do
  ln -s "$legacy_link_target" "$UNIO_COMPLETION_DIR/$legacy_command"
done
install
[ -f "$UNIO_COMPLETION_DIR/$legacy_link_target" ] || fail 'modified completion was removed'
for legacy_command in "${legacy_commands[@]:0:2}"; do
  [ -L "$UNIO_COMPLETION_DIR/$legacy_command" ] || fail 'modified completion alias was removed'
done
! grep -q '^Removed legacy install: ' "$BRAND_SANDBOX/install.log"
for legacy_command in "${legacy_commands[@]}"; do
  rm -- "$UNIO_COMPLETION_DIR/$legacy_command"
done

# Test foreign alias preservation in both dirs.
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  printf '#!/bin/sh\necho unrelated tool\n' > "$legacy_dir/$legacy_link_target"
  chmod +x "$legacy_dir/$legacy_link_target"
  cp "$legacy_dir/$legacy_link_target" "$BRAND_SANDBOX/unrelated-tool"
  for legacy_command in "${legacy_commands[@]:0:2}"; do
    ln -s "$legacy_link_target" "$legacy_dir/$legacy_command"
  done
done
install
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  cmp "$BRAND_SANDBOX/unrelated-tool" "$legacy_dir/$legacy_link_target"
  [ -x "$legacy_dir/$legacy_link_target" ] || fail 'unrelated executable lost its mode'
  for legacy_command in "${legacy_commands[@]:0:2}"; do
    [ -L "$legacy_dir/$legacy_command" ] || fail 'foreign alias was removed'
  done
done
! grep -q '^Removed legacy install: ' "$BRAND_SANDBOX/install.log"
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  for legacy_command in "${legacy_commands[@]}"; do
    rm -- "$legacy_dir/$legacy_command"
  done
done

# Files, directories and differently targeted symlinks are never ours.
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  for legacy_command in "${legacy_commands[@]}"; do
    printf 'unrelated %s\n' "$legacy_command" > "$legacy_dir/$legacy_command"
  done
done
install
! grep -q '^Removed legacy install: ' "$BRAND_SANDBOX/install.log"
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  for legacy_command in "${legacy_commands[@]}"; do
    grep -Fxq "unrelated $legacy_command" "$legacy_dir/$legacy_command"
    rm -- "$legacy_dir/$legacy_command"
    mkdir "$legacy_dir/$legacy_command"
  done
done
install
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  for legacy_command in "${legacy_commands[@]}"; do
    [ -d "$legacy_dir/$legacy_command" ] || fail 'unrelated directory removed'
    rmdir "$legacy_dir/$legacy_command"
    # Even a link to an owned regular file must survive a different target.
    printf '%s"0.4.0"\n' "$legacy_version_marker" > "$BRAND_SANDBOX/owned-target"
    ln -s "$BRAND_SANDBOX/owned-target" "$legacy_dir/$legacy_command"
  done
done
install
for legacy_dir in "$UNIO_BIN_DIR" "$UNIO_COMPLETION_DIR"; do
  for legacy_command in "${legacy_commands[@]}"; do
    [ -L "$legacy_dir/$legacy_command" ] || fail 'unrelated symlink removed'
    [ "$(readlink "$legacy_dir/$legacy_command")" = "$BRAND_SANDBOX/owned-target" ]
    rm -- "$legacy_dir/$legacy_command"
  done
done
only_unio

cat "$REPO_DIR/NOTICE" "$REPO_DIR/LICENSE" > "$BRAND_SANDBOX/expected-license"
export PATH="$UNIO_BIN_DIR:$PATH"
unio help > "$BRAND_SANDBOX/help"
grep -Fq 'Unio — Your AIs, in sync.' "$BRAND_SANDBOX/help"
for phrase in 'unio result <w> <task>' 'unio handoff <w> <task>' \
    'unio agents [--json]' '2 INCOMPLETE' 'VERDICT: REQUEST-CHANGES' \
    'NOT a backup' 'Python 3 (standard library only)' 'trusted_host' 'skip-worktree' \
    'unio license' 'Daniel Mitev' 'Daniel Mevit (@danielmevit)' 'No warranty.'; do
  grep -Fq -- "$phrase" "$BRAND_SANDBOX/help" || fail "help no longer mentions: $phrase"
done
unio license > "$BRAND_SANDBOX/entry-license"
cmp "$BRAND_SANDBOX/expected-license" "$BRAND_SANDBOX/entry-license"
unio version > "$BRAND_SANDBOX/version"
IFS= read -r branded_version < "$BRAND_SANDBOX/version"
[[ "$branded_version" == "Unio $EXPECTED_VERSION ("* ]] || fail 'installed version differs from release declaration'
grep -Fxq 'Your AIs, in sync.' "$BRAND_SANDBOX/version"
grep -Fxq "config: $UNIO_CONF_DIR/agents.conf" "$BRAND_SANDBOX/version"
rc=0
unio invalid-branding-command > "$BRAND_SANDBOX/error" 2>&1 || rc=$?
[ "$rc" -eq 1 ] || fail "invalid-command status changed ($rc)"
grep -Fq "unknown command 'invalid-branding-command'" "$BRAND_SANDBOX/error"
unio off mock >/dev/null
[ -f "$UNIO_CONF_DIR/off/mock" ] || fail 'config override ignored'
unio on mock >/dev/null
[ ! -f "$UNIO_CONF_DIR/off/mock" ] || fail 'on did not clear bench state'

# Completion registers only Unio and offers real worker/task names.
mkdir -p "$BRAND_SANDBOX/project/wt/w1" "$BRAND_SANDBOX/project/coord/tasks"
: > "$BRAND_SANDBOX/project/coord/tasks/T1.md"
: > "$BRAND_SANDBOX/project/coord/tasks/TEMPLATE.md"
entry=unio
  bash -euo pipefail -s -- "$entry" "$BRAND_SANDBOX/project" <<'COMPLETION_TEST'
entry=$1
source "$UNIO_COMPLETION_DIR/$entry"
registration=$(complete -p "$entry")
[ "$registration" = "complete -F _unio unio" ]
function_name=${registration#* -F }
function_name=${function_name%% *}
declare -F "$function_name" >/dev/null
COMP_WORDS=("$entry" '') COMP_CWORD=1
"$function_name"
[ "${#COMPREPLY[@]}" -gt 20 ]
for candidate in "${COMPREPLY[@]}"; do
  # Each offered command must occur in the installed dispatch table.
  grep -Eq "^  ([a-z-]+\|)*${candidate}(\)|\|)" "$UNIO_BIN_DIR/unio"
done
COMP_WORDS=("$entry" ver) COMP_CWORD=1
"$function_name"
[ "${COMPREPLY[*]}" = 'verify version' ]
COMP_WORDS=("$entry" resul) COMP_CWORD=1
"$function_name"
[ "${COMPREPLY[*]}" = 'result' ]
COMP_WORDS=("$entry" hand) COMP_CWORD=1
"$function_name"
[ "${COMPREPLY[*]}" = 'handoff' ]
COMP_WORDS=("$entry" agents '') COMP_CWORD=2
"$function_name"
[ "${COMPREPLY[*]}" = '--json' ]
cd "$2"
for command in verify result handoff review; do
  COMPREPLY=(); COMP_WORDS=("$entry" "$command" '') COMP_CWORD=2
  "$function_name"
  [ "${COMPREPLY[*]}" = 'w1' ]
  COMPREPLY=(); COMP_WORDS=("$entry" "$command" w1 '') COMP_CWORD=3
  "$function_name"
  [ "${COMPREPLY[*]}" = 'T1' ]
done
# Only review takes a third argument (the reviewer agent).
for command in verify result handoff; do
  COMPREPLY=(); COMP_WORDS=("$entry" "$command" w1 T1 '') COMP_CWORD=4
  "$function_name"
  [ "${#COMPREPLY[@]}" -eq 0 ]
done
COMPREPLY=(); COMP_WORDS=("$entry" review w1 T1 '') COMP_CWORD=4
"$function_name"
[ "${COMPREPLY[*]}" = 'mock' ]
COMPLETION_TEST

# Legacy environment names are ignored by the installer and runtime.
OVERRIDE_HOME="$BRAND_SANDBOX/override home"
env -u UNIO_BIN_DIR -u UNIO_CONF_DIR -u UNIO_COMPLETION_DIR HOME="$OVERRIDE_HOME" \
  "$legacy_bin_override=$BRAND_SANDBOX/ignored bin" \
  "$legacy_conf_override=$BRAND_SANDBOX/ignored config" \
  "$legacy_completion_override=$BRAND_SANDBOX/ignored completion" \
  bash "$REPO_DIR/unio-install.sh" > "$BRAND_SANDBOX/override.log"
[ -x "$OVERRIDE_HOME/.local/bin/unio" ]
[ -f "$OVERRIDE_HOME/.local/share/bash-completion/completions/unio" ]
[ -f "$OVERRIDE_HOME/.config/unio/agents.conf" ]
[ ! -e "$BRAND_SANDBOX/ignored bin" ]
[ ! -e "$BRAND_SANDBOX/ignored config" ]
[ ! -e "$BRAND_SANDBOX/ignored completion" ]
env -u UNIO_CONF_DIR HOME="$OVERRIDE_HOME" \
  "$legacy_conf_override=$BRAND_SANDBOX/ignored config" \
  "$UNIO_BIN_DIR/unio" version > "$BRAND_SANDBOX/override-version"
grep -Fxq "config: $OVERRIDE_HOME/.config/unio/agents.conf" "$BRAND_SANDBOX/override-version"

# Copy legacy default config once, preserving its files and the original.
MIGRATION_HOME="$BRAND_SANDBOX/migration home"
legacy_config="$MIGRATION_HOME/.config/$legacy_conf_name"
mkdir -p "$legacy_config/off" "$legacy_config/playbooks"
printf 'mock=bash -c "exit 0"\n' > "$legacy_config/agents.conf"
printf 'original bench state\n' > "$legacy_config/off/mock"
printf 'private playbook\n' > "$legacy_config/playbooks/custom.md"
ln -s custom.md "$legacy_config/playbooks/link.md"
cp -a "$legacy_config" "$BRAND_SANDBOX/expected-legacy"
migrate_install() {
  env -u UNIO_CONF_DIR HOME="$MIGRATION_HOME" bash "$REPO_DIR/unio-install.sh" > "$BRAND_SANDBOX/migration.log"
}
migrate_install
[ "$(grep -c '^Copied legacy config ' "$BRAND_SANDBOX/migration.log")" -eq 1 ]
for item in agents.conf off/mock playbooks/custom.md; do
  cmp "$legacy_config/$item" "$MIGRATION_HOME/.config/unio/$item"
done
[ -L "$MIGRATION_HOME/.config/unio/playbooks/link.md" ]
[ "$(readlink "$MIGRATION_HOME/.config/unio/playbooks/link.md")" = custom.md ]
diff -r "$BRAND_SANDBOX/expected-legacy" "$legacy_config"
printf 'new config must stay\n' > "$MIGRATION_HOME/.config/unio/agents.conf"
printf 'old config changed\n' > "$legacy_config/agents.conf"
migrate_install
! grep -q '^Copied legacy config ' "$BRAND_SANDBOX/migration.log"
grep -Fxq 'new config must stay' "$MIGRATION_HOME/.config/unio/agents.conf"
grep -Fxq 'old config changed' "$legacy_config/agents.conf"
cmp "$REPO_DIR/NOTICE" "$MIGRATION_HOME/.config/unio/legal/NOTICE"
# Explicit config selection must suppress the default migration.
rm -rf "$MIGRATION_HOME/.config/unio"
HOME="$MIGRATION_HOME" UNIO_CONF_DIR="$BRAND_SANDBOX/explicit config" \
  bash "$REPO_DIR/unio-install.sh" > "$BRAND_SANDBOX/migration.log"
[ ! -e "$MIGRATION_HOME/.config/unio" ]
! grep -q '^Copied legacy config ' "$BRAND_SANDBOX/migration.log"

# A symlinked legacy directory must become a real, independent config tree.
MIGRATION_HOME="$BRAND_SANDBOX/symlink migration home"
legacy_config="$MIGRATION_HOME/.config/$legacy_conf_name"
legacy_target="$BRAND_SANDBOX/legacy config target"
new_config="$MIGRATION_HOME/.config/unio"
mkdir -p "$MIGRATION_HOME/.config" "$legacy_target/templates" \
  "$legacy_target/legal" "$legacy_target/playbooks" "$legacy_target/off"
printf 'mock=bash -c "exit 0"\n' > "$legacy_target/agents.conf"
printf 'legacy task template\n' > "$legacy_target/templates/TASK.md"
printf 'legacy protocol template\n' > "$legacy_target/templates/PROTOCOL.md"
printf 'legacy notice\n' > "$legacy_target/legal/NOTICE"
printf 'private linked playbook\n' > "$legacy_target/playbooks/custom.md"
printf 'legacy bench state\n' > "$legacy_target/off/mock"
ln -s custom.md "$legacy_target/playbooks/link.md"
ln -s "$legacy_target" "$legacy_config"
cp -a -- "$legacy_target" "$BRAND_SANDBOX/expected-symlink-target"
legacy_link_inode=$(stat -c '%d:%i' "$legacy_config")
check_legacy_symlink() {
  [ -L "$legacy_config" ] || fail 'legacy config link was replaced'
  [ "$(readlink -- "$legacy_config")" = "$legacy_target" ] || fail 'legacy config link changed'
  [ "$(stat -c '%d:%i' "$legacy_config")" = "$legacy_link_inode" ] || fail 'legacy config link was recreated'
  [ -L "$legacy_target/playbooks/link.md" ]
  [ "$(readlink -- "$legacy_target/playbooks/link.md")" = custom.md ]
  diff -r -- "$BRAND_SANDBOX/expected-symlink-target" "$legacy_target" \
    || fail 'legacy config, templates or symlink target changed'
}
migrate_install
[ "$(grep -c '^Copied legacy config ' "$BRAND_SANDBOX/migration.log")" -eq 1 ]
[ -d "$new_config" ] && [ ! -L "$new_config" ] || fail 'migrated config must be a real directory'
[ "$(stat -Lc '%d:%i' "$new_config")" != "$(stat -Lc '%d:%i' "$legacy_config")" ] \
  || fail 'migrated config aliases the legacy target'
for item in agents.conf off/mock playbooks/custom.md; do
  cmp "$legacy_target/$item" "$new_config/$item"
done
[ -L "$new_config/playbooks/link.md" ]
[ "$(readlink -- "$new_config/playbooks/link.md")" = custom.md ]
[ "$(readlink -f -- "$new_config/playbooks/link.md")" = "$new_config/playbooks/custom.md" ]
cmp "$REPO_DIR/docs/PROTOCOL.md" "$new_config/templates/PROTOCOL.md"
cmp "$REPO_DIR/NOTICE" "$new_config/legal/NOTICE"
check_legacy_symlink
printf 'new config must stay\n' > "$new_config/agents.conf"
printf 'new private playbook\n' > "$new_config/playbooks/link.md"
check_legacy_symlink
migrate_install
! grep -q '^Copied legacy config ' "$BRAND_SANDBOX/migration.log"
grep -Fxq 'new config must stay' "$new_config/agents.conf"
grep -Fxq 'new private playbook' "$new_config/playbooks/custom.md"
check_legacy_symlink
rm -rf -- "$new_config"
HOME="$MIGRATION_HOME" UNIO_CONF_DIR="$BRAND_SANDBOX/explicit symlink config" \
  bash "$REPO_DIR/unio-install.sh" > "$BRAND_SANDBOX/migration.log"
[ ! -e "$new_config" ] && [ ! -L "$new_config" ]
! grep -q '^Copied legacy config ' "$BRAND_SANDBOX/migration.log"
check_legacy_symlink

# Init converts all existing workers, including ones absent from its arguments.
PROJECT="$BRAND_SANDBOX/doctor"
PROJECT_REPO="$PROJECT/custom checkout"
git init -q -b dev "$PROJECT_REPO"
git -C "$PROJECT_REPO" -c user.email=brand@test.invalid -c user.name=brand \
  commit -q --allow-empty -m init
(cd "$PROJECT_REPO" && unio init mock mock-other) > "$BRAND_SANDBOX/doctor-init" 2>&1
make_legacy_project() {
  local wt hook
  for wt in "$PROJECT"/wt/*/; do
    mv "$wt/.unio-worker" "$wt/$legacy_worker_marker"
  done
  for hook in pre-commit pre-push reference-transaction post-merge; do
    sed "s/unio guard/$legacy_guard/g; s/\\.unio-worker/$legacy_worker_marker/g" \
      "$PROJECT_REPO/.git/hooks/$hook" > "$BRAND_SANDBOX/legacy-hook"
    cat "$BRAND_SANDBOX/legacy-hook" > "$PROJECT_REPO/.git/hooks/$hook"
  done
  sed -i '/^\.unio-worker$/d' "$PROJECT_REPO/.git/info/exclude"
  printf '%s\n' "$legacy_worker_marker" >> "$PROJECT_REPO/.git/info/exclude"
}
check_project_conversion() {
  local wt hook
  for wt in "$PROJECT"/wt/*/; do
    [ ! -e "$wt/$legacy_worker_marker" ] || fail 'legacy worker marker remains'
    [ -f "$wt/.unio-worker" ] || fail 'Unio worker marker missing'
    grep -Fxq "$(basename "$wt")" "$wt/.unio-worker"
    git -C "$wt" check-ignore -q .unio-worker
  done
  grep -Fxq '.unio-worker' "$PROJECT_REPO/.git/info/exclude"
  for hook in pre-commit pre-push reference-transaction post-merge; do
    grep -Fq 'unio guard' "$PROJECT_REPO/.git/hooks/$hook"
    ! grep -Fq "$legacy_guard" "$PROJECT_REPO/.git/hooks/$hook"
    [ -x "$PROJECT_REPO/.git/hooks/$hook" ]
  done
  # The rewritten no-push guard still blocks a worker.
  rc=0
  (cd "$PROJECT/wt/mock" && bash "$PROJECT_REPO/.git/hooks/pre-push") \
    > "$BRAND_SANDBOX/guard-out" 2>&1 || rc=$?
  [ "$rc" -eq 1 ]
  grep -Fq 'unio guard' "$BRAND_SANDBOX/guard-out"
}
make_legacy_project
(cd "$PROJECT_REPO" && unio init mock) > "$BRAND_SANDBOX/doctor-init" 2>&1
check_project_conversion
make_legacy_project
(cd "$PROJECT_REPO" && unio doctor) > "$BRAND_SANDBOX/doctor-out" 2>&1 \
  || fail "doctor reported errors: $(cat "$BRAND_SANDBOX/doctor-out")"
check_project_conversion
grep -Fq 'ok    python3 found' "$BRAND_SANDBOX/doctor-out" || fail 'doctor no longer checks python3'
# Both migration entrypoints must leave unrelated hooks untouched.
printf '#!/bin/sh\n# custom owner hook\nexit 0\n' > "$PROJECT_REPO/.git/hooks/pre-commit"
cp "$PROJECT_REPO/.git/hooks/pre-commit" "$BRAND_SANDBOX/owner-hook"
(cd "$PROJECT_REPO" && unio init mock) > "$BRAND_SANDBOX/doctor-init" 2>&1
cmp "$BRAND_SANDBOX/owner-hook" "$PROJECT_REPO/.git/hooks/pre-commit"
# Trigger doctor migration through another owned hook.
sed -i "s/unio guard/$legacy_guard/g" "$PROJECT_REPO/.git/hooks/pre-push"
(cd "$PROJECT_REPO" && unio doctor) > "$BRAND_SANDBOX/doctor-out" 2>&1
cmp "$BRAND_SANDBOX/owner-hook" "$PROJECT_REPO/.git/hooks/pre-commit"
grep -Fq 'unio guard' "$PROJECT_REPO/.git/hooks/pre-push"

# Run real background sessions with a local holding mock from custom paths.
python3 -B - "$REPO_DIR" "$BRAND_SANDBOX" <<'KILL_TEST'
import os
import json
import stat
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

source, sandbox = map(Path, sys.argv[1:])

def wait_for(condition, label):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(.05)
    raise AssertionError(label)

def live(pid):
    try:
        stat = Path(f'/proc/{pid}/stat').read_text()
        return stat.rpartition(')')[2].split()[0] != 'Z'
    except FileNotFoundError:
        return False

for index, dirname in enumerate(('custom-commands', 'custom commands with spaces')):
    base = sandbox / f'kill-case-{index}'
    bin_dir = base / dirname
    command = bin_dir / 'unio'
    root = base / 'project'
    repo = root / 'repo'
    repo.mkdir(parents=True)
    env = dict(os.environ, UNIO_BIN_DIR=str(bin_dir), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_TIMEOUT='60',
               UNIO_AUTO_VERIFY='0', UNIO_AUTO_SYNC='0', UNIO_AUTO_OFF='0',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock',
               GIT_AUTHOR_EMAIL='mock@example.invalid', GIT_COMMITTER_EMAIL='mock@example.invalid')
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env,
                   check=True, capture_output=True, timeout=20)
    subprocess.run(['git', 'init', '-q', '-b', 'dev'], cwd=repo, env=env, check=True)
    subprocess.run(['git', 'commit', '-q', '--allow-empty', '-m', 'init'],
                   cwd=repo, env=env, check=True)

    def call(*args, code=0):
        result = subprocess.run([str(command), *args], cwd=repo, env=env,
                                capture_output=True, text=True, timeout=20)
        assert result.returncode == code, (args, result.returncode, result.stdout, result.stderr)
        return result

    call('init', 'mock')
    mock = base / 'hold.py'
    marker = base / 'mock.pid'
    mock.write_text("import os,time\nfrom pathlib import Path\n"
                    "Path(__file__).with_name('mock.pid').write_text(str(os.getpid()))\n"
                    "while True: time.sleep(.05)\n")
    (base / 'conf/agents.conf').write_text('mock=python3 ' + shlex.quote(str(mock)) + '\n')
    task = 'custom-kill'
    (root / 'coord/tasks' / f'{task}.md').write_text(
        f'# {task}\n## Allowed scope\n- payload.txt\n## Validate\n$ true\n')
    pidfile = root / 'coord/reports' / f'{task}.pid'
    ownerfile = root / 'coord/reports/.owners/mock' / f'{task}.own'
    provider = None
    def identity(pid):
        fields = Path(f'/proc/{pid}/stat').read_text().rpartition(')')[2].split()
        return int(fields[3]), int(fields[19])
    leader = None
    try:
        call('run', '-b', 'mock', task)
        wait_for(lambda: pidfile.exists() and bool(pidfile.read_text().strip()),
                 'background run did not record its pid')
        leader = int(pidfile.read_text())
        wait_for(lambda: marker.exists() and bool(marker.read_text().strip()),
                 'local holding mock did not start')
        mock_pid = int(marker.read_text())
        assert live(leader) and live(mock_pid), 'background run was not live'
        record = json.loads(ownerfile.read_text())
        assert ownerfile.stat().st_uid == os.getuid() and not stat.S_IMODE(ownerfile.stat().st_mode) & 0o077
        assert record['worker'] == 'mock' and record['task'] == task
        assert record['boot_id'] == Path('/proc/sys/kernel/random/boot_id').read_text().strip()
        assert record['shell_pid'] == leader and record['shell_sid'] == leader
        assert identity(leader) == (record['shell_sid'], record['shell_start'])
        provider_pid = record['provider_pid']
        assert provider_pid == record['provider_sid'] != leader, 'provider session was not isolated'
        assert identity(provider_pid) == (record['provider_sid'], record['provider_start'])
        provider = (provider_pid, record['provider_start'])
        assert os.getsid(mock_pid) == record['provider_sid'], 'mock escaped the owned provider session'
        argv = Path(f'/proc/{leader}/cmdline').read_bytes().split(b'\0')
        assert argv[1:3] == [os.fsencode(command), b'run'], argv
        result = call('kill', task)
        assert f"killed '{task}' (session {leader})" in result.stdout, result.stdout
        assert not pidfile.exists(), 'killed run retained its pidfile'
        wait_for(lambda: not live(leader) and not live(mock_pid), 'kill left the run or mock alive')
        result_path = root / 'coord/results/mock' / f'{task}.json'
        wait_for(result_path.exists, 'kill did not preserve Source result')
        result_doc = json.loads(result_path.read_text())
        assert result_doc['process']['state'] == 'failed' and result_doc['process']['exit_code'] == 143, result_doc['process']
    finally:
        # Only the fixture's proven private provider identity may be cleaned.
        if provider is not None and live(provider[0]) and identity(provider[0]) == provider:
            subprocess.run(['pkill', '-KILL', '-s', str(provider[0])], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if leader is None and pidfile.exists() and pidfile.read_text().strip():
            leader = int(pidfile.read_text())
        if leader is not None and live(leader) and os.getsid(leader) == leader:
            subprocess.run(['pkill', '-KILL', '-s', str(leader)], check=False,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # Neither command text nor a later argv pair is the executed Unio script.
    decoy = str(base / 'bin/unio')
    for label, argv in (
        ('unrelated', ['sleep', '60']),
        ('command-text', ['bash', '-c', 'sleep 60 & wait', decoy + ' run']),
        ('later-arguments', ['bash', '-c', 'sleep 60 & wait', decoy, 'run']),
    ):
        innocent = subprocess.Popen(argv, start_new_session=True, env=env,
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        stale = root / 'coord/reports' / f'{label}.pid'
        try:
            assert os.getsid(innocent.pid) == innocent.pid, 'unrelated session did not start'
            stale.write_text(str(innocent.pid) + '\n')
            result = call('kill', label, code=1)
            assert 'not a Unio run' in result.stderr and 'refusing to signal it' in result.stderr
            assert innocent.poll() is None and live(innocent.pid), 'kill signalled an unrelated session'
            assert not stale.exists(), 'unrelated stale pidfile was not removed'
        finally:
            if innocent.poll() is None:
                os.killpg(innocent.pid, signal.SIGKILL)
            innocent.wait(timeout=5)
    print(f'  kill: {dirname}: live run terminated; unrelated and decoy sessions preserved')
KILL_TEST

[ ! -e "$UNIO_BIN_DIR/flock" ] && [ ! -L "$UNIO_BIN_DIR/flock" ]
[ "$(command -v flock)" = "$FLOCK_PATH" ] || fail 'Linux flock was shadowed'
[ "$(sha256sum "$FLOCK_PATH")" = "$FLOCK_HASH" ] || fail 'Linux flock was modified'
[ "$(stat -Lc '%d:%i' "$FLOCK_PATH")" = "$FLOCK_INODE" ] || fail 'Linux flock was replaced'
flock -n "$BRAND_SANDBOX/lock" true

# Installation failures propagate from the one installer.
: > "$BRAND_SANDBOX/not-a-directory"
rc=0
UNIO_BIN_DIR="$BRAND_SANDBOX/not-a-directory/bin" \
  bash "$REPO_DIR/unio-install.sh" > "$BRAND_SANDBOX/install-error" 2>&1 || rc=$?
[ "$rc" -eq 1 ] || fail "installation failure status changed ($rc)"
echo 'PASS: Unio command, completion, legal copies, legacy cleanup, independent config migration, project migration, custom-path kill safety, reinstall, status propagation and Linux flock'
