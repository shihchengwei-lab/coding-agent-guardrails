#!/usr/bin/env bash
# Shared installer integration test for the POSIX entrypoint.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

python3 -m venv "$TMP/bootstrap venv"
VENVBIN="$TMP/bootstrap venv/bin"
export PATH="$VENVBIN:$PATH"

PROJECT="$TMP/project with spaces"
mkdir -p "$PROJECT/.claude"
git -C "$PROJECT" init -q -b main
git -C "$PROJECT" config user.email test@example.com
git -C "$PROJECT" config user.name Test
cat > "$PROJECT/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "Stop": [{
      "hooks": [
        {"type": "command", "command": "user-existing-hook"},
        {"type": "command", "command": "python old/patch-cost"}
      ]
    }]
  }
}
JSON

"$HERE/install.sh" "$PROJECT" >/dev/null
"$HERE/install.sh" "$PROJECT" >/dev/null

GIT_DIR="$(git -C "$PROJECT" rev-parse --absolute-git-dir)"
GUARDRAILS="$GIT_DIR/guardrails"
MANIFEST="$GUARDRAILS/install.json"
test -f "$MANIFEST"
readarray -t INSTALL_PATHS < <(python3 - "$MANIFEST" <<'PY'
import json, sys
data = json.load(open(sys.argv[1], encoding="utf-8"))
print(data["runtime"])
print(data["python"])
PY
)
RUNTIME="${INSTALL_PATHS[0]}"
AGENTCAM_PYTHON="${INSTALL_PATHS[1]}"
test -d "$RUNTIME"
test -x "$AGENTCAM_PYTHON"
test -x "$PROJECT/guardrails"
(cd "$TMP" && "$PROJECT/guardrails" doctor >/dev/null)

for doc in CLAUDE.md AGENTS.md; do
  test "$(grep -c 'coding-agent-guardrails:discipline:start' "$PROJECT/$doc")" = 1
  grep -q "smallest sufficient semantic displacement" "$PROJECT/$doc"
done

python3 - "$PROJECT" "$GUARDRAILS" "$HERE" <<'PY'
import json, pathlib, sys
repo, guardrails, toolkit = map(pathlib.Path, sys.argv[1:])
for relative in (".claude/settings.json", ".codex/hooks.json"):
    hooks = json.loads((repo / relative).read_text(encoding="utf-8"))["hooks"]
    commands = [
        hook.get("command", "") + " " + hook.get("commandWindows", "")
        for groups in hooks.values() for group in groups for hook in group.get("hooks", [])
    ]
    joined = "\n".join(commands)
    assert str(guardrails) in joined, (relative, joined)
    assert str(toolkit) not in joined, (relative, joined)
claude = json.loads((repo / ".claude/settings.json").read_text(encoding="utf-8"))
stop = [h for g in claude["hooks"]["Stop"] for h in g["hooks"]]
assert any(h.get("command") == "user-existing-hook" for h in stop), stop
assert not any("old/patch-cost" in h.get("command", "") for h in stop), stop
PY

test -f "$PROJECT/.github/workflows/corridor.yml"
grep -q '^# coding-agent-guardrails:managed corridor-ci-v14.0.0$' "$PROJECT/.github/workflows/corridor.yml"
grep -q 'corridor-ci@corridor-ci-v14.0.0' "$PROJECT/.github/workflows/corridor.yml"
test ! -e "$PROJECT/.slime"
"$AGENTCAM_PYTHON" -m agentcam.cli version | grep -q '^agentcam 0.6.0$'
if find "$PROJECT" -name '*.bak-*' -print -quit | grep -q .; then
  echo "FAIL: successful install left permanent backup files" >&2
  exit 1
fi

# Only marker + official hash is upgradeable. Unmarked legacy and custom
# workflows are preserved with explicit warnings.
cp "$HERE/tests/fixtures/corridor-v11-workflow.yml" "$PROJECT/.github/workflows/corridor.yml"
legacy_out=$("$HERE/install.sh" "$PROJECT")
grep -q 'corridor-ci@corridor-ci-v11' "$PROJECT/.github/workflows/corridor.yml"
case "$legacy_out" in *"custom workflow preserved"*) ;; *) exit 1 ;; esac
printf '# custom corridor workflow\n' > "$PROJECT/.github/workflows/corridor.yml"
custom_out=$("$HERE/install.sh" "$PROJECT")
grep -qx '# custom corridor workflow' "$PROJECT/.github/workflows/corridor.yml"
case "$custom_out" in *"custom workflow preserved"*) ;; *) exit 1 ;; esac

# Dry-run and target validation do not mutate repositories.
DRY="$TMP/dry-run"
mkdir -p "$DRY/src"
git -C "$DRY" init -q -b main
"$HERE/install.sh" "$DRY" --dry-run >/dev/null
test ! -e "$DRY/AGENTS.md"
if "$HERE/install.sh" "$DRY/src" >/dev/null 2>&1; then
  echo "FAIL: subdirectory target unexpectedly succeeded" >&2
  exit 1
fi

# A version-environment failure happens before project mutation.
FAIL_PROJECT="$TMP/preflight-failure"
mkdir -p "$FAIL_PROJECT" "$TMP/fake-bin"
git -C "$FAIL_PROJECT" init -q -b main
REAL_PYTHON=$(command -v python3)
cat > "$TMP/fake-bin/python" <<EOF
#!/usr/bin/env bash
if [ "\${1:-}" = "-m" ] && [ "\${2:-}" = "venv" ]; then exit 77; fi
exec "$REAL_PYTHON" "\$@"
EOF
chmod +x "$TMP/fake-bin/python"
ln -s python "$TMP/fake-bin/python3"
if "$REAL_PYTHON" "$HERE/installer/guardrails_installer.py" install "$FAIL_PROJECT" \
    --source "$HERE" --python "$TMP/fake-bin/python" >/dev/null 2>&1; then
  echo "FAIL: fake venv failure unexpectedly succeeded" >&2
  exit 1
fi
for path in AGENTS.md CLAUDE.md .codex .claude .slime .github guardrails guardrails.cmd; do
  test ! -e "$FAIL_PROJECT/$path"
done

# A later working-tree fault restores every earlier mutation.
ROLLBACK="$TMP/rollback"
mkdir -p "$ROLLBACK"
git -C "$ROLLBACK" init -q -b main
printf 'original instructions\n' > "$ROLLBACK/CLAUDE.md"
printf 'user-owned obstacle\n' > "$ROLLBACK/.claude"
if "$HERE/install.sh" "$ROLLBACK" >/dev/null 2>&1; then
  echo "FAIL: post-mutation obstacle unexpectedly succeeded" >&2
  exit 1
fi
grep -qx 'original instructions' "$ROLLBACK/CLAUDE.md"
grep -qx 'user-owned obstacle' "$ROLLBACK/.claude"
test ! -e "$ROLLBACK/AGENTS.md"
test ! -e "$ROLLBACK/.slime"

# Uninstall dry-run is inert; actual uninstall removes only proven managed
# content and runtime, preserving .slime, trusted config, and user hooks.
mkdir -p "$PROJECT/.slime"
printf 'user archived history\n' > "$PROJECT/.slime/PRUNED.md"
"$PROJECT/guardrails" check set primary -- python -V >/dev/null
CONFIG="$GUARDRAILS/config.json"
"$PROJECT/guardrails" uninstall --dry-run >/dev/null
test -f "$MANIFEST"
ENVIRONMENT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["environment"])' "$MANIFEST")"
printf '@echo user modified launcher\r\n' > "$PROJECT/guardrails.cmd"
"$PROJECT/guardrails" uninstall >/dev/null
test ! -e "$MANIFEST"
test ! -e "$RUNTIME"
test ! -e "$ENVIRONMENT"
test -f "$CONFIG"
grep -qx 'user archived history' "$PROJECT/.slime/PRUNED.md"
grep -q 'user-existing-hook' "$PROJECT/.claude/settings.json"
! grep -q 'guardrails_managed' "$PROJECT/.claude/settings.json"
grep -q 'user modified launcher' "$PROJECT/guardrails.cmd"

echo "install.sh toolkit test OK"
