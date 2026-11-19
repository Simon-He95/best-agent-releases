import json
import os
from math import ceil, floor
from time import monotonic
from pathlib import Path

from benchmarks.frontierharness.agents.best_agent import BestAgent
from harbor.models.trial.config import TrialConfig


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

    async def run(self, instruction, environment, context):
        self._attempt_started = monotonic()
        trial = TrialConfig.model_validate_json((self.logs_dir.parent / "config.json").read_text())
        tasks = json.loads((Path(os.environ["FH_AB_DIR"]) / "tasks.json").read_text())
        task = next(row for row in tasks if Path(row["path"]) == trial.task.path)
        timeout_sec = trial.agent.override_timeout_sec or task["agent_timeout_sec"]
        if timeout_sec is None:
            raise ValueError("The selected Harbor task has no agent timeout.")
        if trial.agent.max_timeout_sec is not None:
            timeout_sec = min(timeout_sec, trial.agent.max_timeout_sec)
        multiplier = trial.agent_timeout_multiplier
        if multiplier is None:
            multiplier = trial.timeout_multiplier
        self._harbor_budget_ms = floor(timeout_sec * multiplier * 1000)
        await super().run(instruction, environment, context)

    async def exec_as_agent(self, environment, command, **kwargs):
        entry = 'best-agent run --workspace "$workspace"'
        if entry in command:
            arm = os.environ["FH_BUDGET_ARM"]
            elapsed_ms = ceil((monotonic() - self._attempt_started) * 1000)
            remaining_ms = self._harbor_budget_ms - elapsed_ms
            if arm == "remaining":
                if remaining_ms <= 0:
                    raise RuntimeError("The Harbor agent budget was exhausted before CLI launch.")
                command = command.replace(entry, f"{entry} --attempt-remaining-ms {remaining_ms}", 1)
            record = {
                "arm": arm, "harbor_budget_ms": self._harbor_budget_ms, "elapsed_ms": elapsed_ms,
                "passed_remaining_ms": remaining_ms if arm == "remaining" else None,
                "tag": self.logs_dir.parent.name,
            }
            with (Path(os.environ["FH_AB_DIR"]) / "budget.jsonl").open("a") as output:
                output.write(json.dumps(record) + "\n")
        return await super().exec_as_agent(environment, command, **kwargs)

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
