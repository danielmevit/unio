#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Declared task outcome metadata (docs/development/REPORT-OUTCOME-CONTRACT.md).

An optional '## Outcome' section in a task file declares exactly one plain
value: 'implementation' or 'report-only'. Absence means legacy behavior.
Duplicate, malformed or unknown declarations are actionable refusals, and
fenced examples are ignored while parsing. parse() never classifies arbitrary
model prose and performs no I/O.
"""
import os
import re
import stat
import sys

MODES = ('implementation', 'report-only')
LIMIT = 1048576
HEADER = '## Outcome'
SHOWN = 80


class OutcomeError(ValueError):
    """Actionable refusal for malformed declared outcome metadata."""


def _shown(line):
    text = ''.join(c if c >= ' ' or c in '\t' else '?' for c in line)
    return text[:SHOWN] + ('…' if len(text) > SHOWN else '')


def parse(text):
    """Return None (legacy), 'implementation' or 'report-only'.

    Raises OutcomeError with an actionable message for a duplicate section,
    an empty declaration, multiple values or unrecognized content. Fenced
    code blocks anywhere in the task are examples, never declarations.
    """
    if not isinstance(text, str):
        raise OutcomeError('task text must be a string')
    if '\x00' in text:
        raise OutcomeError('task text contains NUL bytes')
    headers = 0
    values = []
    in_section = False
    fence = None
    for line in text.split('\n'):
        stripped = line.strip()
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue
        heading = re.match(r'^ {0,3}(#{1,6})(?:[ \t]+(.*)|$)', line)
        if heading:
            title = (heading[2] or '').strip()
            if title.lower().startswith('outcome'):
                if line != HEADER:
                    raise OutcomeError("use the exact heading '## Outcome' and one plain value on the next line")
                in_section = True
                headers += 1
            else:
                in_section = False
            continue
        if not in_section or not stripped:
            continue
        if stripped in MODES and line == stripped:
            values.append(stripped)
        else:
            raise OutcomeError("the '## Outcome' section must contain exactly one plain "
                                'value, ' + ' or '.join(MODES)
                                + "; unrecognized line: " + _shown(stripped))
    if headers > 1:
        raise OutcomeError("duplicate '## Outcome' section (" + str(headers)
                           + ' found); a task declares at most one outcome')
    if headers == 0:
        if values:
            raise OutcomeError('outcome values found outside a ' + HEADER + ' section')
        return None
    if not values:
        raise OutcomeError("the '## Outcome' section declares no value; use exactly one of "
                            + ' or '.join(MODES))
    if len(values) > 1:
        raise OutcomeError("the '## Outcome' section declares multiple values ("
                            + ', '.join(values) + '); use exactly one')
    return values[0]


def read_task(path):
    """Bounded regular UTF-8 read; no symlink, FIFO or oversized task."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= LIMIT:
            raise OutcomeError('task file must be a regular file of at most 1 MiB')
        data = b''
        while len(data) <= LIMIT:
            chunk = os.read(fd, LIMIT + 1 - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        os.close(fd)
    if len(data) > LIMIT:
        raise OutcomeError('task file exceeds the 1 MiB bound')
    try:
        return data.decode('utf-8')
    except UnicodeError:
        raise OutcomeError('task file must be valid UTF-8') from None


def main(argv):
    if len(argv) != 2 or argv[0] != 'mode':
        print('usage: task-outcomes.py mode <task-file>', file=sys.stderr)
        return 2
    try:
        mode = parse(read_task(argv[1]))
    except (OutcomeError, OSError) as error:
        print('task outcome: ' + str(error), file=sys.stderr)
        return 2
    print(mode if mode is not None else 'legacy')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
