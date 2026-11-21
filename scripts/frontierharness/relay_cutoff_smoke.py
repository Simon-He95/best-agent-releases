import asyncio
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import shlex
import subprocess
import sys
import threading
import time
from urllib.parse import urlparse

from harbor.agents.installed.base import BaseInstalledAgent

CLIENT = '''
import socket, subprocess, sys, time
import urllib.request
from pathlib import Path

row=next(x.split() for x in Path('/proc/net/route').read_text().splitlines() if x.split()[1]=='00000000')
base='http://'+socket.inet_ntoa(bytes.fromhex(row[2])[::-1])+':'+sys.argv[1]

def send(name):
    request=urllib.request.Request(base+'/'+name,method='POST')
    try:
        urllib.request.urlopen(request,timeout=5).close()
    except urllib.error.HTTPError as error:
        if error.code!=410: raise

send('early')
Path('/app/owned-artifact').write_text('published before cutoff')
if sys.argv[2]=='natural': raise SystemExit(0)
child="""import sys,time,urllib.request,urllib.error
time.sleep(6)
try:
    urllib.request.urlopen(urllib.request.Request(sys.argv[1],method="POST"),timeout=5).close()
except urllib.error.HTTPError as error:
    if error.code!=410: raise
"""
proc=subprocess.Popen([sys.executable,'-c',child,base+'/detached'],start_new_session=True)
time.sleep(6)
send('parent')
proc.wait()
'''


class FixtureAgent(BaseInstalledAgent):
    def __init__(self, *args, mode, **kwargs):
        super().__init__(*args, **kwargs)
        assert mode in ('unguarded','guarded','natural')
        self.mode=mode

    @staticmethod
    def name():
        return 'relay-cutoff-fixture'

    async def install(self, environment):
        await self.exec_as_agent(environment, 'python3 --version')

    async def run(self, instruction, environment, context):
        closed=threading.Event()
        lock=threading.Lock()
        ledger=self.logs_dir/'cutoff-events.jsonl'

        def record(event):
            with ledger.open('a') as out:
                out.write(json.dumps({**event,'time_ms':time.time_ns()//1_000_000})+'\n')

        class Relay(BaseHTTPRequestHandler):
            def do_POST(self):
                lane=urlparse(self.path).path.removeprefix('/')
                with lock:
                    status=410 if closed.is_set() else 204
                    record({'event':'request','lane':lane,'status':status})
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):
                pass

        relay=ThreadingHTTPServer(('0.0.0.0',0),Relay)
        threading.Thread(target=relay.serve_forever,daemon=True).start()
        try:
            command=shlex.join(['python3','-c',CLIENT,str(relay.server_port),self.mode])
            await self.exec_as_agent(environment,command=command)
        except asyncio.CancelledError:
            with lock:
                if self.mode=='guarded':
                    closed.set()
                record({'event':'cancelled','scope_closed':closed.is_set()})
            raise


def main(root):
    task=root/'task'
    (task/'environment').mkdir(parents=True)
    (task/'tests').mkdir()
    (task/'instruction.md').write_text('Publish the local fixture artifact.\n')
    (task/'task.toml').write_text('version = "1.0"\n[metadata]\nauthor_name="Benchmark fixture"\nauthor_email="fixture@example.invalid"\n[verifier]\ntimeout_sec=30.0\n[agent]\ntimeout_sec=3.0\n[environment]\nbuild_timeout_sec=180.0\ncpus=1\nmemory="1G"\nstorage="2G"\n')
    (task/'environment/Dockerfile').write_text('FROM python:3.12-slim\nWORKDIR /app\n')
    (task/'tests/test.sh').write_text('''#!/bin/sh
set -eu
sleep 8
mkdir -p /logs/verifier
if [ "$(cat /app/owned-artifact)" = "published before cutoff" ]; then
  echo 1 > /logs/verifier/reward.txt
else
  echo 0 > /logs/verifier/reward.txt
fi
''')
    (task/'tests/test.sh').chmod(0o755)
    receipts=[]
    for mode in ('unguarded','guarded','natural'):
        jobs=root/mode
        process=subprocess.run(['harbor','run','-p',str(task),'-e','docker','-n','1','-k','1','-y',
          '--agent-import-path','relay_cutoff_smoke:FixtureAgent','--ak',f'mode={mode}','--jobs-dir',str(jobs)])
        (trial,)=list(jobs.glob('*/*/result.json'))
        data=json.loads(trial.read_text())
        events=[json.loads(line) for line in (trial.parent/'agent/cutoff-events.jsonl').read_text().splitlines()]
        exceptions=(data.get('exception_info') or {}).get('exception_type')
        grade=(data.get('verifier_result') or {}).get('rewards',{}).get('reward')
        summary={'mode':mode,'cli_exit':process.returncode,'exception':exceptions,'grade':grade,
                 'agent_window':data['agent_execution'],'verifier_window':data['verifier'],'events':events}
        receipts.append(summary)
        (root/'receipts.json').write_text(json.dumps(receipts,indent=2)+'\n')
        assert grade==1,(mode,summary)
        assert [v['status'] for v in events if v.get('lane')=='early']==[204]
        late=[v for v in events if v.get('lane') in ('parent','detached')]
        if mode=='natural':
            assert not exceptions and not late and len(events)==1,summary
            continue
        assert exceptions=='AgentTimeoutError',summary
        assert {v['lane'] for v in late}=={'parent','detached'},summary
        cutoff=datetime.fromisoformat(data['agent_execution']['finished_at']).timestamp()*1000
        assert all(v['time_ms']>cutoff and v['status']==(410 if mode=='guarded' else 204) for v in late),summary
    print(json.dumps(receipts))


if __name__=='__main__':
    main(Path(sys.argv[1]))
