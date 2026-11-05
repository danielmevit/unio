#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# SPDX-License-Identifier: AGPL-3.0-only; additional terms in NOTICE.
"""Material protocol 3: bounded, hash-bound enclosing source context.

Installed engine, tiny real Git and offline mock reviewers only.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import types
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('receipt_fixture', HERE/'unio-review-receipts.py')
fixture = importlib.util.module_from_spec(spec); spec.loader.exec_module(fixture)
spec = importlib.util.spec_from_file_location('findings_fixture', HERE/'unio-review-findings.py')
findings = importlib.util.module_from_spec(spec); spec.loader.exec_module(findings)

FOOTER = b'\nEnd with exactly one standalone line: VERDICT: APPROVE or VERDICT: REQUEST-CHANGES\n'
START = b'\nENCLOSING SOURCE CONTEXT\n'
END = b'END ENCLOSING SOURCE CONTEXT\n'
SMALL = ''.join('small line %02d\n' % n for n in range(1, 31))
BIG = ''.join('big line %04d %s\n' % (n, 'x' * 20) for n in range(1, 3001))
EDIT = '''import pathlib
small = pathlib.Path('small.py'); lines = small.read_text().splitlines(True)
lines[9] = 'small line 10 changed\\n'; small.write_text(''.join(lines))
big = pathlib.Path('big.py'); lines = big.read_text().splitlines(True)
lines[1499] = 'big line 1500 changed\\n'; lines[1999] = 'big line 2000 changed\\n'
big.write_text(''.join(lines))
pathlib.Path('gone.txt').unlink()
pathlib.Path('new.txt').write_text('new file\\n')
'''


def lines_of(data):
    parts = data.split(b'\n')
    return [p + b'\n' for p in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def parse_context(payload):
    """Independent parser for the protocol-3 section; returns manifest and blocks."""
    start = payload.index(b'\nFULL COMMITTED DIFF\n')
    at = payload.index(START, start)
    end = payload.index(END, at) + len(END)
    section = payload[at:end]
    manifest_at = section.index(b'\nMANIFEST ') + 1
    newline = section.index(b'\n', manifest_at)
    manifest = json.loads(section[manifest_at + len(b'MANIFEST '):newline])
    blocks = []; pos = newline + 1
    while section.startswith(b'CONTEXT ', pos):
        eol = section.index(b'\n', pos)
        header = json.loads(section[pos + len(b'CONTEXT '):eol])
        body = section[eol + 1:eol + 1 + header['bytes']]
        assert section.startswith(b'\nEND CONTEXT\n', eol + 1 + header['bytes']), header
        blocks.append((header, body))
        pos = eol + 1 + header['bytes'] + len(b'\nEND CONTEXT\n')
    assert section[pos:] == END, section[pos:pos + 80]
    return manifest, blocks, payload[:at], payload[end:]


class ReviewContext(unittest.TestCase):
    setUpClass = classmethod(fixture.ReviewReceipts.setUpClass.__func__)
    call = fixture.ReviewReceipts.call
    unio = fixture.ReviewReceipts.unio
    controls = fixture.ReviewReceipts.controls
    calls = fixture.ReviewReceipts.calls
    receipts = fixture.ReviewReceipts.receipts
    summary = fixture.ReviewReceipts.summary

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='review context β ')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root/'project/repo'; self.repo.mkdir(parents=True)
        self.env = dict(self.__class__.env); self.env['UNIO_CONF_DIR'] = str(self.root/'conf')
        conf = self.root/'conf'; conf.mkdir()
        shutil.copytree(self.install/'conf/templates', conf/'templates')
        (self.root/'provider.py').write_text(findings.PROVIDER)
        (self.root/'edit.py').write_text(EDIT)
        lines = ['mock=' + shlex.join(['bash', '-c', 'python3 ' + shlex.quote(str(self.root/'edit.py'))
                                       + ' && git add -A && git commit -qm work'])]
        for name in ('revone', 'revtwo'):
            lines.append(name + '=' + shlex.join(['python3', str(self.root/'provider.py'), str(self.root), name]))
        (conf/'agents.conf').write_text('\n'.join(lines) + '\n')
        self.control = {}; self.controls()
        (self.repo/'small.py').write_text(SMALL)
        (self.repo/'big.py').write_text(BIG)
        (self.repo/'gone.txt').write_text('to be deleted\n')
        self.call(['git', 'init', '-q', '-b', 'dev'])
        self.call(['git', 'add', '-A']); self.call(['git', 'commit', '-qm', 'base'])
        self.unio('init', 'mock')
        self.coord = self.root/'project/coord'
        self.worker = self.root/'project/wt/mock'
        self.task = self.coord/'tasks/evidence.md'
        self.task.write_text('# Task\n## Allowed scope\n- small.py\n- big.py\n- gone.txt\n- new.txt\n'
                             '## Validate\n$ test -s new.txt\n')
        self.unio('run', 'mock', 'evidence'); self.unio('verify', 'mock', 'evidence')

    def findings_view(self, code=0, expect='revone'):
        arguments = [self.engine, 'reviews', 'mock', 'evidence']
        if expect is not None: arguments += ['--expect', expect]
        p = subprocess.run(arguments + ['--findings', '--json'], cwd=self.repo, env=self.env,
                           capture_output=True, text=True, timeout=90)
        if code is not None: self.assertEqual(p.returncode, code, (p.stdout[-2000:], p.stderr[-2000:]))
        return json.loads(p.stdout)

    def head_bytes(self, path):
        return subprocess.check_output(['git', '-C', str(self.worker), 'show', 'HEAD:' + path], env=self.env)

    def commit_worker(self, path, data):
        (self.worker/path).write_bytes(data)
        self.call(['git', 'add', '-A'], cwd=self.worker)
        self.call(['git', 'commit', '-qm', 'more'], cwd=self.worker)
        self.unio('verify', 'mock', 'evidence')

    def test_protocol3_manifest_regions_and_exact_hashes(self):
        self.controls(revone='empty')
        self.unio('review', 'mock', 'evidence', 'revone')
        receipt = json.loads(self.receipts()[0].read_text())
        payload = (self.root/'revone.material.bin').read_bytes()
        self.assertEqual(receipt['schema_version'], 2)
        self.assertEqual(receipt['material_protocol'], 3)
        self.assertEqual(receipt['material_sha256'], hashlib.sha256(payload).hexdigest())
        self.assertLessEqual(len(payload), 300000)
        payload.decode('utf-8')
        manifest, blocks, before, after = parse_context(payload)
        self.assertEqual(manifest['schema_version'], 1)
        self.assertEqual(manifest['candidate_commit'], receipt['before']['candidate_commit'])
        self.assertEqual(manifest['base_commit'], receipt['before']['base_commit'])
        self.assertEqual(manifest['unlisted'], 0)
        files = {item['path']: item for item in manifest['files']}
        self.assertEqual(sorted(files), ['big.py', 'gone.txt', 'new.txt', 'small.py'])
        self.assertEqual((files['gone.txt']['status'], files['gone.txt']['reason']), ('omitted', 'deleted'))
        self.assertEqual((files['new.txt']['status'], files['new.txt']['reason']), ('omitted', 'added_in_diff'))
        small, big = self.head_bytes('small.py'), self.head_bytes('big.py')
        self.assertEqual(files['small.py']['status'], 'full')
        self.assertEqual(files['small.py']['sha256'], hashlib.sha256(small).hexdigest())
        self.assertEqual(files['small.py']['regions'][0]['start'], 1)
        self.assertEqual(files['small.py']['regions'][0]['end'], 30)
        self.assertGreater(len(big), 65536)
        self.assertEqual(files['big.py']['status'], 'regions')
        self.assertEqual(files['big.py']['sha256'], hashlib.sha256(big).hexdigest())
        self.assertEqual(files['big.py']['lines'], 3000)
        self.assertEqual([(r['start'], r['end']) for r in files['big.py']['regions']],
                         [(1460, 1540), (1960, 2040)])
        # Every block is exactly the declared bytes of the candidate file.
        sources = {'small.py': lines_of(small), 'big.py': lines_of(big)}
        self.assertEqual(len(blocks), 3)
        for header, body in blocks:
            expected = b''.join(sources[header['path']][header['start'] - 1:header['end']])
            self.assertEqual(body, expected)
            self.assertEqual(header['sha256'], hashlib.sha256(body).hexdigest())
            listed = {(r['start'], r['end'], r['sha256']) for r in files[header['path']]['regions']}
            self.assertIn((header['start'], header['end'], header['sha256']), listed)
        self.assertIn(b'big line 1500 changed', payload)
        self.assertNotIn(b'big line 1000 ', payload)
        # The complete diff and the legacy body are untouched by the section.
        legacy = findings.ReviewFindings.legacy_body(self, receipt['before'])
        self.assertTrue(before.startswith(legacy))
        self.assertTrue(after.endswith(FOOTER))
        self.assertIn(b'unio-findings-v1', after)
        view = self.findings_view()
        self.assertEqual(view['decision'], 'no_structured_findings')
        self.assertEqual(view['material_protocols']['3'], receipt['material_sha256'])
        self.assertEqual(view['material_protocols']['2'], hashlib.sha256(before + after).hexdigest())
        self.assertEqual(view['material_protocols']['1'], hashlib.sha256(legacy + FOOTER).hexdigest())
        self.assertEqual(view['material_sha256'], view['material_protocols']['3'])
        self.assertEqual(view['evidence'][0]['protocol'], 3)
        self.assertTrue(view['evidence'][0]['current'])
        self.assertEqual(self.summary(expect='revone')['decision'], 'all_recorded_approved')

    def test_bridge_accepts_protocol3_readiness(self):
        self.controls(revone='empty', revtwo='empty')
        self.unio('review', 'mock', 'evidence', 'revone')
        self.unio('review', 'mock', 'evidence', 'revtwo')
        result = json.loads(self.unio('result', 'mock', 'evidence').stdout)
        projection = result['review_current']
        self.assertTrue(projection['machine_review_ready'])
        self.assertEqual({row['protocol'] for row in projection['evidence']}, {3})
        bridge_spec = importlib.util.spec_from_file_location(
            'installed_execution_service', self.install/'conf/lib/browser/execution_service.py')
        bridge = importlib.util.module_from_spec(bridge_spec); bridge_spec.loader.exec_module(bridge)
        current = bridge._revision(result['current_revision'])
        self.assertTrue(bridge._current_review(projection, 'mock', 'evidence', current))
        # The bridge refuses an engine projection without the protocol-3 key.
        stripped = dict(projection, material_protocols={k: v for k, v in projection['material_protocols'].items()
                                                         if k != '3'})
        with self.assertRaises(ValueError):
            bridge._current_review(stripped, 'mock', 'evidence', current)

    def test_review_set_records_protocol3_for_every_reviewer(self):
        self.controls(revone='empty', revtwo='empty')
        self.unio('review-set', 'mock', 'evidence', 'revone', 'revtwo')
        records = [json.loads(p.read_text()) for p in self.receipts()]
        self.assertEqual(sorted(r['reviewer'] for r in records), ['revone', 'revtwo'])
        self.assertEqual({r['material_protocol'] for r in records}, {3})
        self.assertEqual(len({r['material_sha256'] for r in records}), 1)
        self.assertEqual((self.root/'revone.material.bin').read_bytes(),
                         (self.root/'revtwo.material.bin').read_bytes())
        self.assertEqual(self.summary(expect='revone,revtwo')['decision'], 'all_recorded_approved')

    def test_candidate_change_makes_protocol3_receipt_stale(self):
        self.controls(revone='empty')
        self.unio('review', 'mock', 'evidence', 'revone')
        big = bytearray(self.head_bytes('big.py'))
        self.commit_worker('big.py', bytes(big).replace(b'big line 1501 ', b'big line 1501 edited '))
        d = self.summary(code=2, expect='revone')
        self.assertEqual(d['counts']['stale'], 1)
        self.assertEqual(d['counts']['current'], 0)

    def test_legacy_protocol2_receipt_stays_current_and_unknown_protocols_refused(self):
        self.controls(revone='empty')
        self.unio('review', 'mock', 'evidence', 'revone')
        real = self.receipts()[0]; base = json.loads(real.read_text())
        view = self.findings_view()
        def write(name, material_hash, protocol):
            target = self.coord/'reports'/('evidence.review.' + name)
            shutil.copytree(real.parent, target)
            receipt = dict(base, id=hashlib.sha256(name.encode()).hexdigest()[:32],
                           material_sha256=material_hash, material_protocol=protocol)
            (target/'receipt.json').write_text(json.dumps(receipt, sort_keys=True) + '\n')
        write('Proto200', view['material_protocols']['2'], 2)
        d = self.findings_view()
        rows = {row['raw_directory'][-8:]: row for row in d['evidence']}
        self.assertTrue(rows['Proto200']['current'])
        self.assertEqual(rows['Proto200']['protocol'], 2)
        self.assertEqual(self.summary(expect='revone')['counts']['current'], 2)
        # A protocol-3 claim over protocol-2 bytes never binds.
        write('Proto300', view['material_protocols']['2'], 3)
        d = self.summary(expect='revone')
        self.assertEqual((d['counts']['current'], d['counts']['stale']), (2, 1))
        write('Proto400', view['material_protocols']['3'], 4)
        d = self.summary(code=2, expect='revone')
        self.assertEqual(d['decision'], 'incomplete')
        self.assertEqual(d['counts']['unresolved'], 1)

    def test_budget_falls_back_to_protocol2_and_omits_explicitly(self):
        # Grow the added file until only part of the context fits, then until
        # no context fits. The diff itself is never clipped.
        omitted = fallback = None
        for size in range(286000, 300000, 500):
            self.commit_worker('new.txt', b'y' * size + b'\n')
            view = self.findings_view(code=None, expect=None)
            if view['material_protocols']['2'] is None: break
            if view['material_protocols']['3'] is None:
                fallback = size; break
            if omitted is None:
                self.unio('review', 'mock', 'evidence', 'revone')
                newest = max(self.receipts(), key=lambda p: p.stat().st_mtime_ns)
                if json.loads(newest.read_text())['material_protocol'] == 3:
                    payload = (self.root/'revone.material.bin').read_bytes()
                    manifest, blocks = parse_context(payload)[:2]
                    bounded = [f for f in manifest['files'] if f['reason'] == 'size_bound']
                    if bounded:
                        omitted = size
                        self.assertLessEqual(len(payload), 300000)
                        for item in bounded:
                            self.assertEqual((item['status'], item['regions']), ('omitted', []))
                            self.assertNotIn(item['path'], {header['path'] for header, _ in blocks})
        self.assertIsNotNone(omitted, 'no partial-context window found')
        self.assertIsNotNone(fallback, 'no protocol-2 fallback window found')
        calls = self.calls()
        self.unio('review', 'mock', 'evidence', 'revone')
        self.assertNotEqual(self.calls(), calls)
        newest = max(self.receipts(), key=lambda p: p.stat().st_mtime_ns)
        receipt = json.loads(newest.read_text())
        self.assertEqual(receipt['material_protocol'], 2)
        payload = (self.root/'revone.material.bin').read_bytes()
        self.assertNotIn(b'\nMANIFEST {', payload)
        self.assertTrue(payload.endswith(FOOTER))
        view = self.findings_view(code=None, expect=None)
        self.assertEqual(receipt['material_sha256'], view['material_protocols']['2'])
        row = next(r for r in view['evidence'] if r['raw_directory'] == newest.parent.name)
        self.assertTrue(row['current'])

    def test_context_ignores_diff_configuration(self):
        # Load the installed quality helper in-process and inject Git config
        # through the environment: the pinned context bytes must not change.
        engine = Path(self.engine).read_text()
        body = engine.split("<<'QUALITY_PY'\n", 1)[1].split('\nQUALITY_PY\n', 1)[0]
        module = types.ModuleType('installed_quality_context')
        module.__dict__['__name__'] = 'installed_quality_context'
        exec(compile(body.split('\ntry:\n    cmd,*a=sys.argv[1:]\n', 1)[0], self.engine, 'exec'), module.__dict__)
        root = str(self.root/'project')
        rev = module.snapshot(root, 'mock', 'evidence')
        plain = module.material_context(root, 'mock', 'evidence', rev, 200000)
        settings = {'diff.algorithm': 'patience', 'diff.interHunkContext': '1000', 'diff.indentHeuristic': 'false',
                    'diff.noprefix': 'true', 'color.diff': 'always', 'diff.context': '9',
                    'diff.renames': 'copies', 'diff.mnemonicPrefix': 'true', 'core.quotePath': 'true'}
        saved = dict(os.environ)
        try:
            os.environ['GIT_CONFIG_COUNT'] = str(len(settings))
            for i, (key, value) in enumerate(settings.items()):
                os.environ['GIT_CONFIG_KEY_%d' % i] = key; os.environ['GIT_CONFIG_VALUE_%d' % i] = value
            configured = module.material_context(root, 'mock', 'evidence', rev, 200000)
        finally:
            os.environ.clear(); os.environ.update(saved)
        self.assertIsNotNone(plain)
        self.assertEqual(plain, configured)
        self.assertIsNone(module.material_context(root, 'mock', 'evidence', rev, 100))


if __name__ == '__main__':
    unittest.main(verbosity=2)
