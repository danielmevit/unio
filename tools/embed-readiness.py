#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed explicit authentication observations and CLI byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('bridge', 'readiness.py', 'UNIO_READINESS_STORE_PY'),
         ('tools', 'agent-readiness.py', 'UNIO_READINESS_CLI_PY'))
BEGIN = '# BEGIN EMBEDDED READINESS\n'
END = '# END EMBEDDED READINESS\n'
DIRS = ('"$CONF_DIR/lib"', '"$CONF_DIR/lib/readiness"',
        '"$CONF_DIR/lib/readiness/bridge"', '"$CONF_DIR/lib/readiness/tools"')


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any readiness file.\n'
    block += 'for readiness_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$readiness_dir" ] || { [ -e "$readiness_dir" ] && [ ! -d "$readiness_dir" ]; }; then
    echo "unio: refusing unsafe readiness directory: $readiness_dir" >&2
    exit 1
  fi
done
'''
    block += 'for readiness_name in ' + ' '.join(d + '/' + n for d, n, _ in FILES) + '; do\n'
    block += '''  readiness_file="$CONF_DIR/lib/readiness/$readiness_name"
  if [ -L "$readiness_file" ] || { [ -e "$readiness_file" ] && { [ ! -f "$readiness_file" ] || [ "$(stat -c '%h' -- "$readiness_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe readiness file: $readiness_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib/readiness/bridge" "$CONF_DIR/lib/readiness/tools"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('readiness source must be UTF-8 LF text with a final newline: ' + name)
        block += 'cat > "$CONF_DIR/lib/readiness/' + directory + '/' + name + '" <<\'' + delimiter + "'\n"
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
        marker = '# END EMBEDDED CAPACITY\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded readiness differs; run python3 -B tools/embed-readiness.py')
        print('embedded readiness: stores and CLI byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-readiness.py [--check]')


if __name__ == '__main__':
    main()
