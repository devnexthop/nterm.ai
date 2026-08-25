# PyInstaller spec — run from relay/backend
#   pyinstaller nterm-engine.spec

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
root = Path(".").resolve()
static = root / "app" / "static"

hidden = []
for pkg in ("uvicorn", "anyio", "starlette", "fastapi", "asyncssh", "cryptography", "sqlalchemy", "pydantic", "openai", "httpx"):
    hidden += collect_submodules(pkg)

datas = []
if static.exists():
    datas.append((str(static), "static"))

a = Analysis(
    ["engine_entry.py"],
    pathex=[str(root)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden + ["app.engine", "app.main", "engineio"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="nterm-engine",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    name="nterm-engine",
)
