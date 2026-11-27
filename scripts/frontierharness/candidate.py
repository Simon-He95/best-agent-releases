import json
import os
from pathlib import Path

from benchmarks.frontierharness.agents.best_agent import BestAgent

# One bundle serves every arm, so an arm selects its behavior through the environment its runner
# wrapper exports. arms.json is the single declaration: the cap an arm declares there is also what
# report.py expects to see in the ledger.
ARMS = json.loads(Path(__file__).with_name("arms.json").read_text())
DEFAULT_OUTPUT_CAP = ARMS["short"]["output_cap"]


def arm_environment(profile):
    arm = ARMS[profile]
    env = dict(arm.get("env") or {})
    if profile == "short-private-evidence":
        port = os.environ["FH_EVIDENCE_PORT"]
        assert port.isdecimal() and 0 < int(port) <= 65535
        env["FH_EVIDENCE_PORT"] = port
    if arm["output_cap"] != DEFAULT_OUTPUT_CAP:
        env["BEST_AGENT_BENCHMARK_OUTPUT_CAP"] = str(arm["output_cap"])
    return "".join(f"{key}={value} " for key, value in sorted(env.items()))


class Candidate(BestAgent):
    async def install(self, environment):
        arm_env = arm_environment(os.environ["FH_PROFILE"])
        if arm_env:
            arm_env = "env " + arm_env
        await self.exec_as_root(environment, r"""set -eu
cat > /usr/local/bin/best-agent <<'SH'
#!/bin/sh
PATH="/opt/best-agent/bin:$PATH"
export PATH
if [ "$1" = run ]; then
  shift
  exec """ + arm_env + r"""/opt/best-agent/bin/best-agent run --process-close-policy release "$@"
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
