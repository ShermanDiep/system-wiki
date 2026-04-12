#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${PYTHON_BIN:-}" ]]; then
  PYTHON_BIN="$PYTHON_BIN"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PYTHON_BIN="$ROOT/.venv/bin/python"
else
  PYTHON_BIN="$ROOT/../.venv/bin/python"
fi
TARGET="${1:-.}"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "[smoke] Missing Python environment at $PYTHON_BIN"
  echo "[smoke] Create it first, for example:"
  echo "  python3 -m venv .venv"
  exit 1
fi

cd "$ROOT"

echo "[smoke] Building wiki for $TARGET"
"$PYTHON_BIN" -m system_wiki "$TARGET"

echo "[smoke] Query stats"
"$PYTHON_BIN" -m system_wiki query stats

echo "[smoke] Lint graph"
"$PYTHON_BIN" -m system_wiki lint

echo "[smoke] OK"
