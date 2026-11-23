import json
import os
from pathlib import Path

# Model latency dominates the wall clock on these, and each ran either into the task timeout with a
# passing verifier or into a long fail. The control is the fast stable task every pair run carries.
cohort = {
    "adaptive-rejection-sampler",
    "gcode-to-text",
    "ontology-kg-querying",
    "log-summary-date-ranges",
}
# Per-task arm order: the candidate goes first on the task expected to flip, so a runner warm-up
# effect cannot be mistaken for the prompt's effect.
candidate_first = {"adaptive-rejection-sampler"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the batched tool-call pilot")
matrix = []
for task in selected:
    profiles = ["short", "short-batched"]
    if task in candidate_first:
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
