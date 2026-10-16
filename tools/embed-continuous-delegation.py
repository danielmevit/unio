#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the explicit continuous-delegation helper byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'continuous-delegation.py', 'UNIO_CONTINUOUS_DELEGATION_PY'),)
BEGIN = '# BEGIN EMBEDDED CONTINUOUS DELEGATION\n'
END = '# END EMBEDDED CONTINUOUS DELEGATION\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any continuous delegation file.\n'
    block += 'for dispatch_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$dispatch_dir" ] || { [ -e "$dispatch_dir" ] && [ ! -d "$dispatch_dir" ]; }; then
    echo "unio: refusing unsafe continuous delegation directory: $dispatch_dir" >&2
    exit 1
  fi
done
'''
    block += 'for dispatch_name in ' + ' '.join(name for _, name, _ in FILES) + '; do\n'
    block += '''  dispatch_file="$CONF_DIR/lib/$dispatch_name"
  if [ -L "$dispatch_file" ] || { [ -e "$dispatch_file" ] && { [ ! -f "$dispatch_file" ] || [ "$(stat -c '%h' -- "$dispatch_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe continuous delegation file: $dispatch_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('continuous delegation source must be UTF-8 LF text with a final newline: ' + name)
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
        marker = '# END EMBEDDED TASK DISPATCH\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded continuous delegation differs; run python3 -B tools/embed-continuous-delegation.py')
        print('embedded continuous delegation: helper byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-continuous-delegation.py [--check]')


if __name__ == '__main__':
    main()
