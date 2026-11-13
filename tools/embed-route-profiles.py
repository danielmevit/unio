#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the optional route-profile helper byte-identically.

The canonical copy lives at tools/route-profiles.py and installs as
$CONF_DIR/lib/route-profiles.py, driven by the read-only `unio routes`
command. The installer copies the exact reviewed bytes: no external
dependency is added and no model, provider or CLI is invoked.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
NAME = 'route-profiles.py'
DELIMITER = 'UNIO_ROUTE_PROFILES_PY'
BEGIN = '# BEGIN EMBEDDED ROUTE PROFILES\n'
END = '# END EMBEDDED ROUTE PROFILES\n'


def embedded_block():
    source = (ROOT / 'tools' / NAME).read_bytes().decode('utf-8')
    if not source.endswith('\n') or DELIMITER in source.splitlines() or '\r' in source:
        raise SystemExit('route profile source must be UTF-8 LF text with a final newline')
    block = (BEGIN + '# Check every generated destination before replacing the route profile helper.\n'
             'for route_profiles_dir in "$CONF_DIR/lib"; do\n'
             '  if [ -L "$route_profiles_dir" ] || { [ -e "$route_profiles_dir" ] && [ ! -d "$route_profiles_dir" ]; }; then\n'
             '    echo "unio: refusing unsafe route profile directory: $route_profiles_dir" >&2\n'
             '    exit 1\n'
             '  fi\n'
             'done\n'
             'route_profiles_file="$CONF_DIR/lib/' + NAME + '"\n'
             'if [ -L "$route_profiles_file" ] || { [ -e "$route_profiles_file" ] && { [ ! -f "$route_profiles_file" ] || [ "$(stat -c \'%h\' -- "$route_profiles_file")" != 1 ]; }; }; then\n'
             '  echo "unio: refusing unsafe route profile file: $route_profiles_file" >&2\n'
             '  exit 1\n'
             'fi\n'
             'mkdir -p "$CONF_DIR/lib"\n'
             'cat > "$route_profiles_file" <<\'' + DELIMITER + "'\n"
             + source + DELIMITER + '\n' + END)
    return block


def main():
    installer = ROOT / 'unio-install.sh'
    old = installer.read_text()
    block = embedded_block()
    if BEGIN in old:
        left, rest = old.split(BEGIN, 1)
        _, right = rest.split(END, 1)
        updated = left + block + right
    else:
        marker = '# END EMBEDDED CLI UPDATES\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded route profiles differ; run python3 -B tools/embed-route-profiles.py')
        print('embedded route profiles: helper byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-route-profiles.py [--check]')


if __name__ == '__main__':
    main()
