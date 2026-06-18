#!/usr/bin/env bash
# Tests for install.sh --with-cg flag (pairing with coding-guidelines).
# Stubs $HOME and a fake cg dir so the real user-level settings.json is never
# touched. Same style as tests/test.sh: temp dirs, JSON / stdout assertions,
# no framework. Run: tests/test-cg-install.sh   (needs python3 + git + bash).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INSTALL="$ROOT/install.sh"

pass=0
fail=0
ok()  { printf '  ok   %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf 'FAIL   %s\n         got: %s\n' "$1" "$2"; fail=$((fail + 1)); }

TMP_DIRS=()
mktmp() { local d; d="$(mktemp -d)"; TMP_DIRS+=("$d"); printf '%s' "$d"; }
cleanup() { for d in "${TMP_DIRS[@]:-}"; do rm -rf "$d"; done; }
trap cleanup EXIT

# Stub coding-guidelines dir: just the three .sh scripts install.sh checks for.
CG="$(mktmp)"
for s in rules inventory_gate review; do
  printf '#!/usr/bin/env bash\nexit 0\n' > "$CG/$s.sh"
  chmod +x "$CG/$s.sh"
done

PROJ="$(mktmp)"
FAKE_HOME="$(mktmp)"

# --- run install.sh twice with HOME redirected --------------------------------
HOME="$FAKE_HOME" "$INSTALL" "$PROJ" --with-cg "$CG" >/dev/null 2>&1
HOME="$FAKE_HOME" "$INSTALL" "$PROJ" --with-cg "$CG" >/dev/null 2>&1

# 1. user-level settings.json exists
[ -f "$FAKE_HOME/.claude/settings.json" ] \
  && ok "1  user-level settings.json created" \
  || bad "1  user-level settings.json created" "missing"

# 2. three scripts copied into ~/.claude/scripts/
miss=""
for s in rules inventory_gate review; do
  [ -f "$FAKE_HOME/.claude/scripts/$s.sh" ] || miss="$miss $s.sh"
done
[ -z "$miss" ] \
  && ok "2  cg scripts copied to ~/.claude/scripts/" \
  || bad "2  cg scripts copied" "missing:$miss"

# 3. idempotent: each event has exactly the expected number of "ours" groups
python3 - "$FAKE_HOME/.claude/settings.json" <<'PY'
import json, sys, re
hooks = json.load(open(sys.argv[1]))["hooks"]
CG = re.compile(r"\.claude/scripts/(rules|inventory_gate|review)(\.en)?\.(sh|py)")
expected = {"UserPromptSubmit": 2, "Stop": 1}
for evt, want in expected.items():
    ours = [g for g in hooks.get(evt, [])
            if any(CG.search(h.get("command", "")) for h in g.get("hooks", []))]
    assert len(ours) == want, f"{evt}: ours={len(ours)} (want {want})"
PY
[ $? -eq 0 ] \
  && ok "3  idempotent across 2 runs (no duplicate cg groups)" \
  || bad "3  idempotent across 2 runs" "duplicate or missing"

# 4. slime project-level install still happened
[ -f "$PROJ/.claude/settings.json" ] \
  && ok "4  slime project install still produces settings.json" \
  || bad "4  slime project install untouched" "missing"

# 5. unrelated user-level hook survives --with-cg merge
THIRD_HOME="$(mktmp)"
mkdir -p "$THIRD_HOME/.claude"
cat > "$THIRD_HOME/.claude/settings.json" <<'JSON'
{
  "hooks": {
    "UserPromptSubmit": [
      {"hooks": [{"type": "command", "command": "other-hook"}]}
    ]
  }
}
JSON
HOME="$THIRD_HOME" "$INSTALL" "$(mktmp)" --with-cg "$CG" >/dev/null 2>&1
grep -q '"other-hook"' "$THIRD_HOME/.claude/settings.json" \
  && ok "5  unrelated third-party hook preserved" \
  || bad "5  unrelated third-party hook preserved" "lost"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
