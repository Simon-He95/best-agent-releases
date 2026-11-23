import json
import os
from pathlib import Path

# Two tasks whose verifier already passed but whose run was killed by the task timeout (the only
# convertible timeout pool), two slow-but-passing tasks where lower effort is the risk, and a fast
# control that must not move.
cohort = {
    "adaptive-rejection-sampler",
    "large-scale-text-editing",
    "batched-eval-parity",
    "embedding-drift-monitor",
    "log-summary-date-ranges",
}
candidate_first = {"adaptive-rejection-sampler"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the whole-run effort pilot")
matrix = []
for task in selected:
    profiles = ["short", "short-effort-high"]
    if task in candidate_first:
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
