"""Paired report for a FrontierHarness arm comparison.

Reads the `score-*` directories that `fh-fetch.py score` writes and compares arms that ran
in the same run. Three things this report refuses to do, because each one produced a wrong
conclusion before:

- count an `infra` or `request_rejected` cell as a failure of the arm: such a cell measures
  the transport, not the instruction, so a pair containing one is excluded and listed;
- call a single-run difference a result: it also prints how often the control itself flips
  across every observation available for the same arm, which is the noise band;
- compare arms that ran in different runs: only same-run pairs are scored.

usage: pair-report.py SCORE_ROOT [SCORE_ROOT ...] [--arm A] [--versus B]

With no --arm/--versus the pairs are discovered from the profiles present.
"""

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path

EXCLUDED_OUTCOMES = ("infra", "request_rejected")


def load(root):
    """task -> arm -> row, plus arm -> output cap declared by that run."""
    cells = defaultdict(dict)
    caps = {}
    for directory in sorted(Path(root).rglob("score-*")):
        profile_path = directory / "profile.json"
        csv_path = directory / "tasks.csv"
        if not (profile_path.exists() and csv_path.exists()):
            continue
        profile = json.loads(profile_path.read_text())
        arm = profile.get("profile")
        caps.setdefault(arm, profile.get("output_cap"))
        for row in csv.DictReader(csv_path.open()):
            cells[row["task"].split("/")[-1]][arm] = row
    return cells, caps


def is_pass(row):
    return row["reward"] == "1.0" and row["outcome"] == "pass"


def is_verifier_pass(row):
    return row["reward"] == "1.0"


def number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def discover_arms(cells):
    counts = Counter()
    for rows in cells.values():
        for arm in rows:
            counts[arm] += 1
    return [arm for arm, _ in counts.most_common()]


def report(root, arm_a, arm_b):
    cells, caps = load(root)
    tasks = sorted(t for t, rows in cells.items() if arm_a in rows and arm_b in rows)
    if not tasks:
        print(f"{root}: no task was run by both {arm_a} and {arm_b}")
        return 1

    print(f"source: {root}")
    print(f"cap: {arm_a}={caps.get(arm_a)} {arm_b}={caps.get(arm_b)}")
    print(f"{'task':<32}{arm_a[:11]:>12}{arm_b[:11]:>12}{'A s':>7}{'B s':>7}{'A out':>9}{'B out':>9}  read")

    usable, excluded = [], []
    for task in tasks:
        a, b = cells[task][arm_a], cells[task][arm_b]
        if a["outcome"] in EXCLUDED_OUTCOMES or b["outcome"] in EXCLUDED_OUTCOMES:
            excluded.append((task, a["outcome"], b["outcome"]))
            read = f"excluded ({a['outcome']}/{b['outcome']})"
        else:
            usable.append((a, b))
            read = ("B" if is_pass(b) and not is_pass(a)
                    else "A" if is_pass(a) and not is_pass(b)
                    else "both" if is_pass(a) else "neither")
        print(f"{task:<32}{a['outcome']:>12}{b['outcome']:>12}"
              f"{number(a['agent_seconds']):>7.0f}{number(b['agent_seconds']):>7.0f}"
              f"{int(number(a['output_tokens'])):>9}{int(number(b['output_tokens'])):>9}  {read}")

    n = len(usable)
    strict_a = sum(is_pass(a) for a, _ in usable)
    strict_b = sum(is_pass(b) for _, b in usable)
    ver_a = sum(is_verifier_pass(a) for a, _ in usable)
    ver_b = sum(is_verifier_pass(b) for _, b in usable)
    sec_a = sum(number(a["agent_seconds"]) for a, _ in usable)
    sec_b = sum(number(b["agent_seconds"]) for _, b in usable)
    out_a = sum(number(a["output_tokens"]) for a, _ in usable)
    out_b = sum(number(b["output_tokens"]) for _, b in usable)
    wins = sum(1 for a, b in usable if is_pass(b) and not is_pass(a))
    losses = sum(1 for a, b in usable if is_pass(a) and not is_pass(b))
    percent = lambda x, y: (100 * (y / x - 1)) if x else 0.0

    print()
    print(f"paired cells: {n}   excluded: {len(excluded)}")
    print(f"strict   {arm_a}={strict_a}/{n}  {arm_b}={strict_b}/{n}  delta={strict_b - strict_a:+d}")
    print(f"verifier {arm_a}={ver_a}/{n}  {arm_b}={ver_b}/{n}  delta={ver_b - ver_a:+d}")
    print(f"agent s  {arm_a}={sec_a:.0f}  {arm_b}={sec_b:.0f}  ({percent(sec_a, sec_b):+.1f}%)")
    print(f"output   {arm_a}={out_a:.0f}  {arm_b}={out_b:.0f}  ({percent(out_a, out_b):+.1f}%)")
    print(f"flips: {arm_b} wins {wins}, {arm_a} wins {losses}")
    if excluded:
        print("excluded cells: " + ", ".join(f"{t}({a}/{b})" for t, a, b in excluded))

    for arm in (arm_a, arm_b):
        observations = defaultdict(list)
        for task in tasks:
            if arm in cells[task]:
                observations[task].append(is_pass(cells[task][arm]))
        flippers = sorted(t for t, xs in observations.items() if len(set(xs)) > 1)
        est = sum(sum(xs) / len(xs) for xs in observations.values())
        print(f"\n{arm}: {len(observations)} tasks observed in this root, "
              f"pooled expected strict ~{est:.1f}")
        if flippers:
            print(f"  tasks that flip within this root: {len(flippers)} ({', '.join(flippers)})")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("roots", nargs="+")
    parser.add_argument("--arm")
    parser.add_argument("--versus")
    args = parser.parse_args()

    status = 0
    for root in args.roots:
        cells, _ = load(root)
        arm_a, arm_b = args.arm, args.versus
        if not arm_a or not arm_b:
            arms = discover_arms(cells)
            if len(arms) < 2:
                print(f"{root}: needs two arms, found {arms}")
                status = 1
                continue
            arm_a, arm_b = arms[0], arms[1]
        status |= report(root, arm_a, arm_b)
        print()
    return status


if __name__ == "__main__":
    raise SystemExit(main())
