#!/bin/bash
set -euo pipefail
umask 077
export FH_ROOT="${FH_ROOT:-$RUNNER_TEMP/frontier}"
export FH_AB_DIR="$FH_ROOT/raw"
mkdir -p "$FH_AB_DIR/cutoff"
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
