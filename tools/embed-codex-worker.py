#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed explicit codex-worker script byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'codex-worker.py', 'UNIO_CODEX_WORKER_PY'), ('docs', 'WORKER-EFFORT.md', 'UNIO_WORKER_EFFORT_MD'))
BEGIN = '# BEGIN EMBEDDED CODEX WORKER\n'
END = '# END EMBEDDED CODEX WORKER\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any effort file.\n'
    block += 'for effort_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$effort_dir" ] || { [ -e "$effort_dir" ] && [ ! -d "$effort_dir" ]; }; then
    echo "unio: refusing unsafe effort directory: $effort_dir" >&2
    exit 1
  fi
done
'''
    block += 'for effort_name in codex-worker.py WORKER-EFFORT.md; do\n'
    block += '''  effort_file="$CONF_DIR/lib/$effort_name"
  if [ -L "$effort_file" ] || { [ -e "$effort_file" ] && { [ ! -f "$effort_file" ] || [ "$(stat -c '%h' -- "$effort_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe effort file: $effort_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('effort source must be UTF-8 LF text with a final newline: ' + name)
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
            raise SystemExit('embedded effort differs; run python3 -B tools/embed-codex-worker.py')
        print('embedded effort: helper and guide byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-codex-worker.py [--check]')


if __name__ == '__main__':
    main()
