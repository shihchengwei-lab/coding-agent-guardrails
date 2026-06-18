#!/usr/bin/env bash
# Slime Coding — clone-and-install.
#
# Wires the three hooks into a project's .claude/settings.json (with an
# absolute, quoted path to this clone), and links the skill + slash commands
# into the project's .claude/ so Claude Code discovers them. No plugin, no
# marketplace — just clone this repo anywhere and run:
#
#   ./install.sh [/path/to/target/project]   # default: current directory
#
# Re-running is safe (idempotent): existing Slime Coding hooks are replaced,
# not duplicated. A timestamped backup of settings.json is kept.
set -euo pipefail

SLIME_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT="${1:-$PWD}"
PROJECT="$(cd "$PROJECT" && pwd)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required (the hooks are python3 stdlib scripts)." >&2
  exit 1
fi

echo "Slime Coding home : $SLIME_HOME"
echo "Target project    : $PROJECT"

mkdir -p "$PROJECT/.claude/commands" "$PROJECT/.claude/skills"
SETTINGS="$PROJECT/.claude/settings.json"

# 1. Merge hooks into settings.json (absolute path baked into the template).
SLIME_HOME="$SLIME_HOME" SETTINGS="$SETTINGS" TEMPLATE="$SLIME_HOME/hooks/hooks.template.json" \
python3 - <<'PY'
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

cat <<EOF

Done. Remaining manual step (L0 discipline is a request, so it is not forced):
  paste the block in
    $SLIME_HOME/templates/CLAUDE.slime.md
  into $PROJECT/CLAUDE.md

Optional config (env): SLIME_TEST_CMD, SLIME_PRUNE_RECENT, SLIME_TEST_TIMEOUT,
SLIME_PUBSPEC. See $SLIME_HOME/README.md.
EOF
