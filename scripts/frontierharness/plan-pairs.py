import json
import os
from pathlib import Path

# Two tasks whose verifier already passed but whose run was killed by the task timeout (the only
# convertible timeout pool), two slow-but-passing tasks where lower effort is the risk, and a fast
# control that must not move.
pilot = {
    "adaptive-rejection-sampler",
    "large-scale-text-editing",
    "batched-eval-parity",
    "embedding-drift-monitor",
    "log-summary-date-ranges",
}

# The highest single-turn reasoning passes that the pilot did not cover. A default change must not
# convert any of them.
regression = {
    "html-js-filter",
    "circuit-fibsqrt",
    "mvcc-lsm-compaction",
    "sam-cell-seg",
    # Next tier by longest single-turn reasoning among archived passes. The default change only
    # shortens very long turns, so these bound its blast radius without running the whole board.
    "chess-best-move",
    "sqlite-with-gcov",
    "code-from-image",
    "intrastat-meldung",
    "portfolio-optimization",
    "polyglot-c-py",
}

# Verifier already 1.0 but killed by the task timeout, with most of the budget in model time:
# lower effort is the only lever that can convert them.
convertible = {
    "dna-insert",
    "tune-mjcf",
}

allowed = pilot | regression | convertible
candidate_first = {"adaptive-rejection-sampler"}
scope = os.environ.get("FH_SCOPE", "pilot")
if scope not in ("pilot", "board"):
    raise SystemExit("FH_SCOPE must be pilot or board")
if scope == "board":
    cohort = Path(__file__).with_name("cohort57.txt").read_text().splitlines()
    allowed = {name.strip() for name in cohort if name.strip()}
second = os.environ.get("FH_SECOND", "short-effort-high")
first = os.environ.get("FH_FIRST", "short")
default_arms = first if second == "none" else f"{first},{second}"
arms = [arm.strip() for arm in os.environ.get("FH_ARMS", default_arms).split(",") if arm.strip()]
if not arms or any(arm not in ("short", "short-effort-high") for arm in arms):
    raise SystemExit("FH_ARMS must list short and/or short-effort-high")
selected = [entry.strip() for entry in os.environ.get("FH_TASKS", "").split(",") if entry.strip()]
if not selected:
    selected = sorted(allowed) if scope == "board" else sorted(pilot)
if len(selected) != len(set(selected)) or not set(selected) <= allowed:
    raise SystemExit("Select unique tasks from the allowed cohort")
matrix = []
for task in selected:
    profiles = list(arms)
    if len(profiles) == 2 and task in candidate_first:
        profiles.reverse()
    if os.environ.get("FH_REVERSE_ORDER") == "true":
        profiles.reverse()
    matrix.append({
        "task": task,
        "first": profiles[0],
        "second": profiles[1] if len(profiles) > 1 else "",
    })
with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
    print("matrix=" + json.dumps({"include": matrix}, separators=(",", ":")), file=output)
print(f"Scheduled {len(matrix)} task arms")
