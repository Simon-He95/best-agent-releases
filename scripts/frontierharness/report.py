import csv
import json
import os
from datetime import datetime
from pathlib import Path

root = Path(os.environ["FH_ROOT"])
rows = []

def duration(stage):
    if not stage or not stage.get("started_at") or not stage.get("finished_at"):
        return 0
    return (
        datetime.fromisoformat(stage["finished_at"].replace("Z", "+00:00"))
        - datetime.fromisoformat(stage["started_at"].replace("Z", "+00:00"))
    ).total_seconds()

for p in sorted((root / "raw/jobs").glob("*/*/result.json")):
    trial = json.loads(p.read_text())
    exception = (trial.get("exception_info") or {}).get("exception_type")
    reward = ((trial.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    file = p.parent/"agent/best-agent-evidence.jsonl"
    used = set()
    input_tokens = cache = output = 0
    provider_failure = False
    unavailable = False
    if file.exists():
        with file.open(errors="replace") as stream:
            for line in stream:
                if not any(part in line[:80] for part in ('"model-usage"', '"model-failure"', '"model-http"')):
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event["type"]=="model-usage" and event["invocationId"] not in used:
                    used.add(event["invocationId"])
                    values=event["usage"]
                    input_tokens += values.get("promptTokens") or 0
                    cache += values.get("cacheReadTokens") or 0
                    output += values.get("completionTokens") or 0
                elif event["type"]=="model-http":
                    status=(event.get("http") or {}).get("status")
                    unavailable |= status in (401,402,403,429,500,502,503,504)
                elif event["type"]=="model-failure":
                    provider_failure=True
    if exception=="AgentTimeoutError":
        category="timeout"
    elif reward==1 and not exception:
        category="pass"
    elif exception=="VerifierTimeoutError" or unavailable and provider_failure:
        category="infra"
    elif provider_failure or reward is not None and not exception:
        category="fail"
    else:
        category="infra"
    rows.append({
        "task":trial["task_name"],"outcome":category,
        "agent_seconds":round(duration(trial.get("agent_execution")),3),
        "verifier_seconds":round(duration(trial.get("verifier")),3),
        "input_tokens":input_tokens,"cache_read_tokens":cache,"output_tokens":output,
    })

if not rows:
    raise SystemExit("No Harbor trial results")
job=next((root/"raw/jobs").glob("*/result.json"))
job_results=json.loads(job.read_text())
public=root/"report"
with (public/"tasks.csv").open("w",newline="") as out:
    writer=csv.DictWriter(out,fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
summary={
    "source_sha":os.environ["SOURCE_SHA"],
    "dataset":"frontier-harness-eval@v1.1.0",
    "provider":"api.deepseek.com",
    "model":"deepseek-flash",
    "planned":job_results["n_total_trials"],
    "completed":len(rows),
    "started_at":job_results["started_at"],
    "finished_at":job_results["finished_at"],
    **{outcome:sum(t["outcome"]==outcome for t in rows) for outcome in ("pass","fail","timeout","infra")},
}
(public/"summary.json").write_text(json.dumps(summary,indent=2)+"\n")
print(json.dumps(summary))
if summary["completed"] != summary["planned"]:
    raise SystemExit("The benchmark did not finish every scheduled trial")
