#!/usr/bin/env bash
# Materialize a fixture as a standalone git repo for one experiment run, so its
# baseline commit and diffs are isolated from the slime-coding repo.
#
#   experiments/new-run.sh <fixture-name> <dest-dir>
#
# Then install the condition into <dest-dir> and run the agent there.
set -eu
fixture="${1:?usage: new-run.sh <fixture> <dest>}"
dest="${2:?usage: new-run.sh <fixture> <dest>}"
src="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/fixtures/$fixture"
[ -d "$src" ] || { echo "no such fixture: $fixture" >&2; exit 1; }

mkdir -p "$dest"
cp -r "$src/." "$dest/"
rm -rf "$dest/.slime" "$dest/.claude" "$dest/notes.json"  # start from clean baseline
# In a run repo, .slime/ must be tracked (so corridor changes show up), while
# .claude/ install artifacts and run files stay ignored (so they don't inflate
# new_files). This differs from the in-repo fixture .gitignore.
cat > "$dest/.gitignore" <<'EOF'
notes.json
__pycache__/
.pytest_cache/
.claude/
EOF
cd "$dest"
git init -q
git add -A
git -c commit.gpgsign=false -c user.email=exp@slime -c user.name=exp \
    commit -qm "baseline: $fixture"
cat <<EOF
run repo ready: $dest (baseline committed)
next:
  1. install the condition into it (e.g. C):  ./install.sh "$dest"
  2. write the real .slime/corridor.md (/slime-corridor), then commit it as the
     task baseline:  git -C "$dest" add -A && git -C "$dest" commit -m corridor
  3. run the implementation agent in "$dest", then the fixture tests
  4. measure (before committing the agent's work):
       python3 experiments/metrics.py --repo "$dest" --task <T> --condition <c> --run <n>
EOF
