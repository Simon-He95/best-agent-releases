#!/bin/bash
set -euo pipefail
mkdir -p "$FH_ROOT/packed" "$FH_ROOT/runtime/bin"
cp "$(realpath "$(command -v node)")" "$FH_ROOT/runtime/bin/node"
npm install --global --prefix "$FH_ROOT/runtime" --no-fund --no-audit npm@11.19.1 pnpm@10.34.9
cd source
corepack install
pnpm install --frozen-lockfile
node scripts/pack-cli-node.mjs "$FH_ROOT/packed"
npm install --global --prefix "$FH_ROOT/runtime" --no-fund --no-audit "$FH_ROOT"/packed/*.tgz
PATH="$FH_ROOT/runtime/bin:$PATH" "$FH_ROOT/runtime/bin/best-agent" --version
PATH="$FH_ROOT/runtime/bin:$PATH" "$FH_ROOT/runtime/bin/npm" --version
PATH="$FH_ROOT/runtime/bin:$PATH" "$FH_ROOT/runtime/bin/npx" --version
PATH="$FH_ROOT/runtime/bin:$PATH" "$FH_ROOT/runtime/bin/pnpm" --version
