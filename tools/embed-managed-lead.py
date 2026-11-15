#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed managed lead core, bridge, effort policy and lead-session CLI."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'managed-lead.py', 'UNIO_MANAGED_LEAD_PY'),
         ('tools', 'managed-lead-codex.py', 'UNIO_MANAGED_LEAD_CODEX_PY'),
         ('tools', 'lead-effort.py', 'UNIO_LEAD_EFFORT_PY'),
         ('tools', 'lead-session.py', 'UNIO_LEAD_SESSION_PY'),
         ('tools', 'lead-session-codex.py', 'UNIO_LEAD_SESSION_CODEX_PY'),
         ('docs', 'ADAPTIVE-LEAD-EFFORT.md', 'UNIO_ADAPTIVE_LEAD_EFFORT_MD'))
BEGIN = '# BEGIN EMBEDDED MANAGED LEAD\n'
END = '# END EMBEDDED MANAGED LEAD\n'
DIRS = ('"$CONF_DIR/lib"',)
NAMES = ('managed-lead.py', 'managed-lead-codex.py', 'lead-effort.py',
         'lead-session.py', 'lead-session-codex.py',
         'ADAPTIVE-LEAD-EFFORT.md')


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any managed lead file.\n'
    block += 'for lead_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$lead_dir" ] || { [ -e "$lead_dir" ] && [ ! -d "$lead_dir" ]; }; then
    echo "unio: refusing unsafe managed lead directory: $lead_dir" >&2
    exit 1
  fi
done
'''
    block += 'for lead_name in ' + ' '.join(repr(name).replace("'", '"') for name in NAMES) + '; do\n'
    block += '''  lead_file="$CONF_DIR/lib/$lead_name"
  if [ -L "$lead_file" ] || { [ -e "$lead_file" ] && { [ ! -f "$lead_file" ] || [ "$(stat -c '%h' -- "$lead_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe managed lead file: $lead_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('managed lead source must be UTF-8 LF text with a final newline: ' + name)
        block += 'cat > "$CONF_DIR/lib/' + name + '" <<\'' + delimiter + "'\n"
        block += source + delimiter + '\n'
    return block + END


def main():
    installer = ROOT / 'unio-install.sh'
    old = installer.read_text()
    block = embedded_block()
    if BEGIN in old:
        left, rest = old.split(BEGIN, 1)
        _, right = rest.split(END, 1)
        updated = left + block + right
    else:
        marker = '# END EMBEDDED CODEX WORKER\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded managed lead differs; run python3 -B tools/embed-managed-lead.py')
        print('embedded managed lead: stores and CLI byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-managed-lead.py [--check]')


if __name__ == '__main__':
    main()
