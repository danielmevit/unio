#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the declared-outcome helper byte-identically for engine and adapters."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (('tools', 'task-outcomes.py', 'UNIO_TASK_OUTCOMES_PY'),)
BEGIN = '# BEGIN EMBEDDED TASK OUTCOMES\n'
END = '# END EMBEDDED TASK OUTCOMES\n'
DIRS = ('"$CONF_DIR/lib"', '"$CONF_DIR/lib/adapters"')
NAMES = ('task-outcomes.py',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing the helper.\n'
    block += 'for outcomes_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$outcomes_dir" ] || { [ -e "$outcomes_dir" ] && [ ! -d "$outcomes_dir" ]; }; then
    echo "unio: refusing unsafe adapter directory: $outcomes_dir (task outcomes)" >&2
    exit 1
  fi
done
'''
    block += 'for outcomes_file in'
    for name in NAMES:
        block += ' "$CONF_DIR/lib/' + name + '" "$CONF_DIR/lib/adapters/' + name + '"'
    block += '''; do
  if [ -L "$outcomes_file" ] || { [ -e "$outcomes_file" ] && { [ ! -f "$outcomes_file" ] || [ "$(stat -c '%h' -- "$outcomes_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe task outcome file: $outcomes_file" >&2
    exit 1
  fi
done
mkdir -p "$CONF_DIR/lib" "$CONF_DIR/lib/adapters"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('task outcome source must be UTF-8 LF text with a final newline: ' + name)
        for target in ('"$CONF_DIR/lib"', '"$CONF_DIR/lib/adapters"'):
            block += 'cat > ' + target + '/' + name + " <<'" + delimiter + "'\n"
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
    # Freeze the parser into the engine as well: copied engines and thin
    # UNIO_CONF_DIR overrides cannot depend on an installed lib directory.
    begin, end = '# BEGIN QUALITY OUTCOME PARSER\n', '# END QUALITY OUTCOME PARSER\n'
    source = (ROOT/'tools/task-outcomes.py').read_text()
    parser = begin + 'outcome_ns = {"__name__": "unio_task_outcomes"}\nexec(' + repr(source) + ', outcome_ns)\n' + end
    if begin in updated:
        left, rest = updated.split(begin, 1)
        _, right = rest.split(end, 1)
        updated = left + parser + right
    else:
        marker = " <<'QUALITY_PY'\n"
        updated = updated.replace(marker, marker + parser, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded task outcomes differ; run python3 -B tools/embed-task-outcomes.py')
        print('embedded task outcomes: engine and adapters byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-task-outcomes.py [--check]')


if __name__ == '__main__':
    main()
