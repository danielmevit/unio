#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed the runtime observation module byte-identically into QUALITY_PY."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
BEGIN = '# BEGIN QUALITY RUN OBSERVATION\n'
END = '# END QUALITY RUN OBSERVATION\n'
ANCHOR = '# END QUALITY OUTCOME PARSER\n'


def block():
    source = (ROOT / 'tools' / 'run-observation.py').read_bytes().decode('utf-8')
    if not source.endswith('\n') or '\r' in source:
        raise SystemExit('run-observation.py must be UTF-8 LF text with a final newline')
    return (BEGIN + 'observation_ns = {"__name__": "unio_run_observation"}\n'
            + 'exec(' + repr(source) + ', observation_ns)\n' + END)


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
            raise SystemExit('quality anchor not found exactly once')
        updated = old.replace(ANCHOR, ANCHOR + new, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded run observation differs; run python3 -B tools/embed-run-observation.py')
        print('embedded run observation: byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-run-observation.py [--check]')


if __name__ == '__main__':
    main()
