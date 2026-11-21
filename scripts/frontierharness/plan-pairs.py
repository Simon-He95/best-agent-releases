import json
import os
from pathlib import Path

cohort = {"batched-eval-parity", "pytorch-model-cli", "log-summary-date-ranges"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the single-model subagent catalog pilot")
matrix = []
for task in selected:
    profiles = ["short-readonly-audit", "short-readonly-audit-single-model"]
    if task in {"batched-eval-parity", "log-summary-date-ranges"}:
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
