#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Bounded, read-only capacity observations. No observation reserves space."""
import base64
import datetime
import json
import os
import platform
import re
import selectors
import shutil
import signal
import subprocess
import time

GIB = 1024 ** 3
LIMIT = 4096
TIMEOUT = 4.5
# All registry strings remain data. Never interpolate them into PowerShell code.
POWERSHELL = r'''
$ErrorActionPreference = 'Stop'
try {
  $request = [Console]::In.ReadLine() | ConvertFrom-Json
  $matches = @(Get-ChildItem -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Lxss' | ForEach-Object { Get-ItemProperty -LiteralPath $_.PSPath } | Where-Object { $_.DistributionName -ceq $request.distro })
  if ($matches.Count -ne 1) { throw 'mapping' }
  $entry = $matches[0]
  if ($entry.Version -ne 2) { throw 'version' }
  $base = [Environment]::ExpandEnvironmentVariables([string]$entry.BasePath)
  $name = 'ext4.vhdx'
  if ($entry.VhdFileName) { $name = [string]$entry.VhdFileName }
  if ($name -notmatch '^[^\\/:]+\.vhdx$') { throw 'filename' }
  $file = Join-Path -Path $base -ChildPath $name
  if ($file.StartsWith('\\?\')) { $file = $file.Substring(4) }
  if ($file -notmatch '^[A-Za-z]:\\') { throw 'path' }
  $item = Get-Item -LiteralPath $file -Force
  if ($item.PSIsContainer -or $item.Length -le 0 -or $item.Extension -ine '.vhdx') { throw 'file' }
  $volumes = @(Get-Volume -FilePath $item.FullName)
  if ($volumes.Count -ne 1 -or -not $volumes[0].DriveLetter) { throw 'volume' }
  $v = $volumes[0]
  @{ verified = $true; volume = ([string]$v.DriveLetter + ':\'); available_bytes = $v.SizeRemaining } | ConvertTo-Json -Compress
} catch { '{"unknown":true}' }
'''


def thresholds(env=None):
    env = os.environ if env is None else env
    result = []
    for name, default in (('UNIO_DISK_MIN_FREE_BYTES', 2 * GIB),
                          ('UNIO_DISK_WARN_FREE_BYTES', 10 * GIB)):
        value = env.get(name, str(default))
        if not re.fullmatch(r'[0-9]{1,16}', value) or not 1024**2 <= int(value) <= 1024**5:
            raise ValueError(name + ' must be a decimal integer from 1 MiB to 1 PiB')
        result.append(int(value))
    if result[1] < result[0]:
        raise ValueError('UNIO_DISK_WARN_FREE_BYTES must be >= UNIO_DISK_MIN_FREE_BYTES')
    return dict(min_free_bytes=result[0], warn_free_bytes=result[1])


def unknown(kind, reason):
    return dict(status='unknown', kind=kind, volume=None, available_bytes=None, reason=reason)


def bounded_probe(argv, payload, timeout=TIMEOUT):
    """Bound both output and wall time, including descendants retaining pipes."""
    start = time.monotonic()
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, start_new_session=True)
    data = bytearray()
    try:
        proc.stdin.write(payload)
        proc.stdin.close()
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            while True:
                remaining = timeout - (time.monotonic() - start)
                if remaining <= 0:
                    raise ValueError('host probe timed out')
                if not selector.select(remaining):
                    raise ValueError('host probe timed out')
                chunk = os.read(proc.stdout.fileno(), LIMIT + 1 - len(data))
                if not chunk:
                    break
                data.extend(chunk)
                if len(data) > LIMIT:
                    raise ValueError('host probe output exceeded bound')
        remaining = timeout - (time.monotonic() - start)
        if remaining <= 0:
            raise ValueError('host probe timed out')
        if proc.wait(timeout=remaining) != 0:
            raise ValueError('host probe failed')
        return bytes(data).decode('utf-8-sig')
    except subprocess.TimeoutExpired:
        raise ValueError('host probe timed out') from None
    finally:
        # A failed/oversized probe may leave descendants holding the pipe.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.wait()
        proc.stdout.close()


def windows_metadata(text, kind='wsl-host'):
    """Validate the fixed observer's narrow response; never show raw metadata."""
    if len(text.encode('utf-8')) > LIMIT:
        return unknown(kind, 'host probe output exceeded bound')
    try:
        doc = json.loads(text)
        volume = doc.get('volume')
        free = doc.get('available_bytes')
        if (doc.get('verified') is not True or not isinstance(volume, str)
                or not re.fullmatch(r'[A-Za-z]:\\', volume)
                or type(free) is not int or not 0 <= free <= 2**63 - 1):
            raise ValueError()
        return dict(status='known', kind=kind, volume=volume.upper(),
                    available_bytes=free, reason=None)
    except (ValueError, TypeError, AttributeError):
        return unknown(kind, 'distro backing file/volume mapping unavailable or ambiguous')


def wsl_host():
    distro = os.environ.get('WSL_DISTRO_NAME', '')
    if not distro or len(distro) > 256 or any(ord(c) < 32 for c in distro):
        return unknown('wsl-host', 'current distro identity unavailable')
    executable = shutil.which('powershell.exe')
    if not executable:
        return unknown('wsl-host', 'Windows interop unavailable')
    encoded = base64.b64encode(POWERSHELL.encode('utf-16le')).decode('ascii')
    try:
        output = bounded_probe([executable, '-NoLogo', '-NoProfile', '-NonInteractive',
                                '-EncodedCommand', encoded],
                               (json.dumps(dict(distro=distro), ensure_ascii=True) + '\n').encode())
        return windows_metadata(output)
    except ValueError as exc:
        return unknown('wsl-host', str(exc))
    except OSError:
        return unknown('wsl-host', 'Windows interop failed')


FILESYSTEM_PROBE = r'''import json, os, sys
path = json.loads(sys.stdin.readline())
actual = os.path.abspath(path)
while not os.path.exists(actual):
    parent = os.path.dirname(actual)
    if parent == actual:
        raise OSError('no existing ancestor')
    actual = parent
info = os.statvfs(actual)
print(json.dumps(dict(available_bytes=info.f_bavail * info.f_frsize,
                      device=os.stat(actual).st_dev)))
'''


def filesystem(path, kind):
    # Isolate potentially stalled filesystem syscalls behind the same bounded
    # pipe reader. The child has no write operation or environment dump.
    import sys
    try:
        payload = (json.dumps(os.path.abspath(path), ensure_ascii=True) + '\n').encode()
        if len(payload) > LIMIT:
            return unknown(kind, 'filesystem path exceeds observation bound')
        doc = json.loads(bounded_probe([sys.executable, '-I', '-S', '-B', '-c', FILESYSTEM_PROBE],
                                       payload, timeout=0.5))
        free, device = doc['available_bytes'], doc['device']
        if type(free) is not int or free < 0 or type(device) is not int or device < 0:
            raise ValueError()
        return dict(status='known', kind=kind, volume='device:' + str(device),
                    available_bytes=free, reason=None)
    except (OSError, ValueError, KeyError, TypeError):
        return unknown(kind, 'filesystem capacity unavailable or observation timed out')


def temp_directory():
    # tempfile.gettempdir() performs writable probes. This command is read-only.
    for path in (os.environ.get('TMPDIR'), os.environ.get('TEMP'), os.environ.get('TMP'),
                 '/tmp', '/var/tmp', '/usr/tmp', os.getcwd()):
        if path and os.path.isdir(path):
            return path
    return '/tmp'


def observe(root, worker=''):
    configured = thresholds()
    measurements = [filesystem(os.path.join(root, 'wt', worker) if worker else root, 'project'),
                    filesystem(os.path.join(root, 'coord'), 'coordination'),
                    filesystem(temp_directory(), 'temp')]
    # WSL1 also yields Unknown, rather than calling virtual ext4 host capacity.
    if 'microsoft' in platform.release().lower() or os.environ.get('WSL_DISTRO_NAME'):
        measurements.append(wsl_host())
    known = [m['available_bytes'] for m in measurements if m['status'] == 'known']
    if any(n < configured['min_free_bytes'] for n in known):
        overall = 'critical'
    elif any(n < configured['warn_free_bytes'] for n in known):
        overall = 'warning'
    elif any(m['status'] == 'unknown' for m in measurements):
        overall = 'unknown'
    else:
        overall = 'adequate'
    return dict(schema_version=1, observed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                measurements=measurements, thresholds=configured, overall=overall)


def describe(doc):
    return '\n'.join('disk ' + doc['observed_at'] + ' ' + m['kind'] + ' '
                     + (m['volume'] or 'Unknown') + ' free_bytes='
                     + (str(m['available_bytes']) if m['status'] == 'known' else 'Unknown')
                     + (' reason=' + m['reason'] if m['reason'] else '')
                     for m in doc['measurements'])


def admission(root, worker=''):
    doc = observe(root, worker)
    if doc['overall'] == 'critical':
        raise ValueError('storage refused: critical disk space\n' + describe(doc))
    # Concise observations are visible even when adequate; Unknown warns.
    import sys
    print(('warning: ' if any(m['status'] == 'unknown' for m in doc['measurements']) or doc['overall'] == 'warning' else '')
          + 'disk observation: ' + doc['overall'] + '\n' + describe(doc), file=sys.stderr)


def command(root, mode='text'):
    import sys
    if mode not in ('text', '--json'):
        raise ValueError('usage: unio disk [--json]')
    doc = observe(root)
    print(json.dumps(doc, sort_keys=True) if mode == '--json' else
          'disk observation: ' + doc['overall'] + '\n' + describe(doc))
    if doc['overall'] == 'critical':
        sys.exit(2)
