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
    Returns an empty list if the section exists but declares no artifacts.
    Raises DeliveryError for malformed declarations.

    Rules:
    - Section header must be exactly '## Required artifacts'
    - One artifact per line
    - Empty lines and lines starting with '#' are ignored
    - Duplicate names are refused
    - Each name must match SAFE_PATH pattern
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

        # Check for section headers
        heading = re.match(r'^ {0,3}(#{1,6})(?:[ \t]+(.*)|$)', line)
        if heading:
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

        # Validate artifact name
        if not SAFE_PATH.fullmatch(stripped):
            raise DeliveryError(
                "invalid artifact name: " + _shown(stripped) +
                "; must be a safe relative path (alphanumeric, hyphen, underscore, dot, slash)")

        if stripped in artifacts:
            raise DeliveryError("duplicate artifact name: " + _shown(stripped))

        artifacts.append(stripped)

    if headers > 1:
        raise DeliveryError(
            "duplicate '## Required artifacts' section (" + str(headers) +
            " found); a task declares at most one required artifacts section")

    if headers == 0:
        return None  # Legacy: no declaration

    if len(artifacts) > MAX_ARTIFACT_COUNT:
        raise DeliveryError(
            "too many artifacts (" + str(len(artifacts)) +
            "); maximum is " + str(MAX_ARTIFACT_COUNT))

    return artifacts


def read_task(path):
    """Bounded regular UTF-8 read; no symlink, FIFO or oversized task."""
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= LIMIT:
            raise DeliveryError('task file must be a regular file of at most 1 MiB')
        data = b''
        while len(data) <= LIMIT:
            chunk = os.read(fd, LIMIT + 1 - len(data))
            if not chunk:
                break
            data += chunk
    finally:
        os.close(fd)
    if len(data) > LIMIT:
        raise DeliveryError('task file exceeds the 1 MiB bound')
    try:
        return data.decode('utf-8')
    except UnicodeError:
        raise DeliveryError('task file must be valid UTF-8') from None


def validate_artifact_path(name):
    """Validate an artifact name as a safe relative path."""
    if not isinstance(name, str):
        raise DeliveryError('artifact name must be a string')
    if not name:
        raise DeliveryError('artifact name cannot be empty')
    if not SAFE_PATH.fullmatch(name):
        raise DeliveryError(
            "invalid artifact name: " + _shown(name) +
            "; must be a safe relative path")
    # Check for path traversal
    if '..' in name or name.startswith('/') or name.endswith('/'):
        raise DeliveryError("artifact name contains path traversal: " + _shown(name))
    return name


def validate_artifacts(artifacts):
    """Validate a list of artifact names.

    Returns the validated list or raises DeliveryError.
    """
    if artifacts is None:
        return None

    if not isinstance(artifacts, list):
        raise DeliveryError('artifacts must be a list')

    if len(artifacts) > MAX_ARTIFACT_COUNT:
        raise DeliveryError(
            "too many artifacts (" + str(len(artifacts)) +
            "); maximum is " + str(MAX_ARTIFACT_COUNT))

    seen = set()
    validated = []
    for name in artifacts:
        name = validate_artifact_path(name)
        if name in seen:
            raise DeliveryError("duplicate artifact name: " + _shown(name))
        seen.add(name)
        validated.append(name)

    return validated


def read_artifact(path, limit=MAX_ARTIFACT_SIZE):
    """Read and validate an artifact file.

    Returns the file contents as bytes.
    Raises DeliveryError if the file is unsafe or invalid.
    """
    path = Path(path)

    # Validate path is within delivery directory (no symlink traversal)
    fd = os.open(str(path.parent), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        # Open the file with O_NOFOLLOW and O_NONBLOCK
        f = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(f)
            # Must be a regular file
            if not stat.S_ISREG(info.st_mode):
                raise DeliveryError('artifact must be a regular file')
            # Must have exactly one hard link
            if info.st_nlink != 1:
                raise DeliveryError('artifact must have exactly one hard link')
            # Must be owned by current user
            if info.st_uid != os.getuid():
                raise DeliveryError('artifact must be owned by current user')
            # Must have mode 0600
            if info.st_mode & 0o777 != 0o600:
                raise DeliveryError('artifact must have mode 0600')
            # Size must be within bounds
            if not 0 < info.st_size <= limit:
                raise DeliveryError(
                    'artifact size ' + str(info.st_size) +
                    ' out of bounds (1..' + str(limit) + ')')

            # Read the file
            data = os.read(f, limit + 1)
            if len(data) > limit:
                raise DeliveryError('artifact exceeds size limit')

            # Check that file didn't change during read
            after = os.fstat(f)
            if (info.st_size, info.st_mtime_ns, info.st_ctime_ns) != \
               (after.st_size, after.st_mtime_ns, after.st_ctime_ns):
                raise DeliveryError('artifact changed while reading')

            return data
        finally:
            os.close(f)
    finally:
        os.close(fd)


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

    if not required_keys <= set(binding):
        return False

    if binding.get('schema_version') != 1:
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

    if require_artifacts:
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
