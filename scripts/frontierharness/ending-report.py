"""Classify how each trial ended, so a failure can be attributed to its shape.

`pair-report.py` answers "which arm passed more tasks". This answers "why did the failing
trials fail", which is a different question and the one that decides whether a cap or a
prompt is the right lever.

The shape that motivated this report: at an output cap of 32768, a trial's final turn can
spend the entire budget on reasoning, return zero content and zero tool calls, and still be
recorded as a completed run. Such a cell looks like an ordinary wrong answer in the score
table, and reading it as a model mistake hides the real cause.

The cap that a trial actually ran with is read from the package's own `transport.jsonl`,
the same ledger `report.py` trusts, not from a directory name or a current arm table: after
an arm is renamed or its cap changes, a name would mislabel an old package.

`share` is the trial's reasoning tokens over its output tokens. A `+` after it means some turn
reported no `reasoningTokens`, so the value is a lower bound rather than a measurement.

`mut` and `paths` answer a different question from `shape`: how the trial spent its edits.
`mut` counts turns that emitted a file-writing call (`write`, `apply_patch`, `edit`) and `paths`
the distinct normalized spellings those calls named. Both count what the model proposed, so a
call the tool gate refused still counts; and a shell redirection inside `exec` writes a file
without appearing here, so both numbers are floors. A path named absolutely in one call and
relatively in another counts twice, because resolving it would need the trial's workspace root.

`edit` separates two shapes that `shape` alone conflates, using only those floors:
`rework` (at least eight edit turns and at most half as many targets — the same few files
rewritten), `spread` (at least eight edit turns over more targets — many files, few rewrites),
`few` (fewer than eight), and `-` for a trial with nothing to explain. The distinction matters
because the two shapes call for opposite instructions, and neither says anything about
under-delivery: a trial that built its deliverable through shell redirection also shows zero.

This column describes effort, it does not predict outcome. On the 62-trial archive both shapes
appear on solved and unsolved trials alike (rework: `adaptive-rejection-sampler` reached reward
1.0 with 24 turns on one file; spread: `dna-insert`, `large-scale-text-editing` and `tune-mjcf`
reached 1.0 over 20–26 targets). Failing trials do spend more edit turns on average — median 18
against 3 — but no per-trial shape separates the two groups, so an instruction that targets one
shape is not thereby targeting failure.

usage: ending-report.py DIAGNOSTICS_ROOT [--arms arms.json]

DIAGNOSTICS_ROOT contains one directory per decrypted package, each holding `profile.json`
and `raw/jobs/...`; the report walks down to the trial evidence itself.
"""

import argparse
import json
import posixpath
import re
from collections import Counter
from pathlib import Path

ORD = re.compile(r",(\d+)\]$")
SHAPES = ("pass", "starvation", "timeout", "no-deliverable", "answered-wrong", "infra")
WRITE_TOOLS = ("write", "apply_patch", "edit")
HEAVY_MUTATIONS = 8
PATH_PATTERN = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+)$|^\+\+\+ b/(.+)$", re.M)


def written_targets(call):
    """The file(s) one writing tool call names, across the shapes those tools accept."""
    payload = call.get("input")
    if not isinstance(payload, dict):
        try:
            payload = json.loads(payload or "{}")
        except Exception:
            return []
    if not isinstance(payload, dict):
        # A provider can leave an unparsable argument as a string; a malformed call is a
        # fact about that call, not a reason to lose the whole tree.
        return []
    found = [payload[key] for key in ("path", "file_path", "file")
             if isinstance(payload.get(key), str)]
    patch = payload.get("patch")
    if isinstance(patch, str):
        found.extend(next(group for group in match if group) for match in PATH_PATTERN.findall(patch))
    return [posixpath.normpath(target.strip()) for target in found if target.strip()]


def edit_shape(outcome, facts):
    """Separates rewriting a few files from spreading edits over many."""
    if outcome in ("pass", None):
        return "-"
    if facts["mutating"] < HEAVY_MUTATIONS:
        return "few"
    return "rework" if facts["paths"] * 2 <= facts["mutating"] else "spread"


def ordinal(invocation_id):
    match = ORD.search(invocation_id or "")
    return int(match.group(1)) if match else None


def trial_facts(evidence_path):
    """Per-turn usage, tool-call counts and written targets for one trial."""
    usage, calls, content, written, mutating = {}, {}, {}, set(), set()
    for line in evidence_path.open("rb"):
        try:
            event = json.loads(line)
        except Exception:
            continue
        index = ordinal(event.get("invocationId"))
        if index is None:
            continue
        kind = event.get("type")
        if kind == "model-usage":
            usage[index] = event.get("usage") or {}
        elif kind == "model-outcome":
            candidate = (event.get("outcome") or {}).get("candidate") or {}
            tool_calls = candidate.get("toolCalls") or candidate.get("tool_calls") or []
            if not isinstance(tool_calls, list):
                tool_calls = []
            calls[index] = len(tool_calls)
            for call in tool_calls:
                if not isinstance(call, dict):
                    continue
                if str(call.get("name") or "").lower() not in WRITE_TOOLS:
                    continue
                mutating.add(index)
                written.update(written_targets(call))
            raw = json.dumps(candidate.get("content")) if candidate.get("content") is not None else ""
            content[index] = max(len(raw) - 2, 0)
    if not usage:
        return None
    last = max(usage)
    return {
        "turns": len(usage),
        "completion": usage[last].get("completionTokens", 0),
        "reasoning": usage[last].get("reasoningTokens", 0),
        "calls": calls.get(last, 0),
        "content": content.get(last, 0),
        "output": sum(v.get("completionTokens", 0) for v in usage.values()),
        # Reasoning over the whole trial, not only its last turn. A change can move this share
        # without moving the pass rate, and reading only the last turn hides that.
        "reasoning_total": sum(v.get("reasoningTokens", 0) for v in usage.values()),
        # A provider that reports no reasoning leaves the field out; counting those turns as
        # zero would understate the share silently, so the report marks the value a lower bound.
        "reasoning_turns": sum(1 for v in usage.values() if "reasoningTokens" in v),
        "mutating": len(mutating),
        "paths": len(written),
    }


def reward_outcome(trial_dir):
    result = trial_dir / "result.json"
    if not result.exists():
        return None
    try:
        data = json.loads(result.read_text())
    except Exception:
        return None
    reward = ((data.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    exception = (data.get("exception_info") or {}).get("exception_type")
    if exception == "AgentTimeoutError":
        return "timeout", reward
    if reward == 1 and not exception:
        return "pass", reward
    if reward is not None:
        return "fail", reward
    return "infra", reward


def shape_of(outcome, facts, cap):
    if outcome in (None, "infra"):
        return "infra"
    if outcome == "pass":
        return "pass"
    if outcome == "timeout":
        return "timeout"
    starved = (cap and facts["completion"] >= cap
               and facts["reasoning"] >= cap * 0.95
               and facts["calls"] == 0 and facts["content"] == 0)
    if starved:
        return "starvation"
    if facts["calls"] == 0 and facts["content"] == 0:
        return "no-deliverable"
    return "answered-wrong"


def ledgers_for(trial_dir):
    """transport.jsonl files beside this trial's package."""
    for parent in trial_dir.parents:
        candidate = parent / "raw/transport.jsonl"
        if candidate.exists():
            return candidate
        if parent == parent.parent:
            break
    return None


def cap_of(ledger, tag):
    """The output cap the relay recorded for this trial's requests."""
    caps = set()
    if not ledger:
        return None
    for line in ledger.open():
        try:
            entry = json.loads(line)
        except Exception:
            continue
        if entry.get("phase") != "request" or entry.get("tag") != tag:
            continue
        if isinstance(entry.get("output_cap"), int):
            caps.add(entry["output_cap"])
    return max(caps) if len(caps) == 1 else (max(caps) if caps else None)


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root")
    parser.add_argument("--arms", default=str(Path(__file__).with_name("arms.json")))
    args = parser.parse_args()

    arms = {}
    arms_path = Path(args.arms)
    if arms_path.exists():
        arms = {name: spec.get("output_cap") for name, spec in json.loads(arms_path.read_text()).items()}

    root = Path(args.root)
    table = []
    for evidence in sorted(root.rglob("agent/best-agent-evidence.jsonl")):
        trial_dir = evidence.parent.parent
        outcome, reward = reward_outcome(trial_dir) or (None, None)
        facts = trial_facts(evidence)
        if not facts:
            continue
        cap = cap_of(ledgers_for(trial_dir), trial_dir.name)
        table.append((cap, trial_dir.name, outcome, reward, facts,
                      shape_of(outcome, facts, cap), cap))

    if not table:
        print(f"{root}: no trial evidence found")
        return 1

    by_arm = Counter((cap, shape) for cap, _, _, _, _, shape, _ in table)
    print(f"{'cap':>8} {'trial':<44}{'outcome':>9}{'turns':>6}{'lastC':>8}{'lastR':>8}"
          f"{'share':>8}{'mut':>5}{'paths':>6}  {'shape':<14} edit")
    for cap, name, outcome, _, facts, shape, _ in table:
        share = (facts["reasoning_total"] / facts["output"] * 100) if facts["output"] else 0
        exact = facts["reasoning_turns"] == facts["turns"]
        mark = "+" if not exact else " "
        print(f"{str(cap):>8} {name[:42]:<44}{str(outcome):>9}{facts['turns']:>6}"
              f"{facts['completion']:>8}{facts['reasoning']:>8}{share:>6.0f}%{mark}"
              f"{facts['mutating']:>5}{facts['paths']:>6}  "
              f"{shape:<14} {edit_shape(outcome, facts)}")

    print()
    for cap in sorted({row[0] for row in table}, key=lambda v: (v is None, v)):
        total = sum(1 for row in table if row[0] == cap)
        parts = [f"{shape}={by_arm[(cap, shape)]}" for shape in SHAPES if by_arm[(cap, shape)]]
        print(f"cap={cap}: {total} trials — " + ", ".join(parts))
    outputs = sum(row[4]["output"] for row in table)
    reasoning = sum(row[4]["reasoning_total"] for row in table)
    if outputs:
        partial = [row[1] for row in table
                   if row[4]["reasoning_turns"] != row[4]["turns"]]
        print(f"whole tree: {len(table)} trials, output={outputs}, "
              f"reasoning={reasoning} ({'at least ' if partial else ''}"
              f"{reasoning / outputs * 100:.0f}% of output)")
        if partial:
            print(f"  {len(partial)} trial(s) report no reasoning tokens on some turn, so the "
                  f"share is a lower bound: {', '.join(partial[:6])}"
                  f"{' …' if len(partial) > 6 else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
