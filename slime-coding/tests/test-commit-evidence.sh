#!/usr/bin/env bash
# Behavioural tests for commit-message Slime evidence.
# Run: tests/test-commit-evidence.sh   (needs bash, python3, git)
set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVIDENCE="$ROOT/bin/commit-evidence"
INSTALL="$ROOT/install.sh"

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

R="$(mkrepo)"
mkdir -p "$R/.slime" "$R/lib" "$R/test"
cat > "$R/.slime/corridor.md" <<'EOF'
# Corridor: login-redirect

## Scope
Redirect expired sessions to login.

## Semantic Delta
- This task changes: expired session requests now redirect to login.
- This task preserves: existing auth API and session storage.

## Non-goals
- Do not add a new auth provider or config system.

## Paths
- lib/auth/**
- test/auth/**

## Goal Frontier
- Expired session request redirects to login.

## Start Frontier
- lib/auth/session.py:handle_session

## Stop Condition
- pytest test/auth/test_session.py
EOF
printf '# Pruned\n' > "$R/.slime/PRUNED.md"
git -C "$R" add . && git -C "$R" commit -qm init

mkdir -p "$R/lib/auth"
printf 'x = 1\n' > "$R/lib/auth/session.py"
git -C "$R" add lib/auth/session.py
MSG="$R/msg.txt"
printf 'Fix expired session redirect\n' > "$MSG"

(cd "$R" && python3 "$EVIDENCE" "$MSG")
out="$(cat "$MSG")"

if grep -q 'Slime-Corridor: login-redirect' "$MSG" &&
   grep -q 'Slime-Scope: Redirect expired sessions to login.' "$MSG" &&
   grep -q 'Slime-Delta: expired session requests now redirect to login.' "$MSG" &&
   grep -q 'Slime-Preserves: existing auth API and session storage.' "$MSG" &&
   grep -Fq 'Slime-Paths: lib/auth/**, test/auth/**' "$MSG" &&
   grep -q 'Slime-Touched-Files: 1' "$MSG" &&
   grep -q 'Slime-Out-Of-Corridor: 0' "$MSG" &&
   grep -q 'Slime-New-Dependencies: none' "$MSG" &&
   grep -q 'Slime-Verification: pytest test/auth/test_session.py' "$MSG"; then
  ok "1  commit evidence appends corridor and diff facts"
else
  bad "1  commit evidence appends corridor and diff facts" "$out"
fi

(cd "$R" && python3 "$EVIDENCE" "$MSG")
count="$(grep -c 'Slime-Corridor:' "$MSG")"
[ "$count" -eq 1 ] && ok "2  commit evidence is idempotent" || bad "2  commit evidence is idempotent" "count=$count"

printf '' > "$MSG"
(cd "$R" && python3 "$EVIDENCE" "$MSG")
if grep -q 'Slime-Corridor: login-redirect' "$MSG"; then
  ok "2b empty commit message still gets evidence"
else
  bad "2b empty commit message still gets evidence" "$(cat "$MSG")"
fi

mkdir -p "$R/scripts"
printf 'print(1)\n' > "$R/scripts/tool.py"
git -C "$R" add scripts/tool.py
printf 'Add helper\n' > "$MSG"
(cd "$R" && python3 "$EVIDENCE" "$MSG")
out="$(cat "$MSG")"
case "$out" in
  *"Slime-Out-Of-Corridor: 1 (scripts/tool.py)"*) ok "3  commit evidence reports out-of-corridor staged file" ;;
  *) bad "3  commit evidence reports out-of-corridor staged file" "$out" ;;
esac

S="$(mkrepo)"
mkdir -p "$S/.git/hooks"
cat > "$S/.git/hooks/prepare-commit-msg" <<'EOF'
#!/usr/bin/env bash
echo existing >> "$1"
EOF
chmod +x "$S/.git/hooks/prepare-commit-msg"

bash "$INSTALL" "$S" >/dev/null
hook="$(cat "$S/.git/hooks/prepare-commit-msg")"
if grep -q 'Slime Coding commit evidence' "$S/.git/hooks/prepare-commit-msg" &&
   grep -q 'commit-evidence' "$S/.git/hooks/prepare-commit-msg" &&
   grep -q 'echo existing' "$S/.git/hooks/prepare-commit-msg"; then
  ok "4  install wires prepare-commit-msg without dropping existing hook"
else
  bad "4  install wires prepare-commit-msg without dropping existing hook" "$hook"
fi

bash "$INSTALL" "$S" >/dev/null
count="$(grep -c '# >>> Slime Coding commit evidence' "$S/.git/hooks/prepare-commit-msg")"
[ "$count" -eq 1 ] && ok "5  install is idempotent for prepare-commit-msg" || bad "5  install is idempotent for prepare-commit-msg" "count=$count"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
