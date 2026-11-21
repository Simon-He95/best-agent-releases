import asyncio
import json
import os
from pathlib import Path

from benchmarks.frontierharness.agents.best_agent import BestAgent


class Candidate(BestAgent):
    async def run(self, instruction, environment, context):
        try:
            await super().run(instruction, environment, context)
        except asyncio.CancelledError:
            tag = self.logs_dir.parent.name
            (Path(os.environ["FH_AB_DIR"]) / "cutoff" / tag).touch()
            raise

    async def install(self, environment):
        audit_env = "env BEST_AGENT_FH_READONLY_AUDIT=1 "
        if os.environ["FH_PROFILE"] == "short-readonly-audit-single-model":
            audit_env += "BEST_AGENT_FH_SINGLE_CHILD_MODEL=1 "
        await self.exec_as_root(environment, r"""set -eu
cat > /usr/local/bin/best-agent <<'SH'
#!/bin/sh
PATH="/opt/best-agent/bin:$PATH"
export PATH
if [ "$1" = run ]; then
  shift
  exec """ + audit_env + r"""/opt/best-agent/bin/best-agent run --process-close-policy release "$@"
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
        tag = self.logs_dir.parent.name
        self._base_url_override = f"http://{route.stdout.strip()}:{os.environ['FH_PORT']}/{tag}/v1"
        return await super()._upload_provider_config(environment, provider, model_id)

    def populate_context_post_run(self, context):
        ledger=Path(os.environ["FH_AB_DIR"])/"transport.jsonl"
        tag=self.logs_dir.parent.name
        usage=[]
        if ledger.is_file():
            with ledger.open() as f:
                for line in f:
                    try: row=json.loads(line)
                    except json.JSONDecodeError: continue
                    if row.get("tag")==tag and row.get("phase")=="finish" and row.get("usage"):
                        usage.append(row["usage"])
        if usage:
            context.n_input_tokens=sum(x.get("prompt_tokens",0) for x in usage)
            context.n_cache_tokens=sum((x.get("prompt_tokens_details") or {}).get("cached_tokens", x.get("prompt_cache_hit_tokens",0)) for x in usage)
            context.n_output_tokens=sum(x.get("completion_tokens",0) for x in usage)
