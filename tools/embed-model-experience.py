#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed explicit model-experience script byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'model-experience.py', 'UNIO_MODEL_EXPERIENCE_PY'),)
BEGIN = '# BEGIN EMBEDDED MODEL EXPERIENCE\n'
END = '# END EMBEDDED MODEL EXPERIENCE\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any experience file.\n'
    block += 'for experience_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$experience_dir" ] || { [ -e "$experience_dir" ] && [ ! -d "$experience_dir" ]; }; then
    echo "unio: refusing unsafe experience directory: $experience_dir" >&2
    exit 1
  fi
done
'''
    block += 'for experience_name in model-experience.py; do\n'
    block += '''  experience_file="$CONF_DIR/lib/$experience_name"
  if [ -L "$experience_file" ] || { [ -e "$experience_file" ] && { [ ! -f "$experience_file" ] || [ "$(stat -c '%h' -- "$experience_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe experience file: $experience_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('experience source must be UTF-8 LF text with a final newline: ' + name)
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
        marker = '# END EMBEDDED ADAPTERS\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded experience differs; run python3 -B tools/embed-model-experience.py')
        print('embedded experience: stores and CLI byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-model-experience.py [--check]')


if __name__ == '__main__':
    main()
