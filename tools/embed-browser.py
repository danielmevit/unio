#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the fixed browser payload as readable, byte-identical shell heredocs."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = ('server.py', 'launcher.py', 'progress.py', 'worker_files.py',
         'plan_store.py', 'job_store.py', 'execution_service.py', 'index.html',
         'activity.js', 'activity.css', 'drafts.js', 'jobs.js', 'worker_console.js', 'theme.js')
BEGIN = '# BEGIN EMBEDDED BROWSER\n'
END = '# END EMBEDDED BROWSER\n'


def embedded_block():
    block = BEGIN + '''# Check every generated destination before replacing any browser file.
for browser_dir in "$CONF_DIR/lib" "$CONF_DIR/lib/browser"; do
  if [ -L "$browser_dir" ] || { [ -e "$browser_dir" ] && [ ! -d "$browser_dir" ]; }; then
    echo "unio: refusing unsafe browser directory: $browser_dir" >&2
    exit 1
  fi
done
'''
    block += 'for browser_name in ' + ' '.join(FILES) + '; do\n'
    block += '''  browser_file="$CONF_DIR/lib/browser/$browser_name"
  if [ -L "$browser_file" ] || { [ -e "$browser_file" ] && { [ ! -f "$browser_file" ] || [ "$(stat -c '%h' -- "$browser_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe browser file: $browser_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib/browser"
'''
    for name in FILES:
        raw = (ROOT / 'bridge' / name).read_bytes()
        source = raw.decode('utf-8')
        delimiter = 'UNIO_BROWSER_' + name.upper().replace('.', '_')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('browser source must be UTF-8 LF text with a final newline: ' + name)
        block += 'cat > "$CONF_DIR/lib/browser/' + name + '" <<\'' + delimiter + "'\n"
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
        marker = '# Remove only copies and links owned by the legacy installer.\n'
        assert marker in old
        updated = old.replace(marker, block + '\n' + marker, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded browser differs; run python3 -B tools/embed-browser.py')
        print('embedded browser: all 13 files byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-browser.py [--check]')


if __name__ == '__main__':
    main()
