#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Offline tests for tools/perplexity-worker.py against a fake perplexity_web_mcp.

The fake mirrors the pinned 0.16.1 surfaces the adapter may touch (core.Perplexity,
create_conversation, Conversation.ask, frozen configs, enums, models, exceptions,
token_store.load_token) and nothing else, so invented call names fail. It lives in
a private `venv --without-pip` with dist-info metadata: no install, network or token.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import unittest

WORKER = Path(__file__).resolve().parent.parent / 'tools' / 'perplexity-worker.py'
SECRET = 'tok-SECRET-4711'
FAKE = {
    '__init__.py': '''
import json, os
def log(**event):
    with open(os.environ['FAKE_PPLX_LOG'], 'a') as handle:
        handle.write(json.dumps(event) + '\\n')
log(event='imported')
''',
    'enums.py': '''
from enum import Enum
class LogLevel(str, Enum):
    DISABLED = 'DISABLED'
    DEBUG = 'DEBUG'
class SourceFocus(str, Enum):
    WEB = 'web'
    ACADEMIC = 'scholar'
    SOCIAL = 'social'
    FINANCE = 'edgar'
''',
    'config.py': '''
from .enums import LogLevel, SourceFocus
class _Frozen:
    FIELDS = {}
    def __init__(self, **values):
        unknown = set(values) - set(self.FIELDS)
        if unknown:
            raise TypeError(f'unexpected fields {sorted(unknown)}')
        self.__dict__.update({**self.FIELDS, **values})
    def __setattr__(self, *_):
        raise TypeError('frozen')
class ClientConfig(_Frozen):
    FIELDS = dict(timeout=3600, impersonate='chrome', max_retries=3, retry_base_delay=1.0,
                  retry_max_delay=60.0, retry_jitter=0.5, requests_per_second=0.5,
                  rotate_fingerprint=True, logging_level=LogLevel.DISABLED, log_file=None)
class ConversationConfig(_Frozen):
    FIELDS = dict(model=None, citation_mode='clean', save_to_library=False, search_focus='internet',
                  source_focus=SourceFocus.WEB, time_range='', language='en-US', timezone=None,
                  coordinates=None)
''',
    'models.py': '''
import os
from dataclasses import dataclass
@dataclass(frozen=True, slots=True)
class Model:
    identifier: str
    mode: str = 'copilot'
class Models:
    BEST = Model(identifier='pplx_pro')
    SONAR = Model(identifier='experimental', mode='concise')
    GLM_5_2 = Model(identifier='glm_5_2')
    GLM_5_3 = Model(identifier='glm_5_3_thinking')
    GPT_6_SOL_THINKING = Model(identifier='gpt6_sol_thinking')
    KIMI_K2_6_THINKING = Model(identifier='kimik26thinking')
    KIMI_K3 = Model(identifier='kimik3thinking')
if os.environ.get('FAKE_PPLX_MODE') == 'renamed':
    Models.KIMI_K3 = Model(identifier='kimik3')
''',
    'types.py': '''
from dataclasses import dataclass
@dataclass(frozen=True)
class SearchResultItem:
    title: str | None = None
    snippet: str | None = None
    url: str | None = None
''',
    'exceptions.py': '''
class PerplexityError(Exception):
    def __init__(self, message):
        self.message = message
        super().__init__(message)
class HTTPError(PerplexityError):
    def __init__(self, message, status_code=None, url=None, response_body=None):
        self.status_code, self.url, self.response_body = status_code, url, response_body
        super().__init__(message)
class AuthenticationError(HTTPError):
    def __init__(self, message=None, url=None, response_body=None):
        super().__init__(message or 'forbidden', 403, url, response_body)
class RateLimitError(HTTPError):
    def __init__(self, message=None, url=None, response_body=None):
        super().__init__(message or 'rate limited', 429, url, response_body)
class ResponseParsingError(PerplexityError):
    pass
''',
    'token_store.py': '''
import os
from . import log
def load_token():
    log(event='load_token')
    return os.environ.get('FAKE_PPLX_TOKEN') or None
''',
    'shared.py': 'from . import log\nlog(event="forbidden", name="shared")\n',
    'router.py': 'from . import log\nlog(event="forbidden", name="router")\n',
    'core.py': '''
import hashlib, os, subprocess, sys, time
from . import log
from .config import ClientConfig, ConversationConfig
from .exceptions import AuthenticationError, HTTPError, RateLimitError
from .types import SearchResultItem
class Perplexity:
    __slots__ = ('_http',)
    def __init__(self, session_token, config=None):
        if not session_token or not session_token.strip():
            raise ValueError('session_token cannot be empty')
        assert isinstance(config, ClientConfig)
        self._http = session_token
        log(event='client', token_ok=session_token == os.environ['FAKE_PPLX_TOKEN'],
            **{k: getattr(config, k) for k in ClientConfig.FIELDS if k != 'logging_level'},
            logging_level=config.logging_level.value)
    def create_conversation(self, config=None):
        return Conversation(self._http, config or ConversationConfig())
    def close(self):
        log(event='close')
class Conversation:
    __slots__ = ('_http', '_config', '_answer', '_search_results')
    def __init__(self, http, config):
        self._http, self._config = http, config
        self._answer, self._search_results = None, []
        log(event='conversation', model=config.model.identifier, mode=config.model.mode,
            sources=[getattr(s, 'value', s) for s in config.source_focus],
            save_to_library=config.save_to_library)
    @property
    def answer(self):
        return self._answer
    @property
    def search_results(self):
        return self._search_results
    def ask(self, query, model=None, files=None, citation_mode=None, stream=False, init_query=None):
        mode = os.environ.get('FAKE_PPLX_MODE', 'ok')
        log(event='ask', sha256=hashlib.sha256(query.encode()).hexdigest(), model=model,
            files=files, stream=stream)
        if mode == 'auth':
            raise AuthenticationError('SECRET-EXC 403 ' + self._http)
        if mode == 'ratelimit':
            raise RateLimitError('SECRET-EXC 429')
        if mode == 'denied':
            raise HTTPError('SECRET-EXC model not in plan', status_code=400, response_body='SECRET')
        if mode == 'boom':
            raise RuntimeError('SECRET-EXC ' + self._http)
        if mode == 'sleep':
            helper = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])
            log(event='grandchild', pid=helper.pid)
            time.sleep(60)
        if mode == 'noisy':
            print('library chatter on stdout', flush=True)
            os.write(1, b'raw fd chatter\\n')
        self._answer = ('x' * (3 << 20)) if mode == 'huge' else 'Findings\\x1b[31m here\\r\\nline two\\n\\n'
        self._search_results = [SearchResultItem(title='Doc', url='https://example.invalid/a'),
                                SearchResultItem(title='Doc again', url='https://example.invalid/a'),
                                SearchResultItem(title='No link', url=None),
                                SearchResultItem(title='Spaced', url='https://example.invalid/a b'),
                                SearchResultItem(title=None, url='https://example.invalid/b')]
        return self
''',
}


def make_venv(base, version=None):
    subprocess.run([sys.executable, '-m', 'venv', '--without-pip', str(base)], check=True)
    python = base / 'bin' / 'python'
    if version:
        site = Path(subprocess.run([str(python), '-I', '-c', 'import sysconfig; print(sysconfig.get_paths()["purelib"])'],
                                   check=True, capture_output=True, text=True).stdout.strip())
        (site / 'perplexity_web_mcp').mkdir()
        for name, text in FAKE.items():
            (site / 'perplexity_web_mcp' / name).write_text(text.lstrip())
        info = site / 'perplexity_web_mcp_cli-0.16.1.dist-info'
        info.mkdir()
        (info / 'METADATA').write_text(f'Metadata-Version: 2.1\nName: perplexity-web-mcp-cli\nVersion: {version}\n')
        (info / 'RECORD').write_text(''.join(f'perplexity_web_mcp/{name},,\n' for name in FAKE))
    return python


class PerplexityWorker(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='unio perplexity ')
        cls.base = Path(cls.tmp.name)
        cls.python = make_venv(cls.base / 'fake venv', '0.16.1')
        cls.old = make_venv(cls.base / 'old venv', '0.16.0')
        cls.bare = make_venv(cls.base / 'bare venv')
        cls.prompt = cls.base / 'task with spaces.md'
        cls.prompt.write_text('Summarize the trade-offs of X.\n')

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_worker(self, *args, mode='ok', python=None, token=SECRET, env=None, timeout=60):
        log = self.base / 'events.jsonl'
        log.unlink(missing_ok=True)
        full = {k: v for k, v in os.environ.items() if k != 'TASKFILE'}
        full.update(FAKE_PPLX_LOG=str(log), FAKE_PPLX_MODE=mode, FAKE_PPLX_TOKEN=token, **(env or {}))
        result = subprocess.run([str(python or self.python), '-B', str(WORKER), *args], env=full,
                                capture_output=True, text=True, timeout=timeout)
        events = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
        self.assertNotIn('forbidden', [e['event'] for e in events])
        self.assertNotIn(SECRET, result.stdout + result.stderr)
        self.assertNotIn('SECRET', result.stderr)
        self.assertNotIn('Traceback', result.stderr)
        return result, events

    def kinds(self, events):
        return [e['event'] for e in events if e['event'] != 'imported']

    def private_dir(self, name):
        path = self.base / name
        path.mkdir(mode=0o700)
        path.chmod(0o700)
        return path

    def test_check_reads_metadata_only(self):
        result, events = self.run_worker('--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(events, [])
        for line in ('auth: unknown', 'effective model: unknown', 'remaining capacity: unknown'):
            self.assertIn(line, result.stdout)
        for python, state in ((self.old, 'dependency_version'), (self.bare, 'dependency_missing')):
            for args in (['--check'], ['--model', 'glm53', '--prompt-file', str(self.prompt)]):
                result, events = self.run_worker(*args, python=python)
                self.assertEqual((result.returncode, events), (3, []))
                self.assertIn(state, result.stderr)

    def test_exact_identifiers_one_token_load_one_ask(self):
        sha = hashlib.sha256(self.prompt.read_bytes()).hexdigest()
        cases = ((['--model', 'glm53', '--prompt-file', str(self.prompt)], {}, 'glm_5_3_thinking', ['web']),
                 (['--model', 'gpt6_sol', '--prompt-file', str(self.prompt)], {}, 'gpt6_sol_thinking', ['web']),
                 (['--model', 'kimi_k3', '--source', 'none', '--timeout', '90'], {'TASKFILE': str(self.prompt)},
                  'kimik3thinking', []))
        for args, env, identifier, sources in cases:
            result, events = self.run_worker(*args, env=env)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.kinds(events), ['load_token', 'client', 'conversation', 'ask', 'close'])
            client, conversation, ask = events[2], events[3], events[4]
            self.assertTrue(client['token_ok'])
            self.assertEqual((client['max_retries'], client['logging_level'], client['rotate_fingerprint']),
                             (0, 'DISABLED', False))
            self.assertEqual(client['timeout'], 90 if '90' in args else 600)
            self.assertEqual(conversation, dict(event='conversation', model=identifier, mode='copilot',
                                                sources=sources, save_to_library=False))
            self.assertEqual((ask['sha256'], ask['model'], ask['files'], ask['stream']), (sha, None, None, False))
            self.assertEqual(result.stdout, 'Findings[31m here\nline two\n\nSources:\n'
                             '[1] Doc https://example.invalid/a\n[2] https://example.invalid/b\n')
        result, _ = self.run_worker('--model', 'glm53', '--json', '--prompt-file', str(self.prompt), mode='noisy')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.endswith('}\n') and result.stdout.count('\n') == 1)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {'answer', 'citations', 'requested_model', 'configured_identifier',
                                     'effective_model', 'transport'})
        self.assertEqual((data['effective_model'], data['configured_identifier']), ('unknown', 'glm_5_3_thinking'))
        self.assertEqual(len(data['citations']), 2)

    def test_large_prompt_and_private_receipts(self):
        large = self.base / 'large task.md'
        large.write_text('é research question\n' * 20000)
        receipts = self.private_dir('receipts')
        for _ in range(2):
            result, events = self.run_worker('--model', 'kimi_k3', '--prompt-file', str(large), '--receipt-dir', str(receipts))
            self.assertEqual(result.returncode, 0, result.stderr)
        runs = sorted(receipts.iterdir())
        self.assertEqual(len(runs), 2)
        text = (runs[0] / 'receipt.json').read_text()
        receipt = json.loads(text)
        self.assertEqual(stat.S_IMODE(runs[0].stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((runs[0] / 'receipt.json').stat().st_mode), 0o600)
        self.assertEqual(receipt['task_sha256'], hashlib.sha256(large.read_bytes()).hexdigest())
        expected = dict(requested_model='kimi_k3', requested_lab='Moonshot AI', configured_identifier='kimik3thinking',
                        thinking=True, budget_group='perplexity', effective_model='unknown', effective_lab='unknown',
                        max_retries=0, outcome='ok', exit_code=0, transport='Perplexity Pro web session')
        self.assertEqual({k: receipt[k] for k in expected}, expected)
        for leak in (SECRET, 'research question', 'Findings', 'example.invalid'):
            self.assertNotIn(leak, text)

    def test_selected_context_and_proposal_handoff(self):
        context = self.base / 'selected source.py'
        context.write_text('def selected_function():\n    return 42\n')
        original = context.read_bytes()
        proposals = self.private_dir('proposals')
        channel = self.base / 'engine-report.txt'
        result, events = self.run_worker('--model', 'gpt6_sol', '--prompt-file', str(self.prompt),
                                         '--context-file', str(context), '--proposal-dir', str(proposals), '--json',
                                         env={'UNIO_TASK_REPORT': str(channel)})
        self.assertEqual(result.returncode, 0, result.stderr)
        packet = json.loads(result.stdout)
        self.assertEqual(packet['status'], 'draft_requires_review')
        run = Path(packet['proposal_dir'])
        self.assertEqual(run.parent, proposals)
        self.assertEqual({p.name for p in run.iterdir()}, {'task.md', 'proposal.md', 'handoff.md', 'receipt.json'})
        self.assertEqual(context.read_bytes(), original)
        self.assertEqual((run / 'task.md').read_bytes(), self.prompt.read_bytes())
        self.assertIn('Findings', (run / 'proposal.md').read_text())
        self.assertIn('Findings', channel.read_text())
        self.assertNotIn('proposal_dir', channel.read_text())
        self.assertIn('https://example.invalid/a', (run / 'proposal.md').read_text())
        self.assertIn('bounded Unio task', (run / 'handoff.md').read_text())
        record = json.loads((run / 'receipt.json').read_text())
        self.assertEqual(record['workflow'], 'code_proposal')
        self.assertEqual(record['selected_files'], [{'path': str(context), 'bytes': len(original),
                                                    'sha256': hashlib.sha256(original).hexdigest()}])
        ask = next(e for e in events if e['event'] == 'ask')
        self.assertEqual(record['question_sha256'], ask['sha256'])
        self.assertNotEqual(record['question_sha256'], record['task_sha256'])
        self.assertGreater(record['question_bytes'], len(original) + len(self.prompt.read_bytes()))
        self.assertEqual(self.kinds(events), ['load_token', 'client', 'conversation', 'ask', 'close'])
        for file in run.iterdir():
            self.assertEqual(stat.S_IMODE(file.stat().st_mode), 0o600)
            self.assertNotIn(SECRET, file.read_text())

    def test_invalid_context_never_authenticates(self):
        large = self.base / 'large selected.py'
        large.write_bytes(b'x' * (300 * 1024))
        other = self.base / 'other selected.py'
        other.write_bytes(b'y' * (300 * 1024))
        secret = self.base / '.env'
        secret.write_text(SECRET)
        cases = [['--context-file', str(secret)], ['--context-file', str(self.base / 'missing.py')],
                 ['--context-file', str(large), '--context-file', str(other)],
                 ['--receipt-dir', str(self.base), '--proposal-dir', str(self.base)],
                 ['--model', 'gpt61_sol']]
        for extra in cases:
            result, events = self.run_worker('--model', 'glm53', '--prompt-file', str(self.prompt), *extra)
            self.assertEqual((result.returncode, events), (2, []))

    def test_invalid_input_rejected_before_any_import(self):
        oversize = self.base / 'oversize.md'
        oversize.write_bytes(b'a' * (512 * 1024 + 1))
        binary = self.base / 'binary.md'
        binary.write_bytes(b'\xff\xfe')
        empty = self.base / 'empty.md'
        empty.write_text(' \n')
        link = self.base / 'link.md'
        link.symlink_to(self.prompt)
        public = self.base / 'public receipts'
        public.mkdir(mode=0o755)
        public.chmod(0o755)
        task = ['--prompt-file', str(self.prompt)]
        cases = [['--model', 'glm5', *task], ['--model', 'kimi_k3_fast', *task], ['--model', 'glm53'],
                 ['--model', 'glm53', '--timeout', 'nan', *task], ['--model', 'glm53', '--timeout', 'inf', *task],
                 ['--model', 'glm53', '--timeout', '1', *task], ['--model', 'glm53', '--timeout', '2.5', *task],
                 ['--model', 'glm53', '--max-output', '1e309', *task], ['--model', 'glm53', '--source', 'social', *task],
                 ['--model', 'glm53', 'inline prompt text'], ['--model', 'glm53', *task, '--receipt-dir', str(public)],
                 ['--model', 'glm53', *task, '--receipt-dir', str(self.base / 'missing')]]
        cases += [['--model', 'glm53', '--prompt-file', str(p)] for p in (oversize, binary, empty, link, self.base)]
        for args in cases:
            result, events = self.run_worker(*args)
            self.assertEqual((result.returncode, events), (2, []), args)
        self.assertEqual(list(public.iterdir()), [])

    def test_auth_and_model_states_before_ask(self):
        result, events = self.run_worker('--model', 'glm53', '--prompt-file', str(self.prompt), token='')
        self.assertEqual((result.returncode, self.kinds(events)), (5, ['load_token']))
        self.assertIn('pwm login', result.stderr)
        result, events = self.run_worker('--model', 'kimi_k3', '--prompt-file', str(self.prompt), mode='renamed')
        self.assertEqual((result.returncode, self.kinds(events)), (4, []))

    def test_upstream_failures_are_safe_and_not_retried(self):
        receipts = self.private_dir('failure receipts')
        for mode, code, state in (('auth', 5, 'auth_denied'), ('ratelimit', 6, 'rate_limited'),
                                  ('denied', 6, 'upstream_refused'), ('boom', 10, 'internal_error')):
            result, events = self.run_worker('--model', 'glm53', '--prompt-file', str(self.prompt),
                                             '--receipt-dir', str(receipts), mode=mode)
            self.assertEqual(result.returncode, code, mode)
            self.assertEqual(result.stdout, '')
            self.assertIn(state, result.stderr)
            self.assertEqual(self.kinds(events), ['load_token', 'client', 'conversation', 'ask', 'close'])
        for run in receipts.iterdir():
            text = (run / 'receipt.json').read_text()
            self.assertNotIn('SECRET', text)
            self.assertNotEqual(json.loads(text)['exit_code'], 0)

    def test_timeout_and_overflow_kill_owned_group(self):
        started = time.monotonic()
        result, events = self.run_worker('--model', 'glm53', '--timeout', '3', '--prompt-file', str(self.prompt), mode='sleep')
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertLess(time.monotonic() - started, 20)
        pid = [e['pid'] for e in events if e['event'] == 'grandchild'][0]
        for _ in range(50):
            try:
                state = Path(f'/proc/{pid}/stat').read_text().rsplit(')', 1)[1].split()[0]
            except FileNotFoundError:
                break
            if state == 'Z':
                break
            time.sleep(0.1)
        else:
            self.fail('owned grandchild survived timeout')
        result, _ = self.run_worker('--model', 'glm53', '--max-output', '4096', '--prompt-file', str(self.prompt), mode='huge')
        self.assertEqual((result.returncode, result.stdout), (8, ''))

    def test_transport_parser_is_strict(self):
        spec = importlib.util.spec_from_file_location('perplexity_worker', WORKER)
        worker = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(worker)
        good = b'{"state": "ok", "answer": "A", "citations": [{"title": null, "url": "https://x.invalid"}]}\n'
        self.assertEqual(worker.parse_transport(good, 4096), ('ok', 'A', [{'title': '', 'url': 'https://x.invalid'}]))
        self.assertEqual(worker.parse_transport(b'{"state": "auth_missing"}\n', 4096)[0], 'auth_missing')
        self.assertEqual(worker.parse_transport(b'{"state": "ok", "answer": "' + b'a' * 5000 + b'", "citations": []}\n',
                                                4096)[0], 'output_overflow')
        for raw in (b'{"state": "ok", "state": "ok", "answer": "A", "citations": []}\n',
                    b'{"state": "ok", "answer": NaN, "citations": []}\n',
                    b'{"state": "ok", "answer": "A", "citations": [], "n": Infinity}\n',
                    b'{"state": "ok", "answer": "A", "citations": [], "raw_data": {}}\n',
                    b'{"state": "ok", "answer": "A", "citations": [{"title": "t", "url": "file:///etc/passwd"}]}\n',
                    b'{"state": "ok", "answer": " ", "citations": []}\n',
                    b'{"state": "fine"}\n', b'{"state": []}\n', b'{"state": {"ok": 1}}\n', b'{"state": "ok", "answer": "A", "citations": []}',
                    b'{"state": "auth_missing"}\n{"state": "ok"}\n', b'[]\n', b'',
                    b'{"state": ' + b'[' * 2000 + b'0' + b']' * 2000 + b'}\n'):
            with self.assertRaises((ValueError, UnicodeDecodeError), msg=raw):
                worker.parse_transport(raw, 4096)

    def test_sigterm_stops_owned_group_and_records_interruption(self):
        receipts = self.private_dir('interrupted receipts')
        log = self.base / 'interrupted events.jsonl'
        env = dict(os.environ, FAKE_PPLX_LOG=str(log), FAKE_PPLX_MODE='sleep', FAKE_PPLX_TOKEN=SECRET)
        process = subprocess.Popen([str(self.python), '-B', str(WORKER), '--model', 'glm53',
                                    '--prompt-file', str(self.prompt), '--receipt-dir', str(receipts)],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        grandchild = None
        try:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                events = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
                pids = [e['pid'] for e in events if e['event'] == 'grandchild']
                if pids:
                    grandchild = pids[0]
                    break
                self.assertIsNone(process.poll(), 'adapter stopped before the fake query began')
                time.sleep(0.05)
            self.assertIsNotNone(grandchild, 'fake query did not start')
            process.send_signal(signal.SIGTERM)
            stdout, stderr = process.communicate(timeout=15)
            self.assertEqual((process.returncode, stdout), (130, ''))
            self.assertIn('interrupted', stderr)
            self.assertNotIn('Traceback', stderr)
            self.assertNotIn(SECRET, stderr)
            for _ in range(50):
                try:
                    state = Path(f'/proc/{grandchild}/stat').read_text().rsplit(')', 1)[1].split()[0]
                except FileNotFoundError:
                    break
                if state == 'Z':
                    break
                time.sleep(0.05)
            else:
                self.fail('owned query grandchild survived SIGTERM')
            record = json.loads(next(receipts.glob('*/receipt.json')).read_text())
            self.assertEqual((record['outcome'], record['exit_code'], record['ask_may_have_run']),
                             ('interrupted', 130, True))
        finally:
            if process.poll() is None:
                process.kill()
                process.communicate()
            if grandchild is not None:
                try:
                    os.kill(grandchild, signal.SIGKILL)
                except ProcessLookupError:
                    pass


if __name__ == '__main__':
    if shutil.which('true') is None:
        sys.exit('needs a POSIX environment')
    unittest.main(verbosity=1)
