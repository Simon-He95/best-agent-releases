#!/bin/bash
set -euo pipefail
umask 077
export FH_ROOT="$RUNNER_TEMP/frontier"
export FH_AB_DIR="$FH_ROOT/raw"
script_root=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$script_root:$PWD/source"
export FH_REPO="$PWD/source"
export FH_LEDGER="$FH_ROOT/raw/transport.jsonl"
test -n "${FH_DIM_OAUTH_SESSION:-}"
node -e 'console.log("::add-mask::" + JSON.parse(process.env.FH_DIM_OAUTH_SESSION).access)'

unset DEEPSEEK_API_KEY OPENAI_API_KEY ANTHROPIC_API_KEY BEST_AGENT_PROVIDER_API_KEY
export FH_OAUTH_REPRO_PROXY_KEY=$(openssl rand -hex 32)
echo "::add-mask::$FH_OAUTH_REPRO_PROXY_KEY"
node "$script_root/relay.mjs" >"$FH_ROOT/raw/port" 2>"$FH_ROOT/raw/relay.log" &
relay=$!
trap 'kill "$relay" 2>/dev/null || true' EXIT
unset FH_DIM_OAUTH_SESSION
for _ in {1..50}; do
  test ! -s "$FH_ROOT/raw/port" || break
  kill -0 "$relay"
  sleep .1
done
export FH_PORT=$(cat "$FH_ROOT/raw/port")
curl --fail --silent --show-error --max-time 90 --output "$FH_ROOT/raw/preflight.json" \
  "http://127.0.0.1:$FH_PORT/preflight/v1/chat/completions" \
  -H "Authorization: Bearer $FH_OAUTH_REPRO_PROXY_KEY" -H "Content-Type: application/json" \
  -d '{"model":"deepseek-v4.1-flash","messages":[{"role":"user","content":"Reply OK."}],"max_tokens":128}'
"$FH_ROOT/venv/bin/python" - <<'CHECK'
import json,os
from pathlib import Path
d=json.loads((Path(os.environ["FH_ROOT"])/"raw/preflight.json").read_text())
assert d.get("choices") and d.get("usage"), "Missing authenticated model response or usage"
CHECK
printf 'Dim OAuth authenticated model preflight passed\n'
"$FH_ROOT/venv/bin/python" "$script_root/prepare-tasks.py" >"$FH_ROOT/raw/prepare-tasks.log" 2>&1
mounts=$(python3 -c 'import json,sys;print(json.dumps([dict(type="bind",source=sys.argv[1],target="/opt/best-agent",read_only=True)]))' "$FH_ROOT/runtime")
result=0
"$FH_ROOT/venv/bin/harbor" run -c "$FH_ROOT/raw/job-config.json" -e docker -k 1 -n 1 -y \
  --agent-import-path candidate:Candidate --model openai/deepseek-v4.1-flash \
  --ak base_instructions=true --ak api_key_env=FH_OAUTH_REPRO_PROXY_KEY \
  --jobs-dir "$FH_ROOT/raw/jobs" --mounts "$mounts" >"$FH_ROOT/raw/harbor.log" 2>&1 || result=$?
"$FH_ROOT/venv/bin/python" "$script_root/report.py"
exit "$result"
