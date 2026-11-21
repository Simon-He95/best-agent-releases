import asyncio
import json
import os
from pathlib import Path

from harbor.models.job.config import DatasetConfig
from harbor.models.task.task import Task
from harbor.tasks.client import TaskClient

async def main():
    root = Path(os.environ["FH_ROOT"])
    allowed = set(Path(__file__).with_name("cohort57.txt").read_text().splitlines())
    requested = [x.strip() for x in os.environ.get("FH_TASKS", "").split(",") if x.strip()]
    selected = requested or sorted(allowed)
    if len(selected) != len(set(selected)) or not set(selected) <= allowed:
        raise ValueError("Task selection must be a unique subset of cohort57.txt")
    dataset = DatasetConfig(
        name="frontier-harness-eval/frontier-harness-eval",
        ref="sha256:9236400fc1a6619eb72a663445c580417be9bbbab32f816c7dff76d0a96ab24a",
        task_names=["terminal-bench/" + name for name in selected],
    )
    configs = await dataset.get_task_configs()
    assert len(configs) == len(selected)
    downloaded = await TaskClient().download_tasks([c.get_task_id() for c in configs])
    records = []
    for config, item in zip(configs, downloaded.results):
        task = Task(item.path)
        assert task.name == config.name
        records.append({"name": task.name, "checksum": task.checksum, "path": str(item.path),
                        "agent_timeout_sec": task.config.agent.timeout_sec})
    (root / "raw/tasks.json").write_text(json.dumps(records, indent=2))
    (root / "raw/job-config.json").write_text(json.dumps({
        "datasets": [], "tasks": [{"path": r["path"]} for r in records],
    }, indent=2))

asyncio.run(main())
