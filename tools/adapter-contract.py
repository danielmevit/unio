#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Offline canonical argv preflight. Never execute a configured command.

Only this installed helper's own sibling adapter modules are loaded. No module
path or metadata executable supplied by a route is imported or invoked.
Custom/wrapped shell commands retain their existing execution behavior and are
explicitly unvalidated. Validation proves argument syntax/bounds only.
"""
import argparse
import contextlib
import importlib.util
import io
import os
import stat
from pathlib import Path
import re
import shlex
import sys
import types

ROUTES = ('vibe', 'antigravity', 'copilot', 'perplexity')


class ArgumentError(ValueError):
    pass


class SafeParser(argparse.ArgumentParser):
    """Keep raw values (including secrets) out of parse diagnostics."""
    def error(self, message):
        match = re.search(r'argument (--[a-z][a-z-]*)', message)
        flag = match.group(1) if match else None
        action = self._option_string_actions.get(flag)
        if action is not None:
            bounds = getattr(action, 'safe_integer_bounds', None)
            if bounds is not None:
                accepted = 'an integer in [' + ', '.join(str(v) for v in bounds) + ']'
            elif action.choices:
                accepted = 'one of ' + ', '.join(str(v) for v in action.choices)
            elif action.type is int:
                accepted = 'an integer within the adapter bounds'
            elif action.type is float:
                accepted = 'a finite number within the adapter bounds'
            else:
                accepted = 'a value in the documented adapter range'
            self.exit(2, flag + ': expected ' + accepted + '; edit the agents.conf route\n')
        missing = [a.option_strings[0] for a in self._actions
                   if a.required]
        detail = 'required options: ' + ', '.join(missing) if missing else 'see adapter --help for accepted options'
        self.exit(2, 'invalid or unrecognized route arguments; ' + detail + '\n')


def parser(**kwargs):
    return SafeParser(**kwargs)


def validate(parser, bounds, argv, route):
    """Use the actual adapter parser, choices and bound checks, without I/O."""
    captured = io.StringIO()
    parser.error = SafeParser.error.__get__(parser, type(parser))
    try:
        # argparse --help must not pollute the metadata JSON or become a run.
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(captured):
            args = parser.parse_args(argv)
        problems = bounds(args) if bounds else []
        if route == 'perplexity':
            if args.check or args.child:
                problems.append('--check and --child are metadata/internal modes, not runnable routes')
            if args.model is None:
                problems.append('--model: required; accepted choices: ' + ', '.join(sorted(
                    parser._option_string_actions['--model'].choices)))
            if args.receipt_dir and args.proposal_dir:
                problems.append('--receipt-dir and --proposal-dir are mutually exclusive; select one')
        if problems:
            raise ArgumentError('; '.join(problems))
    except ArgumentError as error:
        return dict(schema_version=1, adapter=route+'-worker', state='invalid', detail=str(error))
    except SystemExit:
        return dict(schema_version=1, adapter=route+'-worker', state='invalid',
                    detail=captured.getvalue().strip() or 'help/exit is not a runnable route; supply the required adapter arguments')
    return dict(schema_version=1, adapter=route+'-worker', state='valid', detail=None)


def simple_argv(command):
    # Expansions are shell semantics we cannot validate. Single-quoted literals
    # remain valid paths/arguments; operators inside quotes are literals too.
    argv = shlex.split(command)
    quote = None
    escape = False
    for char in command:
        if escape:
            escape = False
            continue
        if char == '\\' and quote != "'":
            escape = True
            continue
        if char in ("'", '"'):
            if quote is None:
                quote = char
            elif quote == char:
                quote = None
        elif char in '$`' and quote != "'":
            return None
        elif char in '\n\r':
            return None
        elif quote is None and char in ';&|<>()*?{}~':
            return None
    return argv


def check(command):
    base = Path(__file__).resolve().parent
    targets = {str(base / (r+'-worker.py')): r for r in ROUTES}
    try:
        argv = simple_argv(command)
    except ValueError:
        # Recover only complete leading tokens. Recognize the interpreter and
        # canonical source normally; a wrapper containing a path is not proof.
        lexer = shlex.shlex(command, posix=True)
        lexer.whitespace_split = True
        lexer.commenters = ''
        prefix = []
        try:
            while True:
                token = lexer.get_token()
                if token is None:
                    break
                prefix.append(token)
        except ValueError:
            pass
        if prefix and check(shlex.join(prefix))['state'] != 'unvalidated':
            return dict(state='invalid', detail='malformed quoting in canonical adapter arguments; close the quote')
        argv = None
    if not argv or Path(argv[0]).name not in ('python', 'python3'):
        return dict(state='unvalidated', detail='custom/wrapped command; no discoverable canonical argument contract')
    argv = argv[1:]
    while argv and argv[0] in ('-B', '-I', '-S'):
        argv = argv[1:]
    bundled = globals().get('BUNDLED_ADAPTERS', {})
    if bundled:
        targets = {}
    if argv and bundled:
        # Recognize relocated canonical sources by exact bytes, never by a
        # route-supplied module name. Execute only our frozen bundled source.
        candidate = Path(argv[0])
        route = candidate.name.removesuffix('-worker.py')
        if candidate.name == route + '-worker.py' and route in bundled:
            try:
                expected = bundled[route].encode()
                # O_NONBLOCK prevents FIFO/device opens from stalling preflight;
                # O_NOFOLLOW refuses a final symlink. Inspect the opened fd to
                # avoid a pathname race and read only a bounded regular file.
                flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
                with os.fdopen(os.open(candidate, flags), 'rb') as source:
                    info = os.fstat(source.fileno())
                    if stat.S_ISREG(info.st_mode) and info.st_size == len(expected):
                        actual = source.read(len(expected) + 1)
                        if actual == expected:
                            targets[str(candidate)] = route
            except OSError:
                pass
    if not argv or argv[0] not in targets:
        return dict(state='unvalidated', detail='custom/wrapped command; no discoverable canonical argument contract')
    route = targets[argv[0]]
    # Crucially use OUR path, never an import path extracted from shell text.
    if bundled:
        # The engine's bundle is generated from the same canonical sources as
        # installed adapter execution, including every parser and bound check.
        module = types.ModuleType('unio_contract_'+route)
        module.__file__ = str(base/(route+'-worker.py'))
        exec(compile(bundled[route], module.__file__, 'exec'), module.__dict__)
    else:
        spec = importlib.util.spec_from_file_location('unio_contract_'+route, base/(route+'-worker.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    return validate(module.build_parser(), getattr(module, 'check_bounds', None), argv[1:], route)


def main(argv):
    if len(argv) != 1:
        print('Route contract: invalid invocation', file=sys.stderr)
        return 2
    try:
        result = check(argv[0])
        print('Route contract: '+result['state'] + (': '+result['detail'] if result.get('detail') else ' (canonical argument syntax and bounds)'))
        return 2 if result['state'] == 'invalid' else 0
    except (OSError, ValueError, ImportError, AttributeError):
        print('Route contract: unavailable; reinstall the matching adapter helpers', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
