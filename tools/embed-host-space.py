#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Keep the standalone quality runtime's host observer byte-identical."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parent.parent
path = ROOT / 'unio-install.sh'
old = path.read_text()
begin = '# BEGIN QUALITY HOST SPACE\n'
end = '# END QUALITY HOST SPACE\n'
block = begin + 'host_space = {"__name__": "unio_host_space"}\nexec(' + repr((ROOT / 'tools/host-space.py').read_text()) + ', host_space)\n' + end
if begin in old:
    left, rest = old.split(begin, 1)
    _, right = rest.split(end, 1)
    updated = left + block + right
else:
    marker = "<<'QUALITY_PY'\n"
    updated = old.replace(marker, marker + block, 1)
if sys.argv[1:] == ['--check']:
    if old != updated:
        raise SystemExit('host space embed differs; run tools/embed-host-space.py')
    print('host space embed: byte-identical')
elif not sys.argv[1:]:
    path.write_text(updated)
else:
    raise SystemExit('usage: embed-host-space.py [--check]')
