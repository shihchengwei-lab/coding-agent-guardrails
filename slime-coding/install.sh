#!/usr/bin/env bash
# Slime Coding — clone-and-install.
#
# Wires the two hook scripts (prune-inject, patch-cost) into a project's
# .claude/settings.json across four events (SessionStart, UserPromptSubmit,
# PreToolUse, Stop), with an absolute, quoted path to this clone, and links the
# skill + slash commands into the project's .claude/ so Claude Code discovers
# them. No plugin, no marketplace — just clone this repo anywhere and run:
#
#   ./install.sh [/path/to/target/project] [--with-cg /path/to/coding-guidelines]
#
# --with-cg additionally installs the owner's user-level coding-guidelines
# hooks (rules + inventory_gate + review) into ~/.claude/scripts/ and merges
# them into ~/.claude/settings.json. Skip the flag and that step is not run.
#
# Re-running is safe (idempotent): existing Slime Coding hooks are replaced,
# not duplicated. A timestamped backup of settings.json is kept.
set -euo pipefail

SLIME_HOME="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- arg parse: positional [target] + optional --with-cg <path> ---------------
CG_HOME=""
ARGS=()
while [ $# -gt 0 ]; do
  case "$1" in
    --with-cg=*)  CG_HOME="${1#--with-cg=}"; shift ;;
    --with-cg)    CG_HOME="${2:-}"; shift 2 ;;
    -*)           echo "error: unknown flag: $1" >&2; exit 2 ;;
    *)            ARGS+=("$1"); shift ;;
  esac
done
PROJECT="${ARGS[0]:-$PWD}"
PROJECT="$(cd "$PROJECT" && pwd)"

# --- validate --with-cg path looks like a coding-guidelines repo --------------
if [ -n "$CG_HOME" ]; then
  CG_HOME="$(cd "$CG_HOME" 2>/dev/null && pwd)" || {
    echo "error: --with-cg path not found" >&2; exit 1; }
  for f in rules.sh inventory_gate.sh review.sh; do
    [ -f "$CG_HOME/$f" ] || {
      echo "error: $CG_HOME does not look like coding-guidelines (missing $f)" >&2
      exit 1; }
  done
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required (the hooks are python3 stdlib scripts)." >&2
  exit 1
fi

echo "Slime Coding home : $SLIME_HOME"
echo "Target project    : $PROJECT"
[ -n "$CG_HOME" ] && echo "coding-guidelines : $CG_HOME"

mkdir -p "$PROJECT/.claude/commands" "$PROJECT/.claude/skills"
SETTINGS="$PROJECT/.claude/settings.json"

# 1. Merge hooks into settings.json (the two scripts run via `python3`, so the
#    install does not depend on the clone keeping its executable bit).
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

# 4. Optional: also wire the owner's user-level coding-guidelines hooks.
install_cg() {
  local user_dir="$HOME/.claude"
  local scripts="$user_dir/scripts"
  mkdir -p "$scripts"
  local s
  for s in rules inventory_gate review; do
    cp "$CG_HOME/$s.sh" "$scripts/$s.sh"
    chmod +x "$scripts/$s.sh"
  done
  echo "  copied cg scripts -> $scripts/*.sh"

  CG_SETTINGS="$user_dir/settings.json" \
  CG_SCRIPTS="$scripts" \
  python3 - <<'PY'
import json, os, re, shutil, time

settings_path = os.environ["CG_SETTINGS"]
scripts       = os.environ["CG_SCRIPTS"]

def cmd(stem):
    return f'{scripts}/{stem}.sh'

template = {
    "UserPromptSubmit": [
        {"hooks": [{"type": "command", "command": cmd("rules"),          "timeout": 5}]},
        {"hooks": [{"type": "command", "command": cmd("inventory_gate"), "timeout": 5}]},
    ],
    "Stop": [
        {"hooks": [{"type": "command", "command": cmd("review"),         "timeout": 5}]},
    ],
}

settings = {}
if os.path.exists(settings_path):
    try:
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
    except (OSError, ValueError):
        settings = {}
    shutil.copy2(settings_path, settings_path + ".bak-" + time.strftime("%Y%m%d%H%M%S"))

hooks = settings.setdefault("hooks", {})
CG = re.compile(r"\.claude/scripts/(rules|inventory_gate|review)(\.en)?\.(sh|py)")

def is_ours(group):
    return any(CG.search(h.get("command", "")) for h in group.get("hooks", []))

for event, groups in template.items():
    existing = [g for g in hooks.get(event, []) if not is_ours(g)]
    hooks[event] = existing + groups

with open(settings_path, "w", encoding="utf-8") as f:
    json.dump(settings, f, indent=2)
    f.write("\n")
print("  wired cg hooks -> " + settings_path)
PY
}

if [ -n "$CG_HOME" ]; then
  install_cg
fi

cat <<EOF

Done. Remaining manual step (L0 discipline is a request, so it is not forced):
  paste the block in
    $SLIME_HOME/templates/CLAUDE.slime.md
  into $PROJECT/CLAUDE.md

Optional config (env): SLIME_TEST_CMD, SLIME_PRUNE_RECENT, SLIME_TEST_TIMEOUT,
SLIME_PUBSPEC. See $SLIME_HOME/README.md.
EOF
