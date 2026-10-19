#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed managed Codex Source and usage guide byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'codex-worker.py', 'UNIO_CODEX_WORKER_PY'),
         ('docs', 'WORKER-EFFORT.md', 'UNIO_WORKER_EFFORT_MD'),
         ('docs', 'MANAGED-SESSIONS.md', 'UNIO_MANAGED_SESSIONS_MD'))
BEGIN = '# BEGIN EMBEDDED CODEX WORKER\n'
END = '# END EMBEDDED CODEX WORKER\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any codex worker file.\n'
    block += 'for worker_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$worker_dir" ] || { [ -e "$worker_dir" ] && [ ! -d "$worker_dir" ]; }; then
    echo "unio: refusing unsafe codex worker directory: $worker_dir" >&2
    exit 1
  fi
done
'''
    block += 'for worker_name in codex-worker.py WORKER-EFFORT.md MANAGED-SESSIONS.md; do\n'
    block += '''  worker_file="$CONF_DIR/lib/$worker_name"
  if [ -L "$worker_file" ] || { [ -e "$worker_file" ] && { [ ! -f "$worker_file" ] || [ "$(stat -c '%h' -- "$worker_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe codex worker file: $worker_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('codex worker source must be UTF-8 LF text with a final newline: ' + name)
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
            raise SystemExit('embedded codex worker differs; run python3 -B tools/embed-codex-worker.py')
        print('embedded codex worker: stores and CLI byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-codex-worker.py [--check]')


if __name__ == '__main__':
    main()
