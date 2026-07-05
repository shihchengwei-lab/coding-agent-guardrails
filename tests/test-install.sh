#!/usr/bin/env bash
# Toolkit installer test: fresh project, install twice, verify wiring
# and idempotency.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

cd "$TMP"
git init -q -b main .
git config user.email test@example.com
git config user.name Test

"$HERE/install.sh" "$TMP" >/dev/null
"$HERE/install.sh" "$TMP" >/dev/null   # second run must stay idempotent

count=$(grep -c "coding-agent-guardrails:discipline:start" CLAUDE.md)
if [ "$count" != "1" ]; then
  echo "FAIL: discipline block count=$count (expected exactly 1)" >&2
  exit 1
fi
grep -q "minimal semantic displacement" CLAUDE.md

python3 - <<'PY'
import json
hooks = json.load(open(".claude/settings.json"))["hooks"]
assert set(hooks) >= {"SessionStart", "UserPromptSubmit", "PreToolUse", "Stop"}, hooks
for event, groups in hooks.items():
    assert len(groups) == 1, f"{event} not idempotent: {len(groups)} groups"
PY

test -f .github/workflows/corridor.yml

echo "install.sh toolkit test OK"
