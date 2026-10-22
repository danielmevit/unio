#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Required delivery artifact contract.

An optional '## Required artifacts' section in a task file declares an explicit
delivery contract: a bounded set of text artifacts that must be present for
the delivery to be considered complete.

This is an opt-in enhancement that preserves existing behavior for tasks
without this declaration. The contract is strictly additive: it does not modify
Source exit semantics, provider outcomes, or acceptance authority.
"""
import hashlib
import os
import re
import stat
from pathlib import Path

# Bounds
MAX_ARTIFACT_COUNT = 32
MAX_ARTIFACT_SIZE = 262144  # 256 KiB
MAX_NAME_LENGTH = 128
LIMIT = 1048576  # 1 MiB for task file reading

# Patterns
ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,' + str(MAX_NAME_LENGTH - 1) + r'}')
HEX = re.compile(r'[a-f0-9]{64}')
RUN = re.compile(r'[a-f0-9]{32}')
STAMP = re.compile(r'\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:Z|[+-]\d\d:\d\d)')

# Safe relative path: alphanumeric, hyphen, underscore, dot, forward slash
# Must not start or end with slash, no consecutive slashes, no ..
SAFE_PATH = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$')


class DeliveryError(ValueError):
    """Actionable refusal for malformed required delivery metadata."""


def _shown(line):
    """Show a line safely for error messages."""
    text = ''.join(c if c >= ' ' or c in '\t' else '?' for c in line)
    return text[:80] + ('…' if len(text) > 80 else '')


def parse(text):
    """Parse a task file and return a list of required artifact names, or None.

    Returns None if no '## Required artifacts' section is present (legacy).
    Raises DeliveryError for malformed declarations or empty section.

    Rules:
    - Section header must be exactly '## Required artifacts'
    - One artifact per line
    - Empty lines and lines starting with '#' (comments) are ignored
    - Duplicate names are refused
    - Each name must match safe relative path constraints
    - Maximum MAX_ARTIFACT_COUNT artifacts
    """
    if not isinstance(text, str):
        raise DeliveryError('task text must be a string')
    if '\x00' in text:
        raise DeliveryError('task text contains NUL bytes')

    headers = 0
    artifacts = []
    in_section = False
    fence = None

    for line in text.splitlines():
        stripped = line.strip()

        # Skip fenced code blocks
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if marker and marker[1][0] == fence[0] and len(marker[1]) >= len(fence) and not marker[2].strip():
                fence = None
            continue
        if marker:
            fence = marker[1]
            continue

        # Check for section headers (## Heading)
        if line.startswith('## '):
            if line == '## Required artifacts':
                in_section = True
                headers += 1
            else:
                in_section = False
            continue

        if not in_section:
            continue

        # Skip empty lines and comments
        if not stripped or stripped.startswith('#'):
            continue

        if line != stripped:
            raise DeliveryError('artifact declaration must be one plain portable path per line')

        # Validate artifact name
        validate_artifact_path(stripped)

        if stripped in artifacts:
            raise DeliveryError("duplicate artifact name: " + _shown(stripped))

        artifacts.append(stripped)

    if headers > 1:
        raise DeliveryError(
            "malformed '## Required artifacts' section: duplicate '## Required artifacts' section (" + str(headers) +
            " found); a task declares at most one required artifacts section")

    if headers == 0:
        return None  # Legacy: no declaration

    if not artifacts:
        raise DeliveryError(
            "malformed '## Required artifacts' section: section declares no artifacts; "
            "list at least one artifact or omit the section")

    if not artifacts or len(artifacts) > MAX_ARTIFACT_COUNT:
        raise DeliveryError(
            "too many artifacts (" + str(len(artifacts)) +
            "); count exceeds bound of " + str(MAX_ARTIFACT_COUNT))

    return validate_artifacts(artifacts)


def read_task(path):
    """Bounded owned regular UTF-8 task, with no symlink ancestors."""
    return read_artifact(path, LIMIT).decode('utf-8')


def validate_artifact_path(name):
    """Validate an artifact name as a safe relative path."""
    if not isinstance(name, str):
        raise DeliveryError('artifact name must be a string')
    if not name or len(name) > MAX_NAME_LENGTH:
        raise DeliveryError("invalid artifact name: " + _shown(name) + "; length out of bounds (1.." + str(MAX_NAME_LENGTH) + ")")
    if '..' in name or name.startswith('/') or name.endswith('/') or '//' in name:
        raise DeliveryError("artifact name contains path traversal or invalid slashes: " + _shown(name))
    for part in name.split('/'):
        if part.endswith('.') or part.split('.')[0].casefold() in {'con','prn','aux','nul',*(f'com{i}' for i in range(1,10)),*(f'lpt{i}' for i in range(1,10))}:
            raise DeliveryError('nonportable artifact name: ' + name)
        if not part or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', part) or '..' in part or part.startswith('.'):
            raise DeliveryError("invalid artifact name: " + _shown(name) + "; must be a safe relative path")
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', part):
            raise DeliveryError("invalid artifact name: " + _shown(name))
    if name.split('/')[0].casefold() in ('binding.json', 'prompt.md'):
        raise DeliveryError('reserved engine metadata name: ' + name)
    return name


def validate_artifacts(artifacts):
    """Validate a list of artifact names.

    Returns the validated list or raises DeliveryError.
    """
    if artifacts is None:
        return None

    if not isinstance(artifacts, list):
        raise DeliveryError('artifacts must be a list')

    if not artifacts or len(artifacts) > MAX_ARTIFACT_COUNT:
        raise DeliveryError(
            "too many artifacts (" + str(len(artifacts)) +
            "); count exceeds bound of " + str(MAX_ARTIFACT_COUNT))

    seen = set()
    validated = []
    for name in artifacts:
        name = validate_artifact_path(name)
        if name in seen:
            raise DeliveryError("duplicate artifact name: " + _shown(name))
        if any(name.casefold() == v.casefold() or name.casefold().startswith(v.casefold() + '/') or v.casefold().startswith(name.casefold() + '/') for v in seen):
            raise DeliveryError('artifact path collision: ' + name)
        seen.add(name)
        validated.append(name)

    return validated


def directory_fd(path):
    """Walk every component without following symlinks, including ancestors."""
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in os.path.abspath(path).split('/')[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        return fd
    except BaseException:
        os.close(fd)
        raise


def identity(info):
    return [info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns]


def read_evidence(path, limit=MAX_ARTIFACT_SIZE):
    path = Path(path)
    parent = directory_fd(path.parent)
    try:
        fd = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.getuid() or not 0 < info.st_size <= limit):
                raise DeliveryError('evidence must be bounded, owned, singly-linked regular text')
            data = b''
            while len(data) <= limit:
                chunk = os.read(fd, limit + 1 - len(data))
                if not chunk:
                    break
                data += chunk
            after = os.fstat(fd)
            named = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            # Reopen the full path as well: an ancestor may have been replaced.
            again = directory_fd(path.parent)
            try:
                current = os.stat(path.name, dir_fd=again, follow_symlinks=False)
            finally:
                os.close(again)
            if any(identity(x) != identity(info) for x in (after, named, current)) or len(data) != info.st_size:
                raise DeliveryError('evidence changed during read')
            data.decode('utf-8')
            if b'\0' in data:
                raise DeliveryError('evidence contains NUL')
            return data, identity(info)
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def read_artifact(path, limit=MAX_ARTIFACT_SIZE):
    try:
        return read_evidence(path, limit)[0]
    except UnicodeError:
        raise DeliveryError('artifact must be valid UTF-8') from None


def write_metadata(directory, name, data):
    parent = directory_fd(directory)
    try:
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_NONBLOCK, 0o400, dir_fd=parent)
        try:
            view = memoryview(data)
            while view:
                view = view[os.write(fd, view):]
        finally:
            os.close(fd)
    finally:
        os.close(parent)


def validate_artifact(path, expected_hash, limit=MAX_ARTIFACT_SIZE):
    """Validate an artifact file against expected hash.

    Returns True if valid, False otherwise.
    Raises DeliveryError if the file is unsafe.
    """
    try:
        data = read_artifact(path, limit)
        actual_hash = hashlib.sha256(data).hexdigest()
        return actual_hash == expected_hash
    except (OSError, DeliveryError):
        return False


def create_binding(task, worker, run, task_sha256, command_sha256, prompt_sha256,
                   route, started_at, artifacts=None):
    """Create a delivery binding dictionary.

    All string values are validated. Artifacts is optional list of artifact names.
    Returns a dictionary suitable for JSON serialization.
    """
    if not ID.fullmatch(task):
        raise DeliveryError('invalid task identifier')
    if not ID.fullmatch(worker):
        raise DeliveryError('invalid worker identifier')
    if not RUN.fullmatch(run):
        raise DeliveryError('invalid run identifier')
    if not all(HEX.fullmatch(v) for v in (task_sha256, command_sha256, prompt_sha256)):
        raise DeliveryError('invalid hash value')
    if not isinstance(route, str) or route not in ('vibe', 'antigravity', 'copilot', 'perplexity', 'unsupported'):
        raise DeliveryError('invalid route')
    if not STAMP.fullmatch(started_at):
        raise DeliveryError('invalid started_at timestamp')

    validated_artifacts = validate_artifacts(artifacts)

    binding = {
        'schema_version': 1,
        'task': task,
        'worker': worker,
        'run': run,
        'task_sha256': task_sha256,
        'command_sha256': command_sha256,
        'prompt_sha256': prompt_sha256,
        'route': route,
        'started_at': started_at,
    }

    if validated_artifacts is not None:
        binding['artifacts'] = validated_artifacts

    return binding


def validate_binding(binding, require_artifacts=False):
    """Validate a delivery binding dictionary.

    If require_artifacts is True, the binding must have an 'artifacts' key.
    Returns True if valid, False otherwise.
    """
    if not isinstance(binding, dict):
        return False

    required_keys = {'schema_version', 'task', 'worker', 'run',
                     'task_sha256', 'command_sha256', 'prompt_sha256',
                     'route', 'started_at'}

    if not required_keys <= set(binding) or not set(binding) <= required_keys | {'artifacts'}:
        return False

    if type(binding.get('schema_version')) is not int or binding.get('schema_version') != 1:
        return False

    if not all(isinstance(binding.get(k), str) for k in required_keys - {'schema_version'}):
        return False

    if not all(ID.fullmatch(binding.get(k)) for k in ('task', 'worker')):
        return False

    if not RUN.fullmatch(binding.get('run')):
        return False

    if not all(HEX.fullmatch(binding.get(k)) for k in ('task_sha256', 'command_sha256', 'prompt_sha256')):
        return False

    if binding.get('route') not in ('vibe', 'antigravity', 'copilot', 'perplexity', 'unsupported'):
        return False

    if not STAMP.fullmatch(binding.get('started_at')):
        return False

    if require_artifacts or 'artifacts' in binding:
        if 'artifacts' not in binding:
            return False
        if not isinstance(binding['artifacts'], list):
            return False
        try:
            validate_artifacts(binding['artifacts'])
        except DeliveryError:
            return False

    return True


def main(argv):
    """Command-line interface for testing."""
    import sys

    if len(argv) != 2 or argv[0] != 'parse':
        print('usage: required-delivery.py parse <task-file>', file=sys.stderr)
        return 2

    try:
        text = read_task(argv[1])
        artifacts = parse(text)
        if artifacts is None:
            print('legacy')
        else:
            print('artifacts: ' + ', '.join(artifacts))
        return 0
    except (DeliveryError, OSError) as error:
        print('required delivery: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
