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
  grep -q "smallest sufficient semantic displacement" "$doc"
  grep -q "agentcam verify" "$doc"   # the block must teach the handoff loop
done

python3 - <<'PY'
import json
hooks = json.load(open(".claude/settings.json"))["hooks"]
# slime and agentcam share SessionStart; agentcam alone owns SessionEnd.
expected = {"SessionStart": 2, "SessionEnd": 1,
            "UserPromptSubmit": 1, "PreToolUse": 1, "Stop": 1}
assert set(hooks) == set(expected), hooks
for event, n in expected.items():
    assert len(hooks[event]) == n, (
        f"{event} not idempotent: {len(hooks[event])} groups (expected {n})")
cmds = [h["command"] for gs in hooks.values() for g in gs for h in g.get("hooks", [])]
assert any("hook-session-start" in c for c in cmds), cmds
assert any("hook-session-end" in c for c in cmds), cmds
PY

test -f .github/workflows/corridor.yml
grep -q '^## Rigor$' .slime/corridor.md
grep -A1 '^## Rigor$' .slime/corridor.md | grep -q '^normal$'

# agentcam must have been installed into the venv (not just hinted at),
# and it must be this checkout's version — `verify` exists.
"$VENVBIN/agentcam" version >/dev/null
"$VENVBIN/agentcam" verify --help >/dev/null

echo "install.sh toolkit test OK"
