import json
import os
import shlex
from pathlib import Path

from benchmarks.frontierharness.agents.best_agent import BestAgent


ARTIFACT_PATHS = {
    "terminal-bench/adaptive-rejection-sampler": [
        "/app/ars.R", "/app/normal_samples.txt", "/app/exponential_samples.txt",
    ],
    "terminal-bench/code-from-image": ["/app/output.txt"],
    "terminal-bench/gcode-to-text": ["/app/out.txt"],
    "terminal-bench/sqlite-db-truncate": ["/app/recover.json"],
    "terminal-bench/regex-log": ["/app/regex.txt"],
}


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
        trial = json.loads((self.logs_dir.parent / "config.json").read_text())
        tasks = json.loads((Path(os.environ["FH_AB_DIR"]) / "tasks.json").read_text())
        task = next(row for row in tasks if Path(row["path"]) == Path(trial["task"]["path"]))
        self._artifact_paths = ARTIFACT_PATHS.get(task["name"], [])
        if self._artifact_paths:
            await environment.upload_file(
                Path(__file__).with_name("observe-artifacts.mjs"),
                "/tmp/fh-observe-artifacts.mjs",
            )
        await super().run(instruction, environment, context)

    async def exec_as_agent(self, environment, command, **kwargs):
        entry = 'best-agent run --workspace "$workspace"'
        if getattr(self, "_artifact_paths", []) and entry in command:
            paths = " ".join(shlex.quote(path) for path in self._artifact_paths)
            audit = "/logs/agent/artifact-timing.json"
            observer = (
                f'/opt/best-agent/bin/node /tmp/fh-observe-artifacts.mjs "$$" {audit} {paths} '
                '</dev/null >/dev/null 2>/logs/agent/artifact-observer.stderr & observer=$!; '
                f'while [ ! -s {audit} ]; do kill -0 "$observer"; sleep .02; done; '
            )
            command = command.replace(entry, observer + "exec " + entry, 1)
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
