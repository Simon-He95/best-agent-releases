#!/bin/bash
set -euo pipefail
umask 077
export FH_ROOT="$RUNNER_TEMP/frontier"
script_root=$(cd "$(dirname "$0")" && pwd)
export PYTHONPATH="$script_root:$PWD/source"
test -n "${DEEPSEEK_API_KEY:-}"
export FH_RELAY_TOKEN=$(openssl rand -hex 24)
echo "::add-mask::$FH_RELAY_TOKEN"
node "$script_root/relay.mjs" > "$FH_ROOT/raw/port" 2> "$FH_ROOT/raw/relay.log" &
relay=$!
trap 'kill "$relay" 2>/dev/null || true' EXIT
unset DEEPSEEK_API_KEY
for _ in {1..50}; do
  test ! -s "$FH_ROOT/raw/port" || break
  kill -0 "$relay"
  sleep .1
done
export FH_PORT=$(cat "$FH_ROOT/raw/port")
test -n "$FH_PORT"
curl --fail --silent --show-error --max-time 45 --output "$FH_ROOT/raw/preflight.json" \
  "http://127.0.0.1:$FH_PORT/v1/chat/completions" \
  -H "Authorization: Bearer $FH_RELAY_TOKEN" -H 'Content-Type: application/json' \
  -d '{"model":"deepseek-flash","messages":[{"role":"user","content":"Reply OK."}],"max_tokens":32}'
printf 'Official DeepSeek preflight returned HTTP 200\n'
mounts=$(python3 -c 'import json,sys;print(json.dumps([dict(type="bind",source=sys.argv[1],target="/opt/best-agent",read_only=True)]))' "$FH_ROOT/runtime")
args=()
IFS=, read -r -a tasks <<< "${FH_TASKS:-}"
for task in "${tasks[@]}"; do
  args+=(-i "terminal-bench/$task")
done
result=0
"$FH_ROOT/venv/bin/harbor" run -d frontier-harness-eval/frontier-harness-eval@v1.1.0 -e docker -k 1 -n 4 -y \
  --agent-import-path candidate:Candidate --model deepseek/deepseek-flash --ak base_instructions=true --ak api_key_env=FH_RELAY_TOKEN \
  --jobs-dir "$FH_ROOT/raw/jobs" --mounts "$mounts" "${args[@]}" > "$FH_ROOT/raw/harbor.log" 2>&1 || result=$?
"$FH_ROOT/venv/bin/python" "$script_root/report.py"
exit "$result"
