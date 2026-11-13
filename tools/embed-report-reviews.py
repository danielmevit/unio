#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only
"""Keep the standalone installer's report-review module byte-identical.

Embeds tools/report-reviews.py into the installer's quality runtime as a
QUALITY REPORT REVIEWS block. The module is exec'd into a namespace
pre-populated with the engine's existing validators, so the embedded copy
reuses them instead of shipping a second validator engine. Run without
arguments to refresh the embedded block; --check verifies byte identity.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
installer = ROOT / 'unio-install.sh'
begin = '# BEGIN QUALITY REPORT REVIEWS\n'
end = '# END QUALITY REPORT REVIEWS\n'
helpers = ("for _helper in ('fail','ident','safe','storage_directory','stamp',"
           "'locations','snapshot','revision','load','task_mode','report_evidence',"
           "'outcome_directory','delivery_directory','delivery_check',"
           "'material_bytes_v2','changed','review_json','findings_block_schema',"
           "'regular','delivery_ns'):\n"
           "    report_reviews_ns[_helper] = globals()[_helper]\n")
source = (ROOT / 'tools/report-reviews.py').read_text()
block = (begin + 'report_reviews_ns = {"__name__": "unio_report_reviews"}\n'
         + helpers + 'exec(' + repr(source) + ', report_reviews_ns)\n' + end)
old = installer.read_text()
if begin in old:
    left, rest = old.split(begin, 1)
    _, right = rest.split(end, 1)
    updated = left + block + right
else:
    marker = 'try:\n    cmd,*a=sys.argv[1:]\n'
    assert marker in old, 'quality dispatch marker missing'
    updated = old.replace(marker, block + marker, 1)
if sys.argv[1:] == ['--check']:
    if old != updated:
        raise SystemExit('embedded report reviews differ; run tools/embed-report-reviews.py')
    print('embedded report reviews: byte-identical')
elif not sys.argv[1:]:
    installer.write_text(updated)
else:
    raise SystemExit('usage: embed-report-reviews.py [--check]')
