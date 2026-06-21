#!/usr/bin/env bash
# Behavioural tests for experiments/slime-bench (the controlled-benchmark
# runner). Same style as tests/test.sh: temp dirs, JSON / stdout assertions,
# no framework. Run: tests/test-bench.sh   (needs python3, git, and bash).
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BENCH="$ROOT/experiments/slime-bench"

pass=0
fail=0
ok()   { printf '  ok   %s\n' "$1"; pass=$((pass + 1)); }
bad()  { printf 'FAIL   %s\n         got: %s\n' "$1" "$2"; fail=$((fail + 1)); }

TMP_DIRS=()
mktmp() { local d; d="$(mktemp -d)"; TMP_DIRS+=("$d"); printf '%s' "$d"; }
cleanup() { for d in "${TMP_DIRS[@]:-}"; do rm -rf "$d"; done; }
trap cleanup EXIT

# === 1. plan ================================================================
out=$(python3 "$BENCH" plan T1 --conditions baseline,prompt-only --runs 2 2>&1)
n=$(printf '%s\n' "$out" | grep -c .)
[ "$n" = "4" ] && ok "1  plan: 2 conditions x 2 runs -> 4 lines" \
               || bad "1  plan: 2 conditions x 2 runs -> 4 lines" "n=$n out=$out"

# === 2. new-cell baseline ===================================================
ROOT_RUNS=$(mktmp)
CELL_A=$(python3 "$BENCH" new-cell --task T1 --condition baseline --run 1 \
          --fixture cli-notes --root "$ROOT_RUNS" 2>&1 | tail -1)
if [ -d "$CELL_A/.git" ] && [ ! -f "$CELL_A/.claude/settings.json" ]; then
  ok "2  new-cell baseline: git baseline + no settings.json"
else
  bad "2  new-cell baseline: git baseline + no settings.json" "cell=$CELL_A"
fi

# === 3. new-cell prompt-only ================================================
# The L0 discipline must land in CLAUDE.md (the file Claude Code auto-loads),
# not a bare CLAUDE.slime.md (which a nested `claude -p` run never reads). An
# empirical probe confirmed an unloaded CLAUDE.slime.md leaves the agent with no
# active discipline — that would silently collapse condition B onto baseline A.
CELL_B=$(python3 "$BENCH" new-cell --task T1 --condition prompt-only --run 1 \
          --fixture cli-notes --root "$ROOT_RUNS" 2>&1 | tail -1)
if [ -d "$CELL_B/.git" ] \
    && [ -e "$CELL_B/.claude/skills/slime-navigate" ] \
    && [ -e "$CELL_B/.claude/commands/slime-corridor.md" ] \
    && [ -f "$CELL_B/CLAUDE.md" ] \
    && grep -q "Meeting Corridor" "$CELL_B/CLAUDE.md" \
    && [ ! -f "$CELL_B/.claude/settings.json" ]; then
  ok "3  new-cell prompt-only: skill + commands + discipline in CLAUDE.md, no settings.json"
else
  bad "3  new-cell prompt-only: skill + commands + discipline in CLAUDE.md, no settings.json" \
      "cell=$CELL_B"
fi

# === 4. new-cell hooked-slime ==============================================
# C is the full stack: hooks AND the L0 discipline in CLAUDE.md (so the prose
# the gates back up is actually loaded).
CELL_C=$(python3 "$BENCH" new-cell --task T1 --condition hooked-slime --run 1 \
          --fixture cli-notes --root "$ROOT_RUNS" 2>&1 | tail -1)
if [ -f "$CELL_C/.claude/settings.json" ] \
    && grep -q prune-inject "$CELL_C/.claude/settings.json" \
    && grep -q patch-cost   "$CELL_C/.claude/settings.json" \
    && [ -f "$CELL_C/CLAUDE.md" ] \
    && grep -q "Meeting Corridor" "$CELL_C/CLAUDE.md"; then
  ok "4  new-cell hooked-slime: prune-inject + patch-cost wired + discipline in CLAUDE.md"
else
  bad "4  new-cell hooked-slime: prune-inject + patch-cost wired + discipline in CLAUDE.md" "cell=$CELL_C"
fi

# === 5. new-cell hooked-no-l1 ==============================================
CELL_D=$(python3 "$BENCH" new-cell --task T1 --condition hooked-no-l1 --run 1 \
          --fixture cli-notes --root "$ROOT_RUNS" 2>&1 | tail -1)
if [ -f "$CELL_D/.claude/settings.json" ] \
    && ! grep -q prune-inject "$CELL_D/.claude/settings.json" \
    && grep -q patch-cost     "$CELL_D/.claude/settings.json"; then
  ok "5  new-cell hooked-no-l1: patch-cost only, prune-inject removed"
else
  bad "5  new-cell hooked-no-l1: patch-cost only, prune-inject removed" "cell=$CELL_D"
fi

# === 6. measure =============================================================
# Make a fake agent edit in the baseline cell, then measure.
mkdir -p "$CELL_A/cli_notes"
printf '\n# slime-bench test edit\n' >> "$CELL_A/cli_notes/__init__.py"
python3 "$BENCH" measure "$CELL_A" >/dev/null 2>&1
if [ -f "$CELL_A/metrics.json" ]; then
  touched=$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1]))["touched_files"])' \
              "$CELL_A/metrics.json" 2>/dev/null)
  if [ -n "$touched" ] && [ "$touched" -ge 1 ]; then
    ok "6  measure: metrics.json written, touched_files=$touched"
  else
    bad "6  measure: touched_files not >= 1" "touched=$touched"
  fi
else
  bad "6  measure: metrics.json not written" "missing"
fi

# === 7. validate good (auto-filled human-judged fields so schema passes) ====
FILLED="$CELL_A/metrics-filled.json"
python3 - "$CELL_A/metrics.json" "$FILLED" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m.update(task_success=True, tests_pass=True, pruned_path_revived=False,
         unrelated_refactor_count=0, over_implementation_review=0,
         reviewer_accept=True, manual_reverts_required=0, blocks_count=0,
         false_block_count=0, manual_steps=0, turn_count=5,
         task_success_score=2, notes="test")
json.dump(m, open(sys.argv[2], "w"))
PY
python3 "$BENCH" validate "$FILLED" >/dev/null 2>&1
[ $? -eq 0 ] && ok "7  validate filled metrics.json -> exit 0" \
             || bad "7  validate filled metrics.json -> exit 0" "exit $?"

# === 8. validate bad (missing required fields) ==============================
BADDIR=$(mktmp); BAD="$BADDIR/bad.json"
printf '{"task_id":"T1","condition":"baseline","run_id":1}\n' > "$BAD"
python3 "$BENCH" validate "$BAD" >/dev/null 2>&1
[ $? -ne 0 ] && ok "8  validate bad metrics.json -> non-zero" \
             || bad "8  validate bad metrics.json -> non-zero" "exited 0"

# === 9. aggregate ===========================================================
# Use the filled file under CELL_A so aggregate has at least one row.
cp "$FILLED" "$CELL_A/metrics.json"
out=$(python3 "$BENCH" aggregate "$ROOT_RUNS" 2>&1)
case "$out" in
  *"| task"*"| condition"*"| run"*) ok "9  aggregate: markdown table header present" ;;
  *) bad "9  aggregate: markdown table header" "$out" ;;
esac

# === 10. plan rejects unknown condition ====================================
python3 "$BENCH" plan T1 --conditions baseline,zzz --runs 1 >/dev/null 2>&1
[ $? -ne 0 ] && ok "10 plan: unknown condition -> non-zero" \
             || bad "10 plan: unknown condition -> non-zero" "exit 0"

# === 11. new-cell rejects (task, condition, run) collision =================
# Re-using the existing CELL_A cell — second new-cell with same coords must fail.
python3 "$BENCH" new-cell --task T1 --condition baseline --run 1 \
        --fixture cli-notes --root "$ROOT_RUNS" >/dev/null 2>&1
[ $? -ne 0 ] && ok "11 new-cell: existing cell -> non-zero (no silent overwrite)" \
             || bad "11 new-cell: existing cell -> non-zero" "exit 0"

# === 12. validate catches int-in-boolean-field =============================
# task_success is schema-type boolean. `1` is int, not bool, and a record with
# task_success: 1 must NOT be accepted — that's the anti-fabrication guard.
INTBOOL="$BADDIR/intbool.json"
python3 - "$FILLED" "$INTBOOL" <<'PY'
import json, sys
m = json.load(open(sys.argv[1]))
m["task_success"] = 1
json.dump(m, open(sys.argv[2], "w"))
PY
python3 "$BENCH" validate "$INTBOOL" >/dev/null 2>&1
[ $? -ne 0 ] && ok "12 validate: int in boolean field -> non-zero" \
             || bad "12 validate: int in boolean field -> non-zero" "exit 0"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
