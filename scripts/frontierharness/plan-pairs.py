import json
import os
from pathlib import Path

cohort = {"vpp-loss-divergence", "cargo-flight-dispatch", "log-summary-date-ranges"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the exec stream budget pilot")
matrix = []
for task in selected:
    profiles = ["short", "short-exec-stream-budget"]
    if task == "vpp-loss-divergence":
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
