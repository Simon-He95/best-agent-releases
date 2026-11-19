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
    root_id = None
    source_failure = None
    source_http_status = None
    reference_reads = 0
    terminal = None
    trace = path.parent / "agent/best-agent-evidence.jsonl"
    if trace.exists():
        for line in trace.open("rb"):
            if not any(marker in line[:130] for marker in (
                b'"type":"header"', b'"type":"model-failure-diagnostic"',
                b'"type":"terminal-snapshot"', b'"type":"model-outcome"',
            )):
                continue
            event = json.loads(line)
            if event["type"] == "header":
                root_id = event["rootRunId"]
            elif event.get("runId") == root_id and event["type"] == "model-failure-diagnostic":
                source_failure = event["sourceReason"]
                source_http_status = event["diagnostic"].get("statusCode")
            elif event.get("runId") == root_id and event["type"] == "terminal-snapshot":
                terminal = event["snapshot"]["status"]
            elif event["type"] == "model-outcome":
                tool_calls = (event.get("outcome", {}).get("candidate") or {}).get("toolCalls", [])
                reference_reads += sum(
                    call["name"] in ("read", "search", "exec", "process-start")
                    and ".best-agent-exec-results/" in json.dumps(call.get("input"))
                    for call in tool_calls
                )
    exception = (result.get("exception_info") or {}).get("exception_type")
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    statuses = [v["status"] for v in entries if v["phase"] == "headers"]
    if exception == "AgentTimeoutError":
        outcome = "timeout"
    elif source_http_status in (400, 413) and source_failure == "transport":
        outcome = "request_rejected"
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
    projections = [entry for entry in entries if entry["phase"] == "projected"]
    retained = [entry for entry in entries if entry["phase"] == "retained"]
    forwarded_sizes = {entry["id"]: entry["after"] for entry in projections}
    rows.append({
        "experiment": os.environ["FH_EXPERIMENT"], "exec_cutoff_ms": 120_000,
        "source_http_status": source_http_status,
        "projected_requests": len(projections), "reference_reads": reference_reads,
        "retained_receipts": len(retained),
        "retained_stdout_bytes": sum(entry["stdoutBytes"] for entry in retained),
        "retention_failures": sum(entry["phase"] == "retention-failure" for entry in entries),
        "projected_wire_bytes_saved": sum(entry["before"] - entry["after"] for entry in projections),
        "peak_reported_prompt_tokens": max((v.get("prompt_tokens", 0) for v in receipts), default=0),
        "max_forwarded_request_bytes": max(
            (forwarded_sizes.get(entry["id"], entry["bytes"])
             for entry in requests), default=0,
        ),
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
        for label in ("pass", "fail", "timeout", "request_rejected", "infra")
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
