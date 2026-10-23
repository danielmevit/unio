#!/usr/bin/env python3
# Unio — Copyright (C) 2026 Daniel Mitev
# Public attribution: Daniel Mevit (@danielmevit)
# Original project: https://github.com/danielmevit/unio
# SPDX-License-Identifier: AGPL-3.0-only
# Additional attribution/origin terms: NOTICE (AGPLv3 sections 7(b), 7(c)).
# See LICENSE and NOTICE; distributed without warranty.
"""Additional contract regressions inside the shell suite's disposable checkout."""
import copy
import json
import os
from pathlib import Path
import subprocess
import time

root = Path.cwd().parent
wt = root / 'wt/mock'
at = str(Path(os.environ['UNIO_BIN_DIR']) / 'unio')
conf = Path(os.environ['UNIO_CONF_DIR']) / 'agents.conf'
result = root / 'coord/results/mock/evidence.json'
tf = root / 'coord/tasks/evidence.md'
count = 0


def call(*args, code=0, env=None):
    # These M1 fixtures intentionally rerun old failure scenarios. The test
    # operator grants each blocked invocation; the separate brake suite must
    # prove that unapproved invocations cannot reach a mock provider.
    if args and args[0] == 'run':
        retry_file = root / 'coord/retries' / args[2] / 'state.json'
        if retry_file.exists() and json.loads(retry_file.read_text())['failed_attempts'] >= 2:
            grant = subprocess.run([at, 'allow-retry', args[2]], capture_output=True, text=True)
            assert grant.returncode == 0, grant.stderr
    p = subprocess.run([at, *args], capture_output=True, text=True,
                       env=dict(os.environ, **(env or {})))
    assert p.returncode == code, (args, p.returncode, code, p.stdout, p.stderr)
    return p


def git(*args, cwd=wt):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def check(label, condition=True):
    global count
    assert condition, label
    count += 1
    print('  quality: ' + label)


def configuration(review="printf '%s\\n' '```unio-findings-v1' '{\"schema_version\":1,\"findings\":[]}' '```' 'VERDICT: APPROVE'", extra=''):
    conf.write_text("mock=bash -c 'echo evidence >> hello.txt; git add hello.txt; git commit -qm evidence'\n"
                    "noop=bash -c 'exit 0'\nrev=bash -c " + __import__('shlex').quote(review) + '\n' + extra)


def data(task='evidence'):
    return json.loads(call('result', 'mock', task).stdout)


def verify():
    call('verify', 'mock', 'evidence')


def ready():
    call('run', 'mock', 'evidence')
    verify()
    call('review', 'mock', 'evidence', 'rev')
    check('current success persists and reloads', data()['ready_for_human_review'])


tf.write_text('# Evidence\n## Allowed scope\n- *\n## Validate\n$ test -s hello.txt\n')
configuration()
call('result', 'mock', 'evidence', code=2)
check('missing result fails closed')
call('review', 'mock', 'evidence', 'rev', code=2)
check('review requires structured validation')
ready()
d = data()
check('separate human and integration states', d['human']=={'state':'pending'} and d['integration']=={'state':'not_attempted'})
call('run', 'mock', 'evidence')
d = data()
check('new run clears old validation/review', d['validation']['state']=='not_run' and d['review']['state']=='not_run' and not d['ready_for_human_review'])
verify()
for label, command, code, state in [
    ('verdict-only approve', 'printf "VERDICT: APPROVE\\n"', 0, 'approved'),
    ('request changes', 'printf "VERDICT: REQUEST-CHANGES\\n"', 1, 'changes_requested'),
    ('stderr approval', 'printf "VERDICT: APPROVE\\n" >&2', 2, 'unknown'),
    ('no verdict', 'printf done', 2, 'unknown'),
    ('malformed verdict', 'printf "VERDICT: APPROVED\\n"', 2, 'unknown'),
    ('indented verdict', 'printf " VERDICT: APPROVE\\n"', 2, 'unknown'),
    ('duplicate verdict', 'printf "VERDICT: APPROVE\\nVERDICT: APPROVE\\n"', 2, 'unknown'),
    ('contradictory verdict', 'printf "VERDICT: APPROVE\\nVERDICT: REQUEST-CHANGES\\n"', 2, 'unknown'),
    ('process failed with approval', 'printf "VERDICT: APPROVE\\n"; exit 7', 1, 'failed'),
]:
    configuration(command)
    call('review','mock','evidence','rev',code=code)
    d=data()
    check('review '+label, d['review']['state']==state and d['review']['process_exit_code']==(7 if state=='failed' else 0))
    if label == 'verdict-only approve':
        projection = d['review_current']
        check('verdict-only approval remains visible but extraction is incomplete',
              not projection['machine_review_ready'] and not d['ready_for_human_review']
              and not projection['extraction_complete'])
configuration('sleep 3; printf "VERDICT: APPROVE\\n"')
call('review','mock','evidence','rev',code=1,env={'UNIO_REVIEW_TIMEOUT':'1'})
check('timeout process exit preserved',data()['review']['process_exit_code']==124)
configuration()
ready()

# Every dimension independently invalidates already-ready evidence.
original_task = tf.read_text()
tf.write_text(original_task+'changed task\n')
check('task hash stale', data()['stale'] and not data()['ready_for_human_review'])
call('review','mock','evidence','rev',code=2)
tf.write_text(original_task)
hello=wt/'hello.txt'; original=hello.read_text()
hello.write_text(original+'dirty\n')
check('tracked content stale',data()['stale'])
git('add','hello.txt')
check('index stale',data()['stale'])
git('restore','--staged','hello.txt')
hello.write_text(original)
git('update-index','--assume-unchanged','hello.txt')
hello.write_text(original+'hidden edit\n')
check('assume-unchanged content is hashed',data()['stale'])
# Git diff/status skip flagged paths, so scope and review would miss the edit.
p=call('verify','mock','evidence',code=2)
check('assume-unchanged edit refused by verify','assume-unchanged/skip-worktree' in p.stderr and 'hello.txt' in p.stderr)
call('handoff','mock','evidence',code=2)
check('assume-unchanged edit refused by handoff')
hello.write_text(original)
git('update-index','--no-assume-unchanged','hello.txt')
git('update-index','--skip-worktree','hello.txt')
hello.write_text(original+'hidden edit\n')
call('verify','mock','evidence',code=2)
check('skip-worktree edit refused by verify')
hello.write_text(original)
git('update-index','--no-skip-worktree','hello.txt')
ready()
# A flag alone leaves the hash current, but review cannot prove complete material.
git('update-index','--skip-worktree','hello.txt')
call('review','mock','evidence','rev',code=2)
check('flagged index refuses review material',data()['review']['state']=='unknown' and not data()['review']['material_complete'])
git('update-index','--no-skip-worktree','hello.txt')
special=wt/'space " quote\\ tab\tline\nž.txt'
special.write_text('one')
check('JSON-special untracked filename',data()['stale'])
verify()
first=data()['revision']['worktree_sha256']
special.write_text('two')
check('untracked content changes hash',data()['current_revision']['worktree_sha256']!=first)
verify()
call('review','mock','evidence','rev',code=2)
check('dirty review refused without invocation',data()['review']['state']=='unknown' and not data()['review']['material_complete'])
special.unlink()
git('commit','--allow-empty','-qm','candidate advanced')
check('candidate commit stale',data()['stale'])
ready()
git('commit','--allow-empty','-qm','base advanced',cwd=root/'repo')
check('base commit stale',data()['stale'])
ready()

fifo=wt/'pipe'
os.mkfifo(fifo)
call('result','mock','evidence',code=2)
check('FIFO refused without blocking')
fifo.unlink()
nested=wt/'nested'
git('init','-q',str(nested))
(nested/'file').write_text('nested')
call('result','mock','evidence',code=2)
check('nested repository refuses incomplete hash')
__import__('shutil').rmtree(nested)
link=wt/'link'
link.symlink_to('/a/nonexistent/outside-target')
verify()
linkhash=data()['revision']['worktree_sha256']
link.unlink(); link.symlink_to('/different-target')
check('symlink target hashed without dereference',data()['current_revision']['worktree_sha256']!=linkhash)
link.unlink()
ready()

# A check or reviewer modifying the candidate cannot issue fresh evidence.
tf.write_text('# Evidence\n## Allowed scope\n- *\n## Validate\n$ echo mutation >> hello.txt\n')
call('run','mock','evidence')
call('verify','mock','evidence',code=2)
check('candidate changes during validation',data()['validation']['state']=='incomplete' and data()['stale'])
tf.write_text(original_task)
configuration()
ready()
configuration('printf mutation >> "$QUALITY_WT/hello.txt"; printf "VERDICT: APPROVE\\n"')
call('review','mock','evidence','rev',code=2,env={'QUALITY_WT':str(wt)})
check('candidate changes during review',data()['review']['state']=='unknown' and data()['stale'])
configuration()
ready()

# Contradictory JSON must not manufacture readiness after a refresh.
good=result.read_text()
for label, mutate in [
    ('process exit',lambda d:d['process'].update(exit_code=7)),
    ('zero checks',lambda d:d['validation'].update(checks_run=0)),
    ('failed checks',lambda d:d['validation'].update(checks_failed=1)),
    ('unknown scope',lambda d:d['validation'].update(scope='UNCHECKED')),
    ('review exit',lambda d:d['review'].update(process_exit_code=7)),
    ('partial material',lambda d:d['review'].update(material_complete=False)),
    ('missing evidence revision',lambda d:d['review'].update(revision=None)),
    ('human forged',lambda d:d.update(human={'state':'accepted'})),
]:
    altered=json.loads(good); mutate(altered); result.write_text(json.dumps(altered))
    call('result','mock','evidence',code=2)
    check('malformed state rejects '+label)
result.write_text('{broken')
call('result','mock','evidence',code=2)
call('handoff','mock','evidence',code=2)
check('malformed JSON fails closed for result and handoff')
result.write_text(good)

# One real flock blocks run, review, and packet creation.
lock=root/'coord/.locks/mock.lock'
with lock.open('a') as f:
    __import__('fcntl').flock(f,__import__('fcntl').LOCK_EX)
    for operation in ('run','review','handoff','verify'):
        call(operation,'mock','evidence',code=1)
        check(operation+' refuses worker lock')
    call('verify','mock','evidence','locked',code=1)
    check('public verify argument cannot bypass held lock')

# Review itself owns the lock throughout its provider call.
# The reviewer holds the lock until released, not for a fixed sleep: on a slow
# drive the two refused calls below could outlast a sleep and race the lock.
marker=root/'review-started'; release=root/'review-release'
configuration('touch "$QUALITY_MARKER"; i=0; while [ ! -e "$QUALITY_RELEASE" ] && [ $i -lt 1200 ]; do sleep .05; i=$((i+1)); done; printf "VERDICT: APPROVE\\n"')
review=subprocess.Popen([at,'review','mock','evidence','rev'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,
                        env=dict(os.environ,QUALITY_MARKER=str(marker),QUALITY_RELEASE=str(release)))
for _ in range(1200):
    if marker.exists(): break
    time.sleep(.05)
assert marker.exists()
call('run','mock','evidence',code=1)
call('handoff','mock','evidence',code=1)
release.touch()
out,err=review.communicate(timeout=120)
check('review holds worker lock',review.returncode==0)
configuration()

# Handoff is unique context only, with uncommitted data still in the checkout.
(wt/'local.txt').write_text('not a backup')
packet1=Path(call('handoff','mock','evidence').stdout.strip())
packet2=Path(call('handoff','mock','evidence').stdout.strip())
check('unique atomic handoff',packet1!=packet2 and packet1.is_dir() and packet2.is_dir() and not list(packet1.parent.glob('.pending-*')))
check('handoff contains only context',set(p.name for p in packet1.iterdir())=={'task.md','result.json','revision.json','changed-files.json','HANDOFF.md'})
check('handoff states source-only untracked work','local.txt' in (packet1/'changed-files.json').read_text() and 'NOT a backup' in (packet1/'HANDOFF.md').read_text() and not (packet1/'local.txt').exists())
check('handoff result is current and stale',json.loads((packet1/'result.json').read_text())['stale'])
(wt/'local.txt').unlink()
absent=root/'coord/tasks/absent.md'; absent.write_text(original_task)
newpacket=Path(call('handoff','mock','absent').stdout.strip())
check('handoff without result has explicit unknown states',json.loads((newpacket/'result.json').read_text())['process']['state']=='not_run')
for operation in ('result','handoff'):
    call(operation,'../escape','evidence',code=1)
    check(operation+' invalid IDs refused')
outside=root/'outside'; outside.mkdir()
escape=root/'coord/handoffs/mock/escape'; escape.symlink_to(outside,target_is_directory=True)
(root/'coord/tasks/escape.md').write_text(original_task)
call('handoff','mock','escape',code=2)
check('handoff symlink escape refused',not list(outside.iterdir()))
result.unlink(); result.symlink_to(outside/'result.json')
call('verify','mock','evidence',code=2)
check('result symlink refused',not (outside/'result.json').exists())
result.unlink(); result.write_text(good)

# A failed post-run snapshot keeps the worker's real exit, report and ledger line.
(root/'coord/tasks/snapfail.md').write_text(original_task)
snap=root/'coord/results/mock/snapfail.json'
ledger=root/'coord/reports/ledger.jsonl'
for code in (7, 0):
    conf.write_text(f"mock=bash -c 'echo snap >> hello.txt; git add hello.txt; git commit -qm snap; mkfifo pipe; exit {code}'\n")
    p=call('run','mock','snapfail',code=code or 2,env={'UNIO_AUTO_VERIFY':'1'})
    d=json.loads(snap.read_text())
    check(f'snapshot failure keeps worker exit {code}',d['process']['exit_code']==code
          and d['process']['state']==('failed' if code else 'succeeded') and d['process']['post_run_snapshot']=='failed'
          and d['stale'] and not d['ready_for_human_review'] and 'post-run snapshot failed' in p.stderr)
    last=json.loads(ledger.read_text().splitlines()[-1])
    check(f'snapshot failure still writes report and ledger ({code})',last['event']=='run' and last['task']=='snapfail'
          and last['exit']==code and last['snapshot_failed']==1
          and f'exit={code}' in (root/'coord/reports/snapfail.md').read_text().split('## run ')[-1])
    call('result','mock','snapfail',code=2)
    (wt/'pipe').unlink()
    d=data('snapfail')
    check(f'unbound process evidence stays stale after cleanup ({code})',d['stale'] and not d['ready_for_human_review'])
configuration()

# Availability never executes even hostile configured commands.
marker=root/'availability-executed'
configuration(extra='literal=LANG="en US" env X=1 /usr/bin/true\nmissing=env X=1 /no/such/binary\n'
                    'wrapper=bash -c "touch '+str(marker)+'"\nquoted=env X="a b" "/usr/bin/true"\n')
agents=json.loads(call('agents','--json').stdout)['agents']
mapping={a['name']:a for a in agents}
check('assignments/env and quoted executable resolve',mapping['literal']['binary']['present'] is True and mapping['quoted']['binary']['present'] is True)
check('missing and ambiguous binaries truthful',mapping['missing']['binary']['present'] is False and mapping['wrapper']['binary']['present'] is None)
check('no availability command executed',not marker.exists())
check('availability authentication/capacity unknown',all(a['authentication']=='unknown' and a['capacity']=='unknown' and a['execution_boundary']=='trusted_host' for a in agents))
call('off','literal','5m')
a={a['name']:a for a in json.loads(call('agents','--json').stdout)['agents']}['literal']
check('operator retry recorded honestly',a['bench']['off'] and a['bench']['operator_retry_at']>time.time() and 'not a provider reset' in call('agents').stdout)
# Every shipped line passes "$(cat "$TASKFILE")": quoted arguments must not hide
# the program, while operators or expansion in the program word stay unknown.
configuration(extra='shipped=FOO="$HOME/x" /usr/bin/true -p "$(cat "$TASKFILE")" --model m\n'
                    'chained=/usr/bin/true; /usr/bin/false\npiped=/usr/bin/true | tee out\n'
                    'expanded=$(echo /usr/bin/true) arg\nvariable=$HOME/bin/tool -p x\n')
mapping={a['name']:a for a in json.loads(call('agents','--json').stdout)['agents']}
check('quoted shell syntax in arguments still resolves the program',mapping['shipped']['binary']['present'] is True
      and 'shipped: installed=yes' in call('agents').stdout)
check('operators or expansion in the program stay unknown',all(mapping[n]['binary']['present'] is None for n in ('chained','piped','expanded','variable')))
# Fresh lines read the task on stdin: one plain input redirect keeps the program
# known; any other redirect, here-doc or process substitution stays unknown.
configuration(extra='stdin=/usr/bin/true -p < "$TASKFILE"\nmissingstdin=/no/such/binary - < "$TASKFILE"\n'
                    'stdout=/usr/bin/true > out\nheredoc=/usr/bin/true <<EOF\nprocsub=/usr/bin/true < <(cat x)\n'
                    'redirchain=/usr/bin/true < "$TASKFILE"; /usr/bin/false\n')
mapping={a['name']:a for a in json.loads(call('agents','--json').stdout)['agents']}
check('plain stdin redirect keeps the program known',mapping['stdin']['binary']=={'value':'/usr/bin/true','present':True}
      and mapping['missingstdin']['binary']['present'] is False)
check('other redirects stay unknown',all(mapping[n]['binary']['present'] is None for n in ('stdout','heredoc','procsub','redirchain')))
conf.write_text('mock=FOO="a b" /usr/bin/true -p "$(cat "$TASKFILE")"\nnoop=/no/such/binary\n')
out=subprocess.run([at,'doctor'],capture_output=True,text=True)
out=out.stdout+out.stderr
check('doctor accepts env-prefixed agent lines but flags a missing binary',
      "agent 'mock' binary not on PATH" not in out and "agent 'noop' binary not on PATH" in out)
configuration()
print(f'quality contract regressions: {count} passed')
