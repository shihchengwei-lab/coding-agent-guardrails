#!/usr/bin/env bash
# Reset the cli-notes fixture to its committed baseline: discard tracked-file
# edits and remove anything an experiment run created (.slime/, .claude/,
# notes.json, __pycache__, ...).
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
git -C "$DIR" checkout -- "$DIR"
git -C "$DIR" clean -fdq "$DIR"
echo "cli-notes reset to baseline"
