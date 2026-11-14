#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only
"""Keep the standalone installer's task-preview helper byte-identical.

Embeds tools/task-preview.sh into the installer as:
- a QUALITY TASK PREVIEW Python facts block (snapshot/changed/mode/artifacts)
- a TASK PREVIEW SHELL block (cmd_verify_preview)
and keeps the thin quality dispatch plus verify --preview case arm in sync.

Run without arguments to refresh; --check verifies byte identity.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
installer = ROOT / 'unio-install.sh'
helper = ROOT / 'tools/task-preview.sh'
source = helper.read_text()
begin_marker = ": <<'TASK_PREVIEW_PY'\n"
end_marker = "TASK_PREVIEW_PY\n"
assert begin_marker in source, 'task-preview python marker missing'
assert end_marker in source, 'task-preview python terminator missing'
python_source = source.split(begin_marker, 1)[1].split(end_marker, 1)[0]

begin_py = '# BEGIN QUALITY TASK PREVIEW\n'
end_py = '# END QUALITY TASK PREVIEW\n'
helpers = ("for _helper in ('fail','ident','locations','snapshot','changed',"
           "'task_mode','task_artifacts'):\n"
           "    task_preview_ns[_helper] = globals()[_helper]\n")
py_block = (begin_py + 'task_preview_ns = {"__name__": "unio_task_preview"}\n'
            + helpers + 'exec(' + repr(python_source) + ', task_preview_ns)\n'
            + end_py)

begin_sh = '# BEGIN TASK PREVIEW SHELL\n'
end_sh = '# END TASK PREVIEW SHELL\n'
sh_block = begin_sh + source + end_sh

dispatch = ("    elif cmd=='task-preview-facts':\n"
            "        print(json.dumps(task_preview_ns['facts'](*a),"
            "sort_keys=True,ensure_ascii=True,separators=(',',':')))\n")
dispatch_anchor = ("    elif cmd=='changed':\n"
                   "        ch=changed(*a)\n"
                   "        sys.stdout.buffer.write(b''.join(os.fsencode(p)+b'\\0' "
                   "for p in sorted(set(sum(ch.values(),[])))))\n")

verify_old = '  verify)   cmd_verify "${2:-}" "${3:-}";;\n'
verify_new = '''  verify)
    _preview=0
    for _preview_arg in "${@:2}"; do
      [ "$_preview_arg" = --preview ] && _preview=1
    done
    if [ "$_preview" = 1 ]; then cmd_verify_preview "${@:2}"
    else cmd_verify "${2:-}" "${3:-}"; fi;;
'''

old = installer.read_text()
updated = old

if begin_py in updated:
    left, rest = updated.split(begin_py, 1)
    _, right = rest.split(end_py, 1)
    updated = left + py_block + right
else:
    marker = 'try:\n    cmd,*a=sys.argv[1:]\n'
    assert marker in updated, 'quality dispatch marker missing'
    updated = updated.replace(marker, py_block + marker, 1)

if begin_sh in updated:
    left, rest = updated.split(begin_sh, 1)
    _, right = rest.split(end_sh, 1)
    updated = left + sh_block + right
else:
    marker = '# ---------------------------------------------------------------- verify\ncmd_verify() {'
    assert marker in updated, 'cmd_verify marker missing'
    updated = updated.replace(marker, sh_block + marker, 1)

if dispatch not in updated:
    assert dispatch_anchor in updated, 'quality changed dispatch missing'
    updated = updated.replace(dispatch_anchor, dispatch_anchor + dispatch, 1)

if verify_old in updated:
    updated = updated.replace(verify_old, verify_new, 1)
elif verify_new not in updated:
    raise SystemExit('verify dispatch arm missing')

if sys.argv[1:] == ['--check']:
    if old != updated:
        raise SystemExit('embedded task preview differs; run tools/embed-task-preview.py')
    print('embedded task preview: byte-identical')
elif not sys.argv[1:]:
    installer.write_text(updated)
else:
    raise SystemExit('usage: embed-task-preview.py [--check]')
