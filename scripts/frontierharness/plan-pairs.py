import json
import os
from pathlib import Path

# 8 of the 14 scored baseline failures miss only one or two verifier checks, and every one of them
# ended because the agent declared completion (`terminal` completed), not because a deadline killed
# it. So the candidate asks the same agent to keep working until the checks it can run pass; the
# control is a task that already passes but only after 1219 s, where extra work is the risk.
cohort = {
    "glycan-ms2-elucidation",
    "pytorch-model-cli",
    "wal-recovery-ordering",
    "batched-eval-parity",
}
candidate_first = {"glycan-ms2-elucidation"}
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected or len(selected) != len(set(selected)) or not set(selected) <= cohort:
    raise SystemExit("Select unique tasks from the verify-to-green pilot")
matrix = []
for task in selected:
    profiles = ["short", "short-verify-to-green"]
    if task in candidate_first:
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({"task": task, "first": profiles[0], "second": profiles[1]})
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} same-runner pairs")
