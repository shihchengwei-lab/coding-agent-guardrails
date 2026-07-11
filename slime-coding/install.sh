#!/usr/bin/env bash
# Slime Coding — clone-and-install.
#
# Wires the Claude hook scripts (prune-inject, patch-cost) into a project's
# .claude/settings.json, installs the Git commit-message evidence hook, and
# links the skill + slash commands into the project's .claude/ so Claude Code
# discovers them. No plugin, no marketplace — just clone this repo anywhere and
# run:
#
#   ./install.sh [/path/to/target/project]
#
# Re-running is safe (idempotent): existing Slime Coding hooks are replaced,
# not duplicated, and a timestamped backup of settings.json is kept.
set -euo pipefail

SLIME_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- arg parse: positional [target] -------------------------------------------
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    -*)           echo "error: unknown flag: $1" >&2; exit 2 ;;
    *)            ARGS+=("$1"); shift ;;
  esac
done
PROJECT="${ARGS[0]:-$PWD}"
PROJECT="$(cd "$PROJECT" && pwd)"

PY="${SLIME_PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: Python 3.11 or newer is required (the hooks are stdlib scripts)." >&2
  exit 1
fi
"$PY" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null || {
  echo "error: Python 3.11 or newer is required." >&2
  exit 1
}
command -v git >/dev/null 2>&1 || { echo "error: git is required" >&2; exit 1; }
git -C "$PROJECT" rev-parse --git-dir >/dev/null 2>&1 || {
  echo "error: target must be a git repository: $PROJECT" >&2
  exit 1
}
for source in "$SLIME_HOME/hooks/hooks.template.json" \
              "$SLIME_HOME/templates/.slime/corridor.md" \
              "$SLIME_HOME/templates/.slime/PRUNED.md" \
              "$SLIME_HOME/skills/slime-navigate/SKILL.md"; do
  [ -f "$source" ] || { echo "error: required installer source is missing: $source" >&2; exit 1; }
done
TEMPLATE="$SLIME_HOME/hooks/hooks.template.json" "$PY" - <<'PY'
import json, os
json.load(open(os.environ["TEMPLATE"], encoding="utf-8"))
PY

echo "Slime Coding home : $SLIME_HOME"
echo "Target project    : $PROJECT"

JOURNAL="$(mktemp -d)"
COMMITTED=0
MANAGED=(".claude" ".slime")
for relative in "${MANAGED[@]}"; do
  if [ -e "$PROJECT/$relative" ] || [ -L "$PROJECT/$relative" ]; then
    mkdir -p "$JOURNAL/backup"
    cp -a "$PROJECT/$relative" "$JOURNAL/backup/$relative"
    printf '%s\n' "$relative" >> "$JOURNAL/existed"
  fi
done
restore_project() {
  status=$?
  if [ "$COMMITTED" -eq 0 ]; then
    for relative in "${MANAGED[@]}"; do rm -rf "$PROJECT/$relative"; done
    if [ -f "$JOURNAL/existed" ]; then
      while IFS= read -r relative; do
        cp -a "$JOURNAL/backup/$relative" "$PROJECT/$relative"
      done < "$JOURNAL/existed"
    fi
    echo "error: Slime installation failed; project files were restored" >&2
  fi
  rm -rf "$JOURNAL"
  exit "$status"
}
trap restore_project EXIT

mkdir -p "$PROJECT/.claude/commands" "$PROJECT/.claude/skills"
SETTINGS="$PROJECT/.claude/settings.json"

# 1. Merge hooks into settings.json (the two scripts run via `python3`, so the
#    install does not depend on the clone keeping its executable bit).
SLIME_HOME="$SLIME_HOME" SETTINGS="$SETTINGS" TEMPLATE="$SLIME_HOME/hooks/hooks.template.json" \
"$PY" - <<'PY'
import json, os, re, shutil, time

home = os.environ["SLIME_HOME"]
settings_path = os.environ["SETTINGS"]
template_path = os.environ["TEMPLATE"]

with open(template_path, encoding="utf-8") as f:
    template = json.load(f)
# Bake the absolute clone path in place of the placeholder.
def fill(obj):
    if isinstance(obj, dict):
        return {k: fill(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [fill(v) for v in obj]
    if isinstance(obj, str):
        return obj.replace("__SLIME_HOME__", home)
    return obj
template = fill(template)

settings = {}
if os.path.exists(settings_path):
    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except (OSError, ValueError):
        settings = {}
    shutil.copy2(settings_path, settings_path + ".bak-" + time.strftime("%Y%m%d%H%M%S"))

hooks = settings.setdefault("hooks", {})
SLIME = re.compile(r"/bin/(prune-inject|patch-cost)")

def is_ours(group):
    return any(SLIME.search(h.get("command", "")) for h in group.get("hooks", []))

for event, groups in template["hooks"].items():
    existing = [g for g in hooks.get(event, []) if not is_ours(g)]
    hooks[event] = existing + groups

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print("  wired hooks -> " + settings_path)
PY

# 2. Link the skill and the slash commands into the project's .claude/.
ln_force() {  # ln_force <src> <dst>
  rm -rf "$2"
  ln -s "$1" "$2"
  echo "  linked $2 -> $1"
}
ln_force "$SLIME_HOME/skills/slime-navigate" "$PROJECT/.claude/skills/slime-navigate"
for cmd in "$SLIME_HOME"/commands/*.md; do
  ln_force "$cmd" "$PROJECT/.claude/commands/$(basename "$cmd")"
done

# 3. Seed the .slime/ artifacts if the project has none yet.
if [ ! -e "$PROJECT/.slime/corridor.md" ]; then
  mkdir -p "$PROJECT/.slime"
  cp "$SLIME_HOME/templates/.slime/corridor.md" "$PROJECT/.slime/corridor.md"
  cp "$SLIME_HOME/templates/.slime/PRUNED.md" "$PROJECT/.slime/PRUNED.md"
  echo "  seeded $PROJECT/.slime/ (replace the template before editing code)"
else
  echo "  .slime/ already present — left untouched"
fi

COMMITTED=1

cat <<EOF

Done. The L0 discipline block comes from the toolkit's root installer
(templates/DISCIPLINE.md -> CLAUDE.md + AGENTS.md).

Trusted checks: <git-dir>/guardrails/config.json. SLIME_TEST_TIMEOUT may lower
the timeout ceiling. SLIME_TEST_CMD and SLIME_TYPECHECK_CMD are not executed.
See $SLIME_HOME/README.md.
EOF
