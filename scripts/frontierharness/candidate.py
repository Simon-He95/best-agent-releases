import asyncio
import json
import os
from pathlib import Path
from time import monotonic

from benchmarks.frontierharness.agents.best_agent import BestAgent, EVIDENCE_FILENAME, LOGS_DIR
from harbor.models.trial.config import TrialConfig


class Candidate(BestAgent):
    review_active = False

    async def run(self, instruction, environment, context):
        started = monotonic()
        try:
            await super().run(instruction, environment, context)
            if os.environ["FH_PROFILE"] != "short-fresh-review":
                return
            trial = TrialConfig.model_validate_json((self.logs_dir.parent / "config.json").read_text())
            metadata = json.loads((Path(os.environ["FH_AB_DIR"]) / "tasks.json").read_text())
            task = next(row for row in metadata if Path(row["path"]) == trial.task.path)
            seconds = trial.agent.override_timeout_sec or task["agent_timeout_sec"]
            if trial.agent.max_timeout_sec is not None:
                seconds = min(seconds, trial.agent.max_timeout_sec)
            multiplier = trial.agent_timeout_multiplier
            if multiplier is None:
                multiplier = trial.timeout_multiplier
            remaining = seconds * multiplier - (monotonic() - started)
            event = {"tag": self.logs_dir.parent.name, "remaining_seconds": remaining,
                     "review_started": remaining >= 120}
            with (Path(os.environ["FH_AB_DIR"]) / "review.jsonl").open("a") as output:
                output.write(json.dumps(event) + "\n")
            if not event["review_started"]:
                return
            self.review_active = True
            review = (
                "Independently review the work already in this workspace against the original "
                "request below. Keep existing work that satisfies the request. Check the actual "
                "entry point and use public task materials or your own checks. Change only a "
                "concrete mismatch you can demonstrate, then leave the requested deliverables ready."
                "\n\nOriginal request:\n" + instruction
            )
            await super().run(review, environment, context)
        except asyncio.CancelledError:
            tag = self.logs_dir.parent.name
            (Path(os.environ["FH_AB_DIR"]) / "cutoff" / tag).touch()
            raise

    async def exec_as_agent(self, environment, command, **kwargs):
        evidence = f"--attempt-evidence {LOGS_DIR}/{EVIDENCE_FILENAME}"
        if self.review_active and evidence in command:
            assert command.count(evidence) == 1
            command = command.replace(evidence, f"--attempt-evidence {LOGS_DIR}/review-evidence.jsonl")
            kwargs["env"] = {**kwargs["env"], "BEST_AGENT_STORAGE_ROOT": "/tmp/best-agent-review-state"}
        return await super().exec_as_agent(environment, command, **kwargs)

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
