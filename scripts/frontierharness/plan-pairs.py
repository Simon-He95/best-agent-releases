import json
import os
from pathlib import Path

cohort = {"adaptive-rejection-sampler", "pytorch-model-cli", "polyglot-c-py", "sqlite-db-truncate"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the foreground tool routing pilot")
matrix = [{"task": task, "profile": profile} for task in selected for profile in ("short", "short-foreground")]
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} task attempts in {len(selected)} pairs")
