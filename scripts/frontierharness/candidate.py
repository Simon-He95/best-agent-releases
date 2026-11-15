import os

from benchmarks.frontierharness.agents.best_agent import BestAgent

class Candidate(BestAgent):
    async def install(self, environment):
        await self.exec_as_root(environment, r"""set -eu
cat > /usr/local/bin/best-agent <<'SH'
#!/bin/sh
PATH="/opt/best-agent/bin:$PATH"
export PATH
if [ "$1" = run ]; then
  shift
  exec /opt/best-agent/bin/best-agent run --process-close-policy release "$@"
fi
exec /opt/best-agent/bin/best-agent "$@"
SH
chmod 0755 /usr/local/bin/best-agent
best-agent --version
""")

    async def _upload_provider_config(self, environment, provider, model_id):
        route = await self.exec_as_agent(environment, r"""/opt/best-agent/bin/node -e '
const fs=require("node:fs");
const row=fs.readFileSync("/proc/net/route","utf8").split("\n")
  .map(line=>line.trim().split(/\s+/)).find(fields=>fields[1]==="00000000");
if(!row) process.exit(2);
console.log(Array.from(Buffer.from(row[2],"hex")).reverse().join("."));
'""")
        self._base_url_override = f"http://{route.stdout.strip()}:{os.environ['FH_PORT']}/v1"
        return await super()._upload_provider_config(environment, provider, model_id)
