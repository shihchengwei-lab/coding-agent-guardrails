#!/usr/bin/env bash
# Install the complete toolkit into a target git project.
set -euo pipefail

TOOLKIT_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${1:-$PWD}"
PROJECT="$(cd "$PROJECT" && pwd)"

fail() {
  echo "error: $*" >&2
  exit 1
}

# Resolve one Python >= 3.11 before touching the target. Prefer the active
# venv's `python`; Windows venvs commonly have no python3 shim.
PY=""
for cand in python python3; do
  if command -v "$cand" >/dev/null 2>&1 &&
     "$cand" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$cand"
    break
  fi
done
[ -n "$PY" ] || fail "Python 3.11 or newer is required"
command -v git >/dev/null 2>&1 || fail "git is required"
git -C "$PROJECT" rev-parse --git-dir >/dev/null 2>&1 || fail "target must be a git repository: $PROJECT"

# Preflight every source and template that later mutation depends on.
for source in \
  "$TOOLKIT_HOME/templates/DISCIPLINE.md" \
  "$TOOLKIT_HOME/corridor-ci/examples/workflow.yml" \
  "$TOOLKIT_HOME/slime-coding/install.sh" \
  "$TOOLKIT_HOME/slime-coding/hooks/hooks.template.json" \
  "$TOOLKIT_HOME/slime-coding/templates/.slime/corridor.md" \
  "$TOOLKIT_HOME/slime-coding/templates/.slime/PRUNED.md" \
  "$TOOLKIT_HOME/agentcam/pyproject.toml"; do
  [ -f "$source" ] || fail "required installer source is missing: $source"
done
TOOLKIT_HOME="$TOOLKIT_HOME" "$PY" - <<'PY'
import json, os
from pathlib import Path
root = Path(os.environ["TOOLKIT_HOME"])
json.loads((root / "slime-coding/hooks/hooks.template.json").read_text(encoding="utf-8"))
PY

echo "Toolkit home : $TOOLKIT_HOME"
echo "Target       : $PROJECT"
echo "Python       : $($PY -c 'import sys; print(sys.executable)')"

# Package installation is deliberately before project mutation. It may remain
# installed if a later project write fails; it does not damage the project.
"$PY" -m pip install --quiet --upgrade "$TOOLKIT_HOME/agentcam"

# Journal the finite project areas this installer manages. Any later failure
# restores the exact prior state and removes paths created by this run.
JOURNAL="$(mktemp -d)"
COMMITTED=0
MANAGED=(
  "CLAUDE.md"
  "AGENTS.md"
  ".claude"
  ".slime"
  ".github/workflows/corridor.yml"
)
for relative in "${MANAGED[@]}"; do
  if [ -e "$PROJECT/$relative" ] || [ -L "$PROJECT/$relative" ]; then
    mkdir -p "$JOURNAL/backup/$(dirname "$relative")"
    cp -a "$PROJECT/$relative" "$JOURNAL/backup/$relative"
    printf '%s\n' "$relative" >> "$JOURNAL/existed"
  fi
done

restore_project() {
  status=$?
  if [ "$COMMITTED" -eq 0 ]; then
    for relative in "${MANAGED[@]}"; do
      rm -rf "$PROJECT/$relative"
    done
    if [ -f "$JOURNAL/existed" ]; then
      while IFS= read -r relative; do
        mkdir -p "$PROJECT/$(dirname "$relative")"
        cp -a "$JOURNAL/backup/$relative" "$PROJECT/$relative"
      done < "$JOURNAL/existed"
    fi
    echo "error: installation failed; project files were restored" >&2
  fi
  rm -rf "$JOURNAL"
  exit "$status"
}
trap restore_project EXIT

# Unified discipline in both agent instruction files. os.replace keeps each
# individual file write atomic; the journal supplies multi-file rollback.
for agent_doc in CLAUDE.md AGENTS.md; do
  "$PY" - "$TOOLKIT_HOME/templates/DISCIPLINE.md" "$PROJECT/$agent_doc" <<'PY'
import os, sys, tempfile
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
start = "<!-- coding-agent-guardrails:discipline:start -->"
end = "<!-- coding-agent-guardrails:discipline:end -->"
block = f"{start}\n{src.read_text(encoding='utf-8').strip()}\n{end}"
text = dst.read_text(encoding="utf-8") if dst.exists() else ""
if start in text and end in text:
    head, _, rest = text.partition(start)
    _, _, tail = rest.partition(end)
    text = head + block + tail
else:
    if text and not text.endswith("\n"):
        text += "\n"
    text += ("\n" if text else "") + block + "\n"
dst.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(prefix=dst.name + ".", dir=dst.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    os.replace(temporary, dst)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
print(f"  discipline block -> {dst}")
PY
done

SLIME_PYTHON="$PY" "$TOOLKIT_HOME/slime-coding/install.sh" "$PROJECT"

# Upgrade only a managed template or the byte-equivalent official v11
# starter. Unknown content belongs to the user and is preserved.
WF="$PROJECT/.github/workflows/corridor.yml"
WF_TEMPLATE="$TOOLKIT_HOME/corridor-ci/examples/workflow.yml"
install_workflow() {
  mkdir -p "$(dirname "$WF")"
  temporary="$WF.tmp.$$"
  cp "$WF_TEMPLATE" "$temporary"
  mv -f "$temporary" "$WF"
}
if [ ! -f "$WF" ]; then
  install_workflow
  echo "  corridor workflow -> $WF"
elif grep -q '^# coding-agent-guardrails:managed corridor-ci-v' "$WF"; then
  install_workflow
  echo "  managed corridor workflow updated -> $WF"
else
  workflow_hash=$("$PY" - "$WF" <<'PY'
import hashlib, sys
data = open(sys.argv[1], "rb").read().replace(b"\r\n", b"\n")
print(hashlib.sha256(data).hexdigest())
PY
)
  if [ "$workflow_hash" = "73506c8746a13741be6a70bd1800a3267337d8f8fbeabd9cbf68370b631739d6" ]; then
    install_workflow
    echo "  official corridor-ci-v11 workflow upgraded -> $WF"
  else
    echo "  warning: custom workflow is not overwritten; verify it no longer pins an older Corridor version: $WF"
  fi
fi

# Claude Code session hooks for agentcam. Keep unrelated user hook groups.
if command -v agentcam >/dev/null 2>&1; then
  AGENTCAM_CMD="agentcam"
else
  AGENTCAM_CMD="\"$($PY -c 'import sys; print(sys.executable)')\" -m agentcam.cli"
fi
SETTINGS="$PROJECT/.claude/settings.json" AGENTCAM_CMD="$AGENTCAM_CMD" "$PY" - <<'PY'
import json, os, tempfile
from pathlib import Path

path = Path(os.environ["SETTINGS"])
cmd = os.environ["AGENTCAM_CMD"]
settings = {}
if path.exists():
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        settings = {}
hooks = settings.setdefault("hooks", {})
def ours(group):
    return any("hook-session-" in hook.get("command", "") for hook in group.get("hooks", []))
for event, sub in (("SessionStart", "hook-session-start"), ("SessionEnd", "hook-session-end")):
    kept = [group for group in hooks.get(event, []) if not ours(group)]
    kept.append({"matcher": "", "hooks": [{"type": "command", "command": f"{cmd} {sub}"}]})
    hooks[event] = kept
path.parent.mkdir(parents=True, exist_ok=True)
fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(settings, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)
finally:
    if os.path.exists(temporary):
        os.unlink(temporary)
print("  agentcam session hooks -> " + str(path))
PY

COMMITTED=1
echo ""
echo "Done. The loop:"
echo "  agentcam run -- <agent command>"
echo "  agentcam verify -- <test command>"
echo "  agentcam handoff"
echo "  agentcam export latest --files .agentcam/"
