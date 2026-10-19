#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the optional subscription adapters as byte-identical shell heredocs.

The canonical adapters install under $CONF_DIR/lib/adapters, separately
from the browser/capacity/dashboard payloads. The installer copies the
exact reviewed bytes: it installs no external dependency and invokes no
model, provider or interpreter for them.
"""
from pathlib import Path
import base64
import json
import textwrap
import zlib
import sys

ROOT = Path(__file__).resolve().parent.parent
ADAPTERS = (
    (ROOT / 'tools' / 'adapter-contract.py', 'UNIO_ADAPTER_CONTRACT_PY', 'adapter-contract.py'),
    (ROOT / 'tools' / 'adapter-outcome.py', 'UNIO_ADAPTER_OUTCOME_PY', 'adapter-outcome.py'),
    (ROOT / 'tools' / 'adapter-budget.py', 'UNIO_ADAPTER_BUDGET_PY', 'adapter-budget.py'),
    (ROOT / 'tools' / 'vibe-worker.py', 'UNIO_VIBE_WORKER_PY', 'vibe-worker.py'),
    (ROOT / 'tools' / 'perplexity-worker.py', 'UNIO_PERPLEXITY_WORKER_PY', 'perplexity-worker.py'),
    (ROOT / 'tools' / 'copilot-worker.py', 'UNIO_COPILOT_WORKER_PY', 'copilot-worker.py'),
    (ROOT / 'tools' / 'antigravity-worker.py', 'UNIO_ANTIGRAVITY_WORKER_PY', 'antigravity-worker.py'),
)
BEGIN = '# BEGIN EMBEDDED ADAPTERS\n'
END = '# END EMBEDDED ADAPTERS\n'

PREFLIGHT = '''# Check every generated destination before replacing any adapter: all
# directories and all files are validated first, then all are written.
for adapters_dir in "$CONF_DIR/lib" "$CONF_DIR/lib/adapters"; do
  if [ -L "$adapters_dir" ] || { [ -e "$adapters_dir" ] && [ ! -d "$adapters_dir" ]; }; then
    echo "unio: refusing unsafe adapter directory: $adapters_dir" >&2
    exit 1
  fi
done
for adapters_file in "$CONF_DIR/lib/adapters/adapter-contract.py" "$CONF_DIR/lib/adapters/adapter-outcome.py" "$CONF_DIR/lib/adapters/adapter-budget.py" "$CONF_DIR/lib/adapters/vibe-worker.py" "$CONF_DIR/lib/adapters/perplexity-worker.py" "$CONF_DIR/lib/adapters/copilot-worker.py" "$CONF_DIR/lib/adapters/antigravity-worker.py"; do
  if [ -L "$adapters_file" ] || { [ -e "$adapters_file" ] && { [ ! -f "$adapters_file" ] || [ "$(stat -c '%h' -- "$adapters_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe adapter file: $adapters_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib/adapters"
'''


def embedded_block():
    parts = [BEGIN, PREFLIGHT]
    for source, delimiter, name in ADAPTERS:
        text = source.read_bytes().decode('utf-8')
        if not text.endswith('\n') or delimiter in text.splitlines() or '\r' in text:
            raise SystemExit(name + ' must be UTF-8 LF text with a final newline')
        head = 'cat > "$CONF_DIR/lib/adapters/' + name + "\" <<'" + delimiter + "'\n"
        parts.append(head + text + delimiter + '\n')
    for relative, name in (
        ('docs/development/AGENT-FLEET.md', 'AGENT-FLEET'),
        ('docs/WORK-WIP.md', 'WORK-WIP'),
        ('docs/WORKER-OUTCOMES.md', 'WORKER-OUTCOMES'),
        ('docs/REMOTE-POLICY.md', 'REMOTE-POLICY'),
        ('docs/development/LEAD-ROUTING.md', 'LEAD-ROUTING'),
        ('docs/development/MODEL-EFFORT.md', 'MODEL-EFFORT'),
        ('docs/ai/REASONING-PROFILES.md', 'REASONING-PROFILES'),
    ):
        guide = (ROOT / relative).read_text()
        delimiter = 'UNIO_' + name.replace('-', '_') + '_MD'
        if not guide.endswith('\n') or '\r' in guide or delimiter in guide.splitlines():
            raise SystemExit(name + ' guide must be LF text ending in a newline without its delimiter')
        # Existing operator guides stay intact, including symlinks.
        target = '$TPL_DIR/' + name + '.md'
        parts.append('if [ ! -e "' + target + '" ] && [ ! -L "' + target + '" ]; then\n'
                     + 'cat > "' + target + '" <<\'' + delimiter + "'\n"
                     + guide + delimiter + '\nfi\n')
    parts.append(END)
    return ''.join(parts)


def main():
    installer = ROOT / 'unio-install.sh'
    old = installer.read_text()
    block = embedded_block()
    if BEGIN in old:
        left, rest = old.split(BEGIN, 1)
        _, right = rest.split(END, 1)
        updated = left + block + right
    else:
        marker = '# END EMBEDDED DASHBOARD\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    # A copied engine or per-run thin config must retain offline contracts.
    # Bundle only reviewed canonical bytes, never import a route-selected file.
    sources = {route: (ROOT / ('tools/' + route + '-worker.py')).read_text()
               for route in ('vibe', 'antigravity', 'copilot', 'perplexity')}
    payload = base64.b64encode(zlib.compress(json.dumps(sources).encode())).decode()
    contract = (ROOT / 'tools/adapter-contract.py').read_text()
    contract = contract[:contract.index("if __name__ == '__main__':")]
    bootstrap = ('import base64, json, zlib\n'
                 + 'BUNDLED_ADAPTERS = json.loads(zlib.decompress(base64.b64decode(\n'
                 + ''.join(repr(line) + '\n' for line in textwrap.wrap(payload, 100)) + ')))\n'
                 + '__file__ = str(Path(sys.argv[2]) / "lib/adapters/adapter-contract.py")\n'
                 + 'if len(sys.argv)>3 and sys.argv[3]:\n'
                 + '    outcome_ns = {"__name__": "unio_outcomes"}\n'
                 + '    exec(' + repr((ROOT/'tools/task-outcomes.py').read_text()) + ', outcome_ns)\n'
                 + '    try: mode = outcome_ns["parse"](outcome_ns["read_task"](sys.argv[3]))\n'
                 + '    except (ValueError, OSError) as e: print("task outcome: "+str(e), file=sys.stderr); raise SystemExit(2)\n'
                 + '    route = check(sys.argv[1])\n'
                 + '    if mode=="implementation" and route.get("adapter") in ("copilot-worker","perplexity-worker"):\n'
                 + '        print("blocked_no_repo_access: declared implementation requires repository access; use a repository route or declare report-only", file=sys.stderr)\n'
                 + '        raise SystemExit(2)\n'
                 + 'if len(sys.argv)>4 and sys.argv[4]=="capture":\n'
                 + '    print("channel" if check(sys.argv[1]).get("adapter") in ("copilot-worker","perplexity-worker") else "native")\n'
                 + '    raise SystemExit(0)\n'
                 + 'raise SystemExit(main(sys.argv[1:2]))\n')
    block = ('route_contract() {\n  python3 -I -S -B - "$1" "$CONF_DIR" "${2:-}" "${3:-}" <<\'UNIO_ROUTE_CONTRACT_PY\'\n'
             + contract + bootstrap + 'UNIO_ROUTE_CONTRACT_PY\n}\n')
    begin, end = '# BEGIN EMBEDDED ROUTE CONTRACT\n', '# END EMBEDDED ROUTE CONTRACT\n'
    left, rest = updated.split(begin, 1)
    _, right = rest.split(end, 1)
    updated = left + begin + block + end + right
    helper = (ROOT / 'tools/wip-worker.py').read_text()
    begin, end = '# BEGIN EMBEDDED WIP\n', '# END EMBEDDED WIP\n'
    left, rest = updated.split(begin, 1)
    _, right = rest.split(end, 1)
    updated = left + begin + helper + end + right
    remote_helper = (ROOT / 'tools/remote-guard.py').read_bytes().decode('utf-8')
    if not remote_helper.endswith('\n') or '\r' in remote_helper or any(marker in remote_helper.splitlines() for marker in ('UNIO_REMOTE_GUARD_CORE_PY', 'UNIO_REMOTE_GUARD_PY')):
        raise SystemExit('remote guard must be UTF-8 LF text ending in a newline without its delimiter')
    begin_core, end_core = '# BEGIN EMBEDDED REMOTE GUARD CORE\n', '# END EMBEDDED REMOTE GUARD CORE\n'
    left, rest = updated.split(begin_core, 1)
    _, right = rest.split(end_core, 1)
    core = "remote_guard_source() {\n  cat <<'UNIO_REMOTE_GUARD_CORE_PY'\n" + remote_helper + 'UNIO_REMOTE_GUARD_CORE_PY\n}\n'
    updated = left + begin_core + core + end_core + right
    begin_rg, end_rg = '# BEGIN EMBEDDED REMOTE GUARD\n', '# END EMBEDDED REMOTE GUARD\n'
    left, rest = updated.split(begin_rg, 1)
    _, right = rest.split(end_rg, 1)
    rg_block = 'mkdir -p "$CONF_DIR/lib"\ncat > "$CONF_DIR/lib/remote-guard.py" <<\'UNIO_REMOTE_GUARD_PY\'\n' + remote_helper + 'UNIO_REMOTE_GUARD_PY\nchmod +x "$CONF_DIR/lib/remote-guard.py"\n'
    updated = left + begin_rg + rg_block + end_rg + right
    # These pre-existing templates have canonical public copies too. Updating
    # a role or task-fit result must not leave a stale standalone installer.
    for relative, name, delimiter in (
        ('docs/ai/MODEL-ROLES.md', 'MODEL-ROLES.md', 'MODEL_ROLES_TPL_EOF'),
        ('docs/development/MODEL-SCOREBOARD.md', 'MODEL-SCOREBOARD.md', 'MODEL_SCOREBOARD_TPL_EOF'),
        ('docs/WORK-MODES.md', 'WORK-MODES.md', 'WORKMODES_TPL_EOF'),
        ('docs/development/LEAD-BUDGET-CONSENT.md', 'LEAD-BUDGET-CONSENT.md', 'LEAD_BUDGET_CONSENT_TPL_EOF'),
    ):
        guide = (ROOT / relative).read_text()
        if not guide.endswith('\n') or '\r' in guide or delimiter in guide.splitlines():
            raise SystemExit(name + ' must be LF text ending in a newline without its delimiter')
        marker = 'cat > "$TPL_DIR/' + name + '" <<\'' + delimiter + "'\n"
        left, rest = updated.split(marker, 1)
        _, right = rest.split('\n' + delimiter + '\n', 1)
        updated = left + marker + guide + delimiter + '\n' + right
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded adapters differ; run python3 -B tools/embed-adapters.py')
        print('embedded adapters: all helpers byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-adapters.py [--check]')


if __name__ == '__main__':
    main()
