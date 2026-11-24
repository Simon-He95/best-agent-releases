#!/bin/bash
# Publish the per-task score reports to the bench-results branch.
#
# The artifacts API is the only other way to read these files, and it is unreachable on
# hosts where api.github.com is filtered. A branch turns the scores into a plain
# `git fetch results/<run_id>/...`, so take them from there.
#
# Layout on the branch (one directory per workflow run):
#   results/<run_id>/score-<profile>-<task>/{profile.json,summary.json,tasks.csv}
#   results/<run_id>/meta.json
#
# Every push attempt starts from a fresh clone, so a concurrent run that moved the
# branch is picked up instead of being overwritten.
set -euo pipefail
shopt -s nullglob

: "${RUN_ID:?RUN_ID is required}"
: "${REPO:?REPO is required}"
: "${RUNNER_TEMP:?RUNNER_TEMP is required}"

scores="${SCORES_DIR:-$RUNNER_TEMP/scores}"
branch="${RESULT_BRANCH:-bench-results}"
remote="${RESULT_REMOTE:-https://github.com/${REPO}.git}"
push_remote="${RESULT_PUSH_REMOTE:-}"
if [ -z "$push_remote" ]; then
  : "${PUSH_TOKEN:?PUSH_TOKEN is required unless RESULT_PUSH_REMOTE is set}"
  push_remote="https://x-access-token:${PUSH_TOKEN}@github.com/${REPO}.git"
fi

work="$RUNNER_TEMP/bench-results"
err="$RUNNER_TEMP/bench-results-push.log"
label_suffix=""
[ -n "${LABEL:-}" ] && label_suffix=" (${LABEL})"

dir_empty() {
  [ -z "$(ls -A "$1" 2>/dev/null)" ]
}

prepare_clone() {
  rm -rf "$work"
  if git ls-remote --exit-code --heads "$remote" "$branch" >/dev/null 2>&1; then
    git clone --quiet --depth 1 --branch "$branch" "$remote" "$work"
  else
    git clone --quiet --depth 1 "$remote" "$work"
    git -C "$work" checkout --quiet --orphan "$branch"
    git -C "$work" rm -rfq --ignore-unmatch .
    cat >"$work/README.md" <<'DOC'
# bench-results

Per-task FrontierHarness score reports, one directory per workflow run:

    results/<run_id>/score-<profile>-<task>/{profile.json,summary.json,tasks.csv}
    results/<run_id>/meta.json

Written by `.github/workflows/frontierharness-benchmark.yml`. Do not edit by hand.
DOC
    git -C "$work" add -- README.md
  fi
  git -C "$work" config user.name "github-actions[bot]"
  git -C "$work" config user.email "41898282+github-actions[bot]@users.noreply.github.com"
}

# Returns non-zero when the run has no score files at all.
stage_results() {
  local dest="$work/results/$RUN_ID" dir name target file
  mkdir -p "$dest"
  for dir in "$scores"/*/; do
    name=$(basename "$dir")
    case "$name" in score-*) ;; *) continue ;; esac
    target="$dest/$name"
    mkdir -p "$target"
    for file in profile.json summary.json tasks.csv; do
      [ -f "$dir/$file" ] && cp "$dir/$file" "$target/$file"
    done
    if dir_empty "$target"; then rmdir "$target"; fi
  done
  if dir_empty "$dest"; then
    rmdir "$dest" 2>/dev/null || true
    return 1
  fi
  RUN_ID="$RUN_ID" RUN_URL="${RUN_URL:-}" SOURCE_SHA="${SOURCE_SHA:-}" \
    LABEL="${LABEL:-}" FIRST="${FIRST:-}" SECOND="${SECOND:-}" REPO="$REPO" \
    WORKFLOW_REF="${WORKFLOW_REF:-}" \
    python3 - "$dest/meta.json" <<'PY'
import json
import os
import sys

profiles = [
    profile for profile in (os.environ["FIRST"], os.environ["SECOND"])
    if profile and profile != "none"
]
meta = {
    "run_id": os.environ["RUN_ID"],
    "run_url": os.environ["RUN_URL"],
    "source_sha": os.environ["SOURCE_SHA"],
    "label": os.environ["LABEL"],
    "profiles": profiles,
    "repository": os.environ["REPO"],
    "workflow_ref": os.environ["WORKFLOW_REF"],
}
with open(sys.argv[1], "w") as f:
    json.dump(meta, f, indent=2, sort_keys=True)
    f.write("\n")
PY
  git -C "$work" add --all -- results
}

if dir_empty "$scores"; then
  echo "no score artifacts for run $RUN_ID; nothing to publish"
  exit 0
fi

delay=3
for attempt in 1 2 3 4 5; do
  prepare_clone
  if ! stage_results; then
    echo "no score files for run $RUN_ID; nothing to publish"
    exit 0
  fi
  if git -C "$work" diff --cached --quiet -- results; then
    echo "run $RUN_ID is already published on $branch"
    exit 0
  fi
  git -C "$work" commit -q -m "bench: scores for run $RUN_ID${label_suffix}"
  if git -C "$work" push --quiet "$push_remote" "HEAD:$branch" 2>"$err"; then
    echo "published results/$RUN_ID to $branch (attempt $attempt)"
    exit 0
  fi
  echo "push attempt $attempt failed; retrying from a fresh clone" >&2
  sed 's#x-access-token:[^@]*@#x-access-token:***@#g' "$err" >&2 || true
  sleep "$delay"
  delay=$((delay * 2))
done

echo "could not publish results for run $RUN_ID to $branch" >&2
exit 1
