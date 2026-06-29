#!/usr/bin/env bash
# Regression tests for the removed --with-cg pairing flag.
# Run: tests/test-cg-install.sh   (needs bash).
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

rejects_flag() {
  local label="$1"
  shift
  local home proj out rc
  home="$(mktmp)"
  proj="$(mktmp)"

  out=$(HOME="$home" bash "$INSTALL" "$proj" "$@" 2>&1)
  rc=$?

  if [ "$rc" -ne 0 ] && grep -q 'unknown flag: --with-cg' <<<"$out"; then
    ok "$label"
  else
    bad "$label" "exit=$rc output=$out"
  fi

  if [ ! -e "$home/.claude" ] && [ ! -e "$proj/.claude" ]; then
    ok "$label leaves no hook config behind"
  else
    bad "$label leaves no hook config behind" "home=$home proj=$proj"
  fi
}

rejects_flag "1  --with-cg <path> is rejected" --with-cg "$(mktmp)"
rejects_flag "2  --with-cg=<path> is rejected" --with-cg="$(mktmp)"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ]
