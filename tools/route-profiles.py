#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Optional typed route profiles: offline list/show/compile. No execution.

A route profile is a reusable launch recipe declaration. This helper only
reads the optional registry at $CONF_DIR/route-profiles.json and prints
declared requested settings; effective model/effort and remaining allowance
stay Unknown. `compile` prints exactly one safely quoted agents.conf entry
for the tested packaged Vibe 3.1.1 path, reusing the installed trusted
adapter parser/check_bounds as the authoritative accepted limits. Nothing
is written, executed, signed in or probed: no provider, CLI, version or
quota subprocess ever runs, and this works outside a project and while STOP
is set. The owner reviews the compiled line and adds it to agents.conf
themselves; a profile label never manufactures identity, consent or
allowance, and account/budget mappings stay native policy.
"""
import contextlib
import io
import json
import math
import os
from pathlib import Path
import re
import shlex
import stat
import sys
import types

REGISTRY_NAME = 'route-profiles.json'
REGISTRY_BYTES = 1048576
ADAPTER_RELATIVE = ('lib', 'adapters', 'vibe-worker.py')
ADAPTER_BYTES = 2097152
ROUTE_NAME = re.compile(r'[a-z][a-z0-9_-]{0,63}\Z')
# Credential-shaped input is refused (and never echoed) even where the plain
# grammar would accept it: a profile label or path is not a secret store.
SECRET_LIKE = re.compile(r'(?i)(?:sk-|gh[pousr]_|github_pat_|AKIA)[A-Za-z0-9_-]{8,}')
# Documented V1 compilation subset: the tested packaged Vibe 3.1.1 path.
# The installed trusted adapter remains authoritative at compile time; these
# closed declarations only decide what list/show reports and what refuses
# before any adapter is loaded.
SUPPORTED_ADAPTERS = ('vibe',)
SUPPORTED_CLI_VERSIONS = ('3.1.1',)
# Frozen V1 contract: the tested GLM 5.3 path only. The canonical adapter
# keeps its own original pins and legacy model routes unchanged and stays
# the final authority at compile time.
SUPPORTED_MODELS = ('glm-5-3',)
SUPPORTED_THINKING = ('high',)
REQUIRED_FIELDS = ('adapter', 'requested_cli_version', 'model', 'thinking', 'receipt_dir')
CAP_FIELDS = ('max_price', 'max_tokens', 'time_limit', 'max_turns')
CAP_FLAGS = {'max_price': '--max-price', 'max_tokens': '--max-tokens',
             'time_limit': '--time-limit', 'max_turns': '--max-turns'}
FIELDS = REQUIRED_FIELDS + CAP_FIELDS
UNKNOWN = 'unknown'
USAGE = ('usage: unio routes [--json] | unio routes show NAME [--json] | '
         'unio routes compile NAME')


class Invalid(Exception):
    pass


def read_regular(path, limit):
    """Bounded, no-follow read of a regular UTF-8 file without NUL bytes."""
    flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise Invalid('registry_or_adapter_input_invalid_or_oversized')
        data = source.read(limit + 1)
        if len(data) > limit:
            raise Invalid('registry_or_adapter_input_invalid_or_oversized')
    data.decode('utf-8', errors='strict')
    if b'\0' in data:
        raise Invalid('registry_or_adapter_input_contains_nul')
    return data


def strict_json(data):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def constant(_):
        raise ValueError('nonfinite JSON')

    return json.loads(data, object_pairs_hook=pairs, parse_constant=constant)


def check_text(value, what):
    if not isinstance(value, str) or not value:
        raise Invalid(what + ' must be a non-empty string')
    if re.search(r'[\x00-\x1f\x7f]', value):
        raise Invalid(what + ' contains control characters')
    return value


def check_cap(field, value):
    if value is None:
        return None
    if type(value) is bool or not isinstance(value, (int, float)):
        raise Invalid('cap ' + field + ' must be a finite number or null')
    try:
        finite = math.isfinite(value)
    except OverflowError:
        # Pathological magnitudes (for example 10**400) are not float-
        # representable; refuse them with the same bounded diagnostic
        # instead of crashing, and without duplicating any cap maximum.
        finite = False
    if not finite:
        raise Invalid('cap ' + field + ' must be a finite number or null')
    return value


def check_route(name, route):
    if not ROUTE_NAME.match(name):
        raise Invalid('route name does not match the agent identifier grammar '
                     '(a lowercase letter, then letters/digits/-/_, at most 64 characters)')
    if SECRET_LIKE.search(name):
        raise Invalid('route name contains a secret-like value (not shown); '
                     'use a plain agent-style identifier')
    if not isinstance(route, dict):
        raise Invalid('route ' + name + ' must be a mapping')
    unknown = sorted(set(route) - set(FIELDS))
    if unknown:
        raise Invalid('route ' + name + ' has unknown fields; the schema is closed '
                     '(see docs/integrations/ROUTE-PROFILES.md)')
    missing = [field for field in REQUIRED_FIELDS if field not in route]
    if missing:
        raise Invalid('route ' + name + ' is missing required fields: ' + ', '.join(missing))
    if route['adapter'] not in SUPPORTED_ADAPTERS:
        raise Invalid('route ' + name + ': unsupported adapter; V1 compiles only '
                     'the packaged vibe path (supported: ' + ', '.join(SUPPORTED_ADAPTERS) + ')')
    if route['requested_cli_version'] not in SUPPORTED_CLI_VERSIONS:
        raise Invalid('route ' + name + ': unsupported requested_cli_version; V1 compiles '
                     'only the documented Vibe ' + ', '.join(SUPPORTED_CLI_VERSIONS)
                     + ' path; other versions stay legacy routes')
    if route['model'] not in SUPPORTED_MODELS:
        raise Invalid('route ' + name + ': unsupported model for the Vibe '
                     + ', '.join(SUPPORTED_CLI_VERSIONS) + ' path (supported: '
                     + ', '.join(SUPPORTED_MODELS) + ')')
    if route['thinking'] not in SUPPORTED_THINKING:
        raise Invalid('route ' + name + ': unsupported thinking for Vibe '
                     + ', '.join(SUPPORTED_CLI_VERSIONS)
                     + '; the CLI has no per-run thinking control, so only the observed '
                     'catalog level high may be declared, with the effective effort Unknown')
    receipt = check_text(route['receipt_dir'], 'route ' + name + ' receipt_dir')
    if not receipt.startswith('/'):
        raise Invalid('route ' + name + ' receipt_dir must be an absolute path')
    if len(receipt) > 4096:
        raise Invalid('route ' + name + ' receipt_dir is too long')
    if SECRET_LIKE.search(receipt):
        raise Invalid('route ' + name + ' receipt_dir contains a secret-like value '
                     '(not shown); declare a plain private directory path')
    for field in CAP_FIELDS:
        if field in route:
            check_cap(field, route[field])
    return route


def check_requested_name(name):
    """Validate a requested show/compile name; refusals never echo it.

    A requested name is untrusted free-form input, so no error branch may
    echo it: the plain grammar accepts credential-shaped lowercase values,
    and no secret-prefix list is exhaustive enough to safely quote them.
    """
    if not ROUTE_NAME.match(name):
        raise Invalid('route name does not match the agent identifier grammar '
                     '(a lowercase letter, then letters/digits/-/_, at most 64 characters)')
    if SECRET_LIKE.search(name):
        raise Invalid('route name contains a secret-like value (not shown); '
                     'use a plain agent-style identifier')


def load_registry(conf_dir):
    """Missing optional file means an empty inventory; anything else validates."""
    path = Path(conf_dir) / REGISTRY_NAME
    try:
        info = os.lstat(path)
    except FileNotFoundError:
        return {}, path, False
    except OSError:
        raise Invalid('registry file is unreadable')
    if not stat.S_ISREG(info.st_mode):
        raise Invalid('registry file is not a regular file')
    if info.st_size > REGISTRY_BYTES:
        raise Invalid('registry file is oversized')
    try:
        value = strict_json(read_regular(path, REGISTRY_BYTES))
    except (ValueError, UnicodeError, RecursionError):
        raise Invalid('registry file is not valid JSON (strict parsing: no duplicate '
                     'keys, no nonfinite numbers)')
    except OSError:
        raise Invalid('registry file is unreadable')
    if not isinstance(value, dict):
        raise Invalid('registry root must be an object')
    unknown = sorted(set(value) - {'schema_version', 'routes'})
    if unknown:
        raise Invalid('registry root has unknown fields; the schema is closed '
                     '(see docs/integrations/ROUTE-PROFILES.md)')
    if type(value.get('schema_version')) is not int or value['schema_version'] != 1:
        raise Invalid('registry schema_version must be 1')
    routes = value.get('routes')
    if not isinstance(routes, dict):
        raise Invalid('registry routes must be an object mapping names to declarations')
    for name, route in routes.items():
        check_route(name, route)
    return routes, path, True


def route_view(name, route):
    caps = {field: route[field] for field in CAP_FIELDS if field in route}
    return dict(name=name, adapter=route['adapter'],
                requested_cli_version=route['requested_cli_version'],
                model=route['model'], thinking=route['thinking'],
                receipt_dir=route['receipt_dir'], caps=caps,
                effective_model=UNKNOWN, effective_effort=UNKNOWN,
                remaining_allowance=UNKNOWN)


def cap_text(route):
    if not any(field in route for field in CAP_FIELDS):
        return 'none declared (compile maps omitted caps to the explicit 3.1.1 choice none)'
    parts = []
    for field in CAP_FIELDS:
        if field not in route:
            parts.append(field + ':omitted')
        elif route[field] is None:
            parts.append(field + ':none')
        else:
            parts.append(field + ':' + repr(route[field]))
    return ', '.join(parts)


def print_list(routes, path, present, as_json):
    if as_json:
        print(json.dumps(dict(schema_version=1, command='list', registry=str(path),
                              registry_present=present,
                              routes=[route_view(name, routes[name]) for name in sorted(routes)],
                              note='declared requested settings only; effective model/effort '
                                   'and remaining allowance stay unknown'), ensure_ascii=False))
        return
    print('unio routes: declared route profiles (requested settings only)')
    print('registry: ' + str(path) + ('' if present else ' (absent: empty inventory)'))
    if not routes:
        print('  (no route profiles declared)')
    for name in sorted(routes):
        route = routes[name]
        print('  ' + name + ': adapter=' + route['adapter']
              + ' cli=' + route['requested_cli_version']
              + ' model=' + route['model']
              + ' thinking=' + route['thinking']
              + ' receipt_dir=' + route['receipt_dir']
              + ' caps=' + cap_text(route))
    print('effective model/effort and remaining allowance: Unknown')


def print_show(name, route, as_json):
    if as_json:
        print(json.dumps(dict(schema_version=1, command='show',
                              route=route_view(name, route),
                              note='declared requested settings only; effective model/effort '
                                   'and remaining allowance stay unknown'), ensure_ascii=False))
        return
    print('route: ' + name)
    print('adapter: ' + route['adapter'] + ' (requested)')
    print('requested_cli_version: ' + route['requested_cli_version'])
    print('model: ' + route['model'] + ' (requested)')
    print('thinking: ' + route['thinking'] + ' (requested; catalog declaration, '
          'not a proven native per-run effort control)')
    print('receipt_dir: ' + route['receipt_dir'] + ' (declared existing private parent; '
          'compile checks it read-only and never creates it)')
    for field in CAP_FIELDS:
        if field not in route:
            print(field + ': omitted (compile maps it to the explicit 3.1.1 choice none)')
        elif route[field] is None:
            print(field + ': none (omitted native cap; the CLI default applies and stays Unknown)')
        else:
            print(field + ': ' + repr(route[field]) + ' (requested)')
    print('effective model: Unknown')
    print('effective effort: Unknown')
    print('remaining allowance: Unknown')


def check_receipt_parent(receipt_dir):
    """Read-only check of the declared existing private parent; never created."""
    try:
        info = os.lstat(receipt_dir)
    except FileNotFoundError:
        raise Invalid('receipt_dir does not exist; create the private receipt parent '
                     'explicitly (for example mkdir -m 700) before compiling: ' + receipt_dir)
    except OSError:
        raise Invalid('receipt_dir is unreadable: ' + receipt_dir)
    if not stat.S_ISDIR(info.st_mode):
        raise Invalid('receipt_dir is not a directory: ' + receipt_dir)
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise Invalid('receipt_dir must be an owner-only private directory '
                     '(like the adapter requires, for example 0700): ' + receipt_dir)


def load_adapter(conf_dir):
    """Load only the trusted packaged sibling adapter, never a profile path."""
    path = Path(conf_dir).joinpath(*ADAPTER_RELATIVE)
    try:
        data = read_regular(path, ADAPTER_BYTES)
    except FileNotFoundError:
        raise Invalid('the packaged vibe adapter is not installed under '
                     + str(path) + '; run the installer to package it, or keep '
                     'the route as a legacy agents.conf line')
    except OSError:
        raise Invalid('the packaged vibe adapter is unreadable; reinstall it')
    except Invalid:
        raise Invalid('the packaged vibe adapter is not a regular readable file; reinstall it')
    module = types.ModuleType('unio_route_vibe_worker')
    module.__file__ = str(path)
    exec(compile(data.decode('utf-8'), str(path), 'exec'), module.__dict__)
    for attr in ('build_parser', 'check_bounds', 'CLI_VERSIONS'):
        if not hasattr(module, attr):
            raise Invalid('the packaged vibe adapter is missing its parser contract; reinstall it')
    return module, path


def format_cap(value):
    if isinstance(value, float) and value.is_integer() and abs(value) < 1e16:
        return repr(value)
    return str(value)


def compile_route(conf_dir, name):
    routes, _path, _present = load_registry(conf_dir)
    if name not in routes:
        raise Invalid("unknown route (requested name not echoed); use 'unio routes' "
                     "to list declared profiles")
    route = routes[name]
    check_receipt_parent(route['receipt_dir'])
    adapter, adapter_path = load_adapter(conf_dir)
    cli_version = route['requested_cli_version']
    if route['model'] not in adapter.CLI_VERSIONS[cli_version]['models']:
        raise Invalid('unsupported model for the Vibe ' + cli_version + ' path (supported: '
                     + ', '.join(adapter.CLI_VERSIONS[cli_version]['models']) + ')')
    argv = ['python3', '-I', '-S', '-B', str(adapter_path),
            '--model', route['model'], '--thinking', route['thinking'],
            '--receipt-dir', route['receipt_dir']]
    for field in CAP_FIELDS:
        value = route.get(field)
        argv.extend([CAP_FLAGS[field], 'none' if value is None else format_cap(value)])
    # The trusted adapter parser and bound checks are authoritative: the
    # printed line is exactly what they accept, with no duplicated maxima.
    captured = io.StringIO()
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(captured):
            args = adapter.build_parser().parse_args(argv[5:])
    except SystemExit:
        raise Invalid('the trusted adapter rejected the compiled arguments; check the '
                     'declared model/thinking/caps against the adapter bounds')
    problems = adapter.check_bounds(args, cli_version)
    if problems:
        raise Invalid('; '.join(problems) + '; edit the route profile and retry')
    print(name + '=' + shlex.join(argv))
    print('unio routes: read-only compile; review the line and add it to agents.conf '
          'yourself (nothing was written, executed or verified)', file=sys.stderr)
    return 0


def main(argv):
    if len(argv) < 2:
        print(USAGE, file=sys.stderr)
        return 2
    conf_dir, action, rest = argv[0], argv[1], argv[2:]
    try:
        if action == 'list':
            if rest not in ([], ['--json']):
                raise Invalid(USAGE)
            routes, path, present = load_registry(conf_dir)
            print_list(routes, path, present, rest == ['--json'])
            return 0
        if action == 'show':
            if len(rest) not in (1, 2) or not rest[0] or (len(rest) == 2 and rest[1] != '--json'):
                raise Invalid(USAGE)
            check_requested_name(rest[0])
            name = rest[0]
            routes, _path, _present = load_registry(conf_dir)
            if name not in routes:
                raise Invalid("unknown route (requested name not echoed); use 'unio routes' "
                             "to list declared profiles")
            print_show(name, routes[name], len(rest) == 2)
            return 0
        if action == 'compile':
            if len(rest) != 1 or not rest[0]:
                raise Invalid(USAGE)
            check_requested_name(rest[0])
            return compile_route(conf_dir, rest[0])
        raise Invalid(USAGE)
    except Invalid as error:
        print('unio routes: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
