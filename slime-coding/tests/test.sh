#!/usr/bin/env bash
# Minimal behavioural tests for the Slime Coding hooks. No framework — just
# temp git repos, JSON on stdin, and assertions on stdout / exit code.
# Run: tests/test.sh   (needs python3 and git)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH="$ROOT/bin/patch-cost"
PRUNE="$ROOT/bin/prune-inject"

pass=0
fail=0
ok()  { printf '  ok   %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf 'FAIL   %s\n         got: %s\n' "$1" "$2"; fail=$((fail + 1)); }

TMP_DIRS=()
mkrepo() {
  local d
  d="$(mktemp -d)"
  TMP_DIRS+=("$d")
  git -C "$d" init -q
  git -C "$d" config user.email t@t.t
  git -C "$d" config user.name t
  git -C "$d" config commit.gpgsign false
  printf '%s' "$d"
}
cleanup() { for d in "${TMP_DIRS[@]:-}"; do rm -rf "$d"; done; }
trap cleanup EXIT

pre()    { printf '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"%s"},"cwd":"%s"}' "$2" "$1"; }
prompt() { printf '{"hook_event_name":"UserPromptSubmit","cwd":"%s"}' "$1"; }
stop()   { printf '{"hook_event_name":"Stop","cwd":"%s"}' "$1"; }

# --- PreToolUse corridor gate ----------------------------------------------
D="$(mkrepo)"

out=$(pre "$D" "$D/lib/x.dart" | python3 "$PATCH")
case "$out" in
  *'"deny"'*) ok "1  missing corridor + edit code -> deny" ;;
  *) bad "1  missing corridor + edit code -> deny" "$out" ;;
esac

out=$(pre "$D" "$D/.slime/corridor.md" | python3 "$PATCH")
[ -z "$out" ] && ok "2  write .slime/corridor.md -> allow" || bad "2  write .slime/corridor.md -> allow" "$out"

mkdir -p "$D/.slime"
cp "$ROOT/templates/.slime/corridor.md" "$D/.slime/corridor.md"
out=$(pre "$D" "$D/lib/x.dart" | python3 "$PATCH")
case "$out" in
  *'"deny"'*) ok "3  template corridor + edit code -> deny" ;;
  *) bad "3  template corridor + edit code -> deny" "$out" ;;
esac

printf '# Corridor: real\n## Paths\n- lib/**\n' > "$D/.slime/corridor.md"
out=$(pre "$D" "$D/lib/x.dart" | python3 "$PATCH")
[ -z "$out" ] && ok "4  valid corridor + edit allowed file -> allow" || bad "4  valid corridor + edit allowed file -> allow" "$out"

# --- prune-inject env handling ---------------------------------------------
printf '# Pruned\n## [2026-01-01] corridor:other\n**Pruned:** y\n' > "$D/.slime/PRUNED.md"

prompt "$D" | SLIME_PRUNE_RECENT=abc python3 "$PRUNE" >/dev/null 2>&1
[ $? -eq 0 ] && ok "5  SLIME_PRUNE_RECENT=abc -> no crash (exit 0)" || bad "5  SLIME_PRUNE_RECENT=abc -> no crash" "exit $?"

out=$(prompt "$D" | SLIME_PRUNE_RECENT=0 python3 "$PRUNE")
[ -z "$out" ] && ok "6  RECENT=0 + non-matching corridor -> no injection" || bad "6  RECENT=0 -> no injection" "$out"

out=$(prompt "$D" | SLIME_PRUNE_RECENT=5 python3 "$PRUNE")
case "$out" in
  *additionalContext*) ok "6b RECENT=5 -> injects recent record" ;;
  *) bad "6b RECENT=5 -> injects recent record" "$out" ;;
esac

# --- Stop gates -------------------------------------------------------------
git -C "$D" add -A && git -C "$D" commit -qm init   # PRUNED.md now clean vs HEAD

out=$(stop "$D" | SLIME_TEST_CMD='exit 1' python3 "$PATCH")
case "$out" in
  *'"block"'*) ok "7  failing check + clean PRUNED.md -> block" ;;
  *) bad "7  failing check + clean PRUNED.md -> block" "$out" ;;
esac

# bonus: new-dependency gate
E="$(mkrepo)"
printf 'name: d\ndependencies:\n  flutter:\n    sdk: flutter\n' > "$E/pubspec.yaml"
mkdir -p "$E/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$E/.slime/corridor.md"
git -C "$E" add -A && git -C "$E" commit -qm init
printf 'name: d\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^1\n' > "$E/pubspec.yaml"
out=$(stop "$E" | python3 "$PATCH")
case "$out" in
  *'"block"'*http*) ok "8  added dependency -> block (names it)" ;;
  *) bad "8  added dependency -> block (names it)" "$out" ;;
esac

# bonus: clean stop -> systemMessage report, never block
git -C "$E" checkout -q pubspec.yaml
out=$(stop "$E" | python3 "$PATCH")
case "$out" in
  *systemMessage*) ok "9  clean stop -> systemMessage report (no block)" ;;
  *) bad "9  clean stop -> systemMessage report" "$out" ;;
esac

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
