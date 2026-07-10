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
#     PreToolUse allows (gate only checks corridor validity), and Stop blocks
#     by default because out-of-corridor product code is semantic displacement.
G="$(mkrepo)"
mkdir -p "$G/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$G/.slime/corridor.md"
git -C "$G" add -A && git -C "$G" commit -qm init
out=$(pre "$G" "$G/other/y.py" | python3 "$PATCH")
[ -z "$out" ] && ok "12 out-of-corridor edit -> PreToolUse allow" || bad "12 out-of-corridor edit -> PreToolUse allow" "$out"
mkdir -p "$G/other"; printf 'x\n' > "$G/other/y.py"
out=$(stop "$G" | python3 "$PATCH")
case "$out" in
  *'"block"'*"out-of-corridor"*) ok "13 out-of-corridor product code blocks by default" ;;
  *) bad "13 out-of-corridor product code blocks by default" "$out" ;;
esac

# A3b: report-only escape hatch keeps the cost report visible without blocking.
out=$(stop "$G" | SLIME_STRICT_CORRIDOR=0 python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "13b SLIME_STRICT_CORRIDOR=0 -> report only" "$out" ;;
  *"out-of-corridor files: 1"*) ok "13b SLIME_STRICT_CORRIDOR=0 -> report only" ;;
  *) bad "13b SLIME_STRICT_CORRIDOR=0 -> report only" "$out" ;;
esac

# A3c: git-style glob semantics — a single * must not cross directories, so
#      lib/*.dart cannot silently admit lib/vendor/deep.dart; and **/ matches
#      zero directories, so lib/**/*.dart covers lib/top.dart.
G2="$(mkrepo)"
mkdir -p "$G2/.slime"
printf '# Corridor: real\n## Paths\n- lib/*.dart\n' > "$G2/.slime/corridor.md"
git -C "$G2" add -A && git -C "$G2" commit -qm init
mkdir -p "$G2/lib/vendor"; printf 'x\n' > "$G2/lib/vendor/deep.dart"
out=$(stop "$G2" | python3 "$PATCH")
case "$out" in
  *'"block"'*"out-of-corridor"*) ok "13c single * does not cross / -> nested edit blocks" ;;
  *) bad "13c single * does not cross / -> nested edit blocks" "$out" ;;
esac
G3="$(mkrepo)"
mkdir -p "$G3/.slime"
printf '# Corridor: real\n## Paths\n- lib/**/*.dart\n' > "$G3/.slime/corridor.md"
git -C "$G3" add -A && git -C "$G3" commit -qm init
mkdir -p "$G3/lib"; printf 'x\n' > "$G3/lib/top.dart"
out=$(stop "$G3" | python3 "$PATCH")
case "$out" in
  *'"block"'*"out-of-corridor"*) bad "13d **/ matches zero dirs -> top-level edit allowed" "$out" ;;
  *) ok "13d **/ matches zero dirs -> top-level edit allowed" ;;
esac

# A3e: non-ASCII filename inside the corridor must not false-block — git's
#      default core.quotepath C-quoting reports "lib/caf\303\251.dart", which
#      can never match a corridor glob.
G4="$(mkrepo)"
mkdir -p "$G4/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$G4/.slime/corridor.md"
git -C "$G4" add -A && git -C "$G4" commit -qm init
mkdir -p "$G4/lib"; printf 'x\n' > "$G4/lib/café.dart"
out=$(stop "$G4" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "13e non-ASCII name inside corridor -> no false block" "$out" ;;
  *systemMessage*) ok "13e non-ASCII name inside corridor -> no false block" ;;
  *) bad "13e non-ASCII name inside corridor -> no false block" "$out" ;;
esac

# A3f: corridor listing the exact non-ASCII filename must match it — git's
#      UTF-8 path bytes must be decoded as UTF-8, not the locale codepage
#      (cp936 turns "caf\303\251" into mojibake, so the glob never matches
#      and the gate false-blocks; lib/** in 13e cannot catch this because
#      the "lib/" prefix survives the mis-decode).
G5="$(mkrepo)"
mkdir -p "$G5/.slime"
printf '# Corridor: real\n## Paths\n- lib/café.dart\n' > "$G5/.slime/corridor.md"
git -C "$G5" add -A && git -C "$G5" commit -qm init
mkdir -p "$G5/lib"; printf 'x\n' > "$G5/lib/café.dart"
out=$(stop "$G5" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "13f corridor lists exact non-ASCII name -> no false block" "$out" ;;
  *systemMessage*) ok "13f corridor lists exact non-ASCII name -> no false block" ;;
  *) bad "13f corridor lists exact non-ASCII name -> no false block" "$out" ;;
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

# === Repo-meta files exempt from corridor gate ==============================
# These are repo metadata, not product code — the corridor concept has no real
# "frontier" to compute against them, so requiring a corridor is pure friction.
N="$(mkrepo)"

# 25: no corridor + edit .gitignore -> allow (was: deny, pre-exemption)
out=$(pre "$N" "$N/.gitignore" | python3 "$PATCH")
[ -z "$out" ] && ok "25 no corridor + edit .gitignore -> allow" || bad "25 no corridor + edit .gitignore -> allow" "$out"

# 26: no corridor + edit LICENSE -> allow
out=$(pre "$N" "$N/LICENSE" | python3 "$PATCH")
[ -z "$out" ] && ok "26 no corridor + edit LICENSE -> allow" || bad "26 no corridor + edit LICENSE -> allow" "$out"

# 27: no corridor + edit nested .gitignore -> allow (basename match, mirrors git)
out=$(pre "$N" "$N/sub/dir/.gitignore" | python3 "$PATCH")
[ -z "$out" ] && ok "27 no corridor + edit nested .gitignore -> allow" || bad "27 no corridor + edit nested .gitignore -> allow" "$out"

# 28: no corridor + edit README.md -> still DENY (README is not on the exempt list)
out=$(pre "$N" "$N/README.md" | python3 "$PATCH")
case "$out" in
  *'"deny"'*) ok "28 no corridor + edit README.md -> deny (not exempt)" ;;
  *) bad "28 no corridor + edit README.md -> deny (not exempt)" "$out" ;;
esac

# 29: default strict corridor still ignores repo metadata; it is not product code.
mkdir -p "$N/.slime"
printf '# Corridor: meta\n## Paths\n- lib/**\n' > "$N/.slime/corridor.md"
printf 'tmp/\n' > "$N/.gitignore"
out=$(stop "$N" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "29 default strict + metadata edit -> no block" "$out" ;;
  *systemMessage*) ok "29 default strict + metadata edit -> no block" ;;
  *) bad "29 default strict + metadata edit -> no block" "$out" ;;
esac

# === Gate integrity (round 2) ===============================================

# 30: PRUNED.md seeded untracked by install.sh must not neuter the
#     failing-check gate — the untracked template only counts as "prune
#     logged" once it carries a record for a real corridor.
Q="$(mkrepo)"
mkdir -p "$Q/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$Q/.slime/corridor.md"
git -C "$Q" add -A && git -C "$Q" commit -qm init
cp "$ROOT/templates/.slime/PRUNED.md" "$Q/.slime/PRUNED.md"   # untracked, as installed
out=$(stop "$Q" | SLIME_TEST_CMD='exit 1' python3 "$PATCH")
case "$out" in
  *'"block"'*"failing check"*) ok "30 untracked template PRUNED.md does not disarm red-check gate" ;;
  *) bad "30 untracked template PRUNED.md does not disarm red-check gate" "$out" ;;
esac

# 30b: a real record appended to the still-untracked log re-arms the exit.
printf '\n## [2026-07-06] corridor:real\n**Pruned:** the abandoned design\n' >> "$Q/.slime/PRUNED.md"
out=$(stop "$Q" | SLIME_TEST_CMD='exit 1' python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "30b untracked PRUNED.md with real record -> may stop on red" "$out" ;;
  *systemMessage*) ok "30b untracked PRUNED.md with real record -> may stop on red" ;;
  *) bad "30b untracked PRUNED.md with real record -> may stop on red" "$out" ;;
esac

# 31: emptying corridor.md after editing product code must not launder the
#     out-of-corridor check (.slime/ writes are exempt at PreToolUse).
R2="$(mkrepo)"
mkdir -p "$R2/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$R2/.slime/corridor.md"
git -C "$R2" add -A && git -C "$R2" commit -qm init
mkdir -p "$R2/other"; printf 'x\n' > "$R2/other/z.py"
printf '# Corridor: real\n## Paths\n' > "$R2/.slime/corridor.md"   # scope laundering
out=$(stop "$R2" | python3 "$PATCH")
case "$out" in
  *'"block"'*"Restore or complete"*) ok "31 emptied corridor + product change -> block" ;;
  *) bad "31 emptied corridor + product change -> block" "$out" ;;
esac

# 31b: report-only mode still escapes (no false-block training).
out=$(stop "$R2" | SLIME_STRICT_CORRIDOR=0 python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "31b emptied corridor + STRICT=0 -> report only" "$out" ;;
  *systemMessage*) ok "31b emptied corridor + STRICT=0 -> report only" ;;
  *) bad "31b emptied corridor + STRICT=0 -> report only" "$out" ;;
esac

# 32: dependency gate survives 4-space pubspec indentation.
P6="$(mkrepo)"
printf 'name: d\ndependencies:\n    flutter:\n        sdk: flutter\n' > "$P6/pubspec.yaml"
mkdir -p "$P6/.slime"
printf '# Corridor: real\n## Paths\n- lib/**\n' > "$P6/.slime/corridor.md"
git -C "$P6" add -A && git -C "$P6" commit -qm init
printf 'name: d\ndependencies:\n    flutter:\n        sdk: flutter\n    http: ^1\n' > "$P6/pubspec.yaml"
out=$(stop "$P6" | python3 "$PATCH")
case "$out" in
  *'"block"'*http*) ok "32 4-space pubspec + new dep -> block (names it)" ;;
  *) bad "32 4-space pubspec + new dep -> block (names it)" "$out" ;;
esac

# === Rigor-aware corridor validation =======================================

# 33: a legacy corridor has no Rigor section and must remain valid.
R3="$(mkrepo)"
mkdir -p "$R3/.slime"
printf '# Corridor: legacy\n## Paths\n- lib/**\n' > "$R3/.slime/corridor.md"
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
[ -z "$out" ] && ok "33 legacy corridor remains valid" || bad "33 legacy corridor remains valid" "$out"

printf '# Corridor: legacy-labeled\n## Paths (allowed files)\n- lib/**\n' > "$R3/.slime/corridor.md"
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
[ -z "$out" ] && ok "33b legacy decorated Paths heading remains valid" || bad "33b legacy decorated Paths heading remains valid" "$out"

# 34: an explicit but unknown rigor is an unambiguous format error.
cat > "$R3/.slime/corridor.md" <<'EOF'
# Corridor: bad-rigor
## Rigor
extreme
## Paths
- lib/**
EOF
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"unknown rigor"*) ok "34 unknown rigor -> deny" ;;
  *) bad "34 unknown rigor -> deny" "$out" ;;
esac

cat > "$R3/.slime/corridor.md" <<'EOF'
# Corridor: empty-rigor
## Rigor
## Paths
- lib/**
EOF
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"empty Rigor"*) ok "34b empty explicit rigor -> deny" ;;
  *) bad "34b empty explicit rigor -> deny" "$out" ;;
esac

# 35: trivial requires only Scope, Paths, and Stop Condition.
cat > "$R3/.slime/corridor.md" <<'EOF'
# Corridor: tiny-fix
## Rigor
trivial
## Scope
Correct one local typo.
## Paths
- lib/x.py
## Stop Condition
- The focused check passes.
EOF
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
[ -z "$out" ] && ok "35 complete trivial corridor -> allow" || bad "35 complete trivial corridor -> allow" "$out"

# 36: explicit rigor activates structural validation.
sed '/## Stop Condition/,$d' "$R3/.slime/corridor.md" > "$R3/.slime/corridor.tmp"
mv "$R3/.slime/corridor.tmp" "$R3/.slime/corridor.md"
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"Stop Condition"*) ok "36 trivial missing Stop Condition -> deny" ;;
  *) bad "36 trivial missing Stop Condition -> deny" "$out" ;;
esac

# 37: normal requires both supporting and falsifying evidence.
cat > "$R3/.slime/corridor.md" <<'EOF'
# Corridor: normal-fix
## Rigor
normal
## Scope
Change one observable behavior.
## Semantic Delta
- This task changes: the requested behavior.
- This task preserves: existing APIs.
## Non-goals
- No unrelated refactor.
## Paths
- lib/**
## Goal Frontier
- The acceptance criterion passes.
## Start Frontier
- lib/x.py:run
## Evidence
- Supports: the failing test reaches lib/x.py:run.
- Would falsify: the stack trace points to another owner.
## Stop Condition
- The focused test passes.
EOF
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
[ -z "$out" ] && ok "37 complete normal corridor -> allow" || bad "37 complete normal corridor -> allow" "$out"

sed '/Supports:/d' "$R3/.slime/corridor.md" > "$R3/.slime/corridor.tmp"
mv "$R3/.slime/corridor.tmp" "$R3/.slime/corridor.md"
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"Supports:"*) ok "38 normal missing Supports evidence -> deny" ;;
  *) bad "38 normal missing Supports evidence -> deny" "$out" ;;
esac

sed 's/- Would falsify:/- Supports: replacement\n- Missing falsifier:/' "$R3/.slime/corridor.md" > "$R3/.slime/corridor.tmp"
mv "$R3/.slime/corridor.tmp" "$R3/.slime/corridor.md"
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"Would falsify:"*) ok "39 normal missing falsifier -> deny" ;;
  *) bad "39 normal missing falsifier -> deny" "$out" ;;
esac

# 40: high adds explicit failure, rollback, and independent-check controls.
cat > "$R3/.slime/corridor.md" <<'EOF'
# Corridor: risky-change
## Rigor
high
## Scope
Change a high-risk behavior.
## Semantic Delta
- This task changes: the requested behavior.
- This task preserves: existing ownership.
## Non-goals
- No unrelated migration.
## Paths
- lib/**
## Goal Frontier
- The acceptance criterion passes.
## Start Frontier
- lib/x.py:run
## Evidence
- Supports: the runtime trace reaches lib/x.py:run.
- Would falsify: the trace bypasses that seam.
## Stop Condition
- The focused and full checks pass.
## High-risk Controls
- Failure mode: requests may be rejected.
- Rollback: revert the feature flag.
- Independent check: run the integration suite.
EOF
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
[ -z "$out" ] && ok "40 complete high corridor -> allow" || bad "40 complete high corridor -> allow" "$out"

for field in 'Failure mode:' 'Rollback:' 'Independent check:'; do
  grep -v -- "$field" "$R3/.slime/corridor.md" > "$R3/.slime/corridor.tmp"
  mv "$R3/.slime/corridor.tmp" "$R3/.slime/corridor.missing.md"
  mv "$R3/.slime/corridor.md" "$R3/.slime/corridor.full.md"
  mv "$R3/.slime/corridor.missing.md" "$R3/.slime/corridor.md"
  out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
  case "$out" in
    *'"deny"'*"$field"*) ok "41 high missing $field -> deny" ;;
    *) bad "41 high missing $field -> deny" "$out" ;;
  esac
  mv "$R3/.slime/corridor.md" "$R3/.slime/corridor.missing.md"
  mv "$R3/.slime/corridor.full.md" "$R3/.slime/corridor.md"
done

# 42: rigor mismatch signals are report-only and do not create a Stop block.
TIER="$(mkrepo)"
mkdir -p "$TIER/.slime" "$TIER/lib"
cat > "$TIER/.slime/corridor.md" <<'EOF'
# Corridor: under-scoped
## Rigor
trivial
## Scope
One local change.
## Paths
- lib/**
## Stop Condition
- Focused check passes.
EOF
printf 'old\n' > "$TIER/lib/a.py"
printf 'old\n' > "$TIER/lib/b.py"
git -C "$TIER" add -A && git -C "$TIER" commit -qm init
printf 'class A:\n    pass\n' > "$TIER/lib/a.py"
printf 'new\n' > "$TIER/lib/b.py"
out=$(stop "$TIER" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "42 trivial mismatch stays warning-only" "$out" ;;
  *"rigor mismatch"*"consider normal/high"*) ok "42 trivial mismatch stays warning-only" ;;
  *) bad "42 trivial mismatch stays warning-only" "$out" ;;
esac

# 43: normal above the existing 12-file review default suggests high, not block.
NORM="$(mkrepo)"
mkdir -p "$NORM/.slime" "$NORM/lib"
cat > "$NORM/.slime/corridor.md" <<'EOF'
# Corridor: broad-normal
## Rigor
normal
## Scope
Update a broad generated surface.
## Semantic Delta
- This task changes: generated values.
- This task preserves: public APIs.
## Non-goals
- No architecture change.
## Paths
- lib/**
## Goal Frontier
- Generated values are current.
## Start Frontier
- lib/:generated files
## Evidence
- Supports: the generator owns these files.
- Would falsify: a hand-owned file appears.
## Stop Condition
- Generated output check passes.
EOF
for i in $(seq 1 13); do printf 'old\n' > "$NORM/lib/$i.txt"; done
git -C "$NORM" add -A && git -C "$NORM" commit -qm init
for i in $(seq 1 13); do printf 'new\n' > "$NORM/lib/$i.txt"; done
out=$(stop "$NORM" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "43 broad normal mismatch stays warning-only" "$out" ;;
  *"rigor mismatch"*"consider high"*) ok "43 broad normal mismatch stays warning-only" ;;
  *) bad "43 broad normal mismatch stays warning-only" "$out" ;;
esac

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
