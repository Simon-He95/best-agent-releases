"""Task-by-task diff between two single-arm boards.

`pair-report.py` compares two arms inside one run, which a board re-run cannot offer: it is
one arm, later, against the previous board's numbers. This reads that comparison and borrows
two of `pair-report.py`'s refusals, then adds a third:

- a pair whose either side is `infra` or `request_rejected` measured the transport, not the
  change, so it is excluded and listed instead of counted as a loss or a win;
- every number is computed over the intersection of both boards, and over that same set of
  pairs on both sides, so a task one board never ran, or a cell that was excluded, cannot
  enter either numerator or denominator;
- the flip list is printed in full and the net is stated, because one observation per task
  per board cannot tell the change from the run: re-run the LOST and GAINED tasks first.

The two arms must declare the same prompt and output cap; a drifted prompt is reported as an
identity mismatch and no diff is printed, because that comparison would answer a different
question.

usage: board-diff.py OLD_ROOT --old-arm NAME NEW_ROOT --new-arm NAME
"""

import argparse
import csv
import json
import sys
from pathlib import Path

EXCLUDED_OUTCOMES = ("infra", "request_rejected")


def load(root, arm):
    """task -> row for one arm, plus every package that declared it."""
    root = Path(root)
    if not root.is_dir():
        raise SystemExit(f"{root}: not a directory")
    rows, packages, duplicates = {}, [], []
    for directory in sorted(root.rglob("score-*")):
        profile_path = directory / "profile.json"
        csv_path = directory / "tasks.csv"
        if not (profile_path.exists() and csv_path.exists()):
            continue
        profile = json.loads(profile_path.read_text())
        if profile.get("profile") != arm:
            continue
        packages.append((directory, profile))
        for row in csv.DictReader(csv_path.open()):
            task = row["task"].split("/")[-1]
            if task in rows:
                duplicates.append((task, directory.name))
                continue
            rows[task] = row
    return rows, packages, duplicates


def value(row, key):
    return row.get(key, "")


def number(value_text):
    try:
        return float(value_text)
    except (TypeError, ValueError):
        return 0.0


def is_pass(row):
    return value(row, "reward") == "1.0" and value(row, "outcome") == "pass"


def is_verifier_pass(row):
    return value(row, "reward") == "1.0"


def is_excluded(row):
    return value(row, "outcome") in EXCLUDED_OUTCOMES


def checks(row):
    return f"{value(row, 'checks_passed') or '-'}/{value(row, 'checks_total') or '-'}"


def identity(packages):
    """The facts that make two arms the same measurement."""
    prompts = {profile.get("prompt_sha256") for _, profile in packages}
    caps = {profile.get("output_cap") for _, profile in packages}
    sources = {profile.get("source_sha") for _, profile in packages}
    return prompts, caps, sources


def describe(packages, label):
    prompts, caps, sources = identity(packages)
    prompt = prompts.pop() if len(prompts) == 1 else "MIXED"
    cap = caps.pop() if len(caps) == 1 else "MIXED"
    source = sources.pop() if len(sources) == 1 else "MIXED"
    return f"{label}: {len(packages)} packages, source {str(source)[:9]}, " \
           f"prompt {str(prompt)[:12]}, cap {cap}"


def totals(rows):
    return {
        "tasks": len(rows),
        "strict": sum(is_pass(row) for row in rows),
        "verifier": sum(is_verifier_pass(row) for row in rows),
        "seconds": sum(number(value(row, "agent_seconds")) for row in rows),
        "output": sum(number(value(row, "output_tokens")) for row in rows),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("old_root")
    parser.add_argument("--old-arm", required=True)
    parser.add_argument("new_root")
    parser.add_argument("--new-arm", required=True)
    args = parser.parse_args()

    old, old_packages, old_duplicates = load(args.old_root, args.old_arm)
    new, new_packages, new_duplicates = load(args.new_root, args.new_arm)
    for label, arm, packages, duplicates in (
        ("old", args.old_arm, old_packages, old_duplicates),
        ("new", args.new_arm, new_packages, new_duplicates),
    ):
        if not packages:
            print(f"{label} root has no score package for arm {arm}")
            return 1
        if duplicates:
            print(f"{label} root declares the same task in more than one package: "
                  + ", ".join(f"{task} ({package})" for task, package in duplicates))
            return 1

    print(describe(old_packages, f"old {args.old_root} [{args.old_arm}]"))
    print(describe(new_packages, f"new {args.new_root} [{args.new_arm}]"))

    old_prompts, old_caps, _ = identity(old_packages)
    new_prompts, new_caps, _ = identity(new_packages)
    problems = []
    if old_prompts != new_prompts:
        problems.append(f"prompt differs: {sorted(old_prompts)} vs {sorted(new_prompts)}")
    if old_caps != new_caps:
        problems.append(f"output cap differs: {sorted(old_caps)} vs {sorted(new_caps)}")
    if problems:
        print("\nIDENTITY MISMATCH — these are different measurements, no diff printed:")
        for problem in problems:
            print(f"  {problem}")
        return 2

    shared = sorted(set(old) & set(new))
    if not shared:
        print("\nno task was run by both boards")
        return 1

    usable, excluded = [], []
    for task in shared:
        before, after = old[task], new[task]
        if is_excluded(before) or is_excluded(after):
            excluded.append((task, value(before, "outcome"), value(after, "outcome")))
        else:
            usable.append((task, before, after))
    if not usable:
        print(f"\nevery shared task had an excluded cell ({len(excluded)} pairs)")
        return 1

    before_rows = [before for _, before, _ in usable]
    after_rows = [after for _, _, after in usable]
    before, after = totals(before_rows), totals(after_rows)
    kept = [t for t, a, b in usable if is_pass(a) and is_pass(b)]
    lost = [t for t, a, b in usable if is_pass(a) and not is_pass(b)]
    gained = [t for t, a, b in usable if is_pass(b) and not is_pass(a)]
    same_fail = [t for t, a, b in usable if not is_pass(a) and not is_pass(b)]
    only_old = sorted(set(old) - set(new))
    only_new = sorted(set(new) - set(old))

    def change(old_value, new_value):
        if not old_value:
            return ""
        return f"  ({100 * (new_value / old_value - 1):+.1f}%)"

    print()
    print(f"paired cells: {len(usable)}   excluded: {len(excluded)}   "
          f"only-in-old: {len(only_old)}   only-in-new: {len(only_new)}")
    print(f"strict   old={before['strict']}/{before['tasks']}  "
          f"new={after['strict']}/{after['tasks']}  "
          f"delta={after['strict'] - before['strict']:+d}")
    print(f"verifier old={before['verifier']}/{before['tasks']}  "
          f"new={after['verifier']}/{after['tasks']}  "
          f"delta={after['verifier'] - before['verifier']:+d}")
    print(f"output   old={before['output']:.0f}  new={after['output']:.0f}"
          f"{change(before['output'], after['output'])}")
    print(f"agent s  old={before['seconds']:.0f}  new={after['seconds']:.0f}"
          f"{change(before['seconds'], after['seconds'])}")
    print(f"kept={len(kept)} LOST={len(lost)} GAINED={len(gained)} "
          f"same_fail={len(same_fail)} net={len(gained) - len(lost):+d}")
    if lost:
        print("LOST: " + ", ".join(
            f"{t} ({checks(old[t])} -> {checks(new[t])})" for t in lost))
    if gained:
        print("GAINED: " + ", ".join(
            f"{t} ({checks(old[t])} -> {checks(new[t])})" for t in gained))
    if excluded:
        print("excluded: " + ", ".join(f"{t} ({a}/{b})" for t, a, b in excluded))
    if only_old:
        print("only in old (not scored): " + ", ".join(only_old))
    if only_new:
        print("only in new (not scored): " + ", ".join(only_new))

    for label, tasks in (("kept", kept), ("LOST", lost), ("GAINED", gained)):
        if not tasks:
            continue
        print(f"\n{label}:")
        for task in tasks:
            a, b = old[task], new[task]
            print(f"  {task:34s} {value(a, 'outcome'):8s} {checks(a):<7s} "
                  f"{number(value(a, 'agent_seconds')):7.0f}s "
                  f"{int(number(value(a, 'output_tokens'))):8d} "
                  f"-> {value(b, 'outcome'):8s} {checks(b):<7s} "
                  f"{number(value(b, 'agent_seconds')):7.0f}s "
                  f"{int(number(value(b, 'output_tokens'))):8d}")

    print()
    print(f"net {len(gained) - len(lost):+d} over {len(usable)} paired cells, "
          f"{len(lost) + len(gained)} of them flipped: one observation per task per board "
          f"is not a result. Re-run the LOST and GAINED tasks before reading this as the "
          f"change rather than the run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
