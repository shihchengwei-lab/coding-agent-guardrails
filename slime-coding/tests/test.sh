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
prepatch() { printf '{"hook_event_name":"PreToolUse","tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\\n*** Update File: %s\\n*** End Patch"},"cwd":"%s"}' "$(hostpath "$2")" "$(hostpath "$1")"; }
prompt() { printf '{"hook_event_name":"UserPromptSubmit","cwd":"%s"}' "$(hostpath "$1")"; }
stop()   { printf '{"hook_event_name":"Stop","cwd":"%s"}' "$(hostpath "$1")"; }
turn_start() { printf '{"hook_event_name":"UserPromptSubmit","turn_id":"%s","session_id":"session-test","cwd":"%s"}' "$2" "$(hostpath "$1")"; }
turn_stop() { printf '{"hook_event_name":"Stop","turn_id":"%s","session_id":"session-test","cwd":"%s"}' "$2" "$(hostpath "$1")"; }
post_bash() { printf '{"hook_event_name":"PostToolUse","turn_id":"%s","session_id":"session-test","tool_name":"Bash","tool_input":{"command":"%s"},"cwd":"%s"}' "$2" "$3" "$(hostpath "$1")"; }
write_checks() {
  local gitdir
  gitdir="$(git -C "$1" rev-parse --absolute-git-dir)"
  mkdir -p "$gitdir/guardrails"
  printf '%s' "$2" > "$gitdir/guardrails/config.json"
}

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

printf '# Corridor: real\n## Rigor\ntrivial\n## Outcome\nEdit lib only.\n## Paths\n- lib/**\n## Stop Condition\n- Manual: inspected\n' > "$D/.slime/corridor.md"
out=$(pre "$D" "$D/lib/x.dart" | python3 "$PATCH")
[ -z "$out" ] && ok "4  valid corridor + edit allowed file -> allow" || bad "4  valid corridor + edit allowed file -> allow" "$out"

out=$(prepatch "$D" "$D/lib/x.dart" | python3 "$PATCH")
[ -z "$out" ] && ok "4b Codex apply_patch inside corridor -> allow" || bad "4b Codex apply_patch inside corridor -> allow" "$out"

out=$(prepatch "$D" "$D/other/x.dart" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"outside the corridor"*) ok "4c Codex apply_patch outside corridor -> deny" ;;
  *) bad "4c Codex apply_patch outside corridor -> deny" "$out" ;;
esac

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
  *systemMessage*) ok "7  legacy env without product delta is not executed" ;;
  *) bad "7  legacy env without product delta is not executed" "$out" ;;
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

printf '# Corridor: real-task\n## Paths\n- **/*\n' > "$F/.slime/corridor.md"
out=$(pre "$F" "$F/lib/x.dart" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"match-all"*) ok "11b match-all corridor -> deny" ;;
  *) bad "11b match-all corridor -> deny" "$out" ;;
esac

printf '# Corridor: real-task\n## Paths\n- ../**\n' > "$F/.slime/corridor.md"
out=$(pre "$F" "$(dirname "$F")/outside.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"outside the repository"*) ok "11c parent-path corridor cannot authorize external edit" ;;
  *) bad "11c parent-path corridor cannot authorize external edit" "$out" ;;
esac

# A3: valid corridor + edit a file OUTSIDE the corridor -> deny before writing.
G="$(mkrepo)"
mkdir -p "$G/.slime"
printf '# Corridor: real\n## Rigor\ntrivial\n## Outcome\nEdit lib only.\n## Paths\n- lib/**\n## Stop Condition\n- Manual: inspected\n' > "$G/.slime/corridor.md"
git -C "$G" add -A && git -C "$G" commit -qm init
out=$(pre "$G" "$G/other/y.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"outside the corridor"*) ok "12 out-of-corridor edit -> PreToolUse deny" ;;
  *) bad "12 out-of-corridor edit -> PreToolUse deny" "$out" ;;
esac
mkdir -p "$G/other"; printf 'x\n' > "$G/other/y.py"
out=$(stop "$G" | python3 "$PATCH")
case "$out" in
  *'"block"'*"out-of-corridor"*) ok "13 out-of-corridor product code blocks by default" ;;
  *) bad "13 out-of-corridor product code blocks by default" "$out" ;;
esac

# A3b: the core boundary cannot be disabled by an environment escape hatch.
out=$(stop "$G" | SLIME_STRICT_CORRIDOR=0 python3 "$PATCH")
case "$out" in
  *'"block"'*"out-of-corridor"*) ok "13b strict corridor cannot be disabled" ;;
  *) bad "13b strict corridor cannot be disabled" "$out" ;;
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
printf '# Corridor: real\n## Rigor\ntrivial\n## Outcome\nmatch top level\n## Paths\n- lib/**/*.dart\n## Stop Condition\n- Manual: path checked\n' > "$G3/.slime/corridor.md"
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
printf '# Corridor: real\n## Rigor\ntrivial\n## Outcome\nUTF-8 path works\n## Paths\n- lib/**\n## Stop Condition\n- Manual: path checked\n' > "$G4/.slime/corridor.md"
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
printf '# Corridor: real\n## Rigor\ntrivial\n## Outcome\nUTF-8 exact path works\n## Paths\n- lib/café.dart\n## Stop Condition\n- Manual: path checked\n' > "$G5/.slime/corridor.md"
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

# A5: a configured check timing out is not verification and must block.
out=$(stop "$H" | SLIME_TEST_CMD='sleep 5' SLIME_TEST_TIMEOUT=1 python3 "$PATCH")
case "$out" in
  *systemMessage*) ok "15 SLIME_TEST_CMD is not executed without product delta" ;;
  *) bad "15 SLIME_TEST_CMD is not executed without product delta" "$out" ;;
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
  *systemMessage*) ok "21 legacy typecheck is not executed" ;;
  *) bad "21 legacy typecheck is not executed" "$out" ;;
esac

# AC4: a configured command that cannot run is a broken gate and must block.
out=$(stop "$M" | SLIME_TYPECHECK_CMD='this-cmd-does-not-exist-xyz' python3 "$PATCH")
case "$out" in
  *systemMessage*) ok "22 missing legacy typecheck is not executed" ;;
  *) bad "22 missing legacy typecheck is not executed" "$out" ;;
esac

# AC5: typecheck fail + new dependency -> both blocks present
P5="$(mkrepo)"
printf 'name: d\ndependencies:\n  flutter:\n    sdk: flutter\n' > "$P5/pubspec.yaml"
mkdir -p "$P5/.slime"; printf '# Corridor: real\n## Paths\n- lib/**\n' > "$P5/.slime/corridor.md"
git -C "$P5" add -A && git -C "$P5" commit -qm init
printf 'name: d\ndependencies:\n  flutter:\n    sdk: flutter\n  http: ^1\n' > "$P5/pubspec.yaml"
out=$(stop "$P5" | SLIME_TYPECHECK_CMD='sh -c "exit 1"' python3 "$PATCH")
if grep -q 'New dependency' <<<"$out" && grep -q http <<<"$out" && ! grep -q 'SLIME_TYPECHECK_CMD' <<<"$out"; then
  ok "23 retired env is ignored while dependency still blocks"
else
  bad "23 retired env is ignored while dependency still blocks" "$out"
fi

# AC6: a second Stop re-runs the gate; red does not become green by retrying Stop.
out=$(printf '{"hook_event_name":"Stop","stop_hook_active":true,"cwd":"%s"}' "$(hostpath "$M")" | SLIME_TYPECHECK_CMD='sh -c "exit 1"' python3 "$PATCH")
case "$out" in
  *systemMessage*) ok "24 stop retry does not execute legacy typecheck" ;;
  *) bad "24 stop retry does not execute legacy typecheck" "$out" ;;
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
  *systemMessage*) ok "30 PRUNED does not cause legacy env execution" ;;
  *) bad "30 PRUNED does not cause legacy env execution" "$out" ;;
esac

# 30b: recording a pruned route does not turn a failing check into completion.
printf '\n## [2026-07-06] corridor:real\n**Pruned:** the abandoned design\n' >> "$Q/.slime/PRUNED.md"
out=$(stop "$Q" | SLIME_TEST_CMD='exit 1' python3 "$PATCH")
case "$out" in
  *systemMessage*) ok "30b PRUNED record does not restore legacy env execution" ;;
  *) bad "30b PRUNED record does not restore legacy env execution" "$out" ;;
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

# 31b: invalid corridor cannot be laundered through an environment override.
out=$(stop "$R2" | SLIME_STRICT_CORRIDOR=0 python3 "$PATCH")
case "$out" in
  *'"block"'*"Restore or complete"*) ok "31b invalid corridor cannot be disabled" ;;
  *) bad "31b invalid corridor cannot be disabled" "$out" ;;
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

# 32b: npm dependency additions are detected without Flutter-specific config.
NPM="$(mkrepo)"
printf '{"dependencies":{"left-pad":"1.0.0"}}\n' > "$NPM/package.json"
mkdir -p "$NPM/.slime"
printf '# Corridor: npm\n## Paths\n- package.json\n' > "$NPM/.slime/corridor.md"
git -C "$NPM" add -A && git -C "$NPM" commit -qm init
printf '{"dependencies":{"left-pad":"1.0.0","react":"19.0.0"}}\n' > "$NPM/package.json"
out=$(stop "$NPM" | python3 "$PATCH")
case "$out" in
  *'"block"'*package.json*react*) ok "32b npm new dep -> block" ;;
  *) bad "32b npm new dep -> block" "$out" ;;
esac

cat > "$NPM/.slime/corridor.md" <<'EOF'
# Corridor: npm-justified
## Rigor
normal
## Outcome
The requested UI uses the project-standard React runtime.
## Paths
- package.json
## Evidence
- Supports: the existing application is already React-based.
- Would falsify: the target package is not used by the application runtime.
- Dependency: react — required by the requested UI and existing framework.
## Stop Condition
- Manual: dependency manifest contains only the justified package.
EOF
out=$(stop "$NPM" | python3 "$PATCH")
case "$out" in
  *'"block"'*"New dependency"*) bad "32b2 justified npm dep -> allow" "$out" ;;
  *systemMessage*) ok "32b2 justified npm dep -> allow" ;;
  *) bad "32b2 justified npm dep -> allow" "$out" ;;
esac

# 32c: Python requirements and pyproject additions are detected.
PYDEPS="$(mkrepo)"
printf 'requests==2.0\n' > "$PYDEPS/requirements.txt"
printf '[project]\ndependencies = ["requests>=2"]\n' > "$PYDEPS/pyproject.toml"
mkdir -p "$PYDEPS/.slime"
printf '# Corridor: python-deps\n## Paths\n- requirements.txt\n- pyproject.toml\n' > "$PYDEPS/.slime/corridor.md"
git -C "$PYDEPS" add -A && git -C "$PYDEPS" commit -qm init
printf 'requests==2.0\nflask==3.0\n' > "$PYDEPS/requirements.txt"
printf '[project]\ndependencies = ["requests>=2", "httpx>=0.27"]\n' > "$PYDEPS/pyproject.toml"
out=$(stop "$PYDEPS" | python3 "$PATCH")
if grep -q requirements.txt <<<"$out" && grep -q flask <<<"$out" && grep -q pyproject.toml <<<"$out" && grep -q httpx <<<"$out"; then
  ok "32c Python new deps -> block and name both manifests"
else
  bad "32c Python new deps -> block and name both manifests" "$out"
fi

# 32d: Cargo and Go module additions are detected.
SYSDEPS="$(mkrepo)"
printf '[package]\nname="x"\nversion="0.1.0"\n[dependencies]\nserde="1"\n' > "$SYSDEPS/Cargo.toml"
printf 'module example.com/x\n\ngo 1.22\n\nrequire example.com/a v1.0.0\n' > "$SYSDEPS/go.mod"
mkdir -p "$SYSDEPS/.slime"
printf '# Corridor: systems-deps\n## Paths\n- Cargo.toml\n- go.mod\n' > "$SYSDEPS/.slime/corridor.md"
git -C "$SYSDEPS" add -A && git -C "$SYSDEPS" commit -qm init
printf '[package]\nname="x"\nversion="0.1.0"\n[dependencies]\nserde="1"\nanyhow="1"\n' > "$SYSDEPS/Cargo.toml"
printf 'module example.com/x\n\ngo 1.22\n\nrequire (\nexample.com/a v1.0.0\nexample.com/b v1.2.0\n)\n' > "$SYSDEPS/go.mod"
out=$(stop "$SYSDEPS" | python3 "$PATCH")
if grep -q Cargo.toml <<<"$out" && grep -q anyhow <<<"$out" && grep -q go.mod <<<"$out" && grep -q example.com/b <<<"$out"; then
  ok "32d Cargo and Go new deps -> block"
else
  bad "32d Cargo and Go new deps -> block" "$out"
fi

# 32e: an inline Stop Condition command is inert and cannot satisfy the grammar.
AUTOCHK="$(mkrepo)"
mkdir -p "$AUTOCHK/.slime"
cat > "$AUTOCHK/.slime/corridor.md" <<'EOF'
# Corridor: automatic-check
## Rigor
trivial
## Outcome
The focused behavior is correct.
## Paths
- lib/x.py
## Stop Condition
- Command: python3 -c "raise SystemExit(1)"
EOF
mkdir -p "$AUTOCHK/lib" && printf 'delta\n' > "$AUTOCHK/lib/x.py"
out=$(stop "$AUTOCHK" | python3 "$PATCH")
case "$out" in
  *'"block"'*"Check: or Manual:"*) ok "32e inline Stop command is inert and does not satisfy the gate" ;;
  *) bad "32e inline Stop command is inert and does not satisfy the gate" "$out" ;;
esac

# === Rigor-aware corridor validation =======================================

# 33: a corridor without Rigor is rejected instead of silently downgraded.
R3="$(mkrepo)"
mkdir -p "$R3/.slime"
printf '# Corridor: legacy\n## Paths\n- lib/**\n' > "$R3/.slime/corridor.md"
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*"explicit Rigor"*) ok "33 corridor without Rigor is rejected" ;;
  *) bad "33 corridor without Rigor is rejected" "$out" ;;
esac

printf '# Corridor: legacy-labeled\n## Paths (allowed files)\n- lib/**\n' > "$R3/.slime/corridor.md"
out=$(pre "$R3" "$R3/lib/x.py" | python3 "$PATCH")
case "$out" in
  *'"deny"'*) ok "33b decorated legacy Paths heading is rejected" ;;
  *) bad "33b decorated legacy Paths heading is rejected" "$out" ;;
esac

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

# 35: trivial requires only Outcome, Paths, and Stop Condition.
cat > "$R3/.slime/corridor.md" <<'EOF'
# Corridor: tiny-fix
## Rigor
trivial
## Outcome
The typo is corrected without changing behavior.
## Paths
- lib/x.py
## Stop Condition
- Manual: the focused check passes.
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
## Outcome
The requested observable behavior changes while existing APIs remain stable.
## Paths
- lib/**
## Evidence
- Supports: the failing test reaches lib/x.py:run.
- Would falsify: the stack trace points to another owner.
## Stop Condition
- Manual: the focused test passes.
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
## Outcome
The high-risk behavior changes while existing ownership remains stable.
## Paths
- lib/**
## Evidence
- Supports: the runtime trace reaches lib/x.py:run.
- Would falsify: the trace bypasses that seam.
## Stop Condition
- Check: primary
## High-risk Controls
- Failure mode: requests may be rejected.
- Rollback: revert the feature flag.
- Independent check: integration
EOF
write_checks "$R3" '{"schema":1,"checks":{"primary":{"argv":["python3","-c","raise SystemExit(0)"]},"integration":{"argv":["python3","-c","raise SystemExit(0+0)"]}}}'
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

# 41b: high independent check is an actual gate, not a prose placeholder.
write_checks "$R3" '{"schema":1,"checks":{"primary":{"argv":["python3","-c","raise SystemExit(0)"]},"integration":{"argv":["python3","-c","raise SystemExit(1)"]}}}'
mkdir -p "$R3/lib"
printf 'changed\n' > "$R3/lib/x.py"
out=$(stop "$R3" | python3 "$PATCH")
case "$out" in
  *'"block"'*"Independent check"*) ok "41b failing high independent command -> block" ;;
  *) bad "41b failing high independent command -> block" "$out" ;;
esac

# 41c: the independent command cannot merely duplicate the Stop command.
write_checks "$R3" '{"schema":1,"checks":{"primary":{"argv":["python3","-c","raise SystemExit(0)"]},"integration":{"argv":["python3","-c","raise SystemExit(0)"]}}}'
out=$(stop "$R3" | python3 "$PATCH")
case "$out" in
  *'"block"'*"same argv"*) ok "41c duplicate independent argv -> block" ;;
  *) bad "41c duplicate independent argv -> block" "$out" ;;
esac

# 42: trivial is an enforceable one-product-file tier.
TIER="$(mkrepo)"
mkdir -p "$TIER/.slime" "$TIER/lib"
cat > "$TIER/.slime/corridor.md" <<'EOF'
# Corridor: under-scoped
## Rigor
trivial
## Outcome
One local change.
## Paths
- lib/**
## Stop Condition
- Manual: focused check passes.
EOF
printf 'old\n' > "$TIER/lib/a.py"
printf 'old\n' > "$TIER/lib/b.py"
git -C "$TIER" add -A && git -C "$TIER" commit -qm init
printf 'class A:\n    pass\n' > "$TIER/lib/a.py"
printf 'new\n' > "$TIER/lib/b.py"
out=$(stop "$TIER" | python3 "$PATCH")
case "$out" in
  *'"block"'*"trivial corridor"*) ok "42 trivial with multiple product files -> block" ;;
  *) bad "42 trivial with multiple product files -> block" "$out" ;;
esac

# === Turn baseline and shell coverage ======================================

# 44: an unchanged pre-existing dirty file is not attributed to this turn.
TURN="$(mkrepo)"
mkdir -p "$TURN/.slime" "$TURN/lib" "$TURN/other"
cat > "$TURN/.slime/corridor.md" <<'EOF'
# Corridor: turn-delta
## Rigor
trivial
## Outcome
One file changes.
## Paths
- lib/**
## Stop Condition
- Manual: focused check passes.
EOF
printf 'old\n' > "$TURN/lib/a.py"
printf 'old\n' > "$TURN/other/user.py"
git -C "$TURN" add -A && git -C "$TURN" commit -qm init
printf 'user dirty\n' > "$TURN/other/user.py"
turn_start "$TURN" turn-44 | python3 "$PATCH" >/dev/null
printf 'agent change\n' > "$TURN/lib/a.py"
out=$(turn_stop "$TURN" turn-44 | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "44 unchanged pre-existing dirty file is ignored" "$out" ;;
  *systemMessage*) ok "44 unchanged pre-existing dirty file is ignored" ;;
  *) bad "44 unchanged pre-existing dirty file is ignored" "$out" ;;
esac

# 45: modifying that pre-existing file during the turn is detected.
git -C "$TURN" checkout -q -- lib/a.py
turn_start "$TURN" turn-45 | python3 "$PATCH" >/dev/null
printf 'agent overwrote user file\n' > "$TURN/other/user.py"
out=$(turn_stop "$TURN" turn-45 | python3 "$PATCH")
case "$out" in
  *'"block"'*"other/user.py"*) ok "45 changed pre-existing dirty file -> block" ;;
  *) bad "45 changed pre-existing dirty file -> block" "$out" ;;
esac

# 46: a duplicate start cannot launder edits made after the first baseline.
git -C "$TURN" checkout -q -- other/user.py
turn_start "$TURN" turn-46 | python3 "$PATCH" >/dev/null
printf 'outside\n' > "$TURN/other/user.py"
turn_start "$TURN" turn-46 | python3 "$PATCH" >/dev/null
out=$(turn_stop "$TURN" turn-46 | python3 "$PATCH")
case "$out" in
  *'"block"'*"other/user.py"*) ok "46 duplicate start preserves first baseline" ;;
  *) bad "46 duplicate start preserves first baseline" "$out" ;;
esac

# 47: committed changes remain part of the turn delta even with a clean tree.
git -C "$TURN" reset -q --hard HEAD
turn_start "$TURN" turn-47 | python3 "$PATCH" >/dev/null
printf 'committed outside\n' > "$TURN/other/user.py"
git -C "$TURN" add other/user.py && git -C "$TURN" commit -qm outside
out=$(turn_stop "$TURN" turn-47 | python3 "$PATCH")
case "$out" in
  *'"block"'*"other/user.py"*) ok "47 committed out-of-corridor delta -> block" ;;
  *) bad "47 committed out-of-corridor delta -> block" "$out" ;;
esac

# 48: Bash PostToolUse is silent without a delta and reports one immediately.
git -C "$TURN" reset -q --hard HEAD^
turn_start "$TURN" turn-48 | python3 "$PATCH" >/dev/null
out=$(post_bash "$TURN" turn-48 "git status" | python3 "$PATCH")
[ -z "$out" ] && ok "48 Bash without writes -> silent" || bad "48 Bash without writes -> silent" "$out"
printf 'shell outside\n' > "$TURN/other/user.py"
out=$(post_bash "$TURN" turn-48 "write outside" | python3 "$PATCH")
case "$out" in
  *'"block"'*"other/user.py"*) ok "48b Bash outside write -> immediate block" ;;
  *) bad "48b Bash outside write -> immediate block" "$out" ;;
esac

# 49: a pre-existing dependency and product file do not inflate this turn.
DELTAS="$(mkrepo)"
mkdir -p "$DELTAS/.slime" "$DELTAS/lib"
cat > "$DELTAS/.slime/corridor.md" <<'EOF'
# Corridor: scoped-deps
## Rigor
trivial
## Outcome
One product file changes.
## Paths
- lib/**
## Stop Condition
- Manual: focused check passes.
EOF
printf '{"dependencies":{"base":"1"}}\n' > "$DELTAS/package.json"
printf 'old\n' > "$DELTAS/lib/a.py"
printf 'old\n' > "$DELTAS/lib/user.py"
git -C "$DELTAS" add -A && git -C "$DELTAS" commit -qm init
printf '{"dependencies":{"base":"1","user-added":"1"}}\n' > "$DELTAS/package.json"
printf 'user dirty\n' > "$DELTAS/lib/user.py"
turn_start "$DELTAS" turn-49 | python3 "$PATCH" >/dev/null
printf 'agent\n' > "$DELTAS/lib/a.py"
out=$(turn_stop "$DELTAS" turn-49 | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "49 dependency and trivial gates use turn delta" "$out" ;;
  *systemMessage*) ok "49 dependency and trivial gates use turn delta" ;;
  *) bad "49 dependency and trivial gates use turn delta" "$out" ;;
esac

# 50: staged, deleted and untracked paths are classified from the turn delta.
git -C "$DELTAS" reset -q --hard HEAD
turn_start "$DELTAS" turn-50-stage | python3 "$PATCH" >/dev/null
printf 'staged\n' > "$DELTAS/lib/a.py"
git -C "$DELTAS" add lib/a.py
out=$(turn_stop "$DELTAS" turn-50-stage | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "50 staged in-corridor delta -> allow" "$out" ;;
  *systemMessage*) ok "50 staged in-corridor delta -> allow" ;;
  *) bad "50 staged in-corridor delta -> allow" "$out" ;;
esac
git -C "$DELTAS" reset -q --hard HEAD
turn_start "$DELTAS" turn-50-delete | python3 "$PATCH" >/dev/null
rm "$DELTAS/lib/a.py"
out=$(turn_stop "$DELTAS" turn-50-delete | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "50b deleted in-corridor delta -> allow" "$out" ;;
  *systemMessage*) ok "50b deleted in-corridor delta -> allow" ;;
  *) bad "50b deleted in-corridor delta -> allow" "$out" ;;
esac
git -C "$DELTAS" reset -q --hard HEAD
turn_start "$DELTAS" turn-50-new | python3 "$PATCH" >/dev/null
mkdir -p "$DELTAS/other" && printf 'new\n' > "$DELTAS/other/new.py"
out=$(turn_stop "$DELTAS" turn-50-new | python3 "$PATCH")
case "$out" in
  *'"block"'*"other/new.py"*) ok "50c untracked out-of-corridor delta -> block" ;;
  *) bad "50c untracked out-of-corridor delta -> block" "$out" ;;
esac

# 51: renamed paths include the destination, so moving outside cannot hide it.
rm -rf "$DELTAS/other"
git -C "$DELTAS" reset -q --hard HEAD
turn_start "$DELTAS" turn-51 | python3 "$PATCH" >/dev/null
mkdir -p "$DELTAS/other" && git -C "$DELTAS" mv lib/a.py other/a.py
out=$(turn_stop "$DELTAS" turn-51 | python3 "$PATCH")
case "$out" in
  *'"block"'*"other/a.py"*) ok "51 renamed destination outside corridor -> block" ;;
  *) bad "51 renamed destination outside corridor -> block" "$out" ;;
esac

# 52: turn ids are isolated; a later baseline cannot overwrite an earlier one.
git -C "$DELTAS" reset -q --hard HEAD
rm -rf "$DELTAS/other"
turn_start "$DELTAS" turn-52-a | python3 "$PATCH" >/dev/null
mkdir -p "$DELTAS/other" && printf 'outside\n' > "$DELTAS/other/a.py"
turn_start "$DELTAS" turn-52-b | python3 "$PATCH" >/dev/null
out_b=$(turn_stop "$DELTAS" turn-52-b | python3 "$PATCH")
out_a=$(turn_stop "$DELTAS" turn-52-a | python3 "$PATCH")
case "$out_b|$out_a" in
  *systemMessage*'|'*'"block"'*"other/a.py"*) ok "52 turn baselines are isolated" ;;
  *) bad "52 turn baselines are isolated" "$out_b | $out_a" ;;
esac

# 53: missing baseline keeps the strict HEAD fallback and says coverage partial.
out=$(turn_stop "$DELTAS" missing-53 | python3 "$PATCH")
case "$out" in
  *'"block"'*"other/a.py"*"coverage partial"*) ok "53 missing baseline -> strict partial fallback" ;;
  *) bad "53 missing baseline -> strict partial fallback" "$out" ;;
esac

# 54: high independent checks time out and report the independent gate.
HIGH_TIMEOUT="$(mkrepo)"
mkdir -p "$HIGH_TIMEOUT/.slime" "$HIGH_TIMEOUT/lib"
cat > "$HIGH_TIMEOUT/.slime/corridor.md" <<'EOF'
# Corridor: high-timeout
## Rigor
high
## Outcome
The risky path is checked independently.
## Paths
- lib/**
## Evidence
- Supports: the focused trace reaches this path.
- Would falsify: the trace bypasses this path.
## Stop Condition
- Check: primary
## High-risk Controls
- Failure mode: requests fail.
- Rollback: revert the commit.
- Independent check: integration
EOF
write_checks "$HIGH_TIMEOUT" '{"schema":1,"checks":{"primary":{"argv":["python3","-c","raise SystemExit(0)"]},"integration":{"argv":["python3","-c","import time; time.sleep(5)"],"timeout_seconds":600}}}'
printf 'old\n' > "$HIGH_TIMEOUT/lib/a.py"
git -C "$HIGH_TIMEOUT" add -A && git -C "$HIGH_TIMEOUT" commit -qm init
printf 'new\n' > "$HIGH_TIMEOUT/lib/a.py"
out=$(stop "$HIGH_TIMEOUT" | SLIME_TEST_TIMEOUT=1 python3 "$PATCH")
case "$out" in
  *'"block"'*"Independent check"*"timed out"*) ok "54 independent check timeout -> block" ;;
  *) bad "54 independent check timeout -> block" "$out" ;;
esac

# 43: normal has no arbitrary file-count threshold when every file is in scope.
NORM="$(mkrepo)"
mkdir -p "$NORM/.slime" "$NORM/lib"
cat > "$NORM/.slime/corridor.md" <<'EOF'
# Corridor: broad-normal
## Rigor
normal
## Outcome
Generated values are current while public APIs remain stable.
## Paths
- lib/**
## Evidence
- Supports: the generator owns these files.
- Would falsify: a hand-owned file appears.
## Stop Condition
- Manual: generated output check passes.
EOF
for i in $(seq 1 13); do printf 'old\n' > "$NORM/lib/$i.txt"; done
git -C "$NORM" add -A && git -C "$NORM" commit -qm init
for i in $(seq 1 13); do printf 'new\n' > "$NORM/lib/$i.txt"; done
out=$(stop "$NORM" | python3 "$PATCH")
case "$out" in
  *'"block"'*) bad "43 broad normal inside explicit corridor -> allow" "$out" ;;
  *"rigor mismatch"*) bad "43 normal has no arbitrary count warning" "$out" ;;
  *systemMessage*) ok "43 broad normal inside explicit corridor -> allow" ;;
  *) bad "43 broad normal inside explicit corridor -> allow" "$out" ;;
esac

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
