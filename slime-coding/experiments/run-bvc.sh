#!/usr/bin/env bash
# BvC — one-command runner for the "does the hooked stack add anything beyond
# prompt-only?" probe (reports/<date>-bvc.md). Adds condition C (hooked-slime)
# and optionally D (hooked-no-l1) for E1/E2/E3, reusing the existing
# extensibility A/B runs (do NOT re-run those).
#
#   experiments/run-bvc.sh [conditions] [runs]
#     conditions : space-separated, default "hooked-slime" (add "hooked-no-l1" for D)
#     runs       : runs per cell, default 3
#
# Corridor handling: the agent AUTHORS its own corridor (the C/D gate forces it
# corridor-first), matching how the reused 2026-06-18 B runs were done, so the
# B-vs-C delta isn't confounded by C getting a free pre-seeded corridor. We do
# NOT pre-seed.
#
# Per cell it: new-cell (installs the condition stack incl. CLAUDE.md discipline)
# -> runs the agent as a separate, cell-rooted, non-interactive `claude -p` with
# --setting-sources project,local (loads the cell's project hooks for C/D;
# excludes the host user's ~/.claude so nothing leaks in) -> measures the
# working tree against the fixture baseline commit that new-cell already made.
#
# Agent transcripts go to <root>/_logs/ — OUTSIDE the measured tree, so they are
# not counted as new_files by metrics.py. OAuth/CLI only; no billed API.
set -u

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH="$REPO/experiments/slime-bench"
DATE="${BVC_DATE:-2026-06-21}"
ROOT="$REPO/experiments/runs/${DATE}-bvc"
LOGDIR="$ROOT/_logs"
mkdir -p "$LOGDIR"

CONDITIONS="${1:-hooked-slime}"
NRUNS="${2:-3}"

# The Stop gate's failing-check arm only has teeth when a check command exists.
export SLIME_TEST_CMD="${SLIME_TEST_CMD:-python3 -m pytest -q}"

prompt_for() {
  case "$1" in
    E1) printf '%s' "Add an \`export <file>\` subcommand to the notes CLI that writes all stored notes to the given file as JSON. We'll likely add more export formats (csv, md) later. Keep \`python3 -m pytest -q\` green." ;;
    E2) printf '%s' "Add a \`stats\` subcommand to the notes CLI that prints the number of notes. We'll likely add more stats (avg length, oldest) later. Keep \`python3 -m pytest -q\` green." ;;
    E3) printf '%s' "Add a \`--sort text\` option to the \`list\` subcommand that lists notes alphabetically by their text. We'll likely add more sort keys (id, created) later. Keep \`python3 -m pytest -q\` green." ;;
  esac
}

for task in E1 E2 E3; do
  for cond in $CONDITIONS; do
    for n in $(seq 1 "$NRUNS"); do
      cell="$ROOT/$task/$cond/run$n"
      tag="$task-$cond-run$n"
      if [ -e "$cell" ]; then
        echo "skip (exists): $tag"
        continue
      fi
      echo "=== $tag : new-cell ==="
      if ! python3 "$BENCH" new-cell --task "$task" --condition "$cond" \
            --run "$n" --fixture cli-notes --root "$ROOT" >/dev/null; then
        echo "  new-cell FAILED for $tag" >&2
        continue
      fi

      echo "=== $tag : agent run ==="
      ( cd "$cell" && timeout 590 claude -p "$(prompt_for "$task")" \
          --setting-sources project,local \
          --permission-mode bypassPermissions \
          --output-format stream-json --verbose \
          > "$LOGDIR/$tag.jsonl" 2> "$LOGDIR/$tag.err" )
      echo "  agent exit=$?"

      # Deterministic checks captured next to the log (human fields stay human-
      # judged in metrics.json; this is just evidence, not auto-fill).
      ( cd "$cell" && python3 -m pytest -q > "$LOGDIR/$tag.pytest" 2>&1 )
      echo "  pytest exit=$? -> $LOGDIR/$tag.pytest"
      git -C "$cell" --no-pager diff HEAD -- cli_notes tests > "$LOGDIR/$tag.diff" 2>&1

      python3 "$BENCH" measure "$cell" >/dev/null && echo "  measured -> $cell/metrics.json"
    done
  done
done

echo
echo "=== aggregate ($ROOT) ==="
python3 "$BENCH" aggregate "$ROOT"
