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
            "UserPromptSubmit": 1, "PreToolUse": 1,
            "PostToolUse": 1, "Stop": 1}
assert set(hooks) == set(expected), hooks
for event, n in expected.items():
    assert len(hooks[event]) == n, (
        f"{event} not idempotent: {len(hooks[event])} groups (expected {n})")
cmds = [h["command"] for gs in hooks.values() for g in gs for h in g.get("hooks", [])]
assert any("hook-session-start" in c for c in cmds), cmds
assert any("hook-session-end" in c for c in cmds), cmds
PY

test -f .github/workflows/corridor.yml
grep -q '^# coding-agent-guardrails:managed corridor-ci-v13.0.0$' .github/workflows/corridor.yml
grep -q 'corridor-ci@corridor-ci-v13.0.0' .github/workflows/corridor.yml
grep -q '^## Rigor$' .slime/corridor.md
grep -A1 '^## Rigor$' .slime/corridor.md | grep -q '^normal$'

# agentcam must have been installed into the venv (not just hinted at),
# and it must be this checkout's version — `verify` exists.
"$VENVBIN/agentcam" version >/dev/null
"$VENVBIN/agentcam" verify --help >/dev/null

# The exact official v11 starter is safely upgraded; a custom workflow is not.
cp "$HERE/tests/fixtures/corridor-v11-workflow.yml" .github/workflows/corridor.yml
"$HERE/install.sh" "$TMP" >/dev/null
grep -q 'corridor-ci@corridor-ci-v13.0.0' .github/workflows/corridor.yml
printf '# custom corridor workflow\n' > .github/workflows/corridor.yml
custom_out=$("$HERE/install.sh" "$TMP")
grep -q '^# custom corridor workflow$' .github/workflows/corridor.yml
case "$custom_out" in
  *"custom workflow"*"not overwritten"*) ;;
  *) echo "FAIL: custom workflow did not produce a preservation warning" >&2; exit 1 ;;
esac

# A pip preflight failure must happen before the target project is mutated.
FAIL_PROJECT="$TMP/preflight-failure"
mkdir -p "$FAIL_PROJECT" "$TMP/fake-bin"
git -C "$FAIL_PROJECT" init -q -b main
cat > "$TMP/fake-bin/python" <<EOF
#!/usr/bin/env bash
if [ "\${1:-}" = "-m" ] && [ "\${2:-}" = "pip" ]; then exit 77; fi
exec "$(command -v python3)" "\$@"
EOF
chmod +x "$TMP/fake-bin/python"
ln -s python "$TMP/fake-bin/python3"
if PATH="$TMP/fake-bin:$PATH" "$HERE/install.sh" "$FAIL_PROJECT" >/dev/null 2>&1; then
  echo "FAIL: fake pip failure unexpectedly succeeded" >&2
  exit 1
fi
for path in CLAUDE.md AGENTS.md .claude .slime .github; do
  if [ -e "$FAIL_PROJECT/$path" ]; then
    echo "FAIL: preflight failure left $path behind" >&2
    exit 1
  fi
done

# A failure after mutation starts restores pre-existing managed content.
ROLLBACK_PROJECT="$TMP/rollback-project"
mkdir -p "$ROLLBACK_PROJECT"
git -C "$ROLLBACK_PROJECT" init -q -b main
printf 'original instructions\n' > "$ROLLBACK_PROJECT/CLAUDE.md"
printf 'user-owned obstacle\n' > "$ROLLBACK_PROJECT/.claude"
if "$HERE/install.sh" "$ROLLBACK_PROJECT" >/dev/null 2>&1; then
  echo "FAIL: post-mutation obstacle unexpectedly succeeded" >&2
  exit 1
fi
grep -qx 'original instructions' "$ROLLBACK_PROJECT/CLAUDE.md"
grep -qx 'user-owned obstacle' "$ROLLBACK_PROJECT/.claude"
test ! -e "$ROLLBACK_PROJECT/AGENTS.md"
test ! -e "$ROLLBACK_PROJECT/.slime"

echo "install.sh toolkit test OK"
