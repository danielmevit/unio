#!/usr/bin/env bash
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
#
# Opt-in task-scope preview. Embedded into unio-install.sh by
# tools/embed-task-preview.py. The Python facts helper between
# TASK_PREVIEW_PY markers is exec'd into the quality runtime and reuses
# snapshot/changed/task_mode/task_artifacts. Bash below reuses
# task_section/parse_scope_line/scope_allowed. Preview never runs
# Validate commands, never writes results/reports/ledger, and never
# claims admission, delivery or acceptance.

# Python facts module (embedded into the quality runtime; not executed here)
: <<'TASK_PREVIEW_PY'
"""Observational task-scope preview facts (docs/development/contracts/0531-TASK-PREVIEW.md).

Collect current snapshot, classified changed paths, declared outcome mode
and required-artifact names. Every Git/mode/artifact fact is established
by the existing native helpers. This module never runs Validate commands,
never writes results, reports, ledger or saves, and never claims
admission, delivery or acceptance.
"""


def facts(root, worker, task):
    ident(worker)
    ident(task)
    locations(root, worker, task)
    before = snapshot(root, worker, task)
    changed_paths = changed(root, worker, task)
    mode = None
    mode_error = None
    try:
        mode = task_mode(root, worker, task)
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as exc:
        mode_error = str(exc)
    artifacts = None
    artifacts_error = None
    try:
        artifacts = task_artifacts(root, worker, task)
    except (OSError, ValueError, UnicodeError, KeyError, TypeError) as exc:
        artifacts_error = str(exc)
    after = snapshot(root, worker, task)
    return dict(schema_version=1,
                before=before,
                after=after,
                changed=changed_paths,
                outcome_mode=('legacy' if mode is None and mode_error is None else mode),
                outcome_error=mode_error,
                required_artifacts=artifacts,
                artifacts_error=artifacts_error,
                changed_during=before != after)
TASK_PREVIEW_PY

cmd_verify_preview() {
  local worker="" task="" as_json=0 seen_preview=0 seen_json=0
  local arg
  for arg in "$@"; do
    case "$arg" in
      --preview)
        if [ "$seen_preview" = 1 ]; then
          echo 'unio preview: duplicate --preview' >&2
          return 2
        fi
        seen_preview=1;;
      --json)
        if [ "$seen_json" = 1 ]; then
          echo 'unio preview: duplicate --json' >&2
          return 2
        fi
        seen_json=1
        as_json=1;;
      --help|-h)
        echo 'usage: unio verify <worker> <task> --preview [--json]'
        echo 'Observe current implementation-task scope without running Validate'
        echo 'commands, writing results or claiming admission, delivery or acceptance.'
        return 0;;
      -*)
        echo "unio preview: unsupported argument: $arg" >&2
        return 2;;
      *)
        if [ -z "$worker" ]; then
          worker="$arg"
        elif [ -z "$task" ]; then
          task="$arg"
        else
          echo 'unio preview: unsupported extra argument' >&2
          return 2
        fi;;
    esac
  done
  [ "$seen_preview" = 1 ] || { echo 'unio preview: --preview is required' >&2; return 2; }
  [ -n "$worker" ] && [ -n "$task" ] || {
    echo 'usage: unio verify <worker> <task> --preview [--json]' >&2
    return 2
  }
  check_id "$worker" worker || return 2
  check_id "$task" task || return 2
  local root
  root=$(find_root) || { echo 'unio preview: not inside a Unio project' >&2; return 2; }
  task="${task%.md}"
  local tf="$root/coord/tasks/$task.md"
  local wt="$root/wt/$worker"
  [ -f "$tf" ] || { echo "unio preview: no task file: $tf" >&2; return 2; }
  [ -d "$wt" ] || { echo "unio preview: no worktree: $wt" >&2; return 2; }

  mkdir -p "$root/coord/.locks"
  exec 9>>"$root/coord/.locks/$worker.lock" || {
    echo "unio preview: worker lock is inaccessible" >&2
    return 2
  }
  if ! flock -n 9; then
    if [ "$as_json" = 1 ]; then
      python3 -B -c 'import json,sys; print(json.dumps({"schema_version":1,"kind":"task-preview","observation":True,"commands_executed":False,"validate_executed":False,"provider_calls":0,"admission_established":False,"delivery_established":False,"acceptance_established":False,"future_dispatch_safe":False,"worker":sys.argv[1],"task":sys.argv[2],"scope_status":"busy","reasons":["worker_busy"],"note":"preview is an observation; Validate commands were NOT run; provider calls 0; admission, delivery and acceptance are NOT established; this does not claim a future dispatch is safe"},ensure_ascii=True,sort_keys=True,indent=2))' "$worker" "$task"
    else
      echo "== preview $worker / $task =="
      echo "kind     : task-preview (observation)"
      echo "note     : preview is an observation; Validate commands were NOT run; provider calls 0; admission, delivery and acceptance are NOT established; this does not claim a future dispatch is safe"
      echo "scope_status: busy"
      echo "reasons  : worker_busy"
    fi
    echo "unio preview: worker '$worker' is busy: refuse rather than race a live Source" >&2
    return 2
  fi

  local stop_active=0
  [ -e "$root/coord/STOP" ] && stop_active=1

  local facts
  facts=$(quality task-preview-facts "$root" "$worker" "$task") || {
    echo "unio preview: unsupported or unknown Git/task state (fail closed)" >&2
    return 2
  }

  local pats=() scope_warnings=() line
  while IFS= read -r line; do
    case "$line" in '- '*)
      local raw="${line#- }"
      if parse_scope_line "$raw"; then
        [ -n "$REPLY_PATH" ] || continue
        case "$REPLY_PATH" in ..|../*|*/../*|*/..) continue;; esac
        pats+=("$REPLY_PATH")
        if [ -n "$REPLY_ANNOT" ]; then
          scope_warnings+=("stripped annotation '$REPLY_ANNOT' from scope pattern '$REPLY_PATH'")
        fi
      fi
      ;;
    esac
  done < <(task_section "$tf" "Allowed scope")

  local validate_cmds=()
  while IFS= read -r line; do
    case "$line" in '$ '*) validate_cmds+=("${line#\$ }");; esac
  done < <(task_section "$tf" "Validate")

  local tmp rc=0
  tmp=$(mktemp -d) || return 2
  printf '%s\n' "$facts" > "$tmp/facts.json"
  : > "$tmp/patterns"
  local p
  for p in "${pats[@]+"${pats[@]}"}"; do
    printf '%s\0' "$p" >> "$tmp/patterns"
  done
  : > "$tmp/warnings"
  local w
  for w in "${scope_warnings[@]+"${scope_warnings[@]}"}"; do
    printf '%s\0' "$w" >> "$tmp/warnings"
  done
  : > "$tmp/validate"
  local cmd
  for cmd in "${validate_cmds[@]+"${validate_cmds[@]}"}"; do
    printf '%s\0' "$cmd" >> "$tmp/validate"
  done

  python3 -B -c 'import json,sys
doc=json.load(open(sys.argv[1],encoding="utf-8"))
ch=doc.get("changed") or {}
seen=[]
have=set()
for key in ("committed","staged","unstaged","untracked"):
    rows=list(ch.get(key) or [])
    open(sys.argv[2]+"/"+key,"wb").write(b"".join(p.encode("utf-8")+b"\0" for p in rows))
    for p in rows:
        if p not in have:
            have.add(p)
            seen.append(p)
open(sys.argv[2]+"/all_paths","wb").write(b"".join(p.encode("utf-8")+b"\0" for p in seen))
' "$tmp/facts.json" "$tmp"
  : > "$tmp/out_of_scope"
  if [ ${#pats[@]} -gt 0 ]; then
    local path
    while IFS= read -r -d '' path; do
      [ -n "$path" ] || continue
      if ! scope_allowed "$path" "${pats[@]}"; then
        printf '%s\0' "$path" >> "$tmp/out_of_scope"
      fi
    done < "$tmp/all_paths"
  fi

  local base
  base=$(get_base "$root")
  python3 -B - "$tmp/facts.json" "$tmp/patterns" "$tmp/warnings" "$tmp/validate" \
    "$tmp/out_of_scope" "$worker" "$task" "$base" "$stop_active" "$as_json" <<'PY' || rc=$?
import json, sys

NOTE = ('preview is an observation; Validate commands were NOT run; '
        'provider calls 0; admission, delivery and acceptance are NOT '
        'established; this does not claim a future dispatch is safe')


def read_nul(path):
    data = open(path, 'rb').read().split(b'\0')
    out = []
    for item in data:
        if not item:
            continue
        out.append(item.decode('utf-8'))
    return out


facts_path, patterns_path, warnings_path, validate_path, oos_path = sys.argv[1:6]
worker, task, base_ref, stop_raw, as_json = sys.argv[6:11]
facts = json.loads(open(facts_path, encoding='utf-8').read())
patterns = read_nul(patterns_path)
warnings = read_nul(warnings_path)
validate_commands = read_nul(validate_path)
out_of_scope = read_nul(oos_path)
stop_active = stop_raw == '1'
changed = facts.get('changed') or {}
for key in ('committed', 'staged', 'unstaged', 'untracked'):
    changed.setdefault(key, [])
    if not isinstance(changed[key], list):
        changed[key] = []

reasons = []
scope_status = 'in_scope'
exit_code = 0

if facts.get('changed_during'):
    scope_status = 'changed'
    reasons.append('candidate_changed_during_observation')
    exit_code = 2
if facts.get('outcome_error'):
    scope_status = 'incomplete'
    reasons.append('malformed_outcome')
    exit_code = 2
if facts.get('artifacts_error'):
    scope_status = 'incomplete'
    reasons.append('invalid_required_artifact_syntax')
    exit_code = 2

mode = facts.get('outcome_mode') or 'legacy'
if mode == 'report-only':
    reasons.append('report_only_not_predicted')
    if scope_status != 'changed':
        scope_status = 'unsupported'
    exit_code = 2

if not patterns:
    reasons.append('missing_scope')
    if exit_code != 2 or scope_status == 'in_scope':
        scope_status = 'incomplete'
    exit_code = 2
if not validate_commands:
    reasons.append('missing_validate')
    if exit_code != 2 or scope_status == 'in_scope':
        scope_status = 'incomplete'
    exit_code = 2

if out_of_scope:
    reasons.append('scope_mismatch')
    if exit_code == 0:
        scope_status = 'mismatch'
        exit_code = 1
    elif scope_status == 'in_scope':
        scope_status = 'mismatch'

before = facts.get('before') or {}
doc = {
    'schema_version': 1,
    'kind': 'task-preview',
    'observation': True,
    'commands_executed': False,
    'validate_executed': False,
    'provider_calls': 0,
    'admission_established': False,
    'delivery_established': False,
    'acceptance_established': False,
    'future_dispatch_safe': False,
    'worker': worker,
    'task': task,
    'base_ref': base_ref,
    'base_commit': before.get('base_commit'),
    'head': before.get('candidate_commit'),
    'task_sha256': before.get('task_sha256'),
    'worktree_sha256': before.get('worktree_sha256'),
    'outcome_mode': mode,
    'stop_active': stop_active,
    'scope_status': scope_status,
    'scope_patterns': patterns,
    'scope_warnings': warnings,
    'changed': {
        'committed': list(changed['committed']),
        'staged': list(changed['staged']),
        'unstaged': list(changed['unstaged']),
        'untracked': list(changed['untracked']),
    },
    'out_of_scope': out_of_scope,
    'validate_commands': validate_commands,
    'required_artifacts': facts.get('required_artifacts'),
    'reasons': reasons,
    'note': NOTE,
}
if as_json == '1':
    print(json.dumps(doc, ensure_ascii=True, sort_keys=True, indent=2))
else:
    print('== preview %s / %s ==' % (worker, task))
    print('kind     : task-preview (observation)')
    print('note     : %s' % NOTE)
    print('base     : %s @ %s' % (base_ref, doc['base_commit'] or 'Unknown'))
    print('HEAD     : %s' % (doc['head'] or 'Unknown'))
    print('task     : sha256=%s' % (doc['task_sha256'] or 'Unknown'))
    print('mode     : %s' % mode)
    print('stop     : %s' % ('active (preview remains read-only)' if stop_active else 'clear'))
    print('scope_status: %s' % scope_status)
    if patterns:
        print('scope    : %d pattern(s)' % len(patterns))
        for item in patterns:
            print('  - %s' % item)
    else:
        print('scope    : missing — no \'- path\' lines under \'## Allowed scope\'')
    for warning in warnings:
        print('warning  : %s' % warning)
    print('changed  :')
    for key in ('committed', 'staged', 'unstaged', 'untracked'):
        rows = changed[key]
        print('  %s: %s' % (key, ', '.join(rows) if rows else '(none)'))
    if out_of_scope:
        print('out-of-scope:')
        for item in out_of_scope:
            print('  %s' % item)
    else:
        print('out-of-scope: (none)')
    print('validate : declared, NOT run')
    if validate_commands:
        for item in validate_commands:
            print('  $ %s' % item)
    else:
        print('  (none — no \'$ \' command lines under \'## Validate\')')
    artifacts = doc['required_artifacts']
    if artifacts is None and not facts.get('artifacts_error'):
        print('artifacts: (none declared)')
    elif facts.get('artifacts_error'):
        print('artifacts: invalid syntax — %s' % facts['artifacts_error'])
    else:
        print('artifacts: %s' % ', '.join(artifacts))
    print('provider_calls: 0')
    print('admission/delivery/acceptance: NOT established')
    if reasons:
        print('reasons  : %s' % ','.join(reasons))
    if mode == 'report-only':
        print('report-only: unsupported/not-predicted in this first slice')

sys.exit(exit_code)
PY
  rm -rf -- "$tmp"
  return "$rc"
}
