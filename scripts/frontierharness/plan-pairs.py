import json
import os
from pathlib import Path

cohort = {"cargo-flight-dispatch", "batched-eval-parity", "sqlite-db-truncate"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the headless model streaming pilot")
arm = os.environ.get("FH_ARM", "pair")
if arm not in ("pair", "short", "short-stream"):
    raise SystemExit("Select pair, short, or short-stream")
matrix = []
for task in selected:
    if arm != "pair":
        matrix.append({"task": task, "first": arm, "second": ""})
        continue
    profiles = ["short", "short-stream"]
    if task == "batched-eval-parity":
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} task jobs with arm={arm}")
