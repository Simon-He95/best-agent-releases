import json
import os
from pathlib import Path

# One discriminating task and one stable control: the previous configuration flip landed on
# vpp-loss-divergence and never on the control, so this pair asks whether the compacted-context
# text alone reproduces it without the two extra bindings.
cohort = {"vpp-loss-divergence", "log-summary-date-ranges"}
candidate_first = {"vpp-loss-divergence"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the compact hint pilot")
matrix = []
for task in selected:
    profiles = ["short", "short-compact-hint"]
    if task in candidate_first:
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
