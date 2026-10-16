#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Finite owner-granted scheduling over the existing planner and dispatcher."""
import argparse
import contextlib
import datetime
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import stat
import sys
import time

MAX_GRANT = 128 * 1024
MAX_STATE = 2 * 1024 * 1024
MAX_BATCHES = 128
FIELDS = {'schema_version', 'project', 'inventory', 'inventory_sha256', 'expires_at',
          'max_launches', 'poll_seconds', 'run_seconds', 'jobs'}
JOB_FIELDS = {'job_id', 'grant', 'grant_sha256', 'approval_key', 'reservation_key'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def load(name):
    path = Path(__file__).resolve().with_name(name + '.py')
    spec = importlib.util.spec_from_file_location(name.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def expiry(value):
    require(isinstance(value, str) and len(value) <= 64, 'invalid expiry')
    date = datetime.datetime.fromisoformat(value)
    require(date.tzinfo is not None, 'expiry needs explicit timezone')
    return date


def physical(value, directory=False):
    require(isinstance(value, str) and 0 < len(value) <= 4096
            and os.path.isabs(value) and os.path.normpath(value) == value
            and os.path.realpath(value) == value
            and not any(ord(c) < 32 or ord(c) == 127 for c in value), 'physical path required')
    mode = os.lstat(value).st_mode
    require(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode), 'unsupported path')
    return Path(value)


def read_json(planner, path, limit):
    raw, _ = planner.read_regular(path, limit)
    value = planner.parse_strict_json(raw)
    require(value is not None, 'invalid strict JSON')
    return value, raw


def read_grant(planner, path, creation=True):
    grant, _ = read_json(planner, physical(str(path)), MAX_GRANT)
    require(set(grant) == FIELDS and type(grant['schema_version']) is int
            and grant['schema_version'] == 1, 'invalid grant fields')
    physical(grant['project'], True)
    for name in ('coord', 'repo', 'wt'):
        physical(str(Path(grant['project']) / name), True)
    physical(grant['inventory'])
    require(isinstance(grant['inventory_sha256'], str)
            and planner.HEX64.fullmatch(grant['inventory_sha256']), 'invalid inventory hash')
    for name, high in (('max_launches', 128), ('poll_seconds', 60), ('run_seconds', 7200)):
        require(type(grant[name]) is int and 1 <= grant[name] <= high, 'invalid ' + name)
    date = expiry(grant['expires_at'])
    if creation:
        require(now() < date <= now() + datetime.timedelta(hours=24), 'expiry outside creation window')
    require(isinstance(grant['jobs'], list) and 1 <= len(grant['jobs']) <= 128, 'invalid jobs')
    jobs, reservations = set(), set()
    for job in grant['jobs']:
        require(isinstance(job, dict) and set(job) == JOB_FIELDS, 'invalid job fields')
        for name in ('job_id', 'approval_key', 'reservation_key'):
            require(isinstance(job[name], str) and planner.HEX32.fullmatch(job[name]), 'invalid job key')
        require(isinstance(job['grant_sha256'], str) and planner.HEX64.fullmatch(job['grant_sha256']),
                'invalid dispatch grant hash')
        physical(job['grant'])
        require(job['job_id'] not in jobs and job['reservation_key'] not in reservations, 'duplicate job or reservation')
        jobs.add(job['job_id'])
        reservations.add(job['reservation_key'])
    return grant
