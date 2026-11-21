import asyncio
import json
from pathlib import Path
import subprocess
import sys
import tempfile

SPAWN = '''
from pathlib import Path
import os, subprocess, sys, time

root = Path('/trial') / sys.argv[1]
if sys.argv[2] == 'wait':
    worker = subprocess.run([sys.executable, '-c', sys.orig_argv[2], sys.argv[1], 'worker'],
                            start_new_session=True)
    raise SystemExit(worker.returncode)
(root / 'published').write_text('before deadline')
if sys.argv[2] == 'complete':
    (root / 'finished').write_text('on time')
    raise SystemExit(0)

pid = os.getpid()
assert pid == os.getpgrp() == os.getsid(0)
ticks = Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
script = 'import pathlib,sys,time;time.sleep(3);pathlib.Path(sys.argv[1]).touch()'
child = subprocess.Popen([sys.executable, '-c', script, str(root / 'child-late')])
(root / 'owner').write_text(f'{pid} {ticks}')
time.sleep(3)
(root / 'parent-late').touch()
child.wait()
'''

STOP = '''
from pathlib import Path
import os, signal, sys

file = Path('/trial') / sys.argv[1] / 'owner'
pid_text, ticks = file.read_text().split()
pid = int(pid_text)
assert pid > 1 and os.getsid(pid) == os.getpgid(pid) == pid
assert Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19] == ticks
os.killpg(pid, signal.SIGTERM)
'''


async def run_case(container, root, label):
    case = root / label
    case.mkdir()
    mode = 'complete' if label == 'natural-completion' else 'wait'
    session = await asyncio.create_subprocess_exec('docker', 'exec', container, 'python3', '-c',
        SPAWN, label, mode, stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    stop_calls = 0

    async def await_agent():
        nonlocal stop_calls
        try:
            out, _ = await session.communicate()
            if session.returncode:
                raise RuntimeError(out.decode())
        except asyncio.CancelledError:
            if label == 'timeout-with-cleanup':
                stop_calls += 1
                stop = await asyncio.create_subprocess_exec('docker','exec',container,'python3','-c',STOP,label)
                assert await asyncio.wait_for(stop.wait(), timeout=2) == 0
                await asyncio.wait_for(session.wait(), timeout=2)
            raise

    if mode == 'wait':
        async with asyncio.timeout(10):
            while not (case / 'owner').is_file():
                await asyncio.sleep(0.025)
    timed_out = False
    try:
        await asyncio.wait_for(await_agent(), timeout=0.35 if mode == 'wait' else 5)
    except asyncio.TimeoutError:
        timed_out = True
        await asyncio.wait_for(session.wait(), timeout=5)
    return {'case':label,'timed_out':timed_out,'stop_calls':stop_calls,'parent_late':(case/'parent-late').exists(),
            'child_late':(case/'child-late').exists(),'preserved_publication':(case/'published').read_text(),
            'natural_completion':(case/'finished').exists(),'docker_exec_exit':session.returncode}


async def main(output):
    with tempfile.TemporaryDirectory(prefix='fh-timeout-') as work:
        root=Path(work)
        container=subprocess.check_output(['docker','run','--rm','-d','--network','none','--mount',
           f'type=bind,source={root},target=/trial','python:3.12-slim','sleep','60'],text=True).strip()
        try:
            rows=[await run_case(container,root,label) for label in ('outer-timeout-only','timeout-with-cleanup','natural-completion')]
        finally:
            subprocess.run(['docker','rm','-f',container],check=True,capture_output=True)
    Path(output).write_text(json.dumps(rows,indent=2)+'\n')
    baseline, candidate, natural = rows
    assert all(row['preserved_publication']=='before deadline' for row in rows)
    assert baseline['timed_out'] and baseline['parent_late'] and baseline['child_late'] and baseline['stop_calls']==0
    assert candidate['timed_out'] and not candidate['parent_late'] and not candidate['child_late'] and candidate['stop_calls']==1
    assert not natural['timed_out'] and natural['natural_completion'] and natural['stop_calls']==0
    print(json.dumps(rows))


asyncio.run(main(sys.argv[1]))
