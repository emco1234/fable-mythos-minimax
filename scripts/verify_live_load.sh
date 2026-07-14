#!/usr/bin/env bash
# Bash wrapper for verify_live_load.py — locates a Python interpreter and runs
# the helper with `before` or `after` argument.
#
# Usage:
#   bash scripts/verify_live_load.sh before
#   bash scripts/verify_live_load.sh after
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

PY_BIN=""
for cand in python python3 py /c/Python313/python.exe; do
  if command -v "$cand" >/dev/null 2>&1; then
    PY_BIN="$(command -v "$cand")"
    break
  fi
done
if [[ -z "$PY_BIN" ]]; then
  echo "ERROR: python not found in PATH (tried python, python3, py, /c/Python313/python.exe)" >&2
  exit 1
fi

exec "$PY_BIN" "$SCRIPT_DIR/verify_live_load.py" "$@"
