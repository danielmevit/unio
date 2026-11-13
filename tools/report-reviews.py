#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Observational report-review links (docs/development/contracts/0530-REVIEW-REPORTS.md).

Smallest V1: prepare an exact, bounded native material packet for a
separately assigned report-only reviewer; attach only a currently verified
successful report-only Source whose native-frozen predispatch prompt binds
the packet ID and manifest digest; and show the attachments through a
separate --reports observation. Attaching and viewing report reviews has
ZERO effect on canonical native review receipts, findings, result
readiness, owner acceptance or any approval state.

This module is embedded into the standalone installer by
tools/embed-report-reviews.py and exec'd into a namespace pre-populated
with the engine's existing validators (fail, safe, snapshot, load,
report_evidence, delivery_check, material_bytes_v2, review_json,
findings_block_schema, delivery_ns, ...). It deliberately contains no
second validator engine: every identity, revision, material and delivery
fact is established by those existing native helpers.

Importable standalone: module-level engine names are resolved only inside
functions, so importing this file without the engine namespace is safe for
inspection; calling the entry points requires the embedded namespace.
"""
import hashlib
import json
import os
import re
import shutil
import uuid

SCHEMA_VERSION = 1
MATERIAL_PROTOCOL = 2
MATERIAL_LIMIT = 300000
PACKET_FILES_LIMIT = 262144
PACKET_PATHS_MAX = 16
PACKETS_MAX = 256
REPORT_REVIEWS_MAX = 256
RECEIPT_LIMIT = 262144
PROMPT_LIMIT = 1048576
REPORT_REVIEW_ID_HEX = 16
DECLARATION_HEADER = '## Review packet'
DECLARATION_FIELDS = {'schema_version', 'id', 'manifest_sha256'}
REQUIRED_SOURCE_ARTIFACTS = ('summary.md', 'verdict.json', 'findings.json')
VERDICTS = ('APPROVE', 'REQUEST-CHANGES')
COVERAGES = ('task_material', 'paths')
SAFE_RELATIVE = re.compile(r'[A-Za-z0-9][A-Za-z0-9._-]*(/[A-Za-z0-9][A-Za-z0-9._-]*)*$')
REPORT_REVIEW_NAME = re.compile(r'([A-Za-z0-9_.-]+)\.report-review\.([0-9a-f]{16})')

MANIFEST_FIELDS = {'schema_version', 'id', 'worker', 'task', 'revision',
                   'material_protocol', 'material_sha256', 'material_bytes',
                   'coverage', 'paths', 'created_at'}
MANIFEST_PATH_FIELDS = {'path', 'sha256', 'bytes', 'identity'}

RECEIPT_FIELDS = {'schema_version', 'kind', 'id', 'target_worker', 'target_task',
                  'target_revision', 'packet_id', 'packet_manifest_sha256',
                  'coverage', 'declared_paths', 'source_worker', 'source_task',
                  'source_run_id', 'source_command_sha256', 'source_prompt_sha256',
                  'source_binding_sha256', 'source_report_sha256', 'source_report_bytes',
                  'source_artifacts', 'verdict', 'findings_count', 'findings_schema',
                  'requested_model', 'effective_model', 'requested_effort',
                  'effective_effort', 'human_acceptance', 'native_readiness_effect',
                  'recorded_at'}

NO_EFFECT_NOTE = ('observational report reviews only: no native-readiness '
                  'or human-acceptance effect')


def _stop_refused(root):
    if os.path.exists(safe(root, 'coord', 'STOP')):
        fail('STOP is active: review-packet and reviews-bind refuse before any '
             'work or publication in this slice; read-only --reports views still work')


def _busy_refused(root, worker, label):
    if observed_lock(root, worker) == 'held':
        fail(label + ' worker is busy: refuse rather than race a live Source')


def _canonical(doc):
    return json.dumps(doc, sort_keys=True, ensure_ascii=True,
                      separators=(',', ':')).encode('utf-8') + b'\n'


def _write_exclusive(directory_fd, name, data):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                 | os.O_NONBLOCK, 0o400, dir_fd=directory_fd)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        os.fsync(fd)
    finally:
        os.close(fd)


def _read_bounded(path, limit):
    data, identity = delivery_ns['read_evidence'](path, limit)
    return data, list(identity)


def parse_declarations(text):
    """Return the list of active Review packet declarations in a task/prompt.

    Refuses duplicate sections, sections without exactly one fenced JSON
    object, malformed or non-closed fences. Fenced examples elsewhere in
    the document are ignored, matching the native task parsers.
    """
    lines = text.replace('\r\n', '\n').split('\n')
    sections = []
    current = None
    fence = None
    collecting = None
    for line in lines:
        marker = re.match(r'^ {0,3}(`{3,}|~{3,})(.*)$', line)
        if fence:
            if collecting is not None:
                if line == '```':
                    doc = review_json('\n'.join(collecting))
                    if (not isinstance(doc, dict) or set(doc) != DECLARATION_FIELDS
                            or doc['schema_version'] != 1
                            or not isinstance(doc['id'], str)
                            or not re.fullmatch('[0-9a-f]{32}', doc['id'])
                            or not isinstance(doc['manifest_sha256'], str)
                            or not re.fullmatch('[0-9a-f]{64}', doc['manifest_sha256'])):
                        fail('Review packet declaration must be exactly '
                             '{"schema_version":1,"id":"<32hex>","manifest_sha256":"<64hex>"}')
                    current['declaration'] = doc
                    collecting = None
                    fence = None
                    continue
                collecting.append(line)
                continue
            if (marker and fence[0] == marker[1][0] and len(marker[1]) >= len(fence)
                    and not marker[2].strip()):
                fence = None
            continue
        if marker:
            if current is not None and marker[1] == '```' and marker[2].strip() in ('', 'json'):
                if 'declaration' in current:
                    fail('Review packet section declares more than one fenced JSON object')
                fence = marker[1]
                collecting = []
                continue
            fence = marker[1]
            continue
        if line.startswith('## '):
            if current is not None and 'declaration' not in current:
                fail('Review packet section has no fenced JSON declaration')
            if line == DECLARATION_HEADER:
                current = {}
                sections.append(current)
            else:
                current = None
    if collecting is not None:
        fail('Review packet declaration fence is not closed')
    if current is not None and 'declaration' not in current:
        fail('Review packet section has no fenced JSON declaration')
    return [s['declaration'] for s in sections]


def _single_declaration(text, label):
    declarations = parse_declarations(text)
    if not declarations:
        fail('missing original Review packet binding in ' + label)
    if len(declarations) > 1:
        fail('duplicate Review packet sections in ' + label)
    return declarations[0]


def _validate_manifest(doc, packet_id):
    if not isinstance(doc, dict) or set(doc) != MANIFEST_FIELDS:
        fail('invalid review packet manifest schema')
    if (doc['schema_version'] != SCHEMA_VERSION or doc['id'] != packet_id
            or not isinstance(doc['id'], str) or not re.fullmatch('[0-9a-f]{32}', doc['id'])
            or doc['material_protocol'] != MATERIAL_PROTOCOL
            or doc['coverage'] not in COVERAGES
            or not isinstance(doc['material_sha256'], str)
            or not re.fullmatch('[0-9a-f]{64}', doc['material_sha256'])
            or type(doc['material_bytes']) is not int
            or not 0 < doc['material_bytes'] <= MATERIAL_LIMIT):
        fail('invalid review packet manifest identity')
    ident(doc['worker']); ident(doc['task'])
    if not revision(doc['revision']):
        fail('invalid review packet manifest revision')
    if not isinstance(doc['created_at'], str) or len(doc['created_at']) > 64:
        fail('invalid review packet manifest timestamp')
    paths = doc['paths']
    if not isinstance(paths, list) or len(paths) > PACKET_PATHS_MAX:
        fail('invalid review packet manifest paths')
    if doc['coverage'] == 'task_material' and paths:
        fail('task_material packet cannot declare explicit paths')
    if doc['coverage'] == 'paths' and not paths:
        fail('paths packet must declare at least one path')
    seen = set()
    for entry in paths:
        if not isinstance(entry, dict) or set(entry) != MANIFEST_PATH_FIELDS:
            fail('invalid review packet manifest path entry')
        path = entry['path']
        if (not isinstance(path, str) or not SAFE_RELATIVE.fullmatch(path)
                or path in seen):
            fail('invalid review packet manifest path')
        seen.add(path)
        if (not isinstance(entry['sha256'], str)
                or not re.fullmatch('[0-9a-f]{64}', entry['sha256'])
                or type(entry['bytes']) is not int
                or not 0 < entry['bytes'] <= PACKET_FILES_LIMIT
                or not isinstance(entry['identity'], list) or len(entry['identity']) != 5
                or any(type(x) is not int or x < 0 for x in entry['identity'][:3])):
            fail('invalid review packet manifest path evidence')
    return doc


def _packet_directory(root, packet_id):
    if not isinstance(packet_id, str) or not re.fullmatch('[0-9a-f]{32}', packet_id):
        fail('invalid review packet ID')
    return safe(root, 'coord', 'review-packets', packet_id)


def _load_packet(root, declaration):
    """Read and fully verify the declared packet; returns (manifest, directory)."""
    directory = _packet_directory(root, declaration['id'])
    if not os.path.isdir(directory):
        fail('declared review packet is missing: ' + declaration['id'])
    manifest_bytes, _ = _read_bounded(os.path.join(directory, 'manifest.json'), RECEIPT_LIMIT)
    if hashlib.sha256(manifest_bytes).hexdigest() != declaration['manifest_sha256']:
        fail('review packet manifest digest does not match the frozen declaration')
    manifest = _validate_manifest(review_json(manifest_bytes.decode('utf-8')),
                                  declaration['id'])
    material, _ = _read_bounded(os.path.join(directory, 'material.txt'), MATERIAL_LIMIT)
    if (hashlib.sha256(material).hexdigest() != manifest['material_sha256']
            or len(material) != manifest['material_bytes']):
        fail('review packet material bytes do not match the manifest')
    for index, entry in enumerate(manifest['paths']):
        data, identity = _read_bounded(
            os.path.join(directory, 'path-%d.txt' % index), PACKET_FILES_LIMIT)
        if (hashlib.sha256(data).hexdigest() != entry['sha256']
                or len(data) != entry['bytes'] or identity != entry['identity']):
            fail('review packet path bytes do not match the manifest: ' + entry['path'])
    return manifest, directory


def packet_create(root, worker, task, *paths):
    """Prepare a bounded local material packet; no provider call, no slots."""
    ident(worker); ident(task)
    locations(root, worker, task)
    _stop_refused(root)
    _busy_refused(root, worker, 'target')
    if len(paths) > PACKET_PATHS_MAX:
        fail('at most %d explicit paths per packet' % PACKET_PATHS_MAX)
    rev = snapshot(root, worker, task)
    d = load(root, worker, task)
    if (d['validation']['state'] != 'passed'
            or d['validation']['revision'] != rev or d['stale']):
        fail('review packets require a current verify PASS at the live revision')
    material = material_bytes_v2(root, worker, task)
    wt = locations(root, worker, task)[0]
    entries = []
    for path in paths:
        if not isinstance(path, str) or not SAFE_RELATIVE.fullmatch(path):
            fail('explicit packet paths must be safe relative paths without globs: ' + repr(path))
        if any(part in ('', '.', '..') for part in path.split('/')):
            fail('unsafe explicit packet path: ' + path)
        target = safe(wt, *path.split('/'))
        try:
            data, identity = _read_bounded(target, PACKET_FILES_LIMIT)
        except (OSError, ValueError):
            fail('explicit packet path must be a bounded readable text file: ' + path)
        entries.append(dict(path=path, sha256=hashlib.sha256(data).hexdigest(),
                            bytes=len(data), identity=identity))
    coverage = 'paths' if entries else 'task_material'
    packet_id = uuid.uuid4().hex
    manifest = dict(schema_version=SCHEMA_VERSION, id=packet_id, worker=worker, task=task,
                    revision=rev, material_protocol=MATERIAL_PROTOCOL,
                    material_sha256=hashlib.sha256(material).hexdigest(),
                    material_bytes=len(material), coverage=coverage, paths=entries,
                    created_at=stamp())
    manifest_bytes = _canonical(manifest)
    parent = safe(root, 'coord', 'review-packets')
    fd = storage_directory(parent, create=True)
    pending = '.pending-' + packet_id
    published = False
    try:
        try:
            with os.scandir(parent) as scan:
                if sum(1 for _ in scan) >= PACKETS_MAX:
                    fail('review packet bound reached: %d packets' % PACKETS_MAX)
        except OSError:
            fail('cannot observe review packet store')
        try:
            os.mkdir(pending, 0o700, dir_fd=fd)
        except FileExistsError:
            fail('review packet collision; retry the command')
        try:
            _write_exclusive(fd, pending + '/manifest.json', manifest_bytes)
            _write_exclusive(fd, pending + '/material.txt', material)
            for index, entry in enumerate(entries):
                data, _ = _read_bounded(safe(wt, *entry['path'].split('/')),
                                        PACKET_FILES_LIMIT)
                _write_exclusive(fd, pending + '/path-%d.txt' % index, data)
            try:
                os.rename(pending, packet_id, src_dir_fd=fd, dst_dir_fd=fd)
                published = True
            except OSError:
                fail('review packet already published: ' + packet_id)
        finally:
            if not published:
                shutil.rmtree(os.path.join(parent, pending), ignore_errors=True)
    finally:
        os.close(fd)
    declaration = dict(schema_version=SCHEMA_VERSION, id=packet_id,
                       manifest_sha256=hashlib.sha256(manifest_bytes).hexdigest())
    text = (DECLARATION_HEADER + '\n```json\n'
            + json.dumps(declaration, sort_keys=True, separators=(',', ':'))
            + '\n```\n')
    return dict(schema_version=SCHEMA_VERSION, id=packet_id,
                manifest_sha256=declaration['manifest_sha256'], worker=worker,
                task=task, revision=rev, coverage=coverage,
                declared_paths=[e['path'] for e in entries], declaration=text)


def _source_report(root, source_worker, source_task):
    """Verify a current successful report-only Source with complete delivery.

    Returns (result doc, live revision, delivery doc, artifact bytes,
    semantic verdict, findings count). Every fact comes from the existing
    native validators; nothing here upgrades a failed, stale or incomplete
    Source.
    """
    if task_mode(root, source_worker, source_task) != 'report-only':
        fail('report reviews attach only to report-only source tasks')
    rev = snapshot(root, source_worker, source_task)
    d = load(root, source_worker, source_task)
    report_evidence(root, source_worker, source_task, d, rev)
    if (d['validation']['state'] != 'passed'
            or d['validation']['revision'] != rev or d['stale']):
        fail('report review source requires a current verify PASS')
    v = d.get('delivery')
    if not v or delivery_check(root, source_worker, source_task, d) != 'complete':
        fail('report review source requires a complete immutable required delivery')
    missing = set(REQUIRED_SOURCE_ARTIFACTS) - set(v['artifacts'])
    if missing:
        fail('report review source must deliver named artifacts summary.md, '
             'verdict.json and findings.json; missing: ' + ', '.join(sorted(missing)))
    directory = delivery_directory(root, source_worker, source_task, v['run_id'])
    artifacts = {}
    for name in REQUIRED_SOURCE_ARTIFACTS:
        data, identity = _read_bounded(os.path.join(directory, name), PACKET_FILES_LIMIT)
        if hashlib.sha256(data).hexdigest() != v['artifact_hashes'][name]:
            fail('report review source artifact changed during bind: ' + name)
        artifacts[name] = data
    verdict_doc = review_json(artifacts['verdict.json'].decode('utf-8'))
    if (not isinstance(verdict_doc, dict) or set(verdict_doc) != {'schema_version', 'verdict'}
            or verdict_doc['schema_version'] != SCHEMA_VERSION
            or verdict_doc['verdict'] not in VERDICTS):
        fail('verdict.json must be exactly {"schema_version":1,'
             '"verdict":"APPROVE"|"REQUEST-CHANGES"}')
    findings_doc = review_json(artifacts['findings.json'].decode('utf-8'))
    findings = findings_block_schema(findings_doc)
    if not artifacts['summary.md'].strip():
        fail('summary.md must be nonempty text')
    return d, rev, v, artifacts, verdict_doc['verdict'], len(findings)


def _frozen_declaration(root, source_worker, source_task, d):
    """Read the packet declaration from validated native predispatch evidence."""
    o = d['outcome']
    directory = outcome_directory(root, source_worker, source_task, o['run_id'])
    prompt = delivery_ns['read_artifact'](os.path.join(directory, 'prompt.md'), PROMPT_LIMIT)
    frozen = _single_declaration(prompt.decode('utf-8'),
                                 'the frozen predispatch reviewer prompt')
    current = regular(locations(root, source_worker, source_task)[1]).decode('utf-8')
    live = _single_declaration(current, 'the current reviewer task')
    if frozen != live:
        fail('Review packet declaration drift: the frozen predispatch binding '
             'differs from the current task (post-dispatch changes refuse)')
    return frozen


def _validate_receipt(doc, target_task, receipt_id):
    if not isinstance(doc, dict) or set(doc) != RECEIPT_FIELDS:
        fail('invalid report review receipt schema')
    if (doc['schema_version'] != SCHEMA_VERSION or doc['kind'] != 'report-review'
            or doc['id'] != receipt_id
            or not isinstance(doc['id'], str)
            or not re.fullmatch('[0-9a-f]{16}', doc['id'])
            or doc['target_task'] != target_task
            or doc['coverage'] not in COVERAGES
            or doc['verdict'] not in VERDICTS
            or type(doc['findings_count']) is not int or doc['findings_count'] < 0
            or doc['findings_schema'] != 'unio-findings-v1'
            or any(doc[k] != 'unknown' for k in ('requested_model', 'effective_model',
                                                 'requested_effort', 'effective_effort'))
            or doc['human_acceptance'] is not False
            or doc['native_readiness_effect'] != 'none'):
        fail('invalid report review receipt identity')
    for name in ('target_worker', 'source_worker', 'source_task'):
        if not isinstance(doc[name], str):
            fail('invalid report review receipt identity')
        ident(doc[name])
    if not isinstance(doc['target_task'], str):
        fail('invalid report review receipt identity')
    if not revision(doc['target_revision']):
        fail('invalid report review receipt revision')
    for key in ('packet_id', 'packet_manifest_sha256', 'source_command_sha256',
                'source_prompt_sha256', 'source_binding_sha256', 'source_report_sha256'):
        if (not isinstance(doc[key], str)
                or not re.fullmatch('[0-9a-f]{32}' if key == 'packet_id' else '[0-9a-f]{64}',
                                    doc[key])):
            fail('invalid report review receipt digest: ' + key)
    if (not isinstance(doc['source_run_id'], str)
            or not re.fullmatch('[0-9a-f]{32}', doc['source_run_id'])
            or type(doc['source_report_bytes']) is not int
            or not 0 < doc['source_report_bytes'] <= 262144):
        fail('invalid report review receipt source evidence')
    if (not isinstance(doc['declared_paths'], list)
            or len(doc['declared_paths']) > PACKET_PATHS_MAX
            or any(not isinstance(p, str) or not SAFE_RELATIVE.fullmatch(p)
                   for p in doc['declared_paths'])
            or len(set(doc['declared_paths'])) != len(doc['declared_paths'])
            or (doc['coverage'] == 'paths') != bool(doc['declared_paths'])):
        fail('invalid report review receipt coverage')
    artifacts = doc['source_artifacts']
    if (not isinstance(artifacts, dict) or set(artifacts) != set(REQUIRED_SOURCE_ARTIFACTS)
            or any(not isinstance(v, dict) or set(v) != {'sha256', 'bytes'}
                    or not isinstance(v['sha256'], str)
                    or not re.fullmatch('[0-9a-f]{64}', v['sha256'])
                    or type(v['bytes']) is not int or not 0 < v['bytes'] <= PACKET_FILES_LIMIT
                    for v in artifacts.values())):
        fail('invalid report review receipt artifacts')
    if not isinstance(doc['recorded_at'], str) or len(doc['recorded_at']) > 64:
        fail('invalid report review receipt timestamp')
    return doc


def _report_review_directory(root, target_task, receipt_id):
    return safe(root, 'coord', 'reports', target_task + '.report-review.' + receipt_id)


def reviews_bind(root, target_worker, target_task, source_worker, source_task):
    """Attach ONE verified report review; observational only, no provider call."""
    ident(target_worker); ident(target_task); ident(source_worker); ident(source_task)
    locations(root, target_worker, target_task)
    locations(root, source_worker, source_task)
    _stop_refused(root)
    _busy_refused(root, target_worker, 'target')
    _busy_refused(root, source_worker, 'source')
    live_rev = snapshot(root, target_worker, target_task)
    target = load(root, target_worker, target_task)
    if (target['validation']['state'] != 'passed'
            or target['validation']['revision'] != live_rev or target['stale']):
        fail('target task requires a current verify PASS at the live revision')
    d, source_rev, v, artifacts, verdict, findings_count = _source_report(
        root, source_worker, source_task)
    declaration = _frozen_declaration(root, source_worker, source_task, d)
    manifest, _packet = _load_packet(root, declaration)
    if manifest['worker'] != target_worker or manifest['task'] != target_task:
        fail('declared review packet targets a different worker/task')
    if manifest['revision'] != live_rev:
        fail('target revision changed since the packet was prepared; create a '
             'new packet rather than attach stale material')
    live_material = material_bytes_v2(root, target_worker, target_task)
    if hashlib.sha256(live_material).hexdigest() != manifest['material_sha256']:
        fail('target material changed since the packet was prepared')
    wt = locations(root, target_worker, target_task)[0]
    for entry in manifest['paths']:
        data, _ = _read_bounded(safe(wt, *entry['path'].split('/')), PACKET_FILES_LIMIT)
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            fail('target path changed since the packet was prepared: ' + entry['path'])
    o = d['outcome']
    key = dict(schema_version=SCHEMA_VERSION, target_worker=target_worker,
               target_task=target_task, packet_id=manifest['id'],
               packet_manifest_sha256=declaration['manifest_sha256'],
               source_worker=source_worker, source_task=source_task,
               source_run_id=o['run_id'], source_binding_sha256=o['binding_sha256'],
               source_report_sha256=o['report_sha256'],
               artifacts={name: hashlib.sha256(artifacts[name]).hexdigest()
                          for name in REQUIRED_SOURCE_ARTIFACTS},
               verdict=verdict)
    receipt_id = hashlib.sha256(_canonical(key)).hexdigest()[:REPORT_REVIEW_ID_HEX]
    receipt = dict(schema_version=SCHEMA_VERSION, kind='report-review', id=receipt_id,
                   target_worker=target_worker, target_task=target_task,
                   target_revision=live_rev, packet_id=manifest['id'],
                   packet_manifest_sha256=declaration['manifest_sha256'],
                   coverage=manifest['coverage'],
                   declared_paths=[e['path'] for e in manifest['paths']],
                   source_worker=source_worker, source_task=source_task,
                   source_run_id=o['run_id'], source_command_sha256=o['command_sha256'],
                   source_prompt_sha256=o['prompt_sha256'],
                   source_binding_sha256=o['binding_sha256'],
                   source_report_sha256=o['report_sha256'],
                   source_report_bytes=o['report_bytes'],
                   source_artifacts={name: dict(sha256=hashlib.sha256(data).hexdigest(),
                                                bytes=len(data))
                                     for name, data in artifacts.items()},
                   verdict=verdict, findings_count=findings_count,
                   findings_schema='unio-findings-v1',
                   requested_model='unknown', effective_model='unknown',
                   requested_effort='unknown', effective_effort='unknown',
                   human_acceptance=False, native_readiness_effect='none',
                   recorded_at=stamp())
    directory = _report_review_directory(root, target_task, receipt_id)
    if os.path.lexists(directory):
        existing, _ = _read_bounded(os.path.join(directory, 'receipt.json'), RECEIPT_LIMIT)
        stored = _validate_receipt(review_json(existing.decode('utf-8')),
                                   target_task, receipt_id)
        replay = dict(receipt)
        replay.pop('recorded_at')
        compare = dict(stored)
        compare.pop('recorded_at')
        if compare != replay:
            fail('report review replay mismatch: bound evidence changed')
        return dict(schema_version=SCHEMA_VERSION, attached=True, replay=True,
                    id=receipt_id, verdict=verdict, coverage=manifest['coverage'],
                    human_acceptance=False, native_readiness_effect='none',
                    note=NO_EFFECT_NOTE)
    fd = storage_directory(safe(root, 'coord', 'reports'), create=True)
    try:
        name = os.path.basename(directory)
        try:
            os.mkdir(name, 0o700, dir_fd=fd)
        except FileExistsError:
            fail('report review publication collision: ' + receipt_id)
        _write_exclusive(fd, name + '/receipt.json', _canonical(receipt))
        for artifact_name in REQUIRED_SOURCE_ARTIFACTS:
            _write_exclusive(fd, name + '/' + artifact_name, artifacts[artifact_name])
    finally:
        os.close(fd)
    return dict(schema_version=SCHEMA_VERSION, attached=True, replay=False,
                id=receipt_id, verdict=verdict, coverage=manifest['coverage'],
                human_acceptance=False, native_readiness_effect='none',
                note=NO_EFFECT_NOTE)


def _row_current(root, receipt):
    """Recheck packet, target and source freshness for one attached review."""
    reasons = []
    try:
        declaration = dict(schema_version=SCHEMA_VERSION, id=receipt['packet_id'],
                           manifest_sha256=receipt['packet_manifest_sha256'])
        manifest, _packet = _load_packet(root, declaration)
        if (manifest['worker'] != receipt['target_worker']
                or manifest['task'] != receipt['target_task']
                or manifest['coverage'] != receipt['coverage']
                or [e['path'] for e in manifest['paths']] != receipt['declared_paths']):
            reasons.append('packet_changed')
        live_rev = snapshot(root, receipt['target_worker'], receipt['target_task'])
        if live_rev != receipt['target_revision']:
            reasons.append('target_revision_changed')
        elif hashlib.sha256(material_bytes_v2(root, receipt['target_worker'],
                                              receipt['target_task'])).hexdigest() \
                != manifest['material_sha256']:
            reasons.append('target_material_changed')
        d, source_rev, v, artifacts, verdict, findings_count = _source_report(
            root, receipt['source_worker'], receipt['source_task'])
        if (d['outcome']['run_id'] != receipt['source_run_id']
                or verdict != receipt['verdict']
                or findings_count != receipt['findings_count']):
            reasons.append('source_changed')
        for name, data in artifacts.items():
            if (hashlib.sha256(data).hexdigest()
                    != receipt['source_artifacts'][name]['sha256']):
                reasons.append('source_changed')
                break
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        reasons.append('evidence_unavailable')
    return reasons


def reports_view(root, worker, task, mode='--reports'):
    """Separate observational view; never touches canonical projections."""
    if mode not in ('--reports', '--reports-json'):
        fail('unknown report reviews view mode')
    ident(worker); ident(task)
    locations(root, worker, task)
    as_json = mode == '--reports-json'
    reports = safe(root, 'coord', 'reports')
    names = []
    if os.path.exists(reports):
        with os.scandir(reports) as entries:
            for entry in entries:
                match = REPORT_REVIEW_NAME.fullmatch(entry.name)
                if match and match.group(1) == task:
                    names.append(entry.name)
                    if len(names) > REPORT_REVIEWS_MAX:
                        fail('report review folder bound reached')
    rows = []
    exit_code = 0
    for name in sorted(names):
        receipt_id = REPORT_REVIEW_NAME.fullmatch(name).group(2)
        row = dict(id=receipt_id, state='invalid', verdict=None, coverage=None,
                   source_worker=None, source_task=None, findings_count=None,
                   declared_paths=None, recorded_at=None, reasons=[], current=False,
                   stale=False, human_acceptance=False, native_readiness_effect='none')
        try:
            directory = _report_review_directory(root, task, receipt_id)
            data, _ = _read_bounded(os.path.join(directory, 'receipt.json'), RECEIPT_LIMIT)
            receipt = _validate_receipt(review_json(data.decode('utf-8')), task, receipt_id)
            if receipt['target_worker'] != worker:
                fail('report review worker mismatch')
            copies_ok = True
            for artifact_name, recorded in receipt['source_artifacts'].items():
                copy, _ = _read_bounded(os.path.join(directory, artifact_name),
                                        PACKET_FILES_LIMIT)
                if (hashlib.sha256(copy).hexdigest() != recorded['sha256']
                        or len(copy) != recorded['bytes']):
                    copies_ok = False
            if not copies_ok:
                row['reasons'] = ['bound_copies_changed']
                exit_code = 1
                rows.append(row)
                continue
            row.update(verdict=receipt['verdict'], coverage=receipt['coverage'],
                       source_worker=receipt['source_worker'],
                       source_task=receipt['source_task'],
                       findings_count=receipt['findings_count'],
                       declared_paths=receipt['declared_paths'],
                       recorded_at=receipt['recorded_at'])
            reasons = _row_current(root, receipt)
            if reasons:
                row.update(state='stale', stale=True, reasons=sorted(set(reasons)))
                exit_code = 1
            else:
                row.update(state='current', current=True)
            rows.append(row)
        except (OSError, ValueError, KeyError, TypeError, UnicodeError):
            row['reasons'] = ['report_review_receipt_invalid']
            exit_code = 1
            rows.append(row)
    if as_json:
        print(json.dumps(dict(schema_version=SCHEMA_VERSION, worker=worker, task=task,
                              rows=rows, note=NO_EFFECT_NOTE),
                         sort_keys=True, indent=2))
    else:
        print('Report reviews for %s / %s — %s' % (worker, task, NO_EFFECT_NOTE))
        if not rows:
            print('  (no attached report reviews)')
        for row in rows:
            if row['state'] == 'invalid':
                print('  %s — invalid receipt (%s)' % (row['id'], ','.join(row['reasons'])))
                continue
            print('  %s source %s / %s verdict %s coverage %s findings %d — %s'
                  % (row['id'], row['source_worker'], row['source_task'],
                     row['verdict'], row['coverage'], row['findings_count'],
                     'current' if row['current'] else 'stale: ' + ','.join(row['reasons'])))
            print('    human acceptance: not granted; native readiness effect: none')
    return exit_code
