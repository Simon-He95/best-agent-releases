import csv
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

root = Path(os.environ["FH_ROOT"])
profile = json.loads((root / "report/profile.json").read_text())
ledger = defaultdict(list)
for line in (root / "raw/transport.jsonl").open():
    entry = json.loads(line)
    ledger[entry["tag"]].append(entry)


def seconds(stage):
    if not stage or not stage.get("started_at") or not stage.get("finished_at"):
        return None
    start, end = (
        datetime.fromisoformat(stage[key].replace("Z", "+00:00"))
        for key in ("started_at", "finished_at")
    )
    return (end - start).total_seconds()


rows = []
for path in sorted((root / "raw/jobs").glob("*/*/result.json")):
    result = json.loads(path.read_text())
    entries = ledger[path.parent.name]
    requests = [v for v in entries if v["phase"] == "request"]
    receipts = [v["usage"] for v in entries if v["phase"] == "finish" and v.get("usage")]
    if requests:
        first = requests[0]
        assert first["model"] == "deepseek-v4.1-flash"
        assert first["tool_count"] == 31 and first["deadline"] is False
        assert first["baseline_first_instruction"] == profile["prompt_sha256"]
        assert {r.get("effort") for r in requests} == {"max"}
    root_id = None
    source_failure = None
    terminal = None
    trace = path.parent / "agent/best-agent-evidence.jsonl"
    if trace.exists():
        for line in trace.open("rb"):
            if not any(marker in line[:130] for marker in (
                b'"type":"header"', b'"type":"model-failure-diagnostic"',
                b'"type":"terminal-snapshot"',
            )):
                continue
            event = json.loads(line)
            if event["type"] == "header":
                root_id = event["rootRunId"]
            elif event.get("runId") == root_id and event["type"] == "model-failure-diagnostic":
                source_failure = event["sourceReason"]
            elif event.get("runId") == root_id and event["type"] == "terminal-snapshot":
                terminal = event["snapshot"]["status"]
    exception = (result.get("exception_info") or {}).get("exception_type")
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    statuses = [v["status"] for v in entries if v["phase"] == "headers"]
    if exception == "AgentTimeoutError":
        outcome = "timeout"
    elif source_failure in ("connection", "transport"):
        outcome = "infra"
    elif reward == 1 and not exception:
        outcome = "pass"
    elif exception == "VerifierTimeoutError" or (
        exception and any(s in (401, 402, 403, 429, 500, 502, 503, 504) for s in statuses)
    ):
        outcome = "infra"
    elif reward is not None:
        outcome = "fail"
    else:
        outcome = "infra"
    checks = {}
    ctrf = path.parent / "verifier/ctrf.json"
    if ctrf.exists():
        checks = json.loads(ctrf.read_text())["results"]["summary"]
    stdout = path.parent / "verifier/test-stdout.txt"
    if outcome == "fail" and not checks and stdout.exists():
        tail = stdout.read_bytes()[-8192:]
        if b"curl: (18)" in tail and b"uvx: command not found" in tail:
            outcome = "infra"
            exception = "VerifierBootstrapDownloadFailed"
    timing_path = path.parent / "agent/artifact-timing.json"
    timing = json.loads(timing_path.read_text()) if timing_path.is_file() else None
    rows.append({
        "exec_cutoff_ms": 120_000, "artifact_timing": json.dumps(timing),
        "task": result["task_name"], "profile": profile["profile"], "outcome": outcome,
        "reward": reward, "exception": exception, "source_failure": source_failure,
        "terminal": terminal, "checksum": result["task_checksum"],
        "agent_seconds": seconds(result.get("agent_execution")),
        "verifier_seconds": seconds(result.get("verifier")),
        "input_tokens": sum(v.get("prompt_tokens", 0) for v in receipts),
        "cache_read_tokens": sum(
            (v.get("prompt_tokens_details") or {}).get(
                "cached_tokens", v.get("prompt_cache_hit_tokens", 0)
            ) for v in receipts
        ),
        "output_tokens": sum(v.get("completion_tokens", 0) for v in receipts),
        "model_requests": len(requests), "requests_with_usage": len(receipts),
        "tool_digest": requests[0].get("tool_digest") if requests else None,
        "system_count": requests[0].get("system_count") if requests else None,
        "checks_passed": checks.get("passed"), "checks_total": checks.get("tests"),
    })
if not rows:
    raise SystemExit("No Harbor task was scored")
with (root / "report/tasks.csv").open("w", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
planned = len(json.loads((root / "raw/tasks.json").read_text()))
summary = {
    **profile, "dataset": "frontier-harness-eval@v1.1.0",
    "provider": "Dim OAuth", "model": "deepseek-v4.1-flash",
    "planned": planned, "completed": len(rows),
    **{
        label: sum(r["outcome"] == label for r in rows)
        for label in ("pass", "fail", "timeout", "infra")
    },
    **{
        label: sum(r[label] for r in rows)
        for label in (
            "input_tokens", "cache_read_tokens", "output_tokens",
            "model_requests", "requests_with_usage",
        )
    },
}
(root / "report/summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary))
if len(rows) != planned:
    raise SystemExit("Scheduled cohort remains incomplete")
