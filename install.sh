#!/usr/bin/env bash
# Coding Agent Guardrails — one-command install.
#
# Installs the whole toolkit into a target project:
#   1. the unified discipline block into the project's CLAUDE.md
#      (managed block, replaced in place on re-run)
#   2. slime-coding hooks / skills / commands (via slime-coding/install.sh)
#   3. a corridor-ci starter workflow (.github/workflows/corridor.yml,
#      skipped if the project already has one)
#   4. an agentcam availability check (prints the pip command if missing)
#
# Usage: ./install.sh [/path/to/target/project]
# Re-running is safe (idempotent).
set -euo pipefail

TOOLKIT_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${1:-$PWD}"
PROJECT="$(cd "$PROJECT" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required" >&2
  exit 1
fi

echo "Toolkit home : $TOOLKIT_HOME"
echo "Target       : $PROJECT"

# --- 1. unified discipline into CLAUDE.md (managed block) -------------------
python3 - "$TOOLKIT_HOME/templates/DISCIPLINE.md" "$PROJECT/CLAUDE.md" <<'PY'
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
START = "<!-- coding-agent-guardrails:discipline:start -->"
END = "<!-- coding-agent-guardrails:discipline:end -->"
block = f"{START}\n{src.read_text(encoding='utf-8').strip()}\n{END}"
text = dst.read_text(encoding="utf-8") if dst.exists() else ""
if START in text and END in text:
    head, _, rest = text.partition(START)
    _, _, tail = rest.partition(END)
    text = head + block + tail
else:
    if text and not text.endswith("\n"):
        text += "\n"
    text += ("\n" if text else "") + block + "\n"
dst.write_text(text, encoding="utf-8")
print(f"  discipline block -> {dst}")
PY

# --- 2. slime-coding hooks / skills / commands -------------------------------
"$TOOLKIT_HOME/slime-coding/install.sh" "$PROJECT"
echo "  (slime's manual CLAUDE.md step is already covered by the discipline block)"

# --- 3. corridor-ci starter workflow -----------------------------------------
WF="$PROJECT/.github/workflows/corridor.yml"
if [ -f "$WF" ]; then
  echo "  corridor workflow already present - left untouched: $WF"
else
  mkdir -p "$PROJECT/.github/workflows"
  cp "$TOOLKIT_HOME/corridor-ci/examples/workflow.yml" "$WF"
  echo "  corridor workflow -> $WF"
fi

# --- 4. agentcam --------------------------------------------------------------
if command -v agentcam >/dev/null 2>&1; then
  echo "  agentcam found: $(agentcam version)"
else
  echo "  agentcam not found - install it with: pip install agentcam"
fi

echo ""
echo "Done. The loop:"
echo "  agentcam run -- <agent command>            # record what the agent does"
echo "  agentcam handoff                           # five-line handoff draft for the PR body"
echo "  agentcam export latest --files .agentcam/  # commit recorded evidence for corridor-ci"
