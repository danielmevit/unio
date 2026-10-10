#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed explicit fleet-status observation script byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'fleet-status.py', 'UNIO_FLEET_STATUS_PY'),)
BEGIN = '# BEGIN EMBEDDED FLEET\n'
END = '# END EMBEDDED FLEET\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any fleet file.\n'
    block += 'for fleet_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$fleet_dir" ] || { [ -e "$fleet_dir" ] && [ ! -d "$fleet_dir" ]; }; then
    echo "unio: refusing unsafe fleet directory: $fleet_dir" >&2
    exit 1
  fi
done
'''
    block += 'for fleet_name in fleet-status.py; do\n'
    block += '''  fleet_file="$CONF_DIR/lib/$fleet_name"
  if [ -L "$fleet_file" ] || { [ -e "$fleet_file" ] && { [ ! -f "$fleet_file" ] || [ "$(stat -c '%h' -- "$fleet_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe fleet file: $fleet_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('fleet source must be UTF-8 LF text with a final newline: ' + name)
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
        marker = '# END EMBEDDED READINESS\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded fleet differs; run python3 -B tools/embed-fleet.py')
        print('embedded fleet: stores and CLI byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-fleet.py [--check]')


if __name__ == '__main__':
    main()
