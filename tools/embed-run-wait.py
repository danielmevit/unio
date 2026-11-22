#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the background acknowledgement/waiter module into the save runtime."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
BEGIN = '# BEGIN EMBEDDED RUN WAIT\n'
END = '# END EMBEDDED RUN WAIT\n'
ANCHOR = '# END EMBEDDED WIP\n'


def block():
    source = (ROOT / 'tools' / 'run-wait.py').read_bytes().decode('utf-8')
    if not source.endswith('\n') or '\r' in source:
        raise SystemExit('run-wait.py must be UTF-8 LF text with a final newline')
    if BEGIN in source or END in source:
        raise SystemExit('run-wait.py must not contain its own embed markers')
    return BEGIN + source + END


def main():
    installer = ROOT / 'unio-install.sh'
    old = installer.read_text()
    new = block()
    if BEGIN in old:
        left, rest = old.split(BEGIN, 1)
        right = rest.split(END, 1)[1]
        updated = left + new + right
    else:
        if old.count(ANCHOR) != 1:
            raise SystemExit('save-runtime anchor not found exactly once')
        updated = old.replace(ANCHOR, ANCHOR + new, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded run wait differs; run python3 -B tools/embed-run-wait.py')
        print('embedded run wait: byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-run-wait.py [--check]')


if __name__ == '__main__':
    main()
