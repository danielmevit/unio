#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed read-only worktree cache inventory byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'worktree-cache.py', 'UNIO_WORKTREE_CACHE_PY'),)
BEGIN = '# BEGIN EMBEDDED WORKTREE CACHE\n'
END = '# END EMBEDDED WORKTREE CACHE\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any worktree cache file.\n'
    block += 'for cache_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$cache_dir" ] || { [ -e "$cache_dir" ] && [ ! -d "$cache_dir" ]; }; then
    echo "unio: refusing unsafe worktree cache directory: $cache_dir" >&2
    exit 1
  fi
done
'''
    block += 'for cache_name in worktree-cache.py; do\n'
    block += '''  cache_file="$CONF_DIR/lib/$cache_name"
  if [ -L "$cache_file" ] || { [ -e "$cache_file" ] && { [ ! -f "$cache_file" ] || [ "$(stat -c '%h' -- "$cache_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe worktree cache file: $cache_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('worktree cache source must be UTF-8 LF text with a final newline: ' + name)
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
        marker = '# END EMBEDDED TASK PLAN\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded worktree cache differs; run python3 -B tools/embed-worktree-cache.py')
        print('embedded worktree cache: helper byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-worktree-cache.py [--check]')


if __name__ == '__main__':
    main()
