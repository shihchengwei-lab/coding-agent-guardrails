#!/usr/bin/env bash
# Coding Agent Guardrails — one-command install.
#
# Installs the whole toolkit into a target project:
#   1. the unified discipline block into the project's CLAUDE.md and
#      AGENTS.md (managed block, replaced in place on re-run; Claude Code
#      reads CLAUDE.md, Codex and other agents read AGENTS.md)
#   2. slime-coding hooks / skills / commands (via slime-coding/install.sh)
#   3. a corridor-ci starter workflow (.github/workflows/corridor.yml,
#      skipped if the project already has one)
#   4. agentcam, pip-installed from this checkout (so `verify` and the
#      rest of the recorded-evidence loop match the docs, even if the
#      PyPI release lags behind)
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

# --- 1. unified discipline into CLAUDE.md + AGENTS.md (managed block) --------
for agent_doc in CLAUDE.md AGENTS.md; do
python3 - "$TOOLKIT_HOME/templates/DISCIPLINE.md" "$PROJECT/$agent_doc" <<'PY'
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
done

# --- 2. slime-coding hooks / skills / commands -------------------------------
"$TOOLKIT_HOME/slime-coding/install.sh" "$PROJECT"

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
# Try `python` before `python3`: a Windows venv ships only python.exe, and
# resolving python3 there would escape the venv and install globally. The
# version probe also skips stale interpreters (python2, Store stubs).
PY=""
for cand in python python3; do
  if command -v "$cand" >/dev/null 2>&1 &&
     "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$cand"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "error: agentcam needs Python >= 3.11 (no such python/python3 found)" >&2
  exit 1
fi
echo "  installing agentcam into: $("$PY" -c 'import sys; print(sys.executable)')"
"$PY" -m pip install --quiet --upgrade "$TOOLKIT_HOME/agentcam"
if command -v agentcam >/dev/null 2>&1; then
  echo "  agentcam ready: $(agentcam version)"
else
  echo "  agentcam installed, but not on PATH - use: $PY -m agentcam.cli <command>"
fi

echo ""
echo "Done. The loop:"
echo "  agentcam run -- <agent command>            # record what the agent does"
echo "  agentcam verify -- <test command>          # run the check under agentcam, record the exit code"
echo "  agentcam handoff                           # five-line handoff draft for the PR body"
echo "  agentcam export latest --files .agentcam/  # commit recorded evidence for corridor-ci"
