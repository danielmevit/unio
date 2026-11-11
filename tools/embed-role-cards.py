#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Embed canonical role startup cards byte-identically.

The canonical copies live at docs/ai/WORKER-STARTUP-CARD.md and
docs/ai/REVIEWER-STARTUP-CARD.md, and install as templates under
$TPL_DIR ($CONF_DIR/templates). The installer copies the exact reviewed bytes:
no external dependency is added and no model, provider or CLI is invoked.
"""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
FILES = (
    ('docs/ai', 'WORKER-STARTUP-CARD.md', 'UNIO_WORKER_STARTUP_CARD_MD'),
    ('docs/ai', 'REVIEWER-STARTUP-CARD.md', 'UNIO_REVIEWER_STARTUP_CARD_MD'),
)
BEGIN = '# BEGIN EMBEDDED ROLE CARDS\n'
END = '# END EMBEDDED ROLE CARDS\n'
DIRS = ('"$TPL_DIR"',)


def embedded_block():
    block = BEGIN + '# Check every generated destination before replacing any role card template.\n'
    block += 'for role_cards_dir in ' + ' '.join(DIRS) + '; do\n'
    block += '''  if [ -L "$role_cards_dir" ] || { [ -e "$role_cards_dir" ] && [ ! -d "$role_cards_dir" ]; }; then
    echo "unio: refusing unsafe role cards directory: $role_cards_dir" >&2
    exit 1
  fi
done
'''
    block += 'for role_cards_file in ' + ' '.join('"$TPL_DIR/' + name + '"' for _, name, _ in FILES) + '; do\n'
    block += '''  if [ -L "$role_cards_file" ] || { [ -e "$role_cards_file" ] && { [ ! -f "$role_cards_file" ] || [ "$(stat -c '%h' -- "$role_cards_file")" != 1 ]; }; }; then
    echo "unio: refusing unsafe role card file: $role_cards_file" >&2
    exit 1
  fi
done
mkdir -p "$TPL_DIR"
'''
    for directory, name, delimiter in FILES:
        source = (ROOT / directory / name).read_bytes().decode('utf-8')
        if not source.endswith('\n') or delimiter in source.splitlines() or '\r' in source:
            raise SystemExit('role card source must be UTF-8 LF text with a final newline: ' + name)
        block += 'cat > "$TPL_DIR/' + name + '" <<\'' + delimiter + "'\n"
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
        marker = '# ---------------------------------------------------------------- templates\n'
        assert marker in old
        updated = old.replace(marker, marker + block, 1)
    if sys.argv[1:] == ['--check']:
        if old != updated:
            raise SystemExit('embedded role cards differ; run python3 -B tools/embed-role-cards.py')
        print('embedded role cards: templates byte-identical')
    elif not sys.argv[1:]:
        installer.write_text(updated)
    else:
        raise SystemExit('usage: embed-role-cards.py [--check]')


if __name__ == '__main__':
    main()
