#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed explicit task-plan observation script byte-identically."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'task-plan.py', 'UNIO_TASK_PLAN_PY'),)
BEGIN = '# BEGIN EMBEDDED TASK PLAN\n'
END = '# END EMBEDDED TASK PLAN\n'
DIRS = ('"$CONF_DIR/lib"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any task plan file.\n'
    block += 'for plan_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$plan_dir" ] || { [ -e "$plan_dir" ] && [ ! -d "$plan_dir" ]; }; then
    echo "unio: refusing unsafe task plan directory: $plan_dir" >&2
    exit 1
  fi
done
'''
    block += 'for plan_name in task-plan.py; do\n'
    block += '''  plan_file="$CONF_DIR/lib/$plan_name"
  if [ -L "$plan_file" ] || { [ -e "$plan_file" ] && { [ ! -f "$plan_file" ] || [ "$(stat -c '%h' -- "$plan_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe task plan file: $plan_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('task plan source must be UTF-8 LF text with a final newline: ' + name)
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
        marker = '# END EMBEDDED FLEET\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded task plan differs; run python3 -B tools/embed-task-plan.py')
        print('embedded task plan: stores and CLI byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-task-plan.py [--check]')


if __name__ == '__main__':
    main()
