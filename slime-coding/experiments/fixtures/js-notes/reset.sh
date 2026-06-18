#!/usr/bin/env bash
set -eu
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
git -C "$DIR" checkout -- "$DIR"
git -C "$DIR" clean -fdq "$DIR"
echo "js-notes reset to baseline"
