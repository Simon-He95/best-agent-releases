import json
import os
from pathlib import Path

cohort = set(Path(__file__).with_name("cohort57.txt").read_text().splitlines())
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the pinned 57-task benchmark cohort")
matrix = []
reverse_order = os.environ.get("FH_REVERSE_ORDER") == "true"
for index, task in enumerate(selected):
    profiles = ["short", "short-focused-verification"]
    if (index % 2 == 1) != reverse_order:
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
