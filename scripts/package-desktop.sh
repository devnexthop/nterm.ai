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
if [[ ! -x backend/.venv/bin/python && ! -x backend/.venv/Scripts/python.exe ]]; then
  python3 -m venv backend/.venv
fi
PY=backend/.venv/bin/python
[[ -x backend/.venv/Scripts/python.exe ]] && PY=backend/.venv/Scripts/python.exe
"$PY" -m pip install -r backend/requirements.txt -r backend/requirements-build.txt
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
