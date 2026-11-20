import json
import os
from pathlib import Path

cohort = Path(__file__).with_name("cohort57.txt").read_text().splitlines()
assert len(cohort) == len(set(cohort)) == 57
requested = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
selected = requested or cohort
if len(selected) != len(set(selected)) or not set(selected) <= set(cohort):
    raise SystemExit("Select unique tasks from the pinned 57-task cohort")
matrix = [{"task": task, "profile": profile} for task in selected for profile in ("short", "claude")]
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} task attempts in {len(selected)} pairs")
