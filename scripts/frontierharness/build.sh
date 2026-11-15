#!/bin/bash
set -euo pipefail
mkdir -p "$FH_ROOT/packed" "$FH_ROOT/runtime/bin"
cp "$(realpath "$(command -v node)")" "$FH_ROOT/runtime/bin/node"
cd source
corepack install
pnpm install --frozen-lockfile
node scripts/pack-cli-node.mjs "$FH_ROOT/packed"
npm install --global --prefix "$FH_ROOT/runtime" --no-fund --no-audit "$FH_ROOT"/packed/*.tgz
PATH="$FH_ROOT/runtime/bin:$PATH" "$FH_ROOT/runtime/bin/best-agent" --version
