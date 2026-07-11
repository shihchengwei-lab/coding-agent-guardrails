#!/usr/bin/env bash
# Low-friction Guardrails hook contract. Needs Python 3.11+ and git.
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PATCH="$ROOT/bin/patch-cost"
export PYTHONPATH="$(cd "$ROOT/../agentcam/src" && pwd)${PYTHONPATH:+:$PYTHONPATH}"
pass=0
fail=0
ok() { printf '  ok   %s\n' "$1"; pass=$((pass + 1)); }
bad() { printf 'FAIL   %s\n         got: %s\n' "$1" "$2"; fail=$((fail + 1)); }
TMP_DIRS=()
mkrepo() {
  local d
  d="$(mktemp -d)"
  TMP_DIRS+=("$d")
  git -C "$d" init -q -b main
  git -C "$d" config user.email test@example.com
  git -C "$d" config user.name Test
  printf 'base\n' > "$d/base.txt"
  git -C "$d" add . && git -C "$d" commit -qm base
  printf '%s' "$d"
}
cleanup() { for d in "${TMP_DIRS[@]:-}"; do rm -rf "$d"; done; }
trap cleanup EXIT
hostpath() { cygpath -m "$1" 2>/dev/null || printf '%s' "$1"; }
start() { printf '{"hook_event_name":"UserPromptSubmit","turn_id":"%s","session_id":"s","prompt":"work","cwd":"%s"}' "$2" "$(hostpath "$1")"; }
stop() { printf '{"hook_event_name":"Stop","turn_id":"%s","session_id":"s","cwd":"%s"}' "$2" "$(hostpath "$1")"; }
pre() { printf '{"hook_event_name":"PreToolUse","turn_id":"%s","tool_name":"Write","tool_input":{"file_path":"%s"},"cwd":"%s"}' "$2" "$(hostpath "$3")" "$(hostpath "$1")"; }
post() { printf '{"hook_event_name":"PostToolUse","turn_id":"%s","tool_name":"Bash","cwd":"%s"}' "$2" "$(hostpath "$1")"; }

R="$(mkrepo)"
start "$R" routine | python3 "$PATCH" >/dev/null
out=$(pre "$R" routine "$R/src/app.py" | python3 "$PATCH")
case "$out" in *'"deny"'*"internal scope set"*) ok "1 missing intent gives agent-facing remedy" ;; *) bad "1 missing intent" "$out" ;; esac

python3 "$PATCH" scope set --repo "$(hostpath "$R")" --outcome "app changes" --path src/app.py
out=$(pre "$R" routine "$R/src/app.py" | python3 "$PATCH")
[ -z "$out" ] && ok "2 declared direct edit is allowed" || bad "2 declared direct edit" "$out"
out=$(pre "$R" routine "$R/other.py" | python3 "$PATCH")
case "$out" in *'"deny"'*"scope add"*) ok "3 outside direct edit is denied" ;; *) bad "3 outside direct edit" "$out" ;; esac

mkdir -p "$R/src" && printf 'changed = True\n' > "$R/src/app.py"
out=$(stop "$R" routine | python3 "$PATCH")
case "$out" in *"Guardrails ready"*"review.json"*) ok "4 Stop creates review artifact" ;; *) bad "4 Stop creates review artifact" "$out" ;; esac
python3 - "$R/.guardrails/review.json" <<'PY'
import json,sys
data=json.load(open(sys.argv[1],encoding="utf-8"))
assert data["schema"] == 1
assert data["delivery"]["scope"] == ["src/app.py"]
assert data["verification"]["level"] == "structural-only"
PY
[ $? -eq 0 ] && ok "5 artifact has low-friction schema" || bad "5 artifact schema" "invalid"

H="$(mkrepo)"
start "$H" high | python3 "$PATCH" >/dev/null
python3 "$PATCH" scope set --repo "$(hostpath "$H")" --outcome "secure login" --path src/auth/login.py
mkdir -p "$H/src/auth" && printf 'secure = True\n' > "$H/src/auth/login.py"
out=$(stop "$H" high | python3 "$PATCH")
phrase=$(python3 -c 'import json,sys; print(json.load(sys.stdin)["reason"].splitlines()[-1])' <<<"$out")
case "$phrase" in "確認高風險變更 "*) ok "6 high risk asks once" ;; *) bad "6 high risk confirmation" "$out" ;; esac
printf '{"hook_event_name":"UserPromptSubmit","turn_id":"high","session_id":"s","prompt":"%s","cwd":"%s"}' "$phrase" "$(hostpath "$H")" | python3 "$PATCH" >/dev/null
out=$(stop "$H" high | python3 "$PATCH")
case "$out" in *"Guardrails ready"*) ok "7 exact user prompt releases high-risk Stop" ;; *) bad "7 high-risk release" "$out" ;; esac

S="$(mkrepo)"
start "$S" shell | python3 "$PATCH" >/dev/null
python3 "$PATCH" scope set --repo "$(hostpath "$S")" --outcome "app only" --path src/app.py
printf 'outside\n' > "$S/outside.txt"
out=$(post "$S" shell | python3 "$PATCH")
case "$out" in *'"block"'*"already occurred"*) ok "8 shell drift is reported after write" ;; *) bad "8 shell drift" "$out" ;; esac

C="$(mkrepo)"
start "$C" checks | python3 "$PATCH" >/dev/null
python3 "$PATCH" scope set --repo "$(hostpath "$C")" --outcome "checked" --path src/app.py
mkdir -p "$C/src" && printf 'changed\n' > "$C/src/app.py"
GITDIR=$(git -C "$C" rev-parse --absolute-git-dir)
mkdir -p "$GITDIR/guardrails"
printf '{"schema":1,"checks":{"primary":{"argv":["python3","-c","raise SystemExit(3)"],"timeout_seconds":30}}}' > "$GITDIR/guardrails/config.json"
out=$(stop "$C" checks | python3 "$PATCH")
case "$out" in *'"block"'*"primary failed"*) ok "9 red primary check blocks" ;; *) bad "9 red primary check" "$out" ;; esac

printf '\n%s passed, %s failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
