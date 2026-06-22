#!/usr/bin/env bash
# Same as run-bench.sh but with the bait clause "we'll likely add more
# later" REMOVED from the prompt. Tests whether the bait was carrying the
# over-engineering signal — i.e. whether models without an explicit
# extensibility hint still build dispatch tables.
#
#   experiments/run-bench-no-bait.sh [conditions] [runs]
#     conditions : default "hooked-slime"; pass "baseline" to skip Slime
#     runs       : runs per cell, default 3
#
# Env knobs (same as run-bench.sh / run-bvc.sh):
#   BVC_MODEL : passes --model <id> to claude -p (e.g. claude-haiku-4-5)
#   BVC_DATE  : output directory tag (default 2026-06-22-bench-no-bait)
#
# Task B2 (the only one here): "Add support for TSV input. Keep pytest -q
# green." — minimal phrasing, no extensibility hint.

set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH="$REPO/experiments/slime-bench"
DATE="${BVC_DATE:-2026-06-22-bench-no-bait}"
ROOT="$REPO/experiments/runs/${DATE}"
LOGDIR="$ROOT/_logs"
mkdir -p "$LOGDIR"

CONDITIONS="${1:-hooked-slime}"
NRUNS="${2:-3}"

MODEL="${BVC_MODEL:-}"
MODEL_ARGS=()
[ -n "$MODEL" ] && MODEL_ARGS=(--model "$MODEL")

export SLIME_TEST_CMD="${SLIME_TEST_CMD:-python3 -m pytest -q}"

B2_PROMPT="Add support for TSV input. Keep \`python3 -m pytest -q\` green."

for cond in $CONDITIONS; do
  for n in $(seq 1 "$NRUNS"); do
    cell="$ROOT/B2/$cond/run$n"
    tag="B2-$cond-run$n"
    if [ -e "$cell" ]; then
      echo "skip (exists): $tag"
      continue
    fi
    echo "=== $tag : new-cell ==="
    if ! python3 "$BENCH" new-cell --task B2 --condition "$cond" \
          --run "$n" --fixture csv-tsv-pipeline --root "$ROOT" >/dev/null; then
      echo "  new-cell FAILED for $tag" >&2
      continue
    fi

    echo "=== $tag : agent run (model=${MODEL:-default}) ==="
    ( cd "$cell" && timeout 590 claude -p "$B2_PROMPT" \
        "${MODEL_ARGS[@]}" \
        --setting-sources project,local \
        --permission-mode bypassPermissions \
        --output-format stream-json --verbose \
        > "$LOGDIR/$tag.jsonl" 2> "$LOGDIR/$tag.err" )
    echo "  agent exit=$?"

    ( cd "$cell" && python3 -m pytest -q > "$LOGDIR/$tag.pytest" 2>&1 )
    echo "  pytest exit=$? -> $LOGDIR/$tag.pytest"
    # Intent-to-add untracked files so they appear in `diff HEAD` as new files,
    # otherwise score.py's M4 (new_files via `^new file mode`) under-counts.
    git -C "$cell" add -N pipeline tests 2>/dev/null
    git -C "$cell" --no-pager diff HEAD -- pipeline tests > "$LOGDIR/$tag.diff" 2>&1

    python3 "$BENCH" measure "$cell" >/dev/null && echo "  measured -> $cell/metrics.json"
  done
done

echo
echo "=== aggregate ($ROOT) ==="
python3 "$BENCH" aggregate "$ROOT"
