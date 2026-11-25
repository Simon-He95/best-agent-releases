"""Task-by-task diff between two single-arm boards.

`pair-report.py` compares two arms that ran in the same run. A board re-run after a source
change has no such control arm: it is one arm, weeks later, against the previous board's
numbers. This prints that reading and keeps the same three refusals:

- a cell whose either side is `infra` or `request_rejected` measured the transport, not the
  change, so the pair is excluded and listed instead of counted as a loss or a win;
- only the intersection of both boards is scored, so a task that one side never ran cannot
  quietly enter a denominator;
- the flip list is printed in full, because a single board diff cannot decide whether a
  difference is the change or the run: the same tasks that flipped here are the ones to
  re-run before anyone believes a delta.

usage: board-diff.py OLD_ROOT --old-arm NAME NEW_ROOT --new-arm NAME
"""

import argparse
import csv
import json
from pathlib import Path

EXCLUDED_OUTCOMES = ("infra", "request_rejected")


def load(root, arm):
    """task -> row for one arm, plus the profile facts this root declares."""
    rows, profiles = {}, []
    for directory in sorted(Path(root).rglob("score-*")):
        profile_path = directory / "profile.json"
        csv_path = directory / "tasks.csv"
        if not (profile_path.exists() and csv_path.exists()):
            continue
        profile = json.loads(profile_path.read_text())
        if profile.get("profile") != arm:
            continue
        profiles.append(profile)
        for row in csv.DictReader(csv_path.open()):
            rows[row["task"].split("/")[-1]] = row
    return rows, profiles


def is_pass(row):
    return row["reward"] == "1.0" and row["outcome"] == "pass"


def is_verifier_pass(row):
    return row["reward"] == "1.0"


def is_excluded(row):
    return row["outcome"] in EXCLUDED_OUTCOMES


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def totals(rows):
    usable = [row for row in rows.values() if not is_excluded(row)]
    return {
        "tasks": len(usable),
        "strict": sum(is_pass(row) for row in usable),
        "verifier": sum(is_verifier_pass(row) for row in usable),
        "seconds": sum(number(row["agent_seconds"]) for row in usable),
        "output": sum(number(row["output_tokens"]) for row in usable),
        "excluded": len(rows) - len(usable),
    }


def describe(profile):
    if not profile:
        return "unknown source"
    return (f"source {profile.get('source_sha', '?')[:9]} "
            f"prompt {profile.get('prompt_sha256', '?')[:12]} "
            f"cap {profile.get('output_cap')}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old_root")
    parser.add_argument("--old-arm", required=True)
    parser.add_argument("new_root")
    parser.add_argument("--new-arm", required=True)
    args = parser.parse_args()

    old, old_profiles = load(args.old_root, args.old_arm)
    new, new_profiles = load(args.new_root, args.new_arm)
    if not old or not new:
        missing = args.old_root if not old else args.new_root
        print(f"{missing}: no score package for arm {args.old_arm if not old else args.new_arm}")
        return 1

    before, after = totals(old), totals(new)
    print(f"old {args.old_root} [{args.old_arm}]: {describe(old_profiles[0])}")
    print(f"new {args.new_root} [{args.new_arm}]: {describe(new_profiles[0])}")
    print(f"old: tasks={before['tasks']} strict={before['strict']} "
          f"verifier={before['verifier']} excluded={before['excluded']} "
          f"output={before['output']:.0f} agent_s={before['seconds']:.0f}")
    print(f"new: tasks={after['tasks']} strict={after['strict']} "
          f"verifier={after['verifier']} excluded={after['excluded']} "
          f"output={after['output']:.0f} agent_s={after['seconds']:.0f}")

    kept, lost, gained, same_fail, excluded = [], [], [], [], []
    for task in sorted(set(old) & set(new)):
        a, b = old[task], new[task]
        if is_excluded(a) or is_excluded(b):
            excluded.append((task, a["outcome"], b["outcome"]))
        elif is_pass(a) and is_pass(b):
            kept.append(task)
        elif is_pass(a):
            lost.append(task)
        elif is_pass(b):
            gained.append(task)
        else:
            same_fail.append(task)

    paired = len(kept) + len(lost) + len(gained) + len(same_fail)
    print()
    print(f"paired cells: {paired}   excluded: {len(excluded)}   "
          f"only-one-side: {len(set(old) ^ set(new))}")
    print(f"kept={len(kept)} LOST={len(lost)} GAINED={len(gained)} same_fail={len(same_fail)}")
    if lost:
        print("LOST: " + ", ".join(
            f"{t} ({old[t]['checks_passed']}/{old[t]['checks_total']})" for t in lost))
    if gained:
        print("GAINED: " + ", ".join(
            f"{t} ({new[t]['checks_passed']}/{new[t]['checks_total']})" for t in gained))
    if excluded:
        print("excluded: " + ", ".join(f"{t} ({a}/{b})" for t, a, b in excluded))

    for label, tasks in (("kept", kept), ("LOST", lost), ("GAINED", gained)):
        if not tasks:
            continue
        print(f"\n{label}:")
        for task in tasks:
            a, b = old[task], new[task]
            print(f"  {task:34s} {a['outcome']:8s} {a['checks_passed']}/{a['checks_total']:<4s} "
                  f"{number(a['agent_seconds']):7.0f}s {int(number(a['output_tokens'])):8d} "
                  f"-> {b['outcome']:8s} {b['checks_passed']}/{b['checks_total']:<4s} "
                  f"{number(b['agent_seconds']):7.0f}s {int(number(b['output_tokens'])):8d}")

    print()
    print("A flip list is not a result: re-run the LOST and GAINED tasks before reading "
          "this as the change rather than the run.")
    return 0


raise SystemExit(main())
