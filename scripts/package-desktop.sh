#!/usr/bin/env bash
# Build the NTerm engine + Electron installer for the current OS.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== frontend =="
(cd frontend && npm install && npm run build)
rm -rf backend/app/static
mkdir -p backend/app/static
cp -R frontend/dist/. backend/app/static/

echo "== python engine =="
# PyInstaller 6.11.x needs Python <3.14. Prefer 3.12 when present (Homebrew Mac).
PY_BOOT="${PYTHON:-}"
if [[ -z "$PY_BOOT" ]]; then
  for candidate in python3.12 python3.13 python3; do
    if command -v "$candidate" >/dev/null 2>&1; then
      PY_BOOT="$candidate"
      break
    fi
  done
fi
[[ -n "$PY_BOOT" ]] || { echo "No python3 found"; exit 1; }

if [[ ! -x backend/.venv/bin/python && ! -x backend/.venv/Scripts/python.exe ]]; then
  if command -v uv >/dev/null 2>&1; then
    echo "Creating venv with uv (Python 3.12)…"
    (cd backend && uv venv --python 3.12 .venv)
  else
    echo "Using $PY_BOOT ($("$PY_BOOT" --version))"
    "$PY_BOOT" -m venv backend/.venv
  fi
fi
PY=backend/.venv/bin/python
[[ -x backend/.venv/Scripts/python.exe ]] && PY=backend/.venv/Scripts/python.exe
if command -v uv >/dev/null 2>&1; then
  uv pip install -r backend/requirements.txt -r backend/requirements-build.txt --python "$ROOT/$PY"
else
  "$PY" -m pip install -r backend/requirements.txt -r backend/requirements-build.txt
fi
(cd backend && "$ROOT/$PY" -m PyInstaller --noconfirm nterm-engine.spec)

echo "== stage engine for Electron =="
rm -rf desktop/engine
mkdir -p desktop/engine
cp -R backend/dist/nterm-engine/. desktop/engine/

echo "== electron installer =="
(cd desktop && npm install)
TARGET="${1:-}"
if [[ -z "$TARGET" ]]; then
  case "$(uname -s)" in
    Darwin) TARGET=dist:mac ;;
    MINGW*|MSYS*|CYGWIN*|Windows_NT) TARGET=dist:win ;;
    *) TARGET=dist:linux ;;
  esac
fi
(cd desktop && npm run "$TARGET")
echo "Installers in desktop/release/"
ls -la desktop/release || true
