#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Fresh shipped defaults pass >180000-byte prompts to fake provider CLIs by
stdin/file, never argv: native run and native review, offline only."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

source = Path(__file__).resolve().parent.parent
ARG_MAX_ONE = 131072  # Linux MAX_ARG_STRLEN: the single-argument bound that failed
AGENTS = ('claude', 'codex', 'antigravity', 'opencode', 'grok')
EXE = {'claude': 'claude', 'codex': 'codex', 'antigravity': 'agy', 'opencode': 'opencode', 'grok': 'grok'}
REVIEWER = {'claude': 'antigravity', 'antigravity': 'grok', 'codex': 'opencode', 'opencode': 'claude', 'grok': 'codex'}
count = 0


def check(label, ok):
    global count
    assert ok, label
    count += 1
    print('ok', label, flush=True)


# One fake CLI for every provider. It asserts the shipped flags, recovers the
# prompt through the documented transport only, and records what it received.
STUB = r'''#!/usr/bin/env python3
import hashlib, json, os, subprocess, sys
from pathlib import Path
agent = os.environ['STUB_AGENT_' + Path(sys.argv[0]).name.upper()]
argv = sys.argv[1:]
stdin = sys.stdin.buffer.read()
def after(flag):
    assert argv.count(flag) == 1, argv
    return argv[argv.index(flag) + 1]
tf = os.environ['TASKFILE']
otf = os.environ['UNIO_ORIGINAL_TASKFILE']
if agent == 'claude':
    assert argv == ['-p', '--dangerously-skip-permissions'], argv
    payload = stdin
elif agent == 'codex':
    assert argv == ['exec', '--sandbox', 'danger-full-access', '--skip-git-repo-check', '-'], argv
    payload = stdin
elif agent == 'grok':
    assert argv == ['--prompt-file', tf, '--always-approve'], argv
    payload = Path(after('--prompt-file')).read_bytes()
elif agent == 'opencode':
    assert argv[:2] == ['run', '--auto'] and argv[3:] == ['--file', tf], argv
    assert 'read the ENTIRE file' in argv[2] and argv[2].endswith('File: ' + tf), argv
    payload = Path(after('--file')).read_bytes()
elif agent == 'antigravity':
    assert argv[0] == '-p' and argv[2:] == ['--dangerously-skip-permissions', '--print-timeout', '55m'], argv
    assert 'read the ENTIRE file' in argv[1] and 'every chunk through its last line' in argv[1], argv
    payload = Path(argv[1].rsplit('File: ', 1)[1]).read_bytes()
original = Path(otf).read_bytes()
review = original.startswith(b'You are an independent code reviewer')
delimiter = b'--- original review material follows ---\n' if review else b'--- original run material follows ---\n'
receipts = Path(os.environ['STUB_RECEIPTS'])
n = len(list(receipts.iterdir()))
(receipts / f'{n:03d}-{agent}.json').write_text(json.dumps(dict(
    agent=agent, phase='review' if review else 'run', argv=argv, cwd=os.getcwd(), taskfile=tf, original_taskfile=otf,
    taskfile_sha=hashlib.sha256(Path(tf).read_bytes()).hexdigest(), stdin_len=len(stdin),
    payload_len=len(payload), payload_sha=hashlib.sha256(payload).hexdigest(),
    original_len=len(original), original_sha=hashlib.sha256(original).hexdigest(),
    has_authority=b'UNIO_ORIGINAL_TASKFILE' in payload,
    has_header_prefix=payload.startswith(b'# Unio work-policy header (effective prompt; the original task is unchanged)\n'),
    has_delimiter=delimiter in payload,
    exact_match=(payload == payload[:payload.index(delimiter) + len(delimiter)] + original) if delimiter in payload else False,
    max_arg=max(len(a.encode()) for a in sys.argv), argv_bytes=sum(len(a.encode()) + 1 for a in sys.argv),
    max_env=max(len(k) + len(v) for k, v in os.environb.items()),
    sentinel_in_argv=any(b'PAYLOAD-SENTINEL' in os.fsencode(a) for a in sys.argv),
    sentinel_in_env=any(b'PAYLOAD-SENTINEL' in v for v in os.environb.values()),
    ends=original[-200:].decode('utf-8'))))
if os.environ.get('STUB_EXIT'):
    sys.exit(int(os.environ['STUB_EXIT']))
if review:
    print('reviewed full material\n```unio-findings-v1\n{"schema_version":1,"findings":[]}\n```\nVERDICT: APPROVE', flush=True)
else:
    name = f'out-{agent}.txt'
    Path(name).write_text('done\n')
    subprocess.run(['git', 'add', name], check=True)
    if subprocess.run(['git', 'diff', '--cached', '--quiet']).returncode:
        subprocess.run(['git', 'commit', '-qm', 'offline ' + agent], check=True)
'''

with tempfile.TemporaryDirectory(prefix='prompt-transport-') as directory:
    base = Path(directory)
    root = base / 'project with spaces'
    repo = root / 'repo'
    repo.mkdir(parents=True)
    stub = base / 'stub dir'
    stub.mkdir()
    receipts = base / 'receipts'
    receipts.mkdir()
    marker = base / 'shell-executed'
    env = dict(os.environ, UNIO_BIN_DIR=str(base / 'bin'), UNIO_CONF_DIR=str(base / 'conf'),
               UNIO_COMPLETION_DIR=str(base / 'completion'), UNIO_AUTO_VERIFY='0', UNIO_AUTO_OFF='0',
               UNIO_AUTO_SYNC='0', UNIO_TIMEOUT='120', UNIO_REVIEW_TIMEOUT='120', UNIO_VERIFY_TIMEOUT='60',
               GIT_AUTHOR_NAME='mock', GIT_COMMITTER_NAME='mock', GIT_AUTHOR_EMAIL='mock@example.invalid',
               GIT_COMMITTER_EMAIL='mock@example.invalid', STUB_RECEIPTS=str(receipts))
    env.pop('STUB_EXIT', None)
    for agent in AGENTS:
        (stub / EXE[agent]).write_text(STUB)
        (stub / EXE[agent]).chmod(0o755)
        env['STUB_AGENT_' + EXE[agent].upper()] = agent
    env['PATH'] = str(stub) + os.pathsep + env['PATH']
    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env, check=True, capture_output=True)
    at = str(base / 'bin/unio')
    config = base / 'conf/agents.conf'

    def git(*args, cwd=repo):
        return subprocess.run(['git', *args], cwd=cwd, env=env, check=True, capture_output=True)

    def call(*args, code=0, extra=None):
        p = subprocess.run([at, *args], cwd=repo, env=dict(env, **(extra or {})), capture_output=True)
        assert p.returncode == code, (args, p.returncode, code, p.stdout[-2000:], p.stderr[-2000:])
        return p

    def launches():
        return [json.loads(p.read_text()) for p in sorted(receipts.iterdir())]

    git('init', '-q', '-b', 'main')
    (repo / 'seed.txt').write_text('seed\n')
    git('add', 'seed.txt')
    git('commit', '-qm', 'seed')
    call('init', *AGENTS)
    agents = {a['name']: a for a in json.loads(call('agents', '--json').stdout)['agents']}
    check('fresh defaults keep availability known through a plain stdin redirect',
          all(agents[a]['binary'] == dict(value=EXE[a], present=True) for a in AGENTS))

    # Literal shell metacharacters and multibyte UTF-8; a shell that evaluated
    # the prompt would create the marker file.
    hostile = (f'PAYLOAD-SENTINEL $(touch "{marker}") `touch "{marker}"` ; touch "{marker}" | && || '
               f"'\"\\ ${{HOME}} $HOME * ? [a] ~ ! # < > é 漢字 🙂 ")
    filler = ''
    while len(filler.encode()) < 181000:
        filler += f'Line {len(filler)}: {hostile}\n'

    def task(name, agent):
        text = (f'# Task {name}\n## Goal\n{filler}\n## Allowed scope\n- out-{agent}.txt\n'
                f'## Validate\n$ test "$(cat out-{agent}.txt)" = done\n')
        path = root / 'coord/tasks' / f'{name}.md'
        path.write_bytes(text.encode())
        return path.read_bytes()

    for agent in AGENTS:
        before = len(launches())
        data = task('big-' + agent, agent)
        call('run', agent, 'big-' + agent)
        new = launches()[before:]
        check(f'{agent}: run launched the fake provider exactly once', len(new) == 1 and new[0]['phase'] == 'run')
        r = new[0]
        check(f'{agent}: run prompt is the complete task, byte/hash identical ({len(data)} bytes)',
              len(data) > 180000 and r['original_len'] == len(data)
              and r['original_sha'] == hashlib.sha256(data).hexdigest()
              and r['payload_sha'] == r['taskfile_sha']
              and r['has_authority'] and r['has_header_prefix'] and r['has_delimiter'] and r['exact_match'])
        check(f'{agent}: run argv and environment stay bounded and prompt-free',
              r['max_arg'] < 1024 and r['argv_bytes'] < 4096 and r['max_env'] < ARG_MAX_ONE
              and not r['sentinel_in_argv'] and not r['sentinel_in_env'])
        check(f'{agent}: run cwd is the worker checkout', Path(r['cwd']) == (root / 'wt' / agent).resolve())
        check(f'{agent}: stdin carries the task only for stdin transports',
              r['stdin_len'] == (r['payload_len'] if agent in ('claude', 'codex') else 0))
        call('verify', agent, 'big-' + agent)
        result = json.loads(call('result', agent, 'big-' + agent).stdout)
        check(f'{agent}: native process succeeded and validation passed',
              result['process']['state'] == 'succeeded' and result['validation']['state'] == 'passed')

    check('no prompt text was executed by a shell', not marker.exists())

    for agent in AGENTS:
        reviewer = REVIEWER[agent]
        before = len(launches())
        call('review', agent, 'big-' + agent, reviewer)
        new = launches()[before:]
        check(f'{reviewer} reviewing {agent}: exactly one native review launch',
              len(new) == 1 and new[0]['agent'] == reviewer and new[0]['phase'] == 'review')
        r = new[0]
        task_bytes = (root / 'coord/tasks' / f'big-{agent}.md').read_bytes()
        check(f'{reviewer}: complete material file delivered byte/hash identical ({r["payload_len"]} bytes)',
              r['payload_len'] > ARG_MAX_ONE and r['payload_sha'] == r['taskfile_sha']
              and r['has_authority'] and r['has_header_prefix'] and r['has_delimiter'] and r['exact_match']
              and r['ends'].endswith('VERDICT: APPROVE or VERDICT: REQUEST-CHANGES\n'))
        check(f'{reviewer}: material holds the whole task, never clipped', r['original_len'] > len(task_bytes))
        check(f'{reviewer}: review argv and environment stay bounded and prompt-free',
              r['max_arg'] < 1024 and r['argv_bytes'] < 4096 and r['max_env'] < ARG_MAX_ONE
              and not r['sentinel_in_argv'] and not r['sentinel_in_env'])
        check(f'{reviewer}: review runs beside the material file, not in the worker checkout',
              Path(r['cwd']) == Path(r['original_taskfile']).parent and Path(r['cwd']) != (root / 'wt' / agent).resolve())
        result = json.loads(call('result', agent, 'big-' + agent).stdout)
        check(f'{reviewer}: actual verdict and readiness recorded',
              result['review']['state'] == 'approved' and result['review']['material_complete']
              and result['ready_for_human_review'] is True)
    check('antigravity review crossed the exact single-argument bound that failed',
          any(r['agent'] == 'antigravity' and r['phase'] == 'review' and r['payload_len'] > ARG_MAX_ONE for r in launches()))
    check('no review material was executed by a shell', not marker.exists())

    # A failed provider keeps its real exit and is not relaunched.
    task('fail-grok', 'grok')
    before = len(launches())
    p = call('run', 'grok', 'fail-grok', code=7, extra=dict(STUB_EXIT='7'))
    result = json.loads(call('result', 'grok', 'fail-grok').stdout)
    check('failed fake provider exit preserved with one launch',
          len(launches()) == before + 1 and result['process']['state'] == 'failed' and result['process']['exit_code'] == 7)
    before = len(launches())
    call('review', 'claude', 'big-claude', 'codex', code=1, extra=dict(STUB_EXIT='5'))
    result = json.loads(call('result', 'claude', 'big-claude').stdout)
    check('failed fake reviewer exit preserved with one launch',
          len(launches()) == before + 1 and result['review']['state'] == 'failed'
          and result['review']['process_exit_code'] == 5 and not result['ready_for_human_review'])

    # Missing task and incomplete material are refused before any provider starts.
    before = len(launches())
    call('run', 'codex', 'no-such-task', code=1)
    check('missing task refused before the fake provider', len(launches()) == before)
    # Material over the 300000-byte bound is refused whole, never clipped.
    huge = task('huge-opencode', 'opencode')
    (root / 'coord/tasks/huge-opencode.md').write_bytes(huge.replace(b'## Goal\n', b'## Goal\n' + filler.encode(), 1))
    call('run', 'opencode', 'huge-opencode')
    call('verify', 'opencode', 'huge-opencode')
    before = len(launches())
    p = call('review', 'opencode', 'huge-opencode', 'grok', code=2)
    result = json.loads(call('result', 'opencode', 'huge-opencode').stdout)
    check('oversized review material refused before the fake reviewer',
          len(launches()) == before and not result['review']['material_complete']
          and 'incomplete review material' in (p.stdout + p.stderr).decode())

    # Doctor: fresh defaults are clean; legacy whole-file argv lines are only
    # reported, never executed or rewritten.
    p = subprocess.run([at, 'doctor'], cwd=repo, env=env, capture_output=True, text=True)
    check('doctor has no argv-expansion warning for fresh defaults', 'Argument list too long' not in p.stdout + p.stderr)
    legacy = ('# owner settings\n'
              'claude=claude -p "$(cat "$TASKFILE")" --dangerously-skip-permissions --model owner-model\n'
              'codex=codex exec -c model_reasoning_effort=xhigh "$(cat "$TASKFILE")"\n'
              'antigravity=agy -p "$(cat "$TASKFILE")" --dangerously-skip-permissions --print-timeout 55m\n'
              'opencode=opencode run --auto -m owner/choice "$(<"$TASKFILE")"\n'
              'grok=grok -p "$(cat $TASKFILE)" --always-approve\n'
              'custom=my-wrapper --task "$TASKFILE"\n')
    config.write_text(legacy)
    original = config.read_bytes()
    stat = config.stat()
    before = len(launches())
    p = subprocess.run([at, 'doctor'], cwd=repo, env=env, capture_output=True, text=True)
    out = p.stdout + p.stderr
    check('doctor warns for each legacy whole-file argv line with migration guidance',
          all(f"agent '{a}' expands the whole task file" in out for a in AGENTS)
          and "agent 'custom' expands" not in out and '--prompt-file' in out and 'Existing settings preserved' in out)
    check('doctor is read-only: no provider launch, configuration bytes unchanged',
          len(launches()) == before and config.read_bytes() == original and config.stat().st_mtime_ns == stat.st_mtime_ns)

    # The legacy line really fails at the bound; the offline stub never starts.
    task('legacy-agy', 'antigravity')
    p = call('run', 'antigravity', 'legacy-agy', code=126)
    log = (root / 'coord/reports/legacy-agy.log').read_text()
    check('legacy whole-file argv default reproduces Argument list too long without a launch',
          'Argument list too long' in log and len(launches()) == before)

    subprocess.run(['bash', str(source / 'unio-install.sh')], env=env, check=True, capture_output=True)
    check('reinstall preserves custom model/effort/command bytes', config.read_bytes() == original)

print(f'prompt transport: {count} checks passed')
