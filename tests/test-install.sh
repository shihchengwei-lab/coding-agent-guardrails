#!/usr/bin/env bash
# Toolkit installer test: fresh project + fresh venv, install twice,
# verify wiring, agentcam availability, and idempotency.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Fresh venv so the installer's pip step lands here, not in the tester's
# real environment. A Windows venv ships python.exe but no python3 —
# exactly the resolution case the installer must get right.
python3 -m venv "$TMP/venv"
VENVBIN="$TMP/venv/bin"
[ -d "$TMP/venv/Scripts" ] && VENVBIN="$TMP/venv/Scripts"
export PATH="$VENVBIN:$PATH"

cd "$TMP"
git init -q -b main .
git config user.email test@example.com
git config user.name Test

"$HERE/install.sh" "$TMP" >/dev/null
"$HERE/install.sh" "$TMP" >/dev/null   # second run must stay idempotent

# The same discipline block must land in both agent docs: Claude Code
# reads CLAUDE.md, Codex and friends read AGENTS.md.
for doc in CLAUDE.md AGENTS.md; do
  count=$(grep -c "coding-agent-guardrails:discipline:start" "$doc")
  if [ "$count" != "1" ]; then
    echo "FAIL: $doc discipline block count=$count (expected exactly 1)" >&2
    exit 1
  fi
  grep -q "minimal semantic displacement" "$doc"
  grep -q "agentcam verify" "$doc"   # the block must teach the handoff loop
done

python3 - <<'PY'
import json
hooks = json.load(open(".claude/settings.json"))["hooks"]
assert set(hooks) >= {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"}, hooks
for event, groups in hooks.items():
    assert len(groups) == 1, f"{event} not idempotent: {len(groups)} groups"
PY

test -f .github/workflows/corridor.yml

# agentcam must have been installed into the venv (not just hinted at),
# and it must be this checkout's version — `verify` exists.
"$VENVBIN/agentcam" version >/dev/null
"$VENVBIN/agentcam" verify --help >/dev/null

echo "install.sh toolkit test OK"
