import json
import os
from pathlib import Path

# Two tasks whose verdict is already 1.0 but whose run is killed by the task timeout, one of them
# 83% waiting on external computation, plus a fast stable control.
cohort = {"rstan-to-pystan", "tune-mjcf", "log-summary-date-ranges"}
candidate_first = {"rstan-to-pystan"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the independent jobs pilot")
matrix = []
for task in selected:
    profiles = ["short", "short-independent-jobs"]
    if task in candidate_first:
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
