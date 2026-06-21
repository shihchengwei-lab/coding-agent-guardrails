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

# The hooks run under whatever `python3` resolves to. On Windows that is often
# native Python (e.g. C:\PythonXX\python.exe), which cannot use a POSIX
# /tmp/... path as a subprocess cwd — git then reports "not a repo" and every
# gate degrades to a silent exit 0, failing these assertions. cygpath -m gives a
# forward-slash Windows path (C:/Users/...) that native Python accepts and that
# needs no JSON escaping; on Linux/macOS there is no cygpath, so we pass through.
hostpath() { cygpath -m "$1" 2>/dev/null || printf '%s' "$1"; }

pre()    { printf '{"hook_event_name":"PreToolUse","tool_name":"Write","tool_input":{"file_path":"%s"},"cwd":"%s"}' "$(hostpath "$2")" "$(hostpath "$1")"; }
prompt() { printf '{"hook_event_name":"UserPromptSubmit","cwd":"%s"}' "$(hostpath "$1")"; }
stop()   { printf '{"hook_event_name":"Stop","cwd":"%s"}' "$(hostpath "$1")"; }

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

# === Phase A edge cases (validation plan §13) ===============================

# A1: corridor.md without a ## Paths list -> deny
F="$(mkrepo)"
mkdir -p "$F/.slime"
printf '# Corridor: real\n## Scope\njust prose, no paths\n' > "$F/.slime/corridor.md"
out=$(pre "$F" "$F/lib/x.dart" | python3 "$PATCH")
case "$out" in
  *'"deny"'*) ok "10 corridor without ## Paths -> deny" ;;
  *) bad "10 corridor without ## Paths -> deny" "$out" ;;
esac

# A2: corridor.md still listing a template example glob -> deny
printf '# Corridor: real-task\n## Paths\n- lib/feature/example/**\n' > "$F/.slime/corridor.md"
out=$(pre "$F" "$F/lib/x.dart" | python3 "$PATCH")
case "$out" in
  *'"deny"'*) ok "11 template example glob -> deny" ;;
  *) bad "11 template example glob -> deny" "$out" ;;
esac

# A3: valid corridor + edit a file OUTSIDE the corridor ->
#     PreToolUse allows (gate only checks corridor validity), and the Stop
#     cost report lists it as out-of-corridor.
G="$(mkrepo)"
mkdir -p "$G/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$G/.slime/corridor.md"
git -C "$G" add -A && git -C "$G" commit -qm init
out=$(pre "$G" "$G/other/y.py" | python3 "$PATCH")
[ -z "$out" ] && ok "12 out-of-corridor edit -> PreToolUse allow" || bad "12 out-of-corridor edit -> PreToolUse allow" "$out"
mkdir -p "$G/other"; printf 'x\n' > "$G/other/y.py"
out=$(stop "$G" | python3 "$PATCH")
case "$out" in
  *"out-of-corridor files: 1"*) ok "13 out-of-corridor file shown in Stop report" ;;
  *) bad "13 out-of-corridor file shown in Stop report" "$out" ;;
esac

# A4: missing pubspec.yaml -> dependency gate degrades (no block)
H="$(mkrepo)"
mkdir -p "$H/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$H/.slime/corridor.md"
git -C "$H" add -A && git -C "$H" commit -qm init
out=$(stop "$H" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "14 missing pubspec -> no dependency block" "$out" ;;
  *systemMessage*) ok "14 missing pubspec -> dependency gate degrades" ;;
  *) bad "14 missing pubspec -> dependency gate degrades" "$out" ;;
esac

# A5: SLIME_TEST_CMD timing out -> degrades, does not crash or block
out=$(stop "$H" | SLIME_TEST_CMD='sleep 5' SLIME_TEST_TIMEOUT=1 python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "15 SLIME_TEST_CMD timeout -> degrade (no block)" "$out" ;;
  *systemMessage*) ok "15 SLIME_TEST_CMD timeout -> degrade (no block)" ;;
  *) bad "15 SLIME_TEST_CMD timeout -> degrade (no block)" "$out" ;;
esac

# A6: multiple PRUNED records -> inject only matching-corridor + recent N
K="$(mkrepo)"
mkdir -p "$K/.slime"
printf '# Corridor: cur\n## Paths\n- lib/**\n' > "$K/.slime/corridor.md"
cat > "$K/.slime/PRUNED.md" <<'EOF'
# Pruned
## [2026-01-01] corridor:cur
**Pruned:** OLDMATCH
## [2026-01-02] corridor:a
**Pruned:** ALPHA
## [2026-01-03] corridor:b
**Pruned:** RECENT1
## [2026-01-04] corridor:c
**Pruned:** RECENT2
EOF
out=$(prompt "$K" | SLIME_PRUNE_RECENT=2 python3 "$PRUNE")
if grep -q OLDMATCH <<<"$out" && grep -q RECENT1 <<<"$out" && grep -q RECENT2 <<<"$out" && ! grep -q ALPHA <<<"$out"; then
  ok "16 multi PRUNED -> matching corridor + recent N only"
else
  bad "16 multi PRUNED -> matching corridor + recent N only" "$out"
fi

# A7: SLIME_PRUNE_RECENT=0 -> inject only matching-corridor records
out=$(prompt "$K" | SLIME_PRUNE_RECENT=0 python3 "$PRUNE")
if grep -q OLDMATCH <<<"$out" && ! grep -q RECENT2 <<<"$out" && ! grep -q ALPHA <<<"$out"; then
  ok "17 RECENT=0 -> only matching-corridor records"
else
  bad "17 RECENT=0 -> only matching-corridor records" "$out"
fi

# A8: editing .slime/ artifacts is not counted as out-of-corridor
L="$(mkrepo)"
mkdir -p "$L/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$L/.slime/corridor.md"
printf '# Pruned\n' > "$L/.slime/PRUNED.md"
git -C "$L" add -A && git -C "$L" commit -qm init
printf '## changed\n' >> "$L/.slime/corridor.md"   # widen/edit corridor
printf '## entry\n' >> "$L/.slime/PRUNED.md"        # log a prune
out=$(stop "$L" | python3 "$PATCH")
case "$out" in
  *"out-of-corridor files: 0"*) ok "18 .slime/ edits not counted out-of-corridor" ;;
  *) bad "18 .slime/ edits not counted out-of-corridor" "$out" ;;
esac

# === Typecheck gate (SLIME_TYPECHECK_CMD) — proposal AC1-AC6 ================
M="$(mkrepo)"
mkdir -p "$M/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$M/.slime/corridor.md"
git -C "$M" add -A && git -C "$M" commit -qm init

# AC1: unset -> degrade (no typecheck block)
out=$(stop "$M" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "19 SLIME_TYPECHECK_CMD unset -> degrade" "$out" ;;
  *systemMessage*) ok "19 SLIME_TYPECHECK_CMD unset -> degrade (no block)" ;;
  *) bad "19 SLIME_TYPECHECK_CMD unset -> degrade" "$out" ;;
esac

# AC2: exit 0 -> no typecheck block
out=$(stop "$M" | SLIME_TYPECHECK_CMD='sh -c "exit 0"' python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "20 SLIME_TYPECHECK_CMD exit 0 -> no block" "$out" ;;
  *systemMessage*) ok "20 SLIME_TYPECHECK_CMD exit 0 -> no block" ;;
  *) bad "20 SLIME_TYPECHECK_CMD exit 0 -> no block" "$out" ;;
esac

# AC3: exit 1 -> block, reason carries the remedy text
out=$(stop "$M" | SLIME_TYPECHECK_CMD='sh -c "exit 1"' python3 "$PATCH")
case "$out" in
  *'"block"'*Typecheck*hallucinated*) ok "21 SLIME_TYPECHECK_CMD exit 1 -> block (remedy text)" ;;
  *) bad "21 SLIME_TYPECHECK_CMD exit 1 -> block (remedy text)" "$out" ;;
esac

# AC4: command not found -> degrade (no false block)
out=$(stop "$M" | SLIME_TYPECHECK_CMD='this-cmd-does-not-exist-xyz' python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "22 missing typecheck cmd -> degrade" "$out" ;;
  *systemMessage*) ok "22 missing typecheck cmd -> degrade (no block)" ;;
  *) bad "22 missing typecheck cmd -> degrade" "$out" ;;
esac

# AC5: typecheck fail + new dependency -> both blocks present
P5="$(mkrepo)"
printf 'name: d\ndependencies:\n  flutter:\n    sdk: flutter\n' > "$P5/pubspec.yaml"
mkdir -p "$P5/.slime"; printf '# Corridor: real\n## Paths\n- lib/**\n' > "$P5/.slime/corridor.md"
git -C "$P5" add -A && git -C "$P5" commit -qm init
printf 'name: d\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^1\n' > "$P5/pubspec.yaml"
out=$(stop "$P5" | SLIME_TYPECHECK_CMD='sh -c "exit 1"' python3 "$PATCH")
if grep -q Typecheck <<<"$out" && grep -q 'New dependency' <<<"$out" && grep -q http <<<"$out"; then
  ok "23 typecheck + dependency -> both blocks in reason"
else
  bad "23 typecheck + dependency -> both blocks in reason" "$out"
fi

# AC6: stop_hook_active -> no block even if typecheck fails
out=$(printf '{"hook_event_name":"Stop","stop_hook_active":true,"cwd":"%s"}' "$(hostpath "$M")" | SLIME_TYPECHECK_CMD='sh -c "exit 1"' python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "24 stop_hook_active + typecheck fail -> no block" "$out" ;;
  *systemMessage*) ok "24 stop_hook_active + typecheck fail -> no block" ;;
  *) bad "24 stop_hook_active + typecheck fail -> no block" "$out" ;;
esac

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
