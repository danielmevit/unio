#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the AI CLI update payload byte-identically.

The canonical copy lives at tools/cli-updates.py and installs as
$CONF_DIR/lib/cli-updates.py, driven by `unio update clis` and the
doctor/resume awareness line. The installer copies the exact reviewed bytes:
no external dependency is added and no model, provider or CLI is invoked.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'cli-updates.py', 'UNIO_CLI_UPDATES_PY'),)
BEGIN = '# BEGIN EMBEDDED CLI UPDATES\n'
END = '# END EMBEDDED CLI UPDATES\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any CLI update file.\n'
    block += 'for cli_updates_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$cli_updates_dir" ] || { [ -e "$cli_updates_dir" ] && [ ! -d "$cli_updates_dir" ]; }; then
    echo "unio: refusing unsafe CLI update directory: $cli_updates_dir" >&2
    exit 1
  fi
done
'''
    block += 'for cli_updates_name in ' + ' '.join(name for _, name, _ in FILES) + '; do\n'
    block += '''  cli_updates_file="$CONF_DIR/lib/$cli_updates_name"
  if [ -L "$cli_updates_file" ] || { [ -e "$cli_updates_file" ] && { [ ! -f "$cli_updates_file" ] || [ "$(stat -c '%h' -- "$cli_updates_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe CLI update file: $cli_updates_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('CLI update source must be UTF-8 LF text with a final newline: ' + name)
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
        marker = '# END EMBEDDED REMOTE GUARD\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded CLI updates differ; run python3 -B tools/embed-cli-updates.py')
        print('embedded CLI updates: payload byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-cli-updates.py [--check]')


if __name__ == '__main__':
    main()
