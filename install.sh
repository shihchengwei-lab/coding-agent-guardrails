#!/usr/bin/env bash
# Thin POSIX entrypoint for the shared transactional installer.
set -euo pipefail

TOOLKIT_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="$PWD"
DRY_RUN=0

while [ "$#" -gt 0 ]; do
  case "$1" in
    --dry-run) DRY_RUN=1 ;;
    -*) echo "error: unknown option: $1" >&2; exit 2 ;;
    *)
      if [ "$PROJECT" != "$PWD" ]; then
        echo "error: only one project path may be supplied" >&2
        exit 2
      fi
      PROJECT="$1"
      ;;
  esac
  shift
done

PYTHON=""
for candidate in python python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON="$candidate"
    break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "error: Python 3.11 or newer is required" >&2
  exit 1
fi

PYTHON_EXE="$($PYTHON -c 'import sys; print(sys.executable)')"
ARGS=(install "$PROJECT" --source "$TOOLKIT_HOME" --python "$PYTHON_EXE")
[ "$DRY_RUN" -eq 0 ] || ARGS+=(--dry-run)
exec "$PYTHON" "$TOOLKIT_HOME/installer/guardrails_installer.py" "${ARGS[@]}"
